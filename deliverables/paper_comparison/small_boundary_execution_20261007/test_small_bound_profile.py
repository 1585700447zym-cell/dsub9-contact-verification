"""Pure action/protocol counterexamples; no model/environment construction."""
from copy import deepcopy
import numpy as np
import pytest
from small_bound_profile import (outer_contract, profile_digest, validate_outer_contract,
    compose_small_bound_command, audit_action_log, audit_small_bound_episode)


def context(phase='INSERT', enabled=True):
    return dict(base=[0.]*6, phase=phase, enabled=enabled, previous_limited=[0.]*6,
                dt=.002, reference_xy=None, radius=.00012, next_theta=None,
                search_config=None)


@pytest.mark.parametrize('axis', range(4))
@pytest.mark.parametrize('sign', [-1., 1.])
def test_axis_units_and_unscaled_learning_request(axis, sign):
    a=np.zeros(4);a[axis]=sign
    command, log=compose_small_bound_command(a, context(), outer_contract())
    assert log['raw_action']==a.tolist()==log['experience_action']
    assert log['compositor_action']==(a*.25).tolist()
    target=np.zeros(6);target[[0,1,3,4][axis]]=sign*[12.5e-6,12.5e-6,.000125,.000125][axis]
    np.testing.assert_allclose(log['requested_residual'],target,rtol=0,atol=1e-20)
    np.testing.assert_allclose(command,target,rtol=0,atol=1e-20)
    audit_action_log(log, outer_contract())


@pytest.mark.parametrize('phase', ['UNLOAD','RETRACT','FAILED','STOPPING'])
def test_inactive_experience_zero_even_with_nonzero_request(phase):
    _,log=compose_small_bound_command([1.]*4,context(phase,False),outer_contract())
    assert log['experience_action']==[0.]*4 and log['applied_residual']==[0.]*6
    audit_action_log(log,outer_contract())


def test_limiter_preserves_unscaled_request_and_records_actual_effect():
    c=context();c['base'][0]=.000499
    _,log=compose_small_bound_command([1.,0,0,0],c,outer_contract())
    assert log['experience_action']==[1.,0,0,0]
    assert log['effective_command_delta'][0] < log['applied_residual'][0]
    audit_action_log(log,outer_contract())


@pytest.mark.parametrize('field,value',[('experience_action',[.25,0,0,0]),
    ('compositor_action',[1.,0,0,0]),('requested_residual',[.00005,0,0,0,0,0]),
    ('profile_sha256','0'*64),('predicted_limited_command',[1.]*6)])
def test_scaled_replay_or_wrong_physical_command_rejected(field,value):
    _,log=compose_small_bound_command([1.,0,0,0],context(),outer_contract())
    log[field]=value
    with pytest.raises(ValueError):audit_action_log(log,outer_contract())


def test_contract_rejects_missing_profile_or_quarter_xy_only():
    c=outer_contract();assert validate_outer_contract(c)==profile_digest(c)
    for bad in ({},dict(c,physical_scale_SI=[12.5e-6,12.5e-6,.0005,.0005])):
        with pytest.raises(ValueError):validate_outer_contract(bad)


def test_full_episode_requires_outer_identity_before_rows():
    with pytest.raises(ValueError):audit_small_bound_episode({'mode':'F50'},outer_contract())


def test_session_delegates_once_and_keeps_physical_previous_residual(monkeypatch):
    from types import SimpleNamespace
    from small_bound_session import SmallBoundSession
    from tools.learning.layered_session import LayeredReferenceSession
    from tools.control.search_recovery import SearchConfig
    calls=[]
    def inherited(self,snapshot,action):calls.append(list(action));return snapshot.base_command
    monkeypatch.setattr(LayeredReferenceSession,'_command_for_action',inherited)
    session=object.__new__(SmallBoundSession);session.outer_contract=outer_contract()
    session.outer_admission=SimpleNamespace(verify=lambda *args:None)
    session.env=SimpleNamespace(command=np.zeros(6),config=SimpleNamespace(control_period=.002))
    session.controller=SimpleNamespace(theta=0.,config=SearchConfig())
    snapshot=SimpleNamespace(controller_state={'phase':'INSERT'},residual_enabled=True,base_command=[0.]*6)
    session._command_for_action(snapshot,[1.,-1.,1.,-1.])
    assert calls==[[.25,-.25,.25,-.25]]
    assert session.last_action_log['experience_action']==[1.,-1.,1.,-1.]
    assert session.previous_residual==[12.5e-6,-12.5e-6,.000125,-.000125]
    audit_action_log(session.last_action_log,session.outer_contract)


def episode_fixture():
    """Synthetic audit fixture from one recorded state; never published as a run."""
    import gzip,json
    from small_bound_profile import OUT
    from offline_commands import archive_context
    from tools.learning.reward import EpisodeReward
    old=json.loads(gzip.decompress((OUT.parent/'contact_gate_probe_20261007/run/probe_F12p5_aligned.json.gz').read_bytes()))
    i=next(i for i,l in enumerate(old['actions']) if l['enabled'])
    row=deepcopy(old['transitions'][i]);ctx=archive_context(old,i);c=outer_contract()
    _,log=compose_small_bound_command(old['actions'][i]['actor_action'],ctx,c)
    log['actual_end_limited_command']=old['actions'][i]['actual_end_limited_command']
    row.update(action_log=log,action=log['experience_action'],terminated=True,truncated=False,
        next_observation=old['transitions'][-1]['next_observation'],next_action_active=False)
    reward=EpisodeReward(.004);parts=reward.advance(advance_m=row['advance_m'],dt=row['dt'],force_N=row['cycle_force_N'],torque_G_Nm=row['cycle_torque_G_Nm'])
    parts['terminal']=reward.finalize('TASK_FAILURE');parts['total']+=parts['terminal']
    row.update(reward=parts['total'],reward_terms=parts)
    return dict(physical_profile='F12p5',profile_sha256=profile_digest(c),outer_contract=c,mode='F50',comparison_key=c['common_key'],
        transitions=[row],trace=[old['trace'][i],row['trace_row']],actions=[log],outcome={'task_outcome':'TASK_FAILURE'})


def test_full_episode_audit_recomputes_reward_mask_and_trace():
    raw=episode_fixture();assert audit_small_bound_episode(raw,outer_contract())['cycles']==1
    for field in ['reward','action','actual']:
        bad=deepcopy(raw)
        if field=='reward':bad['transitions'][0]['reward']+=1
        elif field=='action':bad['transitions'][0]['action']=[0.]*4
        else:bad['transitions'][0]['trace_row']['limited_command_world'][0]+=.0001
        with pytest.raises(ValueError):audit_small_bound_episode(bad,outer_contract())
