from pathlib import Path
import sys,unittest,uuid
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(HERE))
from gate_worker import NoPhysics
from import_graph import collect_graph,check_guard

class ImportGraphTests(unittest.TestCase):
    def sandbox(self,files):
        root=HERE/'test_work'/uuid.uuid4().hex;local=root/'candidate';local.mkdir(parents=True)
        for name,text in files.items():
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf8')
        return root,local

    def test_required_pure_helper_is_allowed_but_neighbors_are_denied(self):
        guard=NoPhysics();self.assertIsNone(guard.find_spec('tools.dynamics.safety'))
        for name in ('tools.dynamics.safety_extra','tools.dynamics.safety.evil','tools.dynamics.cartesian','mujoco','mujoco.viewer','tools.learning.environment'):
            with self.assertRaises(PermissionError):guard.find_spec(name)

    def test_real_entry_graph_includes_actual_failure_chain(self):
        graph=collect_graph(ROOT,HERE,['numeric_state','gate_worker','run_gate'])
        edges={(e['source'],e['target']) for e in graph['eager_edges']}
        chain=['numeric_state','tools.learning.v4_sac','tools.learning.audited_replay','tools.learning.action','tools.dynamics.safety']
        self.assertTrue(set(zip(chain,chain[1:])).issubset(edges));check_guard(graph,NoPhysics())
        self.assertIn('tools.learning.runtime',graph['modules'])
        self.assertFalse(any(k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3') for k in sys.modules))

    def test_relative_from_imports_and_parent_initializer_are_included(self):
        root,local=self.sandbox({'candidate/entry.py':'from tools.pkg.mod import value\n',
            'tools/pkg/__init__.py':'import tools.dynamics.cartesian\n','tools/pkg/mod.py':'from . import helper\n',
            'tools/pkg/helper.py':'from ..shared import value\n','tools/shared.py':'value=1\n','tools/dynamics/cartesian.py':'pass\n'})
        graph=collect_graph(root,local,['entry'])
        self.assertTrue({'tools.pkg','tools.pkg.helper','tools.shared','tools.dynamics.cartesian'}.issubset(graph['modules']))
        with self.assertRaises(PermissionError):check_guard(graph,NoPhysics())

    def test_deferred_backend_import_is_recorded_without_being_executed(self):
        root,local=self.sandbox({'candidate/entry.py':'def unused():\n    import mujoco\n'})
        graph=collect_graph(root,local,['entry']);check_guard(graph,NoPhysics())
        self.assertTrue(any(e['target']=='mujoco' for e in graph['deferred_edges']))

    def test_literal_dynamic_eager_backend_import_is_rejected(self):
        root,local=self.sandbox({'candidate/entry.py':"import importlib\nimportlib.import_module('mujoco')\n"})
        with self.assertRaises(PermissionError):check_guard(collect_graph(root,local,['entry']),NoPhysics())

    def test_unknown_dynamic_eager_import_fails_closed(self):
        root,local=self.sandbox({'candidate/entry.py':'import importlib\nname=get_name()\nimportlib.import_module(name)\n'})
        with self.assertRaises(ValueError):collect_graph(root,local,['entry'])

    def test_class_body_import_and_conditional_import_are_conservative(self):
        root,local=self.sandbox({'candidate/entry.py':'if flag:\n    import mujoco\nclass C:\n    import tools.learning.environment\n',
            'tools/learning/environment.py':'pass\n'})
        graph=collect_graph(root,local,['entry'])
        self.assertTrue({'mujoco','tools.learning.environment'}.issubset({e['target'] for e in graph['eager_edges']}))
        with self.assertRaises(PermissionError):check_guard(graph,NoPhysics())

    def test_missing_repository_module_is_an_error(self):
        root,local=self.sandbox({'candidate/entry.py':'import tools.does_not_exist\n'})
        with self.assertRaises(ValueError):collect_graph(root,local,['entry'])

if __name__=='__main__':unittest.main(verbosity=2)
