"""Read-only recount; no simulator calls. Run from the worktree root."""
import collections
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

root=Path.cwd()
pkg=root/(sys.argv[1] if len(sys.argv)>1 else 'deliverables/residual_interface/scheduled_boundary_20260926')
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protocol=read(pkg/'protocol.json'); assessment=read(pkg/'assessment.json')
assert len(protocol['attempts'])==8
assert len({s['id'] for s in protocol['attempts']})==8
for name,digest in protocol['source_sha256'].items():
    assert sha(root/name)==sha(pkg/'source_snapshot'/name)==digest,name
assert len(assessment['runs'])==8
compact_by_id={r['id']:r for r in assessment['runs']}
assert len(compact_by_id)==8

def window_pass(rows,end,dt):
    tail=[r for r in rows if r['time_s']>=end-.1-dt/2]
    if not tail or tail[0]['time_s']>end-.1+dt/2 or abs(tail[-1]['time_s']-end)>dt/2:return False
    if any(not 0<b['time_s']-a['time_s']<=dt*1.01 for a,b in zip(tail,tail[1:])):return False
    return all(math.isfinite(r['linear_m_s']) and math.isfinite(r['angular_rad_s']) and r['linear_m_s']<=1e-5 and r['angular_rad_s']<=.001 for r in tail)

runs=[]; verdicts=[]
for spec in protocol['attempts']:
    r=json.loads(gzip.decompress((pkg/(spec['id']+'.json.gz')).read_bytes()))
    assert r['spec']==spec and r['id']==spec['id']
    compact={k:v for k,v in r.items() if k not in ('trace','physical_stop_samples','runtime','environment','initial_policy_observation')}
    assert compact==compact_by_id[spec['id']]==read(pkg/(spec['id']+'.summary.json'))
    assert r['runtime']['version']=='3.13.0' and r['runtime']['dll_verified'] is True
    for name,digest in r['runtime']['dll_sha256'].items():assert sha(Path(name))==digest
    assert r['environment']['guard_config']==protocol['guard_config']
    assert all(r[k] is False for k in ('training_admitted','model_scope_qualified','valid_for_learning'))
    trace=r['trace']; scheduled=[]
    for index,t in enumerate(trace):
        assert t['cycle_index']==index
        if t['source']=='schedule':
            # Independent literal switch boundaries; does not call the runner.
            slot=0 if index<250 else 1 if index<500 else 2 if index<1000 else 3
            want=spec['schedule'][slot]['action']; scheduled.append(t)
        else:
            assert t['source']=='diagnostic_stop'; want=[0]*4
        assert t['request']==t['action_log']['raw_action']==want
        log=t['action_log']
        assert log['enabled'] or not(any(log['experience_action']) or any(log['applied_residual']))
    assert len(trace)==r['active_cycles']+r['masked_cycles']
    assert sum(t['action_log']['enabled'] for t in trace)==r['active_cycles']
    assert sum(t['physical']['contact_count']>0 for t in trace)==r['contact_cycles']
    assert sum(any(abs(v)>1e-15 for v in t['action_log']['effective_command_delta']) for t in trace)==r['command_effect_cycles']
    for j,start in enumerate((0,250,500,1000)):
        end=(250,500,1000,13000)[j]
        rows=[t for t in scheduled if start<=t['cycle_index']<end]
        expected=dict(start_cycle=start,requested_cycles=len(rows),enabled_cycles=sum(t['action_log']['enabled'] for t in rows),effect_cycles=sum(any(abs(v)>1e-15 for v in t['action_log']['effective_command_delta']) for t in rows))
        assert expected==r['segments'][j]
    start=None; phase=None
    for event in r['events']:
        current=event.get('phase')
        if current is None:continue
        if current=='STOPPING':
            if phase!='STOPPING':start=float(event['time_s'])
        else:start=None
        phase=current
    dt=protocol['timestep_s']; end=r['end_time_s']; stops=r['physical_stop_samples']
    stopped=bool(r['completed'] and r['final_phase']=='STOPPING' and start is not None and end>=start+2-1e-9 and window_pass([s for s in stops if s['time_s']<=start+2+dt/2],start+2,dt) and window_pass(stops,end,dt))
    assert stopped==r['physical_stopped'],spec['id']
    rotations=[o for o in r['boundary_observations'] if o['rotation_trigger']]
    assert rotations==r['rotation_guard_observations']
    for ob in r['boundary_observations']:
        assert ob['contact_at_trigger']==(ob['physical']['contact_count']>0)
        q=ob['physical']['quaternion_wxyz']
        angle=math.degrees(2*math.atan2(math.sqrt(sum(v*v for v in q[1:])),abs(q[0])))
        assert abs(angle-ob['rotation_deg'])<1e-9
        if ob['rotation_trigger']:
            assert ob['rotation_deg']>2.5
            assert any('ROTATION_LIMIT' in e['reason'] and abs(e['time_s']-ob['time_s'])<1e-10 for e in r['events'])
    # Descriptive post-run analysis, NOT an added acceptance criterion.
    boundary_context=[]
    def endpoint_angle(t):
        q=t['physical']['quaternion_wxyz']
        return math.degrees(2*math.atan2(math.sqrt(sum(v*v for v in q[1:])),abs(q[0])))
    for ob in rotations:
        trigger=ob['time_s']
        tail=[t for t in trace if t['physical']['time_s']>=trigger]
        touching=[t for t in tail if t['physical']['contact_count']>0]
        near=[t for t in trace if abs(t['physical']['time_s']-trigger)<=.1]
        boundary_context.append(dict(trigger_s=trigger,exact_trigger_contact=ob['contact_at_trigger'],
            stop_tail_contact_endpoints=len(touching),
            max_stop_tail_contact_endpoint_angle_deg=max(map(endpoint_angle,touching),default=None),
            stop_tail_force_cycle_peak_N=max((t['cycle_peaks']['force_N'] for t in tail),default=None),
            plusminus100ms_contact_endpoints=sum(t['physical']['contact_count']>0 for t in near),
            descriptive_only_not_new_gate=True))
    passed=all(r.get(k) is True for k in ('initialization_valid','simulation_valid','physical_stopped','observation_valid','masking_valid','schedule_valid','completed')) and r['error'] is None and r['command_effect_cycles']>0
    verdicts.append(dict(id=spec['id'],passed=passed))
    runs.append(dict(id=spec['id'],task_outcome=r['task_outcome'],simulation_valid=r['simulation_valid'],physical_stopped=stopped,
        trace_cycles=len(trace),physical_steps=r['physical_steps'],max_rotation_deg=r['max_rotation_deg'],
        peak_force_N=r['peaks']['force_N'],peak_penetration_m=r['peaks']['penetration_m'],
        contact_cycles=r['contact_cycles'],command_effect_cycles=r['command_effect_cycles'],
        segments=r['segments'],guard_facts=r['guard_facts'],boundary_observations=r['boundary_observations'],
        events=r['events'],end_time_s=end,stop_start_s=start,rotation_triggered=bool(rotations),
        contact_rotation_triggered=any(o['contact_at_trigger'] for o in rotations),
        boundary_context=boundary_context))
assert sorted(verdicts,key=lambda r:r['id'])==sorted(assessment['checks'],key=lambda r:r['id'])
assert assessment['sample_checks_passed']==all(v['passed'] for v in verdicts)
assert assessment['rotation_boundary_cases']==sum(r['rotation_triggered'] for r in runs)
assert assessment['contact_rotation_boundary_cases']==sum(r['contact_rotation_triggered'] for r in runs)
assert assessment['source_unchanged'] is assessment['accounting_complete'] is True
assert assessment['training_admitted'] is assessment['parameter_frozen'] is assessment['model_scope_qualified'] is False
result=dict(archive_recount_passed=True,raw_archives=8,stop_audits_recomputed=8,source_inputs_verified=len(protocol['source_sha256']),
    outcomes=dict(collections.Counter(r['task_outcome'] for r in runs)),
    totals=dict(trace_cycles=sum(r['trace_cycles'] for r in runs),physical_steps=sum(r['physical_steps'] for r in runs),
        contact_cases=sum(r['contact_cycles']>0 for r in runs),effect_cases=sum(r['command_effect_cycles']>0 for r in runs),
        max_rotation_deg=max(r['max_rotation_deg'] for r in runs),max_force_N=max(r['peak_force_N'] for r in runs),
        max_penetration_m=max(r['peak_penetration_m'] for r in runs),
        rotation_trigger_cases=sum(r['rotation_triggered'] for r in runs),contact_rotation_trigger_cases=sum(r['contact_rotation_triggered'] for r in runs)),
    training_admitted=False,parameter_frozen=False,runs=runs)
print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
