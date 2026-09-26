"""Engineered branch coverage, not a natural recovery success-rate claim."""
import math
import numpy as np


def test_nonzero_requests_stay_masked_through_actual_retraction(runtime):
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.learning.residual_session import ResidualSession
    from tools.control.search_recovery import SearchConfig, SearchRecovery
    from tools.validation.run_b1_baseline import cases
    def ready():
        c = SearchRecovery(SearchConfig(search_time_s=.002))
        c.phase = 'SEARCH'
        c.search_count = 1
        c.search_origin = np.zeros(3)
        c.phase_start = -.01
        return c
    s = ResidualSession(environment=LearningEnvironment(guard_config=GuardCandidateConfig(
        max_rotation_from_start_rad=math.radians(2.5), initial_roll_pitch_limit_rad=math.radians(1.5))),
        controller_factory=ready)
    s.reset(cases()[0])
    saw_retract = False
    for _ in range(1000):
        before = s.prepare_cycle()
        if before.state['phase'] == 'RETRACT':
            saw_retract = True
        result = s.advance_cycle([1, -1, 1, -1])
        assert result.action_log['applied_residual'] == [0.]*6
        assert result.action_log['experience_action'] == [0.]*4
        if result.next_snapshot.residual_enabled:
            break
    assert saw_retract and s.controller.search_count == 2
    assert s.env.recovery_start[2]-s.env.data.qpos[2] >= .0002
    # Permissions come from the updated state: the first resumed SEARCH accepts it.
    result = s.advance_cycle([1, -1, 1, -1])
    assert result.action_log['applied_residual'] == [.00015, -.00015, 0., .005, -.005, 0.]
