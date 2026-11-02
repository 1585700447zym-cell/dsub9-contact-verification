"""Real Windows venv process relationships; never start a training entry."""
import importlib,json,os,subprocess,sys
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
PROBE=ROOT/'deliverables/learning_chain/b2_windows_parent_fix_20260929/process_probe.py'

@pytest.mark.parametrize('scenario',['normal','wrong_parent','stale_registration','duplicate_claim'])
def test_real_supervisor_worker_restore_chain(tmp_path,scenario):
    assert os.name=='nt','This regression must be exercised on Windows, not skipped'
    result=subprocess.run([sys.executable,'-X','utf8','-B',str(PROBE),str(tmp_path),'supervisor',scenario],
        cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
    assert result.returncode==0,result.stdout+result.stderr
    report=json.loads((tmp_path/'probe_report.json').read_text(encoding='utf-8'))
    assert report['scenario']==scenario and not any(report['forbidden_call_counts'].values())
    if scenario=='normal':
        assert report['worker_exit']==0,(tmp_path/'fault.log').read_text(encoding='utf-8')
        for role in ('worker','restore'):
            row=json.loads((tmp_path/(role+'_identity.json')).read_text(encoding='utf-8'))
            assert row['route']=='windows_venv_launcher' and row['registered_parent_pid']!=row['parent_pid']
        assert (tmp_path/'restore_claim.json').exists()
    else:
        assert report['worker_exit']!=0
        assert not (tmp_path/'restore_claim.json').exists()
        if scenario!='duplicate_claim':
            assert not (tmp_path/'worker_claim.json').exists()
            assert 'ValueError: Registered parent identity is stale or inconsistent' in (tmp_path/'fault.log').read_text(encoding='utf-8')
        else:
            assert (tmp_path/'worker_claim.json').exists()
            assert 'FileExistsError' in (tmp_path/'fault.log').read_text(encoding='utf-8')


def test_real_direct_child_is_supported_without_venv_launcher():
    import time
    code='from tools.validation.process_parent import require_registered_parent; import json,sys; print(json.dumps(require_registered_parent(int(sys.argv[1]),float(sys.argv[2]))))'
    result=subprocess.run([sys._base_executable,'-X','utf8','-B','-c',code,str(os.getpid()),str(time.time())],
        cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=15)
    assert result.returncode==0,result.stderr
    assert json.loads(result.stdout)['route']=='direct'


def nodes():
    image=str(Path(sys._base_executable).resolve());launcher=str(Path(sys.executable).resolve())
    return dict(expected_pid=10,registered_at=101.,now=110.,python_image=image,launcher_image=launcher,
        child=dict(pid=30,parent_pid=20,created_at=103.,image=image,alive=True),
        parent=dict(pid=20,parent_pid=10,created_at=102.,image=launcher,alive=True),
        registered=dict(pid=10,parent_pid=1,created_at=100.,image=image,alive=True))


@pytest.mark.parametrize('damage',['wrong_launcher','wrong_python','wrong_ancestor','too_many_hops',
    'dead_registered','dead_launcher','reused_registered_pid','parent_younger_than_child','future_record','self_as_parent'])
def test_unrelated_stale_or_unverifiable_processes_are_rejected(damage):
    m=importlib.import_module('tools.validation.process_parent');r=nodes()
    if damage=='wrong_launcher':r['parent']['image']='C:/unrelated/python.exe'
    elif damage=='wrong_python':r['registered']['image']='C:/unrelated/python.exe'
    elif damage=='wrong_ancestor':r['parent']['parent_pid']=999
    elif damage=='too_many_hops':r['child']['parent_pid']=999
    elif damage=='dead_registered':r['registered']['alive']=False
    elif damage=='dead_launcher':r['parent']['alive']=False
    elif damage=='reused_registered_pid':r['registered']['created_at']=102.
    elif damage=='parent_younger_than_child':r['parent']['created_at']=104.
    elif damage=='future_record':r['registered_at']=111.
    else:r['expected_pid']=30
    with pytest.raises(ValueError):m.validate_chain(**r)


def test_process_inspection_failure_is_not_accepted(monkeypatch):
    m=importlib.import_module('tools.validation.process_parent')
    def unavailable(*args):raise OSError('Cannot inspect parent')
    monkeypatch.setattr(m,'windows_process',unavailable)
    with pytest.raises((OSError,ValueError)):m.require_registered_parent(123,1.)
