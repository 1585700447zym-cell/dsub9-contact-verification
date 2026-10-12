import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import paired_contract as C
import run_pair as R

class Runner(unittest.TestCase):
    def test_parent_seal_and_sources_unchanged(self):C.verify_parent()
    def test_insufficient_warmup_does_not_pass(self):
        rows={arm:[dict(id=f'{arm}{i}',cycles=100,success=False) for i in range(4)] for arm in ('F','S')}
        ledger=SimpleNamespace(rows=lambda stage,arm:rows[arm])
        with patch.object(R,'raw_at',return_value={'transitions':[{'action_active':False}]*100}):
            self.assertFalse(R.warmup_report(ledger)['passed'])
        with patch.object(R,'raw_at',return_value={'transitions':[{'action_active':True}]*100}):
            self.assertTrue(R.warmup_report(ledger)['passed'])
    def test_physics_charges_before_call_and_requires_start(self):
        state=dict(status='healthy',active=None)
        ledger=SimpleNamespace(state=state,write_failed=False,check_live=lambda:None)
        p=R.Physics(ledger)
        with self.assertRaises(RuntimeError):p.step(lambda *a:None,1,2)
        state['active']=0;p.begin()
        def fail(*a):raise OSError('physical fault')
        with self.assertRaises(OSError):p.step(fail,1,2)
        self.assertEqual(p.total_substeps,1)
        with self.assertRaises(ValueError):p.step(lambda *a:None,1,2,nstep=2)
    def test_warmup_model_call_forbidden(self):
        l=SimpleNamespace(state=dict(status='healthy',active=4,update_lease=None),write_failed=False)
        with self.assertRaises(RuntimeError):R.LearningMeter(l).begin_control()
    def test_unknown_worker_exit_blocks_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)
            with self.assertRaises(RuntimeError):R.confirm_exit(p)
            C.write(p/'process_exit.json',dict(status='supervisor_error',worker_stopped=False,cleanup_error='unknown'))
            with self.assertRaises(RuntimeError):R.confirm_exit(p)
    def test_online_publication_follows_finished_physical_lease(self):
        with tempfile.TemporaryDirectory(dir=C.ROOT/'tmp') as d:
            path=Path(d)/'episode.json.gz';path.write_bytes(b'raw')
            state={'active':12};calls=[]
            def finish(row):state['active']=None;calls.append('finish')
            def append(*args):
                self.assertIsNone(state['active']);calls.append('publish')
            row=dict(id='online_F_x_pos_100',stage='online',guard_hit=False,training_batches=500)
            R.finish_and_publish(SimpleNamespace(finish=finish),row,SimpleNamespace(append_archive=append),{'transitions':[1]},path,{})
            self.assertEqual(calls,['finish','publish'])

if __name__=='__main__':unittest.main()
