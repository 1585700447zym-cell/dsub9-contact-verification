"""Hand-derived permission/action cases; no model or physical reset."""
from pathlib import Path
from types import SimpleNamespace
import sys,math
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.learning.v4_pilot_contract import field_slices,permission as legacy_permission
import deployment_profile as p

def test_deployment_module_does_not_break_stdlib_profiling():
    # Our module name must not shadow stdlib profile when Torch loads cProfile.
    import cProfile,importlib
    importlib.reload(cProfile)
    ns={};cProfile.runctx('value=2+3',ns,ns)
    assert ns['value']==5

def observation(profile='G50',fz=-.006,phase=0,active=True):
    o=np.zeros(137,dtype=np.float32);s=field_slices()
    for name,index in [('policy_phase',phase),('physical_phase',0),('recovery_phase',0),('decision',0)]:o[s[name].start+index]=1
    o[s['simulation_valid']]=1;o[s['action_active']]=active;o[s['wrench_history_M'].start+2]=np.float32(fz/.025)
    return o

@pytest.mark.parametrize('phase,base,fz,want',[
    ('INSERT',True,-.005,True),('INSERT',True,-.004,False),('INSERT',True,.01,False),
    ('SEARCH',True,0.,True),('UNLOAD',True,-.02,False),('INSERT',False,-.01,False)])
def test_gate_uses_sign_existing_threshold_and_common_permission(phase,base,fz,want):
    assert p.enabled('G50',phase,base,fz)==want

def test_float32_threshold_neighbour_agrees_with_observation_contract():
    # This sub-double perturbation quantizes to the threshold in float32.
    fz=-.004999999999999
    assert p.enabled('G50','INSERT',True,fz) is True
    assert p.permissions(observation(fz=fz),'G50') is True

def test_session_gate_uses_the_same_visible_feedback_without_reset():
    session=object.__new__(p.ProfileSession);session.profile='G50';session.mode='F50'
    session._cache=SimpleNamespace(state={'contact_wrench_M':[0.,0.,-.004999999999999,0.,0.,0.]})
    assert session.stage_permission('INSERT',True) is True
    session._cache.state['contact_wrench_M'][2]=0.
    assert session.stage_permission('INSERT',True) is False

def test_low_load_gate_is_valid_as_g_and_rejected_as_legacy_f():
    o=observation(fz=0,active=False)
    assert p.permissions(o,'G50') is False
    with pytest.raises(ValueError):legacy_permission(o,'F50')

@pytest.mark.parametrize('name', ['simulation_valid','pending','latched_guards','invalid_latched'])
def test_contact_does_not_bypass_common_stops(name):
    o=observation(active=False);s=field_slices();o[s[name]]=0 if name=='simulation_valid' else 1
    if name=='pending':o[s['decision']]=0;o[s['decision'].start+1]=1
    assert p.permissions(o,'G50') is False

def test_false_mask_above_contact_gate_is_rejected():
    with pytest.raises(ValueError):p.permissions(observation(active=False),'G50')

def test_f_preserves_low_load_insert_permission():
    assert p.permissions(observation(fz=0),'F50') is True
    assert p.permissions(observation(fz=0),'F12.5') is True

def test_small_scale_preserves_actor_output_and_maps_all_four_axes():
    action=np.array([1.,-1.,.5,-.5]);original=action.copy()
    assert np.array_equal(p.deployment_action(action,'F12.5'),[.25,-.25,.125,-.125])
    assert np.array_equal(action,original)
    assert np.array_equal(p.deployment_action(action,'B2'),[0.,0.,0.,0.])

@pytest.mark.parametrize('action', [[float('nan'),0,0,0],[1.01,0,0,0],[0,0,0]])
def test_invalid_actor_request_cannot_be_scaled_into_validity(action):
    with pytest.raises(ValueError):p.deployment_action(action,'F12.5')

def episode(profile='G50'):
    actor=[1.,-1.,.5,-.5];command=[.25,-.25,.125,-.125] if profile=='F12.5' else actor
    ob=observation();nxt=observation(phase=4,active=False)
    log=dict(actor_action=actor,raw_action=command,experience_action=command,enabled=True)
    t=dict(observation=ob.tolist(),next_observation=nxt.tolist(),action=command,action_active=True,next_action_active=False,
           dt=.002,discount=math.exp(-.002/10),terminated=True,truncated=False,action_log=log)
    return dict(profile=profile,mode=profile,scope='contact_gate_deployment_probe',transitions=[t],actions=[log],policy_calls=1,policy_call_attempts=1)

def test_new_rows_audit_keeps_g_mask_and_original_actor_output():
    assert p.audit_rows(episode())['rows']==1
    assert p.audit_rows(episode('F12.5'))['network_policy_calls']==1

@pytest.mark.parametrize('bad', ['actor','mask','discount','terminal','calls'])
def test_row_errors_are_rejected_without_retagging(bad):
    raw=episode();t=raw['transitions'][0]
    if bad=='actor':t['action_log']['actor_action']=[0.]*4
    if bad=='mask':t['action_active']=False
    if bad=='discount':t['discount']=1.
    if bad=='terminal':t['terminated']=False
    if bad=='calls':raw['policy_calls']=0
    with pytest.raises(ValueError):p.audit_rows(raw)

def test_previous_next_mask_cannot_be_discontinuous():
    raw=episode();t=raw['transitions'][0];t['terminated']=False
    from copy import deepcopy
    raw['transitions'].append(deepcopy(t));raw['actions'].append(deepcopy(raw['actions'][0]));raw['transitions'][1]['terminated']=True
    raw['policy_calls']=raw['policy_call_attempts']=2
    with pytest.raises(ValueError):p.audit_rows(raw)
