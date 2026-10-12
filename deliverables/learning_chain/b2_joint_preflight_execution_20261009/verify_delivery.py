"""Verify this actual run, costs, raw hashes, closure and snapshots; never simulate."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
RUNNER=OUT.parent/'b2_joint_admission_preflight_20261009'
sys.path.insert(0,str(RUNNER))
from scope_contract import read,sha,proposal,attempt_specs
from run_preflight import check_binding
from execution_contract import write,validate_grant
from coverage_checks import matrix_route

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seal',action='store_true');parser.add_argument('--current-docs',action='store_true')
    args=parser.parse_args();checks=0
    def check(condition,label):
        nonlocal checks
        if not condition:raise AssertionError(label)
        checks+=1
    if args.seal:check(not (OUT/'delivery_manifest.json').exists(),'new execution seal')
    reg=read(OUT/'registration.json');summary=read(OUT/'execution_summary.json');closure=read(OUT/'authorization_closure.json')
    for n,pin in reg['runner_pins'].items():check(sha(RUNNER/n)==pin,'frozen runner pin '+n)
    parent_members=read(RUNNER/'delivery_manifest.json')['files'];check(len(parent_members)==60,'SCOPE09 file count')
    for rel,meta in parent_members.items():check(sha(RUNNER/rel)==meta['sha256'],'SCOPE09 preserved '+rel)
    older=RUNNER.parent/'b2_joint_admission_design_20261009/verify_delivery.py'
    p=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(older)],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True)
    old=json.loads(p.stdout.strip().splitlines()[-1]);check(old['preserved_sealed_members']==1538 and old['sealed_files']==28,'old1566 files preserved')
    c,b=check_binding();grant=read(OUT/'grant.json')
    check(sha(OUT/'grant.json')==reg['grant_sha256']==closure['grant_sha256'],'new grant bytes')
    validate_grant(grant,reg['runner_pins']['candidate_binding.json'],c);checks+=1
    check(grant['human_message']=='继续' and grant['explicit_user_approval'],'human follow-up authorization')
    ledger=read(OUT/'run/ledger.json');attempts=ledger['attempts'];specs=attempt_specs(c);count=len(attempts)
    check(0<=count<=12 and ledger['dynamic_attempts']==count and ledger['static_attempts']==0,'fixed denominator and count')
    check([e['id'] for e in attempts]==[s['id'] for s in specs[:count]],'fixed prefix, no retries')
    check(ledger['status']!='OPEN' and all(e['status']!='running' for e in attempts),'closed execution')
    check(closure['unused_dynamic_closed']==12-count and closure['scope_consumed'] and closure['status']=='CLOSED_NO_RETRY','unused budget closed')
    check(len(closure['consumed_claim_directories'])<=count,'at most one physical claim per reserved attempt')
    check(summary['cumulative_after_reserved']==225+count and summary['reserved_dynamic']==count,'actual cumulative accounting')
    check(summary['outer_process_exit_confirmed'] and summary['outer_supervisor']['process_exit_confirmed'],'owned process tree exited')
    check(all(v==0 for v in summary['learning_costs'].values()),'no learning cost')
    check(summary['cost_totals'].get('case_environment_instances_attempted',0)<=12 and summary['cost_totals'].get('reset_attempts',0)<=12,'environment/reset ceilings')
    check(summary['recorded_counts']['control_cycles']<=174000 and summary['recorded_counts']['native_steps']<=1740000,'recorded physical ceilings')
    check(summary['cost_totals'].get('native_step_calls',0)<=1740000,'native call ceiling')
    check(ledger['control_cycles_reserved']==count*14500 and ledger['native_steps_reserved']==count*145000,'pre-reserved totals')
    check(summary['outer_supervisor']['wall_seconds']<=21615,'six-hour limit plus owned process termination grace')
    for row,e in zip(summary['rows'],attempts):
        check(row['id']==e['id'] and row['status']==e['status'],'attempt result identity')
        if 'raw_source' in row:check(sha(OUT/'run'/row['raw_source'])==row['raw_sha256'],'retained raw archive '+row['id'])
        if row['audit_passed']:
            receipt=read(OUT/'run'/(row['id']+'.audit.json'))
            check(receipt['binding_sha256']==reg['runner_pins']['candidate_binding.json'],'audit implementation pin')
            check(receipt['archive_sha256']==row['raw_sha256']==e['archive_sha256'],'audited raw hash')
            check(receipt['assessment']==row['assessment']==e['assessment'],'consistent worker/ledger/capture audit')
            check(row['assessment']['outcome']['physical_stopped'] is True,'audited physical stop independently proved')
        check(row.get('control_cycles',0)<=14500 and row.get('physical_substeps',0)<=145000,'per attempt counts')
    for name,meta in closure['evidence_copies'].items():
        check(sha(Path(name))==sha(OUT/meta['copy'])==meta['sha256'],'claim/supervisor preserved copy')
    route=read(OUT/'route_decision.json');check(not route['training_admitted'] and not route['full_B2_accepted'] and not route['C_accepted'],'no inflated qualification')
    check(route['audited_functional_successes']==sum(r.get('assessment',{}).get('functional_success') is True for r in summary['rows']),'functional count independent of coverage')
    check(route['audited_physical_stops']==sum(r.get('assessment',{}).get('outcome',{}).get('physical_stopped') is True for r in summary['rows']),'physical stop count')
    matrix=summary.get('matrix_assessment')
    if matrix:
        check(matrix==read(OUT/'run/assessment.json'),'retained final matrix')
        check(route['route']==matrix['route']==matrix_route(matrix['dynamic']),'route from frozen coverage rules')
        for row,matrix_row in zip(summary['rows'],matrix['dynamic']):
            check(row['id']==matrix_row['id'],'matrix fixed identity')
            if row['audit_passed']:
                check(all(matrix_row[k]==v for k,v in row['assessment'].items()),'final re-audit agrees with per-attempt audit')
    expected_gaps={(r['id'],int(h)) for r in summary['rows']
        for h,n in r.get('assessment',{}).get('joint_coverage',{}).get('hold_contact_effect_cycles',{}).items() if n==0}
    evidence=read(OUT/'coverage_gap_evidence.json')
    check(evidence['read_only'] and evidence['new_physics']==0,'offline gap provenance')
    check({(r['id'],g['hold_cycles']) for r in evidence['episodes'] for g in r['missing']}==expected_gaps,'all raw timing gaps represented')
    check({(g['id'],g['hold_cycles']) for g in route['timing_gaps']}==expected_gaps,'all route timing gaps represented')
    check(route['gap_classifications']==[dict(id=e['id'],hold_cycles=g['hold_cycles'],classification=g['evidence_classification'])
        for e in evidence['episodes'] for g in e['missing']],'route preserves gap classifications')
    by_id={r['id']:r for r in summary['rows']}
    for episode in evidence['episodes']:
        row=by_id[episode['id']]
        check(episode['archive_sha256']==row['raw_sha256'] and episode['control_cycles']==row['control_cycles'],'gap archive and denominator')
        for gap in episode['missing']:
            check(0<=gap['effective_contact_cycles']<=gap['permitted_contact_cycles']<=gap['contact_block_cycles']<=gap['block_cycles'],'gap count containment')
            check(gap['effective_contact_cycles']==0,'gap is uncovered')
            expected='NO_CONTACT_IN_FIXED_BLOCK' if gap['contact_block_cycles']==0 else 'CONTACT_MASKED_IN_FIXED_BLOCK' if gap['permitted_contact_cycles']==0 else 'NO_EFFECT_WITH_PERMISSION_IN_FIXED_BLOCK'
            check(gap['evidence_classification']==expected,'evidence classification')
    covered=[dict(id=r['id'],**r['assessment']['recovery']) for r in summary['rows']
        if r.get('assessment',{}).get('recovery',{}).get('covered')]
    check(route['recovery_covered']==covered,'recovery evidence retained')
    docs=read(OUT/'document_update.json')
    for name,pin in reg['before_documents'].items():
        check(sha(OUT/'before_documents'/name)==pin,'before snapshot')
        check(sha(OUT/'document_snapshots'/name)==docs['after_documents'][name],'after snapshot')
        if args.current_docs:check(sha(ROOT/name)==docs['after_documents'][name],'current document snapshot')
        if name!='AGENTS.md':
            text=(OUT/'document_snapshots'/name).read_text(encoding='utf-8');block=re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->',text,re.S).group(1)
            check(all(s in block for s in ['B2-SCOPE-10','当前阶段B.2','完整B.2/C未验收',str(225+count),'PAUSED']),'current scope/cost boundaries')
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf-8').strip()
    check(git('branch','--show-current')==reg['branch'] and git('rev-parse','HEAD')==reg['head'],'same branch/head')
    original=set((OUT/'git_status_before.txt').read_text(encoding='utf-8').splitlines())
    current=set(subprocess.check_output(['git','status','--porcelain=v1'],cwd=ROOT).decode('utf-8').splitlines())
    check(not original-current,'prior uncommitted entries preserved')
    for script in OUT.glob('*.py'):ast.parse(script.read_text(encoding='utf-8'));checks+=1
    check(not any(m.split('.')[0] in {'numpy','mujoco','torch','stable_baselines3'} for m in sys.modules),'closeout stdlib only')
    result=dict(stage_id='B2-SCOPE-10',status='VERIFIED_EXECUTION_RECORD_AND_CLOSURE',checks=checks,
        preserved_sealed_members=1626,bound_inputs=len(b['files']),dynamic_attempts=count,audited_attempts=summary['audited_attempts'],
        unused_dynamic_closed=12-count,cumulative_dynamic=225+count,route=route['route'],learning_costs=summary['learning_costs'],
        full_B2_accepted=False,C_accepted=False,training_admitted=False,automatic_tracking='PAUSED')
    if args.seal:
        write(OUT/'verification.json',result)
        files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc' and p.name!='delivery_manifest.json'}
        write(OUT/'delivery_manifest.json',dict(stage_id='B2-SCOPE-10',files=files,rolling_documents_may_advance=True))
    if (OUT/'delivery_manifest.json').exists():
        members=read(OUT/'delivery_manifest.json')['files']
        for rel,meta in members.items():check(sha(OUT/rel)==meta['sha256'] and (OUT/rel).stat().st_size==meta['bytes'],'sealed '+rel)
        result.update(checks=checks,sealed_files=len(members),manifest_sha256=sha(OUT/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
