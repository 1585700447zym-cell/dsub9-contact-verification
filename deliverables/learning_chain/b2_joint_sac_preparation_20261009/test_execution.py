"""Authorization, closed accounting and opaque restore checks without torch."""
from pathlib import Path
import copy
import sys
import tempfile
import unittest
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from joint_contract import LIMITS,read,digest
from execution import verify_grant,Counter,restore_equal,verify_execution_copies


class ExecutionTests(unittest.TestCase):
    def test_drifted_execution_copy_is_rejected_before_backend(self):
        import shutil
        temp_root=OUT.parents[2]/'tmp'
        with tempfile.TemporaryDirectory(prefix='b2_joint_copy_',dir=temp_root) as d:
            folder=Path(d).resolve();self.assertTrue(folder.is_relative_to(temp_root.resolve()))
            for name in ('configuration.json','model.xml'):shutil.copyfile(OUT/name,folder/name)
            verify_execution_copies(folder)
            with (folder/'model.xml').open('a',encoding='utf-8') as f:f.write(' ')
            with self.assertRaises(ValueError):verify_execution_copies(folder)

    def test_unadmitted_numeric_entry_refuses_before_torch_import(self):
        import joint_runtime
        self.assertNotIn('torch',sys.modules)
        with self.assertRaises(PermissionError):getattr(joint_runtime,'V4Updater')
        self.assertNotIn('torch',sys.modules)

    def test_old_or_unsigned_grant_fails_before_any_runtime(self):
        candidate=read(OUT/'candidate.json')
        grant=dict(version='b2_joint_sac_grant_v1',explicit_user_authorized=True,status='OPEN',
            candidate_sha256=digest(candidate),binding_sha256='a'*64,limits=LIMITS,cumulative_before=237,
            human_evidence='批准本次17回合和2000次更新及保存恢复开销')
        verify_grant(candidate,grant,digest(grant),'a'*64)
        for key,value in [('explicit_user_authorized',False),('cumulative_before',225),('version','b2_joint_preflight_grant_v1'),('binding_sha256','b'*64)]:
            bad=copy.deepcopy(grant);bad[key]=value
            with self.assertRaises((ValueError,PermissionError)):verify_grant(candidate,bad,digest(bad),'a'*64)

    def test_reserved_attempts_consume_quota_even_when_backend_fails(self):
        temp_root=OUT.parents[2]/'tmp';temp_root.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='b2_joint_offline_',dir=temp_root) as d:
            self.assertTrue(Path(d).resolve().is_relative_to(temp_root.resolve()))
            c=Counter.create(Path(d)/'counter.json',{'construct':2})
            c.take('construct');c=Counter(c.path);c.take('construct')
            with self.assertRaises(RuntimeError):c.take('construct')
            self.assertEqual(read(c.path)['attempted']['construct'],2)
            c.close()
            with self.assertRaises(RuntimeError):c.take('construct')

    def test_restore_requires_full_state_and_all_physical_fields(self):
        parent=dict(state_digest='a',physical={k:[] for k in ('trace','actions','transitions','outcome','controller_events','events','stop_samples','peaks')})
        restore_equal(parent,copy.deepcopy(parent))
        child=copy.deepcopy(parent);child['state_digest']='b'
        with self.assertRaises(ValueError):restore_equal(parent,child)
        child=copy.deepcopy(parent);child['physical']['actions']=[1]
        with self.assertRaises(ValueError):restore_equal(parent,child)
        child=copy.deepcopy(parent);del child['physical']['peaks']
        with self.assertRaises(ValueError):restore_equal(parent,child)


if __name__=='__main__':unittest.main(verbosity=2)
