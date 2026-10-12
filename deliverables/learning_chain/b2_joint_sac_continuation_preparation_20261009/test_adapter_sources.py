"""Source regressions keep unexecuted numerical dependencies explicit."""
import ast, copy, json, sys, unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE))
from bootstrap import read,sha
from joint_contract import LIMITS,advance,schedule,digest,metric
from execution import verify_grant,restore_equal,PHYSICAL_FIELDS

def function(path,name):
    tree=ast.parse(path.read_text(encoding='utf8'))
    return next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)

class SourceTests(unittest.TestCase):
    def test_worker_has_no_eager_numerical_adapter_import(self):
        tree=ast.parse((HERE/'pilot_worker.py').read_text(encoding='utf8'))
        eager=[n.module for n in tree.body if isinstance(n,ast.ImportFrom)]
        self.assertNotIn('warm_adapter',eager,'Numerical adapter must import after GO and current admission')

    def test_archive_rebuild_is_reserved_before_numeric_audit(self):
        text=(HERE/'joint_checkpoint.py').read_text(encoding='utf8')
        body=ast.get_source_segment(text,function(HERE/'joint_checkpoint.py','validate_state'))
        self.assertLess(body.index("take('archive_rebuilds')"),body.index('out=audit_raw('), 'Exhausted or failed audit must not bypass attempted-cost accounting')
    def test_typed_digest_is_identical_to_passed_restore_gate(self):
        previous=HERE.parent/'b2_warm_import_repair_20261009'
        self.assertEqual(ast.dump(function(HERE/'warm_adapter.py','state_digest')),ast.dump(function(previous/'numeric_state.py','state_digest')))

    def test_physical_rollout_and_updater_metering_are_unchanged(self):
        previous=HERE.parent/'b2_joint_sac_preparation_20261009'
        for name in ('joint_runtime.py','joint_rollout.py'):
            self.assertEqual(sha(HERE/name),sha(previous/name))

    def test_private_audited_rng_is_restored_in_common_install_path(self):
        f=function(HERE/'joint_checkpoint.py','install_state')
        assigned={t.attr for n in ast.walk(f) if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Attribute)}
        self.assertTrue({'_audited_warm_rng','_audited_warm_draws','warm_draws','held','updater','replay','boundary','attempts','history','update_attempts','stop_reason'}<=assigned)

    def test_advance_stops_at_first_unhealthy_episode(self):
        plan=schedule()
        self.assertEqual(advance([]),plan[0])
        self.assertIsNone(advance([dict(id=plan[0]['id'],healthy=False)]))
        with self.assertRaises(ValueError):advance([dict(id=plan[1]['id'],healthy=True)])
        self.assertIsNone(advance([dict(id=p['id'],healthy=True) for p in plan]))

    def test_candidate_budget_and_operation_breakdown(self):
        c=read(HERE/'candidate.json')
        self.assertEqual(c['limits'],LIMITS)
        for key in ('learner_constructions','tensor_loads','checkpoint_saves','archive_rebuilds'):
            self.assertEqual(sum(x[key] for x in c['accounting_breakdown'].values()),LIMITS[key])
        self.assertEqual(LIMITS['dynamic_episodes'],len(schedule()))
        self.assertEqual(LIMITS['formal_updates'],4*500)
        self.assertEqual(LIMITS['control_cycles'],9*14500)

    def test_new_grant_is_specific_to_this_candidate(self):
        c=read(HERE/'candidate.json');b=sha(HERE/'source_binding.json')
        g=dict(version='b2_joint_continuation_grant_v1',status='OPEN',explicit_user_authorized=True,human_evidence='test fixture; never execution',
               candidate_sha256=digest(c),binding_sha256=b,cumulative_before=245,limits=LIMITS)
        verify_grant(c,g,digest(g),b)
        for key,value in [('explicit_user_authorized',False),('status','CLOSED')]:
            bad=dict(g,**{key:value})
            with self.assertRaises(PermissionError):verify_grant(c,bad,digest(bad),b)
        for key,value in [('candidate_sha256','0'*64),('cumulative_before',237),('limits',dict(LIMITS,dynamic_episodes=17))]:
            bad=dict(g,**{key:value})
            with self.assertRaises(ValueError):verify_grant(c,bad,digest(bad),b)

    def test_inherited_baseline_is_exact_four_case_reference(self):
        from continuation_contract import baseline_rows
        m=metric(baseline_rows())
        self.assertTrue(m['comparable']);self.assertEqual(m['success_count'],4);self.assertEqual(m['guards'],0)

    def test_physical_restore_requires_all_fields_and_state(self):
        complete=dict(state_digest='c'*64,physical={k:[] for k in PHYSICAL_FIELDS})
        restore_equal(complete,complete)
        with self.assertRaises(ValueError):restore_equal(complete,dict(complete,state_digest='d'*64))
        bad=copy.deepcopy(complete);bad['physical'].pop('actions')
        with self.assertRaises(ValueError):restore_equal(complete,bad)

if __name__=='__main__':unittest.main(verbosity=2)
