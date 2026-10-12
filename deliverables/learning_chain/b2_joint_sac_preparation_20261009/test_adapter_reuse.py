"""Guard against dropping an audit during the narrowly generated adapter port."""
import ast
from pathlib import Path
import sys
import unittest
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))


def definitions(path):
    return {n.name:n for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}


class AdapterReuseTests(unittest.TestCase):
    def test_chain_credit_publication_rng_and_update_bodies_preserved(self):
        old=definitions(ROOT/'tools/learning/v4_pilot_chain.py');new=definitions(OUT/'joint_chain.py')
        for name in ('V4Chain','streams','validate_warm'):
            self.assertEqual(ast.dump(old[name]),ast.dump(new[name]),name)
        audit=new['audit_raw'];added=[n for n in audit.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Name) and n.value.func.id=='validate_raw_identity']
        self.assertEqual(len(added),1);audit.body.remove(added[0])
        for node in ast.walk(old['audit_raw']):
            if isinstance(node,ast.ImportFrom) and node.level==1:
                node.module='tools.learning.'+node.module;node.level=0
        self.assertEqual(ast.dump(old['audit_raw']),ast.dump(audit))

    def test_checkpoint_validation_and_restore_bodies_preserved(self):
        old=definitions(ROOT/'tools/learning/v4_checkpoint.py');new=definitions(OUT/'joint_checkpoint.py')
        class Unmeter(ast.NodeTransformer):
            def visit_Call(self,node):
                if isinstance(node.func,ast.Name) and node.func.id=='metered_load':node.func=ast.Attribute(value=ast.Name(id='torch',ctx=ast.Load()),attr='load',ctx=ast.Load())
                return self.generic_visit(node)
        for name in old:
            self.assertEqual(ast.dump(old[name]),ast.dump(Unmeter().visit(new[name])),name)

    def test_rollout_constructs_real_contactcase_with_nonzero_tilts(self):
        from dataclasses import dataclass,asdict
        import math
        from joint_contract import case_kwargs,training_cases
        # Execute the actual constructor expression with the source's real pure dataclass.
        source=definitions(ROOT/'tools/validation/run_contact_cases.py')['ContactCase']
        ns=dict(dataclass=dataclass,math=math)
        exec(compile(ast.Module(body=[source],type_ignores=[]),'ContactCase','exec'),ns)
        rollout=definitions(OUT/'joint_rollout.py')['rollout']
        assignment=next(n for n in rollout.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='case' for t in n.targets))
        for i,point in enumerate(training_cases()):
            scope=dict(ns,case_kwargs=case_kwargs,point=point)
            exec(compile(ast.Module(body=[assignment],type_ignores=[]),'rollout_case','exec'),scope)
            actual=asdict(scope['case'])
            self.assertEqual(actual['name'],'J0'+str(i+1))
            self.assertAlmostEqual(abs(actual['roll_rad']),.004363323129985824)
            self.assertAlmostEqual(abs(actual['pitch_rad']),.004363323129985824)
            self.assertEqual(actual['start_origin_z_m'],-.004)
            self.assertEqual(actual['target_depth_m'],.004)


if __name__=='__main__':unittest.main(verbosity=2)
