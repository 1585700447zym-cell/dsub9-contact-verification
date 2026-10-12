"""Pure logic contracts; never import the physical backend."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from scope_contract import proposal, attempt_specs, profile_action, next_attempt
from recovery_fixture import RecoveryFixture
from types import SimpleNamespace as NS
from copy import deepcopy


class ContractTests(unittest.TestCase):
    def test_axis_and_corner_periods(self):
        self.assertEqual(profile_action('A_AXIS',0,True),[1,0,0,0])
        self.assertEqual(profile_action('A_AXIS',49,True),[1,0,0,0])
        self.assertEqual(profile_action('A_AXIS',50,True),[-1,0,0,0])
        self.assertEqual(profile_action('A_AXIS',400,True),[1,0,0,0])
        self.assertEqual(profile_action('A_AXIS',407,True),[0,0,0,-1])
        self.assertEqual(profile_action('A_AXIS',408,True),[1,0,0,0])
        self.assertEqual(profile_action('B_CORNERS',0,True),[-1]*4)
        self.assertEqual(profile_action('B_CORNERS',799,True),[1]*4)
        self.assertEqual(profile_action('B_CORNERS',801,True),[-1,-1,-1,1])
        self.assertEqual(profile_action('B_CORNERS',816,True),[-1]*4)

    def test_mask_does_not_pause_index(self):
        self.assertEqual(profile_action('A_AXIS',51,False),[0]*4)
        self.assertEqual(profile_action('A_AXIS',52,True),[-1,0,0,0])
        for cycle in (-1,True,1.1):
            with self.assertRaises(ValueError):profile_action('A_AXIS',cycle,True)

    def test_fixed_order_and_guard_closure(self):
        c=proposal();specs=attempt_specs(c)
        self.assertEqual([s['id'] for s in specs],
            [f'J{i:02d}_{profile}' for profile in ('A_AXIS','B_CORNERS','R_RECOVERY') for i in range(1,5)])
        entries=[]
        for spec in specs:
            self.assertEqual(next_attempt(entries,c),spec)
            entries.append(dict(id=spec['id'],kind='dynamic',status='finished',audit_passed=True,
                outcome=dict(simulation_valid=True,physical_stopped=True,task_outcome='TASK_FAILURE',guard_violations={'contact':False,'motion':False})))
        self.assertIsNone(next_attempt(entries,c))
        entries[0]['outcome']['guard_violations']['contact']=True
        self.assertIsNone(next_attempt(entries[:1],c))


class FixtureTests(unittest.TestCase):
    def state(self):
        sensor=dict(time_s=1.1,phase='RUNNING',contact_count=2,position_m=[1,2,3],velocity_world=[0]*6)
        ctrl=dict(phase='SEARCH',phase_start=1.,search_count=1,history=[[.8,0]],events=[])
        snap=NS(cycle_id=550,time_s=1.1,controller_state=deepcopy(ctrl),state=deepcopy(sensor),
                residual_enabled=True,base_command=[1]*6)
        session=NS(reason=None,guard_latched=False,done=False,task_finished=False,recovery_state=None,wait_start=None,
                   _cache=snap,_decorated_cache=snap)
        session.env=NS(phase='RUNNING',guard_facts=dict(simulation_valid=True,contact_reasons=[],motion_reasons=[],invalid_reasons=[]),
                       recovery_count=0,events=[],observe=lambda:deepcopy(sensor))
        def stop(reason):
            session.env.phase=sensor['phase']='STOPPING';session.env.events.append(dict(reason=reason,time_s=1.1,phase='STOPPING'))
        session.env.stop=stop
        def transition(phase,obs,reason):ctrl.update(phase=phase,phase_start=obs.time_s);ctrl['events'].append(dict(phase=phase,time_s=obs.time_s,reason=reason))
        session.controller=NS(_transition=transition)
        session.policy_observation=lambda row:NS(time_s=row['time_s'])
        session.controller_state_snapshot=lambda:deepcopy(ctrl)
        return session,snap,sensor

    def test_once_refresh_and_no_sensor_change(self):
        session,snap,sensor=self.state();calls=[];fixture=RecoveryFixture()
        def refresh():calls.append(1);return deepcopy(session._cache)
        before=deepcopy(sensor)
        result=fixture.prepare(session,snap,refresh)
        self.assertFalse(result.residual_enabled);self.assertEqual(result.base_command,[0]*6)
        self.assertEqual(result.controller_state['phase'],'WAIT_RECOVERY')
        self.assertEqual(session.recovery_state,'WAIT_STOP');self.assertEqual(calls,[1])
        for key in ('position_m','velocity_world','time_s','contact_count'):self.assertEqual(before[key],sensor[key])
        fixture.prepare(session,result,refresh);self.assertEqual(len(calls),1)
        self.assertEqual(fixture.action(result,'WAIT_STOP'),[1,-1,1,-1])
        result.residual_enabled=True;result.state['phase']='RUNNING';result.controller_state.update(phase='SEARCH',search_count=2)
        self.assertEqual(fixture.action(result,None),[.1,-.1,.1,-.1])
        self.assertEqual(fixture.action(result,None),[0]*4)

    def test_no_trigger_on_pending_guard_or_no_contact(self):
        for bad in ('pending','guard','contact','early','second','invalid','latched','done'):
            session,snap,_=self.state();fixture=RecoveryFixture()
            if bad=='pending':session.reason='TIME_LIMIT'
            if bad=='guard':session.env.guard_facts['contact_reasons']=['FORCE_LIMIT']
            if bad=='contact':snap.state['contact_count']=0
            if bad=='early':snap.time_s=1.01
            if bad=='second':snap.controller_state['search_count']=2
            if bad=='invalid':session.env.guard_facts['simulation_valid']=False
            if bad=='latched':session.guard_latched=True
            if bad=='done':session.done=True
            self.assertIs(fixture.prepare(session,snap,lambda:self.fail('unexpected refresh')),snap,bad)
            self.assertFalse(fixture.events)

    def test_rejected_recovery_does_not_force_resume(self):
        session,snap,_=self.state();fixture=RecoveryFixture()
        stopped=fixture.prepare(session,snap,lambda:deepcopy(session._cache))
        session.reason='RECOVERY_NOT_STABLE';session.recovery_state=None
        self.assertEqual(fixture.action(stopped,None),[0]*4)
        self.assertFalse(fixture.resumed_pulse)


if __name__=='__main__':unittest.main(verbosity=2)
