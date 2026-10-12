"""Pure archive statistics: no environment, policy, optimizer or rollout imports."""
from pathlib import Path
import gzip,hashlib,json,math
import numpy as np

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
PC07=ROOT/'deliverables/paper_comparison/frozen_comparison_20261007'
PC06=ROOT/'deliverables/paper_comparison/v4_learning_requalification_20261006'
SEALS={PC07:'8c64d623247c31e217f71e90cbb473c3d21a05c49360f10872dab4eddd36596c',
       PC06:'fd98d247484e919c3c4e099d03575b1d4d40e977a5da939efc088759c84b9ed5'}
PHASES=('INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED')

def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,value):p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def vector(value,size):
    a=np.asarray(value,dtype=float)
    if a.shape!=(size,) or not np.isfinite(a).all():raise ValueError('Invalid finite vector')
    return a

def phase_of(raw,t):
    groups=[s for s in raw['observation_schema'] if s['name']=='policy_phase']
    if len(groups)!=1 or groups[0]['width']!=5:raise ValueError('Unique five-phase schema required')
    ob=vector(t['observation'],137);i=groups[0]['start'];one=ob[i:i+5]
    if len(one)!=5 or sum(one)!=1 or not all(x in (0.,1.) for x in one):raise ValueError('Invalid phase onehot')
    return PHASES[int(one.argmax())]

def diagnose_episode(raw):
    n=len(raw['actions'])
    if not n or len(raw['transitions'])!=n or len(raw['trace'])!=n+1 or raw['control_cycles']!=n:
        raise ValueError('Aligned nonempty actions/transitions/trace required')
    stages={};enabled=[];effects=[];forces=[];prediction_mismatches=0;active_mismatches=0;mismatch_phases={}
    for i,(log,t) in enumerate(zip(raw['actions'],raw['transitions'])):
        before,after=raw['trace'][i:i+2];dt=float(t['dt']);start=float(before['time_s']);end=float(after['time_s'])
        if not math.isfinite(dt) or dt<=0 or not math.isclose(end-start,dt,abs_tol=1e-12,rel_tol=0):raise ValueError('Invalid dt')
        phase=phase_of(raw,t);active=bool(t['action_active'])
        if active!=log['enabled']:raise ValueError('Permission mismatch')
        action=vector(log['raw_action'],4);request=vector(log['applied_residual'],6);delta=vector(log['effective_command_delta'],6)
        if np.any(np.abs(action)>1) or (not active and (np.any(request!=0) or np.any(delta!=0))):raise ValueError('Invalid inactive action')
        force=float(t['cycle_force_N'])
        if not math.isfinite(force) or force<0:raise ValueError('Invalid cycle force')
        filt=float(log['reference_filter_fraction'])
        if not math.isfinite(filt) or not 0<=filt<=1:raise ValueError('Invalid reference fraction')
        a=stages.setdefault(phase,dict(cycles=0,duration_s=0.,task_duration_s=0.,enabled_cycles=0,enabled_duration_s=0.,
            nonzero_command_cycles=0,clipped_cycles=0,total_target_limited_cycles=0,zero_measured_wrench_enabled_cycles=0,
            reference_filtered_cycles=0,requested_xy_integral_um=0.,effective_xy_integral_um=0.,
            requested_rotation_integral_mrad=0.,effective_rotation_integral_mrad=0.,actual_xy_path_um=0.,actual_rotation_path_mrad=0.,
            actual_xy_net_um=[0.,0.],actual_z_net_um=0.,sum_abs_raw_action=[0.]*4,saturated_components=[0]*4,peak_force_N=0.))
        a['cycles']+=1;a['duration_s']+=dt;a['task_duration_s']+=max(0.,min(end,raw['task_end_time_s'])-start)
        if active:enabled.append(i);a['enabled_cycles']+=1;a['enabled_duration_s']+=dt
        changed=bool(np.any(np.abs(delta)>1e-15))
        if changed:effects.append(i);a['nonzero_command_cycles']+=1
        a['clipped_cycles']+=int(active and not np.allclose(request,delta,rtol=0,atol=1e-15))
        a['total_target_limited_cycles']+=int(active and not np.allclose(vector(log['unfiltered_stage_limited_total'],6),
            vector(log['predicted_limited_command'],6),rtol=0,atol=1e-15))
        if 'contact_wrench_M' in before:
            a['zero_measured_wrench_enabled_cycles']+=int(active and not np.any(vector(before['contact_wrench_M'],6)!=0))
        a['reference_filtered_cycles']+=int(filt<1.)
        for prefix,v in [('requested',request),('effective',delta)]:
            a[prefix+'_xy_integral_um']+=float(np.linalg.norm(v[:2]))*dt*1e6
            a[prefix+'_rotation_integral_mrad']+=float(np.linalg.norm(v[3:5]))*dt*1000
        p0=vector(before['position_m'],3);p1=vector(after['position_m'],3);move=p1-p0
        a['actual_xy_path_um']+=float(np.linalg.norm(move[:2]))*1e6
        a['actual_xy_net_um']=(np.asarray(a['actual_xy_net_um'])+move[:2]*1e6).tolist();a['actual_z_net_um']+=float(move[2])*1e6
        q0=vector(before['quaternion_wxyz'],4);q1=vector(after['quaternion_wxyz'],4)
        if min(np.linalg.norm(q0),np.linalg.norm(q1))==0:raise ValueError('Zero quaternion')
        cosine=abs(float(np.dot(q0,q1)/(np.linalg.norm(q0)*np.linalg.norm(q1))))
        a['actual_rotation_path_mrad']+=2*math.acos(min(1.,cosine))*1000
        if active:
            a['sum_abs_raw_action']=(np.asarray(a['sum_abs_raw_action'])+np.abs(action)).tolist()
            a['saturated_components']=(np.asarray(a['saturated_components'])+(np.abs(action)>=.95)).tolist()
        a['peak_force_N']=max(a['peak_force_N'],force);forces.append(force)
        mismatch=not np.allclose(vector(log['predicted_limited_command'],6),vector(log['actual_end_limited_command'],6),rtol=0,atol=1e-15)
        if mismatch:
            prediction_mismatches+=1;active_mismatches+=int(active)
            key=before.get('phase','UNSPECIFIED')+'->'+after.get('phase','UNSPECIFIED')
            mismatch_phases[key]=mismatch_phases.get(key,0)+1
    first=enabled[0] if enabled else None;peak=int(np.argmax(forces))
    for a in stages.values():
        a['mean_abs_raw_action']=[x/a['enabled_cycles'] if a['enabled_cycles'] else None for x in a.pop('sum_abs_raw_action')]
        a['xy_command_delivery_fraction']=a['effective_xy_integral_um']/a['requested_xy_integral_um'] if a['requested_xy_integral_um'] else None
    return dict(stages=stages,first_enabled_cycle=first,first_enabled_time_s=None if first is None else raw['trace'][first]['time_s'],
        first_effect_cycle=effects[0] if effects else None,peak_cycle_index=peak,peak_cycle_interval_s=[raw['trace'][peak]['time_s'],raw['trace'][peak+1]['time_s']],
        peak_force_N=max(forces),pre_enabled_peak_force_N=None if first is None else max(forces[:first],default=0.),
        peak_before_first_enabled=None if first is None else peak<first,predicted_end_command_mismatch_cycles=prediction_mismatches,
        active_predicted_end_command_mismatch_cycles=active_mismatches,command_mismatch_physical_phases=mismatch_phases)

def pair_prefix(base,candidate):
    enabled=[i for i,a in enumerate(candidate['actions']) if a['enabled']]
    count=enabled[0]+1 if enabled else len(candidate['trace']);compared=min(count,len(base['trace']))
    mismatch=next((i for i in range(compared) if base['trace'][i]!=candidate['trace'][i]),None)
    return dict(prefix_rows=count,compared_rows=compared,trace_prefix_exact=mismatch is None and compared==count,
                first_different_row=mismatch,first_enabled_cycle=enabled[0] if enabled else None)

def time_contributions(base,candidate):
    def index(rows):
        out={}
        for r in rows:
            if r['case_id'] in out or r['outcome'] not in ('FULL_SUCCESS','TASK_FAILURE','CONTACT_GUARD','MOTION_VIOLATION'):raise ValueError('Invalid comparison row')
            out[r['case_id']]=float(r['task_end_time_s']) if r['outcome']=='FULL_SUCCESS' else 26.
        return out
    b=index(base);c=index(candidate)
    if not b or b.keys()!=c.keys():raise ValueError('Matched nonempty cases required')
    values={k:b[k]-c[k] for k in b};total=sum(values.values())
    return dict(savings_s=values,total_saved_s=total,fractions={k:v/total if abs(total)>1e-12 else None for k,v in values.items()})

def verify_sources():
    counts={}
    for folder,pin in SEALS.items():
        assert sha(folder/'delivery_manifest.json')==pin
        files=read(folder/'delivery_manifest.json')['files'];counts[folder.name]=len(files)
        for n,m in files.items():assert sha(folder/n)==m['sha256'] and (folder/n).stat().st_size==m['bytes'],n
    inputs=read(PC06/'configuration.json')['input_sha256']
    for n,pin in inputs.items():assert sha(ROOT/n)==pin,n
    return dict(sealed_files=counts,production_inputs_unchanged=len(inputs),seals={p.name:v for p,v in SEALS.items()})

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed; analyze only in complete copy')
    proof=verify_sources();cfg=read(PC07/'configuration.json');ledger=read(PC07/'run/ledger.json');assessment=read(PC07/'assessment.json')
    assert ledger['status']=='complete' and assessment['audit_errors']==[]
    sources=[]
    for e in ledger['episodes']:
        sources.append(dict(path=(PC07/'run'/(e['id']+'.json.gz')).relative_to(ROOT).as_posix(),sha256=e['archive_sha256'],
            provider=e['spec']['provider'],group=e['spec']['evaluation_scope'],case_id=e['spec']['case']['id'],id=e['id']))
    for r in cfg['inherited_development']:
        sources.append(dict(path=(PC06/'run'/(r['id']+'.json.gz')).relative_to(ROOT).as_posix(),sha256=r['archive_sha256'],
            provider='F2000' if r['mode']=='F50' else 'S2000',group='development',case_id=r['case']['id'],id=r['id']))
    write(OUT/'configuration.json',dict(scope='offline_descriptive_diagnosis_only',dynamic_episodes=0,optimizer_batches=0,network_policy_calls=0,
        published_transitions=0,cumulative_dynamic=200,first_use_positions_consumed=True,source_proof=proof,archives=sources,
        diagnostic_input_sha256={str(p.relative_to(ROOT).as_posix()):sha(p) for p in (Path(__file__),OUT/'test_diagnose.py',ROOT/'docs/superpowers/plans/2026-10-07-residual-effect-diagnosis.md')}))
    records=[];prefixes=[];cycle_rows=0
    for source in sources:
        path=ROOT/source['path'];assert sha(path)==source['sha256'];raw=json.loads(gzip.decompress(path.read_bytes()))
        assert raw['case_id']==source['case_id'] and raw['comparison_key']==cfg['common_key']
        result=diagnose_episode(raw);cycle_rows+=raw['control_cycles']
        records.append(dict(**source,task_outcome=raw['outcome']['task_outcome'],task_end_time_s=raw['task_end_time_s'],
            actual_cycles=raw['control_cycles'],reported_peak_force_N=raw['peaks']['force_N'],**result))
        if source['provider'] in ('S0','S2000'):
            baseline=next(s for s in sources if s['provider']=='B2' and s['case_id']==source['case_id'] and s['group']==source['group'])
            base=json.loads(gzip.decompress((ROOT/baseline['path']).read_bytes()));prefixes.append(dict(candidate_id=source['id'],baseline_id=baseline['id'],**pair_prefix(base,raw)))
        print(json.dumps(dict(id=source['id'],phase='offline',cycles=raw['control_cycles'],peak_before_first_enabled=result['peak_before_first_enabled']),ensure_ascii=False),flush=True)
    assert len(records)==37
    contributions={g:{b+'_to_'+c:time_contributions(methods[b],methods[c]) for b,c in [('B2','F2000'),('B2','S2000'),('F2000','S2000')]}
        for g,methods in assessment['records'].items()}
    write(OUT/'diagnosis.json',dict(records=records,prefixes=prefixes,time_contributions=contributions,archive_count=len(records),cycle_rows=cycle_rows,
        source_proof=proof,new_dynamic=0,new_gradients=0,new_policy_calls=0,new_published_transitions=0,
        scope='description and command-level comparisons; not new causal physics or independent performance samples',
        metric_definitions=dict(clipped_cycles='legacy request != instantaneous zero-alternative delta; not proof of undelivered residual',
            total_target_limited_cycles='post-stage-limit total target != final predicted drive command on enabled cycles',
            xy_command_delivery_fraction='instantaneous limiter-delta/request integral ratio; history-dependent, not a physical transmission fraction',
            actual_motion='observed path in whole phase including stop tail; not caused displacement inferred from residual')))
    assert verify_sources()==proof
    print(json.dumps(dict(archives=len(records),cycles=cycle_rows,prefixes=len(prefixes),new_dynamic=0,new_gradients=0)))
if __name__=='__main__':main()
