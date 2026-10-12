import importlib
import json
import subprocess
import sys
import pytest

def modules():
    return (importlib.import_module('tools.learning.atomic_repaired_cycle'),
            importlib.import_module('tools.validation.run_atomic_repaired_cycle'))

def test_parent_preserved():
    m,_=modules();m.verify_parent()
    assert m.proposed_budget()['previous_dynamic_starts']==44
    assert m.proposed_budget()['cumulative_dynamic_cap']==76

@pytest.mark.parametrize('restore',[False,True])
def test_child_route(restore):
    _,e=modules();c=e.child_command('candidate','auth',restore=restore)
    assert c[c.index('-m')+1]=='tools.validation.run_atomic_repaired_cycle'
    assert c[-1]==('--restore' if restore else '--worker')

def test_binding_restored():
    m,e=modules();r=e.runner
    names=('DELIVERY','ForceAdmission','ForceLedger','accounting','verify_candidate','child_command','reuse_baseline')
    before=[getattr(r,n) for n in names]
    with pytest.raises(RuntimeError):
        with e.bound_runner() as r:
            assert r.ForceLedger is m.ForceLedger and r.accounting is m.accounting
            assert r.DELIVERY==m.DELIVERY and r.ForceAdmission is m.ForceAdmission
            assert r.reuse_baseline is m.reuse_baseline
            raise RuntimeError('test')
    assert before==[getattr(r,n) for n in names]

def test_probe_is_bound_and_new_baseline_used(tmp_path,monkeypatch):
    m,_=modules();sources=m.cycle_sources()
    probe=m.DELIVERY/'process_probe.py'
    assert sources[probe.relative_to(m.ROOT).as_posix()]==m.digest(probe)
    monkeypatch.setattr(m,'DELIVERY',tmp_path)
    receipt=dict(passed=True,input_sha256={probe.relative_to(m.ROOT).as_posix():m.digest(probe)},results=[dict(fixture='new-package')])
    m.write(tmp_path/'baseline_reuse.json',receipt)
    run=tmp_path/'run';run.mkdir();m.reuse_baseline(run)
    assert m.read(run/'baseline/reuse.json')==receipt

def test_ledger_counts_and_order(tmp_path):
    m,_=modules();l=m.ForceLedger(tmp_path/'ledger.json')
    with pytest.raises(RuntimeError):l.start('training','early')
    l.start('initial','first')
    assert m.read(tmp_path/'cumulative_budget.json')['cumulative_dynamic_starts']==45
    assert m.accounting(dict(dynamic_starts=32,attempts=[{}]*32))['cumulative_dynamic_starts']==76
    with pytest.raises(ValueError):m.accounting(dict(dynamic_starts=33,attempts=[{}]*33))

def test_missing_auth(tmp_path,monkeypatch):
    m,_=modules();monkeypatch.setattr(m,'DELIVERY',tmp_path)
    with pytest.raises(ValueError,match='authorization'):
        m.ForceAdmission(tmp_path/'candidate.json',expected_digest='x',authorization_digest=None)

def test_old_auth_budget_rejected():
    m,_=modules();a=m.read(m.PREVIOUS_ATTEMPT/'authorization.json')
    with pytest.raises(ValueError):m.validate_authorization(a,a['candidate_sha256'])

def test_wrong_candidate_path():
    m,_=modules()
    with pytest.raises(ValueError):m.verify_candidate(m.PREVIOUS_ATTEMPT/'candidate.json',m.digest(m.PREVIOUS_ATTEMPT/'candidate.json'))

def test_repair_pin_rejected(monkeypatch):
    m,_=modules();monkeypatch.setattr(m,'REPAIR_PIN','0'*64)
    with pytest.raises(ValueError):m.verify_parent()

def test_real_wrapper_parent_chain(tmp_path):
    m,_=modules()
    r=subprocess.run([sys.executable,'-X','utf8','-B',str(m.DELIVERY/'process_probe.py'),str(tmp_path),'supervisor','normal'],cwd=m.ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert r.returncode==0,r.stdout+r.stderr
    report=m.read(tmp_path/'probe_report.json')
    assert report['worker_exit']==0 and not any(report['forbidden_call_counts'].values())
    for role in ('worker','restore'):
        assert m.read(tmp_path/(role+'_identity.json'))['route']=='windows_venv_launcher'
        assert (tmp_path/(role+'_claim.json')).exists()
