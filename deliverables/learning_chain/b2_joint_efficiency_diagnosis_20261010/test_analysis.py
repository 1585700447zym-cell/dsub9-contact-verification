"""Boundary tests for archive evidence, not tests of the trained controller."""
import math,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import analyze as a
SCHEMA=[dict(name='policy_phase',start=53,width=5),dict(name='physical_phase',start=58,width=4)]
def ob(policy=0,physical=0):
    x=[0.]*137;x[53+policy]=1.;x[58+physical]=1.;return x
class ArchiveBoundaryTests(unittest.TestCase):
    def test_input_phase_defines_cycle_not_stale_left_trace(self):
        self.assertEqual(a.phase_of(ob(2),SCHEMA),'SEARCH')
    def test_physical_stop_overrides_latched_policy_phase(self):
        self.assertEqual(a.phase_of(ob(2,1),SCHEMA),'STOPPING')
    def test_invalid_onehot_is_rejected(self):
        x=ob();x[54]=1.
        with self.assertRaises(ValueError):a.phase_of(x,SCHEMA)
    def test_task_cut_keeps_stop_confirmation_and_excludes_audit_tail(self):
        self.assertEqual(a.time_parts([0.,1.,2.,3.,4.],['INSERT','SEARCH','STOPPING','STOPPING'],2.5),
                         {'INSERT':1.,'SEARCH':1.,'STOPPING':.5})
    def test_bad_time_sequence_is_rejected(self):
        with self.assertRaises(ValueError):a.time_parts([0.,1.,.9],['INSERT','SEARCH'],.8)
    def test_forward_back_forward_does_not_duplicate_progress_reward(self):
        first=a.reward_parts(0.,.001,.002,.025,.0005,.004)
        self.assertEqual(first,{'maximum':.001,'terms':{'progress':1.25,'time':-.0002,'force':-.0004,'torque':-.0004,'terminal':0.,'total':1.249}})
        second=a.reward_parts(.001,.0005,.002,0.,0.,.004)
        self.assertIsNotNone(second)
        self.assertEqual(second['terms']['progress'],0.)
    def test_fixed_real_pose_has_zero_path_despite_nonzero_command(self):
        traces=[{'position_m':[0.,0.,0.],'reference_qpos':[0.,0.,0.]},{'position_m':[0.,0.,0.],'reference_qpos':[.0001,0.,0.]}]
        result=a.motion_stats(traces,[{'actual_end_limited_command':[.0001,0.,0.,0.,0.,0.]}],[{'dt':1.}])
        self.assertIsNotNone(result)
        self.assertEqual(result['actual_xy_path_um'],0.)
        self.assertEqual(result['reference_xy_path_um'],100.)
        self.assertEqual(result['total_command_xy_integral_um'],[100.,0.])
    def test_archive_action_transition_trace_alignment_rejected(self):
        with self.assertRaises(ValueError):a.validate_alignment({'control_cycles':2,'actions':[{}],'transitions':[{'dt':1.}]*2,'trace':[{'time_s':0.},{'time_s':1.},{'time_s':2.}]})
if __name__=='__main__':unittest.main(verbosity=2)
