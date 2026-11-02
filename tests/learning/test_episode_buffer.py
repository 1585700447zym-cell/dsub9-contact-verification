import numpy as np
import pytest


def transition():
    return dict(observation=[0, 1], next_observation=[2, 3], action=[1, -1, 0, 0],
                reward=-.001, terminated=False, truncated=False, action_active=True)


def test_late_invalidity_discards_whole_episode():
    from tools.learning.episode_buffer import EpisodeBuffer
    buffer, sink = EpisodeBuffer(), []
    buffer.stage(transition())
    assert sink == []
    result = buffer.finalize(valid_for_learning=False, sink=sink)
    assert sink == [] and result['discarded'] == 1
    assert buffer.quarantined[0]['next_observation'] == [2, 3]


def test_valid_failure_commits_copies_once():
    from tools.learning.episode_buffer import EpisodeBuffer
    buffer, sink = EpisodeBuffer(), []
    row = transition()
    row.update(terminated=True, reward=-10)
    buffer.stage(row)
    row['action'][0] = 999
    result = buffer.finalize(valid_for_learning=True, sink=sink)
    assert result['committed'] == 1 and sink[0]['action'][0] == 1
    with pytest.raises(RuntimeError):
        buffer.finalize(valid_for_learning=True, sink=sink)
    assert len(sink) == 1


def test_nonfinite_transition_poisoning_cannot_be_overridden_by_final_flag():
    from tools.learning.episode_buffer import EpisodeBuffer
    buffer, sink = EpisodeBuffer(), []
    buffer.stage(transition())
    row = transition()
    row['reward'] = float('nan')
    buffer.stage(row)
    result = buffer.finalize(valid_for_learning=True, sink=sink)
    assert sink == [] and result['discarded'] == 2
    assert buffer.quarantined[1]['reward'] == {'nonfinite': 'nan'}


def test_external_truncation_keeps_real_bootstrap_and_excludes_safety_tail():
    from tools.learning.episode_buffer import EpisodeBuffer
    buffer, sink = EpisodeBuffer(), []
    row = transition()
    row.update(truncated=True)
    buffer.stage(row)
    buffer.finalize(valid_for_learning=True, sink=sink)
    assert sink[0]['next_observation'] == [2, 3]
    with pytest.raises(RuntimeError):
        buffer.stage(transition())


def test_mutually_exclusive_termination_and_action_dimension():
    from tools.learning.episode_buffer import EpisodeBuffer
    row = transition()
    row.update(terminated=True, truncated=True)
    with pytest.raises(ValueError):
        EpisodeBuffer().stage(row)
    row.update(truncated=False, action=[0] * 6)
    with pytest.raises(ValueError):
        EpisodeBuffer().stage(row)


def test_no_entropy_value_in_inactive_next_state():
    from tools.learning.episode_buffer import entropy_adjusted_bootstrap
    np.testing.assert_array_equal(entropy_adjusted_bootstrap(
        q_next=np.array([2., 2.]), log_probability=np.array([-10., -10.]),
        alpha=.2, next_action_active=np.array([False, True])), [2, 4])


def test_invalid_action_poisoning_cannot_publish_earlier_samples():
    from tools.learning.episode_buffer import EpisodeBuffer
    buffer, sink = EpisodeBuffer(), []
    buffer.stage(transition())
    row = transition()
    row.update(action=[float('inf'), 0, 0, 0], action_active=False)
    with pytest.raises(ValueError):
        buffer.stage(row)
    assert buffer.finalize(valid_for_learning=True, sink=sink)['discarded'] == 2
    assert sink == []
    assert buffer.quarantined[1]['action'][0] == {'nonfinite': 'inf'}


def test_no_tail_transition_can_be_staged_after_external_cut_before_audit():
    from tools.learning.episode_buffer import EpisodeBuffer
    buffer = EpisodeBuffer()
    row = transition()
    row['truncated'] = True
    buffer.stage(row)
    with pytest.raises(RuntimeError, match='boundary'):
        buffer.stage(transition())


@pytest.mark.parametrize('change', [
    {'reward': 'NaN'}, {'observation': [{'nonfinite': 'nan'}, 1]},
    {'terminated': 'false'}, {'truncated': 1}, {'action_active': 'yes'},
    {'next_observation': [1]},
])
def test_malformed_numeric_transition_is_rejected_and_poisons_episode(change):
    from tools.learning.episode_buffer import EpisodeBuffer
    buffer, sink = EpisodeBuffer(), []
    buffer.stage(transition())
    row = transition()
    row.update(change)
    with pytest.raises(ValueError):
        buffer.stage(row)
    buffer.finalize(valid_for_learning=True, sink=sink)
    assert sink == []


def test_missing_reward_does_not_enter_sink():
    from tools.learning.episode_buffer import EpisodeBuffer
    buffer, sink = EpisodeBuffer(), []
    row = transition()
    del row['reward']
    with pytest.raises(ValueError):
        buffer.stage(row)
    buffer.finalize(valid_for_learning=True, sink=sink)
    assert sink == []


@pytest.mark.parametrize('change', [
    {'action': [float('inf'), 0, 0, 0], 'metadata': object()},
    {'terminated': True, 'truncated': True},
])
def test_rejected_transition_poison_is_latched_before_error_archival(change):
    from tools.learning.episode_buffer import EpisodeBuffer
    buffer, sink = EpisodeBuffer(), []
    buffer.stage(transition())
    row = transition()
    row.update(change)
    with pytest.raises((ValueError, TypeError)):
        buffer.stage(row)
    assert buffer.finalize(valid_for_learning=True, sink=sink)['discarded'] == 2
    assert sink == []
