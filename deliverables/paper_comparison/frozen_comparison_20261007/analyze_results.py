"""Offline audit of new fixed evaluations and immutable inherited development."""
import datetime,gzip,json,math,os,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_pc07_audit'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import numpy as np
from run_evaluation import PRIOR,PRIOR_SEAL,read,sha,verify_sources,canonical
from tools.validation.run_v4_learning_pilot import audit_evaluation
from tools.validation.native313_matrix_audit import actual_stop_pass
from tools.validation.run_contact_candidate_stop import physical_tail_pass
from tools.validation.verify_admitted_collection import validate_outcome
from tools.model.layered_task import functional_finish,layered_pin_fit
from tools.validation.run_b1_baseline import geometric_finish
from tools.evaluation.paper_comparison import summarize,compare

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

def audit_raw(raw,common):
    audit_evaluation({**raw,'scope':raw.get('collector_scope',raw['scope'])})
    stopped=bool(actual_stop_pass(raw['stop_samples'],raw['events'],raw['stop_time'],raw['audit_end_time_s'],.0002) and
        physical_tail_pass(raw['stop_samples'],raw['audit_end_time_s'],.0002))
    validate_outcome(raw,stopped=stopped)
    criteria=common['finish_criteria'];out=raw['outcome'];peaks=raw['peaks']
    eligible=bool(out['simulation_valid'] and stopped and not any(out['guard_violations'].values()) and
        peaks['force_N']<criteria['force_N'] and peaks['torque_G_Nm']<criteria['torque_Nm'] and peaks['penetration_m']<criteria['penetration_m'])
    success=eligible and hold(raw['trace'],raw['stop_time'],lambda r:functional_finish(r,criteria))
    assert success==(out['task_outcome']=='FULL_SUCCESS')
    strict=bool(success and hold(raw['trace'],raw['stop_time'],lambda r:geometric_finish(r,criteria) and layered_pin_fit(r)))
    maximum=0.;terminal={'FULL_SUCCESS':10.,'TASK_FAILURE':-2.,'CONTACT_GUARD':-10.,'MOTION_VIOLATION':-10.,'INVALID_SIMULATION':0.,'STOP_NOT_QUALIFIED':0.}
    for i,t in enumerate(raw['transitions']):
        prev,row=raw['trace'][i:i+2]
        assert math.isclose(t['dt'],row['time_s']-prev['time_s'],abs_tol=1e-12,rel_tol=0)
        assert math.isclose(t['advance_m'],row['position_m'][2]-raw['trace'][0]['position_m'][2],abs_tol=1e-12,rel_tol=0)
        assert t['cycle_force_N']+1e-12>=np.linalg.norm(row['contact_wrench_M'][:3])
        assert t['cycle_torque_G_Nm']+1e-12>=np.linalg.norm(row['contact_wrench_G'][3:])
        new_max=max(maximum,min(.004,max(0,t['advance_m'])))
        expected=dict(progress=5*(new_max-maximum)/.004,time=-.1*t['dt'],force=-.2*t['dt']*(t['cycle_force_N']/.025)**2,
            torque=-.2*t['dt']*(t['cycle_torque_G_Nm']/.0005)**2,terminal=terminal[out['task_outcome']] if i==len(raw['transitions'])-1 else 0.)
        expected['total']=sum(expected.values());maximum=new_max
        assert expected.keys()==t['reward_terms'].keys() and all(math.isclose(v,t['reward_terms'][k],abs_tol=1e-12,rel_tol=0) for k,v in expected.items())
        assert math.isclose(expected['total'],t['reward'],abs_tol=1e-12,rel_tol=0) and math.isclose(t['discount'],math.exp(-t['dt']/10),abs_tol=1e-12,rel_tol=0)
    assert len(raw['transitions'])==raw['control_cycles'] and raw['physical_substeps']==10*raw['control_cycles']
    times=np.array([r['time_s'] for r in raw['trace']]);loads=np.linalg.norm([r['contact_wrench_M'][:3] for r in raw['trace']],axis=1)
    facts=raw['guard_facts']
    return dict(case_id=raw['case_id'],comparison_key=raw['comparison_key'],status='finished',outcome=out['task_outcome'],
        simulation_valid=out['simulation_valid'],physical_stopped=stopped,contact_guard=bool(facts['contact_reasons']),motion_violation=bool(facts['motion_reasons']),
        guard_reasons=facts['contact_reasons']+facts['motion_reasons'],task_end_time_s=raw['task_end_time_s'],physical_end_time_s=raw['audit_end_time_s'],
        peak_force_N=peaks['force_N'],peak_torque_Nm=peaks['torque_G_Nm'],strict_precision_success=strict,
        sampled_force_integral_N_s=float(np.sum((loads[1:]+loads[:-1])*.5*np.diff(times))))

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    config=read(OUT/'configuration.json');l=read(OUT/'run/ledger.json')
    assert l['status'] in ('complete','controlled_stop','error') and l['unused_closed']==27-len(l['episodes'])
    verify_sources(config)
    for n,m in read(PRIOR/'delivery_manifest.json')['files'].items():assert sha(PRIOR/n)==m['sha256'],n
    continuity=read(OUT/'baseline_continuity.json') if (OUT/'baseline_continuity.json').exists() else None
    if continuity:
        new=OUT/'run'/(continuity['new_id']+'.json.gz');old=ROOT/continuity['prior_path']
        assert sha(new)==continuity['new_sha256'] and sha(old)==continuity['prior_sha256']
        nr=json.loads(gzip.decompress(new.read_bytes()));pr=json.loads(gzip.decompress(old.read_bytes()))
        assert nr['trace']==pr['trace'] and nr['controller_events']==pr['controller_events'] and nr['outcome']==pr['outcome']
        assert nr['network_policy_calls']==0
    if all(m in l['policy_loads'] for m in ('F0','S0')):assert l['policy_loads']['F0']['fingerprints']==l['policy_loads']['S0']['fingerprints']
    records={'development':{m:[] for m in ('B2','F0','S0','F2000','S2000')},
             'first_use_frozen_position_test':{m:[] for m in ('B2','F2000','S2000')}}
    audit_errors=[];costs=[];reward_rows=0
    for entry in l['episodes']:
        spec=entry['spec'];provider=spec['provider'];scope=spec['evaluation_scope']
        network=0 if provider=='B2' else entry.get('policy_calls',0)
        assert network==entry['network_policy_calls']
        costs.append(dict(id=entry['id'],provider=provider,status=entry['status'],control_cycles=entry.get('control_cycles',0),
            physical_substeps=entry.get('physical_substeps',0),network_policy_calls=network,wall_seconds=entry.get('wall_seconds',0)))
        fallback=dict(case_id=spec['case']['id'],comparison_key=config['common_key'],status='error',error=entry.get('error') or l.get('error'))
        if entry['status']!='finished' or not entry.get('evaluation_checks',{}).get('state_unchanged'):
            records[scope][provider].append(fallback);continue
        try:
            path=OUT/'run'/(entry['id']+'.json.gz');assert sha(path)==entry['archive_sha256']
            raw=json.loads(gzip.decompress(path.read_bytes()))
            assert raw['provider']==provider and raw['scope']==scope and raw['evaluation_scope']==scope and raw['case']==spec['case']
            assert raw['evaluation_qualification_sha256']==l['qualification_sha256'] and raw['evaluation_set_sha256']==config['evaluation_set_sha256']
            assert raw['comparison_key']==config['common_key'] and raw['network_policy_calls']==network
            assert raw['optimizer_steps_start']==raw['optimizer_steps']==l['policy_loads'][provider]['counts']['critic']
            assert raw['policy_sha256']==l['policy_loads'][provider]['fingerprints']['actor'] and raw['evaluation_checks']==entry['evaluation_checks']
            if provider=='B2':assert all(not any(float(x)!=0 for x in r[k]) for r in raw['actions'] for k in ('raw_action','requested_residual','applied_residual','effective_command_delta'))
            row=audit_raw(raw,config['common']);row['archive_sha256']=sha(path);row['provenance']='new_pc07'
            records[scope][provider].append(row);reward_rows+=len(raw['transitions'])
        except Exception as exc:
            audit_errors.append(dict(id=entry['id'],error=repr(exc)));records[scope][provider].append(fallback)
    for ref in config['inherited_development']:
        path=PRIOR/'run'/(ref['id']+'.json.gz');assert sha(path)==ref['archive_sha256']
        raw=json.loads(gzip.decompress(path.read_bytes()));assert raw['comparison_key']==config['common_key'] and raw['case']==ref['case']
        row=audit_raw(raw,config['common']);row['archive_sha256']=sha(path);row['provenance']='immutable_pc06'
        records['development']['F2000' if ref['mode']=='F50' else 'S2000'].append(row)
    expected={'development':[p['id'] for p in config['common']['cases']],
              'first_use_frozen_position_test':list(dict.fromkeys(s['case']['id'] for s in config['attempts'] if s['evaluation_scope']!='development'))}
    metrics={scope:{m:summarize(rows,expected[scope]) for m,rows in methods.items()} for scope,methods in records.items()}
    comparisons={}
    for scope,methods in records.items():
        pairs=[('B2','F2000'),('B2','S2000'),('F2000','S2000')]
        if scope=='development':pairs+=[('F0','F2000'),('S0','S2000')]
        comparisons[scope]={b+'_to_'+c:(compare(methods[b],methods[c],expected[scope]) if all(metrics[scope][m]['comparison_eligible'] for m in (b,c)) else None) for b,c in pairs}
    assert sum(e['network_policy_calls'] for e in l['episodes'])==l['network_policy_calls']
    result=dict(status=l['status'],new_attempts=len(l['episodes']),finished=sum(e['status']=='finished' for e in l['episodes']),cumulative=173+len(l['episodes']),
        unused_closed=l['unused_closed'],formal_updates=0,published_transitions=0,network_policy_calls=l['network_policy_calls'],
        control_cycles=sum(r['control_cycles'] for r in costs),physical_substeps=sum(r['physical_substeps'] for r in costs),
        wall_seconds=sum(r['wall_seconds'] for r in costs),costs=costs,records=records,metrics=metrics,comparisons=comparisons,
        audit_errors=audit_errors,independent_reward_rows_new=reward_rows,inherited_development_records=10,
        first_use_test_attempts=sum(e['spec']['evaluation_scope']!='development' for e in l['episodes']),
        first_use_positions=4,single_training_seed=True,paper_three_seed_evidence=False,stage_B2_complete=False,
        baseline_full_trace_continuity=continuity,execution_elapsed_seconds=(datetime.datetime.fromisoformat(l['ended_at'])-datetime.datetime.fromisoformat(l['started_at'])).total_seconds(),
        automatic_tracking='PAUSED',error=l.get('error'),scope='single_seed_frozen_comparison_not_paper_superiority')
    (OUT/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(canonical({k:v for k,v in result.items() if k not in ('costs','records','metrics','comparisons')}))
if __name__=='__main__':main()
