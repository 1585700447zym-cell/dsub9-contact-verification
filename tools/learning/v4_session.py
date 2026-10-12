"""v4 residual adapter retaining layered/reference/rebase lifecycle. No admission."""
from copy import deepcopy
import numpy as np
from .residual_session import ResidualSession
from .layered_session import LayeredReferenceSession
from .v4_action import SCALE,compose_reference_command,ReferenceEnvelopeInfeasible
from .v4_observation import V4ObservationBuilder
from .reward import EpisodeReward

class V4ResidualSession(ResidualSession,LayeredReferenceSession):
    def __init__(self,*,environment,mode,controller_factory,finish_criteria=None,geometry_checker=None):
        if mode not in ('F50','S50'):raise ValueError('Explicit F50 or S50 mode required')
        expected=dict(control_period=.002,linear_speed=.001,linear_acceleration=.005,angular_speed=.03,angular_acceleration=.3)
        if any(getattr(environment.config,k)!=v for k,v in expected.items()):raise ValueError('v4 qualified drive constants required')
        self.mode=mode
        super().__init__(environment=environment,controller_factory=controller_factory,action_scale=SCALE,
                         finish_criteria=finish_criteria,geometry_checker=geometry_checker)

    def stage_permission(self,phase,base_enabled):
        return bool(base_enabled and phase in (('INSERT','SEARCH') if self.mode=='F50' else ('SEARCH',)))

    def _reset_residual(self,case,seed):
        self._ready=self._features_ready=False;self._cache=self._decorated_cache=None
        self.done=self.task_finished=True;self.previous_residual=[0.]*4;self.last_action_log={};self.policy_raw={}
        self.clipped_duration_s=0.;self.external_cut=False;self.reward=EpisodeReward(case.target_depth_m)
        initial=LayeredReferenceSession.reset(self,case,seed)
        self.observations=V4ObservationBuilder(initial.state,self.controller.config)
        self._features_ready=True
        return self.prepare_cycle()

    def _prepare_residual(self):
        snapshot=LayeredReferenceSession.prepare_cycle(self)
        self._cache.residual_enabled=self.stage_permission(self._cache.controller_state['phase'],self._cache.residual_enabled)
        if not self._features_ready:return deepcopy(self._cache)
        if self._decorated_cache is not self._cache:
            from tools.validation.native313_matrix_audit import actual_stop_start
            context=dict(reason=self.reason,recovery_state=self.recovery_state,recovery_count=self.env.recovery_count,
                hold_start=self.hold_start,wait_start=self.wait_start,actual_stop_start=actual_stop_start(self.env.events,self.stop_time),
                previous_residual=self.previous_residual,guard_facts=self.env.guard_facts,
                previous_filter_fraction=self.last_action_log.get('reference_filter_fraction',1.))
            policy_snapshot=deepcopy(self._cache)
            policy_snapshot.state['reference_qpos']=self.env.reference.tolist()
            policy_snapshot.state['limited_command_world']=self.env.command.tolist()
            vector,raw=self.observations.capture(policy_snapshot,context,refresh=True)
            self.policy_raw=raw;self._cache.policy_observation=vector.tolist();self._cache.policy_raw=deepcopy(raw)
            self._cache.privileged_evaluation=dict(case_name=self.case.name,position_m=list(snapshot.state['position_m']),
                quaternion_wxyz=list(snapshot.state['quaternion_wxyz']),penetration_m=snapshot.state['penetration_m'],contact_count=snapshot.state['contact_count'])
            self._decorated_cache=self._cache
        return deepcopy(self._cache)

    def _command_for_action(self,snapshot,action):
        # ResidualSession's override does not delegate: explicitly preserve the
        # inherited one-shot reference release and XY admittance restart first.
        base=LayeredReferenceSession._command_for_action(self,snapshot,action)
        phase=snapshot.controller_state['phase'];ref=None
        if phase=='SEARCH' and snapshot.residual_enabled:
            ref=(self.env.reference[:3]-self.initial-self.controller.search_origin)[:2]
        try:
            command,log=compose_reference_command(base,action,phase=phase,enabled=snapshot.residual_enabled,
                previous_limited=self.env.command.copy(),dt=self.env.config.control_period,reference_xy=ref,
                radius=self.controller.config.spiral_radius_m)
        except ReferenceEnvelopeInfeasible:
            reason='RESIDUAL_REFERENCE_INFEASIBLE'
            self.controller._fail(self.policy_observation(self.env.observe()),reason)
            self._finish(reason)
            command,log=compose_reference_command([0.]*6,action,phase='FAILED',enabled=False,
                previous_limited=self.env.command.copy(),dt=self.env.config.control_period)
            log['reference_failure']=reason
        self.last_action_log=log
        self.previous_residual=np.asarray(log['applied_residual'])[[0,1,3,4]].tolist()
        return command
