"""Real session lifecycle over a test-only environment; no MuJoCo construction."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from tests.learning.test_five_axis_interface import api


def fake_environment():
    from tools.learning.guarded_environment import LearningEnvironment
    from tools.learning.newton_damping import NewtonProfile
    from tools.learning.newton_profile import dynamic_config
    class CommandEnvironment(LearningEnvironment):
        def __init__(self):
            self.profile = NewtonProfile(); self.config = dynamic_config(self.profile)
            self.reset_count = 0
        def reset(self, case):
            from tools.validation.run_contact_cases import _quaternion
            self.reset_count += 1; self._clear_facts(); self.phase = 'RUNNING'; self.wrench = [0.] * 6
            self.events = []; self.stop_samples = []; self.recovery_count = 0; self.physical_steps = 0
            self.data = SimpleNamespace(time=0.)
            self.initial = np.r_[case.x_offset_m, case.y_offset_m, case.start_origin_z_m, _quaternion(case)]
            self.data.qpos = self.initial.copy()
            self.reference = self.initial.copy(); self.command = np.zeros(6); self.raw_command = np.zeros(6)
            self.peaks = dict(force_N=0., torque_G_Nm=0., penetration_m=0.)
            self.begin_cycle()
            return self.observe()
        def begin_cycle(self):
            self.cycle_peaks = dict(force_N=0., torque_G_Nm=0., penetration_m=0., samples=10)
        def observe(self):
            return dict(time_s=self.data.time, position_m=self.initial[:3].tolist(),
                quaternion_wxyz=self.initial[3:].tolist(), velocity_world=[0.] * 6,
                contact_wrench_M=self.wrench.copy(), contact_wrench_G=self.wrench.copy(), penetration_m=0.,
                contact_count=0, phase=self.phase, reference_qpos=self.reference.tolist(),
                raw_command_world=self.raw_command.tolist(), limited_command_world=self.command.tolist())
        def step(self, command):
            from tools.dynamics.safety import limit_command
            self.raw_command = np.array(command)
            self.command = limit_command(command, self.command, .002, [.001] * 3 + [.03] * 3,
                [.005] * 3 + [.3] * 3)
            self.data.time += .002
            self.physical_steps += 10
            return self.observe()
        def _terminate(self, reason):
            self._facts['simulation_valid'] = False; self._facts['invalid_reasons'].append(reason)
            self.phase = 'TERMINAL'; self.events.append(dict(time_s=self.data.time, reason=reason))
    return CommandEnvironment()


def point():
    from tools.validation.yaw_pilot import pilot_cases
    return pilot_cases()[0]


def test_fifth_action_reaches_full_session_without_legacy_four_axis_rejection():
    cls = api('session').session_class()
    s = cls(fake_environment()); first = s.reset(point())
    assert len(first.policy_observation) == 140 and first.residual_enabled
    result = s.advance_cycle([0., 0., 0., 0., 1.])
    assert result.action_log['experience_action'] == [0., 0., 0., 0., 1.]
    assert result.executed_command[5] == pytest.approx(.0005)
    assert s.previous_residual == [0., 0., 0., 0., .0005]
    assert result.next_snapshot.policy_observation[137] == pytest.approx(.0005 / .03)
    assert result.outcome['training_admitted'] is False


def test_zero_residual_session_matches_current_baseline_and_reset_clears_fifth_state():
    from tools.validation.yaw_pilot import session_class
    baseline = session_class()(fake_environment())
    s = api('session').session_class()(fake_environment())
    baseline.reset(point()); s.reset(point())
    for _ in range(4):
        old = baseline.advance_cycle([0.] * 4); new = s.advance_cycle([0.] * 5)
        assert old.trace_row == new.trace_row
        np.testing.assert_array_equal(old.executed_command, new.executed_command)
    s.advance_cycle([0., 0., 0., 0., 1.]); s.reset(point())
    assert s.previous_residual == [0.] * 5
    assert s.controller.admittance.yaw_offset == 0.
    assert s.prepare_cycle().policy_observation[137] == 0.


def test_search_keeps_450_and_unload_masks_only_residual_not_baseline_yaw():
    s = api('session').session_class()(fake_environment()); s.reset(point())
    s.controller.phase = 'SEARCH'; s.controller.search_origin = np.zeros(3)
    s.controller.search_progress_origin_z_m = 0.
    s.controller.theta = 8.
    s._cache = None
    snap = s.prepare_cycle()
    assert np.linalg.norm(snap.base_command[:2]) > .0003
    command = s._command_for_action(snap, np.zeros(5))
    np.testing.assert_array_equal(command, snap.base_command)
    s.controller.phase = 'UNLOAD'; s._cache = None
    s.env.wrench[2] = -1.
    s.controller.admittance.yaw_velocity = .001
    snap = s.prepare_cycle()
    s._command_for_action(snap, np.ones(5))
    assert s.last_action_log['experience_action'] == [0.] * 5
    assert s.last_action_log['stage_limited_total'][5] == snap.base_command[5]


def test_invalid_fifth_action_closes_session_and_cannot_step_again():
    s = api('session').session_class()(fake_environment()); s.reset(point())
    with pytest.raises(ValueError): s.advance_cycle([0.] * 4)
    assert s.done and not s._ready and not s.env.guard_facts['simulation_valid']
    with pytest.raises(RuntimeError): s.advance_cycle([0.] * 5)


def test_prepare_is_idempotent_and_reference_release_preserves_yaw_memory():
    s = api('session').session_class()(fake_environment()); s.reset(point())
    updates = s.controller.admittance.yaw_updates
    s.prepare_cycle(); s.prepare_cycle()
    assert s.controller.admittance.yaw_updates == updates
    s.controller.phase = 'UNLOAD'; s.controller.search_count = 1
    s.env.wrench[2] = -1.
    s.env.reference[0] += .0001
    s.controller.admittance.offset[:2] = .0001
    s.controller.admittance.velocity[:2] = .0001
    s.controller.admittance.yaw_offset = .01
    s._cache = None
    snap = s.prepare_cycle(); yaw = s.controller.admittance.yaw_state().copy()
    s.controller.reference_release_requested = True
    s._command_for_action(snap, np.ones(5))
    np.testing.assert_array_equal(s.env.reference[:2], s.env.data.qpos[:2])
    np.testing.assert_array_equal(s.controller.admittance.offset[:2], [0., 0.])
    assert s.controller.admittance.yaw_state() == yaw
    assert not s.controller.reference_release_requested


def test_collector_quarantines_data_and_does_not_publish_without_audit():
    m = api('collection')
    class OneStepSession:
        def reset(self, case, seed=None):
            self.done = False
            from tests.learning.test_five_axis_learning import obs
            self.snap = SimpleNamespace(policy_observation=obs(False).tolist(), residual_enabled=False, state={})
            return self.snap
        def prepare_cycle(self): return self.snap
        def advance_cycle(self, action):
            assert action == [0.] * 5
            self.done = True
            return SimpleNamespace(next_snapshot=self.snap, action_log=dict(experience_action=action),
                reward_terms={'total': -.1}, dt=.002, done=True, trace_row={}, cycle_peaks={}, events=[])
        def adjudicate(self):
            return dict(simulation_valid=True, physical_stopped=True, valid_for_learning=False,
                training_admitted=False, task_outcome='TASK_FAILURE')
    raw = m.collect_episode(OneStepSession(), None, policy=lambda _: pytest.fail('Inactive policy called'), max_cycles=2)
    assert len(raw['transitions']) == 1 and raw['transitions'][0]['action'] == [0.] * 5
    assert raw['outcome']['valid_for_learning'] is False


def test_mid_episode_checkpoint_is_refused():
    trainer = api('training').FiveAxisTrainer(api('contract').learning_config())
    trainer.active_episode = True
    with pytest.raises(RuntimeError): trainer.state_dict()
    with pytest.raises(RuntimeError): trainer.update_from_replay()


def test_collector_fault_keeps_partial_evidence_and_closes_session():
    collection = api('collection')
    s = api('session').session_class()(fake_environment())
    def broken_policy(_): raise ValueError('synthetic policy failure')
    with pytest.raises(collection.CollectionError) as caught:
        collection.collect_episode(s, point(), policy=broken_policy, max_cycles=2)
    assert caught.value.archive['outcome']['simulation_valid'] is False
    assert 'synthetic policy failure' in caught.value.archive['error']
    assert len(caught.value.archive['trace']) == 1
    assert s.done and not s._ready


def test_collector_ceiling_closes_session_and_preserves_completed_cycles():
    collection = api('collection')
    s = api('session').session_class()(fake_environment())
    with pytest.raises(collection.CollectionError) as caught:
        collection.collect_episode(s, point(), policy=lambda _: [0.] * 5, max_cycles=2)
    assert len(caught.value.archive['transitions']) == 2
    assert s.done and not s._ready


def test_collection_freezes_full_stop_events_and_exact_cost_on_partial_step_failure():
    collection = api('collection')
    env = fake_environment(); s = api('session').session_class()(env)
    def fail_after_substeps(command):
        env.physical_steps += 7; env.data.time += .0014
        env.events.append({'reason': 'PARTIAL_STEP'})
        env.stop_samples.append({'time_s': .0014, 'velocity': [0.] * 6})
        s.controller.events.append({'reason': 'BEFORE_CYCLE_EVENT'})
        raise ValueError('partial physics stub failure')
    env.step = fail_after_substeps
    with pytest.raises(collection.CollectionError) as caught:
        collection.collect_episode(s, point(), policy=lambda _: [0.] * 5, max_cycles=2)
    raw = caught.value.archive
    assert raw['cost']['initialization_attempts'] == raw['cost']['initializations_completed'] == 1
    assert raw['cost']['physical_substeps'] == 7 and raw['transitions'] == []
    assert raw['cost']['wall_time_s'] >= 0.
    assert raw['evidence']['environment_events'][0]['reason'] == 'PARTIAL_STEP'
    assert raw['evidence']['controller_events'][-1]['reason'] == 'BEFORE_CYCLE_EVENT'
    assert raw['evidence']['stop_samples'][0]['time_s'] == .0014
    assert raw['evidence']['current_state']['time_s'] == .0014
    assert raw['evidence']['guard_facts']['simulation_valid'] is False
    assert raw['evidence']['interface_fault'] is not None
    assert 'stop_time_s' in raw['evidence'] and 'audit_end_time_s' in raw['evidence']
    env.events.clear(); env.stop_samples.clear()
    assert raw['evidence']['environment_events'] and raw['evidence']['stop_samples']


@pytest.mark.parametrize('invalid_return', [False, True])
def test_failed_policy_attempt_and_trainer_cost_are_archived(monkeypatch, invalid_return):
    trainer = api('training').FiveAxisTrainer(api('contract').learning_config())
    s = api('session').session_class()(fake_environment())
    def broken_predict(*args, **kwargs):
        if invalid_return: return np.zeros(4), None
        raise ValueError('failed prediction')
    monkeypatch.setattr(trainer.updater, 'predict', broken_predict)
    with pytest.raises(api('collection').CollectionError) as caught:
        trainer.collect(s, point(), max_cycles=2)
    raw = caught.value.archive
    assert raw['action_provider_calls'] == raw['policy_calls'] == trainer.policy_calls == 1
    assert raw['action_provider_successes'] == raw['warmup_draws'] == 0
    assert raw['cost']['physical_substeps'] == 0
    assert not trainer.active_episode


def test_completed_collection_also_freezes_independent_stop_evidence():
    collection = api('collection')
    s = api('session').session_class()(fake_environment())
    advance = s.advance_cycle
    def finish(action):
        result = advance(action)
        s.env.events.append({'reason': 'COMPLETE_EVENT'})
        s.env.stop_samples.append({'time_s': .002})
        return SimpleNamespace(**dict(result.__dict__, done=True))
    s.advance_cycle = finish
    raw = collection.collect_episode(s, point(), policy=lambda _: [0.] * 5, max_cycles=2)
    assert raw['evidence']['stop_samples'] == [{'time_s': .002}]
    assert raw['evidence']['environment_events'][-1]['reason'] == 'COMPLETE_EVENT'
    assert raw['cost']['physical_substeps'] == 10


def test_describe_entry_exposes_new_dimensions_without_starting_physics(capsys):
    import json
    from importlib import util, import_module
    name = 'tools.validation.run_five_axis_sac'
    assert util.find_spec(name) is not None, 'Five-axis command entry is missing'
    assert import_module(name).main(['--describe']) == 0
    data = json.loads(capsys.readouterr().out)
    assert data['config']['width'] == 140 and data['config']['action_dim'] == 5
    assert data['physical_execution_enabled'] is False


def test_training_collection_blocks_checkpoints_and_does_not_auto_publish(monkeypatch):
    trainer = api('training').FiveAxisTrainer(api('contract').learning_config())
    s = api('session').session_class()(fake_environment())
    calls = []
    def action(observation, **kwargs):
        with pytest.raises(RuntimeError): trainer.state_dict()
        calls.append(1)
        return np.zeros(5)
    monkeypatch.setattr(trainer, 'action', action)
    with pytest.raises(api('collection').CollectionError):
        trainer.collect(s, point(), max_cycles=2)
    assert len(calls) == 2 and not trainer.active_episode and not len(trainer.replay)
