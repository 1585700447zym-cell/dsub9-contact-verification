"""Pure authorization/accounting counterexamples; no numerical library core."""
from pathlib import Path
from copy import deepcopy
import sys,json
import pytest
from numeric_contract import (OUT,LIMITS,digest,verify_numeric_authorization,
    NumericLedger,verify_runtime_files,write,profile_contract,profile_pin)


def candidate():
    return dict(status='PREPARED_NOT_AUTHORIZED',version='pc13_numeric_candidate_v1',
        profile_sha256=profile_pin(),outer_contract=profile_contract(),limits=LIMITS,
        training_admitted=False,dynamic_authorized=False)


def grant(c):
    return dict(version='pc13_numeric_authorization_v1',status='OPEN',explicit_user_authorized=True,
        scope='synthetic_numeric_only',candidate_sha256=digest(c),profile_sha256=profile_pin(),
        limits=LIMITS,prior_dynamic=208)


def test_absent_old_or_expanded_grant_rejected():
    c=candidate();g=grant(c);assert verify_numeric_authorization(c,g,digest(g))
    for bad in [None,dict(g,version='pc06'),dict(g,explicit_user_authorized=False),dict(g,scope='physical'),dict(g,limits={**LIMITS,'synthetic_update_batches':5})]:
        with pytest.raises((PermissionError,ValueError)):verify_numeric_authorization(c,bad,digest(bad))
    with pytest.raises(PermissionError):verify_numeric_authorization(c,g,'0'*64)


def test_global_claim_not_output_directory(tmp_path,monkeypatch):
    import numeric_contract as module
    monkeypatch.setattr(module,'CLAIMS',tmp_path/'claims')
    c=candidate();g=grant(c)
    NumericLedger.create(tmp_path/'run_a',c,g,digest(g))
    with pytest.raises(FileExistsError):NumericLedger.create(tmp_path/'run_b',c,g,digest(g))
    assert not (tmp_path/'run_b').exists()


def ledger(tmp_path,monkeypatch):
    import numeric_contract as module
    monkeypatch.setattr(module,'CLAIMS',tmp_path/'claims')
    c=candidate();g=grant(c);return NumericLedger.create(tmp_path/'run',c,g,digest(g))


def test_shared_parent_reader_limits_and_durable_before_work(tmp_path,monkeypatch):
    l=ledger(tmp_path,monkeypatch)
    for _ in range(3):
        token=l.reserve('parent','update');assert json.loads(l.path.read_text())['updates_attempted']==l.data['updates_attempted']
        l.complete(token)
    with pytest.raises(ValueError):l.reserve('parent','update')
    for _ in range(16):t=l.reserve('parent','forward');l.complete(t)
    l.ready_reader('test_request_pin')
    r=NumericLedger.load(l.path,l.candidate,l.grant,l.grant_pin);r.claim_reader('test_request_pin')
    token=r.reserve('reader','update');r.complete(token)
    assert r.data['updates_attempted']==r.data['updates_completed']==4
    with pytest.raises(ValueError):r.reserve('reader','update')


def test_reader_cannot_self_open_or_be_claimed_twice(tmp_path,monkeypatch):
    l=ledger(tmp_path,monkeypatch)
    with pytest.raises(PermissionError):l.reserve('reader','update')
    for _ in range(3):t=l.reserve('parent','update');l.complete(t)
    for _ in range(16):t=l.reserve('parent','forward');l.complete(t)
    l.ready_reader('request');l.claim_reader('request')
    with pytest.raises(FileExistsError):l.claim_reader('request')


def test_forward_counts_and_failure_close_all_unused(tmp_path,monkeypatch):
    l=ledger(tmp_path,monkeypatch)
    for _ in range(16):t=l.reserve('parent','forward');l.complete(t)
    with pytest.raises(ValueError):l.reserve('parent','forward')
    l.fail('fixture interruption')
    with pytest.raises(RuntimeError):l.reserve('parent','update')
    assert l.data['updates_attempted']==0 and l.data['unused_closed']['updates']==4


def test_unresolved_attempt_not_retried_and_files_tamper_fail(tmp_path,monkeypatch):
    l=ledger(tmp_path,monkeypatch);l.reserve('parent','update')
    with pytest.raises(RuntimeError):l.reserve('parent','update')
    write(l.path,dict(l.data,updates_attempted=0))
    with pytest.raises(ValueError):l.complete(l.data['active']['token'])


def test_runtime_file_pin_checked_without_loading_package(tmp_path):
    p=tmp_path/'torch_cpu.dll';p.write_bytes(b'pure fixture')
    import hashlib
    pins={str(p):hashlib.sha256(p.read_bytes()).hexdigest()}
    assert verify_runtime_files(pins)==1
    p.write_bytes(b'changed')
    with pytest.raises(ValueError):verify_runtime_files(pins)
    assert 'torch' not in sys.modules


def test_stage_helpers_resolve_to_pc13_not_sealed_pc12():
    # Pytest also prepends PC12's test directory during mixed-suite collection.
    # Verify the actual fresh -I worker bootstrap rather than that shared test path.
    import subprocess
    script="\n".join(["import sys",f"sys.path.insert(0,{str(OUT)!r})",'import numeric_contract',
        'import prepare_candidate,verify','from pathlib import Path',
        "assert Path(prepare_candidate.__file__).resolve()==numeric_contract.OUT/'prepare_candidate.py'",
        "assert Path(verify.__file__).resolve()==numeric_contract.OUT/'verify.py'",
        "assert 'torch' not in sys.modules"])
    result=subprocess.run([sys.executable,'-I','-c',script],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('boundary',['attempt','complete'])
def test_interrupted_projection_can_only_recover_to_closed(tmp_path,monkeypatch,boundary):
    import numeric_contract as module
    l=ledger(tmp_path,monkeypatch)
    if boundary=='complete':token=l.reserve('parent','update')
    with monkeypatch.context() as m:
        def fail_write(*args):raise OSError('injected ledger projection failure')
        m.setattr(module,'write',fail_write)
        with pytest.raises(OSError):
            if boundary=='attempt':l.reserve('parent','update')
            else:l.complete(token)
    recovered=module.NumericLedger.recover_failed(l.path,l.candidate,l.grant,l.grant_pin,'projection interrupted')
    assert recovered.data['status']=='closed' and recovered.data['updates_attempted']==1
    assert recovered.data['updates_completed']==int(boundary=='complete')
    assert recovered.data['unused_closed']['updates']==3
    with pytest.raises(RuntimeError):recovered.reserve('parent','update')
