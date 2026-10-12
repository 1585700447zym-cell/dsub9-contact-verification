"""Offline stop/outcome/action and file audits only; standard library only."""
import gzip
import hashlib
import json
import math
from pathlib import Path

D=Path(__file__).resolve().parent
ROOT=D.parents[2]
PREVIOUS=ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928'
inputs={}


def load(path):
    b=path.read_bytes();inputs[path.relative_to(ROOT).as_posix()]=hashlib.sha256(b).hexdigest()
    return json.loads(gzip.decompress(b) if path.suffix=='.gz' else b)


def norm(v):return math.sqrt(sum(x*x for x in v))


def angle(row):
    q=row['trace_row']['quaternion_wxyz']
    return math.degrees(2*math.acos(min(1.,abs(q[0])/norm(q))))


def tail_pass(rows,end):
    dt=.0002;tail=[r for r in rows if r['time_s']>=end-.1-dt/2]
    if not tail or tail[0]['time_s']>end-.1+dt/2 or abs(tail[-1]['time_s']-end)>dt/2:return False
    if any(not 0<b['time_s']-a['time_s']<=dt*1.01 for a,b in zip(tail,tail[1:])):return False
    return all(math.isfinite(r['linear_m_s']) and math.isfinite(r['angular_rad_s']) and
        r['linear_m_s']<=1e-5 and r['angular_rad_s']<=.001 for r in tail)


def audit(raw,group):
    rows=raw['transitions'];facts=raw['guard_facts'];phase=None;start=None
    for e in raw['events']:
        now=e.get('phase')
        if now is None:continue
        if now=='STOPPING':
            if phase!='STOPPING':start=e['time_s']
        else:start=None
        phase=now
    assert start is not None and raw['audit_end_time_s']>=start+2.-1e-9
    deadline=start+2.
    stopped=tail_pass([r for r in raw['stop_samples'] if r['time_s']<=deadline+.0001],deadline)
    stopped=stopped and tail_pass(raw['stop_samples'],raw['audit_end_time_s'])
    assert stopped and raw['outcome']['physical_stopped']
    assert facts['simulation_valid'] and not facts['invalid_reasons']
    clear=not facts['contact_reasons'] and not facts['motion_reasons']
    assert raw['guard_clear']==clear
    expected='CONTACT_GUARD' if facts['contact_reasons'] else ('MOTION_VIOLATION' if facts['motion_reasons'] else
        ('FULL_SUCCESS' if raw['final_session']['reason']=='GEOMETRIC_SUCCESS' else 'TASK_FAILURE'))
    assert raw['outcome']['task_outcome']==expected
    assert raw['outcome']['valid_for_learning']==bool(stopped and clear)
    scale=[.00015,.00015,.005,.005] if group=='baseline' else [.00015,.00015,.0005,.0005]
    forces=[];torques=[]
    for r in rows:
        log=r['action_log'];a=log['raw_action'];enabled=log['enabled']
        requested=[a[0]*scale[0],a[1]*scale[1],0.,a[2]*scale[2],a[3]*scale[3],0.]
        assert all(math.isclose(x,y,rel_tol=0.,abs_tol=1e-18) for x,y in zip(requested,log['requested_residual']))
        assert log['applied_residual']==(requested if enabled else [0.]*6)
        assert r['action']==(a if enabled else [0.]*4)
        forces.append(.025*math.sqrt(max(0.,-r['reward_terms']['force']/(.2*r['dt']))))
        torques.append(.0005*math.sqrt(max(0.,-r['reward_terms']['torque']/(.2*r['dt']))))
    active=[r for r in rows if r['action_active']]
    return dict(group=group,id=raw['episode_id'],case=raw['case'],outcome=expected,cycles=len(rows),
        updates_at_start=raw['optimizer_steps_start'],physical_audit_pass=True,guard_clear=clear,
        final_xy_um=norm(rows[-1]['trace_row']['position_m'][:2])*1e6,
        final_z_um=rows[-1]['trace_row']['position_m'][2]*1e6,final_angle_deg=angle(rows[-1]),
        max_substep_rotation_deg=math.degrees(facts['max_rotation_from_start_rad']),
        final_reason=raw['final_session']['reason'],force_peak_N=max(forces),torque_peak_Nm=max(torques),
        sampled_penetration_peak_um=max(r['trace_row']['penetration_m'] for r in rows)*1e6,
        task_stop_time_s=raw['stop_time'],audit_end_time_s=raw['audit_end_time_s'],
        roll_near_bound_fraction=sum(abs(r['action'][2])>=.95 for r in active)/len(active),
        pitch_near_bound_fraction=sum(abs(r['action'][3])>=.95 for r in active)/len(active),events=raw['events'])


def main():
    assert not (D/'assessment.json').exists()
    qualification=load(D/'admission.json')
    assert inputs[(D/'admission.json').relative_to(ROOT).as_posix()]=='d6ac62ef7e0114ab5c042b666ed69b29ad11df9663f6c5a1ff92c5a728ec71e2'
    for table in ('source_sha256','evidence_sha256'):
        for name,pin in qualification[table].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==pin,name
    old_files=load(D/'previous_files.json')
    for name,pin in old_files.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==pin,name
    exit_record=load(D/'process_exit.json');assert exit_record['returncode']==1
    ledger=load(D/'run/ledger.json');budget=load(D/'run/cumulative_budget.json')
    assert ledger['status']=='failed' and ledger['dynamic_starts']==len(ledger['attempts'])==9
    assert budget['cumulative_dynamic_starts']==36
    episodes=[];published=0
    for group,folder in [('baseline',PREVIOUS/'run/baseline/episodes'),('initial',D/'run/initial/episodes'),('training',D/'run/training_episodes')]:
        for path in sorted(folder.glob('*/episode.json.gz')):
            raw=load(path);status=load(path.with_name('status.json'))
            assert status['archive_sha256']==inputs[path.relative_to(ROOT).as_posix()]
            row=audit(raw,group);episodes.append(row)
            if group=='training':
                published+=status['committed']
                assert status['committed']==(len(raw['transitions']) if row['guard_clear'] else 0)
                if raw['episode_id']=='train_04':failure=raw
    assert len(episodes)==13
    updates=load(D/'run/training/updates.json');update_budget=load(D/'run/training_episodes/update_budget.json')
    assert len(updates)==update_budget['attempted']==update_budget['completed']==500
    assert all(math.isfinite(r[k]) for r in updates for k in ['critic_loss','alpha_after'])
    checkpoints=load(D/'run/training/checkpoints.json');assert len(checkpoints)==4
    for c in checkpoints:
        path=D/'run'/c['path'];manifest=load(path/'manifest.json')
        assert inputs[(path/'manifest.json').relative_to(ROOT).as_posix()]==c['sha256']
        assert hashlib.sha256((path/'state.pt').read_bytes()).hexdigest()==manifest['state_sha256']
    trigger=next(e for e in failure['events'] if e['reason']=='FORCE_LIMIT')
    resume=next(e for e in failure['events'] if e['reason']=='B2_RECOVERY_RESUMED')
    index=next(i for i,r in enumerate(failure['transitions']) if any(e['reason']=='FORCE_LIMIT' for e in r['events']))
    assert failure['transitions'][index]['next_action_active'] is False
    assert all(not r['action_active'] and r['action']==[0.]*4 for r in failure['transitions'][index+1:])
    initial=load(D/'run/initial/verification.json');assert initial['training_state_unchanged']
    absent=['frozen.json','final/results.json','restoration.json','holdout_b2/results.json','holdout_sac/results.json','completed.json']
    assert all(not (D/'run'/name).exists() for name in absent)
    result=dict(status='hard_stopped_not_complete',native_crash=False,failure_kind='valid_stopped_contact_force_guard',
        process_exit=exit_record,new_dynamic_starts=9,cumulative_dynamic_starts=36,cumulative_cap=59,
        unexecuted_dynamic_starts=23,formal_updates=500,unexecuted_update_batches=4000,
        published_training_episodes=4,published_transitions=published,rejected_transitions=len(failure['transitions']),
        completed_initial_successes=4,training_warmup_successes=1,updated_policy_collections=1,
        final_evaluation_exists=False,b2_complete=False,learning_benefit_proven=False,episodes=episodes,
        failure=dict(case=failure['case'],trigger_time_s=trigger['time_s'],resume_time_s=resume['time_s'],
            resume_to_guard_s=trigger['time_s']-resume['time_s'],all_cycles_after_trigger_inactive=True,
            guard_facts=failure['guard_facts'],events=failure['events']),
        missing=absent,source_and_qualification_unchanged=True,old_files_verified=len(old_files),
        audit_scope='13 archives: 9 new and 4 reused B2; stop/outcome/action arithmetic only, no state restoration.',
        additional_physical_starts=0,additional_optimizer_calls=0,inputs_sha256=inputs)
    for name,pin in inputs.items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==pin,name
    (D/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('episodes','inputs_sha256')},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
