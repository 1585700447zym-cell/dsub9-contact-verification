"""B2-04 qualification: two reviewed learning changes and frozen physics lineage."""
from copy import deepcopy
import json
from pathlib import Path

from .admission import canonical, digest, validate_config, validate_case, verify_files, verify_test_report
from .b2_sac_admission import _parent as collection_parent, validate_record as validate_sac
from .b2_checkpoint_admission import CheckpointAdmission, validate_record as validate_checkpoint
from .runtime import ROOT
from tools.validation.verify_residual_interface import all_sources, qualified_runtime

PARENT = 'deliverables/learning_chain/b2_checkpoint_20260926/admission.json'
PARENT_SHA256 = '56ff0d2d4619bfaf391921961ab84e636f0ef81c2dc83146f918e6221a951b45'
PARENT_MANIFEST_SHA256 = '5e66b60288513a3db4d96e319d9c61246cfd42cb8f8c85f2c53d6963c4581a80'
SPLIT = 'deliverables/baseline_training_readiness/数据划分_v1.json'
SPLIT_SHA256 = '38e4c6c57044063df068e01cdc93d89d354785047007cbcace9df1ac4e0917da'
MODIFICATIONS = frozenset({'tools/learning/sac_collection.py', 'tools/learning/sac_checkpoint.py'})
ADDITIONS = frozenset({'tools/learning/b2_training_admission.py', 'tools/learning/engineering_training.py',
    'tools/learning/engineering_evaluation.py', 'tools/validation/run_engineering_short_train.py',
    'tests/learning/test_b2_training_admission.py', 'tests/learning/test_engineering_training.py'})
GATES = frozenset({'parent', 'runtime', 'config', 'reviewed_delta', 'tests', 'source_unchanged', 'execution_contract'})
TEST_MODULES = frozenset({'test_b2_training_admission', 'test_engineering_training',
    'test_sac_checkpoint', 'test_sac_update', 'test_sac_collection', 'test_audited_replay'})


def execution_contract():
    return dict(version='engineering_short_train_v1', fresh_initialization=True, target_audited_cycles=20000,
        finish_whole_episode=True, total_cycles_upper_bound=33000, updates_after_each_publication='all_earned_credit',
        warmup='episode_mode_selected_from_pre_episode_audited_total', checkpoint_each_episode=True,
        checkpoint_selection='final_after_target_whole_episode_and_updates', new_process_evaluation=True,
        evaluation_ids=[f'validation_small_xy_{i:02d}' for i in range(8)],
        evaluation_methods=['zero_b2', 'sac'], evaluation_seed=2026092202, deterministic_evaluation=True,
        evaluation_training_admitted=False, independent_test_used=False, retain_all_attempts=True)


def validate_delta(old, current):
    added = set(current) - set(old)
    modified = {p for p in old.keys() & current.keys() if old[p] != current[p]}
    if set(old) - set(current) or added != ADDITIONS or modified != MODIFICATIONS:
        raise ValueError('Only the two reviewed learning changes and six B2-04 additions are allowed')
    return dict(added=sorted(added), modified=sorted(modified))


def validate_record(record, *, current_sources, runtime):
    validate_config(record.get('config'))
    if (record.get('version') != 'b2_engineering_training_admission_v1' or
            record.get('capability') != 'engineering_short_train' or
            any(record.get(k) is not True for k in ('collection_admitted', 'update_admitted', 'restore_admitted', 'runnable_trainer')) or
            record.get('parent_sha256') != PARENT_SHA256 or
            canonical(record.get('execution_contract')) != canonical(execution_contract()) or
            set(record.get('gates', {})) != GATES or any(v is not True for v in record['gates'].values()) or
            record.get('source_sha256') != current_sources or canonical(record.get('runtime')) != canonical(runtime)):
        raise ValueError('Engineering training qualification incomplete, stale or outside frozen scope')


def verify_training_evidence(record):
    relative = record.get('test_report'); tests = record.get('tests')
    if not isinstance(relative, str) or not relative or not isinstance(tests, dict):
        raise ValueError('Explicit qualified test report and result required')
    path = (ROOT / relative).resolve()
    manifest = (Path(PARENT).parent / 'manifest.json').as_posix()
    evidence = record.get('evidence_sha256')
    expected = {relative: tests.get('sha256'), manifest: PARENT_MANIFEST_SHA256, SPLIT: SPLIT_SHA256}
    if not path.is_relative_to(ROOT) or evidence != expected or not tests.get('sha256'):
        raise ValueError('Training test report, parent delivery and split must all be bound')
    verify_files(ROOT, evidence)
    actual = verify_test_report(path, required_modules=TEST_MODULES, minimum=400)
    if actual != tests: raise ValueError('Training test result does not reproduce from bound JUnit report')


def _parent(runtime):
    collection_parent(runtime)
    from .b2_checkpoint_admission import PARENT as sac_path, PARENT_SHA256 as sac_sha, PARENT_MANIFEST_SHA256 as sac_manifest
    for relative, sha, manifest_sha, validator, passed in (
            (sac_path, sac_sha, sac_manifest, validate_sac, 'sac_update_verified'),
            (PARENT, PARENT_SHA256, PARENT_MANIFEST_SHA256, validate_checkpoint, 'full_checkpoint_verified')):
        path = ROOT / relative
        if digest(path) != sha or digest(path.parent / 'manifest.json') != manifest_sha:
            raise ValueError('Historical learning qualification or delivery changed')
        record = json.loads(path.read_text(encoding='utf-8'))
        validator(record, current_sources=record['source_sha256'], runtime=runtime)
        verify_files(ROOT, record['evidence_sha256'])
        verify_files(ROOT, json.loads((path.parent / 'manifest.json').read_text(encoding='utf-8'))['files'])
        # Historical hashes bind the original snapshots, never the two reviewed replacements.
        unchanged = {p: h for p, h in record['source_sha256'].items() if p not in MODIFICATIONS}
        verify_files(ROOT, unchanged)
        for p in MODIFICATIONS & record['source_sha256'].keys():
            snapshot = ((ROOT / sac_path).parent / 'snapshots/sources' if p.endswith('sac_collection.py')
                        else (ROOT / PARENT).parent / 'source_snapshot')
            if digest(snapshot / p) != record['source_sha256'][p]:
                raise ValueError('Historical learning source snapshot changed')
        if json.loads((path.parent / 'assessment.json').read_text(encoding='utf-8')).get(passed) is not True:
            raise ValueError('Historical numerical qualification did not pass')
    if digest(ROOT / SPLIT) != SPLIT_SHA256: raise ValueError('Frozen development split changed')
    return record


def create_training_admission(output, *, test_report, checked_sources):
    output, test_report = Path(output).resolve(), Path(test_report).resolve()
    if not output.is_relative_to(ROOT) or not test_report.is_relative_to(ROOT): raise ValueError('Worktree paths required')
    if output.exists(): raise FileExistsError(output)
    runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe'); parent = _parent(runtime)
    sources = all_sources()
    if sources != checked_sources: raise ValueError('Sources changed during qualification')
    delta = validate_delta(parent['source_sha256'], sources)
    tests = verify_test_report(test_report, required_modules=TEST_MODULES, minimum=400)
    manifest = (ROOT / PARENT).parent / 'manifest.json'
    evidence = {test_report.relative_to(ROOT).as_posix(): digest(test_report),
        manifest.relative_to(ROOT).as_posix(): digest(manifest), SPLIT: SPLIT_SHA256}
    record = dict(version='b2_engineering_training_admission_v1', capability='engineering_short_train',
        collection_admitted=True, update_admitted=True, restore_admitted=True, runnable_trainer=True,
        parent_sha256=PARENT_SHA256, config=parent['config'], runtime=runtime, execution_contract=execution_contract(),
        source_sha256=sources, source_delta=delta, inherited_unchanged_count=len(parent['source_sha256']) - len(MODIFICATIONS),
        test_report=test_report.relative_to(ROOT).as_posix(), tests=tests,
        evidence_sha256=evidence, gates={k: True for k in sorted(GATES)})
    if all_sources() != sources: raise ValueError('Sources changed while binding')
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return record


class TrainingAdmission(CheckpointAdmission):
    def verify(self, case=None):
        if not self.expected_digest or digest(self.path) != self.expected_digest: raise ValueError('Wrong training qualification digest')
        record = json.loads(self.path.read_text(encoding='utf-8'))
        runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe'); parent = _parent(runtime)
        sources = all_sources(); delta = validate_delta(parent['source_sha256'], sources)
        validate_record(record, current_sources=sources, runtime=runtime)
        if record['source_delta'] != delta: raise ValueError('Unexpected learning source delta')
        verify_training_evidence(record)
        if case is not None: validate_case(case)
        self._record = record
        return deepcopy(record)
