"""Run pinned production prepare/resume/observation logic on a nonphysical double.

Imports inside selected definitions are removed, and their pure dependencies
are explicitly supplied. No environment/session constructor or native call.
"""
import ast
from copy import deepcopy
from dataclasses import dataclass,field,asdict
from pathlib import Path
from types import SimpleNamespace as NS
import sys
import unittest
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from scope_contract import ROOT,read,sha,proposal
from offline_math import numerics
from recovery_fixture import RecoveryFixture,session_type

def selected(path,class_name,method,namespace):
    pins=read(ROOT/'deliverables/paper_comparison/small_boundary_numeric_execution_20261008/prior_source_bindings.json')['production_inputs']
    assert sha(ROOT/path)==pins[path]
    tree=ast.parse((ROOT/path).read_text(encoding='utf-8-sig'))
    nodes=tree.body if class_name is None else next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==class_name).body
    node=deepcopy(next(n for n in nodes if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name==method))
    class NoImports(ast.NodeTransformer):
        def visit_Import(self,n):return None
        def visit_ImportFrom(self,n):return None
    node=NoImports().visit(node)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(ROOT/path),'exec'),namespace)
    return namespace[method]

def harness():
    ns=dict(numerics());np=ns['np'];ns.update(dataclass=dataclass,field=field,deepcopy=deepcopy)
    snapshot=selected('tools/learning/types.py',None,'CycleSnapshot',ns)
    selected('tools/control/search_recovery.py',None,'latched_contact_guard',ns)
    selected('tools/control/search_recovery.py',None,'resume_after_recovery',ns)
    selected('tools/validation/run_b2_search.py',None,'stable_for_recovery',ns)
    prepare=selected('tools/learning/session.py','EpisodeSession','prepare_cycle',ns)
    finish=selected('tools/learning/session.py','EpisodeSession','_finish',ns)
    ns['LayeredReferenceSession']=NS(prepare_cycle=prepare)
    decorate=selected('tools/learning/v4_session.py','V4ResidualSession','_prepare_residual',ns)
    common=read(ROOT/proposal()['parent']['configuration'])['common']
    seed=read(OUT/'offline_seed.json');state=deepcopy(seed['snapshot']['state']);ctrl=deepcopy(seed['snapshot']['controller_state'])
    time0=seed['snapshot']['time_s'];initial=seed['initial'];cfg=NS(**common['dynamic_config'])
    facts=dict(simulation_valid=True,contact_reasons=[],motion_reasons=[],invalid_reasons=[],checked_substeps=0,max_rotation_from_start_rad=0.)
    env=NS(config=cfg,data=NS(time=time0,qpos=np.array(state['position_m']+state['quaternion_wxyz']),qvel=np.zeros(6)),
        phase='RUNNING',reference=np.array(state['reference_qpos']),command=np.array(state['limited_command_world']),
        raw_command=np.array(state['raw_command_world']),physical_steps=0,recovery_count=0,recovery_start=None,
        events=[],guard_facts=facts,peaks=dict(force_N=.01,torque_G_Nm=0.,penetration_m=0.))
    def observe():
        return dict(deepcopy(state),time_s=env.data.time,phase=env.phase,position_m=env.data.qpos[:3].tolist(),
            quaternion_wxyz=env.data.qpos[3:].tolist(),velocity_world=env.data.qvel.tolist())
    env.observe=observe;env._state_valid=lambda:True
    def stop(reason):
        env.phase='STOPPING';env.reference=env.data.qpos.copy();env.command[:]=0
        env.events.append(dict(time_s=env.data.time,phase=env.phase,reason=reason))
    env.stop=stop
    def request():
        if facts['contact_reasons'] or facts['motion_reasons'] or env.recovery_count:raise RuntimeError('blocked recovery')
        env.phase='RETRACT';env.recovery_count+=1;env.recovery_start=env.data.qpos.copy()
        env.events.append(dict(time_s=env.data.time,phase=env.phase,reason='RECOVERY_ACCEPTED'))
    env.request_recovery=request
    class Base:
        _prepare_residual=decorate
        _finish=finish
        def prepare_cycle(self):return self._prepare_residual()
        def stage_permission(self,phase,enabled):return bool(enabled and phase in ('INSERT','SEARCH'))
    session=session_type(Base)()
    session.__dict__.update(env=env,reason=None,guard_latched=False,done=False,task_finished=False,recovery_state=None,
        wait_start=None,stop_time=None,hold_start=None,cycle_id=0,_ready=True,_features_ready=True,_cache=None,
        _decorated_cache=None,previous_residual=[0.]*4,last_action_log={},case=NS(name='offline'),
        observations=ns['V4ObservationBuilder'](initial,NS(**common['b2_config'])),fixture=RecoveryFixture())
    command_calls=[];observed_reference=[]
    def command(obs,dt):command_calls.append(obs);return np.array([.0001,0,0,0,0,0])
    def transition(phase,obs,reason):
        ctrl.update(phase=phase,phase_start=obs.time_s,search_composition=None)
        ctrl['events'].append(dict(phase=phase,time_s=obs.time_s,reason=reason))
    def start(obs):
        observed_reference.append(obs.reference.copy());ctrl.update(phase='SEARCH',search_count=2,phase_start=obs.time_s,
            search_origin=obs.displacement_m,search_progress_origin_z_m=max(ctrl['episode_peak_z_m'],obs.displacement_m[2]))
    class Controller(NS):
        def __getattr__(self,name):
            if name in ctrl:return ctrl[name]
            raise AttributeError(name)
    session.controller=Controller(config=NS(**common['b2_config']),command=command,_transition=transition,start_recovered_search=start)
    session.controller_state_snapshot=lambda:deepcopy(ctrl)
    session.policy_observation=lambda row:NS(time_s=row['time_s'],reference=env.reference.copy(),
        displacement_m=(np.array(row['position_m'])-initial['position_m']).tolist())
    return session,ns,state,command_calls,observed_reference

class LifecycleTests(unittest.TestCase):
    def test_real_prepare_decorator_does_not_double_baseline_or_history(self):
        s,ns,state,calls,_=harness();physical_before=s.env.data.qpos.copy()
        snap=s.prepare_cycle();history=deepcopy(s.observations.base._history)
        self.assertEqual(len(calls),1);self.assertEqual(snap.controller_state['phase'],'WAIT_RECOVERY')
        self.assertFalse(snap.residual_enabled);self.assertEqual(len(snap.policy_observation),137)
        self.assertEqual(snap.policy_raw['recovery_phase'],[0.,1.,0.,0.])
        s.prepare_cycle();self.assertEqual(len(calls),1);self.assertEqual(history,s.observations.base._history)
        self.assertEqual(physical_before.tolist(),s.env.data.qpos.tolist());self.assertEqual(s.env.physical_steps,0)
        self.assertEqual(s.fixture.action(snap,s.recovery_state),[1.,-1.,1.,-1.])

    def test_real_resume_uses_fresh_reference_and_single_pulse(self):
        s,ns,state,calls,refs=harness();s.prepare_cycle()
        state.update(contact_wrench_M=[0.]*6,contact_wrench_G=[0.]*6,penetration_m=0.)
        s.env.data.qvel[:]=0;s._cache=None;s.cycle_id+=1;s.env.data.time+=.002
        retract=s.prepare_cycle();self.assertEqual(s.recovery_state,'RETRACT')
        s.env.data.qpos[2]-=.00025;s.env.data.time+=.55;s.cycle_id+=1
        s.env.stop('RECOVERY_DISTANCE_REACHED');s.recovery_state='WAIT_RESUME';s._cache=None
        resumed=s.prepare_cycle()
        self.assertEqual(refs[0].tolist(),s.env.data.qpos.tolist());self.assertEqual(len(calls),2)
        self.assertTrue(resumed.residual_enabled);self.assertEqual(resumed.controller_state['search_count'],2)
        self.assertEqual(s.fixture.action(resumed,s.recovery_state),[.1,-.1,.1,-.1])
        self.assertEqual(s.fixture.action(resumed,s.recovery_state),[0.]*4)
        self.assertEqual(s.env.physical_steps,0)

    def test_real_wait_stop_rejection_and_timeout(self):
        for kind in ('reject','timeout','latched'):
            s,ns,state,calls,_=harness();s.prepare_cycle();s._cache=None;s.cycle_id+=1
            state.update(contact_wrench_M=[0.]*6,contact_wrench_G=[0.]*6,penetration_m=0.)
            if kind=='reject':s.env.request_recovery=lambda:(_ for _ in ()).throw(RuntimeError('no entitlement'))
            if kind=='timeout':s.env.data.qvel[:]=1;s.env.data.time+=2
            if kind=='latched':s.env.guard_facts['contact_reasons']=['FORCE_LIMIT']
            snap=s.prepare_cycle()
            self.assertFalse(snap.residual_enabled);self.assertEqual(len(calls),1)
            self.assertEqual(s.reason,'RECOVERY_NOT_STABLE' if kind=='timeout' else 'RECOVERY_REJECTED')
            self.assertEqual(s.env.recovery_count,0)

    def test_real_resume_rejects_too_short_or_historical_guard(self):
        for kind in ('short','guard'):
            s,ns,state,calls,refs=harness();s.prepare_cycle()
            state.update(contact_wrench_M=[0.]*6,contact_wrench_G=[0.]*6,penetration_m=0.)
            s.env.request_recovery();s.env.data.qpos[2]-=.0001 if kind=='short' else .00025
            s.env.stop('RECOVERY_DISTANCE_REACHED');s.recovery_state='WAIT_RESUME';s._cache=None;s.cycle_id+=1
            if kind=='guard':s.env.events.append(dict(time_s=s.env.data.time,reason='FORCE_LIMIT',phase='STOPPING'))
            snap=s.prepare_cycle();self.assertEqual(s.reason,'RECOVERY_RESUME_REJECTED')
            self.assertFalse(snap.residual_enabled);self.assertFalse(refs);self.assertEqual(len(calls),1)

    def protocol_archive(self):
        s,ns,state,_,_=harness();observations={};capture=s.observations.capture
        def record(snapshot,context,*,refresh=False):
            observations[snapshot.cycle_id]=dict(snapshot=asdict(snapshot),context=deepcopy(context))
            return capture(snapshot,context,refresh=refresh)
        s.observations.capture=record
        snaps=[s.prepare_cycle()]
        state.update(contact_wrench_M=[0.]*6,contact_wrench_G=[0.]*6,penetration_m=0.)
        s.env.data.qvel[:]=0;s._cache=None;s.cycle_id+=1;s.env.data.time+=.002
        snaps.append(s.prepare_cycle())
        s.env.data.qpos[2]-=.00025;s.env.data.time+=.55;s.cycle_id+=1
        s.env.stop('RECOVERY_DISTANCE_REACHED');s.recovery_state='WAIT_RESUME';s._cache=None
        snaps.append(s.prepare_cycle())
        rows=[]
        for snap,action in zip(snaps,([1.,-1.,1.,-1.],[1.,-1.,1.,-1.],[.1,-.1,.1,-.1])):
            _,log=ns['compose_continuation_command'](snap.base_command,action,phase=snap.controller_state['phase'],
                enabled=snap.residual_enabled,previous_limited=[0.]*6,dt=.002,reference_xy=[0.,0.],
                radius=.00012,next_theta=snap.controller_state['theta'],search_config=s.controller.config)
            rows.append(dict(before=asdict(snap),requested=list(action),result={'action_log':log}))
        return dict(cycles=rows,observations=[observations[i] for i in range(3)],
            fixture_events=deepcopy(s.fixture.events),recovery_transitions=deepcopy(s.fixture.transitions),
            events=deepcopy(s.env.events),initial=read(OUT/'offline_seed.json')['initial'])

    def test_recovery_auditor_accepts_logic_fixture_and_rejects_mutations(self):
        from coverage_checks import audit_protocol
        from assess import same
        raw=self.protocol_archive();spec={'profile':'R_RECOVERY'}
        result=audit_protocol(raw,spec,same)
        self.assertTrue(result['recovery']['covered']);self.assertEqual(result['recovery']['masked_cycles'],2)
        for mutation in ('pose','double_baseline','mask','reanchor','short','pulse','skip_trigger'):
            bad=deepcopy(raw)
            if mutation=='pose':bad['fixture_events'][0]['live_after']['qpos'][0]+=.001
            if mutation=='double_baseline':bad['fixture_events'][0]['after']['controller_state']['theta']+=.001
            if mutation=='mask':bad['cycles'][0]['result']['action_log']['experience_action']=[1.]*4
            if mutation=='reanchor':bad['recovery_transitions'][-1]['live']['reference'][0]+=.001
            if mutation=='short':bad['recovery_transitions'][-1]['live']['qpos'][2]+=.0002
            if mutation=='pulse':bad['cycles'][2]['requested']=[0.]*4
            if mutation=='skip_trigger':bad['fixture_events']=[]
            with self.assertRaises((ValueError,KeyError),msg=mutation):audit_protocol(bad,spec,same)

    def test_untriggered_natural_recovery_is_insufficient_not_fake_audit_failure(self):
        from coverage_checks import audit_protocol
        from assess import same
        raw=self.protocol_archive();raw['fixture_events']=[]
        for c in raw['cycles']:c['requested']=[0.]*4
        result=audit_protocol(raw,{'profile':'R_RECOVERY'},same)
        self.assertFalse(result['recovery']['covered'])

if __name__=='__main__':
    unittest.main(verbosity=2)
