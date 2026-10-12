"""Read-only independent archive, stop, publication and frozen comparison audit."""
from pathlib import Path
import gzip,json,math,os,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
import numpy as np
from tools.learning.v4_pilot_contract import ROOT,sha,read,canonical
OUT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_v4_pilot_audit'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.validation.run_v4_learning_pilot import PilotAdmission,audit_evaluation
from tools.learning.v4_pilot_chain import audit_raw
from tools.learning.v4_checkpoint import read_checkpoint
from tools.validation.native313_matrix_audit import actual_stop_pass
from tools.validation.run_contact_candidate_stop import physical_tail_pass
from tools.validation.verify_admitted_collection import validate_outcome
from tools.evaluation.paper_comparison import summarize,compare

def hold(trace,stop,predicate):
    since=None
    for r in trace:
        if r['time_s']<stop-1e-10:continue
        if r['time_s']>stop+1.+1e-10:break
        if predicate(r):
            if since is None:since=r['time_s']
            if r['time_s']-since>=.1-1e-12:return True
        else:since=None
    return False

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    ledger=read(OUT/'run/ledger.json');config=read(OUT/'configuration.json')
    assert ledger['status'] in ('complete','controlled_stop','error') and ledger['unused_closed']==28-len(ledger['episodes'])
    admission=PilotAdmission(OUT,read(OUT/'qualification_pin.json')['sha256']);bindings={m:admission.verify(m) for m in ('F50','S50')}
    rows=[];finals=dict(F50=[],S50=[]);completed=published=0;errors=[]
    for entry in ledger['episodes']:
        spec=entry['spec'];base=dict(id=entry['id'],mode=spec['mode'],stage=spec['stage'],case_id=spec['case']['id'],status=entry['status'],
            control_cycles=entry.get('control_cycles'),physical_substeps=entry.get('physical_substeps'),wall_seconds=entry.get('wall_seconds'),policy_calls=entry.get('policy_calls'))
        if entry['status']!='finished':rows.append({**base,'error':entry.get('error')});continue
        path=OUT/'run'/(entry['id']+'.json.gz');assert sha(path)==entry['archive_sha256']
        raw=json.loads(gzip.decompress(path.read_bytes()));out=raw['outcome']
        stopped=bool(actual_stop_pass(raw['stop_samples'],raw['events'],raw['stop_time'],raw['audit_end_time_s'],.0002) and physical_tail_pass(raw['stop_samples'],raw['audit_end_time_s'],.0002))
        validate_outcome(raw,stopped=stopped)
        assert stopped==out['physical_stopped'] and out==entry['outcome']
        from tools.model.layered_task import functional_finish
        criteria=config['common']['finish_criteria'];peaks=raw['peaks']
        eligible=bool(out['simulation_valid'] and stopped and not any(out['guard_violations'].values()) and
            peaks['force_N']<criteria['force_N'] and peaks['torque_G_Nm']<criteria['torque_Nm'] and peaks['penetration_m']<criteria['penetration_m'])
        functional=bool(eligible and hold(raw['trace'],raw['stop_time'],lambda r:functional_finish(r,criteria)))
        assert functional==(out['task_outcome']=='FULL_SUCCESS')
        publication=entry.get('publication')
        try:
            if spec['stage'] in ('warmup','online'):audit_raw(raw,config['methods'][spec['mode']],bindings[spec['mode']])
            else:audit_evaluation(raw)
        except Exception as exc:errors.append(dict(id=entry['id'],audit_error=repr(exc)))
        if publication:
            chainpath=OUT/'run/chains'/spec['mode']/entry['id']
            assert read(chainpath/'status.json')==publication and sha(chainpath/'episode.json.gz')==publication['archive_sha256']
            assert canonical(json.loads(gzip.decompress((chainpath/'episode.json.gz').read_bytes())))==canonical(raw)
            published+=publication['committed']
        # Check duration and advance directly against the physical trace. Loads
        # are substep peaks, so endpoint wrench norms are only lower bounds.
        maximum=0.
        for i,t in enumerate(raw['transitions']):
            prev,r=raw['trace'][i:i+2]
            assert math.isclose(t['dt'],r['time_s']-prev['time_s'],rel_tol=0,abs_tol=1e-12)
            assert math.isclose(t['advance_m'],r['position_m'][2]-raw['trace'][0]['position_m'][2],rel_tol=0,abs_tol=1e-12)
            assert t['cycle_force_N']+1e-12>=np.linalg.norm(r['contact_wrench_M'][:3])
            assert t['cycle_torque_G_Nm']+1e-12>=np.linalg.norm(r['contact_wrench_G'][3:])
            new_max=max(maximum,min(.004,max(0.,t['advance_m'])))
            expected=dict(progress=5*(new_max-maximum)/.004,time=-.1*t['dt'],force=-.2*t['dt']*(t['cycle_force_N']/.025)**2,
                torque=-.2*t['dt']*(t['cycle_torque_G_Nm']/.0005)**2,
                terminal={'FULL_SUCCESS':10.,'TASK_FAILURE':-2.,'CONTACT_GUARD':-10.,'MOTION_VIOLATION':-10.,
                    'INVALID_SIMULATION':0.,'STOP_NOT_QUALIFIED':0.}[out['task_outcome']] if i==len(raw['transitions'])-1 else 0.)
            expected['total']=sum(expected.values());maximum=new_max
            assert expected.keys()==t['reward_terms'].keys() and all(math.isclose(v,t['reward_terms'][k],abs_tol=1e-12,rel_tol=0) for k,v in expected.items())
            assert math.isclose(expected['total'],t['reward'],abs_tol=1e-12,rel_tol=0)
            assert math.isclose(t['discount'],math.exp(-t['dt']/10),abs_tol=1e-12,rel_tol=0)
        completed+=1
        row={**base,'outcome':out['task_outcome'],'simulation_valid':out['simulation_valid'],'physical_stopped':stopped,
            'reason':raw['final_session']['reason'],'peak_force_mN':raw['peaks']['force_N']*1000,
            'peak_torque_mNm':raw['peaks']['torque_G_Nm']*1000,'task_end_time_s':raw['task_end_time_s'],
            'physical_end_time_s':raw['audit_end_time_s'],'active_rows':sum(t['action_active'] for t in raw['transitions']),
            'transitions':len(raw['transitions']),'committed':publication['committed'] if publication else 0,'functional_success_recomputed':functional,
            'optimizer_steps':raw['optimizer_steps'],'independent_reward_rows':len(raw['transitions']),'reference_problems':raw['reference_problems'],
            'max_actual_reference_radius_um':raw['max_actual_reference_radius_m']*1e6}
        rows.append(row)
        if spec['stage']=='final':
            from tools.validation.run_b1_baseline import geometric_finish
            from tools.model.layered_task import layered_pin_fit
            trace=raw['trace'];times=np.array([r['time_s'] for r in trace]);loads=np.linalg.norm([r['contact_wrench_M'][:3] for r in trace],axis=1)
            strict=bool(out['task_outcome']=='FULL_SUCCESS' and hold(trace,raw['stop_time'],lambda r:geometric_finish(r,config['common']['finish_criteria']) and layered_pin_fit(r)))
            facts=raw['guard_facts']
            finals[spec['mode']].append(dict(case_id=spec['case']['id'],comparison_key=config['common_key'],status='finished',outcome=out['task_outcome'],
                simulation_valid=out['simulation_valid'],physical_stopped=stopped,contact_guard=bool(facts['contact_reasons']),motion_violation=bool(facts['motion_reasons']),
                guard_reasons=facts['contact_reasons']+facts['motion_reasons'],task_end_time_s=raw['task_end_time_s'],physical_end_time_s=raw['audit_end_time_s'],
                peak_force_N=raw['peaks']['force_N'],peak_torque_Nm=raw['peaks']['torque_G_Nm'],strict_precision_success=strict,
                sampled_force_integral_N_s=float(np.sum((loads[1:]+loads[:-1])*.5*np.diff(times))),archive_sha256=sha(path)))
    checkpoints={}
    for mode in ('F50','S50'):
        entries=[e for e in ledger['episodes'] if e['spec']['mode']==mode and e.get('checkpoint')]
        if not entries:continue
        cp=entries[-1]['checkpoint'];state,(u,pool,_,_)=read_checkpoint(OUT/'run/checkpoints'/cp['label'],expected_digest=cp['pin'],expected_binding=bindings[mode],admission=admission)
        assert u.counts['critic']==ledger['per_branch_updates'][mode]
        checkpoints[mode]=dict(label=cp['label'],pin=cp['pin'],updates=u.counts,replay_rows=len(pool),attempts=len(state['attempts']),fingerprints=u.fingerprints())
    cases=[c['id'] for c in config['common']['cases']];baseline=read(ROOT/'deliverables/paper_comparison/protocol_v4_20261004/baseline_records.json')
    metrics={m:summarize(finals[m],cases) for m in finals}
    # Historical B2 has a different frozen control/source key. Do not relabel
    # those archives as this pilot's common version or claim a paired advantage.
    comparisons=dict(S_vs_B2=None,
        S_vs_F=compare(finals['F50'],finals['S50'],cases) if all(finals.values()) else None)
    signal=None
    result=dict(status=ledger['status'],attempts=len(rows),completed=completed,cumulative=config['prior_cumulative']+len(rows),unused_closed=ledger['unused_closed'],
        formal_update_attempts=ledger['formal_update_attempts'],formal_updates=ledger['formal_updates'],per_branch_updates=ledger['per_branch_updates'],
        policy_calls=ledger['policy_calls'],published_transitions=published,control_cycles=sum(r['control_cycles'] or 0 for r in rows),
        physical_substeps=sum(r['physical_substeps'] or 0 for r in rows),wall_seconds=sum(r['wall_seconds'] or 0 for r in rows),
        branches=ledger['branches'],rows=rows,audit_errors=errors,checkpoints=checkpoints,metrics=metrics,comparisons=comparisons,
        pilot_signal=signal,S_vs_F_signal=comparisons['S_vs_F']['pilot_signal'] if comparisons['S_vs_F'] else None,
        B2_baseline_comparison='not_rebound_historical_control_key_differs',historical_B2_context=baseline,
        training_admitted=True,stage_B2_complete=False,independent_tests=0,automatic_tracking='PAUSED',
        error=ledger.get('error'),scope='registered_development_pilot_not_independent_test')
    (OUT/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(canonical({k:v for k,v in result.items() if k not in ('rows','metrics','comparisons','checkpoints')}))

if __name__=='__main__':main()
