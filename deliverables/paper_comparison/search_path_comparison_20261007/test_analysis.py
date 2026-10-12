"""Hand-calculated archive cases; no simulation or policy imports."""
import importlib.util
from pathlib import Path
import unittest


def module():
    path=Path(__file__).with_name('analyze.py')
    if not path.exists():
        raise AssertionError('Pure archive analyzer is not implemented')
    spec=importlib.util.spec_from_file_location('pc10_archive_analysis',path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


def fixture():
    phases=['UNLOAD','SEARCH','SEARCH','WAIT_RECOVERY','SEARCH','FAILED']
    times=[0.,.1,.3,.6,.7,.9,1.]
    xy=[[0.,0.],[0.,0.],[3e-6,4e-6],[3e-6,8e-6],[3e-6,8e-6],[3e-6,8e-6],[3e-6,8e-6]]
    ref=[[0.,0.],[0.,0.],[2e-6,0.],[5e-6,0.],[5e-6,0.],[7e-6,0.],[7e-6,0.]]
    trace=[dict(time_s=t,position_m=[*p,0.],reference_qpos=[*q,0.,1.,0.,0.,0.],
        quaternion_wxyz=[1.,0.,0.,0.],velocity_world=[0.]*6,contact_wrench_M=[0.]*6,
        spiral_theta_rad=float(i),search_progress_origin_z_m=0.,policy_phase='UNLOAD',search_composition=None)
        for i,(t,p,q) in enumerate(zip(times,xy,ref))]
    transitions=[];actions=[]
    for i,phase in enumerate(phases):
        active=phase=='SEARCH';ob=[0.]*137;ob[53+['INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED'].index(phase)]=1.
        ob[99]=float(i)/18.84955592153876
        transitions.append(dict(observation=ob,dt=times[i+1]-times[i],action_active=active,cycle_force_N=0.))
        cmd=[1e-5,0.,0.,0.,0.,0.] if active else [0.]*6
        actions.append(dict(enabled=active,raw_action=[.2,0.,0.,0.],applied_residual=cmd,
            unfiltered_stage_limited_total=cmd,actual_end_limited_command=cmd,predicted_limited_command=cmd,
            reference_filter_fraction=1.,reference_checked=active,
            reference_xy_m=ref[i],predicted_reference_xy_m=ref[i+1]))
    return dict(actions=actions,transitions=transitions,trace=trace,control_cycles=6,
        observation_schema=[dict(name='policy_phase',start=53,width=5),dict(name='spiral_theta_rad',start=99,width=1,scale=[18.84955592153876])])


class ArchiveTests(unittest.TestCase):
    def test_action_before_phase_and_separate_searches(self):
        self.assertEqual(module().search_segments(fixture()),[(1,3),(4,5)])

    def test_variable_dt_actual_motion_differs_from_command(self):
        result=module().segment_metrics(fixture(),1,3)
        self.assertAlmostEqual(result['duration_s'],.5)
        self.assertAlmostEqual(result['actual_xy_path_um'],9.)
        self.assertEqual(result['actual_xy_net_um'],[3.,8.])
        self.assertAlmostEqual(result['total_command_xy_integral_um'][0],5.)
        self.assertAlmostEqual(result['reference_xy_path_um'],5.)

    def test_boundary_is_120um_reference_not_actual_xy(self):
        event=dict(reference_xy_m=[119e-6,0.],predicted_reference_xy_m=[121e-6,0.],radius_limit_m=120e-6)
        result=module().boundary_recheck(event,dict(reference_qpos=[119e-6,0.,0.,1.,0.,0.,0.],position_m=[0.,0.,0.]))
        self.assertTrue(result['current_inside'])
        self.assertTrue(result['next_outside'])
        self.assertAlmostEqual(result['next_excess_nm'],1000.)

    def test_bad_alignment_and_nonfinite_dt_are_rejected(self):
        r=fixture();r['trace'].pop()
        with self.assertRaises(ValueError):module().search_segments(r)
        r=fixture();r['transitions'][1]['dt']=float('nan')
        with self.assertRaises(ValueError):module().segment_metrics(r,1,3)

    def test_explicit_recovery_reference_reset_is_not_command_error(self):
        r=fixture();r['trace'][1]['phase']='STOPPING';r['trace'][2]['phase']='RUNNING'
        r['trace'][1]['reference_qpos'][2]=4e-6
        r['events']=[dict(time_s=.1,reason='B2_RECOVERY_RESUMED')]
        self.assertLess(module().reference_integration_error(r,1),1e-14)
        r['events']=[]
        self.assertGreater(module().reference_integration_error(r,1),3e-6)

    def test_reference_direction_uses_secant_tracking_and_slew(self):
        result=module().reference_next(0.,[0.,0.],[0.,0.],.002)
        self.assertAlmostEqual(result['limited_xy_um_s'][0],10.)
        self.assertAlmostEqual(result['limited_xy_um_s'][1],7.065967606446397)
        self.assertAlmostEqual(result['next_reference_xy_um'][0],.02)


if __name__=='__main__':unittest.main()
