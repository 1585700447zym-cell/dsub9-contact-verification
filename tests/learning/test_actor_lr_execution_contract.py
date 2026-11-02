import importlib
from copy import deepcopy
import pytest


def module():
    try:
        return importlib.import_module('tools.learning.actor_lr_contract')
    except ModuleNotFoundError as exc:
        pytest.fail('Comparison contract missing: '+str(exc))


def test_single_variable_execution_configs_and_exact_scope():
    m=module();a=m.execution_config('A');b=m.execution_config('B')
    assert a['learning']['actor_learning_rate']==3e-4 and b['learning']['actor_learning_rate']==3e-5
    assert a['learning']['learning_rate']==b['learning']['learning_rate']==3e-4
    assert a['learning']['max_gradient_batches']==b['learning']['max_gradient_batches']==500
    assert a['execution']['new_training_collection']==b['execution']['new_training_collection']==0
    assert a['sampling']['max_attempts']==b['sampling']['max_attempts']==0
    for c in (a,b):
        m.validate_execution_config(c)
        c['comparison']['branch']='same';c['learning']['actor_learning_rate']=0
    assert a==b


@pytest.mark.parametrize('field,value',[('actor_learning_rate',3e-6),('learning_rate',3e-5),('batch_size',128),('max_gradient_batches',501)])
def test_unregistered_config_changes_rejected(field,value):
    m=module();c=m.execution_config('B');c['learning'][field]=value
    with pytest.raises(ValueError):m.validate_execution_config(c)


def authorization():
    m=module()
    return dict(version='actor_lr_user_authorization_v1',approved=True,candidate_sha256='a'*64,
        scope='validation_and_conditional_ab',user_confirmation='明确批准所列新预算一次执行',budget=m.compute_budget())


def test_authorization_requires_exact_new_budget_and_candidate():
    m=module();r=authorization();m.validate_authorization(r,'a'*64)
    assert r['budget']['formal']==dict(A=500,B=500)
    assert r['budget']['physical']==dict(A=4,B=4)
    assert r['budget']['synthetic']==16 and r['budget']['test_forward']==128
    assert r['budget']['diagnostic']==dict(initial=256,A=256,B=256)
    assert r['budget']['old_unused_consumed']==0 and r['budget']['automatic_tracking'] is False


@pytest.mark.parametrize('field,value',[('approved',False),('approved',1),('candidate_sha256','b'*64),
    ('scope','continue_old_cycle'),('user_confirmation',''),('version','force_cycle_user_authorization_v1')])
def test_incomplete_or_cross_cycle_authorization_rejected(field,value):
    m=module();r=authorization();r[field]=value
    with pytest.raises(ValueError):m.validate_authorization(r,'a'*64)


@pytest.mark.parametrize('field,value',[('synthetic',17),('test_forward',129),('old_unused_consumed',19),
    ('automatic_tracking',True),('previous_dynamic',0)])
def test_budget_cannot_extend_or_consume_old_remaining(field,value):
    m=module();r=authorization();r['budget'][field]=value
    with pytest.raises(ValueError):m.validate_authorization(r,'a'*64)


def test_preparation_configuration_cannot_be_executed():
    m=module()
    from tools.learning.actor_lr_preparation import preparation_config
    with pytest.raises(ValueError):m.validate_execution_config(preparation_config('A'))


@pytest.mark.parametrize('branch',['initial','C',None,True])
def test_unregistered_execution_branch_rejected(branch):
    with pytest.raises(ValueError):module().execution_config(branch)


def test_candidate_external_a_key_cannot_hold_valid_b_config(monkeypatch):
    m=module();config=m.execution_config('B');pin='a'*64
    record=dict(version='actor_lr_comparison_candidate_v1',synthetic_only=False,
        protocol_preparation_passed=True,real_validation_required=True,user_authorization_required=True,
        origin_manifest_sha256=m.ORIGIN_PIN,budget=m.compute_budget(),configs=dict(A=config,B=config))
    original_digest=m.digest
    monkeypatch.setattr(m,'digest',lambda path:pin if path==m.DELIVERY/'candidate.json' else original_digest(path))
    original_read=m.read
    monkeypatch.setattr(m,'read',lambda path:record if path==m.DELIVERY/'candidate.json' else original_read(path))
    with pytest.raises(ValueError,match='A/B key'):m.verify_candidate(pin,check_runtime=False)
