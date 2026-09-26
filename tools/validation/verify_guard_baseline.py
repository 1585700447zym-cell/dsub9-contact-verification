"""Re-integrate seven development B2 episodes with candidate common guards.

Exact comparison against frozen original and stop-tail archives. Passing proves
no observed behavior change in THESE cases, not all-policy branch equivalence.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import gzip
import hashlib
import json
import math
from pathlib import Path
import time

from tools.learning.runtime import ROOT, verify_runtime
from tools.validation.verify_zero_residual_session import read_archive, compare_exact, development_case_paths
from tools.validation.guard_evidence import input_fingerprints, snapshot_inputs
from tools.validation.native313_matrix_audit import archive_nonfinite


def development_cases():
    return [p.name for p in development_case_paths()]


def run_case(name, *, residual_interface=False):
    runtime = verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.learning.guarded_session import CandidateEpisodeSession
    from tools.validation.run_b1_baseline import cases
    base = ROOT / 'deliverables/native313_baseline_matrix/b2_v1' / name
    old, tail = read_archive(base / 'original.json.gz'), read_archive(base / 'stop_extension.json.gz')
    session_class = CandidateEpisodeSession
    if residual_interface:
        from tools.learning.residual_session import ResidualSession
        session_class = ResidualSession
    s = session_class(environment=LearningEnvironment(guard_config=GuardCandidateConfig(
        max_rotation_from_start_rad=math.radians(2.5), initial_roll_pitch_limit_rad=math.radians(1.5))))
    started = time.perf_counter()
    report = dict(case=name, runtime=runtime, exact_history_match=False, training_admitted=False,
                  task_cycles_compared=0, tail_cycles_compared=0,
                  source_archive_sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in (base / 'original.json.gz', base / 'stop_extension.json.gz')})
    trace = []
    reward_total, terminal_rewards = 0., []

    def check_interface(result):
        nonlocal reward_total
        if not residual_interface:
            return
        import numpy as np
        vector = result.next_snapshot.policy_observation
        if len(vector) != 120 or not np.isfinite(vector).all():
            raise AssertionError('Invalid policy observation in regression')
        if result.action_log['experience_action'] != [0.]*4:
            raise AssertionError('Zero residual was not preserved')
        reward_total += result.reward_terms['total']
        if result.reward_terms['terminal']:
            terminal_rewards.append(result.reward_terms['terminal'])
    try:
        s.reset(next(c for c in cases() if c.name == name), seed=2026092201)
        compare_exact(s.initial_trace_row, old['trace'][0], 'initial')
        trace.append(s.initial_trace_row)
        for i, expected in enumerate(old['trace'][1:], 1):
            result = s.advance_cycle([0]*4)
            check_interface(result)
            trace.append(result.trace_row)
            compare_exact(result.trace_row, expected, f'task cycle {i}')
            if i < len(old['trace'])-1 and s.task_finished:
                raise AssertionError('Candidate task window ended early')
            report['task_cycles_compared'] = i
            if i % 1500 == 0:
                print(name, i, 'task cycles compared', flush=True)
        if not s.task_finished:
            raise AssertionError('Candidate task window ended late')
        for label, actual, expected in (
                ('termination', s.reason, old['termination']),
                ('decision time', s.stop_time, old['stop_time_s']),
                ('task final', s.env.observe(), old['final']),
                ('events', s.env.events, old['events']),
                ('policy events', s.controller.events, old['policy_events']),
                ('tail start', s.env.observe(), tail['trace'][0])):
            compare_exact(actual, expected, label)
        for i, expected in enumerate(tail['trace'][1:], 1):
            result = s.advance_cycle([0]*4)
            check_interface(result)
            trace.append(s.env.observe())
            compare_exact(s.env.observe(), expected, f'tail cycle {i}')
            report['tail_cycles_compared'] = i
        compare_exact(s.env.events, tail['events'], 'tail events')
        compare_exact(s.env.peaks, tail['peaks'], 'peaks')
        compare_exact(s.env.stop_samples, tail['physical_stop_samples'], 'stop substeps')
        if not s.done or not s.adjudicate()['physical_stopped']:
            raise AssertionError('Candidate physical stop audit failed')
        report['exact_history_match'] = True
    except Exception as exc:
        report['error'] = repr(exc)
    report.update(guard_facts=s.env.guard_facts, outcome=s.adjudicate(), events=s.env.events,
                  physical_steps=s.env.physical_steps, trace=trace, physical_stop_samples=s.env.stop_samples,
                  wall_seconds=time.perf_counter()-started)
    if residual_interface:
        report['interface'] = dict(observation_version=s.observations.version,
            schema=s.observations.schema, reward_total=reward_total, terminal_rewards=terminal_rewards)
    return archive_nonfinite(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--workers', type=int, default=3, choices=range(1, 5))
    args = parser.parse_args()
    if Path(args.tag).name != args.tag or args.tag in ('', '.', '..'):
        raise ValueError('Use a new single folder name')
    target = ROOT / 'deliverables/residual_interface' / args.tag
    target.mkdir(exist_ok=False)
    names = development_cases()
    if len(names) != 7:
        raise RuntimeError('Expected exactly seven development cases')
    hashes = input_fingerprints()
    snapshot_inputs(target, hashes)
    def dump(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf-8')
    dump(target / 'protocol.json', dict(cases=names, source_sha256=hashes,
         comparison='exact_all_archived_fields_no_tolerance', training_admitted=False))
    started = time.perf_counter()
    summaries = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_case, name): name for name in names}
        for future in as_completed(futures):
            name = futures[future]
            try:
                report = future.result()
            except Exception as exc:
                report = dict(case=name, exact_history_match=False, error=repr(exc), training_admitted=False)
            (target / (name + '.json.gz')).write_bytes(gzip.compress(
                json.dumps(report, ensure_ascii=False, allow_nan=False).encode('utf-8'), mtime=0))
            compact = {k: v for k, v in report.items() if k not in ('trace', 'physical_stop_samples', 'runtime')}
            summaries.append(compact)
            print(name, compact['exact_history_match'], compact.get('error'), flush=True)
    unchanged = hashes == input_fingerprints()
    verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    passed = unchanged and all(r['exact_history_match'] for r in summaries) and len(summaries) == 7
    dump(target / 'assessment.json', dict(passed=passed, source_unchanged=unchanged,
         runs=sorted(summaries, key=lambda r: r['case']), training_admitted=False,
         wall_seconds=time.perf_counter()-started))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
