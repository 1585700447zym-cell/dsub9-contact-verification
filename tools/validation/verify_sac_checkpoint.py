"""B2-03: fresh two-episode warmup, eight updates, save, paired continuation.

One branch stays alive; the other loads in a new Python process. Both perform
eight more updates and the same real eight-cycle external cutoff. No 20k run.
"""
import argparse
from copy import deepcopy
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import numpy as np
import torch

from tools.learning.runtime import ROOT
from tools.learning.admission import canonical, digest, short_training_config, verify_files
from tools.learning.b2_checkpoint_admission import CheckpointAdmission, create_checkpoint_admission, execution_contract
from tools.learning.sac_checkpoint import (capture, save_checkpoint, load_checkpoint, read_checkpoint,
    _same, _replay_state, _audit_physics)
from tools.validation.verify_residual_interface import all_sources, qualified_runtime, run_logged
from tools.validation.verify_sac_update import comparable, save


def verification_protocol():
    from tools.learning.admitted_collection import EngineeringSampler
    sampler = EngineeringSampler(short_training_config())
    return dict(version='b2_checkpoint_probe_v1', before_save_updates=8, after_save_updates=8,
        execution_contract=execution_contract(), attempts=[
            dict(id='warmup_0', case=sampler.next_case(), mode='uniform_warmup'),
            dict(id='warmup_1', case=sampler.next_case(), mode='uniform_warmup'),
            dict(id='continued_cut', case=sampler.next_case(), mode='sac_policy', cut_steps=8)])


def validate_protocol(protocol):
    if any(canonical(protocol.get(k)) != canonical(v) for k, v in verification_protocol().items()):
        raise ValueError('Checkpoint probe differs from preregistered cases or budget')


def state_digest(value):
    """Typed deterministic semantic digest, independent of torch ZIP metadata."""
    h = hashlib.sha256()
    def visit(x):
        h.update(type(x).__name__.encode() + b':')
        if isinstance(x, torch.Tensor):
            h.update(str(x.dtype).encode()); h.update(str(tuple(x.shape)).encode())
            h.update(x.detach().cpu().contiguous().numpy().tobytes())
        elif isinstance(x, dict):
            for k in sorted(x, key=lambda key: (type(key).__name__, str(key))): visit(k); visit(x[k])
        elif isinstance(x, (list, tuple)):
            h.update(str(len(x)).encode())
            for item in x: visit(item)
        elif isinstance(x, bytes): h.update(hashlib.sha256(x).digest())
        else: h.update(canonical(x).encode('utf-8'))
        h.update(b';')
    visit(value)
    return h.hexdigest()


def semantic_state(state):
    state = deepcopy(state); state['history'] = comparable(state['history'])
    return state_digest(state)


def preview(chain):
    sampler = deepcopy(chain.sampler)
    batch = chain.replay.sample(256, rng=deepcopy(chain.replay_rng))
    return dict(next_case=sampler.next_case(), next_batch_sha256=state_digest(vars(batch)),
        next_warmup_action=deepcopy(chain.warmup).predict(np.zeros(120))[0].tolist())


def continue_chain(chain, folder, protocol):
    folder.mkdir(parents=True, exist_ok=False)
    start = time.perf_counter(); before = preview(chain)
    updates = chain.update(protocol['after_save_updates'])
    if len(updates) != 8: raise ValueError('Continuation did not complete exactly eight updates')
    item = protocol['attempts'][2]
    chain.start(item['id'])
    if chain.collector.attempts[-1]['case'] != item['case']: raise ValueError('Restored initializer diverged')
    chain.collect(item['cut_steps'], cut_at_end=True)
    state = capture(chain)
    raw = json.loads(gzip.decompress(state['archives'][item['id']]))
    _audit_physics(raw)
    rows = raw['transitions']
    if (len(rows) != 8 or rows[-1]['terminated'] or not rows[-1]['truncated'] or
            rows[-1]['reward_terms']['terminal'] != 0 or rows[-1]['trace_row']['time_s'] >= raw['audit_end_time_s']):
        raise ValueError('Continuation cutoff/bootstrap boundary failed')
    # Each final checkpoint is independently validated on save.
    sha = save_checkpoint(chain, folder / 'final_checkpoint')
    report = dict(pid=os.getpid(), preview=before, updates=comparable(updates),
        final_state_sha256=semantic_state(state), final_checkpoint_sha256=sha,
        final_counts=chain.updater.counts, cumulative_audited=chain.budget.total,
        credit_remaining=chain.budget.available, sampler_count=chain.sampler.count,
        cut_archive_sha256=hashlib.sha256(state['archives'][item['id']]).hexdigest(),
        continuation_wall_s=time.perf_counter() - start)
    save(folder / 'result.json', report)
    return report


def child(target, checkpoint_sha):
    qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    protocol = json.loads((target / 'protocol.json').read_text(encoding='utf-8')); validate_protocol(protocol)
    path = target / 'admission.json'
    permit = CheckpointAdmission(path, expected_digest=digest(path))
    start = time.perf_counter()
    chain = load_checkpoint(target / 'checkpoint', expected_digest=checkpoint_sha,
                            admission=permit, output=target / 'resumed_episodes')
    load_wall = time.perf_counter() - start
    report = continue_chain(chain, target / 'resumed', protocol)
    save(target / 'load_timing.json', dict(load_wall_s=load_wall, pid=os.getpid()))
    print(json.dumps(report, ensure_ascii=False), flush=True)


def audit(target):
    """Rebuild initial and continued learning states from raw archives; no physics integration."""
    from tools.learning.admitted_collection import EngineeringSampler
    from tools.learning.audited_replay import AuditedReplay
    from tools.learning.sac_collection import WarmupPolicy, UpdateBudget
    from tools.learning.sac_update import SACUpdater
    protocol = json.loads((target / 'protocol.json').read_text(encoding='utf-8')); validate_protocol(protocol)
    path = target / 'admission.json'
    permit = CheckpointAdmission(path, expected_digest=digest(path))
    checkpoint_sha = json.loads((target / 'checkpoint_receipt.json').read_text(encoding='utf-8'))['sha256']
    initial, _ = read_checkpoint(target / 'checkpoint', expected_digest=checkpoint_sha, admission=permit)
    config = short_training_config()
    replay, budget = AuditedReplay(capacity=100000), UpdateBudget(config)
    updater, sampler, warmup = SACUpdater(config), EngineeringSampler(config), WarmupPolicy(config)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([config['sampling']['seed'], 2])))
    receipts = initial['attempts']
    if [r['episode_id'] for r in receipts] != [p['id'] for p in protocol['attempts'][:2]]:
        raise ValueError('Checkpoint warmup differs from registration')
    summaries = []
    for item, receipt in zip(protocol['attempts'][:2], receipts):
        raw = json.loads(gzip.decompress(initial['archives'][item['id']]))
        if (raw['case'] != sampler.next_case() or raw['case'] != item['case'] or
                raw['optimizer_steps_start'] != 0 or raw['optimizer_steps'] != 0):
            raise ValueError('Wrong warmup case or update count')
        if raw['policy_sha256'] != updater.fingerprints()['actor']: raise ValueError('Wrong warmup policy')
        rows = raw['transitions']
        if not rows[-1]['terminated'] or rows[-1]['truncated']: raise ValueError('Warmup incomplete')
        for row in rows:
            action, _ = warmup.predict(np.asarray(row['observation'], dtype=np.float32))
            if not np.array_equal(action, row['action_log']['raw_action']): raise ValueError('Warmup RNG does not reproduce')
        replay.publish(item['id'], rows, outcome=raw['outcome'], training_admitted=True); budget.record(receipt)
        summaries.append(dict(id=item['id'], transitions=len(rows), outcome=raw['outcome'],
            contact_cycles=sum(r['trace_row']['contact_count'] > 0 for r in rows)))
    history = []
    def update_eight():
        for _ in range(8):
            metrics = updater.update(replay.sample(256, rng=rng)); budget.consume()
            metrics.update(audited_total=budget.total, credit_remaining=budget.available); history.append(metrics)
    update_eight()
    if (not _same(updater._snapshot(), initial['updater']) or not _same(_replay_state(replay), initial['replay']) or
            history != comparable(initial['history']) or sampler.count != initial['sampler']['count'] or
            sampler.rng.bit_generator.state != initial['sampler']['rng'] or
            rng.bit_generator.state != initial['rng']['replay'] or warmup.rng.bit_generator.state != initial['rng']['warmup']):
        raise ValueError('Initial checkpoint does not reproduce from fresh raw warmup and eight updates')
    before = preview(SimpleNamespace(sampler=sampler, replay=replay, replay_rng=rng, warmup=warmup))
    update_eight()
    reports = [json.loads((target / branch / 'result.json').read_text(encoding='utf-8')) for branch in ('continuous', 'resumed')]
    if reports[0]['pid'] == reports[1]['pid']: raise ValueError('Resume did not use a separate process')
    first_final = None
    for branch, report in zip(('continuous', 'resumed'), reports):
        final, _ = read_checkpoint(target / branch / 'final_checkpoint',
            expected_digest=report['final_checkpoint_sha256'], admission=permit)
        if report['preview'] != before or report['updates'] != history[8:]: raise ValueError('Next sample or update diverged')
        if first_final is None: first_final = final
        if semantic_state(final) != semantic_state(first_final) or semantic_state(final) != report['final_state_sha256']:
            raise ValueError('Complete continued state diverged')
        if final['attempts'][:2] != initial['attempts'] or final['history'][:8] != initial['history']:
            raise ValueError('Resume rewrote original history')
    final = first_final; item = protocol['attempts'][2]
    if [r['episode_id'] for r in final['attempts']] != [p['id'] for p in protocol['attempts']]:
        raise ValueError('Missing or extra continuation attempt')
    raw = json.loads(gzip.decompress(final['archives'][item['id']]))
    if (raw['case'] != sampler.next_case() or raw['case'] != item['case'] or
            raw['optimizer_steps_start'] != 16 or raw['optimizer_steps'] != 16):
        raise ValueError('Continuation initializer/counter differs')
    if raw['policy_sha256'] != updater.fingerprints()['actor']: raise ValueError('Wrong continued policy')
    rows = raw['transitions']
    if (len(rows) != 8 or rows[-1]['terminated'] or not rows[-1]['truncated'] or
            rows[-1]['reward_terms']['terminal'] != 0 or rows[-1]['trace_row']['time_s'] >= raw['audit_end_time_s']):
        raise ValueError('Continuation cutoff semantics differ')
    for row in rows:
        action, _ = updater.predict(np.asarray(row['observation'], dtype=np.float32))
        if not np.array_equal(action, row['action_log']['raw_action']): raise ValueError('Continued policy action differs')
    replay.publish(item['id'], rows, outcome=raw['outcome'], training_admitted=True); budget.record(final['attempts'][-1])
    if (not _same(updater._snapshot(), final['updater']) or not _same(_replay_state(replay), final['replay']) or
            history != comparable(final['history']) or sampler.count != final['sampler']['count'] or
            sampler.rng.bit_generator.state != final['sampler']['rng'] or rng.bit_generator.state != final['rng']['replay'] or
            warmup.rng.bit_generator.state != final['rng']['warmup']):
        raise ValueError('Final complete state does not reproduce')
    return dict(full_checkpoint_verified=True, initial_checkpoint_reproduced=True,
        new_process_verified=True, next_batch_equal=True, next_updates_equal=True,
        next_initialization_equal=True, physical_cut_archive_equal=True, full_continued_state_equal=True,
        warmup_attempts=summaries, unique_transitions=budget.total,
        actual_native_attempts=4, actual_native_transitions=budget.total + 8,
        checkpoint_update_counts=initial['updater']['counts'], final_update_counts=updater.counts,
        credit_remaining=budget.available, sampler_count=sampler.count,
        checkpoint_sha256=checkpoint_sha, final_state_sha256=semantic_state(final),
        first_engineering_short_train=False, runnable_trainer=False)


def run(output):
    target = Path(output).resolve()
    if not target.is_relative_to(ROOT): raise ValueError('Worktree output required')
    target.mkdir(parents=True, exist_ok=False)
    save(target / 'assessment.json', dict(full_checkpoint_verified=False, status='started'))
    chain = None
    try:
        runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
        from tools.learning.sac_collection import SACCollection
        protocol = verification_protocol(); protocol.update(runtime=runtime, source_sha256=all_sources())
        save(target / 'protocol.json', protocol)
        run_logged([sys.executable, '-X', 'utf8', '-B', '-m', 'pytest', '-p', 'no:cacheprovider',
            '-q', 'tests/learning', '-o', 'junit_family=xunit1', '--tb=short',
            f'--junitxml={target / "learning_tests.xml"}'], target / 'learning_tests.log')
        create_checkpoint_admission(target / 'admission.json', test_report=target / 'learning_tests.xml',
                                    checked_sources=protocol['source_sha256'])
        path = target / 'admission.json'; permit = CheckpointAdmission(path, expected_digest=digest(path))
        chain = SACCollection(admission=permit, output=target / 'episodes')
        start = time.perf_counter()
        for item in protocol['attempts'][:2]:
            chain.start(item['id'])
            if chain.collector.attempts[-1]['case'] != item['case']: raise ValueError('Wrong registered initializer')
            while chain.collector.active:
                result = chain.collect(500); print(json.dumps(dict(attempt=item['id'], **result)), flush=True)
            save(target / 'attempts.json', chain.collector.attempts)
        if len(chain.update(8)) != 8: raise ValueError('Insufficient credit for fixed checkpoint probe')
        save_start = time.perf_counter(); sha = save_checkpoint(chain, target / 'checkpoint')
        save(target / 'checkpoint_receipt.json', dict(sha256=sha, save_wall_s=time.perf_counter() - save_start,
            bytes=(target / 'checkpoint/state.pt').stat().st_size))
        continue_chain(chain, target / 'continuous', protocol)
        run_logged([sys.executable, '-X', 'utf8', '-B', '-m', 'tools.validation.verify_sac_checkpoint',
            '--output', str(target), '--child', '--checkpoint-sha', sha], target / 'resume_process.log')
        elapsed = time.perf_counter() - start
        report = audit(target)
        report.update(probe_wall_s=elapsed, tests=json.loads(path.read_text(encoding='utf-8'))['tests'])
        save(target / 'assessment.json', report)
        save(target / 'manifest.json', dict(version='b2_checkpoint_delivery_v1', files={
            p.relative_to(ROOT).as_posix(): digest(p) for p in target.rglob('*') if p.is_file() and p != target / 'manifest.json'}))
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return report
    except Exception as exc:
        save(target / 'assessment.json', dict(full_checkpoint_verified=False, runnable_trainer=False, error=repr(exc)))
        if chain is not None:
            save(target / 'attempts.json', chain.collector.attempts); save(target / 'updates.json', chain.history)
        raise


def recheck(output):
    target = Path(output).resolve()
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8')); verify_files(ROOT, manifest['files'])
    actual = audit(target); report = json.loads((target / 'assessment.json').read_text(encoding='utf-8'))
    if any(report[k] != v for k, v in actual.items()): raise ValueError('Saved assessment does not reproduce')
    print(json.dumps(actual, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--child', action='store_true'); parser.add_argument('--checkpoint-sha')
    parser.add_argument('--recheck', action='store_true'); args = parser.parse_args()
    if args.child: child(args.output.resolve(), args.checkpoint_sha)
    elif args.recheck: recheck(args.output)
    else: run(args.output)
