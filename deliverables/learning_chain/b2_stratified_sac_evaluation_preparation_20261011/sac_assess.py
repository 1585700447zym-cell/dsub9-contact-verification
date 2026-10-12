"""Saved episode identity/command audit and shared development metrics."""
from sac_scope import c,canonical,actor_spec,case_kwargs,finite_vector

def audit_archive(raw,config,unit):
    from sac_rollout import audit_command
    spec=actor_spec(unit['role']);point=unit['case'];cycles=raw['control_cycles']
    if (raw['scope']!='stratified_frozen_SAC_development' or raw['role']!=unit['role'] or raw['case_id']!=point['id'] or
        raw['case']!=point or raw['case_index']!=config['cases'].index(point) or raw['simulation_case']!=case_kwargs(point) or
        raw['mode']!='F50' or raw['seed']!=c.SEED or raw['stage']!=spec['stage'] or
        raw['comparison_key']!=config['common_key'] or raw['shared_common_key']!=config['parent_common_key'] or
        raw['policy_sha256']!=spec['actor_sha256'] or raw['policy_sha256_after']!=spec['actor_sha256'] or
        raw['optimizer_steps_start']!=spec['updates'] or raw['optimizer_steps']!=spec['updates'] or
        raw['observation_schema']!=config['schema'] or raw['fault'] is not None or raw['reference_problems'] or raw['actual_reference_failed'] or
        raw['source_session_outcome']['model_scope_qualified'] is not False or raw['source_session_outcome']['training_admitted'] is not False or
        raw['initial_audit'].get('passed') is not True):raise ValueError('Frozen actor/archive/common/scope identity failed')
    c.check_pose(point,raw['trace'][0])
    if type(cycles) is not int or not 0<cycles<=14500 or raw['physical_substeps']!=10*cycles or not (
        len(raw['trace'])==cycles+1 and len(raw['actions'])==len(raw['transitions'])==cycles):raise ValueError('Incomplete cycle/native/transcript archive')
    calls=nonzero=0;maxerror=0.
    for log,t in zip(raw['actions'],raw['transitions']):
        active=t['action_active'];requested=finite_vector(log['raw_action'],4)
        if type(active) is not bool or max(abs(v) for v in requested)>1 or t['action']!=log['experience_action']:
            raise ValueError('Normalized action/permission archive differs')
        error,n=audit_command(log,requested,active);calls+=int(active);nonzero+=n;maxerror=max(maxerror,error)
    if raw['policy_calls']!=calls or raw['policy_call_attempts']!=calls or raw['nonzero_applied_command_cycles']!=nonzero or raw['max_command_error']!=maxerror:
        raise ValueError('Call or command evidence counts differ')
    # Existing physical stop validators and original outcome classifier, no replay publication.
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    from tools.validation.verify_admitted_collection import validate_outcome
    stopped=bool(actual_stop_pass(raw['stop_samples'],raw['events'],raw['stop_time'],raw['audit_end_time_s'],.0002) and
        physical_tail_pass(raw['stop_samples'],raw['audit_end_time_s'],.0002))
    out=validate_outcome(raw,stopped=stopped)
    return bool(out['simulation_valid'] is True and out['physical_stopped'] is True and
        out['guard_violations']==dict(contact=False,motion=False) and out['task_outcome'] in ('FULL_SUCCESS','TASK_FAILURE'))
