import importlib,json
from types import SimpleNamespace
import pytest

def api():return importlib.import_module('tools.validation.run_v4_continuation_preflight')

def test_exact_one_pulse_and_missed_or_wrong_phase_fail_closed():
    m=api();s=SimpleNamespace(time_s=9.146,controller_state={'phase':'SEARCH'},residual_enabled=True)
    assert m.boundary_action(s,False)==[1,-1,0,0]
    assert m.boundary_action(s,True)==[0]*4
    s.time_s=9.148
    with pytest.raises(RuntimeError):m.boundary_action(s,False)
    s.time_s=9.146;s.residual_enabled=False
    with pytest.raises(RuntimeError):m.boundary_action(s,False)

def test_one_claim_cannot_retry_or_extend_budget(tmp_path):
    m=api();r=tmp_path/'run';ledger=m.claim_run(r)
    assert ledger['max_new_episodes']==1 and ledger['prior_cumulative']==139 and ledger['cumulative_limit']==140
    with pytest.raises(FileExistsError):m.claim_run(r)

def test_stop_before_entry_does_not_construct_environment(tmp_path,monkeypatch):
    m=api();(tmp_path/'STOP').touch();monkeypatch.setattr(m,'verify_inputs',lambda _: {})
    monkeypatch.setattr(m,'run_episode',lambda *args:pytest.fail('STOP still constructed an episode'))
    ledger=m.execute(tmp_path)
    assert ledger['status']=='controlled_stop' and ledger['episodes']==[] and ledger['unused_closed']==1

def test_whole_lifecycle_exception_closes_ledger(tmp_path,monkeypatch):
    m=api();monkeypatch.setattr(m,'verify_inputs',lambda _: {})
    def fail(*args):raise RuntimeError('Injected lifecycle failure')
    monkeypatch.setattr(m,'run_episode',fail)
    with pytest.raises(RuntimeError):m.execute(tmp_path)
    ledger=json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf8'))
    assert ledger['status']=='error' and ledger['unused_closed']==1

def test_changed_input_is_never_constructed_or_run(tmp_path,monkeypatch):
    m=api()
    def fail(*args):raise RuntimeError('changed frozen input')
    monkeypatch.setattr(m,'verify_inputs',fail)
    monkeypatch.setattr(m,'run_episode',lambda *args:pytest.fail('Changed source ran'))
    with pytest.raises(RuntimeError):m.execute(tmp_path)
    ledger=json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf8'))
    assert ledger['status']=='error' and ledger['episodes']==[] and ledger['unused_closed']==1
