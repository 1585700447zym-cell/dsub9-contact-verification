from copy import deepcopy
import importlib
import json
from pathlib import Path

import numpy as np
import pytest
import torch


def module():
    try:
        return importlib.import_module('tools.learning.actor_lr_origin')
    except ModuleNotFoundError as exc:
        pytest.fail('Origin reconstruction implementation missing: ' + str(exc))


def state():
    return dict(version='actor_lr_origin_v1', updater=dict(
        policy={'actor.weight': torch.tensor([1., 2.])},
        actor=dict(state={}, param_groups=[dict(lr=3e-4, params=[0])]),
        critic=dict(state={}, param_groups=[dict(lr=3e-4, params=[0])]),
        temperature=dict(state={}, param_groups=[dict(lr=3e-4, params=[0])]),
        alpha=torch.tensor(-6.), rng=torch.get_rng_state().clone(),
        counts=dict(actor=0, critic=0, temperature=0, target=0)),
        history=[], update_attempts=0, sampler_count=4,
        budget=dict(total=8, completed=0, receipts={}),
        replay=dict(episodes=[['train_00', {'actions': torch.ones((2,4))}]]),
        rng=dict(replay=generator(2).bit_generator.state, boundary=generator(3).bit_generator.state))


def generator(stream):
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence([2026092716, stream])))


def test_branch_forks_only_change_actor_rate_and_identity_and_are_isolated():
    m = module()
    source = state()
    before = deepcopy(source)
    a = m.fork_origin(source, 'A', 'a'*64)
    b = m.fork_origin(source, 'B', 'a'*64)
    assert a['updater']['actor']['param_groups'][0]['lr'] == 3e-4
    assert b['updater']['actor']['param_groups'][0]['lr'] == 3e-5
    assert b['updater']['critic']['param_groups'][0]['lr'] == b['updater']['temperature']['param_groups'][0]['lr'] == 3e-4
    from tools.learning.sac_checkpoint import _same
    aa, bb = deepcopy(a), deepcopy(b)
    for value in (aa, bb):
        value.pop('comparison_binding')
        value['updater']['actor']['param_groups'][0]['lr'] = 3e-4
    assert _same(aa, bb) and _same(source, before)
    b['updater']['policy']['actor.weight'][0] = -99
    b['replay']['episodes'][0][1]['actions'][0,0] = -99
    assert a['updater']['policy']['actor.weight'][0] == source['updater']['policy']['actor.weight'][0] == 1
    assert a['replay']['episodes'][0][1]['actions'][0,0] == source['replay']['episodes'][0][1]['actions'][0,0] == 1


@pytest.mark.parametrize('field', ['actor', 'critic', 'temperature', 'target'])
def test_nonzero_counts_cannot_be_relabelled_as_origin(field):
    source = state()
    source['updater']['counts'][field] = 500
    with pytest.raises(ValueError, match='zero'):
        module().fork_origin(source, 'B', 'a'*64)


@pytest.mark.parametrize('role', ['actor', 'critic', 'temperature'])
def test_nonempty_adam_state_rejected_as_origin(role):
    source = state()
    source['updater'][role]['state'][0] = dict(step=torch.tensor(1.))
    with pytest.raises(ValueError, match='zero'):
        module().fork_origin(source, 'B', 'a'*64)


@pytest.mark.parametrize('value', [-1, True, 1, 500])
def test_nonzero_or_malformed_update_attempts_rejected(value):
    source = state()
    source['update_attempts'] = value
    with pytest.raises(ValueError, match='zero'):
        module().fork_origin(source, 'B', 'a'*64)


def test_draw_plan_matches_both_rng_streams_without_mutating_source():
    m = module()
    streams = dict(replay=generator(2).bit_generator.state, boundary=generator(3).bit_generator.state)
    before = deepcopy(streams)
    plan = m.draw_plan([2, 3, 4, 5], [1, 2, 2, 4], streams, batches=500)
    r, b = generator(2), generator(3)
    for row in plan['batches']:
        assert row['actor_flat_indices'] == r.integers(0, 14, size=256).tolist()
        assert row['boundary_episode_indices'] == b.integers(0, 4, size=16).tolist()
        assert len(row['critic_indices']) == 256
        for key, index in row['critic_indices'][-16:]:
            assert key == 'train_%02d' % row['boundary_episode_indices'][row['critic_indices'][-16:].index([key,index])]
            assert index == [1,2,2,4][int(key[-2:])]
    assert plan['final_rng'] == dict(replay=r.bit_generator.state, boundary=b.bit_generator.state)
    assert streams == before


@pytest.mark.parametrize('lengths,bounds,count', [([1,2], [0,1], 500), ([2,3,4,5], [2,2,2,2], 500),
    ([2,3,4,5], [1,None,2,4], 500), ([2,3,4,True], [1,2,2,0], 500), ([2,3,4,5], [1,2,2,4], 501)])
def test_draw_plan_refuses_unregistered_lengths_boundaries_or_budget(lengths, bounds, count):
    with pytest.raises(ValueError):
        module().draw_plan(lengths, bounds, dict(replay=generator(2).bit_generator.state,
            boundary=generator(3).bit_generator.state), batches=count)


def metadata(i=0):
    from tools.learning.bounded_contact import BalancedSampler, SEED
    sampler = BalancedSampler()
    for _ in range(i+1):
        case = sampler.next_case()
    raw = dict(episode_id='train_%02d' % i, case=case, seed=SEED, qualification_sha256='a'*64,
        optimizer_steps=0, optimizer_steps_start=0, policy_sha256='b'*64,
        sampling_mode='uniform_warmup', audit_end_time_s=.004, transitions=[{}, {}],
        outcome=dict(simulation_valid=True, physical_stopped=True, valid_for_learning=True, task_outcome='TASK_FAILURE'))
    receipt = {k:v for k,v in raw.items() if k not in ('outcome', 'transitions')}
    receipt.update(raw['outcome'])
    receipt.update(steps=2, committed=2, discarded=0, evicted=0, status='published', guard_clear=True,
        learning_eligibility=dict(version='force_only_v1', kind='guard_clear'))
    return raw, receipt


def test_warmup_metadata_accepts_matching_registered_zero_update_receipt():
    raw, receipt = metadata()
    module().validate_warmup_metadata(raw, receipt, 0, 'a'*64, 'b'*64)


@pytest.mark.parametrize('field,value', [('optimizer_steps',500), ('optimizer_steps_start',1),
    ('sampling_mode','sac_policy'), ('qualification_sha256','c'*64), ('policy_sha256','c'*64),
    ('seed',0), ('episode_id','train_04')])
def test_warmup_metadata_rejects_relabelled_or_wrong_origin(field, value):
    raw, receipt = metadata()
    raw[field] = receipt[field] = value
    with pytest.raises(ValueError):
        module().validate_warmup_metadata(raw, receipt, 0, 'a'*64, 'b'*64)


def test_warmup_receipt_mismatch_rejected_even_if_raw_is_valid():
    raw, receipt = metadata()
    receipt['committed'] = 1
    with pytest.raises(ValueError):
        module().validate_warmup_metadata(raw, receipt, 0, 'a'*64, 'b'*64)


def test_checkpoint_pin_failure_precedes_deserialization(tmp_path, monkeypatch):
    path = tmp_path / 'checkpoint'
    path.mkdir()
    (path / 'manifest.json').write_text(json.dumps(dict(version='bounded_checkpoint_manifest_v2',state_sha256='a'*64)))
    (path / 'state.pt').write_bytes(b'not a checkpoint')
    monkeypatch.setattr(torch, 'load', lambda *a, **k: pytest.fail('Deserialization must not occur'))
    with pytest.raises(ValueError, match='pin'):
        module().read_pinned_state(path, 'a'*64)
