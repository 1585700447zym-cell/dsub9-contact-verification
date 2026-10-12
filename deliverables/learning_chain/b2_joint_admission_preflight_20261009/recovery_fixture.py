"""One-shot engineering fixture; no engine import and no recovery bypass."""
from copy import deepcopy
from dataclasses import asdict,is_dataclass

def snapshot_dict(s):return asdict(s) if is_dataclass(s) else deepcopy(vars(s))

def live_state(env):
    """Read-only physical state evidence; never infer it from phase names."""
    if not hasattr(env,'data'):return None  # Minimal pure logic doubles only.
    return dict(time_s=float(env.data.time),qpos=env.data.qpos.tolist(),qvel=env.data.qvel.tolist(),
        reference=env.reference.tolist(),command=env.command.tolist(),raw_command=env.raw_command.tolist(),
        physical_steps=env.physical_steps,recovery_count=env.recovery_count,
        recovery_start=None if env.recovery_start is None else env.recovery_start.tolist(),
        guard_facts=deepcopy(env.guard_facts),phase=env.phase)

def eligible(snapshot,*,reason,guard_latched,done,task_finished,recovery_state,facts,recovery_count):
    c=snapshot.controller_state
    return (reason is None and not guard_latched and not done and not task_finished and recovery_state is None
        and facts['simulation_valid'] is True and not any(facts[k] for k in ('contact_reasons','motion_reasons','invalid_reasons'))
        and recovery_count==0 and c['phase']=='SEARCH' and c['search_count']==1
        and snapshot.state['phase']=='RUNNING' and snapshot.state['contact_count']>0
        and snapshot.residual_enabled is True and snapshot.time_s-c['phase_start']>=.020)

class RecoveryFixture:
    def __init__(self):self.events=[];self.resumed_pulse=False;self.transitions=[]

    def prepare(self,session,snapshot,refresh):
        if self.events or not eligible(snapshot,reason=session.reason,guard_latched=session.guard_latched,
            done=session.done,task_finished=session.task_finished,recovery_state=session.recovery_state,
            facts=session.env.guard_facts,recovery_count=session.env.recovery_count):return snapshot
        record=dict(cycle_id=snapshot.cycle_id,prepared=snapshot_dict(snapshot),
            sensor_before=deepcopy(session.env.observe()),reason_before=session.reason,
            guard_latched_before=session.guard_latched,done_before=session.done,task_finished_before=session.task_finished,
            recovery_state_before=session.recovery_state,recovery_count_before=session.env.recovery_count,
            guard_facts_before=deepcopy(session.env.guard_facts),live_before=live_state(session.env))
        # Consume before mutation, so a failed transition cannot be retried.
        self.events.append(record)
        session.controller._transition('WAIT_RECOVERY',session.policy_observation(record['sensor_before']),'SEARCH_EXHAUSTED')
        session.env.stop('B2_SEARCH_EXHAUSTED')
        session.recovery_state='WAIT_STOP';session.wait_start=snapshot.time_s
        refreshed=deepcopy(snapshot)
        refreshed.base_command=[0.]*6;refreshed.residual_enabled=False
        refreshed.state=deepcopy(session.env.observe());refreshed.controller_state=session.controller_state_snapshot()
        session._cache=refreshed;session._decorated_cache=None
        # refresh sees an already populated cache: no second controller command,
        # WAIT_STOP evaluation, or native step. Original decorator recaptures v4.
        answer=refresh()
        record['after']=snapshot_dict(answer)
        record['sensor_after']=deepcopy(session.env.observe())
        record['live_after']=live_state(session.env)
        return answer

    def track(self,session,snapshot):
        signature=(session.recovery_state,session.env.recovery_count,snapshot.controller_state['search_count'])
        if not self.transitions or tuple(self.transitions[-1]['signature'])!=signature:
            self.transitions.append(dict(signature=list(signature),cycle_id=snapshot.cycle_id,
                snapshot=snapshot_dict(snapshot),live=live_state(session.env),reason=session.reason))

    def action(self,snapshot,recovery_state):
        if not self.events:return [0.]*4
        if recovery_state in ('WAIT_STOP','RETRACT','WAIT_RESUME'):return [1.,-1.,1.,-1.]
        if (not self.resumed_pulse and snapshot.residual_enabled and snapshot.state['phase']=='RUNNING'
                and snapshot.controller_state['phase']=='SEARCH' and snapshot.controller_state['search_count']==2):
            self.resumed_pulse=True
            return [.1,-.1,.1,-.1]
        return [0.]*4

def session_type(base):
    """Local adapter; the production class is neither patched nor persisted."""
    class JointPreflightSession(base):
        fixture=None
        def _prepare_residual(self):
            snapshot=super()._prepare_residual()
            if self.fixture is None or not self._features_ready:return snapshot
            snapshot=self.fixture.prepare(self,snapshot,lambda:super(JointPreflightSession,self)._prepare_residual())
            self.fixture.track(self,snapshot)
            return snapshot
    return JointPreflightSession
