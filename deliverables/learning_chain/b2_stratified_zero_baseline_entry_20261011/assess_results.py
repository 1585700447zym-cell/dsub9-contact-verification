"""Read-only science-free analysis of a closed finite stratified B2 package."""
import csv
import gzip
import importlib.util
import math
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import baseline_entry  # installs the standard-library preflight import guard
import scope_contract as c
from baseline_rollout import audit_baseline
_previous=None


def previous_assessor():
    global _previous
    if _previous is None:
        spec=importlib.util.spec_from_file_location('stratified_previous_assessor',c.PREV/'assess_results.py')
        _previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(_previous)
    return _previous


def require_closed(ledger,closure):
    if (ledger.get('status') not in ('CLOSED_COMPLETE','CLOSED_EARLY','CLOSED_ERROR') or
        closure.get('status')!=ledger['status'] or closure.get('no_retry') is not True or
        closure.get('claimed_attempts')!=len(ledger['episodes']) or closure.get('unused_closed')!=21-len(ledger['episodes']) or
        closure.get('grant_sha256')!=ledger.get('grant_sha256') or len(ledger['episodes'])>21):
        raise ValueError('Closed single-use package and consistent closure required')


def summarize(rows,expected_ids):
    ids=[r['case_id'] for r in rows]
    if len(set(ids))!=len(ids) or not set(ids)<=set(expected_ids):raise ValueError('Duplicate or unregistered summary case')
    costs=[];successful=[];ordinary=0
    for row in rows:
        value=row['task_time_s']
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('Finite nonnegative task time required')
        valid=row['simulation_valid'] is True and row['physical_stopped'] is True and row['guard'] is False
        if valid and row['task_outcome']=='FULL_SUCCESS':costs.append(value);successful.append(value)
        elif valid and row['task_outcome']=='TASK_FAILURE':costs.append(26.);ordinary+=1
    complete=set(ids)==set(expected_ids) and len(costs)==len(expected_ids)
    def quantile(fraction):
        if not successful:return None
        ordered=sorted(successful);index=(len(ordered)-1)*fraction;low=int(index);high=math.ceil(index)
        return ordered[low]+(ordered[high]-ordered[low])*(index-low)
    return dict(available=len(rows),expected=len(expected_ids),missing=[i for i in expected_ids if i not in ids],
        functional_successes=len(successful),ordinary_failures=ordinary,
        guards=sum(r['guard'] is True for r in rows),invalid=sum(r['simulation_valid'] is not True for r in rows),
        unstopped=sum(r['physical_stopped'] is not True for r in rows),complete_valid_stopped_matrix=complete,
        mean_penalized_time_s=math.fsum(costs)/len(costs) if complete and costs else None,
        success_conditioned_mean_s=math.fsum(successful)/len(successful) if successful else None,
        success_min_s=min(successful) if successful else None,success_max_s=max(successful) if successful else None,
        success_p50_s=quantile(.5),success_p90_s=quantile(.9),quantile_rule='linear_on_sorted_index_(n-1)*p',
        additional_precision=sum(r.get('functional_plus_precision') is True for r in rows))


def cost_summary(entries):
    fields=dict(environment_creation_attempts='environment_creation_attempted',environments_created_recorded='environment_created',
        reset_attempts='reset_attempted',resets_completed_recorded='reset_completed',
        control_cycles_recorded='control_cycles',native_steps_recorded='physical_substeps')
    totals={key:sum(row.get(field,0) for row in entries if type(row.get(field)) is int) for key,field in fields.items()}
    unknown=sum(row.get('operation_counts_known') is not True for row in entries)
    lower=258+totals['reset_attempts']
    return dict(**totals,claimed_slots=len(entries),unknown_operation_attempts=unknown,
        control_counts_complete=all(row.get('receipt_costs_complete') is True for row in entries),
        cumulative_dynamic=lower if unknown==0 else None,cumulative_dynamic_range=[lower,lower+unknown],
        count_basis='observed charged reset attempts; reservations separate; incomplete control counts are lower bounds',
        policy_calls=sum(row.get('policy_calls',0) for row in entries),formal_updates=sum(row.get('formal_updates',0) for row in entries))


def assess_entry(entry,path,config,index):
    fault=dict(case_id=entry['case_id'],status=entry.get('status'),retained_attempt=True,
        archive_path=str(path),final_supervision=entry.get('supervisor',{}))
    if entry.get('status')!='finished' or not path.exists():
        return None,dict(fault,reason='no_complete_archive',error=entry.get('error'))
    try:
        if c.sha(path)!=entry['archive_sha256']:raise ValueError('New archive pin differs')
        raw=__import__('json').loads(gzip.decompress(path.read_bytes()))
        if raw['attempt_index']!=index:raise ValueError('Charged attempt index differs')
        row=record(raw,path,config)
    except (ValueError,KeyError,TypeError,AssertionError,OSError,EOFError,IndexError,OverflowError) as exc:
        return None,dict(fault,reason='archive_audit_failed',error=repr(exc),retained_archive_sha256=c.sha(path))
    supervisor=entry.get('supervisor',{})
    exited=supervisor.get('go_issued') is True and supervisor.get('process_exit_confirmed') is True and supervisor.get('owned_launcher_exit_confirmed') is True and type(supervisor.get('returncode')) is int and supervisor['returncode']==0
    initial=entry.get('initial_audit',{}).get('passed') is True
    expected_healthy=row['simulation_valid'] is True and row['physical_stopped'] is True and row['guard'] is False and row['task_outcome'] in ('FULL_SUCCESS','TASK_FAILURE')
    if not exited or not initial or entry.get('healthy') is not expected_healthy or (expected_healthy and not c.receipt_healthy(entry)):
        return None,dict(fault,reason='supervision_or_receipt_incomplete',archived_summary=row,
                         counted_as_functional_success=False,counted_in_matrix_mean=False)
    return row,None


def reused_records():
    old=c.read(c.PREV/'assessment.json');config=c.read(c.OLD/'configuration.json')
    geom=c.read(c.PREV/'geometry_assessment.json')['rows'];rows=[]
    aliases={'J01':'J11','J02':'J22','J03':'J33','J04':'J44'}
    for original in old['records']:
        if original['role']!='pure_B2':continue
        if c.sha(original['archive_path'])!=original['sha256']:raise ValueError('Old B2 archive changed')
        clearance=next(g for g in geom if g['role']=='pure_B2' and g['case_id']==original['case_id'])
        rows.append(dict(original,case_id=aliases[original['case_id']],original_case_id=original['case_id'],
            original_comparison_key=config['common_key'],reused=True,group='joint',
            task_end_clearance_um=clearance['task_end_clearance_um'],audit_end_clearance_um=clearance['audit_end_clearance_um']))
    if [r['case_id'] for r in rows]!=['J11','J22','J33','J44']:raise ValueError('Exactly four matched original B2 records required')
    return rows


def record(raw,path,config):
    if raw['scope']!='stratified_zero_B2_development' or raw['shared_common_key']!=config['parent_common_key']:
        raise ValueError('New development archive identity differs')
    healthy=audit_baseline(raw,config);p=previous_assessor();analysis=p.analysis
    times=analysis.validate_alignment(raw)
    phases=analysis.time_parts(times,[analysis.phase_of(t['observation'],raw['observation_schema']) for t in raw['transitions']],raw['task_end_time_s'])
    if abs(math.fsum(phases.values())-raw['task_end_time_s'])>1e-9:raise ValueError('Task phase accounting differs')
    stopped=p.stop_pass(raw)
    if stopped!=raw['outcome']['physical_stopped']:raise ValueError('Saved stop samples disagree with actual outcome')
    final=analysis.precise(raw['trace'][-1]);out=raw['outcome'];point=raw['case']
    task_index=min(range(len(times)),key=lambda i:abs(times[i]-raw['task_end_time_s']))
    if abs(times[task_index]-raw['task_end_time_s'])>1e-9:raise ValueError('Task end row missing')
    geometry=raw['geometry_evidence']
    if geometry['referee_id']!=config['common']['geometry_referee']['id'] or geometry['analytic_saved_pose_only'] is not True or geometry['new_physical_steps']!=0:
        raise ValueError('Saved-pose geometry identity differs')
    def margin(item):
        if item['status']=='no_main_overlap' and item['value_m'] is None:return None
        value=item['value_m']
        if item['status']!='finite' or type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Invalid archived geometry margin')
        return value*1e6
    return dict(case_id=point['id'],group=next(r['group'] for r in config['case_metadata'] if r['id']==point['id']),
        reused=False,archive_path=str(path),sha256=c.sha(path),simulation_valid=out['simulation_valid'],
        physical_stopped=stopped,guard=any(out['guard_violations'].values()),task_outcome=out['task_outcome'],
        functional_success=healthy and out['task_outcome']=='FULL_SUCCESS',task_time_s=raw['task_end_time_s'],
        phase_times_s=phases,final_reason=raw['final_session']['reason'],
        force_mN=raw['peaks']['force_N']*1000,torque_G_mNm=raw['peaks']['torque_G_Nm']*1000,
        penetration_um=raw['peaks']['penetration_m']*1e6,final_xy_um=final['xy_um'],final_angle_deg=final['angle_to_identity_deg'],
        task_end_pose=analysis.precise(raw['trace'][task_index]),functional_plus_precision=healthy and out['task_outcome']=='FULL_SUCCESS' and final['additional_80um_0p5deg'],
        task_end_clearance_um=margin(geometry['task_end']),audit_end_clearance_um=margin(geometry['audit_end']),
        search_entries=sum(e['phase']=='SEARCH' for e in raw['controller_events']),
        unload_entries=sum(e['phase']=='UNLOAD' for e in raw['controller_events']),
        requested_applied_effective_residuals_all_zero=True,
        physical_XY_path_um=math.fsum(math.dist(a['position_m'][:2],b['position_m'][:2]) for a,b in zip(raw['trace'][:task_index],raw['trace'][1:task_index+1]))*1e6,
        control_cycles=raw['control_cycles'],physical_substeps=raw['physical_substeps'],wall_seconds=raw['wall_seconds'])


def main():
    _,config=c.verify_binding();execution=OUT/'execution';ledger=c.read(execution/'ledger.json')
    closure=c.read(execution/'authorization_closure.json');require_closed(ledger,closure)
    target=execution/'assessment.json'
    if target.exists():raise FileExistsError('Preserve first actual result assessment')
    rows=reused_records();incomplete=[]
    for index,entry in enumerate(ledger['episodes']):
        if entry['case_id']!=c.new_cases()[index]['id']:raise ValueError('Recorded attempt order differs')
        path=execution/('case_'+str(index))/'episode.json.gz'
        row,fault=assess_entry(entry,path,config,index)
        if row is not None:rows.append(row)
        if fault is not None:incomplete.append(fault)
    summary=summarize(rows,[p['id'] for p in c.registered_cases()])
    strata={group:summarize([r for r in rows if r['group']==group],
        [p['id'] for p in config['case_metadata'] if p['group']==group])
        for group in ('aligned','position_only','orientation_only','joint')}
    costs=cost_summary(ledger['episodes'])
    result=dict(status=ledger['status'],assessed_at=c.now(),records=rows,incomplete_attempts=incomplete,costs=costs,
        all_attempts=ledger['episodes'],summary=summary,strata=strata,matrix_scope_key=config['common_key'],
        old_scope_aliases_preserved=True,data_use='development',new_attempts=len(ledger['episodes']),
        cumulative_dynamic=costs['cumulative_dynamic'],cumulative_dynamic_range=costs['cumulative_dynamic_range'],policy_calls=0,formal_updates=0,
        independent_tests=0,training_admitted=False,nonzero_SAC_qualified=False,full_B2_accepted=False,C_accepted=False)
    c.write(target,result)
    with (execution/'comparison.csv').open('x',encoding='utf-8-sig',newline='') as stream:
        keys=['case_id','group','reused','task_outcome','simulation_valid','physical_stopped','guard','task_time_s','final_xy_um','final_angle_deg','task_end_clearance_um','audit_end_clearance_um']
        writer=csv.DictWriter(stream,fieldnames=keys,extrasaction='ignore');writer.writeheader();writer.writerows(rows)
    print(c.canonical(dict(status=result['status'],summary=summary,new_attempts=result['new_attempts'])))


if __name__=='__main__':main()
