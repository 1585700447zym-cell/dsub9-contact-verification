"""New execution-contract binding and synthetic SAC state; no native rollouts."""
from copy import deepcopy
from importlib import import_module
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest
import torch


def api():
    return import_module('tools.learning.consistent_sac')


def observation(active=True):
    from tools.learning.five_axis_contract import field_slices
    spans = field_slices(); value = np.zeros(140, dtype=np.float32)
    for name, index in [('policy_phase', 0 if active else 1), ('physical_phase', 0),
                        ('recovery_phase', 0), ('decision', 0)]:
        value[spans[name].start + index] = 1.
    value[spans['simulation_valid']] = 1.
    value[spans['action_active']] = active
    return value


def rows():
    active, inactive = observation().tolist(), observation(False).tolist()
    return [dict(observation=active, next_observation=active, action=[.1] * 5,
                 reward=-.01, dt=.002, discount=math.exp(-.002 / 10), terminated=False,
                 truncated=False, action_active=True, next_action_active=True),
            dict(observation=active, next_observation=inactive, action=[.1] * 5,
                 reward=-2., dt=.002, discount=math.exp(-.002 / 10), terminated=True,
                 truncated=False, action_active=True, next_action_active=False)]


OUTCOME = dict(simulation_valid=True, physical_stopped=True, valid_for_learning=True)


def test_exact_new_contract_and_config_refuse_legacy_or_changed_execution():
    m = api()
    from tools.dynamics.reference_envelope import VERSION
    from tools.learning.five_axis_contract import learning_config as old_config
    from tests.test_reference_consistency import session_fixture
    expected = dict(version='global_residual_G1_30s_reference_consistent_v1',
        observation_version='five_axis_short_history_N2_30s_v1',
        action_scale=[.0005, .0005, .0005, .0005, .005], task_deadline_s=30.,
        max_cycles=16000, reference_consistency_version=VERSION)
    assert m.execution_contract() == expected == session_fixture().contract
    config = m.learning_config()
    assert config['execution_contract'] == expected
    assert config['learning']['replay_capacity'] == 192000
    assert config['learning']['entropy_initial'] == .01
    assert config['learning']['seed'] == 2026092716
    assert m.validate_config(config) == config
    with pytest.raises(ValueError): m.validate_config(old_config())
    for field in ('version', 'observation_version', 'action_scale', 'task_deadline_s',
                  'max_cycles', 'reference_consistency_version'):
        wrong = deepcopy(config); wrong['execution_contract'][field] = None
        with pytest.raises(ValueError): m.validate_config(wrong)


def test_actual_update_complete_checkpoint_next_sample_and_predictions_match(tmp_path):
    m = api()
    from tools.learning.sac_checkpoint import _same
    trainer = m.Trainer(m.learning_config())
    assert trainer.updater.policy.observation_space.shape == (140,)
    assert trainer.updater.policy.action_space.shape == (5,)
    trainer.publish('synthetic', rows(), outcome=OUTCOME, training_admitted=True)
    before = trainer.updater.fingerprints()
    result = trainer.update_from_replay()
    assert result['batch_rows'] == 256 and result['active_rows'] == 256
    assert all(before[key] != trainer.updater.fingerprints()[key] for key in before)
    trainer.action(observation()); trainer.action(observation(), warmup=True)
    target = tmp_path / 'new-checkpoint'
    digest = m.save_checkpoint(trainer, target)
    manifest = json.loads((target / 'manifest.json').read_text())
    assert manifest['version'] == m.CHECKPOINT_VERSION
    assert manifest['state_version'] == m.STATE_VERSION
    assert manifest['execution_contract_sha256'] == m.contract_digest(m.execution_contract())
    assert manifest['config_sha256'] == m.contract_digest(trainer.config)
    restored = m.load_checkpoint(target, expected_digest=digest, config=trainer.config)
    assert _same(trainer.state_dict(), restored.state_dict())
    for options in ({'deterministic': True}, {}, {'warmup': True}):
        np.testing.assert_array_equal(trainer.action(observation(), **options),
                                      restored.action(observation(), **options))
    left = trainer.replay.sample(256, rng=trainer.replay_rng)
    right = restored.replay.sample(256, rng=restored.replay_rng)
    for key in left.__dataclass_fields__:
        assert torch.equal(getattr(left, key), getattr(right, key))
    assert _same(trainer.state_dict(), restored.state_dict())
    with pytest.raises(FileExistsError): m.save_checkpoint(trainer, target)
    with pytest.raises(ValueError):
        m.load_checkpoint(target, expected_digest='0' * 64, config=trainer.config)
    manifest['execution_contract_sha256'] = '0' * 64
    (target / 'manifest.json').write_text(json.dumps(manifest))
    from hashlib import sha256
    wrong_digest = sha256((target / 'manifest.json').read_bytes()).hexdigest()
    with pytest.raises(ValueError):
        m.load_checkpoint(target, expected_digest=wrong_digest, config=trainer.config)


def test_old_or_incomplete_state_is_rejected_without_mutation():
    m = api()
    from tools.learning.sac_checkpoint import _same
    from tools.learning.five_axis_contract import learning_config as old_config
    from tools.learning.five_axis_training import FiveAxisTrainer
    trainer = m.Trainer(m.learning_config()); before = trainer.state_dict()
    with pytest.raises(ValueError): trainer.load_state_dict(FiveAxisTrainer(old_config()).state_dict())
    bad = deepcopy(before); bad['execution_contract']['task_deadline_s'] = 25.
    with pytest.raises(ValueError): trainer.load_state_dict(bad)
    bad = deepcopy(before); del bad['warm_rng']
    with pytest.raises(ValueError): trainer.load_state_dict(bad)
    assert _same(before, trainer.state_dict())


@pytest.mark.parametrize('fail', [False, True])
def test_collection_binds_actual_session_and_error_archives(fail):
    m = api()
    class OneStepSession:
        def __init__(self):
            self.contract = m.execution_contract(); self.reset_calls = 0
            self.observations = SimpleNamespace(version=self.contract['observation_version'], schema=[])
        def reset(self, case, seed=None):
            self.reset_calls += 1
            if fail: raise RuntimeError('synthetic reset failure')
            self.snap = SimpleNamespace(policy_observation=observation(False).tolist(),
                                        residual_enabled=False, state={})
        def prepare_cycle(self): return self.snap
        def advance_cycle(self, action):
            return SimpleNamespace(next_snapshot=self.snap, action_log=dict(experience_action=action),
                reward_terms={'total': -.1}, dt=.002, done=True, trace_row={}, cycle_peaks={}, events=[])
        def adjudicate(self): return dict(OUTCOME, valid_for_learning=False)
    session = OneStepSession()
    if fail:
        with pytest.raises(m.CollectionError) as caught:
            m.collect_episode(session, None, policy=lambda _: pytest.fail('Inactive policy called'))
        raw = caught.value.archive
    else:
        raw = m.collect_episode(session, None, policy=lambda _: pytest.fail('Inactive policy called'))
    from tools.learning.five_axis_contract import VERSION as kernel
    assert raw['version'] == session.contract['version']
    assert raw['execution_contract'] == session.contract
    assert raw['learning_version'] == m.VERSION and raw['collection_kernel_version'] == kernel
    assert raw['observation_version'] == session.contract['observation_version']
    session = OneStepSession(); session.contract['task_deadline_s'] = 25.
    with pytest.raises(ValueError): m.collect_episode(session, None, policy=lambda _: [0.] * 5)
    assert session.reset_calls == 0
