"""Force-unit regressions without starting physical steps or loading actors."""
import math
import xml.etree.ElementTree as ET

import numpy as np
import pytest


def test_newton_reward_uses_new_scales_before_squaring_and_keeps_terminal_once():
    from tools.learning.newton_profile import NewtonReward
    reward = NewtonReward(.005)
    terms = reward.advance(advance_m=.001, dt=.1, force_N=2., torque_G_Nm=.02)
    assert terms['progress'] == pytest.approx(1.)
    assert terms['time'] == pytest.approx(-.01)
    assert terms['force'] == pytest.approx(-.0032)
    assert terms['torque'] == pytest.approx(-.0008)
    assert reward.finalize('FULL_SUCCESS') == 10.
    with pytest.raises(RuntimeError):
        reward.finalize('FULL_SUCCESS')


def test_force_observation_is_normalized_from_raw_not_old_clipped_values():
    from tools.learning.newton_profile import normalize_wrench_history
    history = [2., -5., 1., .02, -.1, .05]*4
    actual = normalize_wrench_history(history)
    assert actual.tolist() == pytest.approx([.4, -1., .2, .2, -1., .5]*4)
    with pytest.raises(ValueError):
        normalize_wrench_history([math.nan]*24)


def test_newton_force_response_preserves_bounded_velocity_and_old_config_rejects_it():
    from tools.learning.newton_profile import make_controller
    from tools.control.search_recovery import SearchConfig
    controller = make_controller()
    actual = controller.admittance.command([1., 0., 0., 0., 0., 0.], .002)
    assert actual[0] == pytest.approx(.0000906346234610091)
    for _ in range(100):
        actual = controller.admittance.command([5., 0., 0., .1, 0., 0.], .002)
    assert abs(actual[0]) <= .0005 + 1e-15
    assert abs(actual[3]) <= .02 + 1e-15
    with pytest.raises(ValueError):
        SearchConfig(search_force_N=2.)


def test_model_adaptation_changes_contact_response_without_changing_geometry():
    from tools.learning.newton_profile import build_model_xml
    from tools.model.clearance_task import build_task_xml
    old, new = ET.fromstring(build_task_xml()), ET.fromstring(build_model_xml())
    assert new.find('.//inertial').attrib == old.find('.//inertial').attrib
    for element in new.iter('geom'):
        if 'solref' in element.attrib:
            assert element.get('solref') == '0.001 1'
            element.set('solref', '0.02 1')
    new.set('model', old.get('model'))
    assert ET.tostring(new) == ET.tostring(old)


def test_profile_rejects_working_force_at_guard_and_unstable_time_constant():
    from dataclasses import replace
    from tools.learning.newton_profile import NewtonProfile
    profile = NewtonProfile()
    with pytest.raises(ValueError):
        replace(profile, search_force_N=5.)
    with pytest.raises(ValueError):
        replace(profile, contact_time_constant_s=.0001)
    assert profile.metadata()['hardware_qualified'] is False


def diagnostics():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).parents[2]/'deliverables/learning_chain/b2_newton_force_profile_20261016/diagnostics.py'
    spec = importlib.util.spec_from_file_location('newton_diagnostics_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_traditional_selection_prefers_completion_over_shorter_failures():
    module = diagnostics()
    rows = [dict(variant=v, outcome=o, scored_time_s=t) for v,o,t in [
        ('original','FULL_SUCCESS',20.), ('original','TASK_FAILURE',26.),
        ('exit_50um','FULL_SUCCESS',22.), ('exit_50um','FULL_SUCCESS',23.),
        ('coverage_180um','TASK_FAILURE',26.), ('coverage_180um','TASK_FAILURE',26.)]]
    assert module.choose_variant(rows) == 'exit_50um'


def test_step_convergence_rejects_changed_force_or_penetration():
    module = diagnostics()
    a = dict(peaks=dict(force_N=2., penetration_m=10e-6), preflight_passed=True)
    b = dict(peaks=dict(force_N=2.1, penetration_m=12e-6), preflight_passed=True)
    assert module.convergence_pass(a,b)
    b['peaks']['force_N'] = 2.3
    assert not module.convergence_pass(a,b)
    b['peaks'].update(force_N=2., penetration_m=16e-6)
    assert not module.convergence_pass(a,b)
