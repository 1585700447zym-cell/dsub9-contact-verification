"""Zero-residual episode driver. Scientific imports are confined to physical_case."""
import math
from pathlib import Path
import sys
import time
from dataclasses import asdict

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
from contract import ROOT, LIMITS, SEED, read, write, digest, case_kwargs, check_pose, check_runtime


def check_zero_log(log):
    for field, width in [('raw_action', 4), ('experience_action', 4),
                         ('requested_residual', 6), ('applied_residual', 6),
                         ('effective_command_delta', 6)]:
        values = log[field]
        if len(values) != width or any(type(v) not in (int, float) or
                                       not math.isfinite(v) or v != 0. for v in values):
            raise ValueError('Nonzero/nonfinite learned correction in pure B2: ' + field)


def drive_zero(session, snapshot, *, clock=time.monotonic, stop=lambda: False,
               cycle_limit=14500, wall_limit=1200, progress=lambda *args: None,
               resource_check=lambda: None):
    started = clock(); trace = [session.initial_trace_row]; actions = []; transitions = []
    try:
        while not session.done:
            if session.cycle_id >= cycle_limit or clock() - started >= wall_limit or stop():
                raise RuntimeError('Registered cycle/wall/STOP bound; no retry')
            resource_check()
            result = session.advance_cycle([0., 0., 0., 0.])
            trace.append(result.trace_row); actions.append(result.action_log)
            check_zero_log(result.action_log)
            if type(result.dt) not in (int, float) or not math.isfinite(result.dt) or result.dt <= 0:
                raise ValueError('Invalid physical control interval')
            transitions.append(dict(observation=snapshot.policy_observation,
                  next_observation=result.next_snapshot.policy_observation,
                  action=[0., 0., 0., 0.], action_active=snapshot.residual_enabled,
                  next_action_active=result.next_snapshot.residual_enabled,
                  reward=result.reward_terms['total'], reward_terms={**dict(terminal=0.), **result.reward_terms},
                  dt=result.dt, discount=math.exp(-result.dt / 10), terminated=bool(result.done), truncated=False,
                  cycle_force_N=result.cycle_peaks['force_N'], cycle_torque_G_Nm=result.cycle_peaks['torque_G_Nm'],
                  advance_m=result.trace_row['position_m'][2] - session.initial[2],
                  action_log=result.action_log, trace_row=result.trace_row, sampling_request=None))
            progress(session.cycle_id, trace, actions, transitions, snapshot)
            snapshot = result.next_snapshot
    except BaseException as exc:
        exc.episode_partial = dict(trace=trace, actions=actions, transitions=transitions)
        raise
    return dict(trace=trace, actions=actions, transitions=transitions)


def make_session(environment, common):
    # Identical factory/referee path to the frozen SCOPE20 joint_rollout.
    from tools.validation.run_v4_adapter_preflight import make_session as wiring
    from tools.learning.v4_continuation import ContinuationResidualSession
    base = wiring(environment, 'F50', common)
    return ContinuationResidualSession(environment=environment, mode='F50',
            controller_factory=base.controller_factory, finish_criteria=common['finish_criteria'],
            geometry_checker=base.geometry_checker)


def audit_baseline(raw, config):
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    point = config['cases'][raw['case_index']]
    if raw['case'] != point or raw['simulation_case'] != case_kwargs(point):
        raise ValueError('Pure B2 case differs from registered joint pose')
    check_pose(point, raw['trace'][0])
    if (raw['role'] != 'pure_B2' or raw['comparison_key'] != config['common_key'] or
            raw['policy_calls'] != 0 or raw['optimizer_steps'] != 0 or raw['policy_sha256'] is not None or
            raw['fault'] is not None or raw['reference_problems'] or raw['actual_reference_failed']):
        raise ValueError('Pure B2 identity or common runtime failed')
    for action in raw['actions']: check_zero_log(action)
    if (raw['control_cycles'] > LIMITS['per_episode_cycles'] or
            raw['physical_substeps'] > LIMITS['per_episode_native_steps']):
        raise ValueError('Physical bound exceeded')
    stopped = actual_stop_pass(raw['stop_samples'], raw['events'], raw['stop_time'],
                              raw['audit_end_time_s'], .0002)
    stopped = bool(stopped and physical_tail_pass(raw['stop_samples'], raw['audit_end_time_s'], .0002))
    out = raw['outcome']
    return bool(stopped and out['physical_stopped'] is True and out['simulation_valid'] is True and
                not any(out['guard_violations'].values()) and
                out['task_outcome'] in ('FULL_SUCCESS', 'TASK_FAILURE'))


def physical_case(config, point, index, run, receipt, binding):
    check_runtime(binding['numerical_runtime'], check_interpreter=True)
    if (not sys.flags.isolated or Path(sys.executable).resolve() != Path(binding['executable']).resolve()):
        raise PermissionError('Frozen isolated CPU interpreter required')
    from tools.learning.runtime import select_runtime, verify_runtime, active_package
    select_runtime(binding['runtime_record'], expected_digest=binding['runtime_record_sha256'])
    native = verify_runtime(active_package())
    if digest(native) != config['common']['runtime_proof_sha256']:
        raise ValueError('Native runtime proof differs from SCOPE20')
    from tools.learning.guarded_environment import LearningEnvironment, GuardCandidateConfig
    from tools.validation.run_contact_cases import ContactCase
    from tools.validation.run_clearance_preflight import archive_episode
    from tools.validation.run_v4_adapter_preflight import actual_reference_radius
    from tools.learning.outcome import classify_outcome
    common = config['common']; receipt['environment_creation_attempted'] = 1
    write(run / 'receipt.json', receipt)
    env = LearningEnvironment(guard_config=GuardCandidateConfig(**common['guard_config']),
                              model_xml=(OUT / 'model.xml').read_text(encoding='utf-8'))
    receipt['environment_created'] = 1; write(run / 'receipt.json', receipt)
    if asdict(env.config) != common['dynamic_config'] or asdict(env.guard_config) != common['guard_config']:
        raise ValueError('Physical/guard configuration drift')
    session = make_session(env, common); receipt['reset_attempted'] = 1
    write(run / 'receipt.json', receipt)
    snapshot = session.reset(ContactCase(**case_kwargs(point)), seed=SEED)
    receipt['reset_completed'] = 1; check_pose(point, session.initial_trace_row)
    write(run / 'receipt.json', receipt)
    started = time.monotonic(); max_radius = 0.; reference_checks = 0

    def resources():
        if env.physical_steps > LIMITS['per_episode_native_steps'] - 10:
            raise RuntimeError('Native-step ceiling before next control cycle')

    def progress(cycle, trace, actions, transitions, pre_snapshot):
        nonlocal max_radius, reference_checks
        # The issued command belongs to the pre-action phase, including SEARCH exit.
        radius = actual_reference_radius(pre_snapshot, trace[-1], session.initial)
        if radius is not None:
            reference_checks += 1; max_radius = max(max_radius, radius)
            if radius > .00012 + 1e-12: raise ValueError('Actual search reference radius exceeded')
        if cycle % 500 == 0 or session.done:
            receipt.update(control_cycles=cycle, physical_substeps=env.physical_steps,
                           simulated_time_s=float(env.data.time), policy_calls=0, formal_updates=0)
            write(run / 'receipt.json', receipt)
            archive_episode(run / 'episode.partial.json.gz', dict(trace=trace, actions=actions,
                            transitions=transitions, events=env.events, stop_samples=env.stop_samples))

    try:
        data = drive_zero(session, snapshot, stop=lambda: (OUT / 'STOP').exists(),
                          progress=progress, resource_check=resources)
        source = session.adjudicate()
        outcome = classify_outcome(simulation_valid=source['simulation_valid'],
                  physical_stopped=source['physical_stopped'],
                  contact_guard=bool(env.guard_facts['contact_reasons']),
                  motion_violation=bool(env.guard_facts['motion_reasons']),
                  full_success=session.task_finished and session.reason == 'GEOMETRIC_SUCCESS')
        raw = dict(version='v4_training_episode_v1', scope='frozen_development_evaluation',
                   role='pure_B2', episode_id='pure_B2_' + point['id'], mode='F50', stage='pure_B2',
                   case_id=point['id'], case_index=index, case=point,
                   simulation_case=asdict(ContactCase(**case_kwargs(point))), seed=SEED,
                   comparison_key=config['common_key'], optimizer_steps_start=0, optimizer_steps=0,
                   policy_sha256=None, policy_calls=0, observation_schema=session.observations.schema,
                   source_session_outcome=source, outcome=outcome, guard_facts=env.guard_facts,
                   events=env.events, stop_samples=env.stop_samples, stop_time=session.stop_time,
                   audit_end_time_s=float(env.data.time), task_end_time_s=session.task_end_time,
                   peaks=env.peaks, final_session=dict(task_finished=session.task_finished,
                       reason=session.reason, phase=env.phase), controller_events=session.controller.events,
                   reference_problems=[e for e in session.controller.events if e['reason'] in
                       ('SEARCH_REFERENCE_LIMIT', 'RESIDUAL_REFERENCE_INFEASIBLE', 'REFERENCE_ACTUAL_LIMIT')],
                   actual_reference_failed=False, max_actual_reference_radius_m=max_radius,
                   actual_reference_checks=reference_checks, control_cycles=session.cycle_id,
                   physical_substeps=env.physical_steps, wall_seconds=time.monotonic() - started,
                   fault=None, **data)
        receipt['archive_sha256'] = archive_episode(run / 'episode.json.gz', raw)
        receipt.update(status='finished', healthy=audit_baseline(raw, config), outcome=outcome,
                       control_cycles=session.cycle_id, physical_substeps=env.physical_steps,
                       wall_seconds=raw['wall_seconds'], policy_calls=0, formal_updates=0)
        write(run / 'receipt.json', receipt)
    except BaseException as exc:
        partial = getattr(exc, 'episode_partial', None)
        if partial is not None:
            archive_episode(run / 'episode.error.json.gz', dict(**partial, events=env.events,
                            stop_samples=env.stop_samples, guard_facts=env.guard_facts, error=repr(exc)))
        receipt.update(status='error', healthy=False, error=repr(exc), control_cycles=session.cycle_id,
                       physical_substeps=env.physical_steps, wall_seconds=time.monotonic() - started)
        write(run / 'receipt.json', receipt)
        raise
