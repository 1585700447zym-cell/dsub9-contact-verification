"""Execute lifecycle consumers with the expensive checkpoint/physics boundaries replaced."""
import ast
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace,ModuleType
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from joint_contract import ROOT,read,write,schedule
import pilot_worker


class WorkerLifecycleTests(unittest.TestCase):
    def test_reader_failure_preserves_all_parent_rows_and_failed_restore(self):
        with tempfile.TemporaryDirectory(prefix='b2_joint_reader_',dir=ROOT/'tmp') as d:
            folder=Path(d).resolve();self.assertTrue(folder.is_relative_to((ROOT/'tmp').resolve()))
            entries=[dict(id=s['id'],healthy=True) for s in schedule()[:-1]]
            write(folder/'run/ledger.json',dict(status='RUNNING',episodes=entries,policy_calls=0))
            write(folder/'run/final.request.json',dict(checkpoint_pin='x',state_digest='same'))
            boundary=ModuleType('joint_checkpoint');boundary.load_checkpoint=lambda *a,**kw:object();boundary.capture=lambda c:{}
            def fail_physics(folder,chain,spec,ledger):
                self.assertEqual(len(ledger['episodes']),16)
                ledger['episodes'].append(dict(id=spec['id'],healthy=False,status='running'))
                write(folder/'run/ledger.json',ledger)
                raise RuntimeError('simulated physical exception before completion')
            with patch.dict(sys.modules,{'joint_checkpoint':boundary}),patch.object(pilot_worker,'state_digest',return_value='same'),patch.object(pilot_worker,'physical',side_effect=fail_physics):
                with self.assertRaises(RuntimeError):pilot_worker.reader(folder,'final',SimpleNamespace(verify=lambda mode:{}))
            kept=read(folder/'run/ledger.json')['episodes']
            self.assertEqual(kept[:16],entries);self.assertEqual(kept[-1]['id'],'restore_F50_J01');self.assertEqual(len(kept),17)

    def test_stop_between_batches_prevents_second_numeric_update(self):
        # Run the actual inherited update loop. Only the expensive numeric/sampling boundary is fake.
        tree=ast.parse((OUT/'joint_chain.py').read_text(encoding='utf-8'))
        cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='V4Chain')
        method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='update')
        ns=dict(deepcopy=deepcopy,time=time,_write_json=write)
        exec(compile(ast.Module(body=[method],type_ignores=[]),'real_update_loop','exec'),ns)
        worker=ast.parse((OUT/'pilot_worker.py').read_text(encoding='utf-8'))
        call=next(n for n in ast.walk(worker) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='chain' and n.func.attr=='update')
        before=next(k.value for k in call.keywords if k.arg=='before_update')
        before=eval(compile(ast.Expression(before),'actual_worker_callback','eval'))
        with tempfile.TemporaryDirectory(prefix='b2_joint_stop_',dir=ROOT/'tmp') as d:
            folder=Path(d).resolve();self.assertTrue(folder.is_relative_to((ROOT/'tmp').resolve()))
            numeric=SimpleNamespace(counts={'critic':0},fingerprints=lambda:{'actor':'x'})
            def numerical_update(*args,**kwargs):
                numeric.counts['critic']+=1;(folder/'STOP').write_text('stop',encoding='utf-8');return {}
            numeric.update=numerical_update
            def verify():
                if (folder/'STOP').exists():raise PermissionError('STOP')
            state=SimpleNamespace(_healthy=verify,verify=verify,active=False,updater=numeric,available=500,warm_gate=lambda:True,
                update_attempts=0,output=folder,_append_event=lambda *a,**kw:None,boundary=SimpleNamespace(sample=lambda *a,**kw:SimpleNamespace(actor=None,critic=None,targets=[],mask=[],indices=[])),
                replay=[],replay_rng=None,boundary_rng=None,attempts=[],history=[])
            with self.assertRaises(PermissionError):ns['update'](state,500,before_update=before)
            self.assertEqual(numeric.counts['critic'],1);self.assertTrue(state.failed)


if __name__=='__main__':unittest.main(verbosity=2)
