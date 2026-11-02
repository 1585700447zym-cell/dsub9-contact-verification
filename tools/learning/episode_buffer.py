"""Episode quarantine. A list sink is the initial atomic in-memory adapter.

No SAC replay implementation is connected here. Future replay adapters must
provide all-or-none batch publication, not repeated per-transition insertion.
"""
from copy import deepcopy
import json
import math
import numpy as np
from .action import normalized_action


def _archive(value):
    if isinstance(value, np.ndarray):
        return _archive(value.tolist())
    if isinstance(value, np.generic):
        return _archive(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return {'nonfinite': str(value)}, False
    if isinstance(value, dict):
        items = {k: _archive(v) for k, v in value.items()}
        return ({k: pair[0] for k, pair in items.items()},
                'nonfinite' not in value and all(pair[1] for pair in items.values()))
    if isinstance(value, (list, tuple)):
        items = [_archive(v) for v in value]
        return [pair[0] for pair in items], all(pair[1] for pair in items)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value, True
    return {'unserializable_type': type(value).__name__}, False


def _validate_schema(row):
    required = {'observation', 'next_observation', 'action', 'reward',
                'terminated', 'truncated', 'action_active'}
    if not isinstance(row, dict) or not required.issubset(row):
        raise ValueError('Missing required numeric transition fields')
    for name in ('terminated', 'truncated', 'action_active'):
        if not isinstance(row[name], (bool, np.bool_)):
            raise ValueError(f'{name} must be boolean')
    if row['terminated'] and row['truncated']:
        raise ValueError('terminated and truncated are mutually exclusive')
    vectors = [np.asarray(row[name]) for name in ('observation', 'next_observation')]
    if any(v.ndim != 1 or not v.size or v.dtype.kind not in 'biuf' for v in vectors):
        raise ValueError('Observations must be numeric vectors, not tagged archives or strings')
    if vectors[0].shape != vectors[1].shape:
        raise ValueError('Observation shapes must match')
    if isinstance(row['reward'], (bool, np.bool_)) or not isinstance(row['reward'], (int, float, np.integer, np.floating)):
        raise ValueError('Reward must be numeric')


def _safe_error_archive(row):
    try:
        archived, _ = _archive(row)
        json.dumps(archived, allow_nan=False)
        return archived
    except Exception as exc:
        # Do not let a failing diagnostic undo the already latched invalidity.
        return {'unarchivable_record_type': type(row).__name__, 'archive_error': type(exc).__name__}


class EpisodeBuffer:
    def __init__(self):
        self._pending = []
        self._finite = True
        self._closed = False
        self._boundary = False
        self.quarantined = []

    def stage(self, transition):
        if self._closed:
            raise RuntimeError('Episode already finalized')
        if self._boundary:
            raise RuntimeError('No transitions after episode boundary; audit safety tail separately')
        prior_finite = self._finite
        self._finite = False  # Fail closed before validation, conversion or diagnostic archival.
        try:
            _validate_schema(transition)
            action = normalized_action(transition['action'])
            row = deepcopy(transition)
            row['action'] = (action if row['action_active'] else np.zeros(4)).tolist()
            archived, finite = _archive(row)
            json.dumps(archived, allow_nan=False)
        except Exception as exc:
            self._pending.append(_safe_error_archive(transition))
            raise ValueError('Invalid transition; entire episode quarantined') from exc
        self._finite = prior_finite and finite
        self._pending.append(archived)
        self._boundary = bool(row['terminated'] or row['truncated'])

    def finalize(self, *, valid_for_learning, sink):
        if self._closed:
            raise RuntimeError('Episode already finalized')
        if type(sink) is not list:
            raise TypeError('Initial adapter requires a list sink; no partial callback writes')
        rows = deepcopy(self._pending)
        accepted = bool(valid_for_learning and self._finite)
        if accepted:
            sink.extend(rows)
        else:
            self.quarantined = rows
        self._closed = True
        self._pending.clear()
        return dict(committed=len(rows) if accepted else 0, discarded=0 if accepted else len(rows))


def entropy_adjusted_bootstrap(*, q_next, log_probability, alpha, next_action_active):
    return np.asarray(q_next) - alpha * np.where(next_action_active, log_probability, 0.)
