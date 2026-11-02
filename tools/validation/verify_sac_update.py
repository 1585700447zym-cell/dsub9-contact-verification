"""B2-02: two fresh warmup episodes, 16 SAC batches, then a real eight-cycle cut.

All attempts are preregistered. Insufficient warmup or any invalid episode fails
this probe; it never expands the experiment or edits the frozen configuration.
"""
import argparse
import gzip
import json
from pathlib import Path
import sys
import time

import numpy as np

from tools.learning.runtime import ROOT
from tools.learning.admission import canonical, digest, short_training_config, verify_files
from tools.learning.b2_sac_admission import SACAdmission, create_sac_admission, execution_contract
from tools.validation.verify_residual_interface import all_sources, qualified_runtime, run_logged


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def verification_protocol():
    from tools.learning.admitted_collection import EngineeringSampler
    sampler = EngineeringSampler(short_training_config())
    return dict(version='b2_sac_update_probe_v1', seed=2026092609, updates=16,
        execution_contract=execution_contract(), attempts=[
            dict(id='warmup_0', case=sampler.next_case(), mode='uniform_warmup', cut_steps=None, optimizer_steps=0),
            dict(id='warmup_1', case=sampler.next_case(), mode='uniform_warmup', cut_steps=None, optimizer_steps=0),
            dict(id='updated_cut', case=sampler.next_case(), mode='sac_policy', cut_steps=8, optimizer_steps=16)])


def validate_protocol(protocol):
    expected = verification_protocol()
    if any(canonical(protocol.get(k)) != canonical(v) for k, v in expected.items()):
        raise ValueError('Preregistered cases, warmup or update budget differs')


def comparable(history): return [{k: v for k, v in r.items() if k != 'wall_s'} for r in history]


def audit_archives(target):
    """Rebuild real replay and repeat numerical updates, without physical replay."""
    from tools.learning.audited_replay import AuditedReplay
    from tools.learning.sac_collection import WarmupPolicy, UpdateBudget
    from tools.learning.sac_update import SACUpdater
    from tools.validation.verify_admitted_collection import validate_attempt, validate_outcome
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    protocol = json.loads((target / 'protocol.json').read_text(encoding='utf-8'))
    validate_protocol(protocol)
    qualification_sha = digest(target / 'admission.json')
    config = short_training_config()
    replay, budget = AuditedReplay(capacity=100000), UpdateBudget(config)
    updater, warmup = SACUpdater(config), WarmupPolicy(config)
    replay_rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([protocol['seed'], 2])))
    fingerprints = {'before': updater.fingerprints()}
    summaries, history = [], []
    receipts = json.loads((target / 'attempts.json').read_text(encoding='utf-8'))
    if [r['episode_id'] for r in receipts] != [r['id'] for r in protocol['attempts']]:
        raise ValueError('Missing, extra or reordered actual attempts')
    for i, item in enumerate(protocol['attempts']):
        if i == 2:
            if budget.available < protocol['updates']: raise ValueError('Insufficient earned update credit')
            for _ in range(protocol['updates']):
                metrics = updater.update(replay.sample(256, rng=replay_rng))
                budget.consume()
                metrics.update(audited_total=budget.total, credit_remaining=budget.available)
                history.append(metrics)
            fingerprints['after'] = updater.fingerprints()
        folder = target / 'episodes' / item['id']
        raw = json.loads(gzip.decompress((folder / 'episode.json.gz').read_bytes()))
        status = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
        validate_attempt(raw, item, seed=protocol['seed'], qualification_sha256=qualification_sha)
        stopped = actual_stop_pass(raw['stop_samples'], raw['events'], raw['stop_time'], raw['audit_end_time_s'], .0002)
        stopped = stopped and physical_tail_pass(raw['stop_samples'], raw['audit_end_time_s'], .0002)
        validate_outcome(raw, stopped=stopped)
        if (raw['fault'] is not None or raw['outcome']['valid_for_learning'] is not True or
                raw['sampling_mode'] != item['mode'] or type(raw['optimizer_steps']) is not int or
                raw['optimizer_steps'] != item['optimizer_steps'] or raw['optimizer_steps_start'] != item['optimizer_steps'] or
                raw['policy_sha256'] != updater.fingerprints()['actor'] or
                status['archive_sha256'] != digest(folder / 'episode.json.gz') or status != receipts[i]):
            raise ValueError('Raw episode differs from current policy, qualification or original receipt')
        rows = raw['transitions']
        if item['cut_steps'] is not None:
            if (len(rows) != 8 or rows[-1]['terminated'] or not rows[-1]['truncated'] or
                    rows[-1]['reward_terms']['terminal'] != 0 or rows[-1]['trace_row']['time_s'] >= raw['audit_end_time_s']):
                raise ValueError('Updated-policy cutoff/bootstrap semantics changed')
        elif not rows[-1]['terminated'] or rows[-1]['truncated']:
            raise ValueError('Warmup did not finish its complete audited episode')
        action_source = warmup if item['mode'] == 'uniform_warmup' else updater
        for row in rows:
            action, _ = action_source.predict(np.asarray(row['observation'], dtype=np.float32))
            if not np.array_equal(np.asarray(row['action_log']['raw_action']), action):
                raise ValueError('Archived action differs from seeded warmup or updated policy')
        result = replay.publish(item['id'], rows, outcome=raw['outcome'], training_admitted=True)
        if result['committed'] != status['committed']: raise ValueError('Publication count differs from original data')
        budget.record(status)
        summaries.append(dict(id=item['id'], transitions=len(rows), outcome=raw['outcome'],
            contact_cycles=sum(r['trace_row']['contact_count'] > 0 for r in rows),
            action_active_cycles=sum(r['action_active'] for r in rows), truncated=rows[-1]['truncated'],
            optimizer_steps=raw['optimizer_steps'], sampling_mode=raw['sampling_mode']))
    saved_history = json.loads((target / 'updates.json').read_text(encoding='utf-8'))
    if canonical(comparable(saved_history)) != canonical(history): raise ValueError('Numerical update history does not reproduce')
    saved_fingerprints = json.loads((target / 'network_fingerprints.json').read_text(encoding='utf-8'))
    if saved_fingerprints != fingerprints: raise ValueError('Learned parameter fingerprints do not reproduce')
    if any(fingerprints['before'][key] == fingerprints['after'][key] for key in ('actor', 'critic', 'target', 'alpha')):
        raise ValueError('Expected SAC parameter block did not change')
    if updater.counts != dict(critic=16, actor=16, temperature=16, target=16):
        raise ValueError('Actual optimizer/target counts differ from planned updates')
    return dict(attempts=summaries, published_transitions=len(replay), cumulative_audited=budget.total,
        update_counts=updater.counts, credit_remaining=budget.available,
        numerical_updates_reproduced=True, updated_policy_actions_reproduced=True,
        parameter_blocks_changed=['actor', 'critic', 'target', 'alpha'])


def run(output):
    target = Path(output).resolve()
    if not target.is_relative_to(ROOT): raise ValueError('Worktree output required')
    target.mkdir(parents=True, exist_ok=False)
    save(target / 'assessment.json', dict(sac_update_verified=False, status='started'))
    chain = None
    try:
        runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
        from tools.learning.sac_collection import SACCollection
        protocol = verification_protocol()
        protocol.update(runtime=runtime, source_sha256=all_sources(),
            purpose='Bounded SAC wiring validation, not first engineering short training or performance evaluation')
        save(target / 'protocol.json', protocol)
        run_logged([sys.executable, '-X', 'utf8', '-B', '-m', 'pytest', '-p', 'no:cacheprovider',
            '-q', 'tests/learning', '-o', 'junit_family=xunit1', '--tb=short',
            f'--junitxml={target / "learning_tests.xml"}'], target / 'learning_tests.log')
        create_sac_admission(target / 'admission.json', test_report=target / 'learning_tests.xml',
                             checked_sources=protocol['source_sha256'])
        permit = SACAdmission(target / 'admission.json', expected_digest=digest(target / 'admission.json'))
        chain = SACCollection(admission=permit, output=target / 'episodes')
        fingerprints = dict(before=chain.updater.fingerprints())
        start = time.perf_counter()
        for i, item in enumerate(protocol['attempts']):
            if i == 2:
                if chain.budget.available < protocol['updates']:
                    raise ValueError('Fixed two-episode probe did not earn enough update credit; no extra episodes allowed')
                updates = chain.update(protocol['updates'])
                if len(updates) != protocol['updates']: raise ValueError('Probe updates incomplete')
                save(target / 'updates.json', chain.history)
                fingerprints['after'] = chain.updater.fingerprints()
                save(target / 'network_fingerprints.json', fingerprints)
                print(json.dumps(dict(completed_updates=chain.updater.counts,
                    cumulative_audited=chain.budget.total, credit_remaining=chain.budget.available)), flush=True)
            chain.start(item['id'], case=item['case'])
            if chain.collector.sampling_mode != item['mode']: raise ValueError('Warmup mode differs from registration')
            if item['cut_steps']:
                chain.collect(item['cut_steps'], cut_at_end=True)
            else:
                while chain.collector.active:
                    result = chain.collect(500)
                    print(json.dumps(dict(attempt=item['id'], **result)), flush=True)
            save(target / 'attempts.json', chain.collector.attempts)
        elapsed = time.perf_counter() - start
        permit.verify()
        report = audit_archives(target)
        update_times = [r['wall_s'] for r in chain.history]
        report.update(sac_update_verified=True, runnable_trainer=False,
            full_checkpoint_verified=False, first_engineering_short_train=False,
            collection_and_update_wall_s=elapsed, update_batch_total_s=sum(update_times),
            update_batch_mean_s=sum(update_times) / len(update_times),
            tests=json.loads((target / 'admission.json').read_text(encoding='utf-8'))['tests'])
        save(target / 'assessment.json', report)
        save(target / 'manifest.json', dict(version='b2_sac_update_delivery_v1', files={
            p.relative_to(ROOT).as_posix(): digest(p) for p in target.rglob('*')
            if p.is_file() and p.name != 'manifest.json'}))
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return report
    except Exception as exc:
        save(target / 'assessment.json', dict(sac_update_verified=False, runnable_trainer=False,
            error=repr(exc), update_counts=None if chain is None else chain.updater.counts))
        if chain is not None:
            save(target / 'attempts.json', chain.collector.attempts)
            save(target / 'updates.json', chain.history)
        raise


def recheck(output):
    target = Path(output).resolve()
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    verify_files(ROOT, manifest['files'])
    path = target / 'admission.json'
    SACAdmission(path, expected_digest=manifest['files'][path.relative_to(ROOT).as_posix()])
    actual = audit_archives(target)
    report = json.loads((target / 'assessment.json').read_text(encoding='utf-8'))
    if report.get('sac_update_verified') is not True or any(report[k] != v for k, v in actual.items()):
        raise ValueError('Assessment differs from recomputed physical and numerical evidence')
    print(json.dumps(actual, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--recheck', action='store_true')
    args = parser.parse_args()
    if args.recheck: recheck(args.output)
    else: run(args.output)
