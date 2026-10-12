"""Read-only inherited-archive audit and zero-compute candidate publication."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
import sys

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
from contract import ROOT, S20, HELPERS, LIMITS, read, write, sha, digest, check_archive, grant_template, check_runtime

S21 = ROOT / 'deliverables/learning_chain/b2_joint_efficiency_diagnosis_20261010'
RUNTIME_RECORD = ROOT / 'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json'


def audit_reuse():
    config = read(S20 / 'configuration.json'); scores = read(S20 / 'assessment.json')['scores']
    sources = read(S21 / 'registration.json')['archives']; rows = []; fingerprints = {'F0': set(), 'F2000': set()}
    if len(sources) != 8 or {(x['model'], x['case_id']) for x in sources} != {
            (role, point['id']) for role in ('F0', 'F2000') for point in config['cases']}:
        raise ValueError('Exactly eight inherited matched evaluations required')
    for item in sources:
        path = Path(item['path'])
        if not path.resolve().is_relative_to(ROOT) or sha(path) != item['sha256']:
            raise ValueError('Inherited archive path/hash differs')
        raw = json.loads(gzip.decompress(path.read_bytes()))
        point = next(p for p in config['cases'] if p['id'] == item['case_id'])
        phase = 'zero' if item['model'] == 'F0' else 'final'
        score = next(r for r in scores[phase]['rows'] if r['case_id'] == item['case_id'])
        row = check_archive(raw, point, item['model'], config['common_key'], score,
                            config['methods']['F50']['schema'])
        row.update(path=str(path), sha256=item['sha256'], control_cycles=raw['control_cycles'])
        rows.append(row); fingerprints[item['model']].add(row['policy_sha256'])
    if any(len(values) != 1 for values in fingerprints.values()):
        raise ValueError('A frozen policy must remain identical across its four evaluations')
    report = dict(version='pure_b2_reuse_audit_v1', reused_evaluations=len(rows), rows=rows,
                  common_key=config['common_key'], verified=True,
                  qualification_labels_preserved=True, new_model_loads=0, new_policy_calls=0,
                  new_physics=0, new_updates=0, independent_tests=0,
                  limit='Immutable previously accepted development archives; no new physical counterfactual')
    write(OUT / 'reuse_assessment.json', report)
    return report


def freeze():
    report = audit_reuse()
    old_binding = read(HELPERS / 'source_binding.json')
    config = read(S20 / 'configuration.json')
    if digest(old_binding['runtime']['native']) != config['common']['runtime_proof_sha256']:
        raise ValueError('Inherited native runtime proof differs from common task')
    if sha(RUNTIME_RECORD) != old_binding['runtime']['native']['compatibility_record_sha256']:
        raise ValueError('Qualified native runtime record changed')
    executable = Path(old_binding['runtime']['executable']); prefix = executable.parent.parent
    cfg = prefix / 'pyvenv.cfg'
    venv = dict(line.split(' = ', 1) for line in cfg.read_text(encoding='utf8').splitlines() if ' = ' in line)
    base_executable = Path(venv['executable']); site = prefix / 'Lib/site-packages'
    lock = ROOT / 'deliverables/residual_interface/learning_tensor_20260924/requirements.lock.txt'
    if sha(lock) != old_binding['runtime']['lock_sha256']: raise ValueError('Original dependency lock differs')
    numerical_paths = [executable, cfg, base_executable, base_executable.parent / 'python313.dll', lock]
    for folder, inventory in old_binding['inventories'].items():
        numerical_paths += [Path(folder) / item for item in inventory]
    for path in numerical_paths:
        if old_binding['files'].get(str(path.resolve())) != sha(path):
            raise ValueError('Previously frozen numerical runtime changed: ' + str(path))
    numerical_inventories = dict(old_binding['inventories'])
    for folder in [site / 'gymnasium', *site.glob('numpy-*.dist-info'), *site.glob('gymnasium-*.dist-info')]:
        inventory = sorted(str(p.relative_to(folder)).replace('\\', '/') for p in folder.rglob('*')
                           if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
        numerical_inventories[str(folder)] = inventory
        numerical_paths += [folder / item for item in inventory]
    numerical_runtime = dict(executable=str(executable), base_executable=str(base_executable),
         prefix=str(prefix), python=old_binding['runtime']['python'], site_packages=str(site),
         versions=old_binding['runtime']['versions'], inventories=numerical_inventories,
         package_paths={name: str(site / name / '__init__.py') for name in ('numpy', 'gymnasium')})
    check_runtime(numerical_runtime)
    shutil.copyfile(S20 / 'configuration.json', OUT / 'configuration.json')
    shutil.copyfile(S20 / 'model.xml', OUT / 'model.xml')
    if sha(OUT / 'model.xml') != config['common']['canonical_model_sha256']:
        raise ValueError('Canonical model changed')
    candidate = dict(version='pure_b2_candidate_v1', status='PREPARED_NOT_AUTHORIZED',
                     case_ids=[p['id'] for p in config['cases']], comparison_key=config['common_key'],
                     limits=LIMITS, reuse_verified=report['verified'], reused_evaluations=8,
                     training_admitted=False, scientific_execution_admitted=False,
                     scope='four_existing_joint_development_cases_only', old_profile_gaps_preserved=3,
                     runtime=old_binding['runtime'], runtime_record=str(RUNTIME_RECORD))
    write(OUT / 'candidate.json', candidate)
    paths = [OUT / name for name in ('contract.py', 'prepare.py', 'baseline_entry.py',
                                     'baseline_rollout.py', 'configuration.json', 'model.xml',
                                     'candidate.json', 'reuse_assessment.json')]
    paths += [HELPERS / name for name in ('bounded_io.py', 'windows_job.py', 'joint_rollout.py', 'source_binding.json',
                                        'supervised.py', 'phase_deadline.py', 'joint_contract.py')]
    paths += [S20 / name for name in ('configuration.json', 'assessment.json', 'delivery_manifest.json')]
    paths += [S21 / 'registration.json', RUNTIME_RECORD]
    paths += [Path(row['path']) for row in report['rows']]
    paths += list((ROOT / 'tools').rglob('*.py'))
    paths += [Path(old_binding['runtime']['executable'])]
    paths += numerical_paths
    for path in config['common']['frozen_common_source_sha256']:
        if sha(ROOT / path) != config['common']['frozen_common_source_sha256'][path]:
            raise ValueError('Frozen common source differs: ' + path)
        paths.append(ROOT / path)
    files = {str(p.resolve()): sha(p) for p in paths}
    binding = dict(version='pure_b2_source_binding_v1', files=files, common_key=config['common_key'],
                   executable=old_binding['runtime']['executable'], runtime_record=str(RUNTIME_RECORD),
                   runtime_record_sha256=sha(RUNTIME_RECORD), inherited_policy_archives=8,
                   preparation_only=True, numerical_runtime=numerical_runtime)
    write(OUT / 'source_binding.json', binding)
    pin = sha(OUT / 'source_binding.json')
    write(OUT / 'authorization_request.json', grant_template(pin, 'pending-new-run-id'))
    write(OUT / 'qualification_candidate.json', dict(offline_prepared=True, reuse_verified=True,
          binding_sha256=pin, physical_execution_verified=False, scientific_execution_admitted=False,
          training_admitted=False, cumulative_dynamic=254, independent_tests=0,
          full_B2_accepted=False, C_accepted=False, automatic_tracking='PAUSED'))
    return dict(reused_evaluations=8, binding_sha256=pin, source_files=len(files), physics=0,
                policy_calls=0, formal_updates=0, scientific_execution_admitted=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--audit-reuse', action='store_true')
    args = parser.parse_args()
    print(json.dumps(audit_reuse() if args.audit_reuse else freeze(), ensure_ascii=False))
