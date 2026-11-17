"""Opt-in event/geometry focus over continuous, externally audited GRU replay.

Labels are referee-only sampling metadata, never observations, rewards or an
admission grant. The publication owner must build them AFTER its whole-archive
audit and bind the complete labels and their digest into training provenance.
"""
from bisect import bisect_left
from dataclasses import fields
import math

import numpy as np
import torch

from .five_axis_contract import field_slices
from .recurrent_replay import SequenceReplayBatch

LABEL_VERSION = 'search_entry_focus_labels_v1'
SAMPLING_VERSION = 'search_entry_event_half_v1'
KINDS = ('search_advanced', 'main_fit')
_PHASE = field_slices()['policy_phase']
_PHYSICAL = field_slices()['physical_phase']
_PERIOD = .002


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def _phase(row):
    return row['action_log']['composition_inputs']['phase']


def validate_focus_labels(labels, *, episode_id, transition_count):
    """Validate immutable label schema; the archive audit authenticates its source."""
    if (not isinstance(labels, dict) or set(labels) != {'version', 'episode_id', 'transitions', 'anchors'}
            or labels['version'] != LABEL_VERSION or labels['episode_id'] != episode_id
            or not isinstance(episode_id, str) or not episode_id
            or type(transition_count) is not int or transition_count <= 0
            or type(labels['transitions']) is not int or labels['transitions'] != transition_count
            or not isinstance(labels['anchors'], list)):
        raise ValueError('Complete matching focus labels required')
    previous = None
    for anchor in labels['anchors']:
        if (not isinstance(anchor, dict) or set(anchor) != {'cycle', 'kind', 'evidence'}
                or type(anchor['cycle']) is not int or not 0 <= anchor['cycle'] < transition_count
                or anchor['kind'] not in KINDS or not isinstance(anchor['evidence'], dict)):
            raise ValueError('Invalid focus anchor')
        cycle, kind, proof = anchor['cycle'], anchor['kind'], anchor['evidence']
        identity = (cycle, kind)
        if previous is not None and identity <= previous:
            raise ValueError('Focus anchors must be sorted and unique')
        previous = identity
        if kind == 'search_advanced':
            expected = {'time_s', 'search_start_cycle', 'progress_origin_z_m', 'observed_z_m', 'net_advance_m'}
            if (set(proof) != expected or type(proof['search_start_cycle']) is not int
                    or not 0 <= proof['search_start_cycle'] < cycle
                    or not all(_finite(proof[k]) for k in expected - {'search_start_cycle'})
                    or abs(proof['time_s'] - cycle*_PERIOD) > 1e-8
                    or proof['net_advance_m'] < .0001 - 1e-12
                    or abs(proof['observed_z_m'] - proof['progress_origin_z_m'] - proof['net_advance_m']) > 1e-9):
                raise ValueError('Invalid verified-search-advance evidence')
        else:
            expected = {'time_s', 'frame_cycle', 'clearance_lower_bound_m', 'referee', 'geometry_tolerance_m'}
            if (set(proof) != expected or type(proof['frame_cycle']) is not int
                    or proof['frame_cycle'] != cycle+1
                    or proof['referee'] != 'clipped_cylinder_convex256_nano100_v3'
                    or proof['geometry_tolerance_m'] != 1e-7
                    or not _finite(proof['time_s']) or abs(proof['time_s']-(cycle+1)*_PERIOD) > 1e-8
                    or not _finite(proof['clearance_lower_bound_m']) or proof['clearance_lower_bound_m'] < -1e-7):
                raise ValueError('Invalid confirmed-main-fit evidence')


def _main_fit_lower_bound(frame, *, verify=True):
    """Conservative cheap screening, then the actual finite-cylinder referee.

    Missed marginal fits remain in uniform replay. A positive label requires all
    nine actual cylinders to overlap the main slab and pass the bound referee;
    neither an origin-Z threshold nor positive travel alone qualifies.
    """
    from tools.model import layered_task as geometry
    pose = geometry._pose(frame)
    if pose is None:
        return None
    position, rotation = pose
    centers = geometry._pin_centers @ rotation.T + position
    axis = rotation[:, 2]
    radius, half = geometry._pin_sizes[:, 0], geometry._pin_sizes[:, 1]
    extent = half*axis[2] + radius*math.sqrt(max(0., 1.-axis[2]**2))
    _, _, zlo, zhi = geometry._LAYERS[1]
    if not np.all((centers[:, 2]+extent > zlo+1e-12) & (centers[:, 2]-extent < zhi-1e-12)):
        return None
    ends = centers[:, None, :2] + np.array([-1., 1.])[None, :, None]*half[:, None, None]*axis[:2]
    clearance = float(np.min(geometry.BORE_RADIUS_M - radius
                            - np.linalg.norm(ends-geometry._holes[:, None, :2], axis=2).max(axis=1)))
    if clearance < -geometry.GEOMETRY_TOLERANCE_M:
        return None
    return clearance if not verify or geometry.layered_pin_fit(frame) else None


def build_focus_labels(raw, *, search_exit_advance_m=.0001):
    """Derive labels from already independently audited raw trace/event evidence."""
    if search_exit_advance_m != .0001:
        raise ValueError('The registered 100 um net-progress gate is required')
    rows, trace = raw['transitions'], raw['trace']
    if not rows or len(trace) != len(rows)+1:
        raise ValueError('Complete trace/transition correspondence required')
    times = [frame['time_s'] for frame in trace]
    if any(not _finite(t) or abs(t-i*_PERIOD) > 1e-8 for i, t in enumerate(times)):
        raise ValueError('Registered contiguous 2 ms trace required')
    positions = np.asarray([frame['position_m'] for frame in trace], dtype=float)
    if positions.shape != (len(trace), 3) or not np.isfinite(positions).all():
        raise ValueError('Actual finite XYZ trace required')
    z = positions[:, 2] - positions[0, 2]
    peaks = np.maximum.accumulate(z)
    events = raw['evidence']['controller_events']
    anchors = []
    latest_search = None
    for event in events:
        reason = event.get('reason')
        if reason not in ('LOW_LOAD_SEARCH', 'SEARCH_ADVANCED'):
            continue
        time = event.get('time_s')
        if not _finite(time):
            raise ValueError('Finite event time required')
        cycle = bisect_left(times, time-1e-9)
        if cycle >= len(rows) or abs(times[cycle]-time) > 1e-8:
            raise ValueError('Event must align with an executed control cycle')
        if reason == 'LOW_LOAD_SEARCH':
            latest_search = cycle
            continue
        if (latest_search is None or latest_search >= cycle
                or event.get('phase') != 'INSERT' or _phase(rows[cycle-1]) != 'SEARCH'
                or _phase(rows[cycle]) != 'INSERT'
                or not rows[cycle-1]['action_active'] or not rows[cycle]['action_active']
                or trace[cycle]['phase'] != 'RUNNING'):
            raise ValueError('SEARCH_ADVANCED must be a real active SEARCH-to-INSERT transition')
        origin = float(peaks[latest_search])
        observed = float(z[cycle])
        net = observed-origin
        if (net < search_exit_advance_m-1e-12
                or any(not _finite(event.get(k)) for k in ('progress_origin_z_m', 'observed_z_m', 'net_advance_m'))
                or abs(event['progress_origin_z_m']-origin) > 1e-9
                or abs(event['observed_z_m']-observed) > 1e-9
                or abs(event['net_advance_m']-net) > 1e-9):
            raise ValueError('Search progress must exceed the pre-recovery historical depth peak')
        anchors.append(dict(cycle=cycle, kind='search_advanced', evidence=dict(
            time_s=float(times[cycle]), search_start_cycle=latest_search,
            progress_origin_z_m=origin, observed_z_m=observed, net_advance_m=net)))
    # Only entry into a confirmed fit contributes a geometry anchor, not every
    # subsequent deep-insertion sample. Uniform replay still covers those rows.
    fitted = False
    for cycle, row in enumerate(rows):
        eligible = (row['action_active'] is True and row['action_log']['enabled'] is True
                    and _phase(row) in ('SEARCH', 'INSERT')
                    and positions[cycle+1, 2] >= positions[cycle, 2] - 1e-12
                    and trace[cycle]['phase'] == trace[cycle+1]['phase'] == 'RUNNING')
        clearance = _main_fit_lower_bound(trace[cycle+1], verify=not fitted) if eligible else None
        if clearance is not None and not fitted:
            anchors.append(dict(cycle=cycle, kind='main_fit', evidence=dict(
                time_s=float(times[cycle+1]), frame_cycle=cycle+1, clearance_lower_bound_m=clearance,
                referee='clipped_cylinder_convex256_nano100_v3', geometry_tolerance_m=1e-7)))
        fitted = clearance is not None
    anchors.sort(key=lambda a: (a['cycle'], a['kind']))
    labels = dict(version=LABEL_VERSION, episode_id=raw['episode_id'], transitions=len(rows), anchors=anchors)
    validate_focus_labels(labels, episode_id=raw['episode_id'], transition_count=len(rows))
    return labels


def sample_focus_sequences(replay, *, labels_by_episode, burn_in, learn_steps, rng):
    """Return one uniform and one anchored sequence plus auditable selection data.

    Focus kinds are equiprobable when both exist; anchors within the chosen kind
    are uniform. A uniformly jittered learning start always includes its anchor
    in the learn suffix. Real burn-in, inactive recovery history and stop-tail
    semantics remain unchanged. No TD priority or importance weights are added.
    """
    if (not isinstance(labels_by_episode, dict) or not isinstance(rng, np.random.Generator)
            or type(burn_in) is not int or burn_in < 0 or type(learn_steps) is not int or learn_steps <= 0):
        raise ValueError('Explicit focus labels, lengths and NumPy RNG required')
    state = replay._state
    if not set(replay.episode_ids).issubset(labels_by_episode) or not set(labels_by_episode).issubset(state.seen):
        raise ValueError('Focus labels must cover exactly known admitted episode identities')
    pools = {kind: [] for kind in KINDS}
    for episode_id, arrays in state.episodes:
        labels = labels_by_episode[episode_id]
        validate_focus_labels(labels, episode_id=episode_id, transition_count=len(arrays['rewards']))
        for anchor in labels['anchors']:
            cycle, kind = anchor['cycle'], anchor['kind']
            phases = arrays['frames'][:, _PHASE].argmax(axis=1)
            if (not arrays['action_active'][cycle, 0] or phases[cycle] not in (0, 2)
                    or arrays['frames'][cycle, _PHYSICAL].argmax() != 0
                    or (kind == 'search_advanced' and (cycle == 0 or phases[cycle] != 0
                        or phases[cycle-1] != 2 or not arrays['action_active'][cycle-1, 0]))):
                raise ValueError('Focus anchor cannot identify an inactive/recovery or mismatched stage row')
            pools[kind].append((episode_id, cycle))
    ordinary = replay.sample_sequences(1, burn_in, learn_steps, rng)
    available = [kind for kind in KINDS if pools[kind]]
    if available:
        kind = available[int(rng.integers(len(available)))]
        pool = pools[kind]
        episode_id, cycle = pool[int(rng.integers(len(pool)))]
        start = int(rng.integers(max(0, cycle-learn_steps+1), cycle+1))
        focused = replay.sample_sequences_from_starts((episode_id,), (start,), burn_in, learn_steps)
    else:
        kind = episode_id = cycle = None
        focused = replay.sample_sequences(1, burn_in, learn_steps, rng)
    values = {}
    for field in fields(SequenceReplayBatch):
        a, b = getattr(ordinary, field.name), getattr(focused, field.name)
        values[field.name] = torch.cat((a, b), dim=0) if isinstance(a, torch.Tensor) else a if field.name == 'burn_in' else a+b
    batch = SequenceReplayBatch(**values)
    report = dict(version=SAMPLING_VERSION, focused_sequences=int(bool(available)),
                  uniform_sequences=1+int(not available), focus_fallback=int(not available), focus_kind=kind,
                  episode_ids=list(batch.episode_ids), start_cycles=list(batch.start_cycles),
                  anchor_episode_id=episode_id, anchor_cycle=cycle)
    return batch, report
