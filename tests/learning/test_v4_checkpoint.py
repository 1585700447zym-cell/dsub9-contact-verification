"""Self-contained 137D state, complete replay audit and actual next-step restore."""
from copy import deepcopy
from pathlib import Path
import gzip,hashlib,json,math
import numpy as np
import pytest
import torch
from tools.learning.sac_checkpoint import _same
from tools.learning.v4_pilot_contract import learning_config,field_slices

def synthetic_binding(mode):
    c=learning_config(mode)
    from tools.learning.v4_pilot_contract import canonical
    return dict(purpose='synthetic_qualification',mode=mode,qualification_sha256='a'*64,
        config_sha256=hashlib.sha256(canonical(c).encode()).hexdigest())

def observation(mode,active):
    s=field_slices();o=np.zeros(137,dtype=np.float32)
    for name,i in [('policy_phase',2 if active else 0),('physical_phase',0 if active or mode=='S50' else 1),
        ('recovery_phase',0),('decision',0 if active or mode=='S50' else 4)]:o[s[name].start+i]=1
    o[s['action_active']]=float(active);o[s['simulation_valid']]=1
    if not active and mode=='F50':o[s['pending']]=1
    o[120:123]=.1
    return o.tolist()

def raw_episode(chain,stage,index,*,valid=True,guard=False):
    from tools.learning.v4_pilot_contract import training_cases
    case=training_cases()[index];active=observation(chain.mode,True);inactive=observation(chain.mode,False)
    rows=[]
    for i in range(80):
        end=i==79
        sample=chain.warm_action(i) if stage=='warmup' else None
        action=sample if sample is not None else [0.]*4
        rows.append(dict(observation=active,next_observation=inactive if end else active,
            action=action,action_active=True,next_action_active=not end,terminated=end,truncated=False,sampling_request=sample,
            dt=.002,discount=math.exp(-.002/10),reward=(-10 if guard else 10)-.0002 if end else -.0002,
            reward_terms=dict(progress=0.,time=-.0002,force=0.,torque=0.,terminal=(-10 if guard else 10) if end else 0.,
                total=(-10 if guard else 10)-.0002 if end else -.0002),advance_m=0.,cycle_force_N=0.,cycle_torque_G_Nm=0.,
            action_log=dict(raw_action=action,enabled=True,experience_action=action,applied_residual=[0.]*6)))
    return dict(version='v4_training_episode_v1',scope='synthetic_qualification',episode_id=stage+'_'+chain.mode+'_'+case['id'],
        mode=chain.mode,stage=stage,case_id=case['id'],case_index=index,case=case,seed=2026092716,
        qualification_sha256=chain.binding['qualification_sha256'],config_sha256=chain.binding['config_sha256'],
        optimizer_steps_start=chain.updater.counts['critic'],optimizer_steps=chain.updater.counts['critic'],
        policy_sha256=chain.updater.fingerprints()['actor'],transitions=rows,warmup_draws=chain.warm_draws,
        outcome=dict(simulation_valid=valid,physical_stopped=True,valid_for_learning=valid,
            task_outcome='CONTACT_GUARD' if guard else 'FULL_SUCCESS',guard_violations=dict(contact=guard,motion=False)),fault=None)

def populated(path,mode='F50'):
    from tools.learning.v4_pilot_chain import V4Chain
    c=V4Chain(learning_config(mode),output=path,binding=synthetic_binding(mode))
    for i in range(4):c.begin('warmup',i);c.publish(raw_episode(c,'warmup',i))
    c.begin('online',0);c.publish(raw_episode(c,'online',0));return c

def api():
    from tools.learning import v4_checkpoint
    return v4_checkpoint

def test_complete_state_restore_matches_rng_next_action_draws_and_update(tmp_path):
    c=populated(tmp_path/'c');c.update(2);pin=api().save_checkpoint(c,tmp_path/'checkpoint')
    r=api().load_checkpoint(tmp_path/'checkpoint',expected_digest=pin,expected_binding=c.binding,output=tmp_path/'r')
    assert _same(c.updater._snapshot(),r.updater._snapshot()) and c.replay.episode_ids==r.replay.episode_ids
    a=c.updater.predict(observation('F50',True))[0];b=r.updater.predict(observation('F50',True))[0]
    np.testing.assert_array_equal(a,b)
    x=c.update(1)[0];y=r.update(1)[0]
    assert {k:v for k,v in x.items() if k!='wall_s'}=={k:v for k,v in y.items() if k!='wall_s'}
    assert c.updater.fingerprints()==r.updater.fingerprints()

def test_zero_admission_blocks_updates_and_invalid_episode_is_wholly_isolated(tmp_path):
    from tools.learning.v4_pilot_chain import V4Chain
    c=V4Chain(learning_config('F50'),output=tmp_path/'c',binding=synthetic_binding('F50'))
    with pytest.raises(RuntimeError):c.update(1)
    c.begin('warmup',0);receipt=c.publish(raw_episode(c,'warmup',0,valid=False))
    assert receipt['committed']==0 and len(c.replay)==0 and c.failed
    with pytest.raises(RuntimeError):c.begin('warmup',1)

def test_valid_guard_data_retained_but_branch_cannot_keep_optimizing(tmp_path):
    c=populated(tmp_path/'c');c.update(1);c.begin('online',1);receipt=c.publish(raw_episode(c,'online',1,guard=True))
    assert receipt['committed']==80 and c.stop_reason=='CONTACT_GUARD'
    with pytest.raises(RuntimeError):c.update(1)

def test_old_width_cross_mode_or_tampered_checkpoint_cannot_create_output(tmp_path):
    c=populated(tmp_path/'c');pin=api().save_checkpoint(c,tmp_path/'checkpoint')
    wrong=deepcopy(c.binding);wrong['mode']='S50'
    with pytest.raises(ValueError):api().load_checkpoint(tmp_path/'checkpoint',expected_digest=pin,expected_binding=wrong,output=tmp_path/'bad')
    assert not (tmp_path/'bad').exists()
    p=tmp_path/'checkpoint/state.pt';data=bytearray(p.read_bytes());data[len(data)//2]^=1;p.write_bytes(data)
    with pytest.raises(ValueError):api().load_checkpoint(tmp_path/'checkpoint',expected_digest=pin,expected_binding=c.binding,output=tmp_path/'bad')
    assert not (tmp_path/'bad').exists()

def test_capture_refuses_active_or_unrecorded_optimizer_attempt(tmp_path):
    c=populated(tmp_path/'c');c.active=True
    with pytest.raises(RuntimeError):api().capture(c)
    c.active=False;c.update_attempts+=1
    with pytest.raises(RuntimeError):api().capture(c)

def test_staging_write_failure_never_publishes_loadable_checkpoint(tmp_path,monkeypatch):
    c=populated(tmp_path/'c');m=api()
    def fail(*args):raise OSError('injected checkpoint write error')
    monkeypatch.setattr(m,'flush_write',fail)
    with pytest.raises(OSError):m.save_checkpoint(c,tmp_path/'checkpoint')
    assert not (tmp_path/'checkpoint').exists() and list(tmp_path.glob('checkpoint.stage-*'))

def test_checkpoint_revalidates_raw_replay_and_adam_counters(tmp_path):
    c=populated(tmp_path/'c');c.update(2);state=api().capture(c)
    state['updater']['counts']['critic']=1
    with pytest.raises(ValueError):api().validate_state(state,expected_binding=c.binding)
    state=api().capture(c);state['replay']['episodes'][0][1]['observations'][0,0]=.99
    with pytest.raises(ValueError):api().validate_state(state,expected_binding=c.binding)

def test_wrong_source_scope_cannot_publish_old_preflight_as_training(tmp_path):
    c=populated(tmp_path/'c');c.begin('online',1);raw=raw_episode(c,'online',1);raw['scope']='development_preflight_only'
    with pytest.raises(ValueError):c.publish(raw)
    assert c.failed and len(c.replay)==400

def test_insufficient_active_warmup_blocks_online_physics_boundary(tmp_path):
    from tools.learning.v4_pilot_chain import V4Chain
    c=V4Chain(learning_config('S50'),output=tmp_path/'c',binding=synthetic_binding('S50'))
    for i in range(4):
        c.begin('warmup',i);raw=raw_episode(c,'warmup',i)
        for row in raw['transitions']:
            row['observation']=observation('S50',False);row['next_observation']=observation('S50',False)
            row['action_active']=row['next_action_active']=False;row['action_log']['enabled']=False
            row['action']=row['action_log']['raw_action']=row['action_log']['experience_action']=[0.]*4
        c.publish(raw)
    with pytest.raises(RuntimeError):c.begin('online',0)

def test_warm_stream_restore_proves_next_held_action(tmp_path):
    from tools.learning.v4_pilot_chain import V4Chain
    c=V4Chain(learning_config('F50'),output=tmp_path/'c',binding=synthetic_binding('F50'))
    c.begin('warmup',0);c.publish(raw_episode(c,'warmup',0));assert c.warm_draws==2
    pin=api().save_checkpoint(c,tmp_path/'checkpoint')
    r=api().load_checkpoint(tmp_path/'checkpoint',expected_digest=pin,expected_binding=c.binding,output=tmp_path/'r')
    c.begin('warmup',1);r.begin('warmup',1)
    assert c.warm_action(0)==r.warm_action(0)
    assert c.warm_action(49)==r.warm_action(49) and c.warm_action(50)==r.warm_action(50)

def test_successful_truncation_is_rejected_before_publication(tmp_path):
    c=populated(tmp_path/'c');c.begin('online',1);raw=raw_episode(c,'online',1)
    raw['transitions'][-1].update(terminated=False,truncated=True)
    with pytest.raises(ValueError):c.publish(raw)
    assert c.failed and len(c.replay)==400

def test_mid_chunk_failure_preserves_completed_batch_journal(tmp_path,monkeypatch):
    c=populated(tmp_path/'c');original=c.updater.update;calls=0
    def fail_second(*args,**kwargs):
        nonlocal calls;calls+=1
        if calls==2:raise RuntimeError('injected second batch failure')
        return original(*args,**kwargs)
    monkeypatch.setattr(c.updater,'update',fail_second)
    with pytest.raises(RuntimeError):c.update(3)
    journal=[json.loads(line) for line in (c.output/'update_journal.jsonl').read_text(encoding='utf8').splitlines()]
    completed=[r for r in journal if r['event']=='complete']
    assert len(completed)==1 and completed[0]['stats']==c.history[0]
    assert completed[0]['counts']['critic']==1 and c.update_attempts==2 and c.failed
    with pytest.raises(RuntimeError):api().capture(c)

def test_completion_write_failure_retains_actual_optimizer_count(tmp_path,monkeypatch):
    c=populated(tmp_path/'c')
    original=getattr(c,'_append_event',lambda *a,**k:None)
    def fail(event,**data):
        if event=='complete':raise OSError('injected completion fsync error')
        return original(event,**data)
    monkeypatch.setattr(c,'_append_event',fail,raising=False)
    with pytest.raises(OSError):c.update(1)
    assert c.failed and c.updater.counts['critic']==1 and len(c.history)==1
    with pytest.raises(RuntimeError):api().capture(c)
