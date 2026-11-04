"""Independent fabricated native samples; no physics or policy inference."""
from copy import deepcopy
import importlib.util
import pytest


@pytest.fixture(scope='module',autouse=True)
def runtime_imports_only():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()


def api():
    name = 'tools.validation.force_recovery_audit'
    assert importlib.util.find_spec(name), 'Independent recovery auditor required'
    return __import__(name, fromlist=['verify_recovery_evidence'])


def evidence():
    samples = []
    for k in range(10, 3531):
        t = round(k * .0002, 10)
        moving = .104 < t < .604
        samples.append(dict(time_s=t, event_id=1,
            phase='RETRACT' if moving else 'STOPPING',
            force_N=5.6 if k == 10 else .1, torque_G_Nm=0., penetration_m=0.,
            linear_m_s=.0005 if moving else 0., angular_rad_s=0.,
            command_world=[0.,0.,-.0005 if moving else 0.,0.,0.,0.],
            position_z_m=-.004-min(.00025,max(0.,(t-.104)*.0005))))
    event = dict(id=1, trigger_time_s=.002, peak_force_N=5.6,
        last_over_force_time_s=.002, continuous_over_force_s=0.,
        unloaded_time_s=.104, retract_start_time_s=.104, retract_start_z_m=-.004,
        retracted_time_s=.604, actual_retraction_m=.00025,
        resume_time_s=.706, end_time_s=.706, status='COMPLETED', eligible=True)
    return dict(events=[event], samples=samples, fatal_reasons=[], had_force_recovery=True,
        force_recovery_count=1, completed_force_recovery_count=1, peak_force_N=5.6)


def verify(record):
    peaks = [dict(force_N=5.6)] + [dict(force_N=.1) for _ in range(352)]
    facts = dict(simulation_valid=True, invalid_reasons=[], motion_reasons=[], contact_reasons=['FORCE_LIMIT'])
    return api().verify_recovery_evidence(record, cycle_peaks=peaks, facts=facts, end_time_s=.706)


def test_completed_recovery_requires_native_unload_actual_retraction_and_stable_tail():
    assert verify(evidence())['all_force_events_recovered']


@pytest.mark.parametrize('kind', ['missing_samples','peak','distance','unload','settle','second_force', 'torque','late_resume','count','phase','eligible','command','stable_penetration'])
def test_forged_recovery_is_rejected(kind):
    record = deepcopy(evidence())
    if kind == 'missing_samples': del record['samples'][50]
    elif kind == 'peak': record['events'][0]['peak_force_N'] = 5.1
    elif kind == 'distance': record['samples'][-1]['position_z_m'] += .0001
    elif kind == 'unload': record['samples'][300]['force_N'] = 1.
    elif kind == 'settle': record['samples'][-100]['linear_m_s'] = .0001
    elif kind == 'second_force': record['samples'][400]['force_N'] = 5.5
    elif kind == 'torque': record['samples'][400]['torque_G_Nm'] = .11
    elif kind == 'late_resume': record['events'][0]['resume_time_s'] = 30.002
    elif kind == 'count': record['completed_force_recovery_count'] = 0
    elif kind == 'phase': record['samples'][400]['phase']='RUNNING'
    elif kind == 'eligible': record['events'][0]['eligible']=False
    elif kind == 'command': record['samples'][400]['command_world']=[.001]*6
    elif kind == 'stable_penetration': record['samples'][-100]['penetration_m']=.00003
    with pytest.raises(ValueError): verify(record)


def test_force_history_cannot_be_excused_without_an_event():
    record = evidence(); record.update(events=[], samples=[], force_recovery_count=0, completed_force_recovery_count=0)
    with pytest.raises(ValueError): verify(record)


def test_recurrence_after_completed_recovery_cannot_hide_in_a_low_cycle_peak():
    record=evidence()
    for k in range(3531,3541):
        s=deepcopy(record['samples'][-1]);s.update(time_s=k*.0002,force_N=5.2,phase='RUNNING')
        record['samples'].append(s)
    with pytest.raises(ValueError,match='cycle peak'):
        api().verify_recovery_evidence(record,cycle_peaks=[dict(force_N=5.6)]+[dict(force_N=.1) for _ in range(353)],
            facts=dict(simulation_valid=True,invalid_reasons=[],motion_reasons=[],contact_reasons=['FORCE_LIMIT']),end_time_s=.708)


@pytest.mark.parametrize('bounds',[dict(wait_stable_s=.05),dict(recovery_time_limit_s=.4)])
def test_completed_recovery_cannot_exceed_stage_timeouts(bounds):
    with pytest.raises(ValueError,match='timeout'):
        api().verify_recovery_evidence(evidence(),cycle_peaks=[dict(force_N=5.6)]+[dict(force_N=.1) for _ in range(352)],
            facts=dict(simulation_valid=True,invalid_reasons=[],motion_reasons=[],contact_reasons=['FORCE_LIMIT']),end_time_s=.706,**bounds)


def test_delayed_recovery_failure_keeps_physical_clock_and_adds_full_final_audit():
    from tools.validation.native_stop_clock import verify_stopping_interval
    from tools.validation.native313_matrix_audit import actual_stop_start
    marker=dict(time_s=.5,phase='STOPPING',reason='RECOVERY_FINAL_AUDIT_START',
                force_recovery_id=1,physical_stop_preserved=True,decision_reason='TIME_LIMIT',
                recovery_kind='force',physical_stop_time_s=.002,recovery_count=0)
    raw=dict(events=[dict(time_s=.002,phase='STOPPING',reason='FORCE_LIMIT'),marker],
             trace=[dict(time_s=2.5,phase='STOPPING',velocity_world=[0.]*6)],
             stop_samples=[dict(time_s=round(k*.0002,10),linear_m_s=0.,angular_rad_s=0.) for k in range(11,12501)])
    receipt=dict(stop_time_s=.5,audit_end_time_s=2.5)
    assert actual_stop_start(raw['events'],.5)==.5
    with pytest.raises(ValueError): verify_stopping_interval(raw,receipt,.0002,.002)
    proof=verify_stopping_interval(raw,receipt,.0002,.002,
        recovery_proof=dict(verified=True,event_ids=[1],recovery_events=[
            dict(id=1,status='ABORTED',end_time_s=.5,status_reason='TIME_LIMIT')]))
    assert proof['physical_start_time_s']==.002
    assert proof['final_audit_start_time_s']==.5
    assert proof['final_audit_native_samples']==10000


def test_current_protocols_bind_the_active_geometry_referee():
    from tools.model.layered_task import TASK_ID
    from tools.learning.time_budget_trial import protocol_config
    assert protocol_config()['task_referee']==TASK_ID


@pytest.mark.parametrize('speed',[450,900])
def test_new_protocol_uses_complete_archive_audit(tmp_path,speed):
    from tests.test_time_budget_archive import converted_archive
    from tools.learning.force_recovery_trial import protocol_config,audit_archive
    raw,receipt,reg,job,publish=converted_archive(tmp_path,speed)
    contract=protocol_config(speed)
    for target in (raw,receipt,reg):target['execution_contract']=deepcopy(contract)
    raw.update(version=contract['version'],observation_version=contract['observation_version'],
               force_recovery_protocol=deepcopy(contract))
    for row in raw['transitions']:row['action_log']['contract_version']=contract['version']
    next(f for f in raw['observation_schema'] if f['name']=='latched_guards')['source']='active_guard_blockers_after_verified_force_recovery'
    record=dict(events=[],samples=[],fatal_reasons=[],had_force_recovery=False,
        force_recovery_count=0,completed_force_recovery_count=0,
        peak_force_N=max(p['force_N'] for p in raw['cycle_peaks']))
    for p in raw['cycle_peaks']:p.setdefault('penetration_m',0.)
    cumulative={key:max(p[key] for p in raw['cycle_peaks']) for key in ('force_N','torque_G_Nm','penetration_m')}
    for target in (raw,receipt,raw['evidence']):
        target.update(force_recovery=deepcopy(record),cumulative_peaks=deepcopy(cumulative))
    raw['outcome'].update({k:record[k] for k in ('had_force_recovery','force_recovery_count','completed_force_recovery_count','peak_force_N')})
    raw['outcome']['force_recovery_fatal_reasons']=[]
    publish()
    proof=audit_archive(tmp_path,reg,job,search_speed_um_s=speed)[2]
    assert proof['verified'] and proof['force_recovery']['verified']
    assert proof['stop']['final_native_samples']==10000
