"""The probe may alter only the extra XY search term, within old budgets."""
import importlib
import math
import numpy as np
import pytest
from tools.control.search_exit_v2 import SearchRecoveryV2
from tools.control.search_recovery import Observation


def candidate():
    name = 'tools.control.search_probe'
    assert importlib.util.find_spec(name) is not None, 'XY probe candidate has not been implemented'
    return importlib.import_module(name).SearchPauseProbe()


def prepare(c, recovered=True):
    c.phase = 'SEARCH'; c.search_count = 2 if recovered else 1
    c.recovered_search = recovered; c.blocked_z_m = .00025
    c.phase_start = 10.; c.search_origin = np.array([0., 0., -.00002]); c.theta = 3.
    c.admittance.velocity[:] = [1e-5, -2e-5, .001, -.002]
    return c


def obs(t=10.3, advance=.000100001, force=True):
    return Observation(t, (1e-5, -1e-5, -.00002+advance),
                       (.001, -.002, -.006, 1e-6, -2e-6, 0.) if force else (0.,)*6)


def test_pause_retains_admittance_z_rotation_and_consumes_phase_budget():
    p, v = prepare(candidate()), prepare(SearchRecoveryV2())
    b = v.command(obs(), .002); a = p.command(obs(), .002)
    np.testing.assert_array_equal(a[2:], b[2:])
    np.testing.assert_array_equal(p.admittance.velocity, v.admittance.velocity)
    np.testing.assert_array_equal(p.admittance.offset, v.admittance.offset)
    np.testing.assert_array_equal(a[:2], np.clip(p.admittance.velocity[:2], -.0003, .0003))
    assert np.linalg.norm(a[:2]-b[:2]) > 1e-6
    assert p.theta == v.theta > 3. and p.phase_start == 10.
    np.testing.assert_array_equal(p.search_origin, v.search_origin)
    assert p.probe_events[0]['time_s'] == 10.3


@pytest.mark.parametrize('recovered,advance', [(False,.00005),(True,.000099)])
def test_first_search_and_pretrigger_are_identical(recovered, advance):
    p, v = prepare(candidate(), recovered), prepare(SearchRecoveryV2(), recovered)
    for i in range(20):
        o = obs(10.+i*.002, advance)
        np.testing.assert_array_equal(p.command(o,.002), v.command(o,.002))
    assert p.probe_events == [] and p.probe_trace == []


def test_resume_blends_only_extra_xy_then_returns_exactly_to_v2():
    p, v = prepare(candidate()), prepare(SearchRecoveryV2())
    for t, gain in [(10.3,0.), (10.8,0.), (11.3,0.), (11.35,.5), (11.4,1.),(11.5,1.)]:
        a=p.command(obs(t),.002); b=v.command(obs(t),.002)
        np.testing.assert_array_equal(a[2:],b[2:])
        base=p.admittance.velocity[:2]
        # These fixtures avoid component saturation, so interpolation is observable.
        np.testing.assert_allclose(a[:2],base+gain*(b[:2]-base),atol=1e-14,rtol=0)
        assert p.theta == v.theta and p.phase_start == v.phase_start
        if gain==1.:np.testing.assert_array_equal(a,b)
    assert len([e for e in p.probe_events if e['event']=='XY_PROBE_START'])==1


@pytest.mark.parametrize('budget', ['radius','time','excursion'])
def test_existing_budget_and_excursion_checks_take_precedence(budget):
    p, v = prepare(candidate()), prepare(SearchRecoveryV2())
    p.command(obs(),.002);v.command(obs(),.002)
    o=obs(10.4)
    if budget=='radius':p.theta=v.theta=p.config.spiral_radius_m/(p.config.spiral_pitch_m/(2*math.pi))
    if budget=='time':p.phase_start=v.phase_start=2.
    if budget=='excursion':o=Observation(10.4,(.000201,0.,.00008),obs().wrench_M)
    np.testing.assert_array_equal(p.command(o,.002),v.command(o,.002))
    assert p.phase==v.phase=='FAILED' and p.reason==v.reason


def test_v2_qualified_exit_is_not_delayed_by_pause():
    p,v=prepare(candidate()),prepare(SearchRecoveryV2())
    p.command(obs(force=False),.002);v.command(obs(force=False),.002)
    for i in range(28):
        o=Observation(10.4+i*.002,(0.,0.,.000351+i*1e-6),(0.,)*6)
        a=p.command(o,.002);b=v.command(o,.002)
        if v.phase=='INSERT':
            assert p.phase=='INSERT';np.testing.assert_array_equal(a,b);break
    else:pytest.fail('Original sustained exit must be reached')
    assert p.exit_evidence==v.exit_evidence


@pytest.mark.parametrize('field,value',[('pause_s',0.),('pause_s',float('nan')),('resume_s',-1.),('resume_s',float('inf'))])
def test_invalid_probe_parameters_rejected(field,value):
    candidate()
    module=importlib.import_module('tools.control.search_probe')
    with pytest.raises(ValueError):module.ProbeConfig(**{field:value})
