"""Opt-in collection noise held for 25 active 2 ms cycles.

Only epsilon is cached. A caller still evaluates the current policy parameters,
admittance and guards every cycle. SAC update-time sampling is not changed.
"""
from copy import deepcopy
import numpy as np


VERSION = 'five_axis_collection_noise_hold_v2'


class HeldExploration:
    def __init__(self, seed, *, hold_cycles=25, distribution='normal'):
        if type(hold_cycles) is not int or hold_cycles <= 0:
            raise ValueError('Positive integer hold_cycles required')
        if distribution not in ('normal', 'uniform'):
            raise ValueError('Normal epsilon or uniform prewarm action required')
        self.hold_cycles = hold_cycles
        self.distribution = distribution
        self.clock_seed = int(seed) if isinstance(seed, (int, np.integer)) and not isinstance(seed, bool) and seed >= 0 else None
        self.rng = np.random.default_rng(seed)
        self.reset()

    def _clear(self):
        self.cached_noise = None
        self.phase = None
        self.remaining_cycles = 0
        self.clock_slot = None

    def reset(self, *, seed=None):
        """Clear episode state; reseed only when explicitly requested."""
        if seed is not None:
            self.rng = np.random.default_rng(seed)
            self.clock_seed = int(seed) if isinstance(seed, (int, np.integer)) and not isinstance(seed, bool) and seed >= 0 else None
        self._clear()
        self.active_calls = self.disabled_calls = self.draw_count = 0
        self.clock_last_cycle = None
        self.clock_draw_count = 0
        self.last_log = {}

    def noise(self, *, phase, enabled):
        if type(enabled) not in (bool, np.bool_):
            raise ValueError('Boolean exploration permission required')
        if not isinstance(phase, str):
            raise ValueError('Controller phase string required')
        if self.last_log.get('mode') == 'absolute':
            self._clear()
        refreshed = False
        if not enabled:
            self.disabled_calls += 1
            self._clear()
            value = np.zeros(5)
        else:
            if phase not in ('INSERT', 'SEARCH'):
                raise ValueError('Exploration is permitted only in INSERT/SEARCH')
            if phase != self.phase:
                self._clear()
                self.phase = phase
            if self.remaining_cycles == 0:
                self.cached_noise = (self.rng.standard_normal(5) if self.distribution == 'normal'
                                     else self.rng.uniform(-1., 1., 5))
                self.remaining_cycles = self.hold_cycles
                self.draw_count += 1
                refreshed = True
            value = self.cached_noise.copy()
            self.remaining_cycles -= 1
            self.active_calls += 1
        self.last_log = dict(mode='active', phase=phase, enabled=bool(enabled), distribution=self.distribution,
            hold_cycles=self.hold_cycles, refreshed=refreshed, draw_count=self.draw_count,
            active_calls=self.active_calls, disabled_calls=self.disabled_calls,
            remaining_cycles=self.remaining_cycles, noise=value.tolist())
        return value

    def noise_at(self, cycle, *, phase, enabled):
        """Paired trials use a seed/absolute-cycle tape independent of phase history.

        Cycles must be strictly increasing; skipped cycles are allowed. Clearing
        a phase rereads the same slot without advancing the exogenous sequence.
        Thus an interrupted slot may have less than 50 ms of active use.
        """
        if type(cycle) is not int or cycle < 0:
            raise ValueError('Nonnegative integer absolute cycle required')
        if self.clock_last_cycle is not None and cycle <= self.clock_last_cycle:
            raise ValueError('Absolute cycles must be strictly increasing')
        if self.clock_seed is None:
            raise ValueError('Absolute noise requires an explicit nonnegative integer seed')
        if type(enabled) not in (bool, np.bool_) or not isinstance(phase, str):
            raise ValueError('Controller phase and Boolean exploration permission required')
        if enabled and phase not in ('INSERT', 'SEARCH'):
            raise ValueError('Exploration is permitted only in INSERT/SEARCH')
        if self.last_log.get('mode') == 'active':
            self._clear()
        slot = cycle // self.hold_cycles
        refreshed = False
        if not enabled:
            self.disabled_calls += 1
            self._clear()
            value = np.zeros(5)
        else:
            if phase != self.phase:
                self._clear()
                self.phase = phase
            if self.cached_noise is None or self.clock_slot != slot:
                slot_rng = np.random.default_rng(np.random.SeedSequence([self.clock_seed, slot]))
                self.cached_noise = (slot_rng.standard_normal(5) if self.distribution == 'normal'
                                     else slot_rng.uniform(-1., 1., 5))
                self.clock_slot = slot
                self.draw_count += 1
                self.clock_draw_count += 1
                refreshed = True
            value = self.cached_noise.copy()
            self.remaining_cycles = self.hold_cycles - cycle % self.hold_cycles - 1
            self.active_calls += 1
        self.clock_last_cycle = cycle
        self.last_log = dict(mode='absolute', cycle=cycle, noise_slot=slot,
            phase=phase, enabled=bool(enabled), distribution=self.distribution,
            hold_cycles=self.hold_cycles, refreshed=refreshed, draw_count=self.draw_count,
            clock_draw_count=self.clock_draw_count, active_calls=self.active_calls,
            disabled_calls=self.disabled_calls, remaining_cycles=self.remaining_cycles,
            noise=value.tolist())
        return value

    def action_from_parameters(self, mean, log_std, *, phase, enabled):
        """Pure NumPy helper; a Torch caller may instead use noise() directly."""
        if self.distribution != 'normal':
            raise ValueError('Policy parameters require normal epsilon')
        mean, log_std = np.asarray(mean, dtype=float), np.asarray(log_std, dtype=float)
        if mean.shape != (5,) or log_std.shape != (5,) or not np.isfinite(np.r_[mean, log_std]).all():
            raise ValueError('Finite five-axis mean and log_std required')
        epsilon = self.noise(phase=phase, enabled=enabled)
        if not enabled:
            return np.zeros(5)
        with np.errstate(over='raise', invalid='raise'):
            return np.tanh(mean + np.exp(log_std) * epsilon)

    def state_dict(self):
        return dict(version=VERSION, hold_cycles=self.hold_cycles, distribution=self.distribution,
            rng=deepcopy(self.rng.bit_generator.state), phase=self.phase,
            cached_noise=None if self.cached_noise is None else self.cached_noise.tolist(),
            remaining_cycles=self.remaining_cycles, active_calls=self.active_calls,
            disabled_calls=self.disabled_calls, draw_count=self.draw_count,
            clock_seed=self.clock_seed, clock_last_cycle=self.clock_last_cycle,
            clock_slot=self.clock_slot, clock_draw_count=self.clock_draw_count,
            last_log=deepcopy(self.last_log))

    def load_state_dict(self, state):
        expected = {'version', 'hold_cycles', 'distribution', 'rng', 'phase', 'cached_noise',
                    'remaining_cycles', 'active_calls', 'disabled_calls', 'draw_count', 'last_log',
                    'clock_seed', 'clock_last_cycle', 'clock_slot', 'clock_draw_count'}
        if (not isinstance(state, dict) or set(state) != expected or state['version'] != VERSION
                or state['hold_cycles'] != self.hold_cycles or state['distribution'] != self.distribution):
            raise ValueError('Matching complete exploration state required')
        counts = [state[k] for k in ('remaining_cycles', 'active_calls', 'disabled_calls', 'draw_count')]
        if any(type(v) is not int or v < 0 for v in counts) or state['remaining_cycles'] >= self.hold_cycles:
            raise ValueError('Invalid exploration counters')
        for key in ('clock_seed', 'clock_last_cycle', 'clock_slot'):
            if state[key] is not None and (type(state[key]) is not int or state[key] < 0):
                raise ValueError('Invalid absolute noise clock')
        if type(state['clock_draw_count']) is not int or state['clock_draw_count'] < 0:
            raise ValueError('Invalid absolute noise draw count')
        phase, cached = state['phase'], state['cached_noise']
        if cached is None:
            if phase is not None or state['remaining_cycles'] != 0:
                raise ValueError('Empty noise requires a cleared hold state')
            value = None
        else:
            value = np.asarray(cached, dtype=float)
            if phase not in ('INSERT', 'SEARCH') or value.shape != (5,) or not np.isfinite(value).all():
                raise ValueError('Invalid held noise')
            if self.distribution == 'uniform' and (abs(value) > 1).any():
                raise ValueError('Uniform prewarm action outside bounds')
        if not isinstance(state['last_log'], dict):
            raise ValueError('Exploration log dictionary required')
        rng = np.random.default_rng()
        rng.bit_generator.state = deepcopy(state['rng'])
        self.rng, self.phase, self.cached_noise = rng, phase, None if value is None else value.copy()
        self.remaining_cycles = state['remaining_cycles']
        self.active_calls, self.disabled_calls, self.draw_count = counts[1:]
        self.clock_seed, self.clock_last_cycle = state['clock_seed'], state['clock_last_cycle']
        self.clock_slot, self.clock_draw_count = state['clock_slot'], state['clock_draw_count']
        self.last_log = deepcopy(state['last_log'])
