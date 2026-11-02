"""Windows JSON replacement contention, with no physical or optimizer calls."""
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
import pytest


def api():return importlib.import_module('tools.learning.admitted_collection')


def denied(code=5):
    error=PermissionError(13,'fixture replacement denial');error.winerror=code
    return error


@pytest.mark.parametrize('code',[5,32,33])
def test_transient_windows_denial_replaces_same_staged_bytes(tmp_path,monkeypatch,code):
    m=api();path=tmp_path/'budget.json';m._write_json(path,{'completed':0})
    real=m.os.replace;attempts=[]
    def replace(source,target):
        attempts.append(Path(source).read_bytes())
        assert json.loads(path.read_text())=={'completed':0}
        if len(attempts)<=2:raise denied(code)
        return real(source,target)
    monkeypatch.setattr(m.os,'replace',replace)
    m._write_json(path,{'completed':1})
    assert json.loads(path.read_text())=={'completed':1}
    assert len(attempts)==3 and len(set(attempts))==1


def test_real_read_handle_release_recovers_without_rewriting(tmp_path,monkeypatch):
    import threading
    m=api();path=tmp_path/'actual.json';m._write_json(path,{'generation':0})
    held=path.open('rb');real=m.os.replace;attempts=[]
    release=threading.Event()
    def close_reader():
        assert release.wait(3)
        # Let the first failed replacement prove the actual OS conflict.
        held.close()
    thread=threading.Thread(target=close_reader);thread.start()
    def replace(source,target):
        try:return real(source,target)
        except PermissionError as exc:
            attempts.append(exc.winerror);release.set();raise
    monkeypatch.setattr(m.os,'replace',replace)
    try:m._write_json(path,{'generation':1})
    finally:
        release.set();thread.join(3);held.close()
    assert attempts and set(attempts)=={5} and not thread.is_alive()
    assert json.loads(path.read_text())=={'generation':1}


def test_persistent_real_lock_stops_with_old_and_staged_data(tmp_path,monkeypatch):
    m=api();path=tmp_path/'persistent.json';m._write_json(path,{'generation':0})
    # Use the actual lock, but omit wall-clock sleeps for the permanent-error test.
    waits=[];monkeypatch.setattr(m.time,'sleep',lambda delay:waits.append(delay))
    with path.open('rb'):
        with pytest.raises(PermissionError) as caught:m._write_json(path,{'generation':1})
    assert 1<=len(waits)<=8 and sum(waits)<=1.1
    assert any('replacement' in note for note in caught.value.__notes__)
    assert json.loads(path.read_text())=={'generation':0}
    assert json.loads(path.with_suffix('.json.tmp').read_text())=={'generation':1}


@pytest.mark.parametrize('kind',['ordinary_permission','disk_full','missing_directory'])
def test_nontransient_replace_errors_are_not_retried(tmp_path,monkeypatch,kind):
    m=api();path=tmp_path/'budget.json';m._write_json(path,{'old':True});calls=[]
    error={'ordinary_permission':PermissionError(13,'no Windows error code'),
           'disk_full':OSError(28,'disk full'),'missing_directory':FileNotFoundError(2,'missing')}[kind]
    def replace(*args):calls.append(1);raise error
    monkeypatch.setattr(m.os,'replace',replace)
    with pytest.raises(type(error)) as caught:m._write_json(path,{'new':True})
    assert caught.value is error and len(calls)==1 and json.loads(path.read_text())=={'old':True}


def test_flush_failure_never_replaces_destination(tmp_path,monkeypatch):
    m=api();path=tmp_path/'budget.json';m._write_json(path,{'old':True})
    def fail(*args):raise OSError('disk flush failed')
    monkeypatch.setattr(m.os,'fsync',fail)
    with pytest.raises(OSError,match='disk flush'):m._write_json(path,{'new':True})
    assert json.loads(path.read_text())=={'old':True}


@pytest.mark.parametrize('boundary',['before','after','persistent_after'])
def test_budget_write_retry_never_repeats_optimizer_or_hides_failure(tmp_path,monkeypatch,boundary):
    import numpy as np
    from tests.learning.test_bounded_checkpoint import SyntheticPermit
    from tests.learning.test_bounded_contact import receipt
    from tools.learning.bounded_contact import BoundedCollection
    m=api();chain=BoundedCollection(admission=SyntheticPermit(),output=tmp_path/'episodes')
    for i in range(4):chain.budget.record(receipt(i))
    sample=SimpleNamespace(actor=None,critic=None,targets=None,mask=np.zeros(32,dtype=bool),indices=[('fixture',0)]*32)
    monkeypatch.setattr(chain.index,'sample',lambda *a,**kw:sample)
    updates=[]
    def fake_update(*args,**kwargs):
        updates.append(1)
        for key in chain.updater.counts:chain.updater.counts[key]+=1
        return dict(critic_batches=len(updates))
    monkeypatch.setattr(chain.updater,'update',fake_update)
    real=m.os.replace;rejections=[]
    def replace(source,target):
        if Path(target).name=='update_budget.json':
            record=json.loads(Path(source).read_text())
            at_boundary=record['completed']==(0 if boundary=='before' else 1)
            if at_boundary and (not rejections or boundary=='persistent_after'):
                rejections.append(record);raise denied()
        return real(source,target)
    monkeypatch.setattr(m.os,'replace',replace)
    if boundary=='persistent_after':
        monkeypatch.setattr(m.time,'sleep',lambda delay:None)
        with pytest.raises(PermissionError):chain.update(1)
        assert chain.failed
        with pytest.raises(RuntimeError):chain.update(1)
        evidence=json.loads((tmp_path/'episodes/failure.json').read_text())
        assert evidence['updates']['critic']==1 and len(evidence['history'])==1
    else:
        chain.update(1)
        assert not chain.failed
        record=json.loads((tmp_path/'episodes/update_budget.json').read_text())
        assert record['attempted']==record['completed']==1
    assert rejections and len(updates)==1 and chain.update_attempts==chain.budget.completed==1
