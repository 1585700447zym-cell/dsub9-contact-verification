"""Zero residual through observation/reward/action layer vs frozen and same-guard B2.

Development cases only, no training. Fresh output tag required; exact comparison
is predeclared, no tolerance tuning or replacement of historical manifests.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
import gzip
import hashlib
import json
from pathlib import Path
import time
from tools.learning.runtime import ROOT
from tools.validation.guard_evidence import input_fingerprints, snapshot_inputs
from tools.validation.verify_guard_baseline import development_cases, run_case
from tools.validation.verify_zero_residual_session import read_archive, compare_exact


def compare_candidate(actual, reference):
    for field in ('trace', 'events', 'physical_stop_samples', 'guard_facts', 'outcome', 'physical_steps'):
        compare_exact(actual[field], reference[field], 'same_guard_' + field)


def run_residual_case(name):
    report = run_case(name, residual_interface=True)
    reference = ROOT / 'deliverables/residual_interface/guard_b2_regression_v3_review_fixes' / (name+'.json.gz')
    report['candidate_reference_sha256'] = hashlib.sha256(reference.read_bytes()).hexdigest()
    report['same_guard_match'] = False
    try:
        compare_candidate(report, read_archive(reference))
        expected = 10. if report['outcome']['task_outcome'] == 'FULL_SUCCESS' else -2.
        compare_exact(report['interface']['terminal_rewards'], [expected], 'unique_terminal_reward')
        report['same_guard_match'] = True
    except Exception as exc:
        report['candidate_error'] = repr(exc)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    if Path(args.tag).name != args.tag or args.tag in ('', '.', '..'):
        raise ValueError('New single folder name required')
    target = ROOT / 'deliverables/residual_interface' / args.tag
    target.mkdir(exist_ok=False)
    hashes = input_fingerprints()
    snapshot_inputs(target, hashes)
    def dump(path, obj):
        path.write_text(json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf-8')
    names = development_cases()
    if len(names) != 7:
        raise RuntimeError('Exactly seven historical development cases required')
    dump(target/'protocol.json', dict(cases=names, source_sha256=hashes,
        comparison='exact_all_archived_fields_and_same_guard_version_no_tolerance',
        action=[0.]*4, training_admitted=False))
    start = time.perf_counter()
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(run_residual_case, name): name for name in names}
        for future in as_completed(jobs):
            name = jobs[future]
            try:
                report = future.result()
            except Exception as exc:
                report = dict(case=name, exact_history_match=False, same_guard_match=False, error=repr(exc))
            (target/(name+'.json.gz')).write_bytes(gzip.compress(
                json.dumps(report, ensure_ascii=False, allow_nan=False).encode('utf-8'), mtime=0))
            compact = {k: v for k, v in report.items() if k not in ('trace', 'physical_stop_samples', 'runtime')}
            rows.append(compact)
            print(name, report['exact_history_match'], report['same_guard_match'],
                  report.get('error', report.get('candidate_error')), flush=True)
    unchanged = hashes == input_fingerprints()
    passed = unchanged and len(rows) == 7 and all(r['exact_history_match'] and r['same_guard_match'] for r in rows)
    dump(target/'assessment.json', dict(passed=passed, source_unchanged=unchanged,
        wall_seconds=time.perf_counter()-start, runs=sorted(rows, key=lambda r: r['case']), training_admitted=False))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
