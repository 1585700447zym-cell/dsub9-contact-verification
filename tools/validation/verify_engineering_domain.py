"""Preregistered finite engineering-domain probes; NEVER a training admission.

Original B2 + residual lifecycle, physics and guard candidate are unchanged.
No automatic resampling, independent dataset, parameter sweep or training.
"""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
import gzip
import json
import math
from pathlib import Path
import re
import time

import numpy as np

from tools.learning.runtime import ROOT, verify_runtime
from tools.learning.episode_buffer import _safe_error_archive
from tools.validation.guard_evidence import input_fingerprints, snapshot_inputs


SEED = 2026092406
WATCHDOG_CYCLES = 13000  # 26s: diagnostic failure, not a new task budget.


def build_protocol():
    points = [('center', 0., 0.)]
    points += [(f'corner_{i}', x * 50e-6, y * 50e-6)
               for i, (x, y) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1)))]
    rng = np.random.Generator(np.random.PCG64(SEED))
    points += [(f'random_{i}', float(x), float(y))
               for i, (x, y) in enumerate(rng.uniform(-50e-6, 50e-6, (4, 2)))]
    attempts = []

    def add(kind, point, action, family, suffix=''):
        name, x, y = point
        key = f'{kind}_{name}{suffix}'
        case = dict(name=key, x_offset_m=x, y_offset_m=y, roll_rad=0., pitch_rad=0.,
                    start_origin_z_m=-.004, target_depth_m=.004)
        attempts.append(dict(id=key, kind=kind, family=family, case=case, action=list(action)))

    for point in points:
        add('initialization', point, [0.] * 4, 'initialization')
    for point in points[:5]:
        add('dynamic', point, [0.] * 4, 'zero', '_zero')
    for axis, name in enumerate(('x', 'y', 'roll', 'pitch')):
        for sign, direction in ((-1., 'neg'), (1., 'pos')):
            action = [0.] * 4
            action[axis] = sign
            add('dynamic', points[0], action, 'single_axis', f'_{name}_{direction}')
    for point in points[1:5]:
        x, y = float(np.sign(point[1])), float(np.sign(point[2]))
        add('dynamic', point, [x, y, x, y], 'coupled_corner', '_outward')
    return dict(version='engineering_preflight_v1', seed=SEED, rng='PCG64',
        data_use='development_only', training_admitted=False, domain_qualified=False,
        guard_config=dict(max_rotation_from_start_rad=math.radians(2.5),
                          initial_roll_pitch_limit_rad=math.radians(1.5)),
        timestep_s=.0002, control_period_s=.002, watchdog_cycles=WATCHDOG_CYCLES,
        action_schedule='constant normalized request; existing per-cycle permission masks apply',
        completion='original full task lifecycle plus final actual-stop audit; no voluntary short cut',
        attempts=attempts)


def fresh_output(parent, tag):
    if not isinstance(tag, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}', tag):
        raise ValueError('Fresh ASCII single-folder tag required')
    target = Path(parent) / tag
    target.mkdir(exist_ok=False)
    return target


def run_attempt(spec, *, watchdog_cycles=WATCHDOG_CYCLES):
    runtime = verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.learning.residual_session import ResidualSession
    from tools.validation.run_contact_cases import ContactCase

    started = time.perf_counter()
    report = dict(id=spec['id'], kind=spec['kind'], case=deepcopy(spec['case']),
        action=list(spec['action']), runtime=runtime, initialization_valid=False,
        simulation_valid=False, physical_stopped=False, observation_valid=True,
        masking_valid=True, completed=False, command_effect_cycles=0, active_cycles=0,
        masked_cycles=0, contact_cycles=0, trace=[], error=None,
        training_admitted=False, model_scope_qualified=False, valid_for_learning=False)
    session = None

    def vector_valid(snapshot):
        obs = np.asarray(snapshot.policy_observation)
        return bool(obs.shape == (120,) and np.isfinite(obs).all() and
                    np.all(obs >= -10) and np.all(obs <= 10))

    def record_cycle(result):
        log = result.action_log
        report['active_cycles' if log['enabled'] else 'masked_cycles'] += 1
        report['contact_cycles'] += int(result.trace_row['contact_count'] > 0)
        report['command_effect_cycles'] += int(np.any(np.abs(log['effective_command_delta']) > 1e-15))
        current_mask_valid = bool(log['enabled'] or
            not (np.any(log['experience_action']) or np.any(log['applied_residual'])))
        current_observation_valid = vector_valid(result.next_snapshot)
        report['masking_valid'] &= current_mask_valid
        report['observation_valid'] &= current_observation_valid
        report['trace'].append(dict(physical=result.trace_row, action_log=log,
            cycle_peaks=result.cycle_peaks, reward=result.reward_terms, dt=result.dt,
            task_finished=result.task_finished, done=result.done))
        # Historical failure remains latched for rejection; healthy subsequent
        # stop cycles must not throw solely because an earlier diagnostic failed.
        if not current_observation_valid or not current_mask_valid:
            raise ValueError('Invalid observation or permission result in preflight')

    try:
        session = ResidualSession(environment=LearningEnvironment(
            guard_config=GuardCandidateConfig(**build_protocol()['guard_config'])))
        initial = session.reset(ContactCase(**spec['case']), seed=SEED)
        report['initialization_valid'] = True
        report['observation_valid'] = vector_valid(initial)
        report['initial_state'] = initial.state
        report['initial_policy_observation'] = initial.policy_observation
        report['environment'] = session.env.metadata()
        if not report['observation_valid']:
            raise ValueError('Invalid initial policy observation')
        if spec['kind'] == 'dynamic':
            for _ in range(watchdog_cycles):
                if session.done:
                    break
                record_cycle(session.advance_cycle(spec['action']))
            if not session.done:
                report['error'] = 'WATCHDOG_EXCEEDED'
                session.start_external_tail()
                for _ in range(1500):
                    if session.done:
                        break
                    record_cycle(session.advance_cycle([0.] * 4))
                if not session.done:
                    report['stop_error'] = 'WATCHDOG_STOP_INCOMPLETE'
            outcome = session.adjudicate()
            report.update(physical_stopped=outcome['physical_stopped'],
                task_outcome=outcome['task_outcome'], outcome=outcome,
                completed=bool(session.done and report['error'] is None))
        else:
            report['completed'] = True  # Initialization only, never a stop audit.
    except Exception as exc:
        report['error'] = report['error'] or repr(exc)
        report['exception'] = repr(exc)
        # If the existing session still allows interaction, request an explicit
        # safety tail. Invalid sessions already fail closed; don't manufacture data.
        if session is not None and session._ready and not session.done:
            try:
                session.start_external_tail()
                for _ in range(1500):
                    if session.done:
                        break
                    record_cycle(session.advance_cycle([0.] * 4))
                report['physical_stopped'] = session.adjudicate()['physical_stopped']
            except Exception as stop_exc:
                report['stop_error'] = repr(stop_exc)
    if session is not None:
        e = session.env
        report.update(simulation_valid=e.guard_facts['simulation_valid'], guard_facts=e.guard_facts,
            events=e.events, physical_stop_samples=e.stop_samples, physical_steps=e.physical_steps,
            peaks=e.peaks, end_time_s=float(e.data.time), final_phase=e.phase,
            max_rotation_deg=math.degrees(e.guard_facts['max_rotation_from_start_rad']))
    report['wall_seconds'] = time.perf_counter() - started
    return _safe_error_archive(report)


def summarize(protocol, reports, *, source_unchanged):
    planned = {r['id']: r for r in protocol['attempts']}
    ids = [r.get('id') for r in reports]
    accounting = len(ids) == len(set(ids)) == len(planned) and set(ids) == set(planned)
    checks = []
    for row in reports:
        spec = planned.get(row.get('id'), {})
        valid = bool(spec and row.get('kind') == spec['kind'] and row.get('error') is None)
        valid &= bool(spec and row.get('case') == spec['case'] and row.get('action') == spec['action'])
        valid &= all(row.get(k) is True for k in
                     ('initialization_valid', 'simulation_valid', 'observation_valid', 'masking_valid', 'completed'))
        valid &= all(row.get(k) is False for k in
                     ('training_admitted', 'model_scope_qualified', 'valid_for_learning'))
        if spec.get('kind') == 'dynamic':
            valid &= row.get('physical_stopped') is True
            if any(spec['action']):
                count = row.get('command_effect_cycles')
                valid &= type(count) is int and count > 0
        checks.append(dict(id=row.get('id'), passed=bool(valid)))
    dynamics = [r for r in reports if r.get('kind') == 'dynamic']
    return dict(sample_checks_passed=bool(source_unchanged is True and accounting and all(r['passed'] for r in checks)),
        source_unchanged=source_unchanged, accounting_complete=accounting,
        attempts_planned=len(planned), attempts_recorded=len(reports), checks=checks,
        initialization_valid=sum(r.get('initialization_valid') is True for r in reports if r.get('kind') == 'initialization'),
        dynamic_valid_stopped=sum(r.get('simulation_valid') is True and r.get('physical_stopped') is True for r in dynamics),
        dynamic_task_successes=sum(r.get('task_outcome') == 'FULL_SUCCESS' for r in dynamics),
        training_admitted=False, domain_qualified=False,
        limitations=['finite development samples, not continuous-domain certification',
                     'zero initial roll/pitch only; no pose parameter freeze',
                     'command effect is not evidence of beneficial physical causality',
                     'no SAC updates, independent test or formal training admission'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=3)
    args = parser.parse_args()
    verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    target = fresh_output(ROOT / 'deliverables/residual_interface', args.tag)
    protocol = build_protocol()
    hashes = input_fingerprints()
    snapshot_inputs(target, hashes)
    protocol['source_sha256'] = hashes
    def dump(path, value):
        path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2) + '\n', encoding='utf-8')
    dump(target / 'protocol.json', protocol)  # Frozen BEFORE any physical attempt.
    start = time.perf_counter()
    reports = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs = {pool.submit(run_attempt, spec): spec for spec in protocol['attempts']}
        for future in as_completed(jobs):
            spec = jobs[future]
            try:
                report = future.result()
            except Exception as exc:
                report = dict(id=spec['id'], kind=spec['kind'], case=spec['case'], action=spec['action'],
                              error=repr(exc), training_admitted=False)
            raw = json.dumps(report, ensure_ascii=False, allow_nan=False).encode('utf-8')
            (target / (spec['id'] + '.json.gz')).write_bytes(gzip.compress(raw, mtime=0))
            compact = {k: v for k, v in report.items() if k not in
                       ('trace', 'physical_stop_samples', 'runtime', 'environment', 'initial_policy_observation')}
            reports.append(compact)
            dump(target / 'attempts_so_far.json', reports)
            print(spec['id'], report.get('task_outcome', 'INITIALIZATION'),
                  'stopped=', report.get('physical_stopped'), 'error=', report.get('error'), flush=True)
    assessment = summarize(protocol, reports, source_unchanged=hashes == input_fingerprints())
    assessment.update(runs=sorted(reports, key=lambda r: r['id']), wall_seconds=time.perf_counter() - start)
    dump(target / 'assessment.json', assessment)
    raise SystemExit(0 if assessment['sample_checks_passed'] else 1)


if __name__ == '__main__':
    main()
