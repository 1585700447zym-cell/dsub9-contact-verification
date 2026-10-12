"""B2-02 qualification for fresh collection and a bounded numerical SAC probe."""
from copy import deepcopy
import json
from pathlib import Path

from .admission import canonical, digest, validate_config, validate_case, verify_files, verify_test_report
from .b2_admission import (CollectionAdmission, _parent as b1_parent,
                          validate_record as validate_collection_record, validate_extension)
from .runtime import ROOT
from tools.validation.verify_residual_interface import all_sources, qualified_runtime

PARENT = 'deliverables/learning_chain/b2_collection_20260926/admission.json'
PARENT_SHA256 = 'dfa711bdca3ff8c4e5c09c53f1221979206ca6b0e4a7c012bc27ea34743bb40d'
PARENT_MANIFEST_SHA256 = 'a31ab5b70d16a4783290bd2c336ceb11dba7690f219a93bcf258c58f2d0ad99f'
ADDITIONS = frozenset({'tools/learning/sac_update.py', 'tools/learning/sac_collection.py',
    'tools/learning/b2_sac_admission.py', 'tools/validation/verify_sac_update.py',
    'tests/learning/test_sac_update.py', 'tests/learning/test_sac_collection.py',
    'tests/learning/test_b2_sac_admission.py'})
GATES = frozenset({'parent', 'runtime', 'config', 'extension', 'tests', 'source_unchanged', 'execution_contract'})


def execution_contract():
    return dict(version='sac_update_probe_v1', warmup='uniform_normalized_four_dimensions_until_5000_audited',
        initialization_rng='PCG64(seed)', action_rng='PCG64(SeedSequence([seed,1]))',
        replay_rng='PCG64(SeedSequence([seed,2]))', torch_rng='private_CPU_state_seeded_from_learning_seed',
        credit='min(8250,floor(max(cumulative_audited-5000,0)/4))-completed_critic_batches',
        update_boundary='whole_episode_audited_and_published', max_probe_updates=16,
        warmup_episodes=2, post_update_cut_cycles=8, full_checkpoint_verified=False,
        first_engineering_short_train=False)


def validate_record(record, *, current_sources, runtime):
    validate_config(record.get('config'))
    if (record.get('version') != 'b2_sac_update_admission_v1' or
            record.get('capability') != 'bounded_sac_update_probe' or
            record.get('collection_admitted') is not True or record.get('update_admitted') is not True or
            record.get('runnable_trainer') is not False or record.get('parent_sha256') != PARENT_SHA256 or
            canonical(record.get('execution_contract')) != canonical(execution_contract()) or
            set(record.get('gates', {})) != GATES or any(v is not True for v in record['gates'].values()) or
            record.get('source_sha256') != current_sources or canonical(record.get('runtime')) != canonical(runtime)):
        raise ValueError('SAC probe qualification incomplete, stale or outside approved scope')


def _parent(runtime):
    b1_parent(runtime)
    path = ROOT / PARENT
    if digest(path) != PARENT_SHA256: raise ValueError('B2-01 parent qualification changed')
    if digest(path.parent / 'manifest.json') != PARENT_MANIFEST_SHA256:
        raise ValueError('B2-01 parent delivery manifest changed')
    record = json.loads(path.read_text(encoding='utf-8'))
    validate_collection_record(record, current_sources=record['source_sha256'], runtime=runtime)
    verify_files(ROOT, record['source_sha256'])
    verify_files(ROOT, record['evidence_sha256'])
    manifest = json.loads((path.parent / 'manifest.json').read_text(encoding='utf-8'))
    verify_files(ROOT, manifest['files'])
    from tools.validation.verify_admitted_collection import audit_archives
    actual = audit_archives(path.parent)
    report = json.loads((path.parent / 'assessment.json').read_text(encoding='utf-8'))
    if report.get('collection_verified') is not True or any(report[k] != v for k, v in actual.items()):
        raise ValueError('B2-01 original publication evidence does not reproduce')
    return record


def create_sac_admission(output, *, test_report, checked_sources):
    output, test_report = Path(output).resolve(), Path(test_report).resolve()
    if not output.is_relative_to(ROOT) or not test_report.is_relative_to(ROOT): raise ValueError('Worktree paths required')
    if output.exists(): raise FileExistsError(output)
    runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    parent = _parent(runtime)
    sources = all_sources()
    if sources != checked_sources: raise ValueError('Sources changed during qualification')
    added = validate_extension(parent['source_sha256'], sources, allowed_additions=ADDITIONS)
    tests = verify_test_report(test_report, required_modules={'test_sac_update', 'test_sac_collection',
        'test_b2_sac_admission', 'test_admitted_collection', 'test_audited_replay', 'test_tensor_masks'}, minimum=32)
    parent_manifest = (ROOT / PARENT).parent / 'manifest.json'
    evidence = {test_report.relative_to(ROOT).as_posix(): digest(test_report),
                parent_manifest.relative_to(ROOT).as_posix(): digest(parent_manifest)}
    record = dict(version='b2_sac_update_admission_v1', capability='bounded_sac_update_probe',
        collection_admitted=True, update_admitted=True, runnable_trainer=False, parent_sha256=PARENT_SHA256,
        config=parent['config'], runtime=runtime, execution_contract=execution_contract(), source_sha256=sources,
        inherited_source_count=len(parent['source_sha256']), added_sources=added, tests=tests,
        evidence_sha256=evidence, gates={k: True for k in sorted(GATES)})
    if all_sources() != sources: raise ValueError('Sources changed while binding')
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    return record


class SACAdmission(CollectionAdmission):
    def verify(self, case=None):
        if not self.expected_digest or digest(self.path) != self.expected_digest: raise ValueError('Wrong SAC qualification digest')
        record = json.loads(self.path.read_text(encoding='utf-8'))
        runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
        parent = _parent(runtime)
        sources = all_sources()
        added = validate_extension(parent['source_sha256'], sources, allowed_additions=ADDITIONS)
        validate_record(record, current_sources=sources, runtime=runtime)
        if record['added_sources'] != added: raise ValueError('Unexpected code additions')
        verify_files(ROOT, record['evidence_sha256'])
        if case is not None: validate_case(case)
        self._record = record
        return deepcopy(record)
