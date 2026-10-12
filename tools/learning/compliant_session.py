"""Functional, guarded search with complete compliant-reference trace evidence."""
from copy import deepcopy
from tools.learning.rebase_session import RebasedLoadReliefSession


class CompliantSearchSession(RebasedLoadReliefSession):
    def controller_state_snapshot(self):
        state=super().controller_state_snapshot();c=self.controller
        state.update(search_admittance_origin_xy_m=None if c.search_admittance_origin is None else c.search_admittance_origin.tolist(),
                     search_composition=deepcopy(c.search_composition))
        return state

    def _trace_row(self,row):
        result=super()._trace_row(row)
        result['search_composition']=deepcopy(self.controller.search_composition) if row['phase']=='RUNNING' else None
        return result
