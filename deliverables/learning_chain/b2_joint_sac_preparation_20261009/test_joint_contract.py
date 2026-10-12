"""Pure tests: no native runtime, learner construction, or archived replay publication."""
from pathlib import Path
import copy
import math
import sys
import unittest
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from joint_contract import training_cases,case_kwargs,check_initial_pose,validate_raw_identity,learning_config,validate_config,schedule,advance,metric


class JointContractTests(unittest.TestCase):
    def test_four_signed_tilts_reach_constructor_and_reset_check(self):
        expected=[(75,75,1,1),(-75,75,-1,1),(-75,-75,-1,-1),(75,-75,1,-1)]
        for c,(x,y,r,p) in zip(training_cases(),expected):
            kw=case_kwargs(c)
            self.assertAlmostEqual(kw['x_offset_m'],x*1e-6)
            self.assertAlmostEqual(kw['y_offset_m'],y*1e-6)
            self.assertAlmostEqual(kw['roll_rad'],r*0.004363323129985824)
            self.assertAlmostEqual(kw['pitch_rad'],p*0.004363323129985824)
            half=math.pi/1440
            row=dict(position_m=[x*1e-6,y*1e-6,-.004],quaternion_wxyz=[math.cos(half)**2,r*math.sin(half)*math.cos(half),p*math.sin(half)*math.cos(half),-r*p*math.sin(half)**2])
            self.assertTrue(check_initial_pose(c,row))
            row['quaternion_wxyz']=[1,0,0,0]
            with self.assertRaises(ValueError):check_initial_pose(c,row)

    def test_old_case_or_zero_angle_transcript_never_reaches_replay(self):
        c=training_cases()[0];kw=case_kwargs(c)
        raw=dict(case=c,case_id='J01',case_index=0,simulation_case=kw,
            trace=[dict(position_m=[.000075,.000075,-.004],quaternion_wxyz=[math.cos(math.pi/1440)**2,math.sin(math.pi/1440)*math.cos(math.pi/1440),math.sin(math.pi/1440)*math.cos(math.pi/1440),-math.sin(math.pi/1440)**2])])
        validate_raw_identity(raw)
        bad=copy.deepcopy(raw);bad['simulation_case']['roll_rad']=0
        with self.assertRaises(ValueError):validate_raw_identity(bad)
        bad=copy.deepcopy(raw);bad['case']['id']='boundary_y_neg_150'
        with self.assertRaises(ValueError):validate_raw_identity(bad)

    def test_joint_config_rejects_old_task_and_wrong_method(self):
        cfg=learning_config();validate_config(cfg)
        for key,value in [('mode','S50'),('joint_cases',[])]:
            bad=copy.deepcopy(cfg);bad[key]=value
            with self.assertRaises(ValueError):validate_config(bad)
        bad=copy.deepcopy(cfg);bad.pop('joint_cases')
        with self.assertRaises(ValueError):validate_config(bad)

    def test_failure_closes_sequence_and_cannot_skip_to_next_case(self):
        plan=schedule();self.assertEqual(len(plan),17)
        self.assertEqual([x['stage'] for x in plan],['zero']*4+['warmup']*4+['online']*4+['final']*4+['restore'])
        records=[]
        for spec in plan:
            self.assertEqual(advance(records)['id'],spec['id'])
            records.append(dict(id=spec['id'],healthy=True))
        self.assertIsNone(advance(records))
        self.assertIsNone(advance([dict(id='zero_F50_J01',healthy=False)]))
        with self.assertRaises(ValueError):advance([dict(id='zero_F50_J02',healthy=True)])

    def test_failure_penalty_cannot_reward_fast_failure_or_missing_case(self):
        rows=[dict(case_id=c,simulation_valid=True,physical_stopped=True,task_outcome='FULL_SUCCESS',task_time_s=t,guard=False) for c,t in zip(['J01','J02','J03','J04'],[8,9,10,11])]
        self.assertEqual(metric(rows)['mean_penalized_time_s'],9.5)
        rows[0].update(task_outcome='TASK_FAILURE',task_time_s=.1)
        self.assertEqual(metric(rows)['mean_penalized_time_s'],14.0)
        rows[0]['simulation_valid']=False
        self.assertFalse(metric(rows)['comparable'])
        with self.assertRaises(ValueError):metric(rows[:3])


if __name__=='__main__':unittest.main(verbosity=2)
