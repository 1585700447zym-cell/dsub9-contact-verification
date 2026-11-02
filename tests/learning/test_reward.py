import pytest


def test_maximum_progress_does_not_pay_twice_for_backtracking():
    from tools.learning.reward import EpisodeReward
    reward = EpisodeReward(target_travel_m=.004)
    first = reward.advance(advance_m=.002, dt=.002, force_N=0, torque_G_Nm=0)
    back = reward.advance(advance_m=.001, dt=.002, force_N=0, torque_G_Nm=0)
    again = reward.advance(advance_m=.002, dt=.002, force_N=0, torque_G_Nm=0)
    assert first['progress'] == 2.5
    assert back['progress'] == again['progress'] == 0
    assert back['total'] == -.0002
    assert reward.advance(advance_m=1, dt=.002, force_N=0, torque_G_Nm=0)['progress'] == 2.5


def test_duration_and_cycle_load_costs_are_not_cumulative_peaks():
    from tools.learning.reward import EpisodeReward
    reward = EpisodeReward(.004)
    first = reward.advance(advance_m=0, dt=.1, force_N=.020, torque_G_Nm=0)
    second = reward.advance(advance_m=0, dt=.1, force_N=.005, torque_G_Nm=0)
    assert first['force'] == pytest.approx(-.0128)
    assert second['force'] == pytest.approx(-.0008)
    assert first['total'] + second['total'] == pytest.approx(-.0336)


@pytest.mark.parametrize('outcome,terminal', [('FULL_SUCCESS', 10), ('CONTACT_GUARD', -10),
                                             ('MOTION_VIOLATION', -10), ('TASK_FAILURE', -2),
                                             ('INVALID_SIMULATION', 0), ('STOP_NOT_QUALIFIED', 0)])
def test_terminal_reward_is_awarded_only_once(outcome, terminal):
    from tools.learning.reward import EpisodeReward
    reward = EpisodeReward(.004)
    assert reward.finalize(outcome) == terminal
    with pytest.raises(RuntimeError):
        reward.finalize(outcome)


def test_time_scaling_and_no_external_truncation_terminal_bonus():
    from tools.learning.reward import EpisodeReward
    a, b = EpisodeReward(.004), EpisodeReward(.004)
    full = a.advance(advance_m=0, dt=.2, force_N=.01, torque_G_Nm=.0001)['total']
    half = sum(b.advance(advance_m=0, dt=.1, force_N=.01, torque_G_Nm=.0001)['total'] for _ in range(2))
    assert full == pytest.approx(half)
    assert a.finalize('EXTERNAL_TRUNCATION') == 0
