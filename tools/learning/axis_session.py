"""Trace axis-separated search and the frozen net-depth progress baseline."""
from copy import deepcopy
from tools.learning.rebase_session import RebasedLoadReliefSession


class AxisSearchSession(RebasedLoadReliefSession):
    def controller_state_snapshot(self):
        state=super().controller_state_snapshot();c=self.controller
        state.update(episode_peak_z_m=c.episode_peak_z_m,
                     search_progress_origin_z_m=c.search_progress_origin_z_m,
                     search_composition=deepcopy(c.search_composition))
        return state

    def _trace_row(self,row):
        result=super()._trace_row(row);c=self.controller
        result.update(episode_peak_z_m=c.episode_peak_z_m,
                      search_progress_origin_z_m=c.search_progress_origin_z_m,
                      search_composition=deepcopy(c.search_composition) if row['phase']=='RUNNING' else None)
        return result
