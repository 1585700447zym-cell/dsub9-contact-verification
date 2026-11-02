"""Protocol tests: fake learning only; real forwards/steps/physics are blocked."""
from copy import deepcopy
import importlib
import pytest
import torch


def module():return importlib.import_module('tools.learning.actor_lr_engine')


@pytest.fixture(scope='module')
def origin():return module().read_origin()


def test_pinned_origin_and_draws(origin):
    state,plan=origin
    assert state['updater']['counts']['critic']==0
    assert state['replay']['size']==22766 and len(plan['batches'])==500


@pytest.mark.parametrize('branch',['A','B'])
def test_private_restore_zero_no_forward(origin,branch):
    m=module();state,plan=origin
    engine=m.OfflineBranch(state,plan,branch,'a'*64,'b'*64)
    snapshot=engine.capture()
    restored=m.validate_state(snapshot,state,plan,branch,'a'*64,'b'*64,formal_only=False)
    assert m._same(restored._snapshot(),engine.updater._snapshot())
    assert snapshot['comparison_binding']['branch']==branch


@pytest.mark.parametrize('field',['binding','replay','count','lr','rng','history','boundary_index'])
def test_restore_tamper_rejected(origin,field):
    m=module();state,plan=origin
    engine=m.OfflineBranch(state,plan,'B','a'*64,'b'*64);saved=engine.capture()
    if field=='binding':saved['comparison_binding']['branch']='A'
    elif field=='replay':saved['replay']['episodes'][0][1]['rewards'][0,0]+=1
    elif field=='count':saved['updater']['counts']['critic']=True
    elif field=='lr':saved['updater']['actor']['param_groups'][0]['lr']=3e-4
    elif field=='rng':saved['rng']['replay']['state']['state']+=1
    elif field=='boundary_index':saved['boundary_index']={}
    else:saved['history']=[{}]
    with pytest.raises(ValueError):m.validate_state(saved,state,plan,'B','a'*64,'b'*64,formal_only=False)


def test_origin_not_formal_checkpoint(origin):
    m=module();state,plan=origin
    saved=m.OfflineBranch(state,plan,'A','a'*64,'b'*64).capture()
    with pytest.raises(ValueError):m.validate_state(saved,state,plan,'A','a'*64,'b'*64)


def test_reserve_precedes_sampling_or_update(origin):
    m=module();state,plan=origin;engine=m.OfflineBranch(state,plan,'A','a'*64,'b'*64)
    before=engine.capture()
    class Refuse:
        def assert_binding(self,*a):pass
        def reserve(self,*a,**k):raise OSError('durable reservation failed')
    with pytest.raises(OSError):engine.update_one(Refuse())
    assert m._same(before,engine.capture())


def test_sampling_plan_mismatch_stops_before_update(origin,monkeypatch):
    m=module();state,plan=origin;engine=m.OfflineBranch(state,plan,'A','a'*64,'b'*64)
    calls=[]
    class Ledger:
        def assert_binding(self,*a):pass
        def reserve(self,*a,**k):calls.append('reserved');return 0
        def fail(self,error):calls.append('failed')
    engine.plan['batches'][0]['critic_indices'][0][1]+=1
    monkeypatch.setattr(engine.updater,'update',lambda *a,**k:pytest.fail('update before exact draws'))
    with pytest.raises(ValueError):engine.update_one(Ledger())
    assert calls==['reserved','failed'] and engine.failed


def test_first_fixed_input_and_metadata_with_fake_update(origin,monkeypatch):
    m=module();state,plan=origin;engine=m.OfflineBranch(state,plan,'A','a'*64,'b'*64)
    events=[]
    class Ledger:
        def assert_binding(self,*a):pass
        def reserve(self,*a,**k):events.append('reserve');return 0
        def finish(self,token,result):events.append('finish');assert result['completed'] is True
        def fail(self,error):pytest.fail(error)
    def fake(actor,**kw):
        events.append('fake_update');assert actor.observations.shape==(256,120)
        engine.updater.counts=dict(actor=1,critic=1,temperature=1,target=1)
        return dict(critic_batches=1,active_rows=int(actor.action_active.sum()),batch_rows=256)
    monkeypatch.setattr(engine.updater,'update',fake)
    result=engine.update_one(Ledger())
    assert events==['reserve','fake_update','finish']
    assert result['episodes']==4 and result['credit_remaining']==499 and result['boundary_quota']==16


def test_mismatched_durable_authorization_rejected_before_draw(origin,tmp_path,monkeypatch):
    m=module();state,plan=origin;e=m.OfflineBranch(state,plan,'A','a'*64,'b'*64)
    from tools.learning.actor_lr_budget import ComparisonLedger
    ledger=ComparisonLedger.create(tmp_path/'ledger.json','a'*64,'c'*64);ledger.complete_validation('d'*64)
    monkeypatch.setattr(e,'next_batch',lambda:pytest.fail('draw before binding check'))
    with pytest.raises(ValueError):e.update_one(ledger)
    assert ledger.state['attempts']==[]


def test_a_reproduction_ignores_only_walltime(origin):
    m=module();state,_=origin;a=deepcopy(state);b=deepcopy(state)
    a['history']=[dict(loss=1.,wall_s=1.)];b['history']=[dict(loss=1.,wall_s=2.)]
    assert m.reproduction_fields_equal(a,b)
    b['updater']['rng'][0]^=1
    assert not m.reproduction_fields_equal(a,b)


def test_a_reproduction_does_not_ignore_losses(origin):
    m=module();state,_=origin;a=deepcopy(state);b=deepcopy(state)
    a['history']=[dict(loss=1.,wall_s=1.)];b['history']=[dict(loss=1.00001,wall_s=1.)]
    assert not m.reproduction_fields_equal(a,b)


def test_noactive_batch_clears_all_action_permissions(origin):
    m=module();state,plan=origin;e=m.OfflineBranch(state,plan,'A','a'*64,'b'*64)
    batch=e.next_batch();inactive=m.inactive_batch(batch.actor)
    assert not inactive.action_active.any() and not inactive.next_action_active.any() and not inactive.actions.any()
    assert torch.equal(inactive.observations,batch.actor.observations)
