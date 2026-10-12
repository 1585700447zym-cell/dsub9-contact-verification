"""Verify archived planning evidence. --seal writes only this new delivery."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
from audit_existing import ROOT, DOCS, audit, canonical, read, sha

PLAN = 'docs/superpowers/plans/2026-10-08-b2-pose-scope-preflight.md'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seal', action='store_true')
    parser.add_argument('--current-docs', action='store_true')
    args = parser.parse_args()
    if args.seal:
        assert not (OUT / 'delivery_manifest.json').exists(), 'Already sealed'
    checks = 0

    def check(condition, label):
        nonlocal checks
        if not condition:
            raise AssertionError(label)
        checks += 1

    old = read(OUT / 'existing_evidence.json')
    current = audit()
    check(current == old, 'Fresh source/raw evidence differs')
    check(old['sealed_members_verified'] == 950 and old['production_inputs_verified'] == 1057, 'Prior inputs')
    c = read(OUT / 'candidate.json')
    check(c['status'] == 'PREPARED_NOT_AUTHORIZED', 'Candidate status')
    check(not any(c[k] for k in ['runner_implemented', 'dynamic_authorized', 'static_authorized', 'training_admitted']), 'No admission')
    check(c['authorization'] is None and not any(c['actual_new'].values()), 'No new computation')
    check(c['cumulative_dynamic'] == 208 and c['automatic_tracking'] == 'PAUSED', 'Counters')
    check(len(c['cases']) == 8 and len(c['static_cases']) == 9 and len(c['attempts']) == 16, 'Matrix size')
    check(len({r['id'] for r in c['cases']}) == 8, 'Unique cases')
    expected = [('P01',0,0,.25,0,1), ('P02',0,0,-.25,0,-1), ('P03',0,0,0,.25,1), ('P04',0,0,0,-.25,-1),
                ('J01',75,75,.25,.25,1), ('J02',-75,75,-.25,.25,-1), ('J03',-75,-75,-.25,-.25,-1), ('J04',75,-75,.25,-.25,1)]
    for row, values in zip(c['cases'], expected):
        check(tuple(row[k] for k in ['id','x_um','y_um','roll_deg','pitch_deg','script_sign']) == values, 'Exact scenario')
        check(row['yaw_deg'] == 0 and row['start_origin_z_m'] == -.004 and row['target_depth_m'] == .004, 'Fixed origin')
    check([(r['case_id'],r['arm']) for r in c['attempts']] == [(r['id'],a) for r in c['cases'] for a in ['zero','script']], 'Fixed paired order')
    limits = c['proposed_limits']
    check(limits['static_initializations'] + limits['dynamic_attempts'] == limits['total_resets'] == 25, 'Reset count')
    check(16 * limits['physical_substeps_per_episode'] == limits['total_physical_substeps'] == 2320000, 'Substep ceiling')
    check(limits['total_supervised_wall_s'] == 21600 and limits['cumulative_dynamic_if_all_run'] == 224, 'Proposed ceilings')
    check(not any(limits[k] for k in ['learner_constructions','tensor_reads','network_forwards','optimizer_updates','replay_publications']), 'No learning proposal')
    fields = ['version','parent','scope','physical_rules','cases','static_cases','attempts','script','proposed_limits','stop_rules']
    check(hashlib.sha256(canonical({k:c[k] for k in fields})).hexdigest() == c['draft_scope_key'], 'Draft scope digest')
    check(c['parent']['configuration_sha256'] == old['common_config_sha256'], 'Parent binding')
    check(c['parent']['common_key'] == old['parent_common_key'] != c['draft_scope_key'], 'Scope distinct from parent')
    for name in DOCS:
        snap = OUT / 'document_snapshots' / name
        text = snap.read_text(encoding='utf-8')
        check(text.count('<!-- b2-scope-current -->') == 1 and '完整B.2/C未验收' in text, 'Scoped current status')
        check((OUT / 'before_documents' / name).exists(), 'Before snapshot')
        if args.current_docs:
            check(snap.read_bytes() == (ROOT / name).read_bytes(), 'Current document equality')
    plan = (OUT / 'document_snapshots' / PLAN).read_text(encoding='utf-8')
    check('- [x]' not in plan and '- [ ]' in plan, 'Unimplemented plan')
    if args.current_docs:
        check((ROOT / PLAN).read_bytes() == (OUT / 'document_snapshots' / PLAN).read_bytes(), 'Plan snapshot')
    for file in [OUT / '范围审计与最小预检方案.md', ROOT / PLAN]:
        for target in re.findall(r'\]\(([^)]+)\)', file.read_text(encoding='utf-8')):
            if not target.startswith(('https:', 'http:', '#')):
                check((file.parent / target.split('#')[0]).resolve().exists(), 'Link: ' + target)
    if args.seal:
        result = dict(status='PASSED_DOCUMENT_AND_ARCHIVE_CHECKS', checked_at_user_date='2026-10-08',
                      check_assertions=checks, prior_sealed_members=950, shared_inputs=1057,
                      raw_archives=63, current_documents_checked=args.current_docs,
                      actual_new=c['actual_new'], limitation='No new physical preflight or independent code review')
        with (OUT / 'verification.json').open('x', encoding='utf-8', newline='\n') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
        files = {p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
                 for p in sorted(OUT.rglob('*')) if p.is_file()}
        manifest = dict(status='SEALED_OFFLINE_SCOPE_PLAN', user_date='2026-10-08',
                        full_B2_accepted=False, C_accepted=False, dynamic_authorized=False,
                        training_admitted=False, cumulative_dynamic=208, automatic_tracking='PAUSED',
                        rolling_documents='immutable snapshots; roots may advance', files=files)
        with (OUT / 'delivery_manifest.json').open('x', encoding='utf-8', newline='\n') as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
            f.write('\n')
    manifest = read(OUT / 'delivery_manifest.json')
    check(manifest['status'] == 'SEALED_OFFLINE_SCOPE_PLAN', 'Archive status')
    for name, item in manifest['files'].items():
        check(sha(OUT / name) == item['sha256'] and (OUT / name).stat().st_size == item['bytes'], 'Member: ' + name)
    print(json.dumps(dict(status='VERIFIED_OFFLINE_SCOPE_PLAN', assertions=checks,
        sealed_files=len(manifest['files']), manifest_sha256=sha(OUT / 'delivery_manifest.json'),
        old_members=950, shared_inputs=1057, raw_pose_records=63,
        new_physics=0, new_learning=0, cumulative_dynamic=208), ensure_ascii=False))


if __name__ == '__main__':
    main()
