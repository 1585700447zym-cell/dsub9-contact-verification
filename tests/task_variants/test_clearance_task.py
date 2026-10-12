import hashlib
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
import pytest


@pytest.fixture(scope='module', autouse=True)
def qualified_runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()


def row(x=0., pitch=0.):
    return dict(position_m=[x, 0., 0.], quaternion_wxyz=[math.cos(pitch/2), 0., math.sin(pitch/2), 0.],
                velocity_world=[0.]*6, contact_wrench_G=[0.]*6, penetration_m=0.)


def test_task_geometry_has_wider_collision_and_no_stale_female_visual():
    from tools.model.clearance_task import build_task_xml
    tree = ET.fromstring(build_task_xml())
    vertices = np.fromstring(tree.find('.//mesh[@name="convex256_main_000"]').get('vertex'), sep=' ').reshape(-1, 3)
    assert min(vertices[:, 0]) == pytest.approx(.0006, abs=1e-15)
    assert tree.find('.//geom[@name="female_visual"]') is None
    pins = tree.findall('.//geom[@class="pin_collision"]')
    assert len(pins) == 9
    assert all(g.get('size').split()[0] == '0.0005' for g in pins)
    assert len(tree.findall('.//geom[@class="hole_convex_collision"]')) == 4608


def test_new_and_old_precision_coexist_without_global_mutation():
    from tools.model.clearance_task import finish_criteria
    from tools.validation.run_b1_baseline import FINISH, geometric_finish
    assert not geometric_finish(row(70e-6))
    assert geometric_finish(row(70e-6), criteria=finish_criteria())
    assert not geometric_finish(row(81e-6), criteria=finish_criteria())
    assert FINISH['xy_tolerance_m'] == 50e-6


def test_pin_fit_rejects_tilt_despite_acceptable_body_xy_and_angle():
    from tools.model.clearance_task import pin_fit, pin_clearance_m
    assert pin_fit(row(80e-6))
    assert pin_clearance_m(row(80e-6)) == pytest.approx(20e-6)
    assert not pin_fit(row(80e-6, math.radians(.5)))
    assert not pin_fit(row(float('nan')))


def test_legacy_default_xml_remains_byte_identical():
    from tools.model.contact_development import build_xml
    assert hashlib.sha256(build_xml(256).encode()).hexdigest() == '2a2ca6cb6e1e3c6dfc567e4a84c087cc0a050d1961b0ca5db83e21363fad9d25'


def test_environment_and_session_bind_new_task_before_reset():
    from tools.model.clearance_task import build_task_xml, finish_criteria, pin_fit
    from tools.learning.guarded_environment import LearningEnvironment, GuardCandidateConfig
    from tools.learning.guarded_session import CandidateEpisodeSession
    guards = GuardCandidateConfig(math.radians(2.5), math.radians(.5))
    env = LearningEnvironment(guard_config=guards, model_xml=build_task_xml())
    session = CandidateEpisodeSession(environment=env, finish_criteria=finish_criteria(), geometry_checker=pin_fit)
    assert session.finish_criteria['xy_tolerance_m'] == 80e-6
    assert session.geometry_checker(row(70e-6))
    import mujoco
    gid = mujoco.mj_name2id(env.model, mujoco.mjtObj.mjOBJ_GEOM, 'hole_convex256_01_main_000')
    assert gid >= 0
    assert env.model.opt.ccd_tolerance == pytest.approx(1e-12)


def test_success_hold_rejects_pin_interference_and_uses_instance_threshold():
    from types import SimpleNamespace
    from tools.model.clearance_task import finish_criteria, pin_fit
    from tools.learning.session import EpisodeSession
    from tools.validation.run_b1_baseline import FINISH
    def run(criteria, state):
        from tools.dynamics.cartesian import DynamicConfig
        s = object.__new__(EpisodeSession)
        s.finish_criteria = criteria
        s.geometry_checker = pin_fit
        s.env = SimpleNamespace(phase='STOPPING', events=[], config=DynamicConfig(), peaks=dict(force_N=0., torque_G_Nm=0., penetration_m=0.))
        s.controller = SimpleNamespace(config=SimpleNamespace(settle_time_s=.5))
        s.reason='TARGET_PLANE_REACHED';s.stop_time=0.;s.hold_start=0.;s.guard_latched=False;s.task_finished=False
        state=dict(state,time_s=.11)
        s._post_task_cycle(state)
        return s
    assert run(finish_criteria(),row(70e-6)).reason == 'GEOMETRIC_SUCCESS'
    assert run(FINISH.copy(),row(70e-6)).reason != 'GEOMETRIC_SUCCESS'
    assert run(finish_criteria(),row(80e-6,math.radians(.5))).hold_start is None
