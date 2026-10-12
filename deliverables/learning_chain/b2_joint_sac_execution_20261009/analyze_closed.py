"""Closeout reads only JSON/gzip/opaque checkpoint bytes; never loads torch tensors."""
from pathlib import Path
import gzip
import json
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];KIT=OUT.parent/'b2_joint_sac_preparation_20261009'
sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha,digest,canonical,schedule,validate_raw_identity,metric


def main():
    folder=OUT/'execution';counter=read(folder/'counter.json');closure=read(folder/'authorization_closure.json')
    if counter['status']!='CLOSED':raise PermissionError('Wait for the one execution to close')
    reg=read(OUT/'registration.json');grant=read(OUT/'grant.json')
    if digest(grant)!=reg['grant_sha256'] or closure['grant_sha256']!=reg['grant_sha256']:raise ValueError('Authorization identity differs')
    if closure.get('process_exit_confirmed') is not True:raise RuntimeError('Owned process tree exit not confirmed')
    for key,used in counter['attempted'].items():
        if type(used) is not int or not 0<=used<=counter['limits'][key] or counter['unused_closed'][key]!=counter['limits'][key]-used:raise ValueError('Quota does not close')
    ledger=read(folder/'run/ledger.json') if (folder/'run/ledger.json').exists() else {}
    specs=schedule();rows=[];raw_totals=dict(control_cycles=0,physical_substeps=0,policy_calls=0,observations=0)
    full={}
    for i,entry in enumerate(ledger.get('episodes',[])):
        spec=specs[i]
        if entry['id']!=spec['id']:raise ValueError('Attempt sequence drift')
        path=folder/'run'/(spec['id']+'.json.gz')
        result=dict(id=spec['id'],stage=spec['stage'],case_id=spec['case']['id'],status=entry['status'],healthy=entry.get('healthy',False))
        result['physical_reserved']=i<counter['attempted']['dynamic_episodes']
        if path.exists():
            raw=json.loads(gzip.decompress(path.read_bytes()));validate_raw_identity(raw)
            if raw['episode_id']!=spec['id'] or raw['qualification_sha256']!=reg['grant_sha256'] or raw['optimizer_steps']!=spec['optimizer_steps'] or raw['optimizer_steps_start']!=spec['optimizer_steps']:raise ValueError('Raw policy/authorization boundary differs')
            if raw['seed']!=2026092716 or raw['config_sha256']!=read(KIT/'candidate.json')['learning_config_sha256']:raise ValueError('Raw seed/config differs')
            if raw['control_cycles']!=len(raw['transitions']) or len(raw['trace'])!=raw['control_cycles']+1 or len(raw['actions'])!=raw['control_cycles']:raise ValueError('Incomplete cycle transcript')
            if entry.get('archive_sha256') and sha(path)!=entry['archive_sha256']:raise ValueError('Raw archive differs from receipt')
            raw_totals['control_cycles']+=raw['control_cycles'];raw_totals['physical_substeps']+=raw['physical_substeps']
            raw_totals['policy_calls']+=raw['policy_calls'];raw_totals['observations']+=len(raw['trace'])
            result.update(archive_sha256=sha(path),content_sha256=digest(raw),task_time_s=raw['task_end_time_s'],outcome=raw['outcome'],peaks=raw['peaks'],
                control_cycles=raw['control_cycles'],physical_substeps=raw['physical_substeps'],policy_calls=raw['policy_calls'],
                task_reason=raw['final_session']['reason'],wall_s=raw['wall_seconds'])
            full[spec['id']]=result
        else:
            result.update(incomplete=True,partial_cycles_lower_bound=entry.get('control_cycles',0),error=entry.get('error'))
            if not result['physical_reserved']:result['execution_class']='REGISTERED_NOT_STARTED_CLOSED'
        rows.append(result)
    events=[];journal=folder/'run/chain/update_journal.jsonl'
    if journal.exists():
        for line in journal.read_text(encoding='utf-8').splitlines():
            try:events.append(json.loads(line))
            except json.JSONDecodeError:events.append(dict(event='incomplete_line',raw=line))
    attempted_updates=sum(e.get('event')=='attempt' for e in events);completed_updates=sum(e.get('event')=='complete' for e in events)
    if not 0<=completed_updates<=attempted_updates<=counter['attempted']['formal_updates']:raise ValueError('Update attempts exceed reserve')
    receipts=[]
    for path in sorted((folder/'run/chain').glob('*/status.json')):
        receipt=read(path);rawpath=path.parent/'episode.json.gz'
        if sha(rawpath)!=receipt['archive_sha256']:raise ValueError('Replay publication source changed')
        # Collection and physical writers have different JSON whitespace, hence different gzip bytes.
        # Each receipt binds its own bytes; compare decoded full content across the two writers.
        replay_raw=json.loads(gzip.decompress(rawpath.read_bytes()))
        if receipt['episode_id'] not in full or digest(replay_raw)!=full[receipt['episode_id']]['content_sha256']:raise ValueError('Replay source is not matching new physical raw')
        receipts.append(receipt)
    checkpoints=[]
    for label in ('zero','final'):
        path=folder/'run/checkpoints'/label
        if (path/'manifest.json').exists():
            m=read(path/'manifest.json')
            if sha(path/'state.pt')!=m['state_sha256']:raise ValueError('Opaque checkpoint payload differs')
            request=read(folder/'run'/(label+'.request.json')) if (folder/'run'/(label+'.request.json')).exists() else None
            reply=read(folder/'run'/(label+'.reply.json')) if (folder/'run'/(label+'.reply.json')).exists() else None
            if reply and (request is None or request['state_digest']!=reply['state_digest']):raise ValueError('Independent full-state restore mismatch')
            checkpoints.append(dict(label=label,manifest_sha256=sha(path/'manifest.json'),state_sha256=m['state_sha256'],independent_restore_verified=reply is not None))
    assessment=read(folder/'assessment.json') if (folder/'assessment.json').exists() else None
    if assessment:
        for stage in ('zero','final'):
            r=[dict(case_id=row['case_id'],simulation_valid=row['outcome']['simulation_valid'],physical_stopped=row['outcome']['physical_stopped'],
                task_outcome=row['outcome']['task_outcome'],task_time_s=row['task_time_s'],guard=any(row['outcome']['guard_violations'].values())) for row in rows if row['stage']==stage and 'outcome' in row]
            if metric(r)!=assessment['scores'][stage]['metric']:raise ValueError('Independent task metric mismatch')
        ratio=1-assessment['scores']['final']['metric']['mean_penalized_time_s']/assessment['scores']['zero']['metric']['mean_penalized_time_s']
        if abs(ratio-assessment['relative_improvement'])>1e-12:raise ValueError('Relative time metric mismatch')
    if closure['status']=='CLOSED_COMPLETE':
        if len(rows)!=17 or not all(r['healthy'] for r in rows) or completed_updates!=2000 or len(receipts)!=8 or len(checkpoints)!=2 or not all(c['independent_restore_verified'] for c in checkpoints):raise ValueError('Incomplete supposedly completed run')
    summary=dict(stage_id='B2-SCOPE-13',status=closure['status'],process_exit_confirmed=True,
        cumulative_before=237,cumulative_dynamic=237+counter['attempted']['dynamic_episodes'],
        attempts=counter['attempted']['dynamic_episodes'],complete_raw_archives=len(full),healthy_completed=sum(r['healthy'] for r in rows),
        counts_reserved_upper_bounds=counter['attempted'],closed_unused=counter['unused_closed'],actual_complete_raw_costs=raw_totals,
        update_attempts=attempted_updates,updates_completed=completed_updates,replay_publications_completed=len(receipts),
        replay_rows=sum(r.get('committed',0) for r in receipts),episodes=rows,checkpoints=checkpoints,assessment=assessment,
        independent_tests=0,full_B2_accepted=False,C_accepted=False,training_admitted=False,automatic_tracking='PAUSED',no_retry=True)
    write(OUT/'execution_summary.json',summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ('episodes','assessment','closed_unused','counts_reserved_upper_bounds')},ensure_ascii=False))


if __name__=='__main__':main()
