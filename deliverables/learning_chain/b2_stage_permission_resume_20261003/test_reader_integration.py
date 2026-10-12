import importlib,json,os,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

HERE=Path(__file__).resolve().parent

class ReaderIntegration(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE/'run_pair.py').exists(),'Recovery runner not implemented')
        self.R=importlib.import_module('run_pair')
        self.temp=tempfile.TemporaryDirectory(dir=self.R.C.ROOT/'tmp');self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'checkpoint_F_0000';self.path.mkdir()
        self.guard=lambda:None
        self.ledger=SimpleNamespace(state=dict(binding_sha256='a'*64,authorization_sha256='b'*64),check_live=self.guard)
        self.proof=dict(complete_equal=True,pid=os.getpid()+100,manifest_sha256='c'*64,calls=dict(model_forward=0,optimizer=0,physics=0),batches=0,arm='F',binding_sha256='a'*64,authorization_sha256='b'*64)
        main=dict(pid=os.getpid(),parent_pid=99,created_at=1.,alive=True,image=sys._base_executable)
        child=dict(pid=self.proof['pid'],parent_pid=os.getpid(),created_at=3.,alive=True,image=sys._base_executable)
        self.proof['parent_chain']=dict(route='direct',pid=child['pid'],parent_pid=main['pid'],registered_parent_pid=main['pid'],child=child,parent=main,registered=main)
        self.process=dict(pid=child['pid'],parent_pid=main['pid'],wall_timestamp=2.)
    def test_reader_uses_bounded_supervisor_and_complete_identity(self):
        import reader_supervision
        with patch.object(reader_supervision,'run_reader',return_value=dict(stdout=json.dumps(self.proof),process=self.process)) as call:
            result=self.R.verify_checkpoint_child(self.path,'c'*64,'F',self.ledger)
        self.assertEqual(result,self.proof)
        self.assertEqual(call.call_args.kwargs,dict(timeout_s=300,guard=self.guard))
        self.assertEqual(call.call_args.args[2],self.path.parent/'zero_reader_F')
    def test_reader_failure_and_wrong_proof_do_not_pass(self):
        import reader_supervision
        with patch.object(reader_supervision,'run_reader',side_effect=reader_supervision.ReaderFailure('failed')):
            with self.assertRaises(reader_supervision.ReaderFailure):self.R.verify_checkpoint_child(self.path,'c'*64,'F',self.ledger)
        self.proof['arm']='S'
        with patch.object(reader_supervision,'run_reader',return_value=dict(stdout=json.dumps(self.proof))):
            with self.assertRaises(ValueError):self.R.verify_checkpoint_child(self.path,'c'*64,'F',self.ledger)
