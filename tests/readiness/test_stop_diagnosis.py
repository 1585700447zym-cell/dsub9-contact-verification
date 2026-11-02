import importlib
from dataclasses import replace
import numpy as np
import pytest
from tools.dynamics.cartesian import CartesianEnvironment
from tools.validation.run_contact_cases import ContactCase


def api():
    spec=importlib.util.find_spec('tools.validation.diagnose_stop_reliability')
    assert spec is not None, 'Complete-state stop diagnosis is not implemented'
    return importlib.import_module(spec.name)


@pytest.mark.parametrize('contact',[False,True])
def test_cloned_state_reproduces_contact_and_free_continuation(contact):
    m=api();env=CartesianEnvironment(segments=128)
    case=replace(ContactCase.x_offset(100e-6),start_origin_z_m=0) if contact else ContactCase.separated()
    env.reset(case,allow_initial_contact=contact)
    for _ in range(3):env.step(np.zeros(6))
    env.stop();clone=m.clone_environment(env)
    assert not np.shares_memory(clone.data.qpos,env.data.qpos)
    for _ in range(10):assert env.step(np.zeros(6))==clone.step(np.zeros(6))
    clone.model.opt.timestep=.0001
    assert env.model.opt.timestep==.0002


def test_instrumentation_records_integration_force_without_changing_motion():
    m=api();env=CartesianEnvironment(segments=128);env.reset(ContactCase.separated());clone=m.clone_environment(env)
    with m.integration_capture(clone) as samples:
        row=clone.step([0,0,.001,0,0,0])
    assert row==env.step([0,0,.001,0,0,0])
    assert len(samples)==10
    assert samples[-1]['integrated_to_s']==pytest.approx(.002)
    assert max(np.linalg.norm(r['translation_balance_residual_N']) for r in samples)<1e-12
