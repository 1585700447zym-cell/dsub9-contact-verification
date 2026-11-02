"""B1 fixed admittance in the common episode protocol; no search or recovery."""
import numpy as np
from .search_recovery import SearchRecovery,SearchConfig

class V4FixedAdmittance(SearchRecovery):
    def __init__(self):super().__init__(SearchConfig(total_action_time_s=25.))
    def command(self,obs,dt):
        p=np.asarray(obs.displacement_m);w=np.asarray(obs.wrench_M)
        if p.shape!=(3,) or w.shape!=(6,) or not np.isfinite(np.r_[p,w,obs.time_s,dt]).all() or dt<=0:
            raise ValueError('Invalid B1 observation or period')
        return self.admittance.command(w,dt)
    def start_recovered_search(self,obs):raise RuntimeError('B1 has no recovery')
    def metadata(self):return {**self.admittance.metadata(),'task_adapter':'v4_common_episode','total_action_time_s':25.}
