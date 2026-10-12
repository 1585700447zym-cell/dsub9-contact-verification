"""Restore guards check every group without mutating caller-owned state."""
from copy import deepcopy
import pytest
from tools.learning.learning_rates import optimizer_learning_rates, validate_optimizer_learning_rates


def saved():
    return {role: dict(state={}, param_groups=[dict(lr=rate, params=[0]), dict(lr=rate, params=[1])])
            for role,rate in (('actor', 3e-5), ('critic', 3e-4), ('temperature', 3e-4))}


@pytest.mark.parametrize('bad', [0., -1., True, float('inf'), float('nan'), None, '0.0003', 10**400])
def test_invalid_public_rate_cannot_initialize_any_optimizer(bad):
    with pytest.raises(ValueError, match='learning rate'):
        optimizer_learning_rates(dict(learning_rate=bad, actor_learning_rate=3e-5))


def test_every_group_must_match_and_guard_does_not_repair_saved_rates():
    s = saved()
    s['actor']['param_groups'][1]['lr'] = 3e-4
    before = deepcopy(s)
    with pytest.raises(ValueError):
        validate_optimizer_learning_rates(s, dict(learning_rate=3e-4, actor_learning_rate=3e-5))
    assert s == before


@pytest.mark.parametrize('damage', ['missing', 'empty', 'nonlist', 'nondict', 'missing_lr', 'bool_lr'])
def test_incomplete_or_non_numeric_saved_groups_are_rejected(damage):
    s = saved()
    if damage == 'missing': del s['actor']
    if damage == 'empty': s['actor']['param_groups'] = []
    if damage == 'nonlist': s['actor']['param_groups'] = {}
    if damage == 'nondict': s['actor']['param_groups'] = [None]
    if damage == 'missing_lr': del s['actor']['param_groups'][0]['lr']
    if damage == 'bool_lr': s['actor']['param_groups'][0]['lr'] = True
    with pytest.raises(ValueError):
        validate_optimizer_learning_rates(s, dict(learning_rate=3e-4, actor_learning_rate=3e-5))


def test_matching_multiple_groups_are_accepted_without_state_changes():
    s = saved(); before = deepcopy(s)
    validate_optimizer_learning_rates(s, dict(learning_rate=3e-4, actor_learning_rate=3e-5))
    assert s == before
