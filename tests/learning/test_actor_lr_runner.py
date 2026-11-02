import importlib
import sys
import pytest


def test_runner_import_does_not_import_engine(monkeypatch):
    sys.modules.pop('tools.validation.run_actor_lr_comparison',None)
    m=importlib.import_module('tools.validation.run_actor_lr_comparison')
    assert callable(m.main)


def test_missing_authorization_rejected_before_runtime_or_model(monkeypatch):
    m=importlib.import_module('tools.validation.run_actor_lr_comparison')
    monkeypatch.setattr(m,'require_authorization',lambda *a:(_ for _ in ()).throw(ValueError('missing auth')))
    monkeypatch.setattr(m,'select_qualified_runtime',lambda:pytest.fail('runtime before authorization'))
    with pytest.raises(ValueError,match='missing auth'):m.main(['--candidate-sha256','a'*64])


def test_verify_only_is_not_execution_authorization(monkeypatch,capsys):
    m=importlib.import_module('tools.validation.run_actor_lr_comparison')
    monkeypatch.setattr(m,'verify_candidate',lambda *a,**k:{})
    monkeypatch.setattr(m,'require_authorization',lambda *a:pytest.fail('verify-only execution'))
    assert m.main(['--candidate-sha256','a'*64,'--verify-only'])==0
    assert 'not authorized' in capsys.readouterr().out


def test_cleanup_unconfirmed_preserves_ledger_and_reports_uncertainty(tmp_path,monkeypatch):
    import json
    m=importlib.import_module('tools.validation.run_actor_lr_comparison')
    monkeypatch.setattr(m,'DELIVERY',tmp_path)
    (tmp_path/'run').mkdir();raw='{"untrusted_test_ledger":true}'
    (tmp_path/'run/ledger.json').write_text(raw,encoding='utf-8')
    (tmp_path/'process_exit.json').write_text(json.dumps(dict(status='supervisor_error',worker_stopped=False,cleanup_error='injected kill failure')),encoding='utf-8')
    m.finalize_failure('a'*64,'b'*64,'supervisor failed')
    assert (tmp_path/'run/ledger.json').read_text(encoding='utf-8')==raw
    result=m.read(tmp_path/'exit_classification.json')
    assert result['worker_stop_confirmed'] is False and result['execution_complete'] is False


def test_stop_request_blocks_worker_before_parent_probe(tmp_path,monkeypatch):
    import json
    m=importlib.import_module('tools.validation.run_actor_lr_comparison')
    monkeypatch.setattr(m,'DELIVERY',tmp_path)
    (tmp_path/'started.json').write_text(json.dumps(dict(supervisor_pid=123,wall_timestamp=1.)),encoding='utf-8')
    (tmp_path/'stop_requested.json').write_text('{}',encoding='utf-8')
    from tools.validation import process_parent
    monkeypatch.setattr(process_parent,'require_registered_parent',lambda *a:pytest.fail('parent probe after stop request'))
    with pytest.raises(RuntimeError,match='requested stop'):m.execution_guard(tmp_path)()


def test_root_stop_request_blocks_descendant_before_parent_probe(tmp_path,monkeypatch):
    import json
    m=importlib.import_module('tools.validation.run_actor_lr_comparison');monkeypatch.setattr(m,'DELIVERY',tmp_path)
    (tmp_path/'started.json').write_text(json.dumps(dict(supervisor_pid=1,wall_timestamp=1.)),encoding='utf-8')
    child=tmp_path/'run/eval_process_A';child.mkdir(parents=True)
    (child/'started.json').write_text(json.dumps(dict(supervisor_pid=2,wall_timestamp=2.)),encoding='utf-8')
    (tmp_path/'stop_requested.json').write_text('{}',encoding='utf-8')
    from tools.validation import process_parent
    monkeypatch.setattr(process_parent,'require_registered_parent',lambda *a:pytest.fail('descendant work after root stop'))
    with pytest.raises(RuntimeError,match='requested stop'):m.execution_guard(child)()


def test_missing_exit_receipt_with_stop_request_remains_unconfirmed(tmp_path,monkeypatch):
    m=importlib.import_module('tools.validation.run_actor_lr_comparison');monkeypatch.setattr(m,'DELIVERY',tmp_path)
    (tmp_path/'run').mkdir();raw='{"untrusted_test_ledger":true}'
    (tmp_path/'run/ledger.json').write_text(raw,encoding='utf-8');(tmp_path/'stop_requested.json').write_text('{}',encoding='utf-8')
    m.finalize_failure('a'*64,'b'*64,'UnconfirmedWorkerStop')
    assert (tmp_path/'run/ledger.json').read_text(encoding='utf-8')==raw
    assert m.read(tmp_path/'exit_classification.json')['worker_stop_confirmed'] is False


def test_descendant_checks_ancestor_even_when_direct_parent_alive(tmp_path,monkeypatch):
    import json
    m=importlib.import_module('tools.validation.run_actor_lr_comparison');monkeypatch.setattr(m,'DELIVERY',tmp_path)
    (tmp_path/'started.json').write_text(json.dumps(dict(supervisor_pid=1,wall_timestamp=1.)),encoding='utf-8')
    child=tmp_path/'run/eval_process_A';child.mkdir(parents=True)
    (child/'started.json').write_text(json.dumps(dict(supervisor_pid=2,wall_timestamp=2.)),encoding='utf-8')
    from tools.validation import process_parent
    monkeypatch.setattr(process_parent,'require_registered_parent',lambda *a:None)
    def gone(record):raise RuntimeError('ancestor stopped')
    monkeypatch.setattr(m,'ensure_live_ancestor',gone)
    with pytest.raises(RuntimeError,match='ancestor stopped'):m.execution_guard(child)()
