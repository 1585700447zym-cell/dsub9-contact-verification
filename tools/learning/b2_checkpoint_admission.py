"""Additive B2-03 qualification, still bounded to sixteen update batches."""
from copy import deepcopy
import json
from pathlib import Path

from .admission import canonical, digest, validate_config, validate_case, verify_files, verify_test_report
from .b2_admission import validate_extension
from .b2_sac_admission import SACAdmission, _parent as collection_parent, validate_record as validate_sac_record
from .runtime import ROOT
from tools.validation.verify_residual_interface import all_sources, qualified_runtime

PARENT = 'deliverables/learning_chain/b2_sac_update_20260926/admission.json'
PARENT_SHA256 = 'd1f42deff861fa00c33b0932695dbb9c06ed0192bb3a0e83901f477996e973bf'
PARENT_MANIFEST_SHA256 = '08288fc1401b14ad58de9b4f17e3c1f8da7a45eafb2e1da5ad1c691c32e55c3d'
ADDITIONS = frozenset({'tools/learning/sac_checkpoint.py', 'tools/learning/b2_checkpoint_admission.py',
    'tools/validation/verify_sac_checkpoint.py', 'tests/learning/test_sac_checkpoint.py',
    'tests/learning/test_b2_checkpoint_admission.py'})
GATES = frozenset({'parent', 'runtime', 'config', 'extension', 'tests', 'source_unchanged', 'execution_contract'})


def execution_contract():
    return dict(version='sac_checkpoint_probe_v1', max_probe_updates=16, before_save_updates=8,
        resume_boundary='whole_episode_audited_and_published', warmup_episodes=2,
        continuation_cut_cycles=8, paired_new_process=True, first_engineering_short_train=False)


def validate_record(record, *, current_sources, runtime):
    validate_config(record.get('config'))
    if (record.get('version') != 'b2_checkpoint_admission_v1' or
            record.get('capability') != 'bounded_checkpoint_probe' or
            any(record.get(k) is not True for k in ('collection_admitted', 'update_admitted', 'restore_admitted')) or
            record.get('runnable_trainer') is not False or record.get('parent_sha256') != PARENT_SHA256 or
            canonical(record.get('execution_contract')) != canonical(execution_contract()) or
            set(record.get('gates', {})) != GATES or any(v is not True for v in record['gates'].values()) or
            record.get('source_sha256') != current_sources or canonical(record.get('runtime')) != canonical(runtime)):
        raise ValueError('Checkpoint probe qualification incomplete, stale or outside approved scope')


def _parent(runtime):
    collection_parent(runtime)
    path = ROOT / PARENT
    if digest(path) != PARENT_SHA256 or digest(path.parent / 'manifest.json') != PARENT_MANIFEST_SHA256:
        raise ValueError('B2-02 parent qualification or delivery changed')
    record = json.loads(path.read_text(encoding='utf-8'))
    validate_sac_record(record, current_sources=record['source_sha256'], runtime=runtime)
    verify_files(ROOT, record['source_sha256']); verify_files(ROOT, record['evidence_sha256'])
    verify_files(ROOT, json.loads((path.parent / 'manifest.json').read_text(encoding='utf-8'))['files'])
    # The immutable numerical probe was independently replayed before extension;
    # its entire raw evidence and assessment are bound by this pinned manifest.
    report = json.loads((path.parent / 'assessment.json').read_text(encoding='utf-8'))
    if report.get('sac_update_verified') is not True: raise ValueError('Parent SAC probe did not pass')
    return record


def create_checkpoint_admission(output, *, test_report, checked_sources):
    output, test_report = Path(output).resolve(), Path(test_report).resolve()
    if not output.is_relative_to(ROOT) or not test_report.is_relative_to(ROOT): raise ValueError('Worktree paths required')
    if output.exists(): raise FileExistsError(output)
    runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe'); parent = _parent(runtime)
    sources = all_sources()
    if sources != checked_sources: raise ValueError('Sources changed during qualification')
    added = validate_extension(parent['source_sha256'], sources, allowed_additions=ADDITIONS)
    tests = verify_test_report(test_report, required_modules={'test_sac_checkpoint', 'test_b2_checkpoint_admission',
        'test_sac_update', 'test_sac_collection', 'test_audited_replay'}, minimum=35)
    manifest = (ROOT / PARENT).parent / 'manifest.json'
    evidence = {test_report.relative_to(ROOT).as_posix(): digest(test_report),
                manifest.relative_to(ROOT).as_posix(): digest(manifest)}
    record = dict(version='b2_checkpoint_admission_v1', capability='bounded_checkpoint_probe',
        collection_admitted=True, update_admitted=True, restore_admitted=True, runnable_trainer=False,
        parent_sha256=PARENT_SHA256, config=parent['config'], runtime=runtime,
        execution_contract=execution_contract(), source_sha256=sources, inherited_source_count=len(parent['source_sha256']),
        added_sources=added, tests=tests, evidence_sha256=evidence, gates={k: True for k in sorted(GATES)})
    if all_sources() != sources: raise ValueError('Sources changed while binding')
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return record


class CheckpointAdmission(SACAdmission):
    def verify(self, case=None):
        if not self.expected_digest or digest(self.path) != self.expected_digest: raise ValueError('Wrong checkpoint qualification digest')
        record = json.loads(self.path.read_text(encoding='utf-8'))
        runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe'); parent = _parent(runtime)
        sources = all_sources()
        added = validate_extension(parent['source_sha256'], sources, allowed_additions=ADDITIONS)
        validate_record(record, current_sources=sources, runtime=runtime)
        if record['added_sources'] != added: raise ValueError('Unexpected code additions')
        verify_files(ROOT, record['evidence_sha256'])
        if case is not None: validate_case(case)
        self._record = record
        return deepcopy(record)
