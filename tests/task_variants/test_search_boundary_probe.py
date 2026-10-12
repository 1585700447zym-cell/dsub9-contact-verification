"""The new development runner must not retry or construct after STOP/fault."""
from pathlib import Path
import importlib.util, json
import pytest


def api():
    path = Path(__file__).resolve().parents[2]/'deliverables/paper_comparison/search_boundary_fix_20261006/probe.py'
    spec = importlib.util.spec_from_file_location('boundary_development_probe', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_stop_before_first_attempt_closes_three_unused_and_never_constructs(tmp_path, monkeypatch):
    m = api(); monkeypatch.setattr(m, 'OUT', tmp_path)
    monkeypatch.setattr(m, 'verify', lambda: {})
    monkeypatch.setattr(m, 'run_episode', lambda *a: pytest.fail('STOP constructed an episode'))
    (tmp_path/'STOP').touch(); m.execute()
    ledger = json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf8'))
    assert ledger['status']=='controlled_stop' and ledger['episodes']==[] and ledger['unused_closed']==3
    with pytest.raises(FileExistsError): m.execute()


def test_common_error_closes_remaining_budget_and_never_retries(tmp_path, monkeypatch):
    m = api(); monkeypatch.setattr(m, 'OUT', tmp_path)
    monkeypatch.setattr(m, 'verify', lambda: {})
    seen=[]
    def fail(config, ledger, spec):
        seen.append(spec['id']); ledger['episodes'].append(dict(id=spec['id'],status='error'))
        raise RuntimeError('Injected common failure')
    monkeypatch.setattr(m, 'run_episode', fail)
    with pytest.raises(RuntimeError, match='Injected common'): m.execute()
    ledger=json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf8'))
    assert ledger['status']=='error' and ledger['unused_closed']==2 and seen==[m.SPECS[0]['id']]


def test_failed_stop_or_guard_closes_later_registered_attempts(tmp_path, monkeypatch):
    m=api(); monkeypatch.setattr(m,'OUT',tmp_path); monkeypatch.setattr(m,'verify',lambda:{})
    seen=[]
    def rejected(config,ledger,spec):
        seen.append(spec['id']);ledger['episodes'].append(dict(id=spec['id'],status='finished',verification_passed=False))
        return False
    monkeypatch.setattr(m,'run_episode',rejected);m.execute()
    ledger=json.loads((tmp_path/'run/ledger.json').read_text(encoding='utf8'))
    assert ledger['status']=='controlled_stop' and ledger['unused_closed']==2 and len(seen)==1

