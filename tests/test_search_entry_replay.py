"""Audited event/geometry anchors and opt-in continuous-window sampling."""
from copy import deepcopy

import numpy as np
import pytest
import torch

from tests.test_recurrent_replay import episode, publish
from tools.learning.five_axis_contract import field_slices
from tools.learning.observation import POLICY_PHASES
from tools.learning.recurrent_replay import RecurrentReplay
from tools.learning.search_entry_replay import (
    build_focus_labels, sample_focus_sequences, validate_focus_labels,
)


@pytest.fixture(scope='module', autouse=True)
def geometry_runtime():
    # Select installed bindings/model files only; no MjModel, MjData or step runs.
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()


def archive(name='a', *, event=True):
    phases = ['SEARCH', 'SEARCH', 'INSERT', 'INSERT', 'WAIT_RECOVERY']
    rows = episode(1, [True, True, True, True, False])
    fields = field_slices()
    frames = [deepcopy(row['observation']) for row in rows] + [deepcopy(rows[-1]['next_observation'])]
    for frame, phase in zip(frames, phases + ['WAIT_RECOVERY']):
        frame[fields['policy_phase']] = [float(i == POLICY_PHASES.index(phase)) for i in range(5)]
    for i, row in enumerate(rows):
        row.update(observation=frames[i], next_observation=frames[i+1],
                   action_log=dict(enabled=row['action_active'], composition_inputs=dict(phase=phases[i])))
    z = [-.0041, -.0041, -.00399, -.00398, -.00397, -.00397]
    trace = [dict(time_s=i*.002, position_m=[.01, .01, value],
                  quaternion_wxyz=[1., 0., 0., 0.], phase='RUNNING') for i, value in enumerate(z)]
    events = [dict(time_s=0., phase='SEARCH', reason='LOW_LOAD_SEARCH', progress_origin_z_m=0.)]
    if event:
        events.append(dict(time_s=.004, phase='INSERT', reason='SEARCH_ADVANCED',
                           progress_origin_z_m=0., observed_z_m=.00011, net_advance_m=.00011))
    return dict(episode_id=name, transitions=rows, trace=trace, evidence=dict(controller_events=events))


def test_event_anchor_requires_real_phase_change_and_progress_beyond_old_peak():
    raw = archive()
    labels = build_focus_labels(raw)
    validate_focus_labels(labels, episode_id='a', transition_count=5)
    assert [(a['cycle'], a['kind']) for a in labels['anchors']] == [(2, 'search_advanced')]
    for change in ('retreat', 'wrong_phase', 'fake_progress', 'wrong_time'):
        bad = deepcopy(raw)
        event = bad['evidence']['controller_events'][-1]
        if change == 'retreat':
            # Re-advancing after a retract is not an advance beyond the prior peak.
            bad['trace'][0]['position_m'][2] = -.0038
        elif change == 'wrong_phase':
            bad['transitions'][1]['action_log']['composition_inputs']['phase'] = 'WAIT_RECOVERY'
        elif change == 'fake_progress':
            event['net_advance_m'] = .0003
        else:
            event['time_s'] += .001
        with pytest.raises(ValueError):
            build_focus_labels(bad)


def test_geometry_anchor_checks_real_nine_pin_fit_and_excludes_recovery():
    raw = archive(event=False)
    # Aligned actual pose has all nine finite cylinders overlapping the main layer.
    for i, frame in enumerate(raw['trace']):
        frame['position_m'] = [0., 0., -.005 if i == 0 else -.0035]
    labels = build_focus_labels(raw)
    assert any(a['kind'] == 'main_fit' for a in labels['anchors'])
    assert all(a['cycle'] < 4 for a in labels['anchors'])
    bad = deepcopy(raw)
    for row in bad['transitions']:
        row['action_active'] = False
        row['action_log']['enabled'] = False
    assert build_focus_labels(bad)['anchors'] == []
    outside = deepcopy(raw)
    for frame in outside['trace']:
        frame['position_m'][0] = .001
    assert build_focus_labels(outside)['anchors'] == []


def test_main_fit_during_backward_search_or_physical_retraction_is_not_entry():
    raw = archive(event=False)
    for i, frame in enumerate(raw['trace']):
        frame['position_m'] = [0., 0., -.003 - i*.00001]
    assert build_focus_labels(raw)['anchors'] == []
    for frame in raw['trace']:
        frame['position_m'] = [0., 0., -.003]
        frame['phase'] = 'RETRACT'
    assert build_focus_labels(raw)['anchors'] == []


def test_focus_preserves_uniform_row_continuity_and_places_anchor_in_learning_suffix():
    raw = archive()
    labels = build_focus_labels(raw)
    replay = RecurrentReplay(capacity=20)
    publish(replay, 'a', raw['transitions'])
    publish(replay, 'b', archive('b', event=False)['transitions'])
    labels_b = build_focus_labels(archive('b', event=False))
    ordinary_rng = np.random.default_rng(74)
    expected = replay.sample_sequences(1, 3, 2, ordinary_rng)
    rng = np.random.default_rng(74)
    batch, report = sample_focus_sequences(replay, labels_by_episode={'a': labels, 'b': labels_b},
                                          burn_in=3, learn_steps=2, rng=rng)
    batch.validate()
    assert batch.episode_ids[0] == expected.episode_ids[0]
    assert batch.start_cycles[0] == expected.start_cycles[0]
    torch.testing.assert_close(batch.observations[0], expected.observations[0])
    assert report['uniform_sequences'] == report['focused_sequences'] == 1
    assert report['focus_fallback'] == 0 and report['focus_kind'] == 'search_advanced'
    assert batch.episode_ids[1] == 'a'
    assert batch.start_cycles[1] <= 2 < batch.start_cycles[1] + 2
    assert report['episode_ids'] == list(batch.episode_ids)
    assert report['start_cycles'] == list(batch.start_cycles)
    saved = deepcopy(rng.bit_generator.state)
    result1 = sample_focus_sequences(replay, labels_by_episode={'a': labels, 'b': labels_b},
                                    burn_in=3, learn_steps=2, rng=rng)
    rng.bit_generator.state = saved
    result2 = sample_focus_sequences(replay, labels_by_episode={'a': labels, 'b': labels_b},
                                    burn_in=3, learn_steps=2, rng=rng)
    assert result1[1] == result2[1]
    torch.testing.assert_close(result1[0].observations, result2[0].observations)


def test_empty_focus_falls_back_and_corrupt_or_missing_labels_are_rejected():
    raw = archive(event=False)
    labels = build_focus_labels(raw)
    replay = RecurrentReplay(capacity=20)
    publish(replay, 'a', raw['transitions'])
    batch, report = sample_focus_sequences(replay, labels_by_episode={'a': labels},
                                          burn_in=2, learn_steps=3, rng=np.random.default_rng(2))
    batch.validate()
    assert report['uniform_sequences'] == 2 and report['focused_sequences'] == 0
    assert report['focus_fallback'] == 1 and report['anchor_cycle'] is None
    with pytest.raises(ValueError):
        sample_focus_sequences(replay, labels_by_episode={}, burn_in=2, learn_steps=3,
                               rng=np.random.default_rng(2))
    forged = build_focus_labels(archive())
    forged['anchors'][0]['cycle'] = 4
    with pytest.raises(ValueError):
        sample_focus_sequences(replay, labels_by_episode={'a': forged}, burn_in=2, learn_steps=3,
                               rng=np.random.default_rng(2))
    forged = build_focus_labels(archive())
    forged['anchors'].append(deepcopy(forged['anchors'][0]))
    with pytest.raises(ValueError):
        validate_focus_labels(forged, episode_id='a', transition_count=5)


def test_explicit_windows_match_uniform_windows_and_legacy_state_is_unchanged():
    replay = RecurrentReplay(capacity=20)
    publish(replay, 'a', archive()['transitions'])
    before = replay.state_dict()
    sampled = replay.sample_sequences(2, 3, 4, np.random.default_rng(17))
    selected = replay.sample_sequences_from_starts(sampled.episode_ids, sampled.start_cycles, 3, 4)
    for key in vars(sampled):
        a, b = getattr(sampled, key), getattr(selected, key)
        assert torch.equal(a, b) if isinstance(a, torch.Tensor) else a == b
    assert replay.state_dict()['version'] == before['version']
    assert set(replay.state_dict()) == set(before)
    with pytest.raises(ValueError):
        replay.sample_sequences_from_starts(('a',), (5,), 3, 4)
