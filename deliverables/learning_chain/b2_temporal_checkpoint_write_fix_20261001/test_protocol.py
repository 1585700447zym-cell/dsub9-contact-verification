import importlib,json,tempfile,subprocess,sys,unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OLD=ROOT/'deliverables/learning_chain/b2_temporal_learning_validation_20261001'
sys.path.insert(0,str(OLD))
import validation_contract as C
import learning_runtime as R
from tools.learning.sac_checkpoint import _same
try:F=importlib.import_module('corrected_runtime')
except ModuleNotFoundError as e:
    if e.name!='corrected_runtime':raise
    F=None

class WriterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Offline zero-update serialization fixture, not a resumed trainer.
        state=C.read(OLD/'run/ledger.json');path=OLD/'run/dataset_C.json'
        ledger=SimpleNamespace(state=state,healthy=lambda:None)
        b=R.Branch('C',ledger,C.read(path),C.digest(path),dataset_bytes=path.read_bytes())
        cls.snapshot=b.capture();cls.updater=b.updater
        assert cls.snapshot['updater']['counts']['critic']==0
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.output=Path(self.tmp.name)/'checkpoint'
    def test_original_production_failure_reproduced(self):
        fake=SimpleNamespace(capture=lambda:self.snapshot,arm='C',manifest_pin=self.snapshot['dataset_sha256'],history=[])
        with self.assertRaisesRegex(TypeError,'bytes-like'):R.Branch.save(fake,self.output)
        self.assertFalse(self.output.exists());self.assertEqual(list(Path(self.tmp.name).glob('*.staging-*/state.pt'))[0].stat().st_size,0)
    def fixed(self):self.assertIsNotNone(F,'Missing corrected real checkpoint writer');return F
    def branch(self):return SimpleNamespace(capture=lambda:self.snapshot)
    def test_complete_tensor_archive_state_real_disk_roundtrip(self):
        f=self.fixed();pin=f.Branch.save(self.branch(),self.output);m=C.read(self.output/'manifest.json')
        import torch
        s=torch.load(self.output/'state.pt',map_location='cpu',weights_only=True)
        self.assertEqual(C.digest(self.output/'manifest.json'),pin);self.assertEqual(C.digest(self.output/'state.pt'),m['state_sha256'])
        self.assertTrue(_same(s,self.snapshot));self.assertEqual(m['batches'],0);self.assertEqual(m['version'],'temporal_checkpoint_manifest_v1')
    def test_duplicate_final_never_overwrites(self):
        f=self.fixed();pin=f.Branch.save(self.branch(),self.output)
        with self.assertRaises(FileExistsError):f.Branch.save(self.branch(),self.output)
        self.assertEqual(C.digest(self.output/'manifest.json'),pin)
    def test_manifest_failure_keeps_staging_not_loadable_final(self):
        from unittest.mock import patch
        f=self.fixed()
        with patch.object(f,'_flush_write',side_effect=OSError('disk error')):
            with self.assertRaises(OSError):f.Branch.save(self.branch(),self.output)
        self.assertFalse(self.output.exists());self.assertGreater(list(Path(self.tmp.name).glob('*.staging-*/state.pt'))[0].stat().st_size,0)
    def test_original_dataset_bytes_survive_without_reserialization(self):
        f=self.fixed();f.Branch.save(self.branch(),self.output)
        import torch
        s=torch.load(self.output/'state.pt',map_location='cpu',weights_only=True)
        self.assertEqual(s['dataset_bytes'],self.snapshot['dataset_bytes']);R.verify_dataset_bytes(s['dataset'],s['dataset_bytes'],s['dataset_sha256'])
    def test_independent_process_loads_complete_zero_update_state(self):
        f=self.fixed();pin=f.Branch.save(self.branch(),self.output)
        process=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'verify_saved.py'),'--path',str(self.output),'--sha256',pin],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
        self.assertEqual(process.returncode,0,process.stderr);proof=json.loads(process.stdout)
        self.assertTrue(proof['complete_updater_equal']);self.assertEqual(proof['batches'],0);self.assertFalse(any(proof['actual_calls'].values()))
    def test_synthetic_nonempty_adam_tensor_payload_roundtrip(self):
        import torch
        f=self.fixed();s=deepcopy(self.snapshot);s['fixture_kind']='synthetic_nonempty_adam_not_training'
        for key,opt in zip(('critic','actor','temperature'),self.updater._optimizers()):
            ids=[p for g in s['updater'][key]['param_groups'] for p in g['params']];params=[p for g in opt.param_groups for p in g['params']]
            s['updater'][key]['state']={i:dict(step=torch.tensor(500.),exp_avg=torch.zeros_like(p),exp_avg_sq=torch.ones_like(p)) for i,p in zip(ids,params)}
        s['updater']['counts']={k:500 for k in s['updater']['counts']};s['history']=[dict(critic_batches=i,active_rows=1,batch_rows=256) for i in range(1,501)]
        pin=f.Branch.save(SimpleNamespace(capture=lambda:s),self.output);loaded=torch.load(self.output/'state.pt',map_location='cpu',weights_only=True)
        self.assertTrue(_same(s,loaded));self.assertEqual(C.read(self.output/'manifest.json')['batches'],500)
        self.assertEqual(C.digest(self.output/'manifest.json'),pin)
