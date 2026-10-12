"""Check closed runtime evidence and immutable archives; never execute physics."""
import argparse
import ast
import json
from pathlib import Path
import re
import subprocess
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
ENTRY=ROOT/'deliverables/learning_chain/b2_stratified_zero_baseline_entry_20261011'
sys.path.insert(0,str(ENTRY))
import baseline_entry
import scope_contract as c
from assess_results import require_closed,cost_summary,summarize

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seal',action='store_true');args=parser.parse_args()
    checks={}
    def check(name,value):
        checks[name]=bool(value)
        if not value:raise AssertionError(name)
    binding,config=c.verify_binding();before=c.read(OUT/'before_state.json')
    check('2379_bound_inputs_intact',len(binding['files'])==2379)
    check('55_original_entry_members_intact',len(before['entry_members'])==55 and all(c.sha(ENTRY/p)==pin for p,pin in before['entry_members'].items()))
    check('original_entry_seal_unchanged',c.sha(ENTRY/'delivery_manifest.json')==before['entry_delivery_manifest_sha256'])
    for folder,count in [(c.PREV,77),(c.SCOPE,29)]:
        pins=c.read(folder/'delivery_manifest.json')['files']
        check('previous_'+str(count)+'_seal_intact',len(pins)==count and all(c.sha(folder/p)==pin for p,pin in pins.items()))
    grant=c.read(OUT/'authorization_grant.json')
    c.require_grant(grant,c.sha(ENTRY/'source_binding.json'),before['run_id'])
    check('new_grant_bound_to_user_continue_and_exact_scope',c.sha(OUT/'authorization_grant.json')==before['grant_sha256'] and grant['explicit_user_authorized'] is True and '用户随后回复：继续' in grant['human_evidence'])
    check('old_request_preserved_draft',c.read(ENTRY/'authorization_request.json')['explicit_user_authorized'] is False)
    original=ENTRY/'execution';copy=OUT/'run'
    originals={str(p.relative_to(original)):c.sha(p) for p in original.rglob('*') if p.is_file()}
    copies={str(p.relative_to(copy)):c.sha(p) for p in copy.rglob('*') if p.is_file()}
    check('entire_closed_run_copied_exactly',originals==copies)
    ledger=c.read(copy/'ledger.json');closure=c.read(copy/'authorization_closure.json')
    require_closed(ledger,closure)
    check('closed_one_time_ledger_and_no_reusable_balance',ledger['new_budget_reusable'] is False and closure['no_retry'] is True and ledger['automatic_tracking']=='PAUSED')
    check('grant_run_and_matrix_identity',ledger['grant_sha256']==before['grant_sha256'] and ledger['run_id']==before['run_id'] and ledger['matrix_scope_key']==config['common_key'] and ledger['shared_common_key']==config['parent_common_key'])
    episodes=ledger['episodes']
    check('registered_order_no_duplicates_or_extra_attempts',[r['case_id'] for r in episodes]==[p['id'] for p in c.new_cases()[:len(episodes)]] and len(episodes)<=21)
    result=c.read(OUT/'assessment.json')
    check('first_assessment_and_csv_preserved',c.sha(OUT/'assessment.json')==c.sha(copy/'assessment.json') and c.sha(OUT/'comparison.csv')==c.sha(copy/'comparison.csv'))
    check('all_attempts_and_faults_retained',result['all_attempts']==episodes and result['new_attempts']==len(episodes) and all(r['case_id'] in [e['case_id'] for e in episodes] for r in result['incomplete_attempts']))
    check('cost_and_cumulative_recomputed',result['costs']==cost_summary(episodes) and result['cumulative_dynamic']==result['costs']['cumulative_dynamic'])
    check('cycle_substep_limits_and_zero_learning',all(c.check_receipt_costs(r) is None for r in episodes) and all(r.get('policy_calls',0)==r.get('formal_updates',0)==r.get('learner_constructions',0)==r.get('tensor_loads',0)==r.get('replay_publications',0)==0 for r in episodes))
    check('25_point_summary_recomputed',result['summary']==summarize(result['records'],[p['id'] for p in c.registered_cases()]))
    for group in ('aligned','position_only','orientation_only','joint'):
        check('stratum_'+group,result['strata'][group]==summarize([r for r in result['records'] if r['group']==group],[p['id'] for p in config['case_metadata'] if p['group']==group]))
    check('exact_four_legacy_aliases',[(r['case_id'],r['original_case_id']) for r in result['records'] if r['reused']]==[('J11','J01'),('J22','J02'),('J33','J03'),('J44','J04')])
    complete=result['summary']['complete_valid_stopped_matrix']
    if ledger['status']=='CLOSED_COMPLETE':
        proof=ledger['package_supervisor']
        check('owned_whole_package_exit_confirmed',proof['go_issued'] is True and proof['process_exit_confirmed'] is True and proof['owned_launcher_exit_confirmed'] is True and proof['returncode']==0 and not proof['deadline_hit'])
        check('21_real_initialization_and_workers_completed',len(episodes)==21 and all(c.receipt_healthy(r) and r['initial_audit']['passed'] is True for r in episodes))
        check('complete25_matrix_and_no_archive_faults',complete and len(result['records'])==25 and result['incomplete_attempts']==[])
        check('exact21_charged_resets_and_cumulative279',result['costs']['reset_attempts']==21 and result['costs']['environments_created_recorded']==21 and result['cumulative_dynamic']==279 and result['costs']['control_counts_complete'] is True)
    else:
        check('incomplete_scope_remains_explicit',not complete and result['summary']['mean_penalized_time_s'] is None)
    q=c.read(OUT/'case_qualification.json')
    check('nonzero_training_continuous_fullB2_C_not_admitted',not q['nonzero_SAC_qualified'] and not q['training_admitted'] and not q['continuous_scope_qualified'] and not q['full_B2_accepted'] and not q['C_accepted'] and result['independent_tests']==0)
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT)
    check('same_branch_and_HEAD',git('branch','--show-current').decode().strip()==before['branch'] and git('rev-parse','HEAD').decode().strip()==before['head'])
    prior=set((OUT/'git_status_before.bin').read_bytes().rstrip(b'\0').split(b'\0'))
    now=set(git('status','--porcelain=v1','-z').rstrip(b'\0').split(b'\0'))
    check('all_previous_uncommitted_entries_retained',len(prior)==before['uncommitted_entries'] and prior<=now)
    docs=before['documents']
    check('six_before_and_after_snapshots',len(docs)==6 and all(c.sha(OUT/'before_documents'/p)==pin and c.sha(OUT/'after_documents'/p)==c.sha(ROOT/p) for p,pin in docs.items()))
    check('AGENTS_unchanged',c.sha(ROOT/'AGENTS.md')==docs['AGENTS.md'])
    markers=[]
    for p in docs:
        if p=='AGENTS.md':continue
        text=(ROOT/p).read_text(encoding='utf-8')
        m=re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->',text,re.S).group(1)
        markers.append(m.replace('../../learning_chain/','deliverables/learning_chain/'))
    check('five_rolling_markers_consistent',len(set(markers))==1)
    check('current_stage_scope_reminder_correct',all(s in markers[0] for s in ['B.2第3项','纯B2','PAUSED','完整B.2/C未验收','强化学习','进入C之前']))
    month=(ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md').read_text(encoding='utf-8')
    headings=['## 一、本月综合摘要','## 二、关键数字与证据','## 三、负结果与限制','## 四、图表与讲稿','## 五、下一项','## 六、来源记录']
    check('five_monthly_sections_updated',all('本次' in month[month.index(a):month.index(b)] for a,b in zip(headings,headings[1:])))
    check('new_sources_parse',all(ast.parse(p.read_text(encoding='utf-8')) is not None for p in OUT.glob('*.py')))
    check('verification_did_not_import_science',not any(n.split('.')[0] in {'numpy','mujoco','torch','gymnasium','stable_baselines3'} for n in sys.modules))
    report=(OUT/'结果说明.md').read_text(encoding='utf-8')
    check('report_limitations_explicit','26/27' in report and '非零SAC' in report and '完整B.2/C' in report and '21' in report)
    verification=dict(status='PASS_CLOSED_BASELINE_DELIVERY' if complete else 'PASS_ARCHIVE_WITH_INCOMPLETE_BASELINE',verified_at=c.now(),checks=checks,
        actual_result_status=ledger['status'],new_attempts=len(episodes),cumulative_dynamic=result['cumulative_dynamic'],costs=result['costs'],
        summary=result['summary'],source_count=len(binding['files']),original_entry_members_preserved=55,new_physical_execution_during_verification=0,
        new_policy_calls=0,new_training_updates=0,automatic_tracking='PAUSED',full_B2_accepted=False,C_accepted=False,
        validation_scope='saved closed-run evidence and author document checks; not a second independent experiment')
    if args.seal:
        c.write(OUT/'verification.json',verification)
        with (OUT/'progress.md').open('a',encoding='utf-8') as stream:stream.write('\nTask4 complete: '+verification['status']+', '+str(len(checks))+' checks; final rolling documents and closed evidence sealed. Author verification only, no second independent experiment.\n')
        pins={str(p.relative_to(OUT)):c.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json'}
        c.write(OUT/'delivery_manifest.json',dict(version='b2_stratified_zero_actual_delivery_v1',sealed_at=c.now(),files=pins,
            scientific_execution_closed=True,training_admitted=False,full_B2_accepted=False,C_accepted=False))
    elif (OUT/'delivery_manifest.json').exists():
        pins=c.read(OUT/'delivery_manifest.json')['files'];check('new_delivery_seal_intact',all(c.sha(OUT/p)==pin for p,pin in pins.items()))
    print(c.canonical(dict(status=verification['status'],checks=len(checks),new_attempts=len(episodes),cumulative=result['cumulative_dynamic'],sealed=args.seal)))

if __name__=='__main__':main()
