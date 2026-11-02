"""Offline v4 development metrics. No simulator, optimizer or training admission.

Records are adjudicated attempts, not raw traces. Their caller must bind source
archives and independently establish the outcome and stop facts. A common key
identifies identical task/physics/evaluator/base-controller settings, not a method.
"""
import hashlib
import json
import math
from copy import deepcopy
from statistics import mean


HORIZON_S = 26.0  # 25 s action window + 1 s adjudication; physical tail is separate.
OUTCOMES = {'FULL_SUCCESS', 'TASK_FAILURE', 'CONTACT_GUARD', 'MOTION_VIOLATION',
            'INVALID_SIMULATION', 'STOP_NOT_QUALIFIED'}
LOAD_FIELDS = ('peak_force_N', 'peak_torque_Nm', 'sampled_force_integral_N_s')


def comparison_key(common):
    """Hash a JSON common contract; reject non-finite configuration numbers."""
    return hashlib.sha256(json.dumps(common, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def build_common_contract(config, *, canonical_model_sha256, evaluator_sha256):
    """Bind the frozen task and executable dependencies, including validation code.

    Conservatively retain the original execution input set except its mutable
    closeout plan. Runtime proofs and the new evaluator are explicitly bound.
    This may reject an irrelevant old-tool change; it must not silently permit
    a changed recovery or stop adjudicator in a purported paired comparison.
    """
    for digest in (canonical_model_sha256, evaluator_sha256):
        if not isinstance(digest, str) or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError('SHA256 digest required')
    fields=('task_id','geometry_referee','success_mode','precision_secondary','finish_criteria',
            'guard_config','dynamic_config','drive_limits','b2_config','rotation_risk','search_load',
            'search_composition','reference_release','cases')
    common={k:deepcopy(config[k]) for k in fields}
    common.update(canonical_model_sha256=canonical_model_sha256,evaluator_source_sha256=evaluator_sha256,
                  runtime_proof_sha256=comparison_key(config['runtime_proof']),failure_penalty_s=HORIZON_S,
                  initial_pose=dict(start_origin_z_m=-.004,target_depth_m=.004,roll_rad=0.,pitch_rad=0.,yaw_rad=0.),
                  metric_version='all_attempts_penalized_time_v1',
                  frozen_common_source_sha256={n:h for n,h in config['input_sha256'].items()
                    if n.startswith(('tools/','models/','assets/','deliverables/'))})
    return common


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('Finite nonnegative number required: '+label)
    return float(value)


def summarize(records, expected_cases):
    """One fixed-seed development matrix; duplicate cases and mixed versions fail.

    Runtime errors still count as attempts and receive the failure time penalty.
    Missing/invalid/unstopped cases disqualify comparison, even if other rows win.
    A missing load statistic stays null instead of being treated as zero load.
    """
    records = list(records)
    cases = list(expected_cases)
    if not cases or any(not isinstance(c, str) or not c for c in cases) or len(set(cases)) != len(cases):
        raise ValueError('Nonempty unique expected case IDs required')
    ids = [r['case_id'] for r in records]
    if len(set(ids)) != len(ids) or any(c not in cases for c in ids):
        raise ValueError('Duplicate or unexpected case; attempts cannot be replaced')
    keys = {r['comparison_key'] for r in records}
    if len(keys) > 1 or any(not isinstance(k, str) or not k for k in keys):
        raise ValueError('Mixed or missing common comparison key')
    successes = strict = guarded = invalid = unstopped = unassessed = 0
    penalties, successful_times = [], []
    loads = {k: [] for k in LOAD_FIELDS}
    for r in records:
        if r['status'] not in ('finished', 'error', 'partial'):
            raise ValueError('Unknown attempt status')
        if r['status'] != 'finished':
            unassessed += 1
            penalties.append(HORIZON_S)
            continue
        for field in ('simulation_valid', 'physical_stopped', 'strict_precision_success',
                      'contact_guard', 'motion_violation'):
            if type(r[field]) is not bool:
                raise ValueError('Boolean fact required: '+field)
        reasons = r['guard_reasons']
        if not isinstance(reasons, list) or any(not isinstance(x, str) or not x for x in reasons):
            raise ValueError('Explicit guard reason list required')
        if r['outcome'] not in OUTCOMES:
            raise ValueError('Unknown outcome')
        if bool(reasons) != (r['contact_guard'] or r['motion_violation']):
            raise ValueError('Guard reasons contradict independent guard facts')
        success = r['outcome'] == 'FULL_SUCCESS'
        expected = ('INVALID_SIMULATION' if not r['simulation_valid'] else
                    'CONTACT_GUARD' if r['contact_guard'] else
                    'MOTION_VIOLATION' if r['motion_violation'] else
                    'STOP_NOT_QUALIFIED' if not r['physical_stopped'] else
                    'FULL_SUCCESS' if success else 'TASK_FAILURE')
        if r['outcome'] != expected:
            raise ValueError('Outcome contradicts independent facts or adjudication priority')
        if r['strict_precision_success'] and not success:
            raise ValueError('Strict precision cannot override functional failure')
        end = _number(r['task_end_time_s'], 'task_end_time_s')
        physical_end = _number(r['physical_end_time_s'], 'physical_end_time_s')
        if end > HORIZON_S+1e-8 or physical_end+1e-8 < end:
            raise ValueError('Task/physical end time inconsistent with v4')
        for field in LOAD_FIELDS:
            loads[field].append(_number(r[field], field))
        successes += int(success)
        strict += int(r['strict_precision_success'])
        guarded += int(bool(reasons))
        invalid += int(not r['simulation_valid'])
        unstopped += int(not r['physical_stopped'])
        penalties.append(min(end, HORIZON_S) if success else HORIZON_S)
        if success:
            successful_times.append(end)
    missing = [c for c in cases if c not in ids]
    count = len(records)
    return dict(comparison_key=next(iter(keys), None), attempts=count, planned_cases=len(cases),
                missing_cases=missing, successes=successes, success_rate=successes/count if count else None,
                strict_precision_successes=strict, guarded_attempts=guarded, invalid_attempts=invalid,
                unstopped_attempts=unstopped, unassessed_attempts=unassessed,
                comparison_eligible=not (missing or invalid or unstopped or unassessed),
                failure_penalty_s=HORIZON_S, mean_penalized_time_s=mean(penalties) if penalties else None,
                mean_success_time_s=mean(successful_times) if successful_times else None,
                **{'mean_'+k:mean(v) if len(v)==count and count else None for k,v in loads.items()})


def compare(baseline, candidate, expected_cases):
    """Predeclared pilot signal: no fewer successes, >=10% penalized-time gain,
    no more guarded attempts and <=5% mean peak-force increase; at least one success.
    This is a development continuation rule, not statistical or publication proof.
    """
    b = summarize(baseline, expected_cases)
    c = summarize(candidate, expected_cases)
    if b['comparison_key'] != c['comparison_key']:
        raise ValueError('Common task/physics/control/evaluator contract differs')
    eligible = b['comparison_eligible'] and c['comparison_eligible']
    reduction = None
    signal = False
    if eligible and b['mean_penalized_time_s'] > 0:
        reduction = 1-c['mean_penalized_time_s']/b['mean_penalized_time_s']
        signal = bool(c['successes'] > 0 and c['successes'] >= b['successes'] and
                      reduction >= .1-1e-12 and c['guarded_attempts'] <= b['guarded_attempts'] and
                      c['mean_peak_force_N'] <= 1.05*b['mean_peak_force_N']+1e-12)
    return dict(baseline=b, candidate=c, pilot_signal=signal, time_reduction_fraction=reduction,
                scope='development_signal_not_paper_evidence')
