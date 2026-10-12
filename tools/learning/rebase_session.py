"""Opt-in, bounded XY admittance restart at a load-relief reference release."""
import numpy as np
from tools.learning.load_session import LoadReliefSession


class RebasedLoadReliefSession(LoadReliefSession):
    def _command_for_action(self,snapshot,action):
        c=self.controller
        if not c.reference_release_requested:
            return super()._command_for_action(snapshot,action)
        # Validate before the parent changes the drive reference. A reset is
        # permitted only with the original remaining-search entitlement.
        count=sum(e['reason']=='XY_ADMITTANCE_REBASED' for e in c.events)
        if not 0<c.search_count<c.config.max_searches or count>=c.config.max_searches-1:
            raise RuntimeError('No bounded admittance rebase entitlement')
        a=c.admittance
        offset=np.asarray(a.offset,dtype=float);velocity=np.asarray(a.velocity,dtype=float)
        if offset.shape!=(4,) or velocity.shape!=(4,) or not np.isfinite(np.r_[offset,velocity]).all():
            raise ValueError('Finite four-channel admittance state required')
        before_offset=offset[:2].copy();before_velocity=velocity[:2].copy()
        # Parent owns the original phase/validity/guard gates and XY reference
        # release. The advance_cycle lifecycle validates the action first.
        command=super()._command_for_action(snapshot,action)
        a.offset=offset.copy();a.velocity=velocity.copy()
        a.offset[:2]=0.;a.velocity[:2]=0.
        c.events.append(dict(time_s=snapshot.time_s,phase=c.phase,reason='XY_ADMITTANCE_REBASED',
            search_count=c.search_count,rebase_number=count+1,
            offset_before_m=before_offset.tolist(),offset_after_m=a.offset[:2].tolist(),
            velocity_before_m_s=before_velocity.tolist(),velocity_after_m_s=a.velocity[:2].tolist(),
            per_segment_budget_m=list(a.config.correction_budget[:2]),
            scope='XY reference release starts a fresh bounded correction segment'))
        return command

    def controller_state_snapshot(self):
        state=super().controller_state_snapshot()
        state['admittance_xy_rebase_count']=sum(e['reason']=='XY_ADMITTANCE_REBASED' for e in self.controller.events)
        return state
