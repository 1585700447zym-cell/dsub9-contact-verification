"""Read-only feasibility probe. Not an admission, replay writer or training entry.

Standard library only; no environment, inference, tensor, restore or optimizer calls.
Historical failure flags and archives are never changed.
"""
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path

D = Path(__file__).resolve().parent
ROOT = D.parents[2]
CURRENT = ROOT / 'deliverables/learning_chain/b2_fixed_rotation_cycle_20260928'
OLD = ROOT / 'deliverables/learning_chain/b2_repaired_cycle_v2_20260928'
PIN = 'd6ac62ef7e0114ab5c042b666ed69b29ad11df9663f6c5a1ff92c5a728ec71e2'
inputs = {}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    data = path.read_bytes()
    inputs[path.relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)


def finite(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(finite(v) for v in value.values())
    if isinstance(value, list):
        return all(finite(v) for v in value)
    return value is None or isinstance(value, (int, str, bool))


def tail_ok(samples, end):
    dt = .0002
    tail = [r for r in samples if r['time_s'] >= end - .1 - dt / 2]
    return bool(tail and tail[0]['time_s'] <= end - .1 + dt / 2
        and abs(tail[-1]['time_s'] - end) <= dt / 2
        and all(0 < b['time_s'] - a['time_s'] <= dt * 1.01 for a, b in zip(tail, tail[1:]))
        and all(0 <= r['linear_m_s'] <= 1e-5 and 0 <= r['angular_rad_s'] <= .001 for r in tail))


def stopped(raw):
    start = None
    phase = None
    for event in raw['events']:
        current = event.get('phase')
        if current is None:
            continue
        if current == 'STOPPING':
            if phase != current:
                start = event['time_s']
        else:
            start = None
        phase = current
    samples = raw['stop_samples']
    if start is None or not finite(samples) or raw['audit_end_time_s'] < start + 2 - 1e-9:
        return False
    return tail_ok([r for r in samples if r['time_s'] <= start + 2 + .0001], start + 2) and tail_ok(samples, raw['audit_end_time_s'])


def features(raw):
    rows = raw['transitions']
    facts = raw['guard_facts']
    case = raw['case']
    structure = bool(rows)
    previous = None
    for i, row in enumerate(rows):
        flags = [row[k] for k in ('terminated', 'truncated', 'action_active', 'next_action_active')]
        structure &= all(type(v) is bool for v in flags)
        structure &= row['terminated'] == (i == len(rows) - 1) and not row['truncated']
        structure &= all(len(row[k]) == 120 and all(-10 <= x <= 10 for x in row[k]) for k in ('observation', 'next_observation'))
        structure &= len(row['action']) == 4 and all(-1 <= x <= 1 for x in row['action'])
        structure &= row['action_active'] or row['action'] == [0.] * 4
        structure &= row['dt'] > 0 and math.isclose(row['discount'], math.exp(-row['dt']/10), abs_tol=1e-12, rel_tol=0)
        terms = row['reward_terms']
        structure &= math.isclose(row['reward'], terms['total'], abs_tol=1e-12, rel_tol=0)
        structure &= math.isclose(terms['total'], sum(terms[k] for k in ('progress', 'time', 'force', 'torque', 'terminal')), abs_tol=1e-12, rel_tol=0)
        if previous is not None:
            structure &= previous['next_observation'] == row['observation'] and previous['next_action_active'] == row['action_active']
        previous = row
    category = raw['outcome']['task_outcome']
    expected_terminal = {'FULL_SUCCESS': 10., 'TASK_FAILURE': -2., 'CONTACT_GUARD': -10.}[category]
    terminals = [(i, row['reward_terms']['terminal']) for i, row in enumerate(rows) if row['reward_terms']['terminal']]
    force_rows = [i for i, row in enumerate(rows) if any('FORCE_LIMIT' in event['reason'] for event in row['events'])]
    after_guard = True
    if force_rows:
        index = force_rows[0]
        after_guard = not rows[index]['next_action_active'] and all(not r['action_active'] and r['action'] == [0.] * 4 for r in rows[index + 1:])
    f = dict(finite=finite(raw), simulation_valid=facts['simulation_valid'], stopped=stopped(raw),
        structure_valid=bool(structure), no_runtime_fault=raw['fault'] is None or raw['fault'] == {'contact_publication_rejected': True},
        invalid_reasons=facts['invalid_reasons'], motion_reasons=facts['motion_reasons'], contact_reasons=facts['contact_reasons'],
        full_substep_coverage=facts['checked_substeps'] == len(rows) * 10,
        action_mask_after_guard=after_guard,
        event_consistent=not facts['contact_reasons'] or (facts['contact_reasons'] == ['FORCE_LIMIT'] and bool(force_rows)),
        terminal_valid=terminals == [(len(rows) - 1, expected_terminal)],
        registered_case=(case['x_offset_m'], case['y_offset_m']) in ((.0001, 0.), (-.0001, 0.), (0., .0001), (0., -.0001))
            and case['roll_rad'] == case['pitch_rad'] == 0. and case['start_origin_z_m'] == -.004 and case['target_depth_m'] == .004,
        policy_frozen=raw['optimizer_steps_start'] == raw['optimizer_steps'],
        category=category,
        peak_force_N=max(.025 * math.sqrt(max(0., -r['reward_terms']['force'] / (.2 * r['dt']))) for r in rows))
    return f


def proposed_decision(f):
    """A diagnostic predicate only. It creates no training authority."""
    required = ('finite', 'simulation_valid', 'stopped', 'structure_valid', 'no_runtime_fault',
                'full_substep_coverage', 'action_mask_after_guard', 'event_consistent', 'terminal_valid',
                'registered_case', 'policy_frozen')
    if any(f[k] is not True for k in required) or f['invalid_reasons'] or f['motion_reasons']:
        return 'reject'
    if not f['contact_reasons']:
        return 'existing_eligible' if f['category'] in ('FULL_SUCCESS', 'TASK_FAILURE') else 'reject'
    if f['contact_reasons'] == ['FORCE_LIMIT'] and f['category'] == 'CONTACT_GUARD':
        return 'candidate_force_failure'
    return 'reject'


def main():
    out = D / 'assessment.json'
    assert not out.exists(), 'Evidence already exists; do not overwrite.'
    qualification = load(CURRENT / 'admission.json')
    assert sha(CURRENT / 'admission.json') == PIN
    for table in ('source_sha256', 'evidence_sha256'):
        for name, pin in qualification[table].items():
            assert sha(ROOT / name) == pin, name
    old_manifest = load(CURRENT / 'previous_files.json')
    for name, pin in old_manifest.items():
        assert sha(ROOT / name) == pin, name
    # Bind the actual classifiers, reward and all affected pipeline boundaries.
    paths = ['guarded_environment.py', 'outcome.py', 'reward.py', 'contact_contract.py', 'contact_execution.py',
             'admitted_collection.py', 'bounded_contact.py', 'audited_replay.py', 'boundary_targets.py',
             'bounded_checkpoint.py', 'bounded_cycle.py', 'sac_checkpoint.py']
    for name in paths:
        path = ROOT / 'tools/learning' / name
        inputs[path.relative_to(ROOT).as_posix()] = sha(path)
    for name in ('docs/stage_b/训练合同_v3.md', 'docs/stage_b/工程范围与姿态参数冻结记录_v1.md',
                 'docs/stage_b/四点接触固定转动配置_v1.json'):
        inputs[name] = sha(ROOT / name)
    selected = [('current_success', CURRENT / 'run/training_episodes/train_00'),
                ('current_task_failure', CURRENT / 'run/training_episodes/train_01'),
                ('current_force_failure', CURRENT / 'run/training_episodes/train_04'),
                ('previous_penetration_failure', OLD / 'run/training_episodes/train_09')]
    results = []
    force_raw = None
    for label, folder in selected:
        raw = load(folder / 'episode.json.gz')
        receipt = load(folder / 'status.json')
        assert sha(folder / 'episode.json.gz') == receipt['archive_sha256']
        f = features(raw)
        row = dict(label=label, features=f, hypothetical_decision=proposed_decision(f),
                   actual_published=receipt['committed'], actual_discarded=receipt['discarded'],
                   actual_valid_for_learning=receipt['valid_for_learning'], transitions=len(raw['transitions']))
        results.append(row)
        if label == 'current_force_failure':
            force_raw, force_features = raw, f
    assert [r['hypothetical_decision'] for r in results] == ['existing_eligible', 'existing_eligible', 'candidate_force_failure', 'reject']
    rows = force_raw['transitions']
    boundary = max(i for i, row in enumerate(rows) if row['action_active'])
    discounted_return = 0.
    for row in reversed(rows[boundary:]):
        discounted_return = row['reward'] + row['discount'] * discounted_return
    terminal_contribution = -10 * math.prod(row['discount'] for row in rows[boundary:-1])
    counterexamples = []
    mutations = {key: False for key in ('finite', 'simulation_valid', 'stopped', 'structure_valid',
        'no_runtime_fault', 'full_substep_coverage', 'action_mask_after_guard', 'event_consistent',
        'terminal_valid', 'registered_case', 'policy_frozen')}
    mutations.update(invalid_reasons=['INVALID_PENETRATION'], motion_reasons=['ROTATION_LIMIT'],
        contact_reasons=['FORCE_LIMIT', 'PENETRATION_LIMIT'], category='FULL_SUCCESS')
    for key, value in mutations.items():
        f = copy.deepcopy(force_features)
        f[key] = value
        assert proposed_decision(f) == 'reject', key
        counterexamples.append(key)
    for reason in ('PENETRATION_LIMIT', 'TORQUE_LIMIT'):
        f = copy.deepcopy(force_features)
        f['contact_reasons'] = [reason]
        assert proposed_decision(f) == 'reject'
        counterexamples.append(reason)
    for name, pin in inputs.items():
        assert sha(ROOT / name) == pin, name
    result = dict(verdict='GO_scoped_rule_design_and_implementation_validation_only',
        training_admitted=False, historical_data_republished=False,
        additional_physics=0, additional_policy_inferences=0, additional_state_restorations=0, additional_optimizer_calls=0,
        qualification_sources_verified=len(qualification['source_sha256']), historical_files_verified=len(old_manifest),
        archived_cases=results, diagnostic_rejection_cases=counterexamples,
        force_tail=dict(last_active_index=boundary, terminal_index=len(rows)-1,
            discounted_logged_return=discounted_return, terminal_minus10_contribution=terminal_contribution,
            existing_boundary_index_rejects_this_episode=True, values_are_offline_arithmetic_not_Q_predictions=True),
        limitations=['No general physical trust domain or real-force calibration established.',
            'Candidate eligibility is not actual admission; no historical flag is changed.',
            'Future FORCE-only failures need the same complete audits under new qualification.',
            'No inference that this explains the first force violation or guarantees performance.'],
        inputs_sha256=inputs, probe_sha256=sha(Path(__file__).resolve()))
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k not in ('archived_cases', 'inputs_sha256')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
