"""Stdlib-only integrity and independent numeric closeout of the archive study."""
import argparse,ast,csv,gzip,hashlib,json,math,subprocess,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seal',action='store_true');parser.add_argument('--current-docs',action='store_true');args=parser.parse_args()
    if args.seal and (OUT/'delivery_manifest.json').exists():raise FileExistsError('Never reseal')
    count=0
    def check(ok,label):
        nonlocal count
        if not ok:raise AssertionError(label)
        count+=1
    reg=read(OUT/'registration.json');prior=Path(reg['prior_directory'])
    check(sha(prior/'delivery_manifest.json')==reg['prior_manifest_sha256'],'fixed SCOPE20 seal')
    command=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(prior/'verify_closed.py')],cwd=ROOT,capture_output=True,text=True,encoding='utf8',check=True)
    old=json.loads(command.stdout.strip().splitlines()[-1]);check(old['old_sealed_members_preserved']+old['sealed_files']==3685 and old['bound_inputs_preserved']==2655,'all old sealed members and sources intact')
    for name,pin in reg['source_code_sha256'].items():check(sha(ROOT/name)==pin,'interpretation source '+name)
    check(sha(OUT/'plan_snapshot.md')==reg['plan_sha256'],'registered plan snapshot')
    check(all(v==0 for v in reg['costs'].values()) and reg['cumulative_dynamic']==254 and not reg['training_admitted'] and reg['automatic_tracking']=='PAUSED','offline scope only')
    d=read(OUT/'diagnosis.json');records={(r['model'],r['case_id']):r for r in d['records']};total_cycles=0;all_observations=[];actions={m:[] for m in ('F0','F2000')};common=None
    check(len(records)==len(reg['archives'])==8,'all eight frozen archives')
    for item in reg['archives']:
        check(sha(item['path'])==item['sha256'],'input archive '+item['model']+item['case_id'])
        raw=json.loads(gzip.decompress(Path(item['path']).read_bytes()));r=records[item['model'],item['case_id']];n=raw['control_cycles'];total_cycles+=n
        check(r['sha256']==item['sha256'] and r['control_cycles']==n and len(raw['trace'])==n+1 and len(raw['transitions'])==len(raw['actions'])==n,'archive record alignment')
        if common is None:common=raw['comparison_key']
        check(raw['comparison_key']==common and raw['case_id']==item['case_id'] and raw['optimizer_steps']==(0 if item['model']=='F0' else 2000),'same common task and frozen policy boundary')
        check(raw['outcome']['task_outcome']=='FULL_SUCCESS' and raw['outcome']['simulation_valid'] and raw['outcome']['physical_stopped'] and not any(raw['outcome']['guard_violations'].values()),'functional outcome preserved')
        fields={x['name']:x for x in raw['observation_schema']};parts={};reward={};task_index=min(range(n+1),key=lambda i:abs(raw['trace'][i]['time_s']-raw['task_end_time_s']))
        check(abs(raw['trace'][task_index]['time_s']-raw['task_end_time_s'])<1e-9,'task cut is an archived trace boundary')
        for i,t in enumerate(raw['transitions']):
            x=t['observation'];pf=fields['policy_phase'];ph=fields['physical_phase'];policy=x[pf['start']:pf['start']+5];physical=x[ph['start']:ph['start']+4]
            check(sum(policy)==sum(physical)==1 and all(v in (0.,1.) for v in policy+physical),'valid input phase onehot')
            label=('INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED')[policy.index(1.)] if physical.index(1.)==0 else ('RUNNING','STOPPING','RETRACT','TERMINAL')[physical.index(1.)]
            elapsed=raw['trace'][i+1]['time_s']-raw['trace'][i]['time_s']
            check(elapsed>0 and abs(elapsed-t['dt'])<2e-12,'saved physical dt')
            if i<task_index:parts[label]=parts.get(label,0.)+elapsed
            for k,v in t['reward_terms'].items():reward[k]=reward.get(k,0.)+v
        check(set(parts)==set(r['phase_times_s']) and all(abs(v-r['phase_times_s'][k])<1e-9 for k,v in parts.items()),'independent task time allocation')
        check(abs(sum(parts.values())-r['task_time_s'])<1e-9 and abs(r['audit_tail_s']-(raw['audit_end_time_s']-raw['task_end_time_s']))<1e-9,'task time distinct from audit tail')
        check(all(abs(v-r['reward_all'][k])<1e-8 for k,v in reward.items()),'archived reward component sums')
        for index,key in ((task_index,'task_end_state'),(n,'archive_end_state')):
            row=raw['trace'][index];xy=math.hypot(*row['position_m'][:2])*1e6;q=row['quaternion_wxyz'];norm=math.sqrt(sum(v*v for v in q));angle=math.degrees(2*math.acos(min(1.,abs(q[0])/norm)))
            check(abs(xy-r[key]['xy_um'])<1e-9 and abs(angle-r[key]['angle_to_identity_deg'])<1e-7,'independent final carrier pose')
            check(r[key]['additional_80um_0p5deg']==(xy<=80. and angle<=.5),'supplementary precision separate from outcome')
        all_observations.append(raw['transitions'][0]['observation']);actions[item['model']].append(raw['actions'][0]['raw_action'])
    check(total_cycles==d['archive_cycles']==42171,'all saved cycles counted')
    check(d['initial_observation_identical_across_all_eight']==all(x==all_observations[0] for x in all_observations),'initial observation equality')
    check(d['initial_action_identical_within_each_actor']=={m:all(x==xs[0] for x in xs) for m,xs in actions.items()},'initial actor action equality without inference')
    check(d['additional_precision_successes']=={m:sum(r['archive_end_state']['additional_80um_0p5deg'] for r in records.values() if r['model']==m) for m in actions}=={'F0':4,'F2000':0},'actual supplementary precision counts')
    f0=sum(r['task_time_s'] for r in records.values() if r['model']=='F0')/4;f2=sum(r['task_time_s'] for r in records.values() if r['model']=='F2000')/4
    assessment=read(prior/'assessment.json')
    check(abs(d['relative_improvement']-(1-f2/f0))<1e-12 and abs(d['relative_improvement']-assessment['relative_improvement'])<1e-12 and not d['development_continue'],'unchanged failed 10 percent continue metric')
    with (OUT/'cycles.csv').open(encoding='utf8',newline='') as f:rows=list(csv.DictReader(f))
    check(len(rows)==total_cycles,'CSV retains all archive cycles')
    offset=0
    for item in reg['archives']:
        n=records[item['model'],item['case_id']]['control_cycles'];subset=rows[offset:offset+n];offset+=n
        check(all(row['model']==item['model'] and row['case_id']==item['case_id'] and int(row['cycle'])==i for i,row in enumerate(subset)),'CSV exact per-case cycle ordering')
    decision=read(OUT/'route_decision.json');check(not decision['candidate_implemented'] and not decision['next_task_started'] and not decision['new_scientific_execution_authorized'] and not decision['old_outcomes_changed'] and not decision['primary_threshold_changed'],'route is a proposed offline candidate only')
    review=read(OUT/'review_resolution.json');check(review['status']=='RESOLVED' and review['open_critical']==review['open_important']==0,'limited review resolved')
    proposal=read(OUT/'document_proposal.json');check(sha(OUT/'document_proposal.json')==review['document_proposal_sha256'],'reviewed proposal identity')
    for key,file in (('report_sha256','结果说明.md'),('route_sha256','路线决定.md'),('publisher_sha256','publish_delivery.py')):check(sha(OUT/file)==proposal[key],'reviewed publication '+file)
    docs=read(OUT/'document_update.json');check(docs['next_task_started'] is False,'next candidate not started')
    for name,pin in reg['before_documents'].items():
        check(sha(OUT/'before_documents'/name)==pin,'before snapshot '+name)
        check(sha(OUT/'document_snapshots'/name)==docs['after_documents'][name],'after snapshot '+name)
        if name=='AGENTS.md':check(docs['after_documents'][name]==pin,'AGENTS unchanged')
        else:check(docs['after_documents'][name]==proposal['proposed_documents'][name]==sha(OUT/'document_proposals'/name),'published exact reviewed document '+name)
        if args.current_docs:check(sha(ROOT/name)==docs['after_documents'][name],'current rolling document '+name)
    git=lambda *x:subprocess.check_output(['git',*x],cwd=ROOT).decode('utf8')
    check(git('branch','--show-current').strip()==reg['branch'] and git('rev-parse','HEAD').strip()==reg['head'],'branch and HEAD preserved')
    before=set((OUT/'git_status_before.txt').read_text(encoding='utf8').splitlines());after=set(git('status','--porcelain=v1').splitlines());check(not before-after,'all old dirty entries retained')
    allowed={'argparse','ast','csv','gzip','hashlib','json','math','subprocess','sys','pathlib','shutil','os','re','unittest','tempfile','analyze','build_report','publish_delivery'}
    for path in OUT.glob('*.py'):
        tree=ast.parse(path.read_text(encoding='utf8'))
        for node in ast.walk(tree):
            names=[a.name.split('.')[0] for a in node.names] if isinstance(node,ast.Import) else [node.module.split('.')[0]] if isinstance(node,ast.ImportFrom) else []
            check(all(name in allowed for name in names),'stdlib-only stage imports '+path.name)
    check(not any(k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3','gymnasium') for k in sys.modules),'no scientific work during closeout')
    result=dict(stage_id='B2-SCOPE-21',status='VERIFIED_OFFLINE_DIAGNOSIS',checks=count,archive_count=8,archive_cycles=total_cycles,
         source_code_pins=len(reg['source_code_sha256']),old_sealed_members_preserved=3685,bound_inputs_preserved=2655,dirty_entries_preserved=len(before),
         additional_precision_successes=d['additional_precision_successes'],relative_improvement=d['relative_improvement'],costs=reg['costs'],
         cumulative_dynamic=254,automatic_tracking='PAUSED',training_admitted=False,independent_tests=0,full_B2_accepted=False,C_accepted=False)
    if args.seal:
        write(OUT/'closure_prior_verification.json',old);write(OUT/'verification.json',result);(OUT/'git_status_after.txt').write_text(git('status','--porcelain=v1'),encoding='utf8')
        files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts}
        write(OUT/'delivery_manifest.json',dict(stage_id='B2-SCOPE-21',files=files,rolling_documents_may_advance=True))
    if (OUT/'delivery_manifest.json').exists():
        files=read(OUT/'delivery_manifest.json')['files']
        for name,entry in files.items():check(sha(OUT/name)==entry['sha256'] and (OUT/name).stat().st_size==entry['bytes'],'sealed '+name)
        result.update(checks=count,sealed_files=len(files),manifest_sha256=sha(OUT/'delivery_manifest.json'))
    print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
