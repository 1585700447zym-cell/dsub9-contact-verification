"""B2-04 first engineering short training and eight paired development cases."""
import argparse
import gzip
import json
import os
from pathlib import Path
import sys
import time

import numpy as np

from tools.learning.runtime import ROOT
from tools.learning.admission import canonical, digest, short_training_config, verify_files
from tools.learning.admitted_collection import _write_json as save, EngineeringSampler
from tools.learning.b2_training_admission import TrainingAdmission, create_training_admission, execution_contract
from tools.learning.engineering_training import run_training
from tools.learning.engineering_evaluation import evaluation_cases, EvaluationCollector, ZeroPolicy, FrozenPolicy, episode_metrics
from tools.learning.sac_checkpoint import capture, load_checkpoint, read_checkpoint, _same, _replay_state, _audit_physics
from tools.validation.verify_residual_interface import all_sources, qualified_runtime, run_logged
from tools.validation.verify_sac_checkpoint import semantic_state
from tools.validation.verify_sac_update import comparable


def verification_protocol():
    return dict(version='b2_engineering_short_train_v1', config=short_training_config(),
        execution_contract=execution_contract(), checkpoint_selection='final_after_target_whole_episode_and_updates',
        evaluation_cases=evaluation_cases(), evaluation_order='case_then_zero_b2_then_sac',
        metric_load_source='cycle_peak_reconstructed_from_frozen_reward_terms',
        penetration_source='end_of_cycle_trace_samples', success_denominator='all_attempts_per_method',
        effectiveness_claim='development_observation_only', independent_test_used=False)


def validate_protocol(protocol):
    if any(canonical(protocol.get(k)) != canonical(v) for k, v in verification_protocol().items()):
        raise ValueError('Training or development evaluation differs from preregistration')


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def permit_for(target):
    path = target / 'admission.json'
    return TrainingAdmission(path, expected_digest=digest(path))


def evaluate(target):
    qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    protocol = read(target / 'protocol.json'); validate_protocol(protocol)
    selection = read(target / 'selection.json'); checkpoint = selection['checkpoint']
    if selection['selection_rule'] != protocol['checkpoint_selection']: raise ValueError('Wrong selection rule')
    permit = permit_for(target); start = time.perf_counter()
    chain = load_checkpoint(target / checkpoint['path'], expected_digest=checkpoint['sha256'], admission=permit,
        output=target / 'restored_training_episodes')
    load_wall = time.perf_counter() - start
    before = semantic_state(capture(chain))
    if before != selection['training_state_sha256']: raise ValueError('New process did not restore selected training state')
    folder = target / 'evaluation'; folder.mkdir(exist_ok=False)
    collectors = {method: EvaluationCollector(admission=permit, output=folder / method,
        checkpoint_sha256=checkpoint['sha256'], method=method, updater=chain.updater)
        for method in execution_contract()['evaluation_methods']}
    policies = dict(zero_b2=ZeroPolicy(), sac=FrozenPolicy(chain.updater)); results = []
    save(folder / 'state_before.json', dict(pid=os.getpid(), state_sha256=before, counts=chain.updater.counts,
        replay_size=len(chain.replay), load_wall_s=load_wall, checkpoint_sha256=checkpoint['sha256']))
    for case in protocol['evaluation_cases']:
        for method, collector in collectors.items():
            begin = time.perf_counter()
            try:
                collector.start(case['name'], case=case, seed=execution_contract()['evaluation_seed'])
                while collector.active:
                    progress = collector.collect(policies[method], 500, deterministic=True)
                    print(f'evaluation {method} {case["name"]}: {progress}', flush=True)
                receipt = collector.attempts[-1]
                raw = json.loads(gzip.decompress((collector.output / case['name'] / 'episode.json.gz').read_bytes()))
                results.append(dict(method=method, case=case, metrics=episode_metrics(raw), wall_s=time.perf_counter() - begin))
                save(folder / 'results.json', results)
                if receipt['status'] != 'evaluation_archived' or collector._blocked:
                    raise RuntimeError('Invalid evaluation retained; expansion stopped without resampling')
            finally:
                save(folder / 'attempts.json', {m: c.attempts for m, c in collectors.items()})
    after = semantic_state(capture(chain))
    if before != after or any(len(c.replay) for c in collectors.values()):
        raise RuntimeError('Evaluation modified training state or admitted evaluation data')
    save(folder / 'state_after.json', dict(pid=os.getpid(), state_sha256=after, counts=chain.updater.counts,
        replay_size=len(chain.replay), checkpoint_sha256=checkpoint['sha256']))
    print('Sixteen fixed development attempts archived; complete training state unchanged.', flush=True)


def audit(target):
    """Reproduce every training action/update, then verify paired frozen evaluation."""
    from tools.learning.audited_replay import AuditedReplay
    from tools.learning.sac_collection import WarmupPolicy, UpdateBudget
    from tools.learning.sac_update import SACUpdater
    protocol = read(target / 'protocol.json'); validate_protocol(protocol)
    selection = read(target / 'selection.json'); report = read(target / 'training.json')
    receipts = read(target / 'checkpoint_receipts.json'); permit = permit_for(target)
    if (selection['selection_rule'] != protocol['checkpoint_selection'] or
            selection['checkpoint'] != receipts[-1] or report['final_checkpoint'] != receipts[-1]):
        raise ValueError('Evaluation did not select the predefined final checkpoint')
    checkpoint = selection['checkpoint']
    final, _ = read_checkpoint(target / checkpoint['path'], expected_digest=checkpoint['sha256'], admission=permit)
    config = short_training_config(); replay = AuditedReplay(capacity=100000); budget = UpdateBudget(config)
    updater, sampler, warmup = SACUpdater(config), EngineeringSampler(config), WarmupPolicy(config)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([config['sampling']['seed'], 2])))
    if final['attempts'] != read(target / 'attempts.json') or final['history'] != read(target / 'updates.json'):
        raise ValueError('Original attempt/update ledgers differ from final checkpoint')
    attempts = final['attempts']; expected_ids = [f'train_{i:06d}' for i in range(len(attempts))]
    if ([r['episode_id'] for r in attempts] != expected_ids or
            {p.name for p in (target / 'episodes').iterdir()} != set(expected_ids) or
            len(receipts) != len(attempts) or {p.name for p in (target / 'checkpoints').iterdir()} != set(expected_ids)):
        raise ValueError('Missing, extra or reordered training attempt/checkpoint')
    history = []; training_metrics = []
    for index, receipt in enumerate(attempts):
        if budget.total >= 20000: raise ValueError('Extra attempt after target boundary')
        identity = receipt['episode_id']; raw = json.loads(gzip.decompress(final['archives'][identity]))
        original = target / 'episodes' / identity
        if (original.joinpath('episode.json.gz').read_bytes() != final['archives'][identity] or
                read(original / 'status.json') != receipt): raise ValueError('Original retained attempt changed')
        mode = 'uniform_warmup' if budget.total < 5000 else 'sac_policy'
        if (raw['case'] != sampler.next_case() or raw['seed'] != config['sampling']['seed'] or
                raw['sampling_mode'] != mode or raw['optimizer_steps_start'] != updater.counts['critic'] or
                raw['optimizer_steps'] != updater.counts['critic'] or raw['policy_sha256'] != updater.fingerprints()['actor']):
            raise ValueError('Training initialization, mode, policy or optimizer boundary differs')
        rows = raw['transitions']
        if not rows[-1]['terminated'] or rows[-1]['truncated'] or len(rows) > 13000:
            raise ValueError('Training did not end as a complete bounded episode')
        policy = warmup if mode == 'uniform_warmup' else updater
        for row in rows:
            action, _ = policy.predict(np.asarray(row['observation'], dtype=np.float32))
            if not np.array_equal(action, row['action_log']['raw_action']): raise ValueError('Training action RNG does not reproduce')
        replay.publish(identity, rows, outcome=raw['outcome'], training_admitted=True); budget.record(receipt)
        while budget.available:
            metrics = updater.update(replay.sample(256, rng=rng)); budget.consume()
            metrics.update(audited_total=budget.total, credit_remaining=budget.available); history.append(metrics)
        expected_receipt = receipts[index]
        if (expected_receipt['episode_id'] != identity or expected_receipt['cumulative_audited'] != budget.total or
                expected_receipt['critic_updates'] != budget.completed or expected_receipt['path'] != f'checkpoints/{identity}' or
                digest(target / expected_receipt['path'] / 'manifest.json') != expected_receipt['sha256']):
            raise ValueError('Per-episode checkpoint receipt differs')
        manifest = read(target / expected_receipt['path'] / 'manifest.json')
        if digest(target / expected_receipt['path'] / 'state.pt') != manifest['state_sha256']:
            raise ValueError('Per-episode checkpoint bytes changed')
        training_metrics.append(dict(episode_id=identity, case=raw['case'], mode=mode, metrics=episode_metrics(raw)))
        print(f'audit training {identity}: {budget.total} rows, {budget.completed} reproduced updates', flush=True)
    if (not 20000 <= budget.total <= 33000 or not _same(updater._snapshot(), final['updater']) or
            not _same(_replay_state(replay), final['replay']) or history != comparable(final['history']) or
            final['budget'] != dict(total=budget.total, completed=budget.completed, receipts=budget._receipts) or
            sampler.count != final['sampler']['count'] or sampler.rng.bit_generator.state != final['sampler']['rng'] or
            rng.bit_generator.state != final['rng']['replay'] or warmup.rng.bit_generator.state != final['rng']['warmup']):
        raise ValueError('Final learning state does not reproduce from fresh training archives')
    expected_report = dict(training_completed=True, target_audited_cycles=20000, cumulative_audited=budget.total,
        overshoot_cycles=budget.total - 20000, attempts=len(attempts), update_counts=updater.counts, credit_remaining=0)
    if any(report.get(k) != v for k, v in expected_report.items()): raise ValueError('Training report counter differs')
    state_sha = semantic_state(final)
    before, after = [read(target / 'evaluation' / f'state_{part}.json') for part in ('before', 'after')]
    if (before['pid'] == selection['pid'] or before['pid'] != after['pid'] or
            state_sha != selection['training_state_sha256'] or
            any(r['state_sha256'] != state_sha or r['counts'] != updater.counts or r['replay_size'] != budget.total or
                r['checkpoint_sha256'] != checkpoint['sha256'] for r in (before, after))):
        raise ValueError('New-process evaluation did not preserve the complete selected training state')
    eval_receipts = read(target / 'evaluation/attempts.json'); results = read(target / 'evaluation/results.json')
    methods = execution_contract()['evaluation_methods']; cases = protocol['evaluation_cases']
    if set(eval_receipts) != set(methods) or len(results) != 16: raise ValueError('Missing evaluation attempts')
    pairs = []; summaries = {}
    for method in methods:
        folder = target / 'evaluation' / method
        if ([r['episode_id'] for r in eval_receipts[method]] != [c['name'] for c in cases] or
                {p.name for p in folder.iterdir()} != {c['name'] for c in cases}):
            raise ValueError('Evaluation excluded or duplicated a fixed case')
    for i, case in enumerate(cases):
        paired = dict(case=case)
        for j, method in enumerate(methods):
            folder = target / 'evaluation' / method / case['name']; receipt = read(folder / 'status.json')
            raw = json.loads(gzip.decompress((folder / 'episode.json.gz').read_bytes())); _audit_physics(raw)
            if (receipt != eval_receipts[method][i] or digest(folder / 'episode.json.gz') != receipt['archive_sha256'] or
                    raw['episode_id'] != case['name'] or raw['case'] != case or raw['seed'] != execution_contract()['evaluation_seed'] or
                    raw['qualification_sha256'] != permit.expected_digest or raw['training_admitted'] is not False or
                    receipt['training_admitted'] is not False or receipt['committed'] != 0 or
                    raw['evaluation_method'] != method or raw['checkpoint_sha256'] != checkpoint['sha256'] or
                    raw['policy_sha256'] != updater.fingerprints()['actor'] or raw['optimizer_steps_start'] != budget.completed or
                    raw['optimizer_steps'] != budget.completed or raw['fault'] is not None or
                    raw['outcome']['valid_for_learning'] is not True or receipt['status'] != 'evaluation_archived'):
                raise ValueError('Evaluation identity, qualification, policy or training isolation differs')
            rows = raw['transitions']
            if not rows[-1]['terminated'] or rows[-1]['truncated'] or len(rows) > 13000:
                raise ValueError('Evaluation episode was incomplete')
            # Validate the full transition schema without publishing to any training replay.
            AuditedReplay(capacity=100000)._prepare(rows)
            policy = ZeroPolicy() if method == 'zero_b2' else FrozenPolicy(updater)
            for row in rows:
                action, _ = policy.predict(np.asarray(row['observation'], dtype=np.float32))
                if not np.array_equal(action, row['action_log']['raw_action']): raise ValueError('Frozen evaluation action differs')
            metrics = episode_metrics(raw); recorded = results[2 * i + j]
            if recorded['case'] != case or recorded['method'] != method or recorded['metrics'] != metrics:
                raise ValueError('Evaluation metrics or all-attempt ordering differs')
            paired[method] = metrics
        pairs.append(paired)
    for method in methods:
        values = [p[method] for p in pairs]
        summaries[method] = dict(attempts=len(values), successes=sum(v['success'] for v in values),
            simulation_valid=sum(v['simulation_valid'] for v in values), physical_stopped=sum(v['physical_stopped'] for v in values),
            contact_cycles=sum(v['contact_cycles'] for v in values), effective_action_cycles=sum(v['effective_action_cycles'] for v in values),
            mean_return=float(np.mean([v['return'] for v in values])), force_peak_N=max(v['force_peak_N'] for v in values),
            torque_peak_Nm=max(v['torque_peak_Nm'] for v in values), mean_stop_time_s=float(np.mean([v['task_stop_time_s'] for v in values])))
    numeric = {key: dict(min=min(r[key] for r in history if r.get(key) is not None),
                        max=max(r[key] for r in history if r.get(key) is not None),
                        final=next(r[key] for r in reversed(history) if r.get(key) is not None))
        for key in ('critic_loss', 'actor_loss', 'alpha_after', 'entropy_abs_mean', 'reward_abs_mean', 'target_abs_max')
        if any(r.get(key) is not None for r in history)}
    return dict(engineering_short_train_completed=True, fixed_development_evaluation_completed=True,
        training_state_reproduced=True, new_process_evaluation=True, evaluation_training_state_unchanged=True,
        independent_test_used=False, effectiveness_claim='development_observation_only',
        cumulative_audited=budget.total, overshoot_cycles=budget.total - 20000, training_attempts=len(attempts),
        update_counts=updater.counts, credit_remaining=budget.available, final_checkpoint_sha256=checkpoint['sha256'],
        final_state_sha256=state_sha, training_metrics=training_metrics, numeric_diagnostics=numeric,
        evaluation_summaries=summaries, paired_evaluation=pairs)


def run(output):
    target = Path(output).resolve()
    if not target.is_relative_to(ROOT): raise ValueError('Worktree output required')
    target.mkdir(parents=True, exist_ok=False)
    save(target / 'assessment.json', dict(engineering_short_train_completed=False, status='started'))
    training_completed = evaluation_completed = False
    phase = 'preflight'; final_checkpoint = None
    try:
        runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
        protocol = verification_protocol(); protocol.update(runtime=runtime, source_sha256=all_sources())
        save(target / 'protocol.json', protocol)
        phase = 'tests'
        run_logged([sys.executable, '-X', 'utf8', '-B', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', 'tests/learning',
            '-o', 'junit_family=xunit1', '--tb=short', f'--junitxml={target / "learning_tests.xml"}'], target / 'learning_tests.log')
        phase = 'qualification'
        create_training_admission(target / 'admission.json', test_report=target / 'learning_tests.xml',
            checked_sources=protocol['source_sha256'])
        from tools.learning.sac_collection import SACCollection
        phase = 'training'
        chain = SACCollection(admission=permit_for(target), output=target / 'episodes')
        report = run_training(chain, target)
        training_completed = True
        final_checkpoint = report['final_checkpoint']; phase = 'final_checkpoint_selection'
        save(target / 'selection.json', dict(pid=os.getpid(), selection_rule=protocol['checkpoint_selection'],
            checkpoint=report['final_checkpoint'], training_state_sha256=semantic_state(capture(chain))))
        phase = 'evaluation'
        run_logged([sys.executable, '-X', 'utf8', '-B', '-m', 'tools.validation.run_engineering_short_train',
            '--output', str(target), '--evaluate'], target / 'evaluation_process.log')
        evaluation_completed = True
        phase = 'audit'
        assessment = audit(target); assessment['tests'] = read(target / 'admission.json')['tests']
        assessment['delivery_verified'] = True
        save(target / 'assessment.json', assessment)
        save(target / 'manifest.json', dict(version='b2_engineering_training_delivery_v1', files={
            p.relative_to(ROOT).as_posix(): digest(p) for p in target.rglob('*') if p.is_file() and p != target / 'manifest.json'}))
        print(json.dumps(assessment, ensure_ascii=False), flush=True)
        return assessment
    except Exception as exc:
        save(target / 'assessment.json', dict(engineering_short_train_completed=training_completed,
            fixed_development_evaluation_completed=evaluation_completed, delivery_verified=False,
            status='failed_retained', failed_phase=phase, final_checkpoint=final_checkpoint, error=repr(exc)))
        raise


def recheck(output):
    target = Path(output).resolve(); verify_files(ROOT, read(target / 'manifest.json')['files'])
    actual = audit(target); recorded = read(target / 'assessment.json')
    if any(recorded.get(k) != v for k, v in actual.items()): raise ValueError('Saved assessment does not reproduce')
    print(json.dumps(actual, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--evaluate', action='store_true'); parser.add_argument('--recheck', action='store_true')
    args = parser.parse_args()
    if args.evaluate: evaluate(args.output.resolve())
    elif args.recheck: recheck(args.output)
    else: run(args.output)
