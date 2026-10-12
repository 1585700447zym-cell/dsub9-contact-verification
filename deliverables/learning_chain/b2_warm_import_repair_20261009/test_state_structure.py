"""Run the exact typed-digest function on stdlib states without scientific imports."""
from pathlib import Path
import ast,hashlib,sys,types,unittest
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from joint_contract import canonical

tree=ast.parse((HERE/'numeric_state.py').read_text(encoding='utf8'))
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in ('state_digest','require_equal')]
# Type sentinels are never instantiated; this executes only the real stdlib branches.
context=dict(hashlib=hashlib,canonical=canonical,torch=types.SimpleNamespace(Tensor=type('TensorSentinel',(),{})),
    np=types.SimpleNamespace(ndarray=type('ArraySentinel',(),{})))
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(HERE/'numeric_state.py'),'exec'),context)

class DigestStructureTests(unittest.TestCase):
    def test_moving_envelope_fields_into_warm_state_changes_digest(self):
        a={'state':{'warm':{'draws':388,'held':[.1]*4}},'training_admitted':False,'version':'b2_archived_warm_checkpoint_v1'}
        b={'state':{'warm':{'draws':388,'held':[.1]*4,'training_admitted':False,'version':'b2_archived_warm_checkpoint_v1'}}}
        self.assertNotEqual(a,b)
        self.assertNotEqual(context['state_digest'](a),context['state_digest'](b))
        with self.assertRaises(ValueError):context['require_equal'](a,b,'Envelope structure')

    def test_dictionary_reordering_preserves_semantic_identity(self):
        a={'alpha':1,'warm':{'draws':388,'held':[.1]*4}}
        b={'warm':{'held':[.1]*4,'draws':388},'alpha':1}
        self.assertEqual(context['state_digest'](a),context['state_digest'](b))

    def test_numeric_types_and_sequence_boundaries_remain_distinct(self):
        for a,b in ((1,True),(1,1.),([1,2],(1,2)),([[1],2],[[1,2]])):
            self.assertNotEqual(context['state_digest'](a),context['state_digest'](b))

if __name__=='__main__':unittest.main(verbosity=2)
