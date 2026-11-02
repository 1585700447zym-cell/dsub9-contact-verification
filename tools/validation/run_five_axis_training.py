"""Bounded first F5 development training. --run is a separate manual launch."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.learning.five_axis_preparation import (OUT, RUNTIME, COMMON, training_plan, check_ready,
    verify_inputs, read, sha, audit_archive, canonical, validate_resume_boundary)


def select():
    from tools.learning.runtime import select_runtime, verify_runtime, active_package
    select_runtime(RUNTIME, expected_digest=sha(RUNTIME)); return verify_runtime(active_package())


def run(*, resume_boundary=False):
    from tools.validation.run_yaw_pilot import write, publish_archive, actual_common, model_archive_bytes
    select(); admission, reg = check_ready()
    destination = OUT / 'training'
    from tools.learning.five_axis_checkpoint import load_checkpoint, save_checkpoint
    from tools.learning.five_axis_session import session_class
    from tools.learning.five_axis_collection import CollectionError
    from tools.learning.newton_profile import build_model_xml
    from tools.validation.yaw_pilot import environment_class, YawContactCase
    if resume_boundary:
        ledger = read(destination / 'ledger.json'); latest = read(destination / 'latest.json')
        start_index = validate_resume_boundary(destination, ledger, latest,
            sha(OUT / 'registration.json'), sha(OUT / 'admission.json'))
        trainer = load_checkpoint(destination / latest['checkpoint'], expected_digest=latest['digest'],
                                  config=reg['training_plan']['config'])
        if trainer.update_attempts != ledger['training_updates']: raise ValueError('Update boundary differs')
    else:
        destination.mkdir()  # Never overwrite/restart a partial training run.
        start_index = 0
        trainer = load_checkpoint(OUT / 'initial_checkpoint', expected_digest=admission['checkpoint_digest'],
                                  config=reg['training_plan']['config'])
        ledger = dict(status='RUNNING', episodes=[], initialization_attempts=0, physical_substeps=0,
                      policy_calls=0, warmup_draws=0, training_updates=0, formal_training_started=True,
                      batch_started_unix_s=time.time(), preparation_admission_sha256=sha(OUT / 'admission.json'))
    ledger['status'] = 'RUNNING'
    write(destination / 'ledger.json', ledger); started = time.monotonic()
    def batch_elapsed(): return time.time() - ledger['batch_started_unix_s']
    try:
        for index, job in enumerate(reg['training_plan']['schedule']):
            if index < start_index: continue
            verify_inputs(reg['inputs'])
            if batch_elapsed() > 21600 or (OUT / 'STOP').exists():
                raise RuntimeError('Batch wall/external bound reached')
            folder = destination / job['id']; folder.mkdir(); env = session = None; raw = {}
            receipt = dict(case_id=job['id'], status='initializing', reset_attempted=0,
                physical_substeps=0, valid=False, stopped=False, policy_calls=0, training_updates=0)
            before_calls, before_draws = trainer.policy_calls, trainer.warmup_draws
            episode_start = time.monotonic()
            try:
                env = environment_class()(); model_bytes = model_archive_bytes(build_model_xml(env.profile))
                (folder / 'model_used.xml').write_bytes(model_bytes)
                receipt.update(actual_common(env, select(), model_bytes))
                if any(canonical(receipt[key]) != canonical(reg['common'][key]) for key in COMMON):
                    raise ValueError('Training domain differs')
                Base = session_class()
                class BoundedSession(Base):
                    def advance_cycle(self, action):
                        if (time.monotonic() - episode_start > 1800 or batch_elapsed() > 21600
                                or (OUT / 'STOP').exists()): raise RuntimeError('Runtime bound; no retry')
                        result = super().advance_cycle(action)
                        if self.cycle_id % 100 == 0:
                            write(folder / 'progress.json', dict(cycles=self.cycle_id,
                                physical_substeps=env.physical_steps, reset_attempted=1,
                                policy_calls=trainer.policy_calls - before_calls,
                                warmup_draws=trainer.warmup_draws - before_draws))
                        return result
                session = BoundedSession(env); point = YawContactCase(**job['case'])
                receipt.update(case=asdict(point), reset_attempted=1)
                write(folder / 'receipt.json', receipt)
                raw = trainer.collect(session, point, seed=reg['training_plan']['config']['learning']['seed'] + index,
                    max_cycles=14500, deterministic=job['stage'] == 'development', warmup=job['stage'] == 'warmup')
                receipt.update(status='finished', valid=raw['outcome']['simulation_valid'],
                    stopped=raw['outcome']['physical_stopped'], outcome=raw['outcome']['task_outcome'],
                    physical_substeps=env.physical_steps, guard_facts=env.guard_facts,
                    final_reason=session.reason, finish_criteria=session.finish_criteria)
            except CollectionError as exc:
                raw = exc.archive; receipt.update(status='error', error=repr(exc)); raise
            except BaseException as exc:
                receipt.update(status='error', error=repr(exc)); raise
            finally:
                if env is not None:
                    receipt.update(physical_substeps=getattr(env, 'physical_steps', 0), guard_facts=env.guard_facts,
                                   control_cycles=getattr(session, 'cycle_id', 0))
                receipt.update(elapsed_wall_s=time.monotonic() - episode_start,
                    policy_calls=trainer.policy_calls - before_calls, warmup_draws=trainer.warmup_draws - before_draws)
                ledger['initialization_attempts'] += receipt['reset_attempted']
                ledger['physical_substeps'] += receipt['physical_substeps']
                ledger['policy_calls'] = trainer.policy_calls; ledger['warmup_draws'] = trainer.warmup_draws
                ledger['episodes'].append(receipt)
                publish_archive(folder, raw, receipt); write(destination / 'ledger.json', ledger)
            # Read the published bytes back before granting replay publication.
            raw, receipt, audit = audit_archive(folder, reg)
            write(folder / 'audit.json', dict(audit, archive_sha256=receipt['archive_sha256'],
                admission_sha256=sha(OUT / 'admission.json')))
            if job['publish']:
                outcome = dict(raw['outcome'], valid_for_learning=True)
                publication = trainer.publish(job['id'], raw['transitions'], outcome=outcome, training_admitted=True)
                write(folder / 'publication.json', dict(publication, archive_sha256=receipt['archive_sha256'],
                    audit_sha256=sha(folder / 'audit.json'), admission_sha256=sha(OUT / 'admission.json')))
            for _ in range(job['updates_after']):
                if batch_elapsed() > 21600 or (OUT / 'STOP').exists(): raise RuntimeError('Update bound')
                trainer.update_from_replay()
                ledger['training_updates'] = trainer.update_attempts
            digest = save_checkpoint(trainer, destination / ('checkpoint_' + str(index + 1)))
            write(destination / 'latest.json', dict(next_schedule_index=index + 1, digest=digest,
                checkpoint='checkpoint_' + str(index + 1), registration_sha256=sha(OUT / 'registration.json'),
                admission_sha256=sha(OUT / 'admission.json')))
            write(destination / 'ledger.json', ledger)
            print(json.dumps(dict(episode=job['id'], outcome=receipt['outcome'], updates=trainer.update_attempts)), flush=True)
        ledger['status'] = 'COMPLETED'
    except BaseException as exc:
        ledger.update(status='STOPPED', error=repr(exc)); raise
    finally:
        ledger.update(training_updates=trainer.update_attempts, policy_calls=trainer.policy_calls,
                      warmup_draws=trainer.warmup_draws, elapsed_wall_s=time.monotonic() - started)
        write(destination / 'ledger.json', ledger)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--describe', action='store_true'); group.add_argument('--check-ready', action='store_true')
    group.add_argument('--run', action='store_true'); group.add_argument('--resume-boundary', action='store_true')
    args = parser.parse_args(argv)
    if args.describe: print(json.dumps(training_plan(), ensure_ascii=False, indent=2)); return 0
    if args.check_ready:
        select(); check_ready(); print(json.dumps(dict(ready=True, formal_training_started=False))); return 0
    run(resume_boundary=args.resume_boundary); return 0


if __name__ == '__main__': raise SystemExit(main())
