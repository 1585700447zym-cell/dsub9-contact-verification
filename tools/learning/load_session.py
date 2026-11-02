"""Functional B2 with explicit one-shot release of stored lateral reference error."""
import numpy as np
from tools.learning.functional_session import FunctionalCandidateSession


class LoadReliefSession(FunctionalCandidateSession):
    def _command_for_action(self,snapshot,action):
        command=super()._command_for_action(snapshot,action)
        c=self.controller
        if c.reference_release_requested:
            e=self.env;facts=e.guard_facts
            if (e.phase!='RUNNING' or not facts['simulation_valid'] or
                    facts['contact_reasons'] or facts['motion_reasons'] or c.phase!='UNLOAD'):
                raise RuntimeError('Reference release requires active unguarded load relief')
            before=e.reference[:2].copy();actual=e.data.qpos[:2].copy()
            if not np.isfinite(np.r_[before,actual]).all():
                raise ValueError('Finite measured/reference XY required')
            # Setpoint management only: no qpos/qvel/time/guard mutation.
            # Preserve command slew limiting in the original environment.step.
            e.reference[:2]=actual
            c.events.append(dict(time_s=snapshot.time_s,phase=c.phase,reason='XY_REFERENCE_RELEASED',
                                 reference_before_m=before.tolist(),reference_after_m=actual.tolist(),
                                 released_error_m=(before-actual).tolist()))
            c.reference_release_requested=False
        return command

    def controller_state_snapshot(self):
        state=super().controller_state_snapshot()
        state.update(search_load_since_s=getattr(self.controller,'load_since',None),
                     reference_release_requested=getattr(self.controller,'reference_release_requested',False))
        return state
