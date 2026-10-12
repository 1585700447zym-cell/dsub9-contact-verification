import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import unittest
from copy import deepcopy
from scope_contract import profile_action
from coverage_checks import action_coverage,matrix_route,audit_protocol

def row(i,action=None,contact=1,effect=True):
    action=profile_action('A_AXIS',i,True) if action is None else action
    delta=[action[0]*.00005,action[1]*.00005,0,action[2]*.0005,action[3]*.0005,0] if effect else [0]*6
    return dict(before=dict(cycle_id=i,residual_enabled=True,time_s=i*.002,state={'phase':'RUNNING'},controller_state={'phase':'INSERT'}),
        requested=action,result=dict(trace_row={'contact_count':contact},cycle_peaks=dict(force_N=.01,torque_G_Nm=.001,penetration_m=.00001),
        action_log=dict(effective_command_delta=delta,applied_residual=delta,experience_action=action)))
def raw():return dict(cycles=[row(i) for i in range(408)],peaks=dict(force_N=.01,torque_G_Nm=.001,penetration_m=.00001),fixture_events=[])

class CoverageTests(unittest.TestCase):
    def test_directions_hold_blocks_and_all_peak_ties(self):
        result=action_coverage(raw(),{'profile':'A_AXIS'})
        self.assertEqual(result['signs'],[[-1,1]]*4)
        self.assertEqual(result['hold_contact_effect_cycles'],{'50':400,'1':8})
        self.assertTrue(result['peaks']['force_N']['covered'])
        changed=raw();changed['cycles'][200]['result']['action_log']['effective_command_delta']=[0]*6
        self.assertFalse(action_coverage(changed,{'profile':'A_AXIS'})['peaks']['force_N']['covered'])
    def test_request_without_effect_is_not_coverage(self):
        changed=raw()
        for r in changed['cycles']:r['result']['action_log']['effective_command_delta']=[0]*6
        self.assertEqual(action_coverage(changed,{'profile':'A_AXIS'})['signs'],[[]]*4)
        changed=raw()
        for r in changed['cycles'][400:]:r['result']['trace_row']['contact_count']=0
        self.assertEqual(action_coverage(changed,{'profile':'A_AXIS'})['hold_contact_effect_cycles']['1'],0)
    def test_protocol_rejects_schedule_shift_or_fixture_on_A(self):
        from assess import same
        changed=raw();changed['cycles'][50]['requested']=[1,0,0,0]
        with self.assertRaises(ValueError):audit_protocol(changed,{'profile':'A_AXIS'},same)
        changed=raw();changed['fixture_events']=[{}]
        with self.assertRaises(ValueError):audit_protocol(changed,{'profile':'A_AXIS'},same)
    def test_routes_separate_task_failure_and_missing_coverage(self):
        coverage=action_coverage(raw(),{'profile':'A_AXIS'});rows=[]
        for profile in ('A_AXIS','B_CORNERS','R_RECOVERY'):
            for case in range(1,5):rows.append(dict(id=f'J{case:02}_{profile}',case_id=f'J{case:02}',profile=profile,
                status='finished',audit_passed=True,outcome=dict(simulation_valid=True,physical_stopped=True,
                task_outcome='FULL_SUCCESS',guard_violations={'contact':False,'motion':False}),
                joint_coverage=coverage,recovery={'covered':True}))
        self.assertEqual(matrix_route(rows),'READY_FOR_SEPARATE_SAC_REGISTRATION')
        rows[-1]['outcome']['task_outcome']='TASK_FAILURE'
        self.assertEqual(matrix_route(rows),'REVIEW_TASK_FAILURE_NO_TRAINING')
        rows[-1]['outcome']['task_outcome']='FULL_SUCCESS';rows[-1]['recovery']['covered']=False
        self.assertEqual(matrix_route(rows),'INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS')
        rows[0]['outcome']['guard_violations']['motion']=True
        self.assertEqual(matrix_route(rows),'NO_SCOPE_QUALIFICATION')

if __name__=='__main__':unittest.main(verbosity=2)
