"""Explicit common task adapter, retaining all guarded session stop semantics."""
from tools.learning.guarded_session import CandidateEpisodeSession
from tools.learning.guarded_environment import relative_rotation_rad
from tools.control.risk_search import PoseObservation
from tools.model.functional_task import functional_finish


class FunctionalCandidateSession(CandidateEpisodeSession):
    def policy_observation(self, row):
        base=super().policy_observation(row)
        return PoseObservation(base.time_s,base.displacement_m,base.wrench_M,
            relative_rotation_rad(self.env.initial[3:],row['quaternion_wxyz']))

    def completion_ready(self, row):
        return functional_finish(row,self.finish_criteria)

    def controller_state_snapshot(self):
        state=super().controller_state_snapshot()
        state['rotation_risk_since_s']=getattr(self.controller,'risk_since',None)
        return state
