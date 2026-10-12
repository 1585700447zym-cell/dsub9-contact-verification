"""Protocol tests: real disk ledger, no model/Adam/physics calls permitted."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
import pytest

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
PIN='a'*64;AUTH='b'*64
NAMES=('x_pos_100','x_neg_100','y_pos_100','y_neg_100')

class MissingImplementation:
    def __getattr__(self,name):
        raise AssertionError('Missing independent evaluation implementation: '+name)

@pytest.fixture
def api():
    if not (HERE/'evaluation_contract.py').is_file():return MissingImplementation()
    return importlib.import_module('evaluation_contract')

def result(**changes):
    r=dict(completed=True,success=False,simulation_valid=True,physical_stopped=True,
           guard_hit=False,cycles=10,actor_states=10)
    r.update(changes);return r

def test_four_ordered_attempts_complete_without_training(api,tmp_path):
    ledger=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH)
    with pytest.raises(RuntimeError):ledger.start('x_neg_100')
    for name in NAMES:
        ledger.start(name)
        disk=json.loads(ledger.path.read_text())
        assert disk['attempts'][-1]['actor_states_reserved']==13000
        assert disk['active']==len(disk['attempts'])-1
        ledger.finish(result())
    ledger.complete()
    assert api.Ledger.load(ledger.path,PIN,AUTH).accounting()==dict(
        previous_dynamic=58,new_dynamic_starts=4,cumulative_dynamic=62,cumulative_dynamic_cap=62,
        unused_new_dynamic=0,actor_states_reserved=52000,actor_states_confirmed=40,
        training_batches=0,extra_diagnostic_states=0,independent_test=0,
        old_unused_consumed=0,status='complete')
    with pytest.raises(RuntimeError):ledger.start('x_pos_100')

@pytest.mark.parametrize('changes,status',[
    ({'guard_hit':True},'stopped'),({'simulation_valid':False},'failed'),
    ({'physical_stopped':False},'failed')])
def test_stop_outcome_prevents_remaining_points(api,tmp_path,changes,status):
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH);l.start(NAMES[0]);l.finish(result(**changes))
    assert l.state['status']==status
    with pytest.raises(RuntimeError):l.start(NAMES[1])
    with pytest.raises(RuntimeError):l.complete()

def test_stale_writer_and_failed_write_cannot_reset_budget(api,tmp_path,monkeypatch):
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH);stale=api.Ledger.load(l.path,PIN,AUTH)
    l.start(NAMES[0])
    with pytest.raises(RuntimeError):stale.start(NAMES[0])
    before=l.path.read_bytes()
    def fail(*a):raise PermissionError('injected persistent write failure')
    monkeypatch.setattr(api,'write',fail)
    with pytest.raises(PermissionError):l.finish(result())
    assert l.path.read_bytes()==before
    with pytest.raises(RuntimeError):l.finish(result())

def test_active_failed_start_is_charged_and_not_retryable(api,tmp_path):
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH);l.start(NAMES[0]);l.fail('reset failure')
    assert l.accounting()['new_dynamic_starts']==1
    assert l.accounting()['actor_states_reserved']==13000
    assert l.state['active'] is None and l.state['attempts'][0]['status']=='failed'
    with pytest.raises(RuntimeError):l.start(NAMES[0])
    with pytest.raises(FileExistsError):api.Ledger.create(l.path,PIN,AUTH)

@pytest.mark.parametrize('mutation',[
    lambda s:s.update(status='complete'),
    lambda s:s['attempts'][0].update(case='y_pos_100'),
    lambda s:s['attempts'][0].update(actor_states_reserved=13001),
    lambda s:s['attempts'][0]['result'].update(actor_states=13001),
    lambda s:s.update(active=0),
    lambda s:s.update(candidate_sha256='z'*64),
])
def test_malformed_restored_budget_rejected(api,tmp_path,mutation):
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH);l.start(NAMES[0]);l.finish(result())
    state=deepcopy(l.state);mutation(state);l.path.write_text(json.dumps(state))
    with pytest.raises(ValueError):api.Ledger.load(l.path,PIN,AUTH)

@pytest.mark.parametrize('changes',[
    {'completed':False},{'success':1},{'cycles':13001},{'actor_states':9},
    {'cycles':0},{'success':True,'guard_hit':True},
])
def test_incomplete_or_inconsistent_outcome_refused(api,tmp_path,changes):
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH);l.start(NAMES[0])
    before=l.path.read_bytes()
    with pytest.raises(ValueError):l.finish(result(**changes))
    assert l.path.read_bytes()==before

def test_live_guard_blocks_before_reservation(api,tmp_path):
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH)
    def gone():raise RuntimeError('registered parent gone')
    l.live_guard=gone
    with pytest.raises(RuntimeError,match='gone'):l.start(NAMES[0])
    assert json.loads(l.path.read_text())['attempts']==[]

def test_authorization_requires_exact_scope_and_binding(api):
    r=dict(version='frozen_B_evaluation_authorization_v1',approved=True,user_confirmation='继续',
           binding_sha256=PIN,scope=api.scope())
    api.validate_authorization(r,PIN)
    for key,value in [('approved',False),('user_confirmation',''),('binding_sha256',AUTH)]:
        bad=deepcopy(r);bad[key]=value
        with pytest.raises(ValueError):api.validate_authorization(bad,PIN)
    for key,value in [('dynamic_cap',5),('training_batches',1),('previous_dynamic',0),('actor_state_cap',52001)]:
        bad=deepcopy(r);bad['scope'][key]=value
        with pytest.raises(ValueError):api.validate_authorization(bad,PIN)

@pytest.fixture
def runner():
    if not (HERE/'run_evaluation.py').is_file():return MissingImplementation()
    return importlib.import_module('run_evaluation')

def test_missing_authorization_stops_before_runtime(runner,monkeypatch,tmp_path):
    monkeypatch.setattr(runner,'HERE',tmp_path)
    monkeypatch.setattr(runner,'select_runtime',lambda:pytest.fail('runtime before authorization'))
    with pytest.raises((ValueError,FileNotFoundError)):runner.main(['--binding-sha256',PIN,'--authorization-sha256',AUTH])
    assert not (tmp_path/'run').exists() and not (tmp_path/'started.json').exists()

def test_stop_marker_blocks_before_parent_probe(runner,monkeypatch,tmp_path):
    (tmp_path/'started.json').write_text(json.dumps(dict(supervisor_pid=123,wall_timestamp=1)))
    (tmp_path/'stop_requested.json').write_text('{}')
    monkeypatch.setattr(runner,'HERE',tmp_path)
    from tools.validation import process_parent
    monkeypatch.setattr(process_parent,'require_registered_parent',lambda *a:pytest.fail('parent probe after stop'))
    with pytest.raises(RuntimeError,match='stop'):runner.live_guard()()

def test_predict_reservation_precedes_single_state_inference(runner,api,tmp_path):
    import numpy as np
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH)
    class Updater:
        def predict(self,obs,deterministic=True):return np.zeros(4),None
    u=Updater();meter=runner.PredictionMeter(u,l)
    with pytest.raises(RuntimeError):meter.predict(np.zeros(120))
    l.start(NAMES[0]);meter.begin()
    assert meter.predict(np.zeros(120))[0].shape==(4,)
    assert meter.count==1
    with pytest.raises(ValueError):meter.predict(np.zeros((2,120)))
    with pytest.raises(ValueError):meter.predict(np.zeros(120),deterministic=False)
    meter.count=13000
    with pytest.raises(RuntimeError):meter.predict(np.zeros(120))

def test_aborted_tail_cannot_exceed_registered_cycle_limit(runner):
    cls=runner.collector_type()
    class Session:
        done=False
        class Env:
            class Data:time=25.998
            data=Data()
        env=Env()
        def start_external_tail(self):pass
        def advance_cycle(self,action):self.env.data.time+=.002
    c=object.__new__(cls);c.session=Session()
    with pytest.raises(RuntimeError,match='tail'):c._stop_tail()
    assert abs(c.session.env.data.time-26)<1e-9

def test_unconfirmed_cleanup_preserves_ledger(runner,monkeypatch,tmp_path):
    monkeypatch.setattr(runner,'HERE',tmp_path);(tmp_path/'run').mkdir()
    ledger=tmp_path/'run/ledger.json';ledger.write_text('{"active":0}')
    (tmp_path/'process_exit.json').write_text(json.dumps(dict(status='supervisor_error',worker_stopped=False,cleanup_error='injected')))
    runner.finalize_exception(PIN,AUTH,RuntimeError('cleanup failure'))
    assert ledger.read_text()=='{"active":0}'
    assert json.loads((tmp_path/'exit_classification.json').read_text())['worker_stop_confirmed'] is False
    assert (tmp_path/'stop_requested.json').exists()

def test_stopped_ledger_cannot_be_relabelled_healthy(api,tmp_path):
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH);l.start(NAMES[0]);l.finish(result(guard_hit=True))
    state=deepcopy(l.state);state['status']='healthy';l.path.write_text(json.dumps(state))
    with pytest.raises(ValueError):api.Ledger.load(l.path,PIN,AUTH)

def test_foreign_authorization_cannot_restore_ledger(api,tmp_path):
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH)
    with pytest.raises(ValueError):api.Ledger.load(l.path,PIN,'c'*64)

def test_failed_forward_is_counted_before_inference(runner,api,tmp_path):
    import numpy as np
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH);l.start(NAMES[0])
    class Broken:
        def predict(self,*a,**k):raise RuntimeError('injected policy failure')
    meter=runner.PredictionMeter(Broken(),l);meter.begin()
    with pytest.raises(RuntimeError,match='policy failure'):meter.predict(np.zeros(120))
    assert meter.count==1 and l.accounting()['actor_states_reserved']==13000

def test_changed_disk_budget_blocks_next_forward(runner,api,tmp_path):
    import numpy as np
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH);l.start(NAMES[0])
    class Never:
        def predict(self,*a,**k):pytest.fail('forward after ownership changed')
    meter=runner.PredictionMeter(Never(),l);meter.begin()
    changed=deepcopy(l.state);changed['status']='failed';l.path.write_text(json.dumps(changed))
    with pytest.raises(RuntimeError):meter.predict(np.zeros(120))
    assert meter.count==0

def test_completed_four_points_cannot_invoke_learning(api,tmp_path):
    l=api.Ledger.create(tmp_path/'ledger.json',PIN,AUTH)
    for name in NAMES:l.start(name);l.finish(result(success=True))
    l.complete()
    with pytest.raises(RuntimeError):l.start(NAMES[0])
    assert l.accounting()['training_batches']==0
