"""CPU SAC update primitive with v3 masks and rollback, not a training permit.

The caller must supply freshly audited replay through SACCollection. This class
also accepts synthetic tensors for numerical tests. Its in-memory transaction
does not provide process-crash recovery or a complete training checkpoint.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import math

import numpy as np
import torch
from gymnasium import spaces
from stable_baselines3.sac.policies import SACPolicy

from .admission import validate_config
from .audited_replay import ReplayBatch
from .learning_rates import optimizer_learning_rates, validate_optimizer_learning_rates
from .tensor_masks import canonical_actions, critic_target, actor_temperature_losses, masked_optimizer_step


def validate_batch(batch):
    if type(batch) is not ReplayBatch: raise ValueError('Audited ReplayBatch required')
    n = len(batch.observations)
    if not n: raise ValueError('Nonempty batch required')
    booleans = {'terminated', 'truncated', 'action_active', 'next_action_active'}
    for name in ReplayBatch.__dataclass_fields__:
        value = getattr(batch, name)
        width = 120 if name in ('observations', 'next_observations') else 4 if name == 'actions' else 1
        dtype = torch.bool if name in booleans else torch.float32
        if (not isinstance(value, torch.Tensor) or value.shape != (n, width) or
                value.dtype != dtype or value.device.type != 'cpu' or value.requires_grad or
                not torch.isfinite(value).all()):
            raise ValueError(f'Invalid batch tensor: {name}')
    if ((batch.observations.abs() > 10).any() or (batch.next_observations.abs() > 10).any() or
            (batch.actions.abs() > 1).any() or (batch.dt <= 0).any() or
            (batch.terminated & batch.truncated).any() or
            not torch.allclose(batch.discounts, torch.exp(-batch.dt / 10), rtol=0, atol=1e-7)):
        raise ValueError('Observation, action, boundary or physical-time discount invalid')


def tensor_digest(state):
    h = hashlib.sha256()
    for name, value in sorted(state.items()):
        h.update(name.encode()); h.update(str(tuple(value.shape)).encode())
        h.update(value.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()


class SACUpdater:
    config_validator = staticmethod(validate_config)

    def __init__(self, config):
        self.config_validator(config)
        self.config = deepcopy(config)
        settings = config['learning']
        rates = optimizer_learning_rates(settings)
        torch.set_num_threads(settings['torch_threads'])
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(settings['seed'])
            self.policy = SACPolicy(spaces.Box(-10., 10., shape=(120,), dtype=np.float32),
                spaces.Box(-1., 1., shape=(4,), dtype=np.float32),
                lambda _: settings['learning_rate'], net_arch=settings['network'], activation_fn=torch.nn.ReLU)
            self.rng_state = torch.get_rng_state().clone()
        for group in self.policy.actor.optimizer.param_groups:
            group['lr'] = rates['actor']
        self.log_alpha = torch.nn.Parameter(torch.tensor(math.log(settings['entropy_initial']), dtype=torch.float32))
        self.temperature_optimizer = torch.optim.Adam([self.log_alpha], lr=settings['learning_rate'])
        self.counts = dict(critic=0, actor=0, temperature=0, target=0)
        self.failed = False
        self.failure = None

    @contextmanager
    def _random(self):
        with torch.random.fork_rng(devices=[]):
            torch.set_rng_state(self.rng_state)
            try: yield
            finally: self.rng_state = torch.get_rng_state().clone()

    def predict(self, observation, deterministic=False):
        if self.failed: raise RuntimeError('Updater failed; prediction refused')
        with self._random():
            return self.policy.predict(observation, deterministic=deterministic)

    def fingerprints(self):
        return dict(actor=tensor_digest(self.policy.actor.state_dict()),
            critic=tensor_digest(self.policy.critic.state_dict()),
            target=tensor_digest(self.policy.critic_target.state_dict()),
            alpha=tensor_digest({'log_alpha': self.log_alpha}))

    def _snapshot(self):
        return deepcopy(dict(policy=self.policy.state_dict(), actor=self.policy.actor.optimizer.state_dict(),
            critic=self.policy.critic.optimizer.state_dict(), alpha=self.log_alpha.detach().clone(),
            temperature=self.temperature_optimizer.state_dict(), counts=self.counts, rng=self.rng_state))

    def _restore(self, saved):
        validate_optimizer_learning_rates(saved, self.config['learning'])
        self.policy.load_state_dict(saved['policy'])
        self.policy.actor.optimizer.load_state_dict(saved['actor'])
        self.policy.critic.optimizer.load_state_dict(saved['critic'])
        with torch.no_grad(): self.log_alpha.copy_(saved['alpha'])
        self.temperature_optimizer.load_state_dict(saved['temperature'])
        self.counts, self.rng_state = saved['counts'], saved['rng']
        for optimizer in self._optimizers(): optimizer.zero_grad(set_to_none=True)

    def _optimizers(self):
        return (self.policy.critic.optimizer, self.policy.actor.optimizer, self.temperature_optimizer)

    def _targets(self, batch, exact_targets=None):
        with torch.no_grad():
            action, logp = self.policy.actor.action_log_prob(batch.next_observations)
            action = canonical_actions(action, batch.next_action_active)
            q = torch.cat(self.policy.critic_target(batch.next_observations, action), 1).min(1, keepdim=True).values
            result = critic_target(reward=batch.rewards, discount=batch.discounts, terminated=batch.terminated,
                q_next=q, log_probability=logp.reshape(-1, 1), alpha=self.log_alpha.detach().exp(),
                next_active=batch.next_action_active)
            if exact_targets is not None:
                if not isinstance(exact_targets, tuple) or len(exact_targets) != 2:
                    raise ValueError('Exact labels and applicability mask required')
                values, mask = exact_targets
                for tensor, dtype in ((values, torch.float32), (mask, torch.bool)):
                    if (not isinstance(tensor, torch.Tensor) or tensor.shape != result.shape or
                            tensor.dtype != dtype or tensor.device.type != 'cpu' or tensor.requires_grad or
                            not torch.isfinite(tensor).all()):
                        raise ValueError('Invalid exact terminal-tail label')
                if (mask & (batch.next_action_active | batch.truncated)).any():
                    raise ValueError('Exact tail labels cannot replace future action or truncation bootstrap')
                result = torch.where(mask, values, result)
            return result

    def targets(self, batch, *, exact_targets=None):
        """Diagnostic target computation; preserves optimizer state."""
        if self.failed: raise RuntimeError('Updater failed')
        validate_batch(batch)
        with self._random():
            return self._targets(batch) if exact_targets is None else self._targets(batch, exact_targets)

    def _finite_state(self):
        values = list(self.policy.state_dict().values()) + [self.log_alpha, self.log_alpha.exp()]
        for optimizer in self._optimizers():
            values.extend(v for state in optimizer.state.values() for v in state.values() if isinstance(v, torch.Tensor))
        if any(not torch.isfinite(v).all() for v in values):
            raise ValueError('Nonfinite network, temperature or optimizer state')

    def update(self, batch, *, critic_batch=None, exact_targets=None):
        if self.failed: raise RuntimeError('Updater failed; restart from a qualified boundary')
        saved = self._snapshot()
        try:
            validate_batch(batch)
            critic_batch = batch if critic_batch is None else critic_batch
            validate_batch(critic_batch)
            if len(critic_batch.observations) != len(batch.observations):
                raise ValueError('Actor and critic batches must have the same row count')
            self._finite_state()
            with self._random():
                self.policy.set_training_mode(True)
                target = (self._targets(critic_batch) if exact_targets is None
                          else self._targets(critic_batch, exact_targets))
                current = self.policy.critic(critic_batch.observations,
                    canonical_actions(critic_batch.actions, critic_batch.action_active))
                critic_loss = .5 * sum(torch.nn.functional.mse_loss(q, target) for q in current)
                masked_optimizer_step(critic_loss, self.policy.critic.optimizer)
                self.counts['critic'] += 1
                active = batch.action_active[:, 0]
                alpha_before = self.log_alpha.detach().exp().item()
                actor_loss = temperature_loss = None
                entropy_abs_mean = 0.
                if active.any():
                    # Freeze Q parameters, not the action-to-Q graph.
                    params = list(self.policy.critic.parameters())
                    flags = [p.requires_grad for p in params]
                    try:
                        for p in params: p.requires_grad_(False)
                        actions, logp = self.policy.actor.action_log_prob(batch.observations[active])
                        q_pi = torch.cat(self.policy.critic(batch.observations[active], actions), 1).min(1, keepdim=True).values
                        actor_loss, temperature_loss = actor_temperature_losses(q=q_pi,
                            log_probability=logp.reshape(-1, 1), log_alpha=self.log_alpha,
                            target_entropy=self.config['learning']['target_entropy'],
                            active=torch.ones((len(actions), 1), dtype=torch.bool))
                        entropy_abs_mean = (alpha_before * logp.detach().abs()).mean().item()
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
                self.counts['target'] += 1
                self._finite_state()
                result = dict(critic_loss=float(critic_loss.detach()),
                    actor_loss=None if actor_loss is None else float(actor_loss.detach()),
                    temperature_loss=None if temperature_loss is None else float(temperature_loss.detach()),
                    active_rows=int(active.sum()), batch_rows=len(active),
                    alpha_before=alpha_before, alpha_after=self.log_alpha.detach().exp().item(),
                    entropy_abs_mean=entropy_abs_mean, reward_abs_mean=batch.rewards.abs().mean().item(),
                    target_abs_max=target.abs().max().item(), discount_mean=batch.discounts.mean().item(),
                    critic_batches=self.counts['critic'])
            return result
        except Exception as exc:
            self._restore(saved)
            self.failed, self.failure = True, repr(exc)
            raise
