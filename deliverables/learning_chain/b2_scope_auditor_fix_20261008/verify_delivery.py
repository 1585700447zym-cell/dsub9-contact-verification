"""Verify/seal the offline repair without importing NumPy or an engine."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = Path(__file__).resolve().parent
PARENT = OUT.parent / 'b2_pose_scope_preflight_20261008'
EXECUTION = OUT.parent / 'b2_pose_scope_execution_20261008'
sys.path.insert(0, str(PARENT))
from scope_contract import read, sha
from run_preflight import check_binding
DOCS = ['项目当前入口.md', '项目进度跟踪.md', '项目交付总览.md', '研究推进计划_当前版.md',
        'deliverables/monthly_progress/2026-10/月报素材_2026-10.md', 'AGENTS.md']

def write_new(path, data):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal', action='store_true')
    parser.add_argument('--current-docs', action='store_true')
    args = parser.parse_args()
    if args.seal:
        assert not (OUT / 'delivery_manifest.json').exists()
    checks = 0
    def check(value, label):
        nonlocal checks
        if not value:
            raise AssertionError(label)
        checks += 1
    _, inherited = check_binding()
    revision = read(OUT / 'revision_binding.json')
    check(len(revision['files']) == 20 and len(inherited['files']) == 2167, 'Source/input counts')
    for name, pin in revision['files'].items():
        check(sha(Path(name)) == pin, 'Bound input ' + name)
    check(not revision['new_simulation_authorized'] and not revision['new_training_authorized'] and not revision['physical_runner_rebound'], 'Offline scope')
    old_members = 0
    for name, pin, count in [
        ('b2_scope_audit_20261008', 'f0ece40fc2fc3ab83b99506bb13a59158dc0282fe674dbaf03b3f5b7e47e0576', 19),
        ('b2_pose_scope_preflight_20261008', '178bf8cab98360b75148b4a587838e1a3493a4739576e4b713ef08a30f00a693', 63),
        ('b2_pose_scope_execution_20261008', 'dee846ade20816e11f5487c7968c0067bcd40c3b59d8e9e180f9138f505962fc', 119)]:
        folder = OUT.parent / name
        check(sha(folder / 'delivery_manifest.json') == pin, 'Old seal ' + name)
        files = read(folder / 'delivery_manifest.json')['files']
        check(len(files) == count, 'Old member count')
        for rel, item in files.items():
            check(sha(folder / rel) == item['sha256'] and (folder / rel).stat().st_size == item['bytes'], 'Old member ' + rel)
            old_members += 1
    history = json.loads(next(line for line in (OUT / 'historical_verification.txt').read_text(encoding='utf-8').splitlines() if line.startswith('{')))
    check(history['status'] == 'VERIFIED_OFFLINE_SCOPE_PLAN' and history['old_members'] == 950 and history['shared_inputs'] == 1057, 'Historical raw/source recheck')
    check(history['raw_pose_records'] == 63, 'Historical actual poses')
    for name, count in [('final_tests.txt', 14), ('inherited_final.txt', 6)]:
        log = (OUT / name).read_text(encoding='utf-8')
        check(f'Ran {count} tests' in log and log.rstrip().endswith('OK'), 'Final tests ' + name)
    for name in ('red_tests.txt', 'review_red.txt'):
        check('FAILED (failures=' in (OUT / name).read_text(encoding='utf-8'), 'Observed regression RED')
    result = read(OUT / 'archive_reassessment_final.json')
    check(result['status'] == 'REPAIRED_OFFLINE_AUDIT_PASSED', 'Final public entry audit')
    check(result['revision_sha256'] == sha(OUT / 'revision_binding.json'), 'Final auditor identity')
    rows = result['archived_attempts']
    check(len(rows) == 10 and all(r['assessment']['audit_passed'] for r in rows), 'Ten existing archives')
    for row in rows:
        check(row['archive_sha256'] == sha(EXECUTION / 'run' / (row['id'] + '.json.gz')), 'Audited raw identity')
    dynamic = rows[-1]['assessment']
    check(rows[-1]['id'] == 'P01_zero' and dynamic['observation']['vectors_verified'] == 3046, 'Actual dynamic record')
    check(dynamic['functional_success'] and dynamic['contact_cycles'] == 0, 'Limited retained physical evidence')
    check(result['original_matrix_route'] == 'NO_SCOPE_QUALIFICATION' and result['original_dynamic_status'] == 'error' and result['original_unrun_dynamics'] == 15, 'Original failure unchanged')
    check(result['new_simulation'] == result['new_training'] == 0 and result['cumulative_dynamic'] == 209 and not result['training_admitted'], 'Actual computation boundary')
    check(read(EXECUTION / 'run/ledger.json')['status'] == 'CLOSED_SUPERVISOR_ERROR', 'Closed grant not reopened')
    check_only = read(OUT / 'check_only_final.json')
    check(check_only['revision_sha256'] == result['revision_sha256'] and check_only['numerical_imports'] == [], 'Check-only runtime boundary')
    old_tree = ast.parse((PARENT / 'assess.py').read_text(encoding='utf-8'))
    new_tree = ast.parse((OUT / 'repaired_assess.py').read_text(encoding='utf-8'))
    old_defs = {n.name: ast.dump(n, include_attributes=False) for n in old_tree.body if isinstance(n, ast.FunctionDef)}
    new_defs = {n.name: ast.dump(n, include_attributes=False) for n in new_tree.body if isinstance(n, ast.FunctionDef)}
    for name in old_defs:
        if name != 'same':
            check(old_defs[name] == new_defs[name], 'Inherited audit logic ' + name)
    for name in DOCS:
        before = OUT / 'before_documents' / name
        after = OUT / 'document_snapshots' / name
        check(before.is_file() and after.is_file(), 'Before/after documents')
        if args.current_docs:
            check((ROOT / name).read_bytes() == after.read_bytes(), 'Current document snapshot')
        if name != 'AGENTS.md':
            text = after.read_text(encoding='utf-8')
            block = re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->', text, re.S).group(1)
            check('当前阶段B.2' in block and 'B2-SCOPE-04' in block and '完整B.2/C未验收' in block and '累计动态209' in block, 'Reported task and limits')
    for path in OUT.glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        checks += 1
    review = (OUT / 'review.md').read_text(encoding='utf-8')
    check('OFFLINE_AUDITOR_REPAIR_VERIFIED' in review and 'Declined to judge' in review, 'Review disposition')
    for name in ('结果说明.md', 'review.md'):
        path = OUT / name
        for link in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            target = (path.parent / link.split('#')[0]).resolve()
            check(target.exists() or (args.seal and target == OUT / 'verification.json'), 'Report link ' + link)
    check(not any(k.split('.')[0] in {'numpy', 'mujoco', 'torch', 'stable_baselines3'} for k in sys.modules), 'Verifier uses standard library')
    check(subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip() == 'feature/dsub9-dynamic-actuator-v1', 'Branch preserved')
    check(subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == 'd2e7e4fa4ed0631d9dd1b7b98a121c1e46ea6406', 'HEAD preserved')
    if args.seal:
        write_new(OUT / 'verification.json', dict(status='VERIFIED_OFFLINE_AUDITOR_REPAIR', user_date='2026-10-08',
            assertions=checks, revision_sha256=result['revision_sha256'], revision_inputs=20, inherited_inputs=2167,
            historical_members=950, prior_scope_members=old_members, production_inputs=1057,
            new_regression_tests=14, inherited_audit_tests=6, existing_archives_reaudited=10,
            actual_new=dict(engine_loads=0,initializations=0,dynamic_attempts=0,physical_substeps=0,
                learner_constructions=0,tensor_reads=0,network_forwards=0,optimizer_updates=0,replay_publications=0),
            cumulative_dynamic=209, automatic_tracking='PAUSED', full_B2_accepted=False, C_accepted=False,
            training_admitted=False, physical_runner_rebound=False))
        (OUT / 'git_status_after.txt').write_bytes(subprocess.check_output(['git', '-c', 'core.quotepath=false', 'status', '--short'], cwd=ROOT))
        members = {p.relative_to(OUT).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size)
                   for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
        write_new(OUT / 'delivery_manifest.json', dict(stage_id='B2-SCOPE-04', status='SEALED_OFFLINE_AUDITOR_REPAIR',
            files=members, cumulative_dynamic=209, training_admitted=False, physical_runner_rebound=False,
            rolling_documents='immutable snapshots; roots may advance'))
    manifest = read(OUT / 'delivery_manifest.json')
    for name, item in manifest['files'].items():
        check(sha(OUT / name) == item['sha256'] and (OUT / name).stat().st_size == item['bytes'], 'Current sealed member ' + name)
    print(json.dumps(dict(status='VERIFIED_OFFLINE_AUDITOR_REPAIR', assertions=checks, sealed_files=len(manifest['files']),
        manifest_sha256=sha(OUT / 'delivery_manifest.json'), regression_tests=20, existing_archives=10,
        new_simulation=0, new_training=0, cumulative_dynamic=209, physical_runner_rebound=False), ensure_ascii=False))

if __name__ == '__main__':
    main()
