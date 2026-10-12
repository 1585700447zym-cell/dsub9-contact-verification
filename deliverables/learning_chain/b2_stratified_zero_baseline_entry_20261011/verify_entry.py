"""Verify and optionally seal offline entry delivery. Never launches science."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import baseline_entry
import scope_contract as c


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seal',action='store_true');args=parser.parse_args()
    binding,config=c.verify_binding();checks={}
    def check(name,value):
        checks[name]=bool(value)
        if not value:raise AssertionError(name)
    check('all_bound_inputs_and_runtime_verified',len(binding['files'])>=2376)
    check('25_registry_21_new_and_four_reuse',len(c.registered_cases())==25 and len(c.new_cases())==21)
    check('exact_shared_and_distinct_scope_keys',config['common_key']!=config['legacy_four_point_comparison_key'] and config['parent_common_key']==c.digest(config['common']))
    before=c.read(OUT/'before_state.json')
    for directory,count in [(c.SCOPE,29),(c.PREV,77)]:
        seal=c.read(directory/'delivery_manifest.json')
        check('old_seal_'+str(count),len(seal['files'])==count and all(c.sha(directory/p)==pin for p,pin in seal['files'].items()))
    check('200_shared_sources_unchanged',len(before['runtime_sources'])==200 and all(c.sha(c.ROOT/p)==pin for p,pin in before['runtime_sources'].items()))
    git=lambda *a:subprocess.check_output(['git',*a],cwd=c.ROOT)
    check('same_branch_and_head',git('branch','--show-current').decode().strip()==before['branch'] and git('rev-parse','HEAD').decode().strip()==before['head'])
    prior=set((OUT/'git_status_before.bin').read_bytes().rstrip(b'\0').split(b'\0'))
    current=set(git('status','--porcelain=v1','-z').rstrip(b'\0').split(b'\0'))
    check('all226_prior_uncommitted_entries_retained',len(prior)==226 and prior<=current)
    request=c.read(OUT/'authorization_request.json')
    check('grant_stays_draft_false_and_fixed_limits',request==c.grant_template(c.sha(OUT/'source_binding.json'),'pending-new-run-id'))
    check('no_actual_execution_or_scientific_imports',not (OUT/'execution').exists() and not any(n.split('.')[0] in {'numpy','mujoco','torch','gymnasium','stable_baselines3'} for n in sys.modules))
    check('all_entry_sources_parse',all(ast.parse(p.read_text(encoding='utf-8')) is not None for p in OUT.glob('*.py')))
    full=(OUT/'tests_full_final.log').read_text(encoding='utf-8')
    match=re.search(r'Ran (\d+) tests',full)
    check('fresh_new_full_suite_green',match is not None and int(match.group(1))>=40 and '\nOK' in full and 'FAILED (' not in full)
    old=(OUT/'tests_existing_regression.log').read_text(encoding='utf-8')
    check('historical26pass_1_known_time_state_failure_recorded','Ran 27 tests' in old and 'FAILED (failures=1)' in old and 'test_unauthorized_CLI_rejects_before_any_scientific_import' in old and "assertFalse((OUT / 'execution').exists())" in old)
    review=c.read(OUT/'review_resolution.json')
    check('fresh_review_and_substantive_findings_addressed',review['fresh_review_completed'] is True and review['unresolved_critical_important']==[])
    docs=before['documents']
    check('six_before_and_after_snapshots',len(docs)==6 and all(c.sha(OUT/'before_documents'/p)==pin and c.sha(OUT/'after_documents'/p)==c.sha(c.ROOT/p) for p,pin in docs.items()))
    check('AGENTS_unchanged',c.sha(c.ROOT/'AGENTS.md')==docs['AGENTS.md'])
    markers=[]
    for name in docs:
        if name=='AGENTS.md':continue
        text=(c.ROOT/name).read_text(encoding='utf-8')
        marker=re.search(r'<!-- b2-scope-current -->(.*?)<!-- /b2-scope-current -->',text,re.S).group(1)
        markers.append(marker.replace('../../learning_chain/','deliverables/learning_chain/'))
    check('five_current_markers_consistent',len(set(markers))==1)
    check('stage_scope_next_and_reminder_correct',all(s in markers[0] for s in ['B.2第3项','21点纯B2','离线','累计动态258','PAUSED','完整B.2/C未验收','进入C之前','强化学习']))
    monthly=(c.ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md').read_text(encoding='utf-8')
    headings=['## 一、本月综合摘要','## 二、关键数字与证据','## 三、负结果与限制','## 四、图表与讲稿','## 五、下一项','## 六、来源记录']
    check('monthly_five_sections_integrated',all('21' in monthly[monthly.index(a):monthly.index(b)] for a,b in zip(headings,headings[1:])))
    report=(OUT/'结果说明.md').read_text(encoding='utf-8')
    check('report_historical_failure_and_pending_physics_explicit','26/27' in report and '真实21次物理评价未执行' in report)
    check('code_plan_snapshot_saved',(OUT/'入口实现计划快照.md').read_bytes()==(c.ROOT/'docs/superpowers/plans/2026-10-11-b2-stratified-zero-baseline-entry.md').read_bytes())
    result=dict(status='PASS_OFFLINE_ENTRY_ONLY',verified_at=c.now(),checks=checks,source_count=len(binding['files']),
        new_unit_tests=int(match.group(1)),historical_pass=26,historical_failures=[dict(name='test_unauthorized_CLI_rejects_before_any_scientific_import',
            reason='old execution-directory absence assumption after previous authorized four-case execution',classification='preserved_historical_time_state_assumption')],
        new_physical_episodes=0,new_models=0,new_policy_calls=0,new_tensors=0,new_formal_updates=0,new_replay_publications=0,
        cumulative_dynamic=258,automatic_tracking='PAUSED',independent_tests=0,full_B2_accepted=False,C_accepted=False,
        source_binding_sha256=c.sha(OUT/'source_binding.json'),native_limit='real nested Windows job/initialization/stop validation pending new21 package')
    if args.seal:
        c.write(OUT/'verification.json',result)
        qualification=c.read(OUT/'qualification_candidate.json')
        qualification.update(status='OFFLINE_ENTRY_VERIFIED_PHYSICAL_EXECUTION_PENDING',offline_checks_passed=True,fresh_review_completed=True,
            verification_sha256=c.sha(OUT/'verification.json'),review_resolution_sha256=c.sha(OUT/'review_resolution.json'))
        c.write(OUT/'qualification_candidate.json',qualification)
        files={str(p.relative_to(OUT)):c.sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json'}
        c.write(OUT/'delivery_manifest.json',dict(version='b2_stratified_zero_offline_entry_delivery_v1',sealed_at=c.now(),files=files,
            source_binding_sha256=c.sha(OUT/'source_binding.json'),scientific_execution_admitted=False,training_admitted=False,full_B2_accepted=False,C_accepted=False))
    elif (OUT/'delivery_manifest.json').exists():
        check('new_delivery_seal_intact',all(c.sha(OUT/p)==pin for p,pin in c.read(OUT/'delivery_manifest.json')['files'].items()))
    print(c.canonical(dict(status=result['status'],checks=len(checks),unit_tests=result['new_unit_tests'],sources=result['source_count'],
        science=0,cumulative=258,seal_written=args.seal)))


if __name__=='__main__':main()
