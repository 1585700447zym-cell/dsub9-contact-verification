"""Offline, truth-only four-section potential; never part of policy observations.

The immutable physical replay keeps its original rewards. A bounded experiment
can replace sampled rewards using the explicit episode/cycle provenance here.
"""
from dataclasses import replace
import numpy as np

VERSION = 'nine_pin_four_section_potential_v1'
SPEC = dict(version=VERSION, depths_m=[0.,.00025,.00025,.00075],
            radii_m=[.000675,.000675,.0006,.0006], clearance_fraction=.1,
            mean_weight=.5, worst_weight=.5, coefficient=1.,
            terminal_potential=0., discount='stored_transition_discount')


def potential(row):
    from tools.model import layered_task as g
    pose = g._pose(row)
    if pose is None:
        raise ValueError('Finite near-vertical pose required by geometry potential')
    position, rotation = pose
    axis = rotation[:,2]
    centers = g._pin_centers @ rotation.T + position
    radii = np.asarray(g._pin_sizes)[:,0]
    if not np.allclose(radii,.0005,rtol=0,atol=1e-15):
        raise ValueError('Reward specification requires 500 um pin radius')
    if not np.allclose([g._LAYERS[0][1],g._LAYERS[0][3],g._LAYERS[1][1]],
                       [.000675,.00025,.0006],rtol=0,atol=1e-15):
        raise ValueError('Reward specification and bound bore geometry differ')
    z = np.asarray(SPEC['depths_m'])
    bore = np.asarray(SPEC['radii_m'])
    points = centers[:,None,:] + ((z[None,:]-centers[:,2,None])/axis[2])[...,None]*axis
    margins = bore[None,:]-np.linalg.norm(points[:,:,:2]-g._holes[:,None,:2],axis=2)-radii[:,None]/axis[2]
    clearance = bore[None,:]-radii[:,None]
    errors = np.max(np.maximum(0.,.1*clearance-margins)/clearance,axis=1)
    squares = errors**2
    return float(1./(1.+.5*np.mean(squares)+.5*np.max(squares)))


def shaping(potentials, discounts, terminated):
    phi=np.asarray(potentials,dtype=np.float64)
    gamma=np.asarray(discounts,dtype=np.float64)
    terminal=np.asarray(terminated,dtype=bool)
    if (phi.shape != (len(gamma)+1,) or terminal.shape != gamma.shape
            or gamma.ndim != 1 or not np.isfinite(phi).all() or not np.isfinite(gamma).all()
            or np.any((phi<0)|(phi>1)) or np.any((gamma<=0)|(gamma>1))):
        raise ValueError('Aligned finite potentials and transition discounts required')
    return gamma*np.where(terminal,0.,phi[1:])-phi[:-1]


def replace_batch_rewards(batch, rewards_by_episode):
    """Map complete-episode rewards to real rows, retaining padding and burn-in."""
    import torch
    rewards=batch.rewards.clone()
    for i,(key,start,prefix) in enumerate(zip(batch.episode_ids,batch.start_cycles,batch.prefix_lengths)):
        indices=torch.flatnonzero(batch.valid_mask[i,:,0]) if hasattr(torch,'flatnonzero') else torch.nonzero(batch.valid_mask[i,:,0]).flatten()
        first=batch.burn_in-prefix
        if not torch.equal(indices,torch.arange(first,first+len(indices))):
            raise ValueError('Expected contiguous valid sequence rows')
        source=np.asarray(rewards_by_episode[key])
        values=source[start-prefix:start-prefix+len(indices)]
        if len(values)!=len(indices) or not np.isfinite(values).all():
            raise ValueError('Reward overlay does not cover the sampled sequence')
        rewards[i,indices,0]=torch.as_tensor(values,dtype=rewards.dtype)
    return replace(batch,rewards=rewards)
