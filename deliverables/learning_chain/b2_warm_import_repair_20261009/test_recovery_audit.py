from copy import deepcopy
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parent))
from recovery_audit import inspect_warmup

def fixture():
    held=[.25,-.25,.5,-.5];rows=[]
    for i in range(4):
        active=i<2;action=held.copy() if active else [0.]*4
        rows.append(dict(observation=[0.]*137,next_observation=[0.]*137,action=action,
            action_active=active,next_action_active=i<1,reward=1.,discount=.9,dt=.002,
            terminated=i==3,truncated=False,sampling_request=held.copy(),
            action_log=dict(raw_action=action.copy(),experience_action=action.copy(),enabled=active)))
    outcome=dict(simulation_valid=True,physical_stopped=True,valid_for_learning=True,task_outcome='FULL_SUCCESS',guard_violations={'contact':False,'motion':False})
    raw=dict(episode_id='warmup_F50_J01',case_id='J01',case_index=0,stage='warmup',mode='F50',seed=2026092716,
        optimizer_steps=0,optimizer_steps_start=0,warmup_draws=1,control_cycles=4,policy_calls=0,
        fault=None,outcome=outcome,policy_sha256='a'*64,transitions=rows)
    receipt=dict(episode_id=raw['episode_id'],stage='warmup',case_index=0,optimizer_steps=0,
        policy_sha256=raw['policy_sha256'],steps=4,committed=4,outcome=deepcopy(outcome))
    return raw,receipt

class RecoveryTests(unittest.TestCase):
    def test_wrong_episode_or_nonzero_update_rejected(self):
        raw,r=fixture();raw['optimizer_steps']=1
        with self.assertRaises(ValueError):inspect_warmup(raw,r,'warmup_F50_J01',0)
        raw,r=fixture()
        with self.assertRaises(ValueError):inspect_warmup(raw,r,'warmup_F50_J02',0)

    def test_held_request_mutation_rejected(self):
        raw,r=fixture();raw['transitions'][1]['sampling_request'][0]=.3
        with self.assertRaises(ValueError):inspect_warmup(raw,r,'warmup_F50_J01',0)

    def test_receipt_or_draw_count_conflict_rejected(self):
        raw,r=fixture();r['committed']=3
        with self.assertRaises(ValueError):inspect_warmup(raw,r,'warmup_F50_J01',0)
        raw,r=fixture();raw['warmup_draws']=2
        with self.assertRaises(ValueError):inspect_warmup(raw,r,'warmup_F50_J01',0)

    def test_missing_or_truncated_terminal_rejected(self):
        for terminated,truncated in ((False,False),(False,True),(True,True)):
            raw,r=fixture();raw['transitions'][-1].update(terminated=terminated,truncated=truncated)
            with self.assertRaises(ValueError):inspect_warmup(raw,r,'warmup_F50_J01',0)

    def test_discontinuous_or_nonfinite_observation_rejected(self):
        raw,r=fixture();raw['transitions'][2]['observation'][0]=1.
        with self.assertRaises(ValueError):inspect_warmup(raw,r,'warmup_F50_J01',0)
        raw,r=fixture();raw['transitions'][0]['observation'][0]=float('nan')
        with self.assertRaises(ValueError):inspect_warmup(raw,r,'warmup_F50_J01',0)

    def test_unpermitted_nonzero_action_rejected(self):
        raw,r=fixture();raw['transitions'][-1]['action'][0]=.1
        with self.assertRaises(ValueError):inspect_warmup(raw,r,'warmup_F50_J01',0)

    def test_complete_fixture_preserves_boundary_and_draws(self):
        raw,r=fixture();before=deepcopy(raw)
        result=inspect_warmup(raw,r,'warmup_F50_J01',0)
        self.assertEqual((result['rows'],result['active_rows'],result['warm_draws']),(4,2,1))
        self.assertEqual(result['held'],[.25,-.25,.5,-.5]);self.assertEqual(result['last_active_row'],1)
        self.assertAlmostEqual(result['tail_return_at_boundary'],2.71)
        self.assertEqual(raw,before)

if __name__=='__main__':unittest.main(verbosity=2)
