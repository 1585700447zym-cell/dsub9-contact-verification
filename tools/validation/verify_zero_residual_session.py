"""Re-integrate all seven DEVELOPMENT B2 cases and compare every archived field.

Exact comparison (no tolerance tuning); writes to a new tag only. This checks
the compatibility session, not the v3 guards or training admission.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import gzip
import hashlib
import json
from pathlib import Path
import time

from tools.learning.runtime import ROOT, verify_runtime


def development_case_paths():
    return sorted((p.parent for p in (ROOT / 'deliverables/native313_baseline_matrix/b2_v1').glob('*/original.json.gz')), key=str)


def compare_exact(actual, expected, label):
    if actual != expected:
        if isinstance(actual, dict) and isinstance(expected, dict):
            differences = [k for k in set(actual) | set(expected) if actual.get(k) != expected.get(k)]
        else:
            differences = ['value']
        raise AssertionError(f'{label}: exact comparison failed: {differences}')


def read_archive(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')


def run_case(original_path, output):
    runtime = verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    from tools.learning.session import EpisodeSession
    from tools.validation.run_b1_baseline import cases
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    original_path, output = Path(original_path), Path(output)
    old = read_archive(original_path)
    tail_path = original_path.parent / 'stop_extension.json.gz'
    tail = read_archive(tail_path)
    started = time.perf_counter()
    session = EpisodeSession()
    case = next(c for c in cases() if c.name == old['case']['name'])
    result = dict(case=case.name, status='RUNNING', training_admitted=False,
                  runtime=runtime, comparison='exact_python_value_equality_no_tolerance',
                  source_archive_sha256={str(original_path.relative_to(ROOT)): digest(original_path),
                                         str(tail_path.relative_to(ROOT)): digest(tail_path)},
                  task_cycles_compared=0, tail_cycles_compared=0)
    write_json(output, result)
    try:
        session.reset(case, seed=2026092201)
        compare_exact(session.initial_trace_row, old['trace'][0], 'initial')
        for i, expected in enumerate(old['trace'][1:], 1):
            cycle = session.advance_cycle([0, 0, 0, 0])
            compare_exact(cycle.trace_row, expected, f'task cycle {i}')
            if i < len(old['trace']) - 1 and session.task_finished:
                raise AssertionError('Task window ended early')
            result['task_cycles_compared'] = i
            if i % 1000 == 0:
                write_json(output, result)
                print(f'{case.name}: compared {i} task cycles', flush=True)
        assert session.task_finished, 'Task window did not end at archived time'
        compare_exact(session.reason, old['termination'], 'termination')
        compare_exact(session.stop_time, old['stop_time_s'], 'decision time')
        compare_exact(session.env.observe(), old['final'], 'task final')
        compare_exact(session.env.events, old['events'], 'task events')
        compare_exact(session.controller.events, old['policy_events'], 'policy events')
        compare_exact(session.env.observe(), tail['trace'][0], 'tail initial')
        for i, expected in enumerate(tail['trace'][1:], 1):
            session.advance_cycle([0, 0, 0, 0])
            compare_exact(session.env.observe(), expected, f'tail cycle {i}')
            result['tail_cycles_compared'] = i
        assert session.done, 'Safety tail not complete'
        compare_exact(session.env.events, tail['events'], 'tail events')
        compare_exact(session.env.peaks, tail['peaks'], 'cumulative peaks')
        compare_exact(session.env.stop_samples, tail['physical_stop_samples'], 'physical stop samples')
        stop_pass = actual_stop_pass(session.env.stop_samples, session.env.events, session.stop_time,
                                     session.env.data.time, session.env.config.timestep)
        final_pass = physical_tail_pass(session.env.stop_samples, session.env.data.time, session.env.config.timestep)
        assert stop_pass and final_pass
        result.update(status='PASS', termination=session.reason, task_end_time_s=session.task_end_time,
                      end_time_s=float(session.env.data.time), physical_stopped=True,
                      physical_steps=session.env.physical_steps, config=asdict(session.controller.config))
    except Exception as exc:
        result.update(status='FAIL', error=repr(exc))
    result['wall_seconds'] = time.perf_counter() - started
    write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--workers', type=int, default=3, choices=range(1, 5))
    args = parser.parse_args()
    if not args.tag or Path(args.tag).name != args.tag or args.tag in ('.', '..'):
        raise ValueError('Use a single folder name')
    target = ROOT / 'deliverables/residual_interface' / args.tag
    target.mkdir(exist_ok=False)
    paths = [folder / 'original.json.gz' for folder in development_case_paths()]
    if len(paths) != 7:
        raise RuntimeError('Expected exactly seven frozen development cases')
    sources = list((ROOT / 'tools/learning').glob('*.py')) + [Path(__file__).resolve()]
    fingerprints = {str(p.relative_to(ROOT)): digest(p) for p in sources}
    write_json(target / 'source_sha256.json', fingerprints)
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(run_case, str(p), str(target / (p.parent.name + '.json'))) for p in paths]
        results = []
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(result['case'], result['status'], result.get('error', ''), flush=True)
    unchanged = fingerprints == {str(p.relative_to(ROOT)): digest(p) for p in sources}
    summary = dict(passed=unchanged and all(r['status'] == 'PASS' for r in results),
                   source_unchanged=unchanged, runs=results, wall_seconds=time.perf_counter()-started,
                   training_admitted=False, scope='compatibility_wrapper_development_only')
    write_json(target / 'assessment.json', summary)
    raise SystemExit(0 if summary['passed'] else 1)


if __name__ == '__main__':
    main()
