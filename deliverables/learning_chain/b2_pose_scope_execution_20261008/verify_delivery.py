"""Verify and optionally seal this closed execution; never imports an engine."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'deliverables/learning_chain/b2_pose_scope_preflight_20261008'
sys.path.insert(0, str(SOURCE))
from scope_contract import sha, read
from run_preflight import check_binding, BINDING

DOCS = ['项目当前入口.md', '项目进度跟踪.md', '项目交付总览.md', '研究推进计划_当前版.md',
        'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
PLAN = 'docs/superpowers/plans/2026-10-08-b2-pose-scope-preflight.md'
LEDGER = '.superpowers/sdd/2026-10-08-b2-pose-scope-preflight/progress.md'

def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seal', action='store_true')
    parser.add_argument('--current-docs', action='store_true')
    args = parser.parse_args()
    if args.seal:
        assert not (OUT / 'delivery_manifest.json').exists()
    _, binding = check_binding()
    checks = 0
    def check(value, label):
        nonlocal checks
        if not value:
            raise AssertionError(label)
        checks += 1
    check(sha(BINDING) == '9c15895cf6c8bac905715275c65dead6a8a48be617a3c197839077c7acf673c6', 'Unchanged implementation binding')
    old_members = 0
    for name, pin, count in [
        ('b2_scope_audit_20261008', 'f0ece40fc2fc3ab83b99506bb13a59158dc0282fe674dbaf03b3f5b7e47e0576', 19),
        ('b2_pose_scope_preflight_20261008', '178bf8cab98360b75148b4a587838e1a3493a4739576e4b713ef08a30f00a693', 63)]:
        folder = OUT.parent / name
        check(sha(folder / 'delivery_manifest.json') == pin, 'Old manifest ' + name)
        manifest = read(folder / 'delivery_manifest.json')
        check(len(manifest['files']) == count, 'Old count ' + name)
        for rel, item in manifest['files'].items():
            check(sha(folder / rel) == item['sha256'] and (folder / rel).stat().st_size == item['bytes'], 'Old member ' + rel)
            old_members += 1
    prior = read(OUT / 'prior_verification.json')
    check(prior['exit_code'] == 0 and prior['result']['old_members'] == 950 and prior['result']['shared_inputs'] == 1057,
          'Completed separate historical source verification')
    check(prior['result']['raw_pose_records'] == 63, 'Historical pose audit')
    closure = read(OUT / 'authorization_closure.json')
    grant = read(OUT / 'grant.json')
    ledger = read(OUT / 'run/ledger.json')
    assessment = read(OUT / 'run/assessment.json')
    diagnosis = read(OUT / 'audit_diagnosis.json')
    check(grant['explicit_user_approval'] is True and grant['version'] == 'b2_pose_scope_grant_v1', 'Explicit authorization')
    check(sha(OUT / 'grant.json') == closure['grant_sha256'] == sha(OUT / 'run/grant.json'), 'Grant bytes')
    check(ledger['status'] == closure['original_ledger_status'] == 'CLOSED_SUPERVISOR_ERROR', 'Closed original run')
    check(sha(OUT / 'run/ledger.json') == closure['original_ledger_sha256'] == diagnosis['original_ledger_sha256'], 'Original ledger preserved')
    check(closure['status'] == 'CLOSED_AUDIT_ERROR' and closure['retry_allowed'] is False, 'Failure retained')
    check((ledger['static_attempts'], ledger['dynamic_attempts'], ledger['unused_static_closed'], ledger['unused_dynamic_closed']) == (9, 1, 0, 15), 'Original budget accounting')
    check(closure['cumulative_dynamic_after'] == 209 and closure['actual']['physical_substeps'] == 30450, 'Reconciled actual counts')
    check(closure['actual']['control_cycles'] == 3045 and closure['actual']['resets'] == 10, 'Cycle/reset counts')
    check(all(closure['actual'][k] == 0 for k in ('learner_constructions', 'tensor_reads', 'network_forwards', 'optimizer_updates', 'replay_publications')), 'No learning costs')
    check(closure['full_B2_accepted'] is False and closure['C_accepted'] is False and closure['training_admitted'] is False, 'Scope not qualified')
    check(closure['automatic_tracking'] == 'PAUSED' and not closure['old_budgets_reopened'], 'Closed scope boundary')
    check(assessment['route'] == 'NO_SCOPE_QUALIFICATION' and len(assessment['dynamic']) == 16, 'Fixed dynamic denominator')
    check(sum(r['audit_passed'] for r in assessment['static']) == 9 and not any(r['audit_passed'] for r in assessment['dynamic']), 'Original acceptance status')
    check(sum(r['status'] == 'NOT_ATTEMPTED' for r in assessment['dynamic']) == 15, 'Unrun points preserved')
    check(diagnosis['reward_rows_verified'] == 3045 and diagnosis['reward_mismatch_rows'] == [], 'Numerical rewards')
    check(len(diagnosis['equal_numeric_counterexamples']) == 3 and len(diagnosis['negative_controls']) == 4, 'Diagnostic controls')
    check(diagnosis['counterfactual']['status'] == 'DIAGNOSTIC_AUDIT_PASSED_AFTER_SCALAR_TYPE_NORMALIZATION', 'Diagnostic hypothesis')
    check(diagnosis['diagnostic_only'] and not diagnosis['sealed_runner_modified'] and not diagnosis['ledger_modified'], 'No retrospective repair')
    check(diagnosis['loaded_forbidden'] == [], 'Offline diagnosis imports')
    for name, pin in diagnosis['source_sha256'].items():
        check(sha(SOURCE / name) == pin, 'Unmodified diagnostic source ' + name)
    for row in closure['actual_attempts']:
        check(sha(OUT / 'run' / (row['id'] + '.json.gz')) == row['archive_sha256'], 'Raw archive ' + row['id'])
        check(read(OUT / 'run' / (row['id'] + '.supervisor.json'))['process_exit_confirmed'], 'Owned process exit ' + row['id'])
    for original, copy in closure['evidence_copies'].items():
        check(sha(Path(original)) == sha(OUT / copy['copy']) == copy['sha256'], 'Supervisor evidence snapshot')
    check(sha(OUT / 'run/P01_zero.json.gz') == diagnosis['original_archive_sha256'], 'Diagnosed archive unchanged')
    receipt = read(OUT / 'authorization_receipt.json')
    for name in DOCS + [PLAN, LEDGER]:
        before = OUT / 'before_documents' / name
        after = OUT / 'document_snapshots' / name
        check(before.is_file() and after.is_file(), 'Document snapshots ' + name)
        if name in receipt['before_documents']:
            check(sha(before) == receipt['before_documents'][name], 'Before snapshot unchanged')
        if args.current_docs:
            check((ROOT / name).read_bytes() == after.read_bytes(), 'Current document ' + name)
        if name in DOCS:
            text = after.read_text(encoding='utf-8')
            block = re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->', text, re.S).group(1)
            check('B2-SCOPE-03' in block and '累计动态209' in block and '完整B.2/C未验收' in block and '15' in block, 'Current evidence scope')
    for name in ('结果说明.md', '路线决定.md'):
        file = OUT / name
        for link in re.findall(r'\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
            target = (file.parent / link.split('#')[0]).resolve()
            check(target.exists() or (args.seal and target == OUT / 'verification.json'), 'Report link ' + link)
    for path in OUT.glob('*.py'):
        ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
        checks += 1
    check(not any(k.split('.')[0] in {'mujoco', 'torch', 'numpy', 'stable_baselines3'} for k in sys.modules), 'No numerical runtime in verifier')
    branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    check(branch == receipt['branch'] and head == receipt['head'], 'Branch and HEAD unchanged')
    if args.seal:
        result = dict(status='VERIFIED_CLOSED_EXECUTION_AND_DIAGNOSIS', user_date='2026-10-08', assertions=checks,
            bound_files_verified=len(binding['files']), old_scope_members_verified=old_members,
            historical_recheck=prior, actual=closure['actual'], cumulative_dynamic=209,
            unused_dynamic_closed=15, diagnostic_only=True, dynamic_scope_accepted=False,
            full_B2_accepted=False, C_accepted=False, training_admitted=False, automatic_tracking='PAUSED')
        write_new(OUT / 'verification.json', result)
        (OUT / 'git_status_after.txt').write_bytes(subprocess.check_output(['git', '-c', 'core.quotepath=false', 'status', '--short'], cwd=ROOT))
        members = {p.relative_to(OUT).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size)
                   for p in sorted(OUT.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc'}
        write_new(OUT / 'delivery_manifest.json', dict(status='SEALED_CLOSED_AUDIT_ERROR', user_date='2026-10-08',
            stage_id='B2-SCOPE-03', files=members, cumulative_dynamic=209, training_admitted=False,
            dynamic_scope_accepted=False, rolling_documents='immutable snapshots; roots may advance'))
    manifest = read(OUT / 'delivery_manifest.json')
    for rel, item in manifest['files'].items():
        check(sha(OUT / rel) == item['sha256'] and (OUT / rel).stat().st_size == item['bytes'], 'New sealed member ' + rel)
    print(json.dumps(dict(status='VERIFIED_CLOSED_EXECUTION_AND_DIAGNOSIS', assertions=checks,
        bound_files=len(binding['files']), sealed_files=len(manifest['files']),
        manifest_sha256=sha(OUT / 'delivery_manifest.json'), cumulative_dynamic=209,
        static_passed=9, dynamic_attempts=1, unused_dynamic_closed=15, training_admitted=False), ensure_ascii=False))

if __name__ == '__main__':
    main()
