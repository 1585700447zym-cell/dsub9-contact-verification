import numpy as np
from tools.validation.run_contact_candidate_stop import physical_tail_pass,stop_steps
from tools.dynamics.contact_candidate import candidate_environment
from tools.validation.run_contact_cases import ContactCase


def steady():
    return [dict(time_s=float(t),linear_m_s=1e-6,angular_rad_s=1e-4) for t in np.linspace(.9,1.,501)]


def test_tail_requires_every_physical_step_and_full_duration():
    rows=steady()
    assert physical_tail_pass(rows,1.,.0002)
    assert not physical_tail_pass(rows[1:],1.,.0002)
    assert not physical_tail_pass(rows[:-1],1.,.0002)
    assert not physical_tail_pass(rows[:250]+rows[251:],1.,.0002)


def test_single_unstable_or_nonfinite_substep_invalidates_tail():
    for field,value in [('linear_m_s',11e-6),('angular_rad_s',.0011),('linear_m_s',float('nan'))]:
        rows=steady();rows[123][field]=value
        assert not physical_tail_pass(rows,1.,.0002)


def test_stop_instrumentation_does_not_change_candidate_trajectory():
    first=candidate_environment(segments=128);second=candidate_environment(segments=128)
    for env in (first,second):
        env.reset(ContactCase.separated());env.step([0,0,.001,0,0,0]);env.stop()
    with stop_steps(first) as rows:
        result=first.step(np.zeros(6))
    assert result==second.step(np.zeros(6))
    assert len(rows)==10
    assert rows[-1]['linear_m_s']==np.linalg.norm(result['velocity_world'][:3])
