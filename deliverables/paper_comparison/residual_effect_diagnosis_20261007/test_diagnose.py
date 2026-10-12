"""Hand-derived data checks; no mocked policy, learning or physics."""
from copy import deepcopy
import pytest
import diagnose as d

def fixture():
    phases=('INSERT','SEARCH','INSERT'); enabled=(False,True,True)
    times=(0.,.1,.3,.4); positions=(0.,1e-6,3e-6,4e-6)
    actions=[];transitions=[]
    for i in range(3):
        ob=[0.]*137;ob[53+('INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED').index(phases[i])]=1.
        request=[5e-5,0,0,5e-4,0,0] if enabled[i] else [0.]*6
        delta=[2.5e-5,0,0,2.5e-4,0,0] if i==1 else request
        log=dict(enabled=enabled[i],raw_action=[1.,0,1.,0] if enabled[i] else [0.]*4,
                 requested_residual=request,applied_residual=request,effective_command_delta=delta,
                 predicted_limited_command=delta,actual_end_limited_command=delta,reference_filter_fraction=1.)
        log['unfiltered_stage_limited_total']=request
        actions.append(log);transitions.append(dict(observation=ob,dt=times[i+1]-times[i],action_active=enabled[i],cycle_force_N=(.02,.01,.005)[i]))
    return dict(case_id='a',mode='F50',control_cycles=3,actions=actions,transitions=transitions,
                trace=[dict(time_s=t,position_m=[x,0,-.004],quaternion_wxyz=[1.,0,0,0],policy_phase='INSERT',contact_count=0) for t,x in zip(times,positions)],
                observation_schema=[dict(name='policy_phase',start=53,width=5)],task_end_time_s=.4)

def test_stage_uses_pre_action_observation_at_transition():
    # Wrong break: assigning the SEARCH cycle from its preceding trace INSERT.
    r=d.diagnose_episode(fixture())
    assert r['stages']['SEARCH']['cycles']==1
    assert r['stages']['SEARCH']['duration_s']==pytest.approx(.2)
    assert r['stages']['INSERT']['duration_s']==pytest.approx(.2)

def test_clipped_requests_are_not_reported_as_delivered_commands():
    # Wrong break: summing applied request instead of effective limiter delta.
    r=d.diagnose_episode(fixture())['stages']['SEARCH']
    assert r['requested_xy_integral_um']==pytest.approx(10.)
    assert r['effective_xy_integral_um']==pytest.approx(5.)
    assert r['clipped_cycles']==1 and r['enabled_cycles']==1

def test_rotation_is_not_combined_with_translation():
    r=d.diagnose_episode(fixture())['stages']['SEARCH']
    assert r['effective_rotation_integral_mrad']==pytest.approx(.05)
    assert r['actual_rotation_path_mrad']==0

def test_actual_motion_is_not_replaced_with_command_delta():
    r=d.diagnose_episode(fixture())['stages']['SEARCH']
    assert r['actual_xy_path_um']==pytest.approx(2.)
    assert r['actual_xy_path_um']!=r['effective_xy_integral_um']

def test_persistent_residual_is_not_called_total_command_clipping():
    # A 40um/s target is reached. The zero alternative can only slew down to
    # 30um/s, so the 10um/s delta is not evidence that 75% was swallowed.
    raw=fixture();log=raw['actions'][2]
    log.update(applied_residual=[4e-5,0,0,0,0,0],effective_command_delta=[1e-5,0,0,0,0,0],
               predicted_limited_command=[4e-5,0,0,0,0,0],actual_end_limited_command=[4e-5,0,0,0,0,0],
               unfiltered_stage_limited_total=[4e-5,0,0,0,0,0])
    r=d.diagnose_episode(raw)['stages']['INSERT']
    assert r['clipped_cycles']==1
    assert r['total_target_limited_cycles']==0

def test_true_drive_target_limit_is_counted():
    r=d.diagnose_episode(fixture())['stages']['SEARCH']
    assert r['total_target_limited_cycles']==1

def test_cycle_peak_precedes_first_enabled_cycle():
    r=d.diagnose_episode(fixture())
    assert r['first_enabled_time_s']==.1
    assert r['peak_cycle_index']==0 and r['peak_before_first_enabled'] is True
    assert r['pre_enabled_peak_force_N']==.02

def test_peak_in_enabled_cycle_has_no_proven_prior_order():
    raw=fixture();raw['transitions'][1]['cycle_force_N']=.03
    r=d.diagnose_episode(raw)
    assert r['peak_before_first_enabled'] is False

def test_disabled_recovery_command_difference_is_preserved_separately():
    raw=fixture();raw['actions'][0]['actual_end_limited_command']=[0,0,-1e-5,0,0,0]
    r=d.diagnose_episode(raw)
    assert r['predicted_end_command_mismatch_cycles']==1
    assert r['active_predicted_end_command_mismatch_cycles']==0

def test_enabled_command_difference_is_not_hidden_as_recovery():
    raw=fixture();raw['actions'][2]['actual_end_limited_command']=[0,0,-1e-5,0,0,0]
    r=d.diagnose_episode(raw)
    assert r['active_predicted_end_command_mismatch_cycles']==1

def test_no_enabled_action_has_no_invented_timestamp():
    raw=fixture()
    for a,t in zip(raw['actions'],raw['transitions']):
        a.update(enabled=False,raw_action=[0.]*4,applied_residual=[0.]*6,effective_command_delta=[0.]*6)
        t['action_active']=False
    r=d.diagnose_episode(raw)
    assert r['first_enabled_time_s'] is None
    assert r['peak_before_first_enabled'] is None

@pytest.mark.parametrize('error', ['nan','dt','length','phase','permission'])
def test_malformed_data_cannot_become_a_successful_diagnosis(error):
    raw=fixture()
    if error=='nan':raw['actions'][0]['effective_command_delta'][0]=float('nan')
    if error=='dt':raw['transitions'][0]['dt']=0
    if error=='length':raw['trace'].pop()
    if error=='phase':raw['transitions'][0]['observation'][53:58]=[0.]*5
    if error=='permission':raw['transitions'][0]['action_active']=True
    with pytest.raises(ValueError):d.diagnose_episode(raw)

def test_prefix_stops_before_first_enabled_action_effect():
    a=fixture();b=deepcopy(a);b['trace'][2]['position_m'][0]=1e-4
    r=d.pair_prefix(a,b)
    assert r['prefix_rows']==2 and r['trace_prefix_exact'] is True
    b['trace'][1]['position_m'][0]=1e-4
    assert d.pair_prefix(a,b)['trace_prefix_exact'] is False

def test_short_baseline_does_not_prove_whole_prefix():
    a=fixture();b=deepcopy(a);a['trace']=a['trace'][:1]
    assert d.pair_prefix(a,b)['trace_prefix_exact'] is False

def test_time_contribution_keeps_negative_contributors():
    b=[dict(case_id='y',outcome='FULL_SUCCESS',task_end_time_s=20),dict(case_id='x',outcome='FULL_SUCCESS',task_end_time_s=10)]
    s=[dict(case_id='y',outcome='FULL_SUCCESS',task_end_time_s=10),dict(case_id='x',outcome='FULL_SUCCESS',task_end_time_s=11)]
    r=d.time_contributions(b,s)
    assert r['savings_s']=={'y':10.,'x':-1.}
    assert r['total_saved_s']==9.
    assert r['fractions']['y']==pytest.approx(10/9)

def test_failed_task_uses_registered_penalty():
    r=d.time_contributions([dict(case_id='a',outcome='TASK_FAILURE',task_end_time_s=8)],
                          [dict(case_id='a',outcome='FULL_SUCCESS',task_end_time_s=10)])
    assert r['savings_s']['a']==16.

def test_missing_matched_case_rejected():
    with pytest.raises(ValueError):d.time_contributions([dict(case_id='a',outcome='FULL_SUCCESS',task_end_time_s=10)],[])
