"""Stage-local residual permissions; the shared B2 lifecycle stays unchanged."""
from tools.learning.action import validated_action_scale
from tools.learning.guarded_session import CandidateEpisodeSession
from tools.learning.residual_session import ResidualSession

ACTION_SCALE = (.00005, .00005, .0005, .0005)


class StageSession(ResidualSession):
    def __init__(self, *, environment, mode, action_scale=ACTION_SCALE, controller_factory=None):
        if type(mode) is not str or mode not in ('F', 'S'):
            raise ValueError('Registered stage mode F or S required')
        scale = validated_action_scale(action_scale)
        if scale != ACTION_SCALE:
            raise ValueError('Registered common XY50/rotation0.0005 mapping required')
        self._stage_mode = mode
        self._allowed_phases = ('INSERT', 'SEARCH') if mode == 'F' else ('SEARCH',)
        super().__init__(environment=environment, controller_factory=controller_factory, action_scale=scale)

    @property
    def mode(self):
        return self._stage_mode

    def _prepare_residual(self):
        # Populate the real shared cache before ResidualSession constructs policy
        # input. Its second prepare call is cached, so B2 still runs exactly once.
        CandidateEpisodeSession.prepare_cycle(self)
        self._cache.residual_enabled = bool(self._cache.residual_enabled and
            self._cache.controller_state['phase'] in self._allowed_phases)
        return super()._prepare_residual()
