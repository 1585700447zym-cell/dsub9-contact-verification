"""Behavioral scope and admission tests; no numerical imports or episodes."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import scope_contract as c


class ContractTests(unittest.TestCase):
    def api(self,name):
        self.assertTrue(callable(getattr(c,name,None)), 'Missing behavior: '+name)
        return getattr(c,name)

    def point(self,case='D00'):
        config=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'))
        return next(p for p in config['cases'] if p['id']==case)

    def row(self):
        return dict(position_m=[0.,0.,-.004],quaternion_wxyz=[1.,0.,0.,0.],
                    contact_count=0,penetration_m=0.,contact_wrench_M=[0.]*6,
                    contact_wrench_G=[0.]*6,velocity_world=[0.]*6)

    def healthy(self,case='D00'):
        return dict(case_id=case,status='finished',healthy=True,
            outcome=dict(simulation_valid=True,physical_stopped=True,
                         guard_violations=dict(contact=False,motion=False),task_outcome='FULL_SUCCESS'),
            environment_creation_attempted=1,environment_created=1,reset_attempted=1,reset_completed=1,
            control_cycles=1,physical_substeps=10,policy_calls=0,formal_updates=0,
            learner_constructions=0,tensor_loads=0,replay_publications=0,
            initial_audit=dict(passed=True),archive_sha256='a'*64,
            supervisor=dict(go_issued=True,process_exit_confirmed=True,owned_launcher_exit_confirmed=True,returncode=0))

    def test_new_order_excludes_the_four_consumed_cases(self):
        self.assertEqual([p['id'] for p in self.api('new_cases')()],
            ['D00','P1','P2','P3','P4','A1','A2','A3','A4','J12','J13','J14','J21','J23','J24','J31','J32','J34','J41','J42','J43'])

    def test_registered_registry_rejects_duplicate_missing_reorder_pose_and_bool(self):
        validate=self.api('validate_registry')
        points=json.loads((OUT/'case_registry.json').read_text(encoding='utf-8'))['cases']
        for changed in [points[:-1],points+[points[0]],list(reversed(points))]:
            with self.assertRaises(ValueError):validate(changed)
        for value in [1.,True,float('nan')]:
            bad=copy.deepcopy(points);bad[0]['x_um']=value
            with self.assertRaises(ValueError):validate(bad)

    def test_case_units_and_registered_off_diagonal_orientation(self):
        kw=self.api('case_kwargs')(self.point('J12'))
        self.assertEqual(kw['name'],'J12');self.assertAlmostEqual(kw['x_offset_m'],.000075,places=15)
        self.assertAlmostEqual(kw['roll_rad'],-.004363323129985824,places=15)
        self.assertAlmostEqual(kw['pitch_rad'],.004363323129985824,places=15)

    def test_unregistered_or_extra_case_parameters_rejected(self):
        fn=self.api('case_kwargs')
        for change in [dict(id='J01'),dict(x_um=100),dict(yaw_deg=.1),dict(extra=0)]:
            p=self.point();p.update(change)
            with self.assertRaises(ValueError):fn(p)

    def test_exact_pose_and_quaternion_sign_equivalence(self):
        fn=self.api('check_pose');row=self.row();fn(self.point(),row)
        row['quaternion_wxyz']=[-1.,0.,0.,0.];fn(self.point(),row)
        row['position_m'][0]=2e-12
        with self.assertRaises(ValueError):fn(self.point(),row)

    def test_nonfinite_incomplete_and_bool_pose_rejected(self):
        fn=self.api('check_pose')
        for key,value in [('position_m',[True,0.,-.004]),('position_m',[0.,0.]),
                          ('quaternion_wxyz',[1.,0.,float('nan'),0.]),('quaternion_wxyz',[0.]*4)]:
            row=self.row();row[key]=value
            with self.assertRaises(ValueError):fn(self.point(),row)

    def test_initial_audit_retains_ordinary_no_contact_reset_rule(self):
        fn=self.api('check_initial_state');common=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'))['common']
        facts=dict(simulation_valid=True,invalid_reasons=[],contact_reasons=[],motion_reasons=[])
        self.assertTrue(fn(self.point(),self.row(),common,facts)['passed'])
        for field,value in [('contact_count',1),('penetration_m',2e-9),('velocity_world',[float('nan')]*6),
                            ('contact_wrench_M',[.026,0.,0.,0.,0.,0.])]:
            row=self.row();row[field]=value
            with self.assertRaises(ValueError):fn(self.point(),row,common,facts)

    def test_initial_guard_latch_rejected(self):
        fn=self.api('check_initial_state');common=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'))['common']
        with self.assertRaises(ValueError):fn(self.point(),self.row(),common,
            dict(simulation_valid=False,invalid_reasons=['INVALID_INITIAL_STATE'],contact_reasons=[],motion_reasons=[]))

    def test_draft_wrong_pin_and_changed_limits_rejected(self):
        template=self.api('grant_template');require=self.api('require_grant')
        grant=template('a'*64,'run-one')
        with self.assertRaises(PermissionError):require(grant,'a'*64,'run-one')
        grant.update(explicit_user_authorized=True,human_evidence='fixture only',status='OPEN')
        require(grant,'a'*64,'run-one')
        with self.assertRaises(PermissionError):require(grant,'b'*64,'run-one')
        bad=copy.deepcopy(grant);bad['limits']['resets']=22
        with self.assertRaises(PermissionError):require(bad,'a'*64,'run-one')

    def test_old_grant_version_and_old_total_rejected(self):
        template=self.api('grant_template');require=self.api('require_grant')
        grant=template('a'*64,'run-one');grant.update(explicit_user_authorized=True,human_evidence='fixture only',status='OPEN')
        for key,value in [('version','b2_pure_baseline_grant_v1'),('cumulative_before',254),('retries',1)]:
            bad=copy.deepcopy(grant);bad[key]=value
            with self.assertRaises(PermissionError):require(bad,'a'*64,'run-one')

    def test_valid_stopped_task_failure_advances(self):
        fn=self.api('next_case');row=self.healthy();row['outcome']['task_outcome']='TASK_FAILURE'
        self.assertEqual(fn([row])['id'],'P1')

    def test_guard_invalid_unstopped_missing_receipt_never_advances(self):
        fn=self.api('next_case')
        mutations=[('simulation_valid',False),('physical_stopped',False),('guard_violations',dict(contact=True,motion=False))]
        for key,value in mutations:
            row=self.healthy();row['outcome'][key]=value
            self.assertIsNone(fn([row]))
        for field in ['supervisor','initial_audit','archive_sha256']:
            row=self.healthy();row.pop(field)
            self.assertIsNone(fn([row]))

    def test_nonzero_cost_overrun_and_second_reset_cannot_advance(self):
        fn=self.api('next_case')
        for key,value in [('policy_calls',1),('control_cycles',14501),('physical_substeps',145001),('reset_attempted',2)]:
            row=self.healthy();row[key]=value
            with self.assertRaises(ValueError):fn([row])

    def test_claim_or_wrong_order_cannot_be_retried(self):
        fn=self.api('next_case')
        self.assertIsNone(fn([dict(case_id='D00',status='claimed',healthy=False)]))
        with self.assertRaises(ValueError):fn([self.healthy('P1')])


if __name__=='__main__':unittest.main(verbosity=2)
