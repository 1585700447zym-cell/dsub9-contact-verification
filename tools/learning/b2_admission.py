"""Additive B.2 collection qualification; no SAC/update/restore permission.

The immutable B.1 parent remains authoritative for unchanged physics. All new
source files are enumerated, tested and rebound; a stale record fails closed.
Hashes are change detection, not protection from a malicious local code author.
"""
from copy import deepcopy
import json
from pathlib import Path

from .admission import (canonical, digest, validate_case, validate_config,
                        verify_admission, verify_files, verify_test_report)
from .runtime import ROOT
from tools.validation.verify_residual_interface import all_sources, qualified_runtime, effective_parameters

PARENT = 'deliverables/residual_interface/b1_closeout_20260926/admission.json'
PARENT_SHA256 = '88fe3b06a2f1e2796ccc3450b1c1955a4187a98f60155d0bf65d11641f79eedf'
ADDITIONS = frozenset({
    'tools/learning/b2_admission.py', 'tools/learning/admitted_collection.py',
    'tools/validation/verify_admitted_collection.py',
    'tests/learning/test_b2_admission.py', 'tests/learning/test_admitted_collection.py',
})
GATES = frozenset({'parent', 'runtime', 'config', 'extension', 'tests', 'source_unchanged'})


def validate_extension(parent_sources, current_sources, *, allowed_additions=ADDITIONS):
    if not parent_sources or any(current_sources.get(k) != v for k, v in parent_sources.items()):
        raise ValueError('Inherited source changed or missing; physical evidence cannot be silently inherited')
    added = set(current_sources) - set(parent_sources)
    if added != set(allowed_additions):
        raise ValueError(f'Unreviewed/missing additions: {sorted(added ^ set(allowed_additions))}')
    return sorted(added)


def validate_record(record, *, current_sources, runtime):
    validate_config(record.get('config'))
    if (record.get('version') != 'b2_collection_admission_v1' or
            record.get('capability') != 'audited_collection_only' or
            record.get('collection_admitted') is not True or record.get('runnable_trainer') is not False or
            record.get('parent_sha256') != PARENT_SHA256 or
            set(record.get('gates', {})) != GATES or
            any(value is not True for value in record['gates'].values()) or
            record.get('source_sha256') != current_sources or
            canonical(record.get('runtime')) != canonical(runtime)):
        raise ValueError('Incomplete, stale or out-of-scope collection qualification')


def _parent(runtime):
    path = ROOT / PARENT
    parent = json.loads(path.read_text(encoding='utf-8'))
    # This deliberately checks the original subset against today's files. Added
    # adapters do not invalidate unchanged physical evidence; any edit does.
    return verify_admission(path, root=ROOT, expected_digest=PARENT_SHA256,
        config=parent['config'], runtime=runtime, current_sources=parent['source_sha256'])


def create_collection_admission(output, *, test_report, checked_sources):
    """Called only after tests, with the exact pre-test source map."""
    output, test_report = Path(output).resolve(), Path(test_report).resolve()
    if not output.is_relative_to(ROOT) or not test_report.is_relative_to(ROOT):
        raise ValueError('Qualification and evidence must stay inside the worktree')
    if output.exists(): raise FileExistsError(output)
    runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    parent = _parent(runtime)
    sources = all_sources()
    if sources != checked_sources: raise ValueError('Sources changed during qualification tests')
    additions = validate_extension(parent['source_sha256'], sources)
    report = verify_test_report(test_report, required_modules={
        'test_b2_admission', 'test_admitted_collection', 'test_audited_replay',
        'test_candidate_collector', 'test_episode_buffer', 'test_gym_env',
        'test_residual_session', 'test_tensor_masks'}, minimum=26)
    evidence = {test_report.relative_to(ROOT).as_posix(): digest(test_report)}
    split = ROOT / 'deliverables/baseline_training_readiness/数据划分_v1.json'
    evidence[split.relative_to(ROOT).as_posix()] = digest(split)
    record = dict(version='b2_collection_admission_v1', capability='audited_collection_only',
        collection_admitted=True, runnable_trainer=False, parent_sha256=PARENT_SHA256,
        config=parent['config'], runtime=runtime, source_sha256=sources, added_sources=additions,
        inherited_source_count=len(parent['source_sha256']), tests=report, evidence_sha256=evidence,
        effective_parameters=effective_parameters(parent['config']),
        gates={key: True for key in sorted(GATES)},
        limitation='Collection-only qualification based on unchanged B.1 physics and adapter tests. '
                   'No SAC updates, training restoration, independent evaluation or arbitrary-policy safety guarantee.')
    if all_sources() != sources: raise ValueError('Sources changed while binding qualification')
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return record


class CollectionAdmission:
    def __init__(self, path, *, expected_digest):
        self.path = Path(path).resolve()
        self.expected_digest = expected_digest
        self.verify()

    @property
    def config(self): return deepcopy(self._record['config'])

    def verify(self, case=None):
        if not self.expected_digest or digest(self.path) != self.expected_digest:
            raise ValueError('Collection record does not match the pinned digest')
        record = json.loads(self.path.read_text(encoding='utf-8'))
        runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
        parent = _parent(runtime)
        sources = all_sources()
        additions = validate_extension(parent['source_sha256'], sources)
        validate_record(record, current_sources=sources, runtime=runtime)
        if record.get('added_sources') != additions:
            raise ValueError('Qualification additions differ from reviewed source delta')
        verify_files(ROOT, record['evidence_sha256'])
        if case is not None: validate_case(case)
        self._record = record
        return deepcopy(record)

