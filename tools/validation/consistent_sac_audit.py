"""Independent saved-evidence audit for fresh repaired G1/30-second SAC.

No environment is created and no optimizer is called. Source trainers supplied
by the runner are disposable checkpoint restores used only to replay inference.
"""
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np

from tools.dynamics.reference_envelope import (VERSION as REFERENCE_VERSION,
    ReferenceIntersectionEmpty, constrain_xy)
from tools.learning.five_axis_contract import field_slices, permission
from tools.learning.five_axis_preparation import (COMMON, canonical, read, sha,
    _auditor, verify_rewards, verify_success_hold)
from tools.learning.global_residual_action import compose_command
from tools.learning.observation import POLICY_PHASES
from tools.validation.run_global_residual_authority import (
    verify_composition_log, verify_task_clock)

MAX_CYCLES = 16000


def verify_action_source(raw, receipt, job, *, source_trainer=None):
    """Reproduce every active request from the registered source and its RNG."""
    stage = job['stage']
    if stage not in ('baseline', 'warmup', 'online', 'development'):
        raise ValueError('Registered action-source stage required')
    baseline = stage == 'baseline'
    if not baseline and source_trainer is None:
        raise ValueError('Independent source trainer required for neural/warmup audit')
    before_calls = 0 if baseline else source_trainer.policy_calls
    before_draws = 0 if baseline else source_trainer.warmup_draws
    active_rows = 0
    for row in raw['transitions']:
        active = permission(row['observation'])
        if active != row['action_active']:
            raise ValueError('Action source permission differs')
        active_rows += active
        expected = np.zeros(5)
        if active and not baseline:
            expected = source_trainer.action(row['observation'],
                deterministic=stage == 'development', warmup=stage == 'warmup')
        requested = np.asarray(row['action_log']['raw_action'])
        if requested.shape != (5,) or not np.array_equal(requested, expected):
            raise ValueError('Saved request differs from zero baseline' if baseline else
                             'Saved request differs from restored source policy')
    calls = 0 if baseline else source_trainer.policy_calls - before_calls
    draws = 0 if baseline else source_trainer.warmup_draws - before_draws
    for key, value in (('policy_calls', calls), ('warmup_draws', draws)):
        if (receipt.get(key) != value or raw.get(key, 0 if baseline else None) != value):
            raise ValueError('Action source call/draw count differs: ' + key)
    if (raw.get('action_provider_calls') != active_rows or
            raw.get('action_provider_successes') != active_rows):
        raise ValueError('Collector action-provider call count differs')
    return dict(verified=True, stage=stage, active_rows=int(active_rows),
                policy_calls=calls, warmup_draws=draws,
                audit_inference_calls=calls, audit_warmup_replays=draws)


def verify_reference_checks(raw, receipt):
    """Check saved real endpoints and the native pre-force/post-step summary."""
    stats = receipt['reference_checks']
    names = ('pre_pd_checks', 'post_step_checks', 'feasible_checks', 'infeasible_checks')
    if any(type(stats.get(key)) is not int or stats[key] < 0 for key in names):
        raise ValueError('Exact native reference check counts required')
    total = stats['pre_pd_checks'] + stats['post_step_checks']
    steps = receipt['physical_substeps']
    if (stats['feasible_checks'] + stats['infeasible_checks'] != total or
            any(stats[key] > steps for key in ('pre_pd_checks', 'post_step_checks'))):
        raise ValueError('Native reference check accounting differs')
    for key in ('max_disk_excess_m', 'max_lead_excess_m'):
        value = stats.get(key)
        if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1e-12:
            raise ValueError('Native joint reference bound exceeded: ' + key)
    radius = receipt['controller_config']['spiral_radius_m']
    lead = receipt['dynamic_config']['reference_lead_m']
    if radius != .0004 or lead != .00012:
        raise ValueError('Frozen search radius/reference lead differs')
    endpoints = 0
    for state in raw['trace']:
        reference_state = state.get('reference_consistency', {})
        if reference_state and reference_state.get('version') != REFERENCE_VERSION:
            raise ValueError('Native reference implementation version differs')
        active = reference_state.get('active', False)
        center = state.get('reference_center_xy_m')
        if active:
            if state['phase'] != 'RUNNING' or state.get('policy_phase') != 'SEARCH' or center is None:
                raise ValueError('Malformed active SEARCH reference endpoint')
            reference = np.asarray(state['reference_qpos'][:2])
            actual = np.asarray(state['position_m'][:2]); center = np.asarray(center)
            if (center.shape != (2,) or not np.isfinite(center).all() or
                    np.linalg.norm(reference-center) > radius + 1e-12 or
                    np.max(abs(reference-actual)) > lead + 1e-12):
                raise ValueError('Saved real reference violates disk or current lead box')
            endpoints += 1
        elif center is not None:
            raise ValueError('Inactive reference must disarm its search center')
    if endpoints and (stats['pre_pd_checks'] == 0 or stats['post_step_checks'] == 0):
        raise ValueError('SEARCH endpoint lacks native reference checks')
    return dict(verified=True, active_trace_endpoints=endpoints, **stats)


def verify_reference_prediction(log, state, controller_config, lead):
    """Recompute the upper layer's fixed-actual prediction, without a rollout."""
    if log.get('reference_consistency_version') != REFERENCE_VERSION:
        raise ValueError('Composition lacks repaired reference implementation')
    if not (log['composition_inputs']['phase'] == 'SEARCH' and log['enabled']):
        return True
    actual = np.asarray(log['actual_before_xy_m'])
    reference = np.asarray(log['reference_before_xy_m'])
    center = np.asarray(log['reference_center_xy_m'])
    if (any(value.shape != (2,) or not np.isfinite(value).all() for value in (actual, reference, center)) or
            not np.allclose(actual, state['position_m'][:2], rtol=0, atol=1e-12)):
        raise ValueError('Reference prediction current-actual binding differs')
    radius = controller_config['spiral_radius_m']
    if not np.allclose(reference-center, log['reference_xy_m'], rtol=0, atol=1e-12):
        raise ValueError('Reference prediction disk coordinates differ')
    desired = reference + np.asarray(log['predicted_limited_command'][:2]) * log['composition_inputs']['dt']
    try:
        predicted = constrain_xy(desired, actual, center, radius, lead) - center
    except ReferenceIntersectionEmpty:
        if log.get('bounded_prediction_infeasible') is not True or log.get('predicted_bounded_reference_xy_m') is not None:
            raise ValueError('Infeasible reference prediction differs')
    else:
        if (log.get('bounded_prediction_infeasible') is not False or
                not np.allclose(log['predicted_bounded_reference_xy_m'], predicted, rtol=0, atol=1e-12)):
            raise ValueError('Fixed-actual bounded reference prediction differs')
    if log.get('bounded_prediction_assumes_fixed_actual') is not True:
        raise ValueError('Reference prediction assumption is missing')
    return True


def _verify_initial_pose(state, case):
    cr, sr = math.cos(case['roll_rad']/2), math.sin(case['roll_rad']/2)
    cp, sp = math.cos(case['pitch_rad']/2), math.sin(case['pitch_rad']/2)
    cy, sy = math.cos(case['yaw_rad']/2), math.sin(case['yaw_rad']/2)
    old = np.array([cp*cr, cp*sr, sp*cr, -sp*sr]); w, x, y, z = old
    quaternion = np.array([cy*w-sy*z, cy*x-sy*y, cy*y+sy*x, cy*z+sy*w])
    if (not np.allclose(state['position_m'],
            [case['x_offset_m'], case['y_offset_m'], case['start_origin_z_m']], rtol=0, atol=1e-12) or
            min(np.max(abs(np.asarray(state['quaternion_wxyz'])-quaternion)),
                np.max(abs(np.asarray(state['quaternion_wxyz'])+quaternion))) > 1e-12):
        raise ValueError('Actual initial pose differs from registered case')


def audit_archive(folder, reg, job, *, source_trainer=None, time_budget_group=None, force_recovery_group=None):
    """Read immutable bytes back before any replay publication or update."""
    from tools.learning.consistent_sac import VERSION, execution_contract
    from tools.learning.five_axis_replay import FiveAxisReplay
    folder = Path(folder); receipt = read(folder/'receipt.json')
    if sha(folder/'episode.json.gz') != receipt['archive_sha256']:
        raise ValueError('Raw archive byte digest differs')
    if sha(folder/'model_used.xml') != receipt['model_xml_sha256']:
        raise ValueError('Used XML byte digest differs')
    raw = json.loads(gzip.decompress((folder/'episode.json.gz').read_bytes()))
    contract = execution_contract()
    learning_version = VERSION
    if force_recovery_group is not None:
        if time_budget_group is not None: raise ValueError('Choose one explicit protocol')
        time_budget_group = force_recovery_group
    base_time_contract = None
    if time_budget_group is not None:
        from tools.learning.time_budget_trial import protocol_config
        contract = base_time_contract = protocol_config(time_budget_group)
        learning_version = None  # Frozen diagnostic, never relabel old training.
    if force_recovery_group is not None:
        from tools.learning.force_recovery_trial import protocol_config
        contract = protocol_config(force_recovery_group)
        if raw.get('force_recovery_protocol') != contract:
            raise ValueError('Force recovery protocol differs')
    if (reg['execution_contract'] != contract or receipt.get('execution_contract') != contract or
            raw.get('execution_contract') != contract or raw.get('version') != contract['version'] or
            raw.get('learning_version') != learning_version or raw.get('observation_version') != contract['observation_version'] or
            raw.get('case') != job['case'] or receipt.get('case') != job['case'] or
            raw.get('seed') != job['seed'] or receipt.get('seed') != job['seed']):
        raise ValueError('Execution/interface/case/seed binding differs')
    if (receipt.get('status') != 'finished' or receipt.get('valid') is not True or
            receipt.get('stopped') is not True or receipt.get('nonfinite_fields')):
        raise ValueError('Completed valid stopped archive required')
    for key in COMMON:
        if canonical(receipt[key]) != canonical(reg['common'][key]):
            raise ValueError('Common physical/runtime domain changed: ' + key)
    evidence = raw['evidence']; facts = evidence['guard_facts']
    if (not facts['simulation_valid'] or facts['invalid_reasons'] or facts['motion_reasons'] or
            evidence['interface_fault'] is not None or evidence['diagnostic_errors'] or
            canonical(facts) != canonical(receipt['guard_facts'])):
        raise ValueError('Invalid, unqualified-motion or incomplete evidence')
    rows, trace = raw['transitions'], raw['trace']; count = len(rows)
    if (not 0 < count <= MAX_CYCLES or len(trace) != count+1 or len(raw['cycle_peaks']) != count or
            receipt['control_cycles'] != count or receipt['physical_substeps'] != 10*count or
            facts['checked_substeps'] != 10*count or raw['cost']['physical_substeps'] != 10*count or
            raw['cost']['initialization_attempts'] != 1 or raw['cost']['initializations_completed'] != 1 or
            receipt['reset_attempted'] != 1):
        raise ValueError('Control-cycle/substep/initialization accounting differs')
    dynamic = receipt['dynamic_config']; period, dt = dynamic['control_period'], dynamic['timestep']
    cfg = receipt['controller_config']
    if time_budget_group is not None:
        controller_events = evidence.get('controller_events')
        if (cfg != contract['controller_config'] or raw.get('time_budget_protocol') != base_time_contract or
                receipt['final_reason'] in ('SEARCH_BUDGET_EXHAUSTED', 'LOADED_ROTATION_RISK') or
                not isinstance(controller_events, list) or
                any(e.get('reason') in ('SEARCH_BUDGET_EXHAUSTED', 'LOADED_ROTATION_RISK')
                    for e in controller_events)):
            raise ValueError('Time-only retry/warning protocol differs')
    if (period != .002 or dt != .0002 or cfg['total_action_time_s'] != 30. or cfg['search_time_s'] != 18.):
        raise ValueError('Frozen native/control/30-second task clock differs')
    recovery_proof = None
    if force_recovery_group is not None:
        from tools.validation.force_recovery_audit import verify_recovery_evidence
        record = raw['force_recovery']
        if record != evidence.get('force_recovery') or record != receipt.get('force_recovery'):
            raise ValueError('Recovery record binding differs')
        cumulative = raw['cumulative_peaks']
        if cumulative != evidence.get('cumulative_peaks') or cumulative != receipt.get('cumulative_peaks'):
            raise ValueError('Cumulative peak binding differs')
        for key in ('force_N','torque_G_Nm','penetration_m'):
            if abs(cumulative[key]-max(p[key] for p in raw['cycle_peaks']))>1e-9:
                raise ValueError('Cumulative/native cycle peaks differ')
        for key,limit,reason in (('torque_G_Nm',.1,'TORQUE_LIMIT'),('penetration_m',.00003,'PENETRATION_LIMIT')):
            if (cumulative[key]>limit)!=(reason in facts['contact_reasons']):
                raise ValueError('Cumulative non-force protection fact differs')
        recovery_proof = verify_recovery_evidence(record,cycle_peaks=raw['cycle_peaks'],facts=facts,
            end_time_s=trace[-1]['time_s'],timestep=dt,control_period=period,
            wait_stable_s=cfg['wait_stable_s'],recovery_time_limit_s=dynamic.get('recovery_time_limit_s',1.))
        for event in record['events']:
            boundaries=[('FORCE_LIMIT',event['trigger_time_s'])]
            if event['status']=='COMPLETED':
                boundaries.extend([('RECOVERY_ACCEPTED',event['retract_start_time_s']),
                    ('RECOVERY_DISTANCE_REACHED',event['retracted_time_s']),
                    ('B2_RECOVERY_RESUMED',event['resume_time_s'])])
            for reason,t in boundaries:
                if not any(reason in e['reason'].split('+') and abs(e['time_s']-t)<1e-9
                           for e in evidence['environment_events']):
                    raise ValueError('Recovery ledger lacks original physical event')
        by_step={round(s['time_s']/dt):s for s in record['samples']}
        for state in trace:
            sample=by_step.get(round(state['time_s']/dt))
            if sample is not None and (abs(sample['position_z_m']-state['position_m'][2])>1e-9 or
                    abs(sample['force_N']-np.linalg.norm(state['contact_wrench_M'][:3]))>1e-9 or
                    abs(sample['linear_m_s']-np.linalg.norm(state['velocity_world'][:3]))>1e-9 or
                    abs(sample['angular_rad_s']-np.linalg.norm(state['velocity_world'][3:]))>1e-9 or
                    not np.allclose(sample['command_world'],state['limited_command_world'],rtol=0,atol=1e-12)):
                raise ValueError('Native recovery samples disagree with control trace')
    spans = field_slices(); schema = raw['observation_schema']
    if len(schema) != len(spans):
        raise ValueError('140-dimensional observation schema differs')
    for field, (name, span) in zip(schema, spans.items()):
        if (field['name'] != name or field['start'] != span.start or field['width'] != span.stop-span.start or
                len(field['scale']) != field['width'] or min(field['scale']) <= 0):
            raise ValueError('Observation schema/order differs')
        if name in ('total_budget_remaining_s', 'phase_elapsed_s') and field['scale'] != [30.]:
            raise ValueError('Observation time scale differs from 30 seconds')
        if time_budget_group is not None and name in ('searches_remaining', 'recoveries_remaining'):
            if field['scale'] != [1.] or field.get('source') != 'time_only_retry_permission':
                raise ValueError('Time-only retry observation schema differs')
        if force_recovery_group is not None and name=='latched_guards' and field.get('source')!='active_guard_blockers_after_verified_force_recovery':
            raise ValueError('Force recovery permission semantics differ')
    if schema[0]['scale'] != ([5.]*3+[.1]*3)*4:
        raise ValueError('N2 force/torque history scale differs')
    auditor = _auditor(); auditor._finite(raw)
    legacy = {key: span for key, span in spans.items() if span.stop <= 137}
    for cycle, state in enumerate(trace):
        if abs(state['time_s']-cycle*period) > 1e-8:
            raise ValueError('Trace clock gap')
        for key, width in (('position_m', 3), ('quaternion_wxyz', 4), ('velocity_world', 6),
                ('contact_wrench_M', 6), ('contact_wrench_G', 6), ('limited_command_world', 6), ('reference_qpos', 7)):
            auditor._vector(state[key], width)
        if abs(np.linalg.norm(state['quaternion_wxyz'])-1.) > 1e-6:
            raise ValueError('Quaternion normalization differs')
    _verify_initial_pose(trace[0], job['case'])
    prepared = FiveAxisReplay(capacity=MAX_CYCLES)._prepare(rows)
    for cycle, row in enumerate(rows):
        obs = np.asarray(row['observation']); log = row['action_log']; inputs = log['composition_inputs']
        active = permission(obs); phase = POLICY_PHASES[int(obs[spans['policy_phase']].argmax())]
        if abs(row['dt']-period) > 1e-10 or log.get('profile') != 'G1' or log.get('contract_version') != contract['version']:
            raise ValueError('Action clock/profile/repaired contract differs')
        auditor._observation(row['observation'][:137], trace, cycle, legacy)
        auditor._observation(row['next_observation'][:137], trace, cycle+1, legacy)
        for observed, index in ((row['observation'], cycle), (row['next_observation'], cycle+1)):
            if recovery_proof is not None:
                t=trace[index]['time_s']
                pending=any(e['trigger_time_s']-1e-9 <= t and
                    (e['status']!='COMPLETED' or t<e['resume_time_s']-1e-9)
                    for e in raw['force_recovery']['events'])
                if pending and permission(observed):
                    raise ValueError('Policy enabled during unresolved force recovery')
            remaining = max(0., 30.-trace[index]['time_s'])/30.
            if abs(observed[spans['total_budget_remaining_s'].start]-remaining) > 1e-6:
                raise ValueError('Remaining-time observation differs from task clock')
            if time_budget_group is not None:
                allowed = float(trace[index]['time_s'] < 30. - 1e-10)
                if any(abs(observed[spans[name].start]-allowed) > 1e-6
                       for name in ('searches_remaining', 'recoveries_remaining')):
                    raise ValueError('Time-only retry observation differs from task clock')
        scale = np.array([.001]*3+[.03]*3)
        failed = log.get('reference_failure') == 'RESIDUAL_REFERENCE_INFEASIBLE'
        if not failed and (inputs['phase'] != phase or log['enabled'] != active or
                not np.allclose(inputs['base_command'], obs[spans['base_command']]*scale, rtol=0, atol=2e-9)):
            raise ValueError('Command phase/base/permission binding differs')
        if failed and (inputs['phase'] != 'FAILED' or log['enabled'] or any(inputs['base_command'])):
            raise ValueError('Malformed reference-infeasible failure')
        if (not np.allclose(inputs['previous_limited_command'], obs[spans['previous_limited_command']]*scale, rtol=0, atol=2e-9) or
                abs(inputs['dt']-period) > 1e-10):
            raise ValueError('Previous command/clock binding differs')
        if time_budget_group is None:
            _, expected = compose_command(inputs['base_command'], log['raw_action'], profile='G1',
                phase=inputs['phase'], enabled=log['enabled'], previous_limited=inputs['previous_limited_command'],
                dt=inputs['dt'], reference_xy=log.get('reference_xy_m'), radius=log.get('reference_radius_limit_m', .0004))
        else:
            from tools.learning.global_residual_action import recompose_logged_command
            _, expected = recompose_logged_command(log, search_xy_limit_m_s=contract['search_xy_limit_m_s'])
        verify_composition_log(log, expected, obs, cfg)
        verify_reference_prediction(log, trace[cycle], cfg, dynamic['reference_lead_m'])
        if inputs['phase'] == 'SEARCH' and log['enabled']:
            center = np.asarray(trace[0]['position_m'][:2]) + obs[spans['search_origin_m']][:2]*.004
            if not np.allclose(log['reference_center_xy_m'], center, rtol=0, atol=2e-9):
                raise ValueError('Current search center differs from observation origin')
        if (row['action'] != expected['experience_action'] or
                log['actual_end_limited_command'] != trace[cycle+1]['limited_command_world']):
            raise ValueError('Saved experience action/physical endpoint differs')
        physical = int(obs[spans['physical_phase']].argmax())
        next_physical = int(np.asarray(row['next_observation'])[spans['physical_phase']].argmax())
        if physical != 2 and physical == next_physical and not np.allclose(
                log['actual_end_limited_command'], expected['predicted_limited_command'], rtol=0, atol=1e-12):
            raise ValueError('Ordinary drive differs from reconstructed limit')
    verify_rewards(raw, final_reason=receipt['final_reason'])
    from tools.validation.native_stop_clock import verify_stopping_interval
    stop = verify_stopping_interval(dict(trace=trace, events=evidence['environment_events'], stop_samples=evidence['stop_samples']),
        dict(receipt, audit_end_time_s=trace[-1]['time_s'], stop_time_s=evidence['stop_time_s']), dt, period,
        recovery_proof=recovery_proof)
    verify_task_clock(stop_time=evidence['stop_time_s'], task_end_time=evidence['task_end_time_s'],
        audit_end_time=trace[-1]['time_s'], settle_time=cfg['settle_time_s'])
    outcome = raw['outcome']
    unresolved_contact = bool(facts['contact_reasons'])
    if recovery_proof is not None and recovery_proof['all_force_events_recovered']:
        unresolved_contact=False
    classified = 'CONTACT_GUARD' if unresolved_contact else (
        'FULL_SUCCESS' if receipt['final_reason'] == 'GEOMETRIC_SUCCESS' else 'TASK_FAILURE')
    if (outcome['simulation_valid'] is not True or outcome['physical_stopped'] is not True or
            outcome['task_outcome'] != classified or receipt['outcome'] != classified):
        raise ValueError('Task outcome differs from physical facts')
    if classified == 'FULL_SUCCESS':
        if recovery_proof is not None and not recovery_proof['all_force_events_recovered']:
            raise ValueError('Success requires all force events fully recovered')
        if recovery_proof is not None and (raw['cumulative_peaks']['torque_G_Nm']>=receipt['finish_criteria']['torque_Nm'] or
                raw['cumulative_peaks']['penetration_m']>=receipt['finish_criteria']['penetration_m']):
            raise ValueError('Historical non-force protection forbids success')
        verify_success_hold(trace, task_end_time_s=evidence['task_end_time_s'], period=period,
                            criteria=receipt['finish_criteria'])
    reference = verify_reference_checks(raw, receipt)
    source = verify_action_source(raw, receipt, job, source_trainer=source_trainer)
    proof = dict(verified=True, archive_sha256=receipt['archive_sha256'], rows=count,
        active_rows=int(prepared['action_active'].sum()), source_replay_verified=True,
        reference_verified=True, native_reference_verified=True, reference_checks=reference,
        action_source=source, stop=stop, task_outcome=classified,
        source_checkpoint_sha256=receipt.get('source_checkpoint_sha256'),
        execution_contract_sha256=hashlib.sha256(canonical(contract).encode('utf-8')).hexdigest(),
        audit_physical_initializations=0, audit_optimizer_updates=0)
    if time_budget_group is not None:
        proof.update(time_only_retry_features_verified=True, search_speed_um_s=time_budget_group)
    if recovery_proof is not None:
        for key in ('had_force_recovery','force_recovery_count','completed_force_recovery_count','peak_force_N'):
            if outcome.get(key)!=recovery_proof[key]:raise ValueError('Outcome recovery history differs')
        if outcome.get('force_recovery_fatal_reasons')!=raw['force_recovery']['fatal_reasons']:
            raise ValueError('Outcome fatal recovery history differs')
        proof['force_recovery']=recovery_proof
    return raw, receipt, proof
