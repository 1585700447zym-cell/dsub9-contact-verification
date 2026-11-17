"""Replay the registered frozen policy across every recorded control cycle."""
import numpy as np

from tools.learning.five_axis_contract import permission
from tools.learning.recurrent_collection import CyclePolicy, VERSION


def audit_source(raw, *, actor, policy_mode, checkpoint_id, exploration_seed,
                 deterministic=False, episode_id=None):
    """Validate policy requests and counters. Physical/terminal admissibility has a separate audit."""
    if raw.get('version') != VERSION or raw.get('policy_mode') != policy_mode:
        raise ValueError('Cycle-policy archive version or requested policy_mode differs')
    if episode_id is not None and raw.get('episode_id') != episode_id:
        raise ValueError('Source episode identity differs')
    rows = raw.get('transitions')
    records = raw.get('source_cycles')
    if not isinstance(rows, list) or not rows or not isinstance(records, list) or len(records) != len(rows):
        raise ValueError('One source record per completed transition required')
    if raw.get('error') or not isinstance(raw.get('outcome'), dict):
        raise ValueError('Aborted source archive')
    source = CyclePolicy(policy_mode, actor, checkpoint_id=checkpoint_id, exploration_seed=exploration_seed,
                         deterministic=deterministic)
    source.begin_episode(raw.get('episode_id'))
    if raw.get('policy_source') != source.source:
        raise ValueError('Policy source settings, episode, or actor digest differ')
    active_count = 0
    for cycle, (row, record) in enumerate(zip(rows, records)):
        obs, next_obs = row['observation'], row['next_observation']
        if cycle and not np.array_equal(obs, rows[cycle-1]['next_observation']):
            raise ValueError('Source observation discontinuity')
        if row.get('terminated') is not (cycle == len(rows)-1) or row.get('truncated') is not False:
            raise ValueError('Complete audited terminal tail required')
        enabled = row['action_active']
        if type(enabled) is not bool or row['next_action_active'] is not permission(next_obs):
            raise ValueError('Source transition permission mismatch')
        if row['terminated'] and row['next_action_active']:
            raise ValueError('Final observation must have residual disabled')
        action = source.select_cycle(cycle, obs, enabled)
        if source.records[-1] != record:
            raise ValueError('Recorded cycle differs from independent source replay')
        log = row['action_log']
        if not np.array_equal(action, log['raw_action']):
            raise ValueError('Policy request differs from frozen source')
        if type(log['enabled']) is not bool or (not enabled and log['enabled']):
            raise ValueError('Recorded execution permission mismatch')
        expected = action if log['enabled'] else [0.] * 5
        if not np.array_equal(expected, log['experience_action']) or not np.array_equal(expected, row['action']):
            raise ValueError('Experience action differs from recorded application')
        active_count += int(enabled)
    if (raw.get('source_counts') != source.counts or raw.get('action_provider_calls') != active_count
            or raw.get('action_provider_successes') != active_count):
        raise ValueError('Action source or encoding counters differ')
    source.end_episode()
    return dict(verified=True, audit_scope='cycle_policy_source', policy_mode=policy_mode,
                audit_cycle_inputs=len(rows), audit_actor_head_calls=active_count,
                audit_encoded_cycles=source.counts['encoded_cycles'])
