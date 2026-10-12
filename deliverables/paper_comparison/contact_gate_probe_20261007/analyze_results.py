"""Read actual archives; independent geometry/reward/mapping audit, no rollout."""
import gzip,importlib.util,math,os,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_pc09_audit'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import numpy as np
from run_probe import read,sha,write,verify_sources,audit_physics,PC07,PC08,PRIOR
from deployment_profile import PROFILES
from tools.model.layered_task import functional_finish,layered_pin_fit
from tools.validation.run_b1_baseline import geometric_finish
from tools.evaluation.paper_comparison import summarize,compare

spec=importlib.util.spec_from_file_location('pc08_frozen_diagnostics',PC08/'diagnose.py')
diagnostics=importlib.util.module_from_spec(spec);spec.loader.exec_module(diagnostics)

def load(p):return __import__('json').loads(gzip.decompress(p.read_bytes()))

def hold(trace,stop,predicate):
    since=None
    for r in trace:
        if r['time_s']<stop-1e-10:continue
        if r['time_s']>stop+1+1e-10:break
        if predicate(r):
            if since is None:since=r['time_s']
            if r['time_s']-since>=.1-1e-12:return True
        else:since=None
    return False

def audit_raw(raw,c):
    audit_physics(raw);criteria=c['common']['finish_criteria'];out=raw['outcome'];peaks=raw['peaks'];n=len(raw['transitions'])
    assert len(raw['trace'])==n+1 and n==raw['control_cycles'] and raw['physical_substeps']==10*n
    safe=bool(not any(out['guard_violations'].values()) and peaks['force_N']<criteria['force_N'] and
        peaks['torque_G_Nm']<criteria['torque_Nm'] and peaks['penetration_m']<criteria['penetration_m'])
    success=bool(safe and hold(raw['trace'],raw['stop_time'],lambda r:functional_finish(r,criteria)))
    assert success==(out['task_outcome']=='FULL_SUCCESS')
    strict=bool(success and hold(raw['trace'],raw['stop_time'],lambda r:geometric_finish(r,criteria) and layered_pin_fit(r)))
    maximum=0.;terminals={'FULL_SUCCESS':10.,'TASK_FAILURE':-2.,'CONTACT_GUARD':-10.,'MOTION_VIOLATION':-10.}
    schema={x['name']:x for x in raw['observation_schema']};phase_start=schema['policy_phase']['start'];wrench_start=schema['wrench_history_M']['start']
    switches=active_switches=0;previous_gate=previous_active=None;active_insert=active_search=low_insert=0;last_xy=0.;gate_changes=[];active_changes=[]
    for i,t in enumerate(raw['transitions']):
        prev,row=raw['trace'][i:i+2];ob=np.asarray(t['observation'],dtype=np.float32)
        assert math.isclose(t['dt'],row['time_s']-prev['time_s'],abs_tol=1e-12,rel_tol=0)
        advance=row['position_m'][2]-raw['trace'][0]['position_m'][2]
        assert math.isclose(t['advance_m'],advance,abs_tol=1e-12,rel_tol=0)
        assert t['cycle_force_N']+1e-12>=np.linalg.norm(row['contact_wrench_M'][:3])
        assert t['cycle_torque_G_Nm']+1e-12>=np.linalg.norm(row['contact_wrench_G'][3:])
        new_max=max(maximum,min(.004,max(0,advance)));dt=t['dt']
        terms=dict(progress=5*(new_max-maximum)/.004,time=-.1*dt,force=-.2*dt*(t['cycle_force_N']/.025)**2,
            torque=-.2*dt*(t['cycle_torque_G_Nm']/.0005)**2,terminal=terminals[out['task_outcome']] if i==n-1 else 0.)
        terms['total']=sum(terms.values());maximum=new_max
        assert terms.keys()==t['reward_terms'].keys() and all(math.isclose(v,t['reward_terms'][k],abs_tol=1e-12,rel_tol=0) for k,v in terms.items())
        assert math.isclose(t['reward'],terms['total'],abs_tol=1e-12,rel_tol=0) and math.isclose(t['discount'],math.exp(-dt/10),abs_tol=1e-12,rel_tol=0)
        measured=np.asarray(np.clip(np.asarray(prev['contact_wrench_M'])/np.array([.025]*3+[.0005]*3),-10,10),dtype=np.float32)
        assert np.array_equal(ob[wrench_start:wrench_start+6],measured),'Action-before feedback must equal actual preceding trace'
        phase=int(ob[phase_start:phase_start+5].argmax());gate=bool(ob[wrench_start+2]<=np.float32(-.2))
        active_insert+=int(phase==0 and t['action_active']);active_search+=int(phase==2 and t['action_active'])
        low_insert+=int(phase==0 and t['action_active'] and not gate)
        if phase==0 and previous_gate is not None and previous_gate!=gate:
            switches+=1;gate_changes.append(dict(cycle=i,time_s=prev['time_s'],enabled_by_force=gate))
        if phase==0 and previous_active is not None and previous_active!=t['action_active']:
            active_switches+=1;active_changes.append(dict(cycle=i,time_s=prev['time_s'],active=t['action_active']))
        previous_gate=gate if phase==0 else None
        previous_active=t['action_active'] if phase==0 else None
        actor=np.asarray(raw['actions'][i]['actor_action']);deployed=actor*(.25 if raw['profile']=='F12.5' else 1.)
        assert np.array_equal(deployed,np.asarray(t['action']))
        if raw['profile']=='G50' and phase==0:assert not t['action_active'] or gate
        if raw['profile']=='B2':assert np.all(actor==0)
        last_xy=float(np.linalg.norm(row['position_m'][:2]))*1e6
    times=np.asarray([r['time_s'] for r in raw['trace']]);loads=np.linalg.norm([r['contact_wrench_M'][:3] for r in raw['trace']],axis=1)
    d=diagnostics.diagnose_episode(raw);assert d['active_predicted_end_command_mismatch_cycles']==0
    facts=raw['guard_facts']
    row=dict(case_id=raw['case_id'],comparison_key=raw['comparison_key'],status='finished',outcome=out['task_outcome'],
        simulation_valid=True,physical_stopped=True,contact_guard=bool(facts['contact_reasons']),motion_violation=bool(facts['motion_reasons']),
        guard_reasons=facts['contact_reasons']+facts['motion_reasons'],task_end_time_s=raw['task_end_time_s'],physical_end_time_s=raw['audit_end_time_s'],
        peak_force_N=peaks['force_N'],peak_torque_Nm=peaks['torque_G_Nm'],strict_precision_success=strict,
        sampled_force_integral_N_s=float(np.sum((loads[1:]+loads[:-1])*.5*np.diff(times))),final_xy_um=last_xy,
        network_calls=raw['network_policy_calls'],insert_active_cycles=active_insert,search_active_cycles=active_search,
        below_5mN_insert_active_cycles=low_insert,insert_force_threshold_crossings=switches,
        insert_force_gate_switches=switches if raw['profile']=='G50' else None,
        insert_active_switches=active_switches,insert_active_changes=active_changes,
        insert_force_threshold_changes=gate_changes,diagnostics=d)
    return row

def main():
    assert not (OUT/'delivery_manifest.json').exists()
    c=read(OUT/'configuration.json');l=read(OUT/'run/ledger.json');assert l['status'] in ('complete','error','controlled_stop')
    assert l['unused_closed']==8-len(l['episodes']) and l['formal_updates']==l['published_transitions']==0
    assert [e['id'] for e in l['episodes']]==[s['id'] for s in c['attempts'][:len(l['episodes'])]]
    verify_sources(c,full=True);q=read(OUT/'qualification.json');assert sha(OUT/'qualification.json')==l['qualification_sha256']
    for n,p in q['evidence_sha256'].items():assert sha(OUT/n)==p,n
    records={p:[] for p in PROFILES};errors=[];continuity=[];new_raw={};reward_rows=cycles=substeps=0
    for entry in l['episodes']:
        profile=entry['profile'];point=entry['spec']['case'];cycles+=entry.get('control_cycles',0);substeps+=entry.get('physical_substeps',0)
        if entry['status']!='finished' or not entry.get('evaluation_checks',{}).get('state_unchanged'):
            records[profile].append(dict(case_id=point['id'],comparison_key=c['common_key'],status='error',error=entry.get('error',l.get('error'))));continue
        try:
            p=OUT/'run'/(entry['id']+'.json.gz');assert sha(p)==entry['archive_sha256'];raw=load(p)
            assert raw['case']==point and raw['profile']==profile and raw['comparison_key']==c['common_key']
            assert raw['qualification_sha256']==l['qualification_sha256'] and raw['evaluation_checks']==entry['evaluation_checks']
            expected=0 if profile=='B2' else 2000
            assert raw['optimizer_steps_start']==raw['optimizer_steps']==expected and not raw['training_admitted'] and raw['published_transitions']==0
            if profile!='B2':assert raw['checkpoint']==c['checkpoint'] and raw['policy_sha256']==l['policy_read_gate']['fingerprints']['actor']
            row=audit_raw(raw,c);row.update(id=entry['id'],profile=profile,archive_sha256=sha(p),wall_seconds=entry['wall_seconds'])
            records[profile].append(row);new_raw[(profile,point['id'])]=raw;reward_rows+=len(raw['transitions'])
            if profile in ('B2','F50'):
                old=PC07/'run'/('dev_B2_'+point['id']+'.json.gz') if profile=='B2' else PRIOR/'run'/('final_F50_'+point['id']+'.json.gz')
                older=load(old);fields=('trace','controller_events','outcome','events','stop_samples','peaks')
                matches={f:raw[f]==older[f] for f in fields};assert all(matches.values()),matches
                keys=('actor_action','profile','deployment_multiplier')
                assert [{k:v for k,v in a.items() if k not in keys} for a in raw['actions']]==older['actions']
                continuity.append(dict(id=entry['id'],prior_path=old.relative_to(ROOT).as_posix(),prior_sha256=sha(old),matched=matches,actions_exact_excluding_new_metadata=True))
            print(entry['id'],row['outcome'],row['task_end_time_s'],flush=True)
        except Exception as exc:errors.append(dict(id=entry['id'],error=repr(exc)));raise
    aligned_exact=None
    if ('G50','aligned') in new_raw:
        g=new_raw[('G50','aligned')];b=new_raw[('B2','aligned')]
        aligned_exact=g['trace']==b['trace'] and g['controller_events']==b['controller_events'] and g['outcome']==b['outcome']
        assert aligned_exact and g['network_policy_calls']==0
    cases=['aligned','y_neg_150'];metrics={p:summarize(v,cases) for p,v in records.items()}
    comparisons={a+'_to_'+b:compare(records[a],records[b],cases) for a,b in [('B2','F50'),('B2','F12.5'),('B2','G50'),('F50','G50'),('F12.5','G50')]}
    assert l['policy_calls']==sum(e.get('policy_calls',0) for e in l['episodes'])
    assert l['policy_call_attempts']==sum(e.get('policy_call_attempts',0) for e in l['episodes'])>=l['policy_calls']
    if l['status']=='complete':assert l['policy_calls']==l['policy_call_attempts']
    result=dict(records=records,metrics=metrics,comparisons=comparisons,audit_errors=errors,baseline_continuity=continuity,
        aligned_G50_B2_trace_exact=aligned_exact,new_attempts=len(l['episodes']),finished=sum(e['status']=='finished' for e in l['episodes']),
        cumulative_dynamic=200+len(l['episodes']),control_cycles=cycles,physical_substeps=substeps,independent_reward_rows=reward_rows,
        network_policy_calls=l['policy_calls'],network_attempts=l['policy_call_attempts'],formal_updates=0,published_transitions=0,
        wall_seconds=sum(e.get('wall_seconds',0) for e in l['episodes']),unused_closed=l['unused_closed'],
        scope='two used development positions, frozen actor sensitivity; not trained G50 or paper superiority')
    write(OUT/'assessment.json',result);verify_sources(c,full=True);print('PC-09 actual archive audit complete',flush=True)

if __name__=='__main__':main()
