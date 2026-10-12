"""Read-only failure reproduction and a type-normalization hypothesis test.

This does not repair the sealed runner, qualify an attempt or reopen a grant.
"""
import gzip
import importlib.abc
import json
import math
from pathlib import Path
import sys
import traceback

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'deliverables/learning_chain/b2_pose_scope_preflight_20261008'
FORBIDDEN = {'mujoco', 'torch', 'stable_baselines3', 'tensorflow', 'jax', 'gymnasium'}

class NoPhysicalOrLearning(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in FORBIDDEN:
            raise ImportError('Offline diagnosis prohibits ' + fullname)

sys.meta_path.insert(0, NoPhysicalOrLearning())
sys.path.insert(0, str(SOURCE))
from scope_contract import sha, read
from run_preflight import check_binding, BINDING
import assess
from offline_math import numerics

def error_evidence(call):
    try:
        call()
    except Exception as exc:
        frames = []
        for frame, line in traceback.walk_tb(exc.__traceback__):
            values = frame.f_locals
            if frame.f_code.co_name == 'same':
                frames.append(dict(line=line, label=values['label'],
                    left_type=type(values['left']).__module__ + '.' + type(values['left']).__name__,
                    right_type=type(values['right']).__module__ + '.' + type(values['right']).__name__,
                    left=repr(values['left']), right=repr(values['right'])))
            elif frame.f_code.co_name == 'assess_raw':
                frames.append(dict(line=line, cycle_index=values.get('i')))
        return dict(error=repr(exc), frames=frames)
    raise AssertionError('Registered comparator unexpectedly accepted the counterexample')

def main():
    assert OUT == ROOT / 'deliverables/learning_chain/b2_pose_scope_execution_20261008'
    ledger = read(OUT / 'run/ledger.json')
    assert ledger['status'] == 'CLOSED_SUPERVISOR_ERROR' and ledger['dynamic_attempts'] == 1
    _, binding = check_binding()
    binding = dict(binding, binding_sha256=sha(BINDING))
    path = OUT / 'run/P01_zero.json.gz'
    raw_pin = sha(path)
    raw = assess.read_archive(path)
    n = numerics()
    np = n['np']
    original_same = assess.same
    original_failure = error_evidence(lambda: assess.assess_raw(raw, raw['spec'], binding))
    examples = []
    for left, right in [(0., np.float64(0.)), (np.float64(0.), 0.),
                        (raw['cycles'][0]['result']['reward_terms']['progress'],
                         np.float64(raw['cycles'][0]['result']['reward_terms']['progress']))]:
        assert float(left) == float(right) and math.isfinite(left) and math.isfinite(right)
        examples.append(dict(equal_finite_value=float(left), evidence=error_evidence(
            lambda left=left, right=right: original_same(left, right, 'scalar_counterexample'))))

    reward = n['EpisodeReward'](.004)
    mismatches = []
    for i, cycle in enumerate(raw['cycles']):
        result = cycle['result']
        row = result['trace_row']
        peaks = result['cycle_peaks']
        parts = reward.advance(advance_m=row['position_m'][2] - raw['initial']['position_m'][2],
            dt=result['dt'], force_N=peaks['force_N'], torque_G_Nm=peaks['torque_G_Nm'])
        parts['terminal'] = reward.finalize(raw['outcome']['task_outcome']) if i == len(raw['cycles']) - 1 else 0.
        parts['total'] += parts['terminal']
        if any(abs(parts[k] - result['reward_terms'][k]) > 1e-12 for k in parts):
            mismatches.append(i)
    assert not mismatches

    def json_scalar_types(value):
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, dict):
            return {k: json_scalar_types(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [json_scalar_types(v) for v in value]
        return value

    def normalized_same(left, right, label, tolerance=1e-12):
        return original_same(json_scalar_types(left), json_scalar_types(right), label, tolerance)

    negative_controls = []
    for label, left, right in [('changed_number', 0., np.float64(1e-6)),
                               ('nonfinite', float('nan'), np.float64(float('nan'))),
                               ('bool_vs_number', True, np.float64(1.)),
                               ('number_vs_bool', 1., np.bool_(True))]:
        negative_controls.append(dict(label=label, rejected=error_evidence(
            lambda left=left, right=right: normalized_same(left, right, 'negative_control'))))
    for left, right in [(0., np.float64(0.)), (np.float64(0.), 0.)]:
        normalized_same(left, right, 'equal_finite')

    # Hypothesis experiment only: change the comparator in this read-only process.
    # No source file, ledger, raw archive or grant is changed.
    assess.same = normalized_same
    try:
        alternative = assess.assess_raw(raw, raw['spec'], binding)
        result = dict(status='DIAGNOSTIC_AUDIT_PASSED_AFTER_SCALAR_TYPE_NORMALIZATION',
            assessment=alternative)
    except Exception as exc:
        result = dict(status='DIAGNOSTIC_AUDIT_STILL_FAILED', error=repr(exc))
    finally:
        assess.same = original_same
    assert sha(path) == raw_pin
    assert not any(k.split('.')[0] in FORBIDDEN for k in sys.modules)
    report = dict(stage_id='B2-SCOPE-03', diagnostic_only=True,
        sealed_runner_modified=False, ledger_modified=False, retry_allowed=False, training_admitted=False,
        original_archive_sha256=raw_pin, original_ledger_sha256=sha(OUT / 'run/ledger.json'),
        source_sha256={name: sha(SOURCE / name) for name in ('assess.py', 'offline_math.py', 'physical_worker.py')},
        production_reward_sha256=sha(ROOT / 'tools/learning/reward.py'),
        loaded_forbidden=[], new_physical_steps=0, new_network_forwards=0, new_optimizer_updates=0,
        worker_original_error='ValueError: reward.progress differs/nonfinite',
        serialized_archive_reproduction=original_failure, equal_numeric_counterexamples=examples,
        reward_rows_verified=len(raw['cycles']), reward_mismatch_rows=mismatches,
        negative_controls=negative_controls, counterfactual=result,
        limitation='Type-normalization is an offline diagnostic hypothesis test; original run remains closed and unqualified.')
    with (OUT / 'audit_diagnosis.json').open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(dict(status=result['status'], reward_rows_verified=len(raw['cycles']),
        original_reproduction=original_failure['error'], scalar_counterexamples=len(examples),
        negative_controls=len(negative_controls), loaded_forbidden=[]), ensure_ascii=False))

if __name__ == '__main__':
    main()
