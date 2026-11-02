"""Candidate Gym-style adapter, with whole-episode quarantine, NOT SAC admission.

No auto-reset/resampling. Ordinary batch boundaries do nothing. A real external
cut uses truncate_after_step, captures the genuine next state, then audits a
separate zero-action stop tail. Generic TimeLimit wrappers bypass this protocol
and must not be used. Candidate data is ALWAYS denied publication.
"""
from copy import deepcopy
from dataclasses import asdict
import math
import gymnasium as gym
import numpy as np
from .episode_buffer import EpisodeBuffer, _safe_error_archive


class ResidualEnv(gym.Env):
    metadata = {'render_modes': []}

    def __init__(self, *, session, case):
        from .residual_session import ResidualSession
        if not isinstance(session, ResidualSession):
            raise TypeError('ResidualSession required')
        self.session, self.case = session, case
        self.action_space = gym.spaces.Box(-1., 1., shape=(4,), dtype=np.float32)
        self.observation_space = gym.spaces.Box(-10., 10., shape=(120,), dtype=np.float32)
        self.attempts, self.sink = [], []
        self._active = False

    def _vector(self, snapshot):
        vector = np.array(snapshot.policy_observation, dtype=np.float32)
        if not self.observation_space.contains(vector):
            raise ValueError('Invalid policy vector; refuse numeric substitution')
        return vector

    def reset(self, *, seed=None, options=None):
        if self._active:
            raise RuntimeError('Cannot reset active episode; finish or explicitly truncate it')
        self.buffer = EpisodeBuffer()
        self._attempt = dict(seed=_safe_error_archive(seed), options=_safe_error_archive(options))
        try:
            super().reset(seed=seed)
            if options is not None and not isinstance(options, dict):
                raise TypeError('reset options must be a dictionary or None')
            selected = self.case if options is None else options.get('case', self.case)
            self._attempt['case'] = _safe_error_archive(asdict(selected))
            snap = self.session.reset(selected, seed=seed)
            vector = self._vector(snap)
        except Exception as exc:
            self._record_attempt(outcome=dict(simulation_valid=False, task_outcome='INVALID_INITIALIZATION',
                physical_stopped=False, valid_for_learning=False, training_admitted=False),
                fault=dict(error=repr(exc)))
            raise
        self._active = True
        return vector, dict(training_admitted=False, observation_version=self.session.observations.version,
                            privileged_evaluation=deepcopy(snap.privileged_evaluation))

    def _record_attempt(self, *, outcome, fault=None):
        publication = self.buffer.finalize(valid_for_learning=False, sink=self.sink)
        record = dict(self._attempt, outcome=deepcopy(outcome), publication=publication,
                      quarantined=deepcopy(self.buffer.quarantined))
        if fault is not None:
            record['fault'] = _safe_error_archive(fault)
        self.attempts.append(_safe_error_archive(record))
        self._active = False

    def _fault(self, exc, action):
        s = self.session
        # Close before diagnostics. Preserve original native failure where present.
        if s.env.guard_facts['simulation_valid']:
            s.env._terminate('INVALID_INTERFACE_DATA')
        s.done = s.task_finished = True
        self._record_attempt(outcome=s.adjudicate(), fault=dict(error=repr(exc), action=action,
            native_time_s=float(s.env.data.time), guard_facts=s.env.guard_facts,
            interface_fault=s.interface_fault))

    def step(self, action):
        return self._step(action, external_cut=False)

    def truncate_after_step(self, action):
        """Explicit real cutoff, not an ordinary rollout/minibatch boundary."""
        return self._step(action, external_cut=True)

    def _step(self, action, *, external_cut):
        if not self._active:
            raise RuntimeError('Reset or completed episode; no active interaction')
        s = self.session
        try:
            before = s.prepare_cycle()
            result = s.advance_cycle(action)
            obs = self._vector(result.next_snapshot)
            terminated = bool(result.done)
            truncated = bool(external_cut and not terminated)
            discount = math.exp(-result.dt/10.)
            info = dict(dt=result.dt, discount=discount, reward_terms=deepcopy(result.reward_terms),
                        action_log=deepcopy(result.action_log), outcome=deepcopy(result.outcome),
                        events=deepcopy(result.events), training_admitted=False,
                        privileged_evaluation=deepcopy(result.next_snapshot.privileged_evaluation))
            self.buffer.stage(dict(observation=self._vector(before).tolist(), next_observation=obs.tolist(),
                action=result.action_log['experience_action'], action_active=before.residual_enabled,
                next_action_active=result.next_snapshot.residual_enabled, reward=result.reward_terms['total'],
                reward_terms=deepcopy(result.reward_terms), dt=result.dt, discount=discount,
                terminated=terminated, truncated=truncated, action_log=deepcopy(result.action_log)))
        except Exception as exc:
            self._fault(exc, action)
            raise
        if truncated:
            info['cut_time_s'] = result.next_snapshot.time_s
            try:
                s.start_external_tail()
                while not s.done:
                    s.advance_cycle([0.]*4)
            except Exception as exc:
                self._fault(exc, [0.]*4)
                info['outcome'] = deepcopy(self.attempts[-1]['outcome'])
            else:
                info['outcome'] = s.adjudicate()
                self._record_attempt(outcome=info['outcome'])
            info['audit_end_time_s'] = _safe_error_archive(float(s.env.data.time))
        elif terminated:
            self._record_attempt(outcome=result.outcome)
        return obs, result.reward_terms['total'], terminated, truncated, info

    def close(self):
        if self._active:
            raise RuntimeError('Finish or explicitly truncate active episode before closing')
