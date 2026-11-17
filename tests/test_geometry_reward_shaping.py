import math
import numpy as np
import pytest


@pytest.fixture(scope='module',autouse=True)
def selected_runtime():
    # Geometry-only tests share the existing suite's binding selection. They do
    # not create or step a model; the experiment separately pins the mesh repair.
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()


def reward_module():
    from tools.learning import geometry_reward_shaping
    return geometry_reward_shaping


def pose(x=0., y=0., angle=0., axis=2, z=-.004):
    q = [math.cos(angle/2), 0., 0., 0.]
    q[axis+1] = math.sin(angle/2)
    return dict(position_m=[x,y,z], quaternion_wxyz=q)


def test_geometry_prefers_aligned_and_detects_all_rotation_axes():
    m = reward_module()
    assert m.potential(pose()) == pytest.approx(1.)
    assert m.potential(pose(x=.0003)) < m.potential(pose(x=.0002)) < 1.
    assert m.potential(pose(y=-.0003)) < m.potential(pose(y=-.0002)) < 1.
    for axis in range(3):
        assert m.potential(pose(angle=.06,axis=axis)) < 1.
    assert m.potential(pose(z=-.003)) == m.potential(pose())


def test_terminal_discounted_telescoping_and_nonterminal_window():
    m = reward_module()
    phi = np.array([.2,.6,.4,.8])
    discounts = np.exp(-np.array([.002,.004,.01])/10)
    terminal = np.array([False,False,True])
    delta = m.shaping(phi, discounts, terminal)
    weights = np.r_[1.,np.cumprod(discounts[:-1])]
    assert float(weights@delta) == pytest.approx(-phi[0],abs=1e-12)
    assert m.shaping(phi[:3],discounts[:2],terminal[:2])[-1] == pytest.approx(discounts[1]*phi[2]-phi[1])


def test_batch_reward_mapping_preserves_padding_and_source():
    from types import SimpleNamespace
    from dataclasses import dataclass
    import torch
    m = reward_module()
    @dataclass
    class Batch:
        rewards: object
        valid_mask: object
        episode_ids: tuple
        start_cycles: tuple
        prefix_lengths: tuple
        burn_in: int
    original = torch.zeros((2,5,1))
    mask = torch.tensor([[0,1,1,1,1],[1,1,1,0,0]],dtype=torch.bool)[...,None]
    b=Batch(original,mask,('a','b'),(1,3),(1,2),2)
    r=m.replace_batch_rewards(b,{'a':np.arange(4.),'b':np.arange(4.)+10})
    assert r.rewards[:,:,0].tolist()==[[0,0,1,2,3],[11,12,13,0,0]]
    assert torch.equal(original,torch.zeros_like(original))
    assert r.valid_mask is b.valid_mask


def test_nonfinite_or_out_of_domain_rejected():
    m=reward_module()
    with pytest.raises(ValueError): m.potential(pose(angle=math.pi,axis=0))
    with pytest.raises(ValueError): m.shaping([.2,float('nan')],[.99],[True])


def test_supplement_accepts_unexercised_search_but_checks_other_yaw():
    import importlib.util
    from pathlib import Path
    path=Path(__file__).resolve().parents[1]/'deliverables/learning_chain/reward_shaping_yaw025_minimal_20261112/run_experiment.py'
    spec=importlib.util.spec_from_file_location('screening',path)
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    raw=dict(force_recovery_protocol={'search_authority':dict(search_xy_residual_m_s=.00075,search_xy_acceleration_m_s2=.020)},
             trace=[{}, {'yaw_admittance':{'updates':1,'velocity_rad_s':.001}}],
             transitions=[{'action_log':{'composition_inputs':{'phase':'INSERT','base_command':[0,0,0,0,0,.001]}}}])
    proof=runner.supplement(raw)
    assert proof['search_authority_rows']==0
    assert proof['yaw']['nonzero_search_rows']==0
    raw['transitions'][0]['action_log']['composition_inputs']['base_command'][5]=0
    with pytest.raises(ValueError,match='Passive yaw output differs'):
        runner.supplement(raw)
    counts=runner.cost_totals([dict(reset_attempted=1,native_steps=10),dict(reset_attempted=None,native_steps=None)],496)
    assert counts['stage_initializations'] is None
    assert counts['native_steps'] is None
    assert counts['known_initializations_lower_bound']==1
    assert counts['unknown_cost_attempts']==1
