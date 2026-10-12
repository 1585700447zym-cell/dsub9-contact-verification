"""Offline archive statistics only; no simulator, policy inference or optimizer."""
import gzip
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean

D = Path(__file__).resolve().parent
R = D / 'run'
bindings = {}


def load(path):
    data = path.read_bytes()
    bindings[str(path.relative_to(D))] = hashlib.sha256(data).hexdigest()
    return json.loads(gzip.decompress(data) if path.suffix == '.gz' else data)


def norm(a):
    return math.sqrt(sum(x*x for x in a))


def action_stats(rows):
    active = [r for r in rows if r['action_active']]
    if not active:
        return {'active_cycles': 0}
    logs = [r['action_log'] for r in active]
    actions = [r['action'] for r in active]
    return dict(active_cycles=len(active),
        mean_normalized_action=[mean(a[j] for a in actions) for j in range(4)],
        near_bound_fraction=[mean(abs(a[j]) >= .95 for a in actions) for j in range(4)],
        changed_by_total_limits_fraction=mean(any(abs(x-y)>1e-15 for x,y in
            zip(l['effective_command_delta'],l['applied_residual'])) for l in logs),
        requested_translation_speed_mean=mean(norm(l['applied_residual'][:3]) for l in logs),
        effective_translation_delta_mean=mean(norm(l['effective_command_delta'][:3]) for l in logs),
        requested_rotation_speed_mean=mean(norm(l['applied_residual'][3:]) for l in logs),
        effective_rotation_delta_mean=mean(norm(l['effective_command_delta'][3:]) for l in logs))


def summarize(raw, group):
    rows=raw['transitions']
    def angle(row):
        q=row['trace_row']['quaternion_wxyz']
        return math.degrees(2*math.acos(min(1.,abs(q[0])/norm(q))))
    tail=[r for r in rows if r['trace_row']['time_s']>=raw['stop_time']]
    return dict(group=group,id=raw['episode_id'],case=raw['case'],
        updates_at_start=raw['optimizer_steps_start'],mode=raw.get('sampling_mode',raw.get('evaluation_method')),
        outcome=raw['outcome'],cycles=len(rows),reward=sum(r['reward'] for r in rows),
        final_xy_um=norm(rows[-1]['trace_row']['position_m'][:2])*1e6,
        final_z_um=rows[-1]['trace_row']['position_m'][2]*1e6,
        final_angle_deg=angle(rows[-1]),stop_tail_min_sampled_angle_deg=min(map(angle,tail)),
        final_reason=raw['final_session']['reason'],
        cycle_end_penetration_peak_um=max(r['trace_row']['penetration_m'] for r in rows)*1e6,
        recovery_resumed=any(e['reason']=='B2_RECOVERY_RESUMED' for e in raw['events']),
        events=raw['events'],actions=action_stats(rows))


def snapshot(row):
    t=row['trace_row'];log=row['action_log']
    return dict(time_s=t['time_s'],position_m=t['position_m'],
        penetration_um=t['penetration_m']*1e6,phase=t['phase'],
        policy_phase=t['policy_phase'],recovery_state=t['recovery_state'],
        action_active=row['action_active'],action=row['action'],
        applied_residual=log['applied_residual'],effective_delta=log['effective_command_delta'],
        zero_residual_limited_command=log['zero_residual_limited_command'],
        actual_end_limited_command=log['actual_end_limited_command'])


def main():
    episodes=[]
    for group,folder in [('baseline',R/'baseline/episodes'),('initial',R/'initial/episodes'),('training',R/'training_episodes')]:
        for path in sorted(folder.glob('*/episode.json.gz')):
            raw=load(path);episodes.append(summarize(raw,group))
            if group=='training' and raw['episode_id']=='train_09':failed=raw
    assert len(episodes)==18
    updates=load(R/'training/updates.json');assert len(updates)==3000
    blocks=[]
    for start in range(0,3000,500):
        b=updates[start:start+500]
        blocks.append(dict(first=start+1,last=start+500,
            critic_loss_mean=mean(r['critic_loss'] for r in b),
            actor_loss_mean=mean(r['actor_loss'] for r in b if r['actor_loss'] is not None),
            alpha_end=b[-1]['alpha_after'],exact_rows_mean=mean(r['exact_target_rows'] for r in b),
            boundary_draws=sum(len(r['boundary_indices']) for r in b),
            boundary_episode_draws=dict(Counter(k for r in b for k,i in r['boundary_indices']))))
    event=next(e for e in failed['events'] if e['reason']=='PENETRATION_LIMIT')
    trigger_index=next(i for i,r in enumerate(failed['transitions'])
        if any(e['reason']=='PENETRATION_LIMIT' for e in r['events']))
    assert not failed['transitions'][trigger_index]['next_action_active']
    assert all(not r['action_active'] and r['action']==[0.,0.,0.,0.]
        for r in failed['transitions'][trigger_index+1:])
    resume=next(e for e in failed['events'] if e['reason']=='B2_RECOVERY_RESUMED')
    samples=[]
    for t in [9.178,9.256,9.805,9.828,10.,10.5,10.7,event['time_s'],10.766,12.766]:
        samples.append(snapshot(min(failed['transitions'],key=lambda r:abs(r['trace_row']['time_s']-t))))
    windows=[]
    for lo,hi in [(0,resume['time_s']),(resume['time_s'],event['time_s']),(event['time_s'],failed['audit_end_time_s']+.001)]:
        rows=[r for r in failed['transitions'] if lo<=r['trace_row']['time_s']<hi]
        windows.append(dict(start=lo,end=hi,cycles=len(rows),actions=action_stats(rows),
            cycle_end_penetration_peak_um=max(r['trace_row']['penetration_m'] for r in rows)*1e6))
    counts={g:dict(Counter(e['outcome']['task_outcome'] for e in episodes if e['group']==g)) for g in ['baseline','initial','training']}
    report=dict(scope='archived trajectories and update logs; no new trajectories or optimization',
        outcome_counts=counts,episodes=episodes,update_blocks=blocks,
        failure=dict(events=failed['events'],resume_to_guard_s=event['time_s']-resume['time_s'],
            snapshots=samples,windows=windows,all_cycles_after_trigger_inactive=True),evidence_sha256=bindings,
        limitations=['Stochastic training episodes use different policies and are not a fixed evaluation.',
                    'Cycle-end penetration samples do not reconstruct the exact substep peak.',
                    'Command delta is a local same-state comparison, not a zero-residual trajectory.',
                    'No post-training deterministic evaluation exists; no causal attribution to one change.'])
    for name,pin in bindings.items():assert hashlib.sha256((D/name).read_bytes()).hexdigest()==pin
    (D/'policy_analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    for e in episodes:
        a=e['actions'];print(e['group'],e['id'],e['updates_at_start'],e['outcome']['task_outcome'],
            'xy_um',round(e['final_xy_um'],2),'peak_um',round(e['cycle_end_penetration_peak_um'],3),
            'near_bound',[round(x,3) for x in a.get('near_bound_fraction',[])],
            'limited',round(a.get('changed_by_total_limits_fraction',0),3),'recovery',e['recovery_resumed'])
    print('update_blocks',json.dumps(blocks));print('failure',json.dumps(report['failure']))


if __name__=='__main__':main()
