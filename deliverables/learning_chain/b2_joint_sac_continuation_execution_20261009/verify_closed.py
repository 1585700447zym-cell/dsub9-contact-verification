"""Read-only stdlib audit of actual continuation; never reload tensors or models."""
import argparse,ast,gzip,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
KIT=HERE.parent/'b2_joint_sac_continuation_preparation_20261009';sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha,digest,LIMITS,schedule,metric
from execution import verify_grant,verify_sources,verify_code,COST_KEYS,Counter,PHYSICAL_FIELDS

def main():
    p=argparse.ArgumentParser();p.add_argument('--runtime-only',action='store_true');p.add_argument('--seal',action='store_true');p.add_argument('--current-docs',action='store_true');a=p.parse_args()
    if a.seal and (a.runtime_only or (HERE/'delivery_manifest.json').exists()):raise FileExistsError('Never reseal or seal a partial audit')
    checks=0
    def check(ok,label):
        nonlocal checks
        if not ok:raise AssertionError(label)
        checks+=1
    reg=read(HERE/'launch_registration/registration.json')
    check(sha(KIT/'delivery_manifest.json')==reg['preparation_manifest_sha256'],'approved frozen candidate seal')
    # The sealed SCOPE19 checker asserted no future claim even after preparation.
    # Preserve that historical checker; audit its immutable members and this run's
    # current claim independently instead of altering the frozen assertion.
    previous=HERE.parent/'b2_warm_restore_execution_20261009'
    proc=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(previous/'verify_closed.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf8',check=True)
    earlier=json.loads(proc.stdout.strip().splitlines()[-1])
    check(earlier['old_sealed_members_preserved']+earlier['sealed_files']==3491,'3491 earlier sealed members preserved')
    members=read(KIT/'delivery_manifest.json')['files']
    for name,record in members.items():check(sha(KIT/name)==record['sha256'] and (KIT/name).stat().st_size==record['bytes'],'frozen preparation member '+name)
    check(len(members)==55,'55 sealed SCOPE19 members preserved')
    binding=read(KIT/'source_binding.json');verify_sources(binding);checks+=len(binding['files'])+len(binding['inventories'])
    check(len(binding['files'])==2655,'all approved source bindings preserved')
    prior=dict(earlier_execution=earlier,old_sealed_members_preserved=3546,bound_inputs=2655,
               preparation_members=len(members),post_execution_checker='immutable preparation members plus current claim and closed run')
    candidate=read(KIT/'candidate.json');grant=read(HERE/'grant.json');pin=read(HERE/'grant_pin.json')['sha256']
    verify_code(candidate);checks+=len(candidate['code_sha256'])
    check(digest(candidate)==reg['candidate_sha256'],'registered candidate identity')
    check(digest(grant)==pin==reg['grant_sha256']==digest(read(HERE/'launch_registration/grant.json')),'one approved new grant')
    verify_grant(candidate,grant,pin,sha(KIT/'source_binding.json'));checks+=1
    check(read(KIT/'future_claims/consumed.json')==dict(grant_sha256=pin,output=str(HERE.resolve())),'unique consumed claim')
    counter=read(HERE/'counter.json');closure=read(HERE/'authorization_closure.json');supervisor=read(HERE/'supervisor.supervisor.json')
    expected={k:LIMITS[k] for k in COST_KEYS}
    check(counter['limits']==expected,'exact attempted-cost caps')
    check(all(type(counter['attempted'][k]) is int and 0<=counter['attempted'][k]<=expected[k] for k in expected),'no cost overrun')
    check(counter['status']=='CLOSED' and counter['unused_closed']=={k:v-counter['attempted'][k] for k,v in expected.items()},'all unused balance closed')
    check(closure['counter_closed'] and closure['unused_closed'] and closure['no_retry'],'durable once-only closure')
    check(closure['counter_error'] is None and closure['receipt_error'] is None,'closure without administrative errors')
    check(closure['process_exit_confirmed'] and supervisor['process_exit_confirmed'] and supervisor['owned_launcher_exit_confirmed'],'owned process tree exited')
    check(closure['automatic_tracking']=='PAUSED' and closure['training_admitted'] is False and closure['cumulative_before']==245,'scope closed without ongoing admission')
    try:Counter(HERE/'counter.json').checked()
    except PermissionError as exc:check('Closed continuation authorization' in str(exc),'closed capability refuses further operations')
    else:raise AssertionError('Closed grant still usable')
    check(not (HERE/'counter.lock').exists(),'no lingering counter lock')
    launch=read(HERE/'launch_registration/launcher_result.json');check(launch['no_retry'],'outer launcher never retried')
    ledger=read(HERE/'run/ledger.json');success=closure['status']=='CLOSED_COMPLETE'
    check(closure['status'] in ('CLOSED_COMPLETE','CLOSED_ERROR'),'known terminal status')
    warm_verified=False
    for label in ('warm','final'):
        receipt_path=HERE/'run'/(label+'.supervisor.json')
        if receipt_path.exists():
            receipt=read(receipt_path)
            check(receipt['process_exit_confirmed'] and receipt['owned_launcher_exit_confirmed'],'reader exited '+label)
        else:check(not success,'success requires reader receipt '+label);continue
        if receipt['returncode']==0:
            request=read(HERE/'run'/(label+'.request.json'));reply=read(HERE/'run'/(label+'.reply.json'))
            check(request['state_digest']==reply['state_digest'] and len(reply['state_digest'])==64,'complete live runtime state digest '+label)
            checkpoint=HERE/'run/checkpoints'/label;manifest=read(checkpoint/'manifest.json')
            check(sha(checkpoint/'manifest.json')==request['checkpoint_pin'],'reader checkpoint manifest '+label)
            check(sha(checkpoint/'state.pt')==manifest['state_sha256'] and manifest['version']=='v4_checkpoint_manifest_v1','checkpoint bytes '+label)
            check(receipt['go_issued'] and not receipt['deadline_hit'] and 0<receipt['wall_seconds']<LIMITS['reader_wall_s'],'reader success within cap '+label)
            if label=='warm':warm_verified=True
        else:check(not success,'reader failure cannot qualify '+label)
    completed_updates=0
    progress=HERE/'run/chain/update_attempt.json'
    if progress.exists():completed_updates=read(progress)['completed']
    journal=HERE/'run/chain/update_journal.jsonl'
    completions=[]
    if journal.exists():
        records=[json.loads(line) for line in journal.read_text(encoding='utf8').splitlines()]
        completions=[r for r in records if r['event']=='complete']
        completed_updates=len(completions)
        if completions:check(completions[-1]['counts']['critic']==completed_updates,'completed update history count')
    episodes=ledger['episodes'];completed=[e for e in episodes if e.get('status')=='finished']
    check(len(episodes)<=9 and [e['id'] for e in episodes]==[s['id'] for s in schedule()[:len(episodes)]],'all registered attempts kept in order')
    if success:
        check(launch['returncode']==supervisor['returncode']==0 and not supervisor['deadline_hit'],'successful outer and owned supervisor')
        check(counter['attempted']==expected,'successful path consumes exact registered caps')
        check(ledger['status']=='CLOSED_COMPLETE' and ledger['training_admitted'] is False and ledger['warm_state_restore_verified'] is True and warm_verified,'actual trainable startup gate passed')
        check(len(episodes)==len(completed)==9 and all(e['healthy'] is True for e in episodes),'nine completed valid physical episodes')
        check(completed_updates==2000 and ledger['formal_updates']=={k:2000 for k in ('actor','critic','temperature','target')},'2000 actual completed updates across all four components')
        expected_events=[(event,i) for i in range(1,2001) for event in ('attempt','complete')]
        check([(r['event'],r['attempt']) for r in records]==expected_events,'all 2000 attempts and completions in exact order; no update errors')
        check(all(r['counts']=={k:i for k in ('actor','critic','temperature','target')} for i,r in enumerate(completions,1)),'all four optimizer component counts at every completed update')
        check(counter['workers']==['parent:main','reader:warm','reader:final'],'exact worker sequence')
        assessment=read(HERE/'assessment.json');scores={};actual_cycles=actual_substeps=actual_calls=0
        for spec,e in zip(schedule(),episodes):
            path=HERE/'run'/(spec['id']+'.json.gz');check(sha(path)==e['archive_sha256'],'physical archive '+spec['id'])
            raw=json.loads(gzip.decompress(path.read_bytes()));out=raw['outcome']
            check(raw['episode_id']==spec['id'] and raw['optimizer_steps']==spec['optimizer_steps'] and raw['qualification_sha256']==pin,'new physical binding and optimizer boundary '+spec['id'])
            check(out['simulation_valid'] is True and out['physical_stopped'] is True and not any(out['guard_violations'].values()),'valid stopped unguarded '+spec['id'])
            actual_cycles+=raw['control_cycles'];actual_substeps+=raw['physical_substeps'];actual_calls+=raw['policy_calls']
            if spec['stage']=='final':scores[raw['case_id']]=dict(case_id=raw['case_id'],simulation_valid=out['simulation_valid'],physical_stopped=out['physical_stopped'],task_outcome=out['task_outcome'],task_time_s=raw['task_end_time_s'],guard=any(out['guard_violations'].values()),peaks=raw['peaks'])
        from continuation_contract import baseline_rows
        zero=baseline_rows();final=[scores['J0'+str(i)] for i in range(1,5)]
        for stage,rows in (('zero',zero),('final',final)):check(assessment['scores'][stage]==dict(rows=rows,metric=metric(rows)),'matched metric '+stage)
        f0=metric(zero);f2=metric(final);improvement=1-f2['mean_penalized_time_s']/f0['mean_penalized_time_s']
        check(abs(assessment['relative_improvement']-improvement)<1e-12,'registered relative improvement')
        check(assessment['development_continue']==(improvement>=.10 and f2['success_count']==4 and not f2['guards']),'unchanged development continue threshold')
        check(assessment['restore_exact'] and assessment['baseline_inherited'] and assessment['independent_tests']==0 and not assessment['full_B2_accepted'] and not assessment['C_accepted'],'development evidence boundary')
        parent=json.loads(gzip.decompress((HERE/'run/final_F50_J01.json.gz').read_bytes()))
        child=json.loads(gzip.decompress((HERE/'run/restore_F50_J01.json.gz').read_bytes()))
        for key in PHYSICAL_FIELDS:check(parent[key]==child[key],'exact restored physical '+key)
        check(actual_cycles<=expected['control_cycles'] and actual_substeps<=expected['native_steps'] and actual_calls==ledger['policy_calls']<=expected['policy_calls'],'actual costs below reservations')
        summary=read(HERE/'execution_summary.json')
        check(summary['scores']==assessment['scores'] and abs(summary['relative_improvement']-improvement)<1e-12 and summary['development_continue']==assessment['development_continue'],'closeout summary matches independently reconstructed metrics')
        check(summary['completed_physical']==9 and summary['completed_updates']==2000 and summary['optimizer_counts']==ledger['formal_updates'] and summary['update_attempts']==2000 and not summary['update_errors'],'closeout summary actual completions')
        check(summary['actual_control_cycles']==actual_cycles and summary['actual_native_steps']==actual_substeps and summary['actual_policy_calls']==actual_calls and summary['reserved_operations']==counter['attempted'],'closeout summary measured and reserved costs distinguished')
        cumulative=254;development_continue=assessment['development_continue']
    else:
        check(launch['returncode']!=0,'failed run recorded, including post-worker closeout errors')
        check(completed_updates<=counter['attempted']['formal_updates'],'completed updates do not exceed reserved blocks')
        cumulative=245+counter['attempted']['dynamic_episodes'];development_continue=False
        actual_cycles=sum(e.get('control_cycles',0) for e in episodes);actual_substeps=sum(e.get('physical_substeps',0) for e in episodes);actual_calls=ledger.get('policy_calls',0)
    check(closure['cumulative_upper_bound']==245+counter['attempted']['dynamic_episodes'],'cumulative attempted upper bound')
    for name,pin in reg['before_documents'].items():check(sha(HERE/'launch_registration/before_documents'/name)==pin,'before snapshot '+name)
    if not a.runtime_only:
        review=read(HERE/'review_resolution.json');check(review['status']=='RESOLVED' and review['open_critical']==review['open_important']==0,'execution review resolved')
        proposal=read(HERE/'document_proposal.json')
        check(sha(HERE/'document_proposal.json')==review['reviewed_document_proposal_sha256'] and sha(HERE/'结果说明.md')==proposal['report_sha256']==review['reviewed_report_sha256'] and sha(HERE/'publish_delivery.py')==proposal['publisher_sha256']==review['reviewed_publisher_sha256'],'exact independently reviewed publication artifacts')
        docs=read(HERE/'document_update.json')
        check(docs['authorization_status']=='CLOSED' and docs['next_task_started'] is False,'publication did not start next scientific task')
        check(docs['before_documents']==proposal['before_documents'],'publication concurrent-edit baseline')
        for name in reg['before_documents']:
            check(sha(HERE/'document_snapshots'/name)==docs['after_documents'][name],'after snapshot '+name)
            if name!='AGENTS.md':check(docs['after_documents'][name]==proposal['proposed_documents'][name]==sha(HERE/'document_proposals'/name),'published exact reviewed proposal '+name)
            else:check(docs['after_documents'][name]==reg['before_documents'][name],'AGENTS preserved unchanged')
            if a.current_docs:check(sha(ROOT/name)==docs['after_documents'][name],'current document '+name)
    git=lambda *x:subprocess.check_output(['git',*x],cwd=ROOT).decode('utf8')
    check(git('branch','--show-current').strip()==reg['branch'] and git('rev-parse','HEAD').strip()==reg['head'],'same branch and HEAD')
    before=set((HERE/'launch_registration/git_status_before.txt').read_text(encoding='utf8').splitlines());after=set(git('status','--porcelain=v1').splitlines());check(not before-after,'old dirty entries preserved')
    for path in HERE.glob('*.py'):ast.parse(path.read_text(encoding='utf8'));checks+=1
    check(not any(k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3','gymnasium') for k in sys.modules),'no scientific work during audit')
    result=dict(stage_id='B2-SCOPE-20',status='VERIFIED_EXECUTION_CLOSEOUT',checks=checks,execution_status=closure['status'],
                reserved_or_attempted_operations=counter['attempted'],warm_trainable_restore_verified=warm_verified,completed_formal_updates=completed_updates,
                registered_physical_attempts=len(episodes),completed_physical_episodes=len(completed),actual_cycles=actual_cycles,actual_substeps=actual_substeps,actual_policy_calls=actual_calls,
                development_continue=development_continue,cumulative_dynamic_or_attempt_upper_bound=cumulative,automatic_tracking='PAUSED',no_retry=True,
                old_sealed_members_preserved=3546,bound_inputs_preserved=2655,full_B2_accepted=False,C_accepted=False,independent_tests=0,
                supervisor_wall_s=supervisor['wall_seconds'])
    if a.seal:
        write(HERE/'prior_verification.json',prior);write(HERE/'verification.json',result);(HERE/'git_status_after.txt').write_text(git('status','--porcelain=v1'),encoding='utf8')
        files={p.relative_to(HERE).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(HERE.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts}
        write(HERE/'delivery_manifest.json',dict(stage_id='B2-SCOPE-20',files=files,rolling_documents_may_advance=True))
    if (HERE/'delivery_manifest.json').exists():
        members=read(HERE/'delivery_manifest.json')['files']
        for name,record in members.items():check(sha(HERE/name)==record['sha256'] and (HERE/name).stat().st_size==record['bytes'],'sealed '+name)
        result.update(checks=checks,sealed_files=len(members),manifest_sha256=sha(HERE/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
