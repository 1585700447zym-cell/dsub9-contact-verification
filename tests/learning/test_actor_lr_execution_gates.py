"""Orchestration and publication gates with explicit stand-ins, no numerics."""
from copy import deepcopy
import importlib
import json
import pytest


def module():return importlib.import_module('tools.learning.actor_lr_execution')


def test_a_learning_mismatch_stops_before_b_or_checkpoint(tmp_path,monkeypatch):
    m=module();events=[]
    monkeypatch.setattr(m,'assert_validation_proof',lambda *a:None)
    class FakeBranch:
        def __init__(self,o,p,branch,*pins):events.append(branch);assert branch=='A'
        def update_one(self,ledger):events.append('fake_batch')
    monkeypatch.setattr(m,'OfflineBranch',FakeBranch)
    def mismatch(engine):raise ValueError('exact A mismatch')
    monkeypatch.setattr(m,'verify_a_reproduction',mismatch)
    monkeypatch.setattr(m,'save_checkpoint',lambda *a:pytest.fail('checkpoint after mismatch'))
    with pytest.raises(ValueError,match='exact A mismatch'):m.formal_branches({}, {},object(),tmp_path,'a'*64,'b'*64)
    assert events[0]=='A' and events.count('fake_batch')==500 and 'B' not in events
    assert not (tmp_path/'frozen.json').exists()


def proof_ledger(tmp_path):
    m=module();from tools.learning.actor_lr_budget import ComparisonLedger
    ledger=ComparisonLedger.create(tmp_path/'ledger.json','a'*64,'b'*64)
    for i in range(4):
        token=ledger.reserve('synthetic','shared',str(i));ledger.finish(token,dict(completed=True))
    token=ledger.reserve('test_forward','shared','predict',units=8);ledger.finish(token,dict(completed=True))
    proof=dict(passed=True,candidate_sha256='a'*64,authorization_sha256='b'*64,synthetic_transactions=4,test_forward_states=8)
    m.write(tmp_path/'real_validation.json',proof);ledger.complete_validation(m.digest(tmp_path/'real_validation.json'))
    return ledger


def test_bound_validation_receipt_checked_before_formal(tmp_path):
    m=module();ledger=proof_ledger(tmp_path);m.assert_validation_proof(ledger,tmp_path)
    proof=m.read(tmp_path/'real_validation.json');proof['authorization_sha256']='c'*64
    m.write(tmp_path/'real_validation.json',proof)
    ledger.state['gates']['real_validation']=m.digest(tmp_path/'real_validation.json')
    with pytest.raises(ValueError):m.assert_validation_proof(ledger,tmp_path)


def test_pinned_validation_receipt_cannot_be_replaced(tmp_path):
    m=module();ledger=proof_ledger(tmp_path);proof=m.read(tmp_path/'real_validation.json');proof['passed']=False
    m.write(tmp_path/'real_validation.json',proof)
    with pytest.raises(ValueError):m.assert_validation_proof(ledger,tmp_path)


def test_allow_active_only_accepts_physical_publication(tmp_path):
    m=module();ledger=proof_ledger(tmp_path);ledger.reserve('formal','A','batch_000')
    with pytest.raises(RuntimeError):m.assert_validation_proof(ledger,tmp_path,allow_active=True)


def test_child_parent_rejection_precedes_execution_import_or_claim(monkeypatch):
    m=importlib.import_module('tools.validation.run_actor_lr_comparison')
    monkeypatch.setattr(m,'require_authorization',lambda *a: {})
    monkeypatch.setattr(m,'select_qualified_runtime',lambda:None)
    monkeypatch.setattr(m,'verify_candidate',lambda *a: {})
    def refuse(*a):raise RuntimeError('registered parent missing')
    monkeypatch.setattr(m,'require_parent',refuse)
    monkeypatch.setattr(m,'claim',lambda *a:pytest.fail('claim before parent'))
    with pytest.raises(RuntimeError,match='registered parent missing'):
        m.main(['--candidate-sha256','a'*64,'--authorization-sha256','b'*64,'--worker'])


def test_evaluation_admission_rejects_holdout_and_training_points(monkeypatch):
    m=module();from types import SimpleNamespace
    ledger=SimpleNamespace(state=dict(candidate_sha256='a'*64,authorization_sha256='b'*64),check_execution=lambda:None)
    monkeypatch.setattr(m,'require_authorization',lambda *a: {})
    monkeypatch.setattr(m,'verify_candidate',lambda *a: {})
    monkeypatch.setattr(m,'verify_evaluation_gate',lambda *a: {})
    permit=m.ComparisonAdmission('a'*64,'b'*64,'A',ledger)
    assert permit.verify(m.cases()[0])['evaluation_admitted'] is True
    case=deepcopy(m.cases()[0]);case['x_offset_m']=.000095
    with pytest.raises(ValueError):permit.verify(case)
    case=deepcopy(m.cases()[0]);case['name']='train_00'
    with pytest.raises(ValueError):permit.verify(case)
    assert permit.config['sampling']['max_attempts']==0
    assert permit.verify()['update_admitted'] is False


def test_diagnostic_parameter_change_rejected_even_with_same_identity(tmp_path,monkeypatch):
    m=module();from types import SimpleNamespace
    monkeypatch.setattr(m,'assert_validation_proof',lambda *a,**k:None)
    selection=tmp_path/'selection.json';selection.write_text('{}',encoding='utf-8');monkeypatch.setattr(m,'DIAGNOSTIC',selection)
    frozen=dict(A=dict(path='checkpoint_A',sha256='d'*64),B=dict(path='checkpoint_B',sha256='e'*64))
    m.write(tmp_path/'frozen.json',frozen)
    m.write(tmp_path/'a_reproduction.json',dict(learning_exact=True,candidate_sha256='a'*64,authorization_sha256='b'*64))
    diagnostic=dict(candidate_sha256='a'*64,authorization_sha256='b'*64,states_per_role=256,
        state_selection_sha256=m.digest(selection),parameters=dict(test_mean=0.))
    m.write(tmp_path/'diagnostics.json',diagnostic)
    ledger=SimpleNamespace(state=dict(phase='evaluation',gates=dict(a_reproduced=m.digest(tmp_path/'a_reproduction.json'),
        b_frozen='e'*64,evaluation_checkpoints=dict(A='d'*64,B='e'*64),diagnostics=m.digest(tmp_path/'diagnostics.json'))))
    m.verify_evaluation_gate(ledger,tmp_path,'a'*64,'b'*64)
    diagnostic['parameters']['test_mean']=1.;m.write(tmp_path/'diagnostics.json',diagnostic)
    with pytest.raises(ValueError):m.verify_evaluation_gate(ledger,tmp_path,'a'*64,'b'*64)
