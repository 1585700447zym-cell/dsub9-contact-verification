"""Pure, frozen scope and scheduling contract. No runtime imports."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PROPOSAL = ROOT / 'deliverables/learning_chain/b2_scope_audit_20261008/candidate.json'
PROPOSAL_PIN = '1cf7ada9d0bc105732bae21c657826c32797a1541bb2b05c9279e20c9f9be2ce'


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    def reject_constant(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=reject_constant)


def proposal():
    if sha(PROPOSAL) != PROPOSAL_PIN:
        raise ValueError('Scope proposal changed')
    return read(PROPOSAL)


def validate_candidate(candidate, parent):
    expected = proposal()
    if canonical(candidate) != canonical(expected):
        raise ValueError('Unregistered scope candidate')
    source = ROOT / expected['parent']['configuration']
    if sha(source) != expected['parent']['configuration_sha256'] or canonical(parent) != canonical(read(source)):
        raise ValueError('Parent physical configuration changed')
    return deepcopy(candidate)


def case_kwargs(spec):
    c = proposal()
    permitted = c['cases'] + c['static_cases']
    try:
        same = any(canonical(spec) == canonical(row) for row in permitted)
    except (TypeError, ValueError) as exc:
        raise ValueError('Invalid case fields') from exc
    if not same:
        raise ValueError('Unregistered case or angle unit')
    return dict(name=spec['id'], x_offset_m=spec['x_um'] * 1e-6, y_offset_m=spec['y_um'] * 1e-6,
                roll_rad=math.radians(spec['roll_deg']), pitch_rad=math.radians(spec['pitch_deg']),
                start_origin_z_m=spec['start_origin_z_m'], target_depth_m=spec['target_depth_m'])


def script_action(phase, elapsed_s, enabled, sign):
    if (not isinstance(phase, str) or type(enabled) is not bool or type(sign) is not int or sign not in (-1, 1)
            or type(elapsed_s) not in (float, int) or not math.isfinite(elapsed_s) or elapsed_s < 0):
        raise ValueError('Invalid script inputs')
    if enabled and phase in ('INSERT', 'SEARCH') and .02 <= elapsed_s < .12:
        return [sign * value for value in (.1, -.1, .1, -.1)]
    return [0.] * 4


def attempt_specs(candidate):
    if canonical(candidate) != canonical(proposal()):
        raise ValueError('Unregistered candidate')
    points = {row['id']: row for row in candidate['cases']}
    return ([dict(id='init_' + row['id'], kind='static', case=row) for row in candidate['static_cases']]
            + [dict(row, kind='dynamic', case=points[row['case_id']]) for row in candidate['attempts']])


def next_attempt(entries, candidate):
    specs = attempt_specs(candidate)
    if len(entries) > len(specs):
        raise ValueError('Attempt ceiling exceeded')
    for index, row in enumerate(entries):
        spec = specs[index]
        if row.get('id') != spec['id'] or row.get('kind') != spec['kind']:
            raise ValueError('Skipped, duplicated or reordered attempt')
        if row.get('status') != 'finished' or row.get('audit_passed') is not True:
            return None
        if spec['kind'] == 'dynamic':
            outcome = row.get('outcome', {})
            if (outcome.get('simulation_valid') is not True or outcome.get('physical_stopped') is not True
                    or outcome.get('task_outcome') not in ('FULL_SUCCESS', 'TASK_FAILURE')):
                return None
    return deepcopy(specs[len(entries)]) if len(entries) < len(specs) else None
