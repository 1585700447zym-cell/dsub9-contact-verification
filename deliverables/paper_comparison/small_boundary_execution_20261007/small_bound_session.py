"""Thin physical session. Construction/rollout requires separate admission."""
from dataclasses import asdict
from copy import deepcopy
import numpy as np
from small_bound_profile import validate_outer_contract, decorate_action_log
from tools.learning.action import normalized_action
from tools.learning.v4_continuation import ContinuationResidualSession


class SmallBoundSession(ContinuationResidualSession):
    def __init__(self,*,contract,admission,**kwargs):
        self.outer_contract=deepcopy(contract)
        self.profile_sha256=validate_outer_contract(contract)
        self.outer_admission=admission
        admission.verify('physical',self.profile_sha256)
        if kwargs.get('mode','F50')!='F50':raise ValueError('Internal F50 permission required')
        kwargs['mode']='F50'
        super().__init__(**kwargs)

    def reset(self,case,seed=None):
        self.outer_admission.verify('physical',validate_outer_contract(self.outer_contract))
        return super().reset(case,seed)

    def _command_for_action(self,snapshot,action):
        self.outer_admission.verify('physical',validate_outer_contract(self.outer_contract))
        a=normalized_action(action);phase=snapshot.controller_state['phase']
        reference=None
        if phase=='SEARCH' and snapshot.residual_enabled:
            reference=(self.env.reference[:3]-self.initial-self.controller.search_origin)[:2].tolist()
        context=dict(base=list(snapshot.base_command),phase=phase,enabled=bool(snapshot.residual_enabled),
            previous_limited=self.env.command.copy().tolist(),dt=self.env.config.control_period,
            reference_xy=reference,radius=self.controller.config.spiral_radius_m,
            next_theta=self.controller.theta,search_config=asdict(self.controller.config))
        # Parent owns reference release, rebase and failure handling, exactly once.
        command=super()._command_for_action(snapshot,(a*.25).tolist())
        self.last_action_log=decorate_action_log(self.last_action_log,a,context,self.outer_contract)
        # The parent already recorded the physical previous_residual; never rescale it.
        return command
