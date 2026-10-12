"""Summarize already-recorded physical and update results after durable closure."""
import gzip,json,sys
from datetime import datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
KIT=HERE.parent/'b2_joint_sac_continuation_preparation_20261009';sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha,metric,schedule
from continuation_contract import baseline_rows

if __name__=='__main__':
    if (HERE/'execution_summary.json').exists():raise FileExistsError('Preserve first closeout summary')
    closure=read(HERE/'authorization_closure.json');counter=read(HERE/'counter.json');ledger=read(HERE/'run/ledger.json')
    if counter['status']!='CLOSED' or not closure['process_exit_confirmed']:raise PermissionError('Summary requires closed counter and owned exit')
    episodes=[];final_rows=[];physical=[]
    for entry in ledger['episodes']:
        record=dict(entry)
        path=HERE/'run'/(entry['id']+'.json.gz')
        if path.exists():
            raw=json.loads(gzip.decompress(path.read_bytes()));out=raw['outcome']
            record.update(task_time_s=raw['task_end_time_s'],audit_end_time_s=raw['audit_end_time_s'],optimizer_steps=raw['optimizer_steps'],
                          policy_sha256=raw['policy_sha256'],peaks=raw['peaks'],source_sha256=sha(path),
                          control_cycles=raw['control_cycles'],physical_substeps=raw['physical_substeps'],policy_calls=raw['policy_calls'])
            physical.append(record)
            if raw['stage']=='final':final_rows.append(dict(case_id=raw['case_id'],simulation_valid=out['simulation_valid'],physical_stopped=out['physical_stopped'],
                  task_outcome=out['task_outcome'],task_time_s=raw['task_end_time_s'],guard=any(out['guard_violations'].values()),peaks=raw['peaks']))
        episodes.append(record)
    records=[];path=HERE/'run/chain/update_journal.jsonl'
    if path.exists():records=[json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
    completed=[r for r in records if r['event']=='complete'];attempts=[r for r in records if r['event']=='attempt'];errors=[r for r in records if r['event']=='error']
    zero=baseline_rows();scores=dict(zero=dict(rows=zero,metric=metric(zero)))
    comparison=[];improvement=None;passed=False
    if len(final_rows)==4:
        scores['final']=dict(rows=final_rows,metric=metric(final_rows));f0=scores['zero']['metric'];f2=scores['final']['metric']
        if f0['comparable'] and f2['comparable'] and f0['mean_penalized_time_s']>0:
            improvement=1-f2['mean_penalized_time_s']/f0['mean_penalized_time_s']
        passed=closure['status']=='CLOSED_COMPLETE' and improvement is not None and improvement>=.10 and f2['success_count']==4 and not f2['guards']
        for base,after in zip(zero,final_rows):
            if base['case_id']!=after['case_id']:raise ValueError('Comparison case mismatch')
            z=base['task_time_s'] if base['task_outcome']=='FULL_SUCCESS' else 26.
            f=after['task_time_s'] if after['task_outcome']=='FULL_SUCCESS' else 26.
            comparison.append(dict(case_id=base['case_id'],F0_outcome=base['task_outcome'],F2000_outcome=after['task_outcome'],
                                   F0_penalized_s=z,F2000_penalized_s=f,relative_improvement=1-f/z))
    counts=completed[-1]['counts'] if completed else dict(critic=0,actor=0,temperature=0,target=0)
    actual_cycles=sum(r.get('control_cycles',0) for r in episodes);actual_substeps=sum(r.get('physical_substeps',0) for r in episodes)
    summary=dict(stage_id='B2-SCOPE-20',closeout_date=datetime.now().strftime('%Y-%m-%d'),execution_status=closure['status'],
                 reserved_operations=counter['attempted'],unused_closed=counter['unused_closed'],episodes=episodes,
                 completed_physical=sum(e.get('status')=='finished' for e in episodes),physical_attempts=len(episodes),
                 actual_control_cycles=actual_cycles,actual_native_steps=actual_substeps,actual_policy_calls=ledger.get('policy_calls',0),
                 update_attempts=len(attempts),completed_updates=len(completed),update_errors=errors,optimizer_counts=counts,
                 startup_restore_passed=ledger.get('warm_state_restore_verified') is True,
                 scores=scores,comparison=comparison,relative_improvement=improvement,development_continue=passed,
                 cumulative_attempt_upper_bound=245+counter['attempted']['dynamic_episodes'],
                 cumulative_dynamic=254 if closure['status']=='CLOSED_COMPLETE' else None,
                 independent_tests=0,full_B2_accepted=False,C_accepted=False,automatic_tracking='PAUSED',training_admitted=False,no_retry=True,
                 supervisor_wall_s=read(HERE/'supervisor.supervisor.json')['wall_seconds'])
    write(HERE/'execution_summary.json',summary)
    print(json.dumps({k:summary[k] for k in ('execution_status','completed_physical','completed_updates','relative_improvement','development_continue','cumulative_dynamic')},ensure_ascii=False))
