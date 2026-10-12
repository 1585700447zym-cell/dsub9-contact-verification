"""Persistent one-claim scheduling and admission, using protocol-only ledgers."""
from copy import deepcopy
import json, math
import pytest
from small_bound_profile import outer_contract,profile_digest,registration
from run_small_bound_pilot import (attempt_specs,reserve_task,verify_admission,
                                  ProtocolLedger,task_specs,execute_protocol)


def test_registered_exact_matrix_and_update_order():
    r=registration();items=attempt_specs(r)
    assert len(items)==21 and len({x['id'] for x in items})==21
    assert [sum(x['stage']==s for x in items) for s in ['preflight','initial','warmup','online','final','restore']]==[2,5,4,4,5,1]
    assert sum(x['updates'] for x in items)==2000
    tasks=task_specs(r)
    assert len(tasks)==27 # 21 physical + 4 blocks + initial/restore checkpoint reads
    for j,t in enumerate(tasks):
        if t['kind']=='update':assert tasks[j-1]['attempt']['stage']=='online' and t['batches']==500


@pytest.mark.parametrize('kind,cap',[('episode',1200),('update',1200),('checkpoint_read',300)])
def test_reserve_worst_case_before_start(kind,cap):
    assert reserve_task(kind,cap)==cap
    for value in [cap-.001,-1,float('nan'),float('inf'),True]:
        with pytest.raises(ValueError):reserve_task(kind,value)


def test_candidate_or_old_authorization_never_admits():
    c=dict(status='NOT_ADMITTED',training_admitted=False,execution_authorized=False)
    with pytest.raises(PermissionError):verify_admission(c,None,None)
    with pytest.raises(PermissionError):verify_admission(c,{'stage':'PC06','remaining':28},{'passed':True})


def test_one_claim_and_persistent_attempt_before_completion(tmp_path):
    ledger=ProtocolLedger(tmp_path/'test_claim',registration(),protocol_only=True)
    with pytest.raises(FileExistsError):ProtocolLedger(tmp_path/'test_claim',registration(),protocol_only=True)
    task=ledger.start(elapsed_wall_s=0)
    saved=json.loads(ledger.path.read_text(encoding='utf8'))
    assert saved['active']['id']==task['id'] and saved['physical_attempts_started']==1
    with pytest.raises(RuntimeError):ledger.start(elapsed_wall_s=0)
    ledger.finish(dict(valid=True,stopped=True,reference_ok=True,guard=False,outcome='TASK_FAILURE',cycles=1,substeps=10,policy_calls=0,published_rows=0),elapsed_wall_s=1)
    assert ledger.data['next_task']==1


def test_insufficient_time_does_not_spend_attempt_and_closes(tmp_path):
    ledger=ProtocolLedger(tmp_path/'test_claim',registration(),protocol_only=True)
    with pytest.raises(ValueError):ledger.start(elapsed_wall_s=21600-1199)
    assert ledger.data['physical_attempts_started']==0 and ledger.data['status']=='closed'
    with pytest.raises(RuntimeError):ledger.start(elapsed_wall_s=21600)


@pytest.mark.parametrize('field,value',[('guard',True),('valid',False),('stopped',False),('reference_ok',False)])
def test_fault_or_guard_closes_unused_credit(tmp_path,field,value):
    ledger=ProtocolLedger(tmp_path/'test_claim',registration(),protocol_only=True);ledger.start(elapsed_wall_s=0)
    outcome=dict(valid=True,stopped=True,reference_ok=True,guard=False,outcome='TASK_FAILURE',cycles=1,substeps=10,policy_calls=0,published_rows=0)
    outcome[field]=value;ledger.finish(outcome,elapsed_wall_s=1)
    assert ledger.data['status']=='closed' and ledger.data['updates_attempted']==0
    with pytest.raises(RuntimeError):ledger.start(elapsed_wall_s=2)


def test_evaluation_publication_and_extra_attempt_rejected(tmp_path):
    ledger=ProtocolLedger(tmp_path/'test_claim',registration(),protocol_only=True);ledger.start(elapsed_wall_s=0)
    with pytest.raises(ValueError):ledger.finish(dict(valid=True,stopped=True,reference_ok=True,guard=False,outcome='FULL_SUCCESS',cycles=1,substeps=10,policy_calls=0,published_rows=1),elapsed_wall_s=1)
    assert ledger.data['status']=='closed'


def test_protocol_fixture_cannot_dispatch_real_backend(tmp_path):
    ledger=ProtocolLedger(tmp_path/'test_claim',registration(),protocol_only=True)
    with pytest.raises(PermissionError):execute_protocol(ledger,object(),object())


def test_external_ledger_mutation_rejected(tmp_path):
    ledger=ProtocolLedger(tmp_path/'test_claim',registration(),protocol_only=True)
    ledger.path.write_text('{}',encoding='utf8')
    with pytest.raises(ValueError):ledger.start(elapsed_wall_s=0)


def test_isolated_cli_inspection_and_unadmitted_rejection():
    import subprocess,sys
    from small_bound_profile import OUT,ROOT
    inspect=subprocess.run([sys.executable,'-I',str(OUT/'run_small_bound_pilot.py'),'--inspect'],cwd=ROOT,capture_output=True,text=True)
    assert inspect.returncode==0
    result=json.loads(inspect.stdout);assert result['actual_new_compute']==0
    blocked=subprocess.run([sys.executable,'-I',str(OUT/'run_small_bound_pilot.py'),'--execute'],cwd=ROOT,capture_output=True,text=True)
    assert blocked.returncode!=0 and 'PermissionError' in blocked.stderr


def test_same_authorization_cannot_claim_two_output_directories(tmp_path,monkeypatch):
    import types
    import run_small_bound_pilot as module
    monkeypatch.setattr(module,'CLAIM_DIRECTORY',tmp_path/'grant_claims',raising=False)
    receipt=dict(authorization_sha256='a'*64,qualification_sha256='b'*64,
        candidate_sha256='c'*64,profile_sha256=profile_digest(outer_contract()))
    admission=types.SimpleNamespace(verify=lambda *args:receipt)
    ProtocolLedger(tmp_path/'run_a',registration(),protocol_only=False,admission=admission)
    with pytest.raises(FileExistsError):
        ProtocolLedger(tmp_path/'run_b',registration(),protocol_only=False,admission=admission)
    assert not (tmp_path/'run_b').exists()


def reach_first_update(ledger):
    elapsed=0.
    while True:
        task=ledger.start(elapsed_wall_s=elapsed)
        if task['kind']=='update':return elapsed
        if task['kind']=='checkpoint_read':result=dict(verified=True,checkpoint=task['checkpoint'])
        else:
            stage=task['attempt']['stage']
            result=dict(valid=True,stopped=True,reference_ok=True,guard=False,outcome='FULL_SUCCESS',
                cycles=128,substeps=1280,policy_calls=0,published_rows=128 if stage in ('warmup','online') else 0,active_rows=128)
        elapsed+=.01;ledger.finish(result,elapsed_wall_s=elapsed)


def test_partial_update_actual_count_and_failure_are_preserved(tmp_path):
    ledger=ProtocolLedger(tmp_path/'test_claim',registration(),protocol_only=True)
    elapsed=reach_first_update(ledger)
    partial=dict(completed_batches=100,attempted_batches=101,error='interrupted protocol fixture')
    with pytest.raises(ValueError):ledger.finish(partial,elapsed_wall_s=elapsed+.01)
    saved=json.loads(ledger.path.read_text(encoding='utf8'))
    assert saved['status']=='closed' and saved['updates_completed']==100
    assert saved['updates_attempted']==101 and saved['results'][-1]['result']==partial


def test_backend_exception_without_counts_is_unknown_not_false_zero(tmp_path):
    ledger=ProtocolLedger(tmp_path/'test_claim',registration(),protocol_only=True)
    elapsed=reach_first_update(ledger)
    ledger.record_backend_failure(RuntimeError('fixture without counter snapshot'),elapsed_wall_s=elapsed+.01)
    saved=json.loads(ledger.path.read_text(encoding='utf8'))
    assert saved['status']=='closed' and saved['updates_completed'] is None and saved['updates_attempted'] is None
    assert saved['results'][-1]['result']['actual_counters_verified'] is False
