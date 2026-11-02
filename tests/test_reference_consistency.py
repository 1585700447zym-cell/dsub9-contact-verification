"""Necessary geometry, substep and session checks; no real physics or policy."""
from importlib import import_module, util
from types import SimpleNamespace
import numpy as np
import pytest


def api():
    assert util.find_spec('tools.dynamics.reference_envelope') is not None, 'Reference consistency repair is missing'
    return import_module('tools.dynamics.reference_envelope')


def test_legacy_lead_clip_counterexample_now_satisfies_both_limits():
    desired = np.array([-398., -30.]) * 1e-6
    actual = np.array([-278., -160.]) * 1e-6
    legacy = np.clip(desired, actual-120e-6, actual+120e-6)
    assert np.linalg.norm(desired) < 400e-6 < np.linalg.norm(legacy)
    if util.find_spec('tools.dynamics.reference_envelope') is None:
        result = legacy  # Exposes the existing bug before the repair is present.
    else:
        result = api().constrain_xy(desired, actual, [0., 0.], 400e-6, 120e-6)
    assert np.linalg.norm(result) <= 400e-6 + 1e-12
    assert np.max(abs(result-actual)) <= 120e-6 + 1e-12


def test_feasible_legacy_values_are_unchanged_and_empty_intersection_is_explicit():
    m = api()
    desired, actual = np.array([.0002, -.0001]), np.array([.00019, -.00009])
    np.testing.assert_array_equal(m.constrain_xy(desired, actual, [0., 0.], .0004, .00012), desired)
    for sign in (-1., 1.):
        tangent = m.constrain_xy([sign*.0006, 0.], [sign*.00052, 0.], [0., 0.], .0004, .00012)
        np.testing.assert_allclose(tangent, [sign*.0004, 0.], atol=1e-12, rtol=0.)
        with pytest.raises(m.ReferenceIntersectionEmpty):
            m.constrain_xy([0., 0.], [sign*.00053, 0.], [0., 0.], .0004, .00012)


def test_substep_applies_joint_bounds_before_force_and_before_saved_row(monkeypatch):
    m = api()
    import mujoco
    checks = []
    class Base:
        def __init__(self):
            from tools.dynamics.cartesian import DynamicConfig
            self.config = DynamicConfig(reference_lead_m=.00012)
            self.phase = 'RUNNING'; self.events = []; self.physical_steps = 0
            self.reference = np.array([-.000398, -.000030, 0., 1., 0., 0., 0.])
            self.data = SimpleNamespace(time=0., qpos=np.array([-.000278, -.000160, 0., 1., 0., 0., 0.]),
                qvel=np.zeros(6), xmat=np.eye(3).reshape(1, 9),
                xpos=np.array([[-.000278, -.000160, 0.]]), qfrc_applied=np.zeros(6))
            self.command = np.zeros(6); self.raw_command = np.zeros(6); self.drive = np.zeros(6)
            self.velocity_limits = np.array([.001]*3+[.03]*3)
            self.acceleration_limits = np.array([.005]*3+[.3]*3)
            self.effort_limits = np.array([8.]*3+[.2]*3)
            self.kp = np.ones(6); self.kd = np.ones(6); self.male = 0; self.grasp_local = np.zeros(3)
            self.command_limited_steps = self.reference_limited_steps = self.drive_saturation_steps = 0
        def _state_valid(self): return True
        def _read(self):
            check(self)
            return dict(time_s=self.data.time, phase=self.phase, reference_qpos=self.reference.tolist(),
                        limited_command_world=self.command.tolist(), contact_wrench_G=[0.]*6)
        def observe(self): return self.last_finite
        def _record_peaks(self, row): pass
        def _guard(self, row): pass
        def stop(self, reason):
            self.phase = 'STOPPING'; self.reference = self.data.qpos.copy(); self.command[:] = 0.
            self.events.append(dict(reason=reason, phase=self.phase, time_s=self.data.time))
        def step(self, command): return 'legacy'
        def reset(self): return 'reset'
    class Env(m.ReferenceEnvelopeMixin, Base): pass
    def check(env):
        if env.phase != 'RUNNING':
            return
        assert np.linalg.norm(env.reference[:2]) <= .0004+1e-12
        assert np.max(abs(env.reference[:2]-env.data.qpos[:2])) <= .00012+1e-12
        checks.append(1)
    def integrate(model, q, velocity, dt): q[:3] += np.asarray(velocity)[:3]*dt
    def differentiate(model, output, dt, a, b):
        output[:] = 0.; output[:3] = (b[:3]-a[:3])/dt
    def physical_stub(model, data):
        data.time += .0002; data.qpos[0] -= .00000025; data.qpos[1] += .00000025
    monkeypatch.setattr(mujoco, 'mju_quat2Mat', lambda out, q: out.__setitem__(slice(None), np.eye(3).ravel()))
    monkeypatch.setattr(mujoco, 'mj_integratePos', integrate)
    monkeypatch.setattr(mujoco, 'mj_differentiatePos', differentiate)
    monkeypatch.setattr(mujoco, 'mj_applyFT', lambda *args: check(env))
    monkeypatch.setattr(mujoco, 'mj_step', physical_stub)
    monkeypatch.setattr(mujoco, 'mj_forward', lambda model, data: data.xpos.__setitem__(0, data.qpos[:3]))
    env = Env(); env.model = object()
    env.configure_search_envelope([0., 0.], .0004)
    row = env.step([0.]*6)
    assert len(checks) == 20 and env.physical_steps == 10
    np.testing.assert_array_equal(row['reference_qpos'], env.reference)
    np.testing.assert_array_equal(env.command, np.zeros(6))
    assert env.reference_envelope_corrections > 0
    env.configure_search_envelope(None)
    assert env.step([0.]*6) == 'legacy'
    env.configure_search_envelope([0., 0.], .0004)
    env.reset()
    assert env.search_reference_center is None
    env = Env(); env.model = object(); env.data.qpos[0] = -.0007
    env.configure_search_envelope([0., 0.], .0004)
    env.step([0.]*6)
    assert env.phase == 'STOPPING' and env.reference_failure_pending
    assert env.search_reference_center is None
    assert [event['reason'] for event in env.events] == ['B2_SEARCH_EXHAUSTED']


def session_fixture():
    from dataclasses import replace
    m = api()
    from tests.learning.test_five_axis_session import fake_environment, point
    from tools.learning.consistent_reference import session_class
    env = fake_environment()
    env.config = replace(env.config, reference_lead_m=.00012, reference_lead_rad=.01)
    env.reference_consistency_version = m.VERSION
    env.search_reference_center = None; env.reference_failure_pending = False
    def configure(center, radius=None):
        env.search_reference_center = None if center is None else np.asarray(center).copy()
    env.configure_search_envelope = configure
    env.stop = lambda reason: (setattr(env, 'phase', 'STOPPING'),
        env.events.append(dict(reason=reason, phase='STOPPING', time_s=env.data.time)))
    session = session_class('G1')(env); session.reset(point())
    return session


def test_session_arms_each_search_origin_and_disarms_other_phases():
    s = session_fixture()
    assert s.controller.config.spiral_radius_m == .0004 and s.controller.config.total_action_time_s == 30.
    for origin in ([.00001, .00002, 0.], [.00003, -.00001, 0.]):
        s.controller.phase = 'SEARCH'; s.controller.search_count = 1
        s.controller.search_origin = np.array(origin); s.controller.search_progress_origin_z_m = 0.
        s._cache = None; snap = s.prepare_cycle(); s._command_for_action(snap, np.zeros(5))
        np.testing.assert_array_equal(s.env.search_reference_center, s.initial[:2]+np.asarray(origin)[:2])
        assert s.last_action_log['reference_consistency_version'] == api().VERSION
    s.controller.phase = 'INSERT'; s._cache = None
    s._command_for_action(s.prepare_cycle(), np.zeros(5))
    assert s.env.search_reference_center is None
    assert s.contract['version'].endswith('reference_consistent_v1')


@pytest.mark.parametrize('count', [1, 2])
def test_empty_intersection_uses_existing_recovery_or_budget_end(count):
    s = session_fixture()
    s.controller.phase = 'SEARCH'; s.controller.search_count = count
    s.controller.search_origin = np.zeros(3)
    s.env.reference_failure_pending = True; s.env.stop('B2_SEARCH_EXHAUSTED')
    s._post_task_cycle(s.env.observe())
    assert not s.env.reference_failure_pending
    assert s.env.events[-1]['reason'] == 'B2_SEARCH_EXHAUSTED'
    if count == 1:
        assert s.controller.phase == 'WAIT_RECOVERY' and s.recovery_state == 'WAIT_STOP'
        assert s.reason is None
    else:
        assert s.controller.phase == 'FAILED' and s.reason == 'SEARCH_BUDGET_EXHAUSTED'


def test_upper_prediction_infeasible_is_left_to_the_same_physical_stop_path():
    s = session_fixture()
    s.controller.phase = 'SEARCH'; s.controller.search_count = 1
    s.controller.search_origin = np.zeros(3); s.controller.search_progress_origin_z_m = 0.
    s.env.data.qpos[0] = s.initial[0]+.0006
    s._cache = None
    command = s._command_for_action(s.prepare_cycle(), np.zeros(5))
    assert np.isfinite(command).all() and s.env.phase == 'RUNNING'
    assert s.last_action_log['bounded_prediction_infeasible'] is True
    assert s.last_action_log['predicted_bounded_reference_xy_m'] is None
