import pytest
import numpy as np


def test_deterministic_critic_uses_zero_inactive_action_and_no_entropy():
    from tools.learning.learning_masks import canonical_actions, critic_target
    actions = np.ones((2, 4))
    active = np.array([[False], [True]])
    canonical = canonical_actions(actions, active)
    # Fixed analytic critic: Q=2+sum(a). Inactive Q must be evaluated at a=0.
    q = 2 + canonical.sum(axis=1, keepdims=True)
    target = critic_target(reward=np.zeros((2, 1)), discount=np.full((2, 1), .5),
        terminated=np.zeros((2, 1), dtype=bool), q_next=q,
        log_probability=np.full((2, 1), -10.), alpha=.2, next_active=active)
    np.testing.assert_array_equal(target, [[1.], [4.]])


def test_inactive_actor_and_temperature_samples_do_not_affect_or_dilute_losses():
    from tools.learning.learning_masks import actor_temperature_losses
    logp = np.array([[-2.], [-100.]])
    q = np.array([[3.], [999.]])
    logalpha = 1.
    actor, temperature = actor_temperature_losses(q=q, log_probability=logp,
        log_alpha=logalpha, target_entropy=-4., active=np.array([[True], [False]]))
    assert actor == pytest.approx(-2*np.e-3) and temperature == pytest.approx(6.)
    logp[1] = -1000.
    q[1] = -999.
    again = actor_temperature_losses(q=q, log_probability=logp,
        log_alpha=logalpha, target_entropy=-4., active=np.array([[True], [False]]))
    assert again == (actor, temperature)
    actor, temperature = actor_temperature_losses(q=q, log_probability=logp,
        log_alpha=logalpha, target_entropy=-4., active=np.zeros((2, 1), dtype=bool))
    assert actor is None and temperature is None  # Caller must skip optimizer.step.


def test_terminal_target_does_not_bootstrap_but_true_cut_does():
    from tools.learning.learning_masks import critic_target
    result = critic_target(reward=np.array([[-2.], [-.1]]), discount=np.full((2, 1), .5),
        terminated=np.array([[True], [False]]), q_next=np.full((2, 1), 4.),
        log_probability=np.zeros((2, 1)), alpha=.2, next_active=np.ones((2, 1), dtype=bool))
    np.testing.assert_allclose(result, [[-2.], [1.9]])


def test_mask_shape_cannot_silently_broadcast_across_batch():
    from tools.learning.learning_masks import canonical_actions
    with pytest.raises(ValueError):
        canonical_actions(np.ones((2, 4)), np.array([True, False]))
