"""Isolated contact candidate. Historical CartesianEnvironment defaults stay frozen."""
from tools.dynamics.cartesian import CartesianEnvironment, DynamicConfig


class NativeTightCandidate(CartesianEnvironment):
    def __init__(self, *, segments=256, timestep=.0002):
        super().__init__(DynamicConfig(collision_backend='native', timestep=timestep), segments=segments)
        self.model.opt.ccd_tolerance=1e-12

    def metadata(self):
        return {**super().metadata(), 'contact_candidate':'native_tight_v1', 'candidate_only':True}


def candidate_environment(*, segments=256, timestep=.0002):
    return NativeTightCandidate(segments=segments,timestep=timestep)
