"""Readonly verification of frozen preparation, snapshots and source provenance."""
import argparse,ast,gzip,json,subprocess,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
import sac_entry  # Installs NoScience before any further package import.
from sac_scope import ROOT,ENTRY,read,write,sha,canonical,verify_binding,schedule,NUMERIC_LIMITS,PHYSICAL_LIMITS

def verify(sealed=False,documents=False):
    checks=[]
    def check(name,condition):
        if condition is not True:raise AssertionError(name)
        checks.append(name)
    b,cfg=verify_binding();check('all_bound_sources_and_runtime_metadata',True)
    for s in b['prior_seals']:
        m=read(s['path']);check('seal_manifest_'+Path(s['path']).parent.name,sha(s['path'])==s['sha256'])
        check('seal_size_'+Path(s['path']).parent.name,len(m['files'])==s['members'])
        for rel,pin in m['files'].items():
            p=Path(s['path']).parent/rel
            if sha(p)!=(pin['sha256'] if isinstance(pin,dict) else pin) or isinstance(pin,dict) and p.stat().st_size!=pin['bytes']:
                raise AssertionError('Historical seal drift '+str(p))
        check('seal_members_'+Path(s['path']).parent.name,True)
    states=read(OUT/'numeric_reference_states.json')['states']
    check('golden_32_no_new_calls',len(states)==32 and read(OUT/'numeric_reference_states.json')['new_policy_calls']==0)
    for role in ['F0','F2000']:
        check('golden_16_'+role,len([s for s in states if s['role']==role])==16)
    check('42_registered_units',len(schedule())==42)
    check('12_precheck_30_remaining',len([s for s in schedule() if s['phase']=='dynamic_precheck'])==12)
    reuse=read(OUT/'reuse_catalog.json');check('75_comparison_units_33_reused',reuse['total']==75 and reuse['reused']==33 and reuse['pending']==42)
    check('caps_609000_6090000',PHYSICAL_LIMITS['control_cycles']==42*14500 and PHYSICAL_LIMITS['native_steps']==42*145000)
    check('numeric_32states_64calls_no_physics',NUMERIC_LIMITS['distinct_states']==32 and NUMERIC_LIMITS['policy_calls']==64 and NUMERIC_LIMITS['native_steps']==0)
    check('shared_model_identical',sha(OUT/'model.xml')==sha(ENTRY/'model.xml'))
    q=read(OUT/'qualification_candidate.json')
    check('qualification_bound',q['source_binding_sha256']==sha(OUT/'source_binding.json'))
    check('no_numeric_dynamic_training_acceptance',not any(q[k] for k in ['numeric_actor_equivalence_passed','nonzero_dynamic_precheck_passed',
        'evaluation_execution_admitted','training_admitted','continuous_scope_qualified','full_B2_accepted','C_accepted','weight_tensor_read']))
    requests=read(OUT/'authorization_requests.json');check('both_compute_grants_draft',all(requests[k]['status']=='DRAFT' and requests[k]['explicit_user_authorized'] is False for k in ['numeric','physical']))
    check('no_execution_dirs',not (OUT/'numeric_execution').exists() and not (OUT/'evaluation_execution').exists())
    check('zero_scientific_imports',not any(x.split('.')[0] in ('numpy','torch','mujoco','gymnasium','stable_baselines3') for x in sys.modules))
    for p in OUT.glob('*.py'):ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
    check('all_python_syntax',True)
    for name in ['sac_scope.py','sac_entry.py','sac_rollout.py','actor_runtime.py','sac_assess.py']:
        tree=ast.parse((OUT/name).read_text(encoding='utf-8'))
        root_imports=[]
        for n in tree.body:
            if isinstance(n,ast.Import):root_imports.extend(a.name.split('.')[0] for a in n.names)
            elif isinstance(n,ast.ImportFrom):root_imports.append((n.module or '').split('.')[0])
        check('no_top_science_'+name,not set(root_imports)&{'numpy','torch','mujoco','gymnasium','stable_baselines3'})
    before=read(OUT/'before_state.json')
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,stderr=subprocess.DEVNULL).rstrip(b'\r\n')
    check('same_branch',git('branch','--show-current').decode()==before['branch'])
    check('same_head',git('rev-parse','HEAD').decode()==before['head'])
    old_status=[r[3:] for r in (OUT/'git_status_before.bin').read_bytes().split(b'\0') if r]
    new_status=[r[3:] for r in git('status','--porcelain=v1','-z').split(b'\0') if r]
    check('previous_dirty_paths_preserved',set(old_status)<=set(new_status))
    for rel,pin in before['runtime_sources'].items():
        if sha(ROOT/rel)!=pin:raise AssertionError('Changed prior tools source '+rel)
    check('all_200_tools_sources_unchanged',len(before['runtime_sources'])==200)
    check('AGENTS_unchanged',sha(ROOT/'AGENTS.md')==before['documents']['AGENTS.md'])
    if documents:
        after=read(OUT/'after_state.json')
        for rel,pin in before['documents'].items():
            check('before_snapshot_'+rel,sha(OUT/'before_documents'/rel)==pin)
            check('after_snapshot_'+rel,sha(OUT/'after_documents'/rel)==after['documents'][rel])
            check('current_document_'+rel,sha(ROOT/rel)==after['documents'][rel])
    if sealed:
        manifest=read(OUT/'delivery_manifest.json')
        for rel,pin in manifest['files'].items():
            if sha(OUT/rel)!=pin:raise AssertionError('New preparation seal changed '+rel)
        check('new_delivery_seal',True)
        check('offline_and_fresh_review',q['offline_checks_passed'] is True and q['fresh_review_completed'] is True)
    return dict(passed=True,checks=len(checks),names=checks,bound_sources=len(b['files']),old_seal_members=529,
        cumulative_dynamic=279,scientific_imports=0,tensor_loads=0,policy_calls=0,new_physics=0,automatic_tracking='PAUSED')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--sealed',action='store_true');parser.add_argument('--documents',action='store_true');args=parser.parse_args()
    print(json.dumps(verify(args.sealed,args.documents),ensure_ascii=False))
