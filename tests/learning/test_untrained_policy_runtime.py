"""Runtime qualification at the project's policy/environment boundary.

These characterize the newly isolated dependencies, not an implemented trainer.
No SAC.learn, replay insertion, actor/critic optimizer step or independent test
case is used. The tiny network and seed are diagnostic, NOT training settings.
"""
import json
import math

import numpy as np
import torch


def test_untrained_policy_reload_reproduces_short_native_trace(runtime, tmp_path, record_property):
    from stable_baselines3.sac.policies import SACPolicy
    from tools.learning.env import ResidualEnv
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.learning.residual_session import ResidualSession
    from tools.validation.run_b1_baseline import cases

    def make_env():
        return ResidualEnv(session=ResidualSession(environment=LearningEnvironment(
            guard_config=GuardCandidateConfig(max_rotation_from_start_rad=math.radians(2.5),
                initial_roll_pitch_limit_rad=math.radians(1.5)))), case=cases()[0])

    env = make_env()
    torch.manual_seed(20260924)
    policy = SACPolicy(env.observation_space, env.action_space, lambda _: .001,
        net_arch=[32, 32], share_features_extractor=False).to('cpu')
    policy.set_training_mode(False)
    checkpoint = tmp_path / 'UNTRAINED_DIAGNOSTIC_POLICY.pt'
    policy.save(checkpoint)
    restored = SACPolicy.load(checkpoint, device='cpu')
    for key, original in policy.state_dict().items():
        torch.testing.assert_close(restored.state_dict()[key], original, rtol=0, atol=0)

    def trace(environment, network):
        obs, info = environment.reset(seed=20260924)
        assert not info['training_admitted']
        rows = []
        for step in range(8):
            action, _ = network.predict(obs, deterministic=True)
            assert action.shape == (4,) and environment.action_space.contains(action)
            before = obs.copy()
            call = environment.truncate_after_step if step == 7 else environment.step
            obs, reward, terminated, truncated, info = call(action)
            rows.append(dict(observation=before.tolist(), action=action.tolist(),
                next_observation=obs.tolist(), reward=reward, terminated=terminated,
                truncated=truncated, action_log=info['action_log']))
        assert not terminated and truncated
        assert info['outcome']['simulation_valid'] and info['outcome']['physical_stopped']
        assert info['outcome']['valid_for_learning'] is False
        assert environment.sink == []
        assert len(environment.attempts) == 1
        assert environment.attempts[0]['publication'] == {'committed': 0, 'discarded': 8}
        environment.close()
        return rows

    first, second = trace(env, policy), trace(make_env(), restored)
    assert first == second  # includes actual limited command and physical velocity logs
    assert not policy.actor.optimizer.state and not policy.critic.optimizer.state
    assert not restored.actor.optimizer.state and not restored.critic.optimizer.state
    record_property('qualification', json.dumps(dict(training_admitted=False,
        sac_updates=0, replay_committed=0, diagnostic_steps_per_trace=8,
        traces=2, exact=True, source_case='aligned development',
        native_runtime=runtime, policy_architecture=[32, 32]), ensure_ascii=False))


def test_sb3_actor_critic_outputs_use_tensor_permission_contract():
    from gymnasium import spaces
    from stable_baselines3.sac.policies import SACPolicy
    from tools.learning.tensor_masks import canonical_actions, critic_target, actor_temperature_losses
    torch.manual_seed(20260924)
    p = SACPolicy(spaces.Box(-10., 10., shape=(120,), dtype=np.float32),
        spaces.Box(-1., 1., shape=(4,), dtype=np.float32), lambda _: .001, net_arch=[32, 32])
    obs = torch.zeros((2, 120))  # synthetic probe; not a simulation replay sample
    actions, raw_logp = p.actor.action_log_prob(obs)
    active = torch.tensor([[True], [False]])
    effective = canonical_actions(actions, active)
    assert torch.equal(effective[1], torch.zeros(4))
    q = torch.cat(p.critic(obs, effective), dim=1).min(dim=1, keepdim=True).values
    log_alpha = torch.tensor(0., requires_grad=True)
    actor, temperature = actor_temperature_losses(q=q, log_probability=raw_logp.reshape(-1, 1),
        log_alpha=log_alpha, target_entropy=-4., active=active)
    actor.backward()
    assert any(v.grad is not None and torch.isfinite(v.grad).all() for v in p.actor.parameters())
    assert log_alpha.grad is None
    p.actor.zero_grad(set_to_none=True)
    temperature.backward()
    assert log_alpha.grad is not None and torch.isfinite(log_alpha.grad)
    assert all(v.grad is None for v in p.actor.parameters())
    with torch.no_grad():
        q_next = torch.cat(p.critic_target(obs, effective), dim=1).min(dim=1, keepdim=True).values
    target = critic_target(reward=torch.zeros((2, 1)), discount=torch.full((2, 1), .5),
        terminated=torch.zeros((2, 1), dtype=torch.bool), q_next=q_next,
        log_probability=raw_logp.reshape(-1, 1), alpha=log_alpha.exp(), next_active=active)
    torch.testing.assert_close(target[1], .5*q_next[1])
    assert not target.requires_grad
    assert not p.actor.optimizer.state and not p.critic.optimizer.state


def test_sb3_q_only_gradient_reaches_actor_without_entropy_shortcut():
    from gymnasium import spaces
    from stable_baselines3.sac.policies import SACPolicy
    from tools.learning.tensor_masks import canonical_actions
    torch.manual_seed(20260924)
    p = SACPolicy(spaces.Box(-10., 10., shape=(120,), dtype=np.float32),
        spaces.Box(-1., 1., shape=(4,), dtype=np.float32), lambda _: .001, net_arch=[32, 32])
    obs = torch.zeros((2, 120))
    actions = p.actor(obs, deterministic=True)
    effective = canonical_actions(actions, torch.tensor([[True], [False]]))
    q = p.critic(obs, effective)[0]
    gradients = torch.autograd.grad(-q[0].mean(), tuple(p.actor.parameters()), allow_unused=True)
    assert any(g is not None and torch.isfinite(g).all() and torch.count_nonzero(g) > 0 for g in gradients)
    assert not p.actor.optimizer.state and not p.critic.optimizer.state
