"""Three one-shot physical qualifications; never start formal training."""
import argparse
from dataclasses import asdict
import gzip
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.learning.five_axis_preparation import (OUT, PARENT, RUNTIME, AUDITOR, COMMON, KINDS,
    preparation_scope, training_plan, qualification_action, verify_inputs, read, sha,
    audit_archive, compare_zero_trace, check_ready, freeze_sources)
from tools.validation.run_yaw_pilot import (write, publish_archive, actual_common, model_archive_bytes,
    supervise, NoLearning, reconcile_receipt)

PYTHON = ROOT / 'tmp/learning_cpu_20260924/Scripts/python.exe'


def select():
    from tools.learning.runtime import select_runtime, verify_runtime, active_package
    select_runtime(RUNTIME, expected_digest=sha(RUNTIME))
    return verify_runtime(active_package())


def prepare():
    OUT.mkdir(parents=True, exist_ok=False)
    paths = list((ROOT / 'tools').rglob('*.py')) + list((ROOT / 'models').rglob('*.xml'))
    paths += [PARENT, RUNTIME, AUDITOR, AUDITOR.with_name('newton_contract.py'),
        ROOT / 'docs/stage_b/五维残差SAC执行补充合同_v1.md',
        ROOT / 'deliverables/learning_chain/five_axis_residual_implementation_20261023/verification_manifest.json']
    for name in ('YAW_P10', 'YAW_M10', 'YAW_P15', 'YAW_M15'):
        paths += [PARENT.parent.parent / name / file for file in ('episode.json.gz', 'receipt.json')]
    pins = freeze_sources(paths, snapshot_only=[ROOT / 'docs/superpowers/plans/2026-10-23-five-axis-pretraining-readiness.md'],
                          folder=OUT / 'source_snapshot')
    parent = read(PARENT)
    reg = dict(scope=preparation_scope(), training_plan=training_plan(), inputs=pins,
        common={key: parent[key] for key in COMMON}, runtime_sha256=sha(RUNTIME),
        authorization='User requested all pretraining validation/preparation on 2026-10-23; no formal training',
        formal_training_started=False)
    write(OUT / 'registration.json', reg)
    write(OUT / 'ledger.json', dict(status='PREPARED', episodes=[], actual_initialization_attempts=0,
        physical_substeps=0, cumulative_initialization_attempts=372))
    print(json.dumps(dict(status='PREPARED', max_initializations=3, formal_training=False)), flush=True)


def worker(kind):
    if kind not in KINDS: raise ValueError('Registered kind required')
    reg = read(OUT / 'registration.json'); verify_inputs(reg['inputs'])
    folder = OUT / 'run' / kind
    with (folder / 'worker.claim').open('x') as handle: handle.write(str(os.getpid()))
    sys.meta_path.insert(0, NoLearning())
    receipt = dict(case_id=kind, status='initializing', reset_attempted=0, reset_completed=0,
        physical_substeps=0, control_cycles=0, policy_calls=0, training_updates=0,
        valid=False, stopped=False, audit_passed=False)
    raw = {}; env = session = None; started = time.monotonic()
    write(folder / 'receipt.json', receipt)
    try:
        proof = select()
        from tools.validation.yaw_pilot import environment_class, pilot_cases
        from tools.learning.five_axis_session import session_class
        from tools.learning.five_axis_collection import collect_episode, CollectionError
        from tools.learning.newton_profile import build_model_xml
        env = environment_class()(); model_bytes = model_archive_bytes(build_model_xml(env.profile))
        (folder / 'model_used.xml').write_bytes(model_bytes)
        receipt.update(actual_common(env, proof, model_bytes))
        if any(receipt[key] != reg['common'][key] for key in COMMON): raise ValueError('Physical baseline differs')
        Base = session_class()
        class BoundedSession(Base):
            def advance_cycle(self, action):
                if time.monotonic() - started > 1800 or (OUT / 'STOP').exists():
                    raise RuntimeError('Wall/external stop; no retry')
                result = super().advance_cycle(action)
                if kind != 'ZERO_P10' and self.cycle_id == 300:
                    self.start_external_tail()
                    result.next_snapshot = self.prepare_cycle()
                if self.cycle_id % 100 == 0:
                    write(folder / 'progress.json', dict(cycles=self.cycle_id,
                        time_s=float(env.data.time), phase=self.controller.phase, reset_attempted=1,
                        physical_substeps=env.physical_steps))
                return result
        session = BoundedSession(env)
        point = pilot_cases()[1 if kind == 'PULSE_M10' else 0]
        receipt.update(case=asdict(point), reset_attempted=1)
        write(folder / 'receipt.json', receipt)
        try:
            raw = collect_episode(session, point,
                policy=lambda _: qualification_action(kind, session.cycle_id),
                seed=reg['scope']['seed'], max_cycles=14500)
        except CollectionError as exc:
            raw = exc.archive
            raise
        receipt.update(status='finished', reset_completed=1, valid=raw['outcome']['simulation_valid'],
            stopped=raw['outcome']['physical_stopped'], outcome=raw['outcome']['task_outcome'],
            final_reason=session.reason, controller_metadata=session.controller.metadata(),
            finish_criteria=session.finish_criteria, stop_time_s=session.stop_time,
            task_time_s=session.task_end_time, audit_end_time_s=float(env.data.time))
    except BaseException as exc:
        receipt.update(status='error', error=repr(exc))
        raise
    finally:
        if env is not None:
            receipt.update(physical_substeps=getattr(env, 'physical_steps', 0), guard_facts=env.guard_facts,
                           peaks=getattr(env, 'peaks', {}))
        if session is not None: receipt['control_cycles'] = getattr(session, 'cycle_id', 0)
        if raw.get('cost'): receipt['reset_completed'] = raw['cost']['initializations_completed']
        receipt['elapsed_wall_s'] = time.monotonic() - started
        publish_archive(folder, raw, receipt)


def run():
    reg = read(OUT / 'registration.json'); verify_inputs(reg['inputs'])
    (OUT / 'run').mkdir()  # Irreversible claim: no reusing a partial batch.
    ledger = read(OUT / 'ledger.json'); ledger['status'] = 'RUNNING'
    write(OUT / 'ledger.json', ledger)
    select()
    for kind in KINDS:
        verify_inputs(reg['inputs']); folder = OUT / 'run' / kind; folder.mkdir()
        proof = supervise([str(PYTHON), '-I', '-B', '-X', 'utf8', str(Path(__file__).resolve()),
                           '--worker', kind], folder, timeout=1830)
        receipt = reconcile_receipt(folder, proof)
        try:
            if proof.get('returncode') != 0 or proof.get('supervision_error'):
                raise ValueError('Worker did not complete')
            raw, receipt, audit = audit_archive(folder, reg, qualification=True)
            if kind == 'ZERO_P10':
                old = json.loads(gzip.decompress((PARENT.parent / 'episode.json.gz').read_bytes()))
                audit['zero_trajectory'] = compare_zero_trace(raw['trace'], old['trace'])
                reasons = [e['reason'] for e in raw['evidence']['environment_events']]
                if not all(e in reasons for e in ('RECOVERY_ACCEPTED', 'B2_RECOVERY_RESUMED')):
                    raise ValueError('Natural recovery not covered')
                if not any(r.get('policy_phase') == 'UNLOAD' for r in raw['trace']):
                    raise ValueError('Natural unload not covered')
            write(folder / 'audit.json', audit); receipt['audit_passed'] = True
        except BaseException as exc:
            receipt.update(audit_passed=False, audit_error=repr(exc))
        receipt.update(proof)
        write(folder / 'receipt.json', receipt)
        ledger['episodes'].append(receipt)
        ledger['actual_initialization_attempts'] += receipt['reset_attempted']
        ledger['physical_substeps'] += receipt['physical_substeps']
        ledger['cumulative_initialization_attempts'] = 372 + ledger['actual_initialization_attempts']
        if not receipt.get('audit_passed'):
            ledger.update(status='STOPPED', stop_reason='INVALID_OR_UNQUALIFIED; NO_AUTOMATIC_RETRY')
        write(OUT / 'ledger.json', ledger)
        print(json.dumps(dict(case=kind, audit_passed=receipt.get('audit_passed'),
            error=receipt.get('audit_error'), physical_substeps=receipt['physical_substeps']), ensure_ascii=False), flush=True)
        if ledger['status'] == 'STOPPED': return 1
    ledger['status'] = 'QUALIFIED'; write(OUT / 'ledger.json', ledger)
    return 0


def finalize():
    reg = read(OUT / 'registration.json'); verify_inputs(reg['inputs'])
    ledger = read(OUT / 'ledger.json')
    if ledger['status'] != 'QUALIFIED' or len(ledger['episodes']) != 3:
        raise ValueError('All three one-shot qualifications required')
    select()
    for kind in KINDS: audit_archive(OUT / 'run' / kind, reg, qualification=True)
    from tools.learning.five_axis_training import FiveAxisTrainer
    from tools.learning.five_axis_checkpoint import save_checkpoint, load_checkpoint
    trainer = FiveAxisTrainer(reg['training_plan']['config'])
    checkpoint_digest = save_checkpoint(trainer, OUT / 'initial_checkpoint')
    restored = load_checkpoint(OUT / 'initial_checkpoint', expected_digest=checkpoint_digest,
                               config=reg['training_plan']['config'])
    import numpy as np
    raw, _, _ = audit_archive(OUT / 'run/ZERO_P10', reg, qualification=True)
    from tools.learning.five_axis_contract import field_slices
    search_index = field_slices()['policy_phase'].start + 2
    samples = [next(row['observation'] for row in raw['transitions'] if row['action_active']),
               next(row['observation'] for row in raw['transitions'] if row['observation'][search_index] == 1 and row['action_active'])]
    for observation in samples:
        if not np.array_equal(trainer.action(observation, deterministic=True), restored.action(observation, deterministic=True)):
            raise ValueError('Actual-observation inference restore differs')
    write(OUT / 'inference_check.json', dict(verified=True, calls=len(samples) * 2,
        task_policy_calls=0, formal_updates=0, source='qualified physical observations, offline inference'))
    admission = dict(version='five_axis_launch_admission_v1', ready=True,
        registration_sha256=sha(OUT / 'registration.json'), checkpoint_digest=checkpoint_digest,
        artifacts={kind: {name: sha(OUT / 'run' / kind / name)
            for name in ('episode.json.gz', 'receipt.json', 'model_used.xml', 'audit.json')}
            for kind in KINDS}, formal_training_started=False,
        scope='Four registered development poses, bounded five-axis commands; no motion-violation admission')
    write(OUT / 'admission.json', admission)
    check_ready()
    print(json.dumps(dict(ready=True, formal_training_started=False)), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true'); group.add_argument('--run', action='store_true')
    group.add_argument('--worker', choices=KINDS); group.add_argument('--finalize', action='store_true')
    args = parser.parse_args(argv)
    if args.prepare: prepare()
    elif args.run: return run()
    elif args.worker: worker(args.worker)
    else: finalize()
    return 0


if __name__ == '__main__': raise SystemExit(main())
