"""Fail-closed runtime selection; fake packages only, no native calls."""
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.learning import runtime as rt


def fixture_record(tmp_path):
    package=tmp_path/'package'; (package/'mujoco').mkdir(parents=True)
    init=package/'mujoco/__init__.py'; init.write_text('# fake')
    dll=package/'mujoco/mujoco.dll'; dll.write_bytes(b'native')
    files={p.relative_to(package).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in (init,dll)}
    record=tmp_path/'runtime.json'
    record.write_text(json.dumps(dict(version='native313_repair_runtime_v1',module_file=str(init),files=files)))
    return record,hashlib.sha256(record.read_bytes()).hexdigest(),package


@pytest.fixture(autouse=True)
def isolated_selection(monkeypatch):
    monkeypatch.setattr(rt,'_selection',None,raising=False)
    monkeypatch.delitem(rt.sys.modules,'mujoco',raising=False)


def test_explicit_pinned_selection_verifies_before_import(tmp_path,monkeypatch):
    record,pin,package=fixture_record(tmp_path)
    fake=SimpleNamespace(__version__='3.13.0',__file__=str(package/'mujoco/__init__.py'))
    monkeypatch.setattr(rt.importlib,'import_module',lambda name:fake)
    rt.select_runtime(record,expected_digest=pin)
    assert rt.active_package()==package.resolve()
    assert rt.verify_runtime(package)['compatibility_record_sha256']==pin


@pytest.mark.parametrize('problem',['pin','dll','extra','traversal'])
def test_record_or_package_tampering_refused_before_native_import(tmp_path,monkeypatch,problem):
    record,pin,package=fixture_record(tmp_path)
    if problem=='pin': pin='0'*64
    elif problem=='dll': (package/'mujoco/mujoco.dll').write_bytes(b'changed')
    elif problem=='extra': (package/'mujoco/injected.py').write_text('')
    else:
        value=json.loads(record.read_text()); value['files']['../escape.dll']='0'*64
        record.write_text(json.dumps(value)); pin=hashlib.sha256(record.read_bytes()).hexdigest()
    monkeypatch.setattr(rt.importlib,'import_module',lambda name:pytest.fail('native imported before rejection'))
    with pytest.raises(RuntimeError): rt.select_runtime(record,expected_digest=pin)


def test_wrong_loaded_path_and_runtime_switch_refused(tmp_path,monkeypatch):
    record,pin,package=fixture_record(tmp_path)
    monkeypatch.setitem(rt.sys.modules,'mujoco',SimpleNamespace(__version__='3.13.0',__file__='wrong'))
    with pytest.raises(RuntimeError): rt.select_runtime(record,expected_digest=pin)
    monkeypatch.delitem(rt.sys.modules,'mujoco')
    rt.select_runtime(record,expected_digest=pin)
    with pytest.raises(RuntimeError): rt.verify_runtime(tmp_path/'other')
    other,other_pin,_=fixture_record(tmp_path/'other')
    with pytest.raises(RuntimeError): rt.select_runtime(other,expected_digest=other_pin)


def test_changed_record_rejected_on_later_verification(tmp_path):
    record,pin,package=fixture_record(tmp_path)
    rt.select_runtime(record,expected_digest=pin)
    record.write_text('{}')
    with pytest.raises(RuntimeError): rt.verify_runtime(package)


def test_session_construction_uses_selected_runtime_without_physics(monkeypatch):
    from tools.learning.runtime import verify_runtime
    verify_runtime(rt.ROOT/'tmp/mujoco_3_13_probe')
    import tools.learning.session as module
    import tools.learning.environment  # import default dependency before substituting selection
    selected=Path('selected_repaired_package').resolve()
    monkeypatch.setattr(module,'active_package',lambda:selected,raising=False)
    def verify(path):
        if Path(path).resolve()!=selected:raise RuntimeError('session used stale default package')
    monkeypatch.setattr(module,'verify_runtime',verify)
    # Real constructor, inert environment injection: no model/reset/forward/optimization.
    session=module.EpisodeSession(environment=object(),controller_factory=lambda:None)
    assert session.done and not session._ready
