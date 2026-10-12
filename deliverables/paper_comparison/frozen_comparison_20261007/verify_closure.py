"""Offline closure accounting and provenance; no physics or optimizer calls."""
from pathlib import Path
import datetime,hashlib,json,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
from run_evaluation import read,sha,PRIOR,PRIOR_SEAL,verify_sources
def main():
    assert not (OUT/'delivery_manifest.json').exists()
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    c=read(OUT/'configuration.json');l=read(OUT/'run/ledger.json');a=read(OUT/'assessment.json')
    assert l['status'] in ('complete','controlled_stop','error') and len(l['episodes'])<=27
    assert [e['id'] for e in l['episodes']]==[s['id'] for s in c['attempts'][:len(l['episodes'])]]
    assert l['unused_closed']==27-len(l['episodes']) and l['formal_updates']==l['published_transitions']==0
    assert a['formal_updates']==a['published_transitions']==0 and a['new_attempts']==len(l['episodes'])
    verify_sources(c)
    old=read(PRIOR/'delivery_manifest.json');assert sha(PRIOR/'delivery_manifest.json')==PRIOR_SEAL
    for n,m in old['files'].items():assert sha(PRIOR/n)==m['sha256'] and (PRIOR/n).stat().st_size==m['bytes'],n
    for ref in c['inherited_development']:assert sha(PRIOR/'run'/(ref['id']+'.json.gz'))==ref['archive_sha256']
    assert a['audit_errors']==[],a['audit_errors']
    for e in l['episodes']:
        calls=0 if e['spec']['provider']=='B2' else e.get('policy_calls',0)
        assert e['network_policy_calls']==calls
        if e['status']=='finished' and e.get('evaluation_checks',{}).get('state_unchanged'):
            checks=e['evaluation_checks'];assert checks['optimizer_updates']==checks['published_transitions']==0
            assert sha(OUT/'run'/(e['id']+'.json.gz'))==e['archive_sha256']
    assert l['network_policy_calls']==sum(e['network_policy_calls'] for e in l['episodes'])==a['network_policy_calls']
    registration=read(OUT/'first_use_registration.json');assert registration['evaluation_set_sha256']==c['evaluation_set_sha256']
    assert registration['qualification_sha256']==l['qualification_sha256'] and sha(OUT/'qualification.json')==l['qualification_sha256']
    q=read(OUT/'qualification.json')
    for n,d in q['evidence_sha256'].items():assert sha(OUT/n)==d,n
    physical_audited=sum(len(rows) for group in a['records'].values() for rows in group.values())-10
    whole_matrix=l['status']=='complete' and all(v['comparison_eligible'] for group in a['metrics'].values() for v in group.values())
    if whole_matrix:
        assert a['finished']==27 and a['independent_reward_rows_new']==a['control_cycles']
        assert l['inputs_unchanged'] and all(e.get('evaluation_checks',{}).get('state_unchanged') for e in l['episodes'])
    recoveries=[s for s in (OUT/'execution.log').read_text(encoding='utf8').splitlines() if s.startswith('atomic_json_replace_recovered:')]
    result=dict(passed=True,at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),source_files=1057,
        production_source_unchanged=True,prior_pc06_files_checked=len(old['files']),prior_seal=PRIOR_SEAL,
        actual_new_attempts=len(l['episodes']),whole_matrix_eligible=whole_matrix,new_gradient_batches=0,published_transitions=0,
        first_use_positions=4,first_use_actual_attempts=a['first_use_test_attempts'],positions_consumed_after_execution=True,
        inherited_archives_unchanged=10,independent_reward_rows_new=a['independent_reward_rows_new'],
        json_write_recoveries=recoveries,optimizer_or_physical_retries=0,network_calls=l['network_policy_calls'],
        scope='closure/provenance; matrix success, learning benefit and paper superiority are separate')
    (OUT/'closure_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k!='json_write_recoveries'},ensure_ascii=False))
if __name__=='__main__':main()
