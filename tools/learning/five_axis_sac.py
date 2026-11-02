"""Ordinary CPU SAC for the 140/5 interface, with inherited rollback utilities."""
from copy import deepcopy
import math
import numpy as np
import torch
from gymnasium import spaces
from stable_baselines3.sac.policies import SACPolicy
from .audited_replay import ReplayBatch
from .five_axis_contract import validate_config, permissions
from .learning_rates import optimizer_learning_rates
from .tensor_masks import critic_target, actor_temperature_losses, masked_optimizer_step
from .v4_sac import V4Updater


def canonical_actions(actions, active):
    if (not isinstance(actions, torch.Tensor) or actions.ndim != 2 or actions.shape[1] != 5
            or not len(actions) or not actions.is_floating_point() or not torch.isfinite(actions).all()
            or (abs(actions) > 1).any() or active.shape != (len(actions), 1)
            or active.dtype != torch.bool or active.device != actions.device):
        raise ValueError('Normalized five-axis actions and boolean permission column required')
    return torch.where(active, actions, torch.zeros_like(actions))


def validate_batch(batch):
    if type(batch) is not ReplayBatch:
        raise ValueError('Audited replay batch required')
    n = len(batch.observations)
    if not n:
        raise ValueError('Nonempty batch required')
    booleans = {'terminated', 'truncated', 'action_active', 'next_action_active'}
    for name in ReplayBatch.__dataclass_fields__:
        value = getattr(batch, name)
        width = 140 if name in ('observations', 'next_observations') else 5 if name == 'actions' else 1
        if (not isinstance(value, torch.Tensor) or value.shape != (n, width)
                or value.dtype != (torch.bool if name in booleans else torch.float32)
                or value.device.type != 'cpu' or value.requires_grad or not torch.isfinite(value).all()):
            raise ValueError('Invalid five-axis batch: ' + name)
    if ((batch.actions.abs() > 1).any() or (batch.dt <= 0).any()
            or (batch.terminated & batch.truncated).any()
            or (batch.terminated & batch.next_action_active).any()
            or not torch.allclose(batch.discounts, torch.exp(-batch.dt / 10), rtol=0, atol=1e-7)):
        raise ValueError('Invalid normalized action, boundary or physical-time discount')
    for observation, flag in ((batch.observations, batch.action_active),
                              (batch.next_observations, batch.next_action_active)):
        if np.any(permissions(observation.numpy()) != flag[:, 0].numpy()):
            raise ValueError('Permission differs from observation')
    if (batch.actions[~batch.action_active[:, 0]] != 0).any():
        raise ValueError('Inactive experience must be zero')


class FiveAxisUpdater(V4Updater):
    """Reuse transactions/RNG/finite checks, never legacy fixed-dimension updates."""
    config_validator = staticmethod(validate_config)

    def __init__(self, config):
        self.config = validate_config(config)
        settings = self.config['learning']; rates = optimizer_learning_rates(settings)
        torch.set_num_threads(settings['torch_threads'])
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(settings['seed'])
            self.policy = SACPolicy(spaces.Box(-10., 10., shape=(140,), dtype=np.float32),
                spaces.Box(-1., 1., shape=(5,), dtype=np.float32), lambda _: settings['learning_rate'],
                net_arch=settings['network'], activation_fn=torch.nn.ReLU)
            self.rng_state = torch.get_rng_state().clone()
        for group in self.policy.actor.optimizer.param_groups:
            group['lr'] = rates['actor']
        self.log_alpha = torch.nn.Parameter(torch.tensor(math.log(settings['entropy_initial']), dtype=torch.float32))
        self.temperature_optimizer = torch.optim.Adam([self.log_alpha], lr=settings['learning_rate'])
        self.counts = dict(critic=0, actor=0, temperature=0, target=0)
        self.failed = False; self.failure = None

    def predict(self, observation, deterministic=False):
        values = np.asarray(observation)
        permissions(values[None] if values.ndim == 1 else values)
        return super().predict(observation, deterministic=deterministic)

    def _targets(self, batch):
        with torch.no_grad():
            actions, logp = self.policy.actor.action_log_prob(batch.next_observations)
            actions = canonical_actions(actions, batch.next_action_active)
            q = torch.cat(self.policy.critic_target(batch.next_observations, actions), 1).min(1, keepdim=True).values
            return critic_target(reward=batch.rewards, discount=batch.discounts, terminated=batch.terminated,
                q_next=q, log_probability=logp.reshape(-1, 1), alpha=self.log_alpha.detach().exp(),
                next_active=batch.next_action_active)

    def targets(self, batch):
        if self.failed:
            raise RuntimeError('Updater failed')
        validate_batch(batch)
        with self._random():
            return self._targets(batch)

    def update(self, batch):
        if self.failed:
            raise RuntimeError('Updater failed; restart from a healthy saved boundary')
        saved = self._snapshot()
        try:
            validate_batch(batch); self._finite_state()
            with self._random():
                self.policy.set_training_mode(True)
                target = self._targets(batch)
                current = self.policy.critic(batch.observations, canonical_actions(batch.actions, batch.action_active))
                critic_loss = .5 * sum(torch.nn.functional.mse_loss(q, target) for q in current)
                masked_optimizer_step(critic_loss, self.policy.critic.optimizer)
                self.counts['critic'] += 1
                active = batch.action_active[:, 0]
                actor_loss = temperature_loss = None
                if active.any():
                    params = list(self.policy.critic.parameters()); flags = [p.requires_grad for p in params]
                    try:
                        for p in params: p.requires_grad_(False)
                        actions, logp = self.policy.actor.action_log_prob(batch.observations[active])
                        q = torch.cat(self.policy.critic(batch.observations[active], actions), 1).min(1, keepdim=True).values
                        actor_loss, temperature_loss = actor_temperature_losses(q=q,
                            log_probability=logp.reshape(-1, 1), log_alpha=self.log_alpha,
                            target_entropy=self.config['learning']['target_entropy'],
                            active=torch.ones((len(actions), 1), dtype=torch.bool))
                        masked_optimizer_step(actor_loss, self.policy.actor.optimizer)
                        self.counts['actor'] += 1
                    finally:
                        for p, flag in zip(params, flags): p.requires_grad_(flag)
                    masked_optimizer_step(temperature_loss, self.temperature_optimizer)
                    self.counts['temperature'] += 1
                else:
                    masked_optimizer_step(None, self.policy.actor.optimizer)
                    masked_optimizer_step(None, self.temperature_optimizer)
                with torch.no_grad():
                    tau = self.config['learning']['tau']
                    for source, dest in zip(self.policy.critic.parameters(), self.policy.critic_target.parameters()):
                        dest.mul_(1 - tau).add_(source, alpha=tau)
                self.counts['target'] += 1; self._finite_state()
                return dict(critic_loss=float(critic_loss.detach()),
                    actor_loss=None if actor_loss is None else float(actor_loss.detach()),
                    temperature_loss=None if temperature_loss is None else float(temperature_loss.detach()),
                    active_rows=int(active.sum()), batch_rows=len(active),
                    alpha_after=float(self.log_alpha.detach().exp()), critic_batches=self.counts['critic'])
        except Exception as exc:
            self._restore(saved); self.failed = True; self.failure = repr(exc)
            raise
