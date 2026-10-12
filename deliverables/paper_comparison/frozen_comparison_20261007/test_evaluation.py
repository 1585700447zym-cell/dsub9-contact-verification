"""Guard against evaluation leakage, retry and false B2/network accounting."""
import copy, importlib.util
import json, hashlib
from pathlib import Path
import numpy as np
import pytest
PATH=Path(__file__).with_name('run_evaluation.py')
COMMON={'cases':[{'id':n,'x_um':x,'y_um':y} for n,x,y in [
    ('y_neg_150',0,-150),('y_pos_150',0,150),('x_pos_150',150,0),('x_neg_150',-150,0),('aligned',0,0)]]}
def module():
    assert PATH.exists(), 'Evaluation adapter is not implemented'
    spec=importlib.util.spec_from_file_location('pc07_test_target',PATH);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def test_unfinished_attempt_cannot_be_retried():
    m=module();ss=m.attempt_specs(COMMON)
    with pytest.raises(RuntimeError,match='Unfinished'):
        m.next_spec({'status':'running','episodes':[{'id':ss[0]['id'],'status':'running'}]},ss)
def test_ordinary_failure_remains_attempt_and_next_case_runs():
    m=module();ss=m.attempt_specs(COMMON)
    l={'status':'running','episodes':[{'id':ss[0]['id'],'status':'finished','outcome':{'task_outcome':'TASK_FAILURE'}}]}
    assert m.next_spec(l,ss)==ss[1]
def test_closed_or_complete_budget_never_reopens():
    m=module();ss=m.attempt_specs(COMMON)
    assert m.next_spec({'status':'error','episodes':[]},ss) is None
    assert m.next_spec({'status':'running','episodes':[{'id':s['id'],'status':'finished'} for s in ss]},ss) is None
def test_unknown_or_duplicate_attempt_is_rejected():
    m=module();ss=m.attempt_specs(COMMON)
    for ids in [['unknown'],[ss[0]['id'],ss[0]['id']]]:
        with pytest.raises(RuntimeError):m.next_spec({'status':'running','episodes':[{'id':x,'status':'finished'} for x in ids]},ss)
def test_fixed_matrix_has_initial_controls_and_first_use_points_only():
    m=module();ss=m.attempt_specs(COMMON)
    assert len(ss)==27 and len({s['id'] for s in ss})==27
    assert [(p,sum(s['provider']==p for s in ss)) for p in ['B2','F0','S0','F2000','S2000']]==[
        ('B2',9),('F0',5),('S0',5),('F2000',4),('S2000',4)]
    held=m.holdout_cases();assert len(held)==4
    assert [(np.sign(c['x_um']),np.sign(c['y_um'])) for c in held]==[(1,1),(-1,1),(-1,-1),(1,-1)]
    assert all(110<=np.hypot(c['x_um'],c['y_um'])<=150 for c in held)
    assert held[0]['x_um']==pytest.approx(72.199490668416,abs=1e-10)
def test_zero_provider_never_needs_a_network():
    z=module().ZeroUpdater();action,_=z.predict(np.zeros(137),deterministic=True)
    assert action.tolist()==[0.,0.,0.,0.] and z.counts==dict(critic=0,actor=0,temperature=0,target=0)
def fixture(provider='B2'):
    s={'id':'dev_B2_aligned','provider':provider,'mode':'F50','case':{'id':'aligned','x_um':0,'y_um':0},'evaluation_scope':'development'}
    z={'raw_action':[0.]*4,'requested_residual':[0.]*6,'applied_residual':[0.]*6,'effective_command_delta':[0.]*6}
    r={'episode_id':s['id'],'case':s['case'],'mode':'F50','scope':'frozen_development_evaluation','stage':'final',
       'optimizer_steps_start':0,'optimizer_steps':0,'actions':[z],'policy_calls':3}
    return s,r,{'counts':{'critic':0},'rng':[1,2,3]}
@pytest.mark.parametrize('part',['counts','rng'])
def test_changed_model_or_rng_refuses_evaluation(part):
    m=module();s,r,b=fixture();after=copy.deepcopy(b);after[part]=None
    with pytest.raises(ValueError,match='state changed'):m.verify_evaluation(r,s,b,after)
@pytest.mark.parametrize('field',['raw_action','requested_residual','applied_residual','effective_command_delta'])
def test_nonzero_b2_cannot_be_mislabeled_baseline(field):
    m=module();s,r,b=fixture();r['actions'][0][field][0]=.01
    with pytest.raises(ValueError,match='B2'):m.verify_evaluation(r,s,b,b)
def test_case_or_scope_change_refuses_registered_evaluation():
    m=module();s,r,b=fixture()
    for field,value in [('case',{'id':'other'}),('scope','bounded_physical_pilot'),('mode','S50')]:
        bad=copy.deepcopy(r);bad[field]=value
        with pytest.raises(ValueError):m.verify_evaluation(bad,s,b,b)
def test_network_calls_are_zero_for_b2_and_actual_for_initial_actor():
    m=module();s,r,b=fixture();assert m.verify_evaluation(r,s,b,b)['network_policy_calls']==0
    s,r,b=fixture('F0');assert m.verify_evaluation(r,s,b,b)['network_policy_calls']==3

@pytest.mark.parametrize('failure',['rollout','audit'])
def test_fault_after_network_calls_preserves_actual_attempt_cost(tmp_path,monkeypatch,failure):
    # Native stepping/audit are the faulting external boundary. Exercise the
    # real execute exception/finally code and its durable ledger, not a mock ledger.
    m=module();monkeypatch.setattr(m,'OUT',tmp_path)
    from types import SimpleNamespace
    from tools.validation import run_v4_learning_pilot as pilot
    from tools.learning import v4_checkpoint as checkpoint
    specs=m.attempt_specs(COMMON);specs[0]={**specs[0],'provider':'F0'}
    config={'attempts':specs,'checkpoints':{'F0':{'label':'zero','pin':'unused'}}}
    (tmp_path/'configuration.json').write_text(json.dumps(config),encoding='utf8')
    q={'evaluation_admitted':True,'training_admitted':False,'formal_updates':0,'max_new_episodes':27,'evidence_sha256':{}}
    (tmp_path/'qualification.json').write_text(json.dumps(q),encoding='utf8')
    admission=SimpleNamespace(verify=lambda mode:{'qualification_sha256':'test','config_sha256':'test'})
    monkeypatch.setattr(m,'verify_sources',lambda config:admission)
    monkeypatch.setattr(checkpoint,'read_checkpoint',lambda *a,**k:({'warm':{'draws':0}},(m.ZeroUpdater(),None,None,None)))
    def faulting_rollout(folder,chain,spec,entry,ledger,**kwargs):
        entry.update(policy_calls=7,status='error' if failure=='rollout' else 'finished')
        ledger['policy_calls']+=7
        if failure=='rollout':raise RuntimeError('injected native boundary fault')
        return {'policy_calls':7}
    def faulting_audit(raw):raise RuntimeError('injected audit boundary fault')
    monkeypatch.setattr(pilot,'rollout',faulting_rollout);monkeypatch.setattr(pilot,'audit_evaluation',faulting_audit)
    with pytest.raises(RuntimeError,match='boundary fault'):m.execute(m.sha(tmp_path/'qualification.json'))
    ledger=json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf8'))
    assert ledger['status']=='error' and ledger['network_policy_calls']==7
    assert ledger['episodes'][0]['network_policy_calls']==7 and ledger['unused_closed']==26
