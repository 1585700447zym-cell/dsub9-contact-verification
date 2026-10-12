from copy import deepcopy
import gzip
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

HERE=Path(__file__).resolve().parent


class InheritedSourceTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue((HERE/'learning_runtime.py').exists(),'Inherited source adapter is missing')
        self.C=importlib.import_module('paired_contract')
        from tools.validation.run_actor_lr_comparison import select_qualified_runtime
        select_qualified_runtime()
        self.R=importlib.import_module('learning_runtime')
        import torch,mujoco
        def forbidden(*args,**kwargs):raise AssertionError('Offline source tests forbid computation')
        self.addCleanup(patch.stopall)
        patch.object(torch.nn.Module,'_call_impl',forbidden).start()
        patch.object(torch.optim.Adam,'step',forbidden).start()
        for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):
            patch.object(mujoco,name,forbidden).start()
        row=self.C.inherited_attempts()[4]['result']
        self.raw=json.loads(gzip.decompress((self.C.ROOT/row['archive_path']).read_bytes()))

    def test_real_inherited_f_archive_is_requalified(self):
        stamp=self.R._source(self.raw,'F','warmup',0,0,'a'*64)
        self.assertEqual(stamp['stage_mode'],'F')

    def test_current_binding_cannot_relabel_old_warmup(self):
        raw=deepcopy(self.raw);raw['qualification_sha256']='a'*64
        with self.assertRaises(ValueError):self.R._source(raw,'F','warmup',0,0,'a'*64)

    def test_source_from_wrong_permission_is_rejected(self):
        with self.assertRaises(ValueError):self.R._source(self.raw,'S','warmup',0,0,'a'*64)


if __name__=='__main__':unittest.main()
