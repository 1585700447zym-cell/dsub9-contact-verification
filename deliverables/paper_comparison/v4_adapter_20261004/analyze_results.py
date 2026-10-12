"""Independent read-only archive checks after the bounded adapter run."""
from pathlib import Path
import json,gzip,hashlib,sys
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import numpy as np
from tools.validation.native313_matrix_audit import actual_stop_pass
from tools.validation.run_contact_candidate_stop import physical_tail_pass

def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
    ledger=read(OUT/'run/ledger.json');assert ledger['status']!='running'
    rows=[]
    for e in ledger['episodes']:
        if e['status']!='finished':
            rows.append(dict(id=e['id'],status=e['status'],error=e.get('error'),physical_substeps=e.get('physical_substeps'),control_cycles=e.get('control_cycles')))
            continue
        p=OUT/'run'/(e['id']+'.json.gz');assert sha(p)==e['archive_sha256']
        d=json.loads(gzip.decompress(p.read_bytes()));assert d['summary']=={k:v for k,v in e.items() if k!='archive_sha256'}
        stopped=bool(actual_stop_pass(d['stop_samples'],d['events'],e['stop_time'],e['end_time'],.0002)
                     and physical_tail_pass(d['stop_samples'],e['end_time'],.0002))
        assert stopped==e['outcome']['physical_stopped']
        equal=None;first_difference=None
        if e['spec']['profile']=='zero' and e['spec']['method']=='F50':
            oldpath=ROOT/'deliverables/task_variants/layered_referee_20261004/run'/(e['spec']['case_id']+'.json.gz')
            old=json.loads(gzip.decompress(oldpath.read_bytes()));equal=d['trace']==old['trace']
            for i,(x,y) in enumerate(zip(d['trace'],old['trace'])):
                if x!=y:
                    first_difference=dict(row=i,time_s=x['time_s'],fields=[k for k in x if x[k]!=y.get(k)]);break
            assert equal==e['equivalence']['trace_equal']
        trace=d['trace'];by_time={round(r['time_s'],8):r for r in trace}
        starts=[x for x in d['controller_events'] if x['reason']=='LOW_LOAD_SEARCH']
        ref_checks=ref_failures=0;maxradius=0.;command_error=0.;effects=np.zeros(4,dtype=int)
        masked_nonzero_requests=0;permission_checks=0
        for log in d['actions']:
            raw=np.asarray(log['raw_action'],dtype=float)
            assert raw.shape==(4,) and np.isfinite(raw).all() and (np.abs(raw)<=1).all()
            allowed=('INSERT','SEARCH') if e['spec']['method']=='F50' else ('SEARCH',)
            assert not log['enabled'] or log['policy_phase'] in allowed
            expected=raw if log['enabled'] else np.zeros(4)
            assert np.array_equal(log['experience_action'],expected)
            expected_residual=np.zeros(6);expected_residual[[0,1,3,4]]=expected*np.array([.00005,.00005,.0005,.0005])
            assert np.array_equal(log['applied_residual'],expected_residual)
            permission_checks+=1
            masked_nonzero_requests+=bool(not log['enabled'] and np.any(raw))
            r=trace[log['cycle']]
            if r['phase']=='RUNNING':
                command_error=max(command_error,float(np.max(np.abs(np.array(r['limited_command_world'])-log['predicted_limited_command']))))
                effects+=np.abs((np.array(r['limited_command_world'])-log['zero_residual_limited_command'])[[0,1,3,4]])>1e-15
            if not log.get('reference_checked') or r['phase']!='RUNNING':continue
            event=max((x for x in starts if x['time_s']<=log['command_time_s']+1e-9),key=lambda x:x['time_s'])
            origin=by_time[round(event['time_s'],8)]['position_m'][:2]
            radius=float(np.linalg.norm(np.array(r['reference_qpos'][:2])-origin))
            ref_checks+=1;maxradius=max(maxradius,radius);ref_failures+=radius>.00012+1e-12
        assert command_error<1e-12
        assert ref_checks==e['actual_reference_checks']
        assert bool(ref_failures)==e['actual_reference_failed']
        assert abs(maxradius-e['max_actual_reference_radius_m'])<1e-12
        if e['spec']['profile']=='pulse' and e['verification_passed']:assert all(effects)
        rows.append(dict(id=e['id'],status='finished',method=e['spec']['method'],profile=e['spec']['profile'],
            outcome=e['outcome']['task_outcome'],reason=e['reason'],simulation_valid=e['outcome']['simulation_valid'],
            physical_stopped=stopped,verification_passed=e['verification_passed'],trace_equal=equal,first_difference=first_difference,
            full_success=e['outcome']['task_outcome']=='FULL_SUCCESS',actual_reference_checks=ref_checks,
            actual_reference_failures=ref_failures,max_actual_reference_radius_um=maxradius*1e6,max_command_error=command_error,
            nonzero_physical_command_cycles=effects.tolist(),permission_checks=permission_checks,masked_nonzero_requests=masked_nonzero_requests,
            filter_cycles=e['filter_cycles'],observation_width=e['observation_width'],
            peak_force_mN=e['peaks']['force_N']*1000,xy_um=e['xy_um'],z_um=e['z_um'],pin_clearance_um=e['pin_clearance_um'],
            stop_time_s=e['stop_time'],task_end_time_s=e['task_end_time'],physical_end_time_s=e['end_time'],
            control_cycles=e['control_cycles'],physical_substeps=e['physical_substeps'],wall_seconds=e['wall_seconds']))
    finished=[r for r in rows if r['status']=='finished']
    passed=len(rows)==9 and len(finished)==9 and all(r['verification_passed'] and r['simulation_valid'] and r['physical_stopped'] for r in finished)
    summary=dict(status=ledger['status'],attempts=len(rows),completed=len(finished),unused_closed=ledger['unused_closed'],cumulative=130+len(rows),
        bounded_preflight_passed=passed,control_cycles=sum(r.get('control_cycles') or 0 for r in rows),physical_substeps=sum(r.get('physical_substeps') or 0 for r in rows),
        wall_seconds_completed=sum(r['wall_seconds'] for r in finished),rows=rows,training_updates=0,network_calls=0,independent_tests=0,
        training_admitted=False,stage_B2_complete=False,automatic_tracking='PAUSED')
    (OUT/'assessment.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},ensure_ascii=False))
    for r in rows:print(json.dumps(r,ensure_ascii=False))

if __name__=='__main__':main()
