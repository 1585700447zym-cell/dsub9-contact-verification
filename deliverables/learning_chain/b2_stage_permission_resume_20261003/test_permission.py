"""Offline behavior checks only: synthetic snapshots and immutable archive reads."""
from copy import deepcopy
import gzip
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))


def implementation(name):
    path = HERE / (name + '.py')
    assert path.is_file(), f'Missing required implementation: {path.name}'
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def forbid_calculation(monkeypatch, tmp_path):
    monkeypatch.setenv('MPLCONFIGDIR', str(tmp_path / 'matplotlib'))
    import torch
    def forbidden(*args, **kwargs):
        raise AssertionError('Physical, model or optimizer calculation is forbidden in offline tests')
    monkeypatch.setattr(torch.nn.Module, '_call_impl', forbidden)
    monkeypatch.setattr(torch.optim.Adam, 'step', forbidden)
    # Importing the local package does not create a model or run physics.
    from tools.learning.runtime import active_package
    monkeypatch.syspath_prepend(str(active_package()))
    import mujoco
    for name in ('mj_step', 'mj_step1', 'mj_step2', 'mj_forward', 'mj_resetData', 'mj_resetDataKeyframe'):
        monkeypatch.setattr(mujoco, name, forbidden)


def snapshot(phase='INSERT', physical='RUNNING', enabled=True):
    from tools.learning.types import CycleSnapshot
    state = dict(position_m=[0., 0., -.004], quaternion_wxyz=[1., 0., 0., 0.],
        velocity_world=[0.] * 6, contact_wrench_M=[0.] * 6,
        reference_qpos=[0., 0., -.004, 1., 0., 0., 0.], limited_command_world=[0.] * 6,
        phase=physical, penetration_m=0., contact_count=0)
    controller = dict(phase=phase, phase_start=0., search_count=0, theta=0.,
        search_origin=None, history=[(0., 0.)], admittance_velocity=[0.] * 4,
        admittance_offset=[0.] * 4)
    return CycleSnapshot(0, 0., [0., 0., .0001, 0., 0., 0.], enabled, state, controller)


def session(monkeypatch, mode, snap, *, features=True):
    from tools.learning.residual_session import ResidualSession
    from tools.learning.session import EpisodeSession
    from tools.learning.observation import ObservationBuilder
    from tools.control.search_recovery import SearchConfig
    config = SearchConfig()
    facts = dict(simulation_valid=True, invalid_reasons=[], contact_reasons=[], motion_reasons=[])
    env = SimpleNamespace(reference=np.array(snap.state['reference_qpos']), recovery_count=0,
        events=[], guard_facts=facts, command=np.zeros(6), config=SimpleNamespace(control_period=.002))
    def initialize(self, *, environment, controller_factory=None, action_scale=None):
        self.env = environment
        self._action_scale = tuple(action_scale)
        self._ready = self._features_ready = True
        self._cache = self._decorated_cache = None
        self.done = self.task_finished = False
    def prepare(self):
        if self._cache is None:
            self._cache = deepcopy(snap)
        return deepcopy(self._cache)
    monkeypatch.setattr(ResidualSession, '__init__', initialize)
    monkeypatch.setattr(EpisodeSession, 'prepare_cycle', prepare)
    cls = implementation('stage_session').StageSession
    value = cls(environment=env, mode=mode)
    value.reason = value.recovery_state = value.hold_start = value.wait_start = value.stop_time = None
    value.previous_residual = [0.] * 4
    value.case = SimpleNamespace(name='synthetic')
    value.observations = ObservationBuilder(snap.state, config)
    value._features_ready = features
    return value


@pytest.mark.parametrize('mode,phase,physical,base_active,want', [
    ('F', 'INSERT', 'RUNNING', True, True), ('F', 'SEARCH', 'RUNNING', True, True),
    ('S', 'INSERT', 'RUNNING', True, False), ('S', 'SEARCH', 'RUNNING', True, True),
    ('S', 'UNLOAD', 'RUNNING', False, False), ('S', 'WAIT_RECOVERY', 'STOPPING', False, False),
    ('S', 'SEARCH', 'RETRACT', False, False), ('S', 'SEARCH', 'STOPPING', False, False),
    ('S', 'SEARCH', 'RUNNING', False, False), ('F', 'SEARCH', 'RUNNING', False, False),
])
def test_permission_reaches_same_observation_command_and_experience(monkeypatch, mode, phase, physical, base_active, want):
    value = session(monkeypatch, mode, snapshot(phase, physical, base_active))
    before = value.prepare_cycle()
    assert before.residual_enabled is want
    assert before.policy_observation[76] == float(want)
    assert before.policy_raw['action_active'] == [float(want)]
    assert value.observe().residual_enabled is want
    value._command_for_action(before, np.array([1., -1., 1., -1.]))
    assert value.last_action_log['experience_action'] == ([1., -1., 1., -1.] if want else [0.] * 4)
    assert value.last_action_log['applied_residual'] == ([.00005, -.00005, 0., .0005, -.0005, 0.] if want else [0.] * 6)
    assert value.last_action_log['stage_limited_total'] == ([.00005, -.00005, .0001, .0005, -.0005, 0.] if want else before.base_command)


def test_reset_intermediate_snapshot_is_already_restricted(monkeypatch):
    value = session(monkeypatch, 'S', snapshot(), features=False)
    assert value.prepare_cycle().residual_enabled is False
    assert value.observe().residual_enabled is False


def test_repeat_observation_preserves_cache_and_sessions_are_isolated(monkeypatch):
    snap = snapshot()
    fixed = session(monkeypatch, 'F', snap)
    restricted = session(monkeypatch, 'S', snap)
    a, b = fixed.prepare_cycle(), restricted.prepare_cycle()
    history = deepcopy(restricted.observations._history)
    for _ in range(3):
        assert fixed.prepare_cycle() == a
        assert restricted.prepare_cycle() == b
        assert restricted.observe() == b
    assert restricted.observations._history == history
    assert a.residual_enabled is True and b.residual_enabled is False


def test_search_exit_stops_residual_and_reentry_uses_current_permission(monkeypatch):
    snap = snapshot('SEARCH')
    value = session(monkeypatch, 'S', snap)
    for cycle, phase, physical, base_active, want in (
        (0, 'SEARCH', 'RUNNING', True, True),
        (1, 'INSERT', 'RUNNING', True, False),
        (2, 'SEARCH', 'RUNNING', True, True),
        (3, 'SEARCH', 'STOPPING', False, False),
    ):
        snap.cycle_id, snap.time_s = cycle, cycle * .002
        snap.controller_state['phase'] = phase
        snap.state['phase'] = physical
        snap.residual_enabled = base_active
        value._cache = None
        current = value.prepare_cycle()
        assert current.residual_enabled is want
        assert current.policy_observation[76] == float(want)
        value._command_for_action(current, np.ones(4))
        assert value.last_action_log['experience_action'] == ([1.] * 4 if want else [0.] * 4)
        assert value.previous_residual == ([.00005, .00005, .0005, .0005] if want else [0.] * 4)


@pytest.mark.parametrize('mode,scale', [('X', [.00005, .00005, .0005, .0005]), ('S', [.00015, .00015, .0005, .0005])])
def test_unregistered_mode_or_scale_refused_before_environment(mode, scale):
    cls = implementation('stage_session').StageSession
    with pytest.raises(ValueError):
        cls(environment=object(), mode=mode, action_scale=scale)


@pytest.fixture(scope='module')
def archived_fixture():
    path = ROOT / 'deliverables/learning_chain/b2_frozen_c2000_closeout_20261001/small/collections/0/x_pos_100/episode.json.gz'
    raw = json.loads(gzip.decompress(path.read_bytes()))
    raw['stage_mode'] = 'F'
    return raw


def as_search_fixture(raw):
    """In-memory audit fixture; never published as physical evidence."""
    raw = deepcopy(raw)
    raw['stage_mode'] = 'S'
    for row in raw['transitions']:
        for name in ('observation', 'next_observation'):
            obs = row[name]
            obs[76] = float(bool(obs[55] and obs[58] and not obs[75] and not any(obs[78:86])))
        row['action_active'] = bool(row['observation'][76])
        row['next_action_active'] = bool(row['next_observation'][76])
        log = row['action_log']
        log['enabled'] = row['action_active']
        log['applied_residual'] = log['requested_residual'] if row['action_active'] else [0.] * 6
        row['action'] = log['experience_action'] = log['raw_action'] if row['action_active'] else [0.] * 4
    return raw


@pytest.mark.parametrize('mode', ['F', 'S'])
def test_complete_archive_rules_accept_own_mode_and_stamp_distinguishes_modes(archived_fixture, mode):
    raw = deepcopy(archived_fixture) if mode == 'F' else as_search_fixture(archived_fixture)
    rules = implementation('stage_rules').StageRules(mode)
    stamp = rules.classify(raw)
    assert stamp['stage_mode'] == mode
    assert rules.receipt_valid(dict(stage_mode=mode, guard_clear=True,
        task_outcome=raw['outcome']['task_outcome'], learning_eligibility=stamp))
    other = implementation('stage_rules').StageRules('S' if mode == 'F' else 'F')
    assert other.version != rules.version
    assert not other.receipt_valid(dict(stage_mode=mode, guard_clear=True,
        task_outcome=raw['outcome']['task_outcome'], learning_eligibility=stamp))
    with pytest.raises(ValueError):
        other.classify(raw)


@pytest.mark.parametrize('fault', ['mode', 'old_scale', 'obs_active', 'next_active', 'insert_enabled', 'experience', 'invalid_onehot', 'pending_without_decision'])
def test_audit_rejects_mapping_or_permission_tampering(archived_fixture, fault):
    raw = as_search_fixture(archived_fixture)
    row = raw['transitions'][0]
    if fault == 'mode':
        raw['stage_mode'] = 'F'
    elif fault == 'old_scale':
        row['action_log']['requested_residual'][0] += .0001
    elif fault == 'obs_active':
        row['observation'][76] = 1.
    elif fault == 'next_active':
        row['next_observation'][76] = 1.
    elif fault == 'insert_enabled':
        # Change the full chain consistently; a mapping-only reader would accept it.
        raw = deepcopy(archived_fixture)
        raw['stage_mode'] = 'S'
    elif fault == 'experience':
        row['action_log']['experience_action'] = [1.] * 4
    elif fault == 'invalid_onehot':
        row['observation'][54] = 1.
    elif fault == 'pending_without_decision':
        row['observation'][75] = 1.
    with pytest.raises(ValueError):
        implementation('stage_rules').StageRules('S').classify(raw)


def test_search_rules_allow_no_active_search_for_separate_training_gate(archived_fixture):
    raw = as_search_fixture(archived_fixture)
    for row in raw['transitions']:
        for key in ('observation', 'next_observation'):
            row[key][53:58] = [1., 0., 0., 0., 0.]
            row[key][76] = 0.
        row['action_active'] = row['next_action_active'] = False
        row['action'] = row['action_log']['experience_action'] = [0.] * 4
        row['action_log']['enabled'] = False
        row['action_log']['applied_residual'] = [0.] * 6
    assert implementation('stage_rules').StageRules('S').classify(raw)['kind'] == 'guard_clear'
