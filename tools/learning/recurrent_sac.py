"""Five-axis recurrent SAC components, with history encoded from observed behavior."""
from contextlib import contextmanager
from copy import deepcopy
import math

import torch
from torch import nn
from torch.nn import functional as F

from .five_axis_contract import ACTION_DIM, WIDTH
from .learning_rates import optimizer_learning_rates
from .tensor_masks import actor_temperature_losses, critic_target


HIDDEN = 64
VERSION = 'five_axis_independent_gru64_sac_v1'


class RecurrentEncoder(nn.Module):
    def __init__(self):
        super().__init__()
        self.projection = nn.Sequential(nn.Linear(WIDTH, HIDDEN), nn.ReLU())
        self.gru = nn.GRU(HIDDEN, HIDDEN, batch_first=True)

    def encode_step(self, observation, hidden=None):
        output, hidden = self.gru(self.projection(observation).unsqueeze(1), hidden)
        return output[:, 0], hidden

    def encode_sequence(self, observations, hidden=None, valid_mask=None):
        """Return h_t aligned to each observation; padding holds the preceding h."""
        batch, length, _ = observations.shape
        if hidden is None:
            hidden = observations.new_zeros(1, batch, HIDDEN)
        if length == 0:
            return observations.new_empty(batch, 0, HIDDEN), hidden
        if valid_mask is None or valid_mask.all():
            return self.gru(self.projection(observations), hidden)
        # Compress each short sequence to its true observations before the GRU.
        # cumsum maps its states back to the common left/right padded time axis.
        outputs = []
        for row in range(batch):
            valid = valid_mask[row, :, 0]
            initial = hidden[:, row:row+1]
            states = initial.transpose(0, 1)
            if valid.any():
                real = self.projection(observations[row, valid]).unsqueeze(0)
                encoded, _ = self.gru(real, initial.contiguous())
                states = torch.cat((states, encoded), dim=1)
            outputs.append(states[0, valid.long().cumsum(dim=0)])
        outputs = torch.stack(outputs)
        return outputs, outputs[:, -1].unsqueeze(0).contiguous()

    def encode_suffix(self, observations, observation_valid_mask, burn_in):
        with torch.no_grad():
            _, hidden = self.encode_sequence(observations[:, :burn_in], None,
                                             observation_valid_mask[:, :burn_in])
        return self.encode_sequence(observations[:, burn_in:], hidden.detach(),
                                    observation_valid_mask[:, burn_in:])[0]


class RecurrentActor(RecurrentEncoder):
    def __init__(self):
        super().__init__()
        self.head = nn.Sequential(nn.Linear(HIDDEN, 256), nn.ReLU())
        self.mu = nn.Linear(256, ACTION_DIM)
        self.log_std = nn.Linear(256, ACTION_DIM)

    def distribution(self, encoded):
        features = self.head(encoded)
        return self.mu(features), self.log_std(features).clamp(-20., 2.)

    def step(self, observation, hidden=None):
        encoded, hidden = self.encode_step(observation, hidden)
        mu, log_std = self.distribution(encoded)
        return mu, log_std, hidden

    def forward_sequence(self, observations, hidden=None, valid_mask=None):
        encoded, hidden = self.encode_sequence(observations, hidden, valid_mask)
        mu, log_std = self.distribution(encoded)
        return mu, log_std, hidden

    def sample(self, encoded, generator):
        mu, log_std = self.distribution(encoded)
        noise = torch.randn(mu.shape, dtype=mu.dtype, device=mu.device, generator=generator)
        raw = mu + log_std.exp() * noise
        log_normal = -.5 * (noise.square() + math.log(2 * math.pi)) - log_std
        # Stable log(1 - tanh(raw)^2), including saturated actions.
        correction = 2 * (math.log(2.) - raw - F.softplus(-2 * raw))
        return raw.tanh(), (log_normal - correction).sum(dim=-1, keepdim=True)


class RecurrentCritic(RecurrentEncoder):
    def __init__(self):
        super().__init__()
        self.head = nn.Sequential(nn.Linear(HIDDEN + ACTION_DIM, 256), nn.ReLU(), nn.Linear(256, 1))

    def q(self, encoded, actions):
        return self.head(torch.cat((encoded, actions), dim=-1))


@contextmanager
def _frozen(module):
    params = list(module.parameters())
    flags = [p.requires_grad for p in params]
    try:
        module.requires_grad_(False)
        yield
    finally:
        for param, flag in zip(params, flags):
            param.requires_grad_(flag)


def _step(loss, optimizer):
    if not torch.isfinite(loss):
        raise ValueError('Nonfinite recurrent SAC loss')
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    params = [p for g in optimizer.param_groups for p in g['params'] if p.grad is not None]
    if not params:
        raise ValueError('Disconnected recurrent SAC gradient')
    norm = nn.utils.clip_grad_norm_(params, max_norm=10., error_if_nonfinite=True)
    optimizer.step()
    return norm.item()


class RecurrentUpdater:
    """Atomic Torch updates on continuous, permission-checked replay subsequences."""
    def __init__(self, settings):
        self.settings = deepcopy(settings)
        rates = optimizer_learning_rates(settings)
        if (not 0 < settings['tau'] <= 1 or settings['target_entropy'] != -5
                or not math.isfinite(settings['entropy_initial']) or settings['entropy_initial'] <= 0
                or settings.get('device', 'cpu') != 'cpu'):
            raise ValueError('Invalid five-axis recurrent SAC settings')
        torch.set_num_threads(settings.get('torch_threads', 1))
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(settings['seed'])
            self.actor = RecurrentActor()
            self.critics = nn.ModuleList([RecurrentCritic(), RecurrentCritic()])
            self.generator = torch.Generator().set_state(torch.get_rng_state())
        self.target_critics = deepcopy(self.critics).requires_grad_(False)
        self.log_alpha = nn.Parameter(torch.tensor(math.log(settings['entropy_initial']), dtype=torch.float32))
        self.actor_optimizer = torch.optim.Adam(self.actor.parameters(), lr=rates['actor'])
        self.critic_optimizer = torch.optim.Adam(self.critics.parameters(), lr=rates['critic'])
        self.temperature_optimizer = torch.optim.Adam([self.log_alpha], lr=rates['temperature'])
        self.counts = dict(critic=0, actor=0, temperature=0, target=0)
        self.failed = False

    @property
    def _networks(self):
        return dict(actor=self.actor, critics=self.critics, target_critics=self.target_critics)

    @property
    def _optimizers(self):
        return dict(actor=self.actor_optimizer, critic=self.critic_optimizer, temperature=self.temperature_optimizer)

    def _snapshot(self):
        state = dict(version=VERSION, settings=self.settings, counts=self.counts,
                     rng=self.generator.get_state(), log_alpha=self.log_alpha.detach())
        state.update({key: net.state_dict() for key, net in self._networks.items()})
        state.update({key+'_optimizer': opt.state_dict() for key, opt in self._optimizers.items()})
        return deepcopy(state)

    def state_dict(self):
        if self.failed:
            raise RuntimeError('Cannot checkpoint a failed update')
        return self._snapshot()

    def _restore(self, state):
        for name, net in self._networks.items():
            net.load_state_dict(state[name])
        with torch.no_grad():
            self.log_alpha.copy_(state['log_alpha'])
        for name, opt in self._optimizers.items():
            opt.load_state_dict(deepcopy(state[name+'_optimizer']))
            opt.zero_grad(set_to_none=True)
        self.generator.set_state(state['rng'])
        self.counts = state['counts'].copy()

    def load_state_dict(self, state):
        from .sac_checkpoint import _optimizer, _same, _tensor
        if (not isinstance(state, dict) or state.keys() != self._snapshot().keys()
                or state['version'] != VERSION or not _same(state['settings'], self.settings)):
            raise ValueError('Matching GRU architecture and learner settings required')
        counts = state['counts']
        if (not isinstance(counts, dict) or counts.keys() != self.counts.keys()
                or any(type(v) is not int or v < 0 for v in counts.values())
                or counts['critic'] != counts['target'] or counts['actor'] != counts['temperature']
                or counts['actor'] > counts['critic']):
            raise ValueError('Inconsistent GRU update counts')
        for name, net in self._networks.items():
            reference = net.state_dict()
            if state[name].keys()!=reference.keys():
                raise ValueError('Incomplete GRU weights: ' + name)
            for key, expected in reference.items():
                _tensor(state[name][key], expected)
        _tensor(state['log_alpha'], self.log_alpha.detach())
        self._check_alpha(state['log_alpha'])
        _tensor(state['rng'], self.generator.get_state())
        torch.Generator().set_state(state['rng'])
        for name, opt in self._optimizers.items():
            _optimizer(state[name+'_optimizer'], opt, counts[name])
        self._restore(state)
        self.failed = False

    @staticmethod
    def _check_alpha(log_alpha):
        alpha = log_alpha.detach().exp()
        if not torch.isfinite(alpha) or alpha <= 0:
            raise ValueError('Nonfinite or zero entropy temperature')

    def _finite_state(self):
        self._check_alpha(self.log_alpha)
        for net in self._networks.values():
            if any(not p.detach().isfinite().all() for p in net.parameters()):
                raise ValueError('Nonfinite recurrent SAC weights')
        for opt in self._optimizers.values():
            for state in opt.state.values():
                if any(isinstance(v, torch.Tensor) and not v.isfinite().all() for v in state.values()):
                    raise ValueError('Nonfinite recurrent SAC optimizer state')

    @staticmethod
    def _learn_rows(batch):
        from .recurrent_replay import SequenceReplayBatch
        if type(batch) is not SequenceReplayBatch:
            raise ValueError('Continuous SequenceReplayBatch required')
        batch.validate()
        learn = (batch.valid_mask & batch.learn_mask)[:, batch.burn_in:, 0]
        if not learn.any():
            raise ValueError('No learning transitions in batch')
        return learn

    @staticmethod
    def _encode(network, batch):
        return network.encode_suffix(batch.observations, batch.observation_valid_mask, batch.burn_in)

    @torch.no_grad()
    def _targets(self, batch, learn):
        k = batch.burn_in
        next_active = batch.next_action_active[:, k:][learn]
        next_states = self._encode(self.actor, batch)[:, 1:][learn]
        actions = next_states.new_zeros(len(next_states), ACTION_DIM)
        logp = next_states.new_zeros(len(next_states), 1)
        enabled = next_active[:, 0]
        if enabled.any():
            actions[enabled], logp[enabled] = self.actor.sample(next_states[enabled], self.generator)
        qs = [q.q(self._encode(q, batch)[:, 1:][learn], actions) for q in self.target_critics]
        return critic_target(reward=batch.rewards[:, k:][learn], discount=batch.discounts[:, k:][learn],
                             terminated=batch.terminated[:, k:][learn], q_next=torch.minimum(*qs),
                             log_probability=logp, alpha=self.log_alpha.detach().exp(), next_active=next_active)

    def targets(self, batch):
        if self.failed:
            raise RuntimeError('Failed recurrent SAC updater')
        learn = self._learn_rows(batch)
        state = self.generator.get_state()
        try:
            return self._targets(batch, learn)
        finally:
            self.generator.set_state(state)

    def _policy_update(self, batch, rows):
        encoded = self._encode(self.actor, batch)[:, :-1][rows]
        actions, logp = self.actor.sample(encoded, self.generator)
        with _frozen(self.critics):
            # Rebuild encodings under the critic weights after critic_optimizer.step().
            qs = [q.q(self._encode(q, batch)[:, :-1][rows], actions) for q in self.critics]
            actor_loss, temperature_loss = actor_temperature_losses(
                q=torch.minimum(*qs), log_probability=logp, log_alpha=self.log_alpha,
                target_entropy=self.settings['target_entropy'], active=torch.ones_like(logp, dtype=torch.bool))
            norm = _step(actor_loss, self.actor_optimizer)
        temperature_norm = _step(temperature_loss, self.temperature_optimizer)
        self.counts['actor'] += 1
        self.counts['temperature'] += 1
        return actor_loss.item(), temperature_loss.item(), norm, temperature_norm

    def update(self, batch):
        if self.failed:
            raise RuntimeError('Restart from a healthy GRU checkpoint')
        saved = self._snapshot()
        try:
            learn = self._learn_rows(batch)
            self._finite_state()
            target = self._targets(batch, learn)
            actions = batch.actions[:, batch.burn_in:][learn]
            qs = [q.q(self._encode(q, batch)[:, :-1][learn], actions) for q in self.critics]
            loss = .5 * sum(F.mse_loss(q, target) for q in qs)
            critic_norm = _step(loss, self.critic_optimizer)
            self.counts['critic'] += 1
            active = learn & batch.action_active[:, batch.burn_in:, 0]
            actor_loss = temperature_loss = actor_norm = temperature_norm = None
            if active.any():
                actor_loss, temperature_loss, actor_norm, temperature_norm = self._policy_update(batch, active)
            with torch.no_grad():
                for src, dest in zip(self.critics.parameters(), self.target_critics.parameters()):
                    dest.lerp_(src, self.settings['tau'])
            self.counts['target'] += 1
            self._finite_state()
            return dict(critic_loss=loss.item(), actor_loss=actor_loss, temperature_loss=temperature_loss,
                        critic_grad_norm=critic_norm, actor_grad_norm=actor_norm, temperature_grad_norm=temperature_norm,
                        active_rows=int(active.sum()), batch_rows=int(learn.sum()),
                        alpha_after=self.log_alpha.detach().exp().item(), critic_batches=self.counts['critic'])
        except Exception:
            self._restore(saved)
            self.failed = True
            raise
