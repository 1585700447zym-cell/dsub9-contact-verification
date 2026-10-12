"""Brand-new synthetic interface data; no historical replay or physics."""
from copy import deepcopy
import math
import numpy as np
from numeric_contract import profile_contract,profile_pin
from tools.learning.v4_pilot_contract import field_slices,training_cases,SEED
from tools.learning.reward import EpisodeReward
from small_bound_profile import compose_small_bound_command,audit_small_bound_episode


def observation(active):
    s=field_slices();o=np.zeros(137,dtype=np.float32)
    for name,index in [('policy_phase',0),('physical_phase',0 if active else 1),
                       ('recovery_phase',0),('decision',0 if active else 4)]:o[s[name].start+index]=1.
    o[s['action_active']]=float(active);o[s['simulation_valid']]=1.;o[s['pending']]=float(not active)
    return o.tolist()


def test_states():
    states=[];s=field_slices()
    for i in range(16):
        o=observation(True);o[s['relative_drive_reference_m'].start]=(i-8)/100.
        states.append(o)
    return states


def synthetic_episode(chain,stage,index):
    if stage not in ('warmup','online') or type(index) is not int or not 0<=index<4:
        raise ValueError('Registered synthetic case required')
    inner=chain.inner;case=training_cases()[index];contract=chain.contract
    rows=[];trace=[dict(time_s=0.,position_m=[0.]*3,limited_command_world=[0.]*6)];logs=[]
    previous=[0.]*6;reward=EpisodeReward(.004)
    for i in range(80):
        active=i<78;end=i==79;sample=chain.warm_action(i) if stage=='warmup' else None
        action=(sample if sample is not None else [1.,-.75,.5,-.25]) if active else [0.]*4
        context=dict(base=[0.]*6,phase='INSERT' if active else 'FAILED',enabled=active,previous_limited=previous,
                     dt=.002,reference_xy=None,radius=.00012,next_theta=None,search_config=None)
        _,log=compose_small_bound_command(action,context,contract)
        previous=list(log['predicted_limited_command']);log['actual_end_limited_command']=previous
        point=dict(time_s=(i+1)*.002,position_m=[0.]*3,limited_command_world=previous)
        parts=reward.advance(advance_m=0.,dt=.002,force_N=0.,torque_G_Nm=0.)
        parts['terminal']=reward.finalize('TASK_FAILURE') if end else 0.;parts['total']+=parts['terminal']
        rows.append(dict(observation=observation(active),next_observation=observation(i<77),
            action=log['experience_action'],action_active=active,next_action_active=i<77,
            terminated=end,truncated=False,dt=.002,discount=math.exp(-.002/10),reward=parts['total'],reward_terms=parts,
            advance_m=0.,cycle_force_N=0.,cycle_torque_G_Nm=0.,action_log=log,trace_row=point,sampling_request=sample))
        trace.append(point);logs.append(log)
    raw=dict(version='v4_training_episode_v1',scope='synthetic_qualification',mode='F50',
        stage=stage,case=case,case_id=case['id'],case_index=index,episode_id=stage+'_F50_'+case['id'],seed=SEED,
        physical_profile='F12p5',profile_sha256=profile_pin(),outer_contract=deepcopy(contract),comparison_key=contract['common_key'],
        qualification_sha256=inner.binding['qualification_sha256'],config_sha256=inner.binding['config_sha256'],
        optimizer_steps_start=inner.updater.counts['critic'],optimizer_steps=inner.updater.counts['critic'],
        policy_sha256=inner.updater.fingerprints()['actor'],warmup_draws=inner.warm_draws,
        transitions=rows,trace=trace,actions=logs,fault=None,synthetic=True,dynamics_executed=False,
        input_origin='registered_new_synthetic_generator',physical_stop_measurement=None,
        outcome=dict(simulation_valid=True,physical_stopped=True,valid_for_learning=True,task_outcome='TASK_FAILURE',
                     guard_violations=dict(contact=False,motion=False)))
    # Boolean eligibility flags exercise the synthetic core interface only.
    # They do not assert that a physical episode or stop measurement occurred.
    audit_small_bound_episode(raw,contract)
    return raw
