"""Prespecified dynamic guard probes, not learning-domain certification.

Free-approach trials start 1mm farther back (-5mm), with contacts ENABLED.
Contact trials start at the original -4mm with bounded open-loop commands.
Neither class is a SAC result or a replacement for same-version B1/B2.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, replace
import gzip
import json
import math
from pathlib import Path
import time
import numpy as np

from tools.learning.runtime import ROOT, verify_runtime
from tools.validation.guard_evidence import input_fingerprints, snapshot_inputs


PROBES = {
    'free_roll_pos': (3, .02, False), 'free_roll_neg': (3, -.02, False),
    'free_pitch_pos': (4, .02, False), 'free_pitch_neg': (4, -.02, False),
    'contact_roll_pos': (3, .005, True), 'contact_pitch_neg': (4, -.005, True),
}


def run_probe(name):
    runtime = verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.validation.run_contact_cases import ContactCase
    from tools.validation.native313_matrix_audit import actual_stop_start, actual_stop_pass, archive_nonfinite
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    axis, speed, contact_trial = PROBES[name]
    case = replace(ContactCase.aligned(), name=name,
                   start_origin_z_m=-.004 if contact_trial else -.005,
                   x_offset_m=100e-6 if contact_trial else 0.)
    e = LearningEnvironment(guard_config=GuardCandidateConfig(
        max_rotation_from_start_rad=math.radians(2.5), initial_roll_pitch_limit_rad=math.radians(1.5)))
    started = time.perf_counter()
    trace = []
    error = None
    try:
        trace.append(e.reset(case))
        command = np.zeros(6)
        command[axis] = speed
        if contact_trial:
            command[2] = .001
        while e.phase != 'TERMINAL':
            if e.phase == 'RUNNING' and e.data.time >= 4. - 1e-10:
                e.stop('PROBE_TIME_LIMIT')
            stop = actual_stop_start(e.events, None)
            if stop is not None and e.data.time >= stop + 2. - 1e-10:
                break
            e.begin_cycle()
            row = e.step(command)
            trace.append(dict(row, cycle_peaks=dict(e.cycle_peaks), guard_facts=e.guard_facts))
    except Exception as exc:
        error = repr(exc)
    stop = actual_stop_start(e.events, None)
    stopped = bool(error is None and e.phase == 'STOPPING' and
                   actual_stop_pass(e.stop_samples, e.events, None, e.data.time, e.config.timestep) and
                   physical_tail_pass(e.stop_samples, e.data.time, e.config.timestep))
    facts = e.guard_facts
    expected = bool(facts['contact_reasons'] if contact_trial else 'ROTATION_LIMIT' in facts['motion_reasons'])
    report = dict(probe=name, case=asdict(case), command_axis=axis, requested_angular_speed=speed,
                  scope='bounded_open_loop_contact' if contact_trial else 'free_approach_boundary_not_training_domain',
                  runtime=runtime, environment=e.metadata(), error=error,
                  simulation_valid=error is None and facts['simulation_valid'], physical_stopped=stopped,
                  expected_event_observed=expected, guard_facts=facts,
                  max_rotation_deg=math.degrees(facts['max_rotation_from_start_rad']),
                  actual_stop_start_s=stop, end_time_s=float(e.data.time),
                  events=e.events, peaks=e.peaks, physical_steps=e.physical_steps,
                  physical_stop_samples=e.stop_samples, trace=trace,
                  wall_seconds=time.perf_counter()-started, training_admitted=False)
    report['probe_passed'] = bool(report['simulation_valid'] and stopped and expected)
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
    hashes = input_fingerprints()
    snapshot_inputs(target, hashes)
    def dump(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n', encoding='utf-8')
    dump(target / 'protocol.json', dict(probes=PROBES, source_sha256=hashes,
                                      budget_s=4., final_stop_s=2., training_admitted=False))
    summaries = []
    started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_probe, name): name for name in PROBES}
        for future in as_completed(futures):
            name = futures[future]
            try:
                report = future.result()
            except Exception as exc:
                report = dict(probe=name, probe_passed=False, error=repr(exc), training_admitted=False)
            raw = json.dumps(report, ensure_ascii=False, allow_nan=False).encode('utf-8')
            (target / (name + '.json.gz')).write_bytes(gzip.compress(raw, mtime=0))
            compact = {k: v for k, v in report.items() if k not in ('trace', 'physical_stop_samples', 'runtime', 'environment')}
            summaries.append(compact)
            print(name, compact.get('probe_passed'), compact.get('max_rotation_deg'), compact.get('error'), flush=True)
    unchanged = hashes == input_fingerprints()
    verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    passed = unchanged and len(summaries) == len(PROBES) and all(x['probe_passed'] for x in summaries)
    dump(target / 'assessment.json', dict(probe_suite_passed=passed, source_unchanged=unchanged,
         runs=sorted(summaries, key=lambda x: x['probe']), training_admitted=False,
         wall_seconds=time.perf_counter()-started,
         limitations=['candidate_parameter_not_frozen', 'no_continuous_domain_proof', 'no_SAC_updates']))
    raise SystemExit(0 if passed else 1)


if __name__ == '__main__':
    main()
