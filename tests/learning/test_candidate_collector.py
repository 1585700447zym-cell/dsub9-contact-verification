"""Collector orchestration fixtures; actual native integration is tested separately."""
from copy import deepcopy
import math

import numpy as np
import pytest


class CandidateFixture:
    def __init__(self, end_at=5):
        self.attempts, self.rows = [], []
        self.end_at, self.reset_count, self.tail_count = end_at, 0, 0

    def reset(self, **kwargs):
        self.reset_count += 1
        self.rows = []
        return np.zeros(120, dtype=np.float32), {'training_admitted': False}

    def step(self, action): return self.advance(action, False)
    def truncate_after_step(self, action):
        self.tail_count += 1
        return self.advance(action, True)

    def advance(self, action, cut):
        i = len(self.rows)
        terminated = i + 1 == self.end_at
        truncated = cut and not terminated
        obs = np.full(120, (i + 1) / 100, dtype=np.float32)
        self.rows.append(dict(observation=[i / 100] * 120, next_observation=obs.tolist(),
            action=list(action), action_active=True, next_action_active=True,
            reward=-.1, dt=.002, discount=math.exp(-.002 / 10),
            terminated=terminated, truncated=truncated))
        if terminated or truncated:
            self.attempts.append(dict(outcome=dict(simulation_valid=True, physical_stopped=True,
                valid_for_learning=False, task_outcome='VALID_FAILURE'),
                quarantined=deepcopy(self.rows)))
        return obs, -.1, terminated, truncated, {'training_admitted': False}


class PolicyFixture:
    def predict(self, obs, deterministic=False):
        return np.array([.1, -.2, .3, -.4]), None


def make_collector(env=None, policy=None):
    from tools.learning.audited_replay import AuditedReplay
    from tools.learning.candidate_collector import CandidateCollector
    return CandidateCollector(env=env or CandidateFixture(), policy=policy or PolicyFixture(),
                              replay=AuditedReplay(capacity=20))


def test_batch_boundary_keeps_same_episode_and_no_eager_insertion():
    c = make_collector()
    c.start('attempt-1', seed=7)
    assert c.collect(2)['steps'] == 2
    assert c.active and not len(c.replay) and not c.env.attempts
    assert c.env.reset_count == 1 and c.env.tail_count == 0
    with pytest.raises(RuntimeError): c.start('attempt-2')
    result = c.collect(10)
    assert result['steps'] == 3 and not c.active
    assert c.env.reset_count == 1 and len(c.attempts) == 1
    assert c.attempts[0]['publication']['discarded'] == 5
    assert len(c.replay) == 0


def test_explicit_cut_does_not_reset_or_replace_bootstrap():
    c = make_collector()
    c.start('cut')
    c.collect(2, cut_at_end=True)
    assert not c.active and c.env.tail_count == 1
    assert c.attempts[0]['environment']['quarantined'][-1]['truncated']
    assert c.env.reset_count == 1
    with pytest.raises(RuntimeError): c.collect(1)
    with pytest.raises(RuntimeError): c.start('cut')


def test_policy_fault_audits_stop_and_keeps_failed_attempt():
    class BadPolicy:
        def predict(self, *args, **kwargs): raise RuntimeError('policy failed')
    c = make_collector(policy=BadPolicy())
    c.start('bad-policy')
    with pytest.raises(RuntimeError, match='policy failed'): c.collect(2)
    assert not c.active and c.env.tail_count == 1
    assert c.attempts[0]['fault']['error'] == "RuntimeError('policy failed')"
    assert c.attempts[0]['publication']['committed'] == 0
    assert c.attempts[0]['environment']['outcome']['physical_stopped']


def test_emergency_cut_cost_is_not_hidden_in_policy_step_count():
    class BadPolicy:
        def predict(self, *args, **kwargs): raise RuntimeError('policy failed')
    c = make_collector(policy=BadPolicy())
    c.start('cost')
    with pytest.raises(RuntimeError): c.collect(1)
    record = c.attempts[0]
    assert record['steps'] == 0
    assert record['emergency_cut_attempts'] == record['emergency_cut_returned_steps'] == 1
    assert record['archived_row_count'] == 1


def test_failed_initialization_is_counted_and_not_resampled():
    class BadReset(CandidateFixture):
        def reset(self, **kwargs):
            self.reset_count += 1
            raise ValueError('bad initialization')
    c = make_collector(env=BadReset())
    with pytest.raises(ValueError): c.start('bad-reset')
    assert c.env.reset_count == 1 and len(c.attempts) == 1 and not c.active
    assert c.attempts[0]['status'] == 'failed'


def test_publication_failure_is_retained_and_retry_does_not_rerun_physics(monkeypatch):
    c = make_collector()
    c.start('retry')
    original = c.replay.publish
    def fail(*args, **kwargs): raise MemoryError('publication failed')
    monkeypatch.setattr(c.replay, 'publish', fail)
    with pytest.raises(MemoryError): c.collect(2, cut_at_end=True)
    assert c.attempts[0]['status'] == 'pending_publication'
    with pytest.raises(RuntimeError): c.start('skip-failure')
    monkeypatch.setattr(c.replay, 'publish', original)
    c.retry_publication()
    assert c.env.tail_count == 1 and c.env.reset_count == 1
    assert c.attempts[0]['publication']['discarded'] == 2


@pytest.mark.parametrize('stopped', [True, False])
def test_archive_copy_failure_blocks_reset_and_can_retry_without_physics(monkeypatch, stopped):
    import tools.learning.candidate_collector as module
    c = make_collector(env=CandidateFixture(end_at=1))
    c.start('copy-failure')
    original = module.deepcopy
    def fail(record):
        record['outcome']['physical_stopped'] = stopped
        raise MemoryError('audit copy failed')
    monkeypatch.setattr(module, 'deepcopy', fail)
    with pytest.raises(MemoryError, match='audit copy failed'): c.collect(1)
    with pytest.raises(RuntimeError): c.start('must-not-skip')
    assert c.attempts[0]['status'] == 'pending_publication'
    monkeypatch.setattr(module, 'deepcopy', original)
    c.retry_publication()
    assert c.env.reset_count == 1 and len(c.env.rows) == 1 and c.env.tail_count == 0
    assert c.attempts[0]['publication']['committed'] == 0
    if stopped:
        c.start('next')
    else:
        with pytest.raises(RuntimeError): c.start('still-unsafe')


def test_unknown_stop_after_policy_and_tail_errors_blocks_reset():
    class BadPolicy:
        def predict(self, *args, **kwargs): raise ValueError('bad policy')
    class BadTail(CandidateFixture):
        def truncate_after_step(self, action): raise RuntimeError('tail failed')
    c = make_collector(env=BadTail(), policy=BadPolicy())
    c.start('unsafe')
    with pytest.raises(ValueError): c.collect(1)
    assert c.attempts[0]['fault']['stop_error'] == "RuntimeError('tail failed')"
    with pytest.raises(RuntimeError): c.start('cannot-hide')


def test_untrained_sb3_native_collection_pause_and_cut(runtime, record_property):
    import torch
    from stable_baselines3.sac.policies import SACPolicy
    from tools.learning.env import ResidualEnv
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.learning.residual_session import ResidualSession
    from tools.validation.run_b1_baseline import cases
    env = ResidualEnv(session=ResidualSession(environment=LearningEnvironment(
        guard_config=GuardCandidateConfig(max_rotation_from_start_rad=math.radians(2.5),
            initial_roll_pitch_limit_rad=math.radians(1.5)))), case=cases()[0])
    torch.manual_seed(20260924)
    policy = SACPolicy(env.observation_space, env.action_space, lambda _: .001, net_arch=[32, 32])
    policy.set_training_mode(False)
    before = {k: v.clone() for k, v in policy.state_dict().items()}
    c = make_collector(env=env, policy=policy)
    c.start('native-untrained', seed=20260924)
    c.collect(4, deterministic=True)
    assert c.active and len(env.attempts) == 0 and len(c.replay) == 0
    c.collect(4, cut_at_end=True, deterministic=True)
    rows = env.attempts[-1]['quarantined']
    assert len(rows) == 8 and rows[-1]['truncated'] and not rows[-1]['terminated']
    assert env.attempts[-1]['outcome']['physical_stopped']
    assert c.attempts[-1]['publication']['discarded'] == 8 and len(c.replay) == 0
    for k, v in before.items(): torch.testing.assert_close(policy.state_dict()[k], v, rtol=0, atol=0)
    assert not policy.actor.optimizer.state and not policy.critic.optimizer.state
    record_property('candidate_rows_discarded', 8)
    record_property('sac_updates', 0)
    env.close()
