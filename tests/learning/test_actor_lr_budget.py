from copy import deepcopy
import importlib
import json
import pytest


def module():
    try:return importlib.import_module('tools.learning.actor_lr_budget')
    except ModuleNotFoundError as exc:pytest.fail('Comparison budget missing: '+str(exc))


def ledger(tmp_path):
    return module().ComparisonLedger.create(tmp_path/'ledger.json','a'*64,'b'*64)


def finish_update(l,branch,n):
    token=l.reserve('formal',branch,f'batch_{n:03d}')
    l.finish(token,dict(completed=True))


def enter_diagnostics(l):
    l.complete_validation('c'*64)
    # These are protocol stand-ins; no updater/network exists.
    for i in range(500):finish_update(l,'A',i)
    l.reproduce_a('d'*64)
    for i in range(500):finish_update(l,'B',i)
    l.freeze_b('e'*64)


def test_creation_is_exclusive_and_authorization_bound(tmp_path):
    l=ledger(tmp_path)
    with pytest.raises(FileExistsError):ledger(tmp_path)
    with pytest.raises(ValueError):module().ComparisonLedger.load(l.path,'a'*64,'c'*64)


@pytest.mark.parametrize('kind,branch,identity',[('formal','A','batch_000'),('formal','B','batch_000'),
    ('diagnostic','initial','states'),('physical','A','x_pos_100')])
def test_real_work_gates_closed_before_validation(tmp_path,kind,branch,identity):
    l=ledger(tmp_path)
    with pytest.raises(RuntimeError):l.reserve(kind,branch,identity)
    assert l.state['attempts']==[]


def test_reservation_is_durable_before_work_and_blocks_reentry(tmp_path):
    l=ledger(tmp_path)
    token=l.reserve('synthetic','shared','active_A')
    disk=json.loads(l.path.read_text(encoding='utf-8'))
    assert disk['attempts'][0]['status']=='started' and disk['active']==0
    with pytest.raises(RuntimeError):l.reserve('synthetic','shared','active_B')
    l.finish(token,dict(completed=True))
    with pytest.raises(RuntimeError):l.reserve('synthetic','shared','active_A')


@pytest.mark.parametrize('kind,cap',[('synthetic',16),('test_forward',128)])
def test_validation_caps_and_invalid_counts_are_refused(tmp_path,kind,cap):
    l=ledger(tmp_path)
    token=l.reserve(kind,'shared','limit',units=cap)
    l.finish(token,dict(completed=True))
    with pytest.raises(RuntimeError):l.reserve(kind,'shared','extra')
    for n in (0,-1,True,1.5):
        with pytest.raises((RuntimeError,ValueError)):l.reserve(kind,'shared','invalid',units=n)


def test_b_and_evaluation_cannot_bypass_exact_a_reproduction_gate(tmp_path):
    l=ledger(tmp_path);l.complete_validation('c'*64)
    with pytest.raises(RuntimeError):l.reserve('formal','B','batch_000')
    with pytest.raises(RuntimeError):l.reproduce_a('d'*64)
    with pytest.raises(RuntimeError):l.reserve('physical','A','x_pos_100')


def test_failed_attempt_remains_charged_and_cannot_retry(tmp_path):
    l=ledger(tmp_path);l.reserve('synthetic','shared','failure')
    l.fail('injected failure')
    disk=module().ComparisonLedger.load(l.path,'a'*64,'b'*64)
    assert len(disk.state['attempts'])==1 and disk.state['status']=='failed'
    with pytest.raises(RuntimeError):disk.reserve('synthetic','shared','again')


def test_write_failure_prevents_any_further_reservation(tmp_path,monkeypatch):
    m=module();l=ledger(tmp_path)
    def failure(*args):raise PermissionError('locked')
    monkeypatch.setattr(m,'write',failure)
    with pytest.raises(PermissionError):l.reserve('synthetic','shared','will_not_run')
    with pytest.raises(RuntimeError):l.reserve('synthetic','shared','retry_refused')


@pytest.mark.parametrize('phase',['A_training','B_training','diagnostic','evaluation','complete'])
def test_empty_ledger_cannot_claim_later_phase(tmp_path,phase):
    l=ledger(tmp_path);raw=deepcopy(l.state);raw['phase']=phase
    if phase=='complete':raw['status']='complete'
    l.path.write_text(json.dumps(raw),encoding='utf-8')
    with pytest.raises(ValueError):module().ComparisonLedger.load(l.path,'a'*64,'b'*64)


def test_formal_bulk_row_cannot_replace_500_transactions(tmp_path):
    l=ledger(tmp_path);raw=deepcopy(l.state)
    raw.update(phase='A_training',gates=dict(real_validation='c'*64),attempts=[
        dict(kind='formal',branch='A',identity='batch_000',units=500,status='finished',result=dict(completed=True))])
    l.path.write_text(json.dumps(raw),encoding='utf-8')
    with pytest.raises(ValueError):module().ComparisonLedger.load(l.path,'a'*64,'b'*64)


def test_finished_formal_cannot_revert_to_validation(tmp_path):
    l=ledger(tmp_path);l.complete_validation('c'*64);finish_update(l,'A',0)
    raw=deepcopy(l.state);raw['phase']='validation';l.path.write_text(json.dumps(raw),encoding='utf-8')
    with pytest.raises(ValueError):module().ComparisonLedger.load(l.path,'a'*64,'b'*64)


def test_dead_supervisor_guard_prevents_reservation(tmp_path):
    l=ledger(tmp_path)
    def dead():raise RuntimeError('supervisor gone')
    l.set_execution_guard(dead)
    with pytest.raises(RuntimeError,match='supervisor gone'):l.reserve('synthetic','shared','never_compute')
    assert l.state['attempts']==[]


def test_external_ledger_write_prevents_stale_owner_overwrite(tmp_path):
    l=ledger(tmp_path);l.set_execution_guard(lambda:None)
    raw=deepcopy(l.state);raw.update(status='failed',phase='failed');l.path.write_text(json.dumps(raw),encoding='utf-8')
    with pytest.raises(RuntimeError,match='durable owner'):l.reserve('synthetic','shared','never_compute')
    assert json.loads(l.path.read_text(encoding='utf-8'))==raw


@pytest.mark.parametrize('bad_value',[True,-1,1])
def test_corrupt_active_state_rejected_on_load(tmp_path,bad_value):
    l=ledger(tmp_path);raw=deepcopy(l.state);raw['active']=bad_value
    l.path.write_text(json.dumps(raw),encoding='utf-8')
    with pytest.raises(ValueError):module().ComparisonLedger.load(l.path,'a'*64,'b'*64)


@pytest.mark.parametrize('cause',['contact','motion','invalid','unstopped'])
def test_any_evaluation_guard_or_invalid_outcome_stops_whole_comparison(tmp_path,monkeypatch,cause):
    m=module();l=ledger(tmp_path)
    # Keep the real state machine, but avoid 1000 repeated disk flushes here.
    writes=[]
    monkeypatch.setattr(m,'write',lambda path,state:writes.append(deepcopy(state)))
    enter_diagnostics(l)
    for role in ('initial','A','B'):
        token=l.reserve('diagnostic',role,'states',units=256);l.finish(token,dict(completed=True))
    l.begin_evaluation(dict(A='d'*64,B='e'*64),'f'*64)
    token=l.reserve('physical','A','x_pos_100')
    l.finish(token,dict(completed=True,simulation_valid=cause!='invalid',physical_stopped=cause!='unstopped',
        guard_hit=cause in ('contact','motion'),task_outcome='TASK_FAILURE',success=False))
    assert l.state['status'] in ('stopped','failed')
    assert l.state['attempts'][-1]['status']=='finished' and l.state['active'] is None
    with pytest.raises(RuntimeError):l.reserve('physical','A','x_neg_100')
    assert len([r for r in l.state['attempts'] if r['kind']=='physical'])==1
