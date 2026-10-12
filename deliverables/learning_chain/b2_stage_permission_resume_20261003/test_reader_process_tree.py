import copy,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
import reader_supervision as R
import paired_contract as C
from report_result import audit_readers

def alive(pid):
    from tools.validation.process_parent import kernel_api
    api=kernel_api();h=api.OpenProcess(0x100000,False,pid)
    if not h:return False
    try:return api.WaitForSingleObject(h,0)==0x102
    finally:api.CloseHandle(h)

class ReaderProcessTree(unittest.TestCase):
    @unittest.skipUnless(os.name=='nt','Windows venv launcher regression')
    def test_guard_failure_terminates_actual_python_not_only_launcher(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/'reader';pidfile=Path(d)/'actual_pid.json'
            code="import json,os,pathlib,sys,time; pathlib.Path(sys.argv[1]).write_text(json.dumps({'pid':os.getpid(),'parent':os.getppid()})); time.sleep(30)"
            def guard():
                if pidfile.exists():raise RuntimeError('registered parent unavailable')
            try:
                with self.assertRaises(R.ReaderFailure):R.run_reader([sys.executable,'-B','-c',code,str(pidfile)],Path.cwd(),folder,timeout_s=8,guard=guard)
                info=json.loads(pidfile.read_text());record=json.loads((folder/'exit.json').read_text())
                self.assertFalse(alive(info['pid']),f'Actual reader survived launcher cleanup: {record}')
                self.assertTrue(record['tree_stop_confirmed'])
            finally:
                if pidfile.exists():
                    pid=json.loads(pidfile.read_text())['pid']
                    if alive(pid):subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],capture_output=True,timeout=10)

    def test_qualified_launcher_receipt_is_complete_wrong_chain_rejected(self):
        main=dict(pid=100,parent_pid=99,created_at=1.,alive=True,image=sys._base_executable)
        launcher=dict(pid=200,parent_pid=100,created_at=2.,alive=True,image=sys.executable)
        child=dict(pid=201,parent_pid=200,created_at=3.,alive=True,image=sys._base_executable)
        chain=dict(route='windows_venv_launcher',pid=201,parent_pid=200,registered_parent_pid=100,child=child,parent=launcher,registered=main)
        proof=dict(complete_equal=True,arm='F',batches=0,pid=201,manifest_sha256='c'*64,binding_sha256='a'*64,authorization_sha256='b'*64,calls=dict(model_forward=0,optimizer=0,physics=0),parent_chain=chain)
        state=dict(binding_sha256='a'*64,authorization_sha256='b'*64,zero_readers={'F':proof},updates={'F':{'attempted':0},'S':{'attempted':0}})
        with tempfile.TemporaryDirectory() as d:
            run=Path(d);folder=run/'zero_reader_F';folder.mkdir()
            C.write(folder/'process.json',dict(pid=200,parent_pid=100,wall_timestamp=2.5))
            C.write(folder/'exit.json',dict(status='finished',returncode=0,process_stopped=True,pid=200,cleanup_error=None))
            C.write(folder/'stdout.txt',proof)
            self.assertTrue(audit_readers(run,state)['complete'])
            bad=copy.deepcopy(proof);bad['parent_chain']['parent']['parent_pid']=999
            state['zero_readers']['F']=bad;C.write(folder/'stdout.txt',bad)
            with self.assertRaises(ValueError):audit_readers(run,state)
