"""Resumption binds new evidence without altering the approved learning cycle."""
import importlib
import json
import pytest


def modules():
    return (importlib.import_module('tools.learning.resumed_force_cycle'),
            importlib.import_module('tools.validation.run_resumed_force_cycle'))


def test_repair_and_failed_attempt_remain_verifiable():
    m,_=modules()
    m.verify_parent()
    assert m.DELIVERY!=m.PREVIOUS_ATTEMPT
    assert m.proposed_budget()['new_dynamic_cap']==32
    assert m.proposed_budget()['cumulative_dynamic_cap']==68


@pytest.mark.parametrize('restore',[False,True])
def test_child_routes_to_new_qualified_entry(restore):
    _,entry=modules()
    cmd=entry.child_command('candidate','authorization',restore=restore)
    assert cmd[cmd.index('-m')+1]=='tools.validation.run_resumed_force_cycle'
    assert cmd[-1]==('--restore' if restore else '--worker')
    assert cmd[cmd.index('--candidate-sha256')+1]=='candidate'
    assert cmd[cmd.index('--authorization-sha256')+1]=='authorization'


def test_bound_runner_restored_even_on_error():
    m,entry=modules()
    from tools.validation import run_force_failure_cycle as old
    before=(old.DELIVERY,old.ForceAdmission,old.verify_candidate,old.child_command)
    with pytest.raises(RuntimeError):
        with entry.bound_runner() as runner:
            assert runner.DELIVERY==m.DELIVERY
            assert runner.ForceAdmission is m.ForceAdmission
            assert runner.verify_candidate is m.verify_candidate
            assert runner.child_command is entry.child_command
            raise RuntimeError('fixture')
    assert before==(old.DELIVERY,old.ForceAdmission,old.verify_candidate,old.child_command)


def test_missing_authorization_rejected_before_candidate(tmp_path,monkeypatch):
    m,_=modules();monkeypatch.setattr(m,'DELIVERY',tmp_path)
    with pytest.raises(ValueError,match='authorization'):
        m.ForceAdmission(tmp_path/'candidate.json',expected_digest='x',authorization_digest=None)


def test_old_authorization_cannot_authorize_new_candidate(tmp_path,monkeypatch):
    m,_=modules();monkeypatch.setattr(m,'DELIVERY',tmp_path)
    auth=m.read(m.PREVIOUS_ATTEMPT/'authorization.json')
    path=tmp_path/'authorization.json';path.write_text(json.dumps(auth),encoding='utf-8')
    with pytest.raises(ValueError,match='authorization'):
        m.ForceAdmission(tmp_path/'candidate.json',expected_digest='new',authorization_digest=m.digest(path))


def test_candidate_wrong_path_rejected():
    m,_=modules()
    with pytest.raises(ValueError,match='path or pin'):
        m.verify_candidate(m.PREVIOUS_ATTEMPT/'candidate.json',m.digest(m.PREVIOUS_ATTEMPT/'candidate.json'))


def test_repair_pin_tampering_rejected(monkeypatch):
    m,_=modules();monkeypatch.setattr(m,'REPAIR_PIN','0'*64)
    with pytest.raises(ValueError):m.verify_parent()


def test_real_resumed_wrapper_parent_chain(tmp_path):
    import subprocess,sys
    m,_=modules()
    result=subprocess.run([sys.executable,'-X','utf8','-B',str(m.DELIVERY/'process_probe.py'),
        str(tmp_path),'supervisor','normal'],cwd=m.ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    report=m.read(tmp_path/'probe_report.json')
    assert report['worker_exit']==0 and not any(report['forbidden_call_counts'].values())
    for role in ('worker','restore'):
        assert m.read(tmp_path/(role+'_identity.json'))['route']=='windows_venv_launcher'
        assert (tmp_path/(role+'_claim.json')).exists()
