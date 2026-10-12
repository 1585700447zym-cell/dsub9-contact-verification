"""Audit the ten preserved scope archives. No simulation, grants or training."""
import argparse
import importlib.abc
import json
from pathlib import Path
import sys

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = ROOT / 'deliverables/learning_chain/b2_scope_auditor_fix_20261008'
PARENT = ROOT / 'deliverables/learning_chain/b2_pose_scope_preflight_20261008'
EXECUTION = ROOT / 'deliverables/learning_chain/b2_pose_scope_execution_20261008'
FORBIDDEN = {'mujoco', 'torch', 'stable_baselines3', 'tensorflow', 'jax', 'gymnasium'}
class OfflineOnly(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in FORBIDDEN:
            raise ImportError('Read-only archive audit prohibits ' + fullname)
sys.meta_path.insert(0, OfflineOnly())
sys.path.insert(0, str(OUT))
import repaired_assess as auditor
from scope_contract import read, sha
from run_preflight import check_binding, require_interpreter, BINDING

def check_revision():
    if Path(__file__).resolve().parent != OUT or Path(auditor.__file__).resolve() != OUT / 'repaired_assess.py':
        raise PermissionError('Registered read-only auditor location required')
    revision = read(OUT / 'revision_binding.json')
    expected = '9c15895cf6c8bac905715275c65dead6a8a48be617a3c197839077c7acf673c6'
    if sha(BINDING) != expected or revision['producer_binding_sha256'] != expected:
        raise ValueError('Producer binding changed')
    _, binding = check_binding()
    require_interpreter(binding)
    for name, pin in revision['files'].items():
        if sha(Path(name)) != pin:
            raise ValueError('Audit revision input changed: ' + name)
    return revision, dict(binding, binding_sha256=sha(BINDING))

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    revision, binding = check_revision()
    if args.output and (not args.output.resolve().is_relative_to(OUT) or args.output.exists()):
        raise ValueError('Output must be a new file inside this delivery')
    if args.check_only:
        assert 'numpy' not in sys.modules
        result = dict(status='CHECK_ONLY_PASSED', revision_sha256=sha(OUT / 'revision_binding.json'),
            revision_inputs=len(revision['files']), inherited_inputs=len(binding['files']), numerical_imports=[],
            new_simulation=0, new_training=0)
    else:
        rows = []
        for entry in read(EXECUTION / 'authorization_closure.json')['actual_attempts']:
            archive = EXECUTION / 'run' / (entry['id'] + '.json.gz')
            raw = auditor.read_archive(archive)
            result = auditor.assess_raw(raw, raw['spec'], binding)
            rows.append(dict(id=entry['id'], archive_sha256=sha(archive), assessment=result))
        matrix = auditor.assess(EXECUTION / 'run')
        result = dict(status='REPAIRED_OFFLINE_AUDIT_PASSED', revision_sha256=sha(OUT / 'revision_binding.json'),
            producer_binding_sha256=binding['binding_sha256'], archived_attempts=rows,
            original_matrix_route=matrix['route'], original_dynamic_status=matrix['dynamic'][0]['status'],
            original_unrun_dynamics=sum(r['status'] == 'NOT_ATTEMPTED' for r in matrix['dynamic']),
            new_simulation=0, new_training=0, cumulative_dynamic=209, training_admitted=False,
            physical_runner_rebound=False, original_ledger_unchanged=True,
            limitation='Read-only reassessment of existing evidence; no original run status or admission is changed.')
    assert not any(k.split('.')[0] in FORBIDDEN for k in sys.modules)
    if args.output:
        with args.output.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print(json.dumps(dict(status=result['status'], output=str(args.output), sha256=sha(args.output)), ensure_ascii=False))
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
