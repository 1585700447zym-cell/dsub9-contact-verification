"""B2-SCOPE-07: read sealed JSON evidence only; no physics or learner imports.

Times refer to existing control boundaries. Substep peaks are localized to a
2 ms interval, not assigned an invented exact substep time. No thresholds are
fitted and no new physical or policy samples are created.
"""
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = ROOT/'deliverables/learning_chain/b2_joint_learning_review_20261009'
SOURCE = OUT.parent/'b2_rebound_execution_20261008'
SOURCE_PIN = '74773ee946d6c9e6d628af08211ca8a564246308ad76f8889cd116db953f4af0'
AXES = [0, 1, 3, 4]

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def save(name, value):
    (OUT/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')

def signature(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def features(snapshot):
    p = snapshot['policy_raw']
    return p['wrench_history_M'][:6]+p['relative_position_m']+p['relative_rotation_world_rad']

def clipped(snapshot, schema):
    return sum(abs(v/s)>10 for field in schema for v,s in zip(snapshot['policy_raw'][field['name']],field['scale']))

def event(cycle, index, schema):
    b=cycle['before']; result=cycle['result']; p=b['policy_raw']
    return dict(cycle_index=index, time_s=b['time_s'], end_time_s=cycle['after']['time_s'],
                policy_phase=b['controller_state']['phase'], physical_phase=b['state']['phase'],
                enabled=b['residual_enabled'], contact_count=b['state']['contact_count'],
                requested=cycle['requested'], effective_command_delta=result['action_log']['effective_command_delta'],
                clipped_components=clipped(b,schema), features=features(b),
                normalized_features=b['policy_observation'][:6]+b['policy_observation'][24:30],
                vector=b['policy_observation'], cycle_peaks=result['cycle_peaks'])

def windows(cycles, predicate):
    groups=[]
    for i,c in enumerate(cycles):
        if not predicate(c): continue
        if not groups or groups[-1]['last_index']!=i-1:
            groups.append(dict(first_index=i,last_index=i,begin_s=c['before']['time_s'],end_s=c['after']['time_s'],cycles=1))
        else:
            groups[-1].update(last_index=i,end_s=c['after']['time_s'],cycles=groups[-1]['cycles']+1)
    return groups

def main():
    assert not (OUT/'delivery_manifest.json').exists(), 'Sealed output must never be rewritten'
    assert sha(SOURCE/'delivery_manifest.json')==SOURCE_PIN
    manifest=read(SOURCE/'delivery_manifest.json')['files']
    assert len(manifest)==254
    for rel,meta in manifest.items():
        assert sha(SOURCE/rel)==meta['sha256'] and (SOURCE/rel).stat().st_size==meta['bytes'], rel
    assessment=read(SOURCE/'run/assessment.json')
    inherited={r['id']:r for r in assessment['dynamic']}
    summaries=[]; compact={}; input_hashes={}; reconciliations=[]
    fields=['id','cycle','t0_s','t1_s','phase','physical_phase','enabled','contact_before','contact_after',
            'force_peak_N','torque_peak_Nm','request_x','request_y','request_roll','request_pitch',
            'effect_x','effect_y','effect_roll','effect_pitch','x_m','y_m','z_m','clipped_components']
    with (OUT/'joint_cycles.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for case in ['J01','J02','J03','J04']:
            for arm in ['zero','script']:
                name=case+'_'+arm; path=SOURCE/'run'/(name+'.json.gz')
                with gzip.open(path,'rt',encoding='utf-8') as f: raw=json.load(f)
                input_hashes[path.relative_to(ROOT).as_posix()]=sha(path)
                cycles=raw['cycles']; schema=raw['observation_schema']; old=inherited[name]
                assert len(cycles)==raw['control_cycles'] and len(raw['observations'])==len(cycles)+1
                assert raw['outcome']['physical_stopped'] and raw['outcome']['simulation_valid']
                assert all(len(c['before']['policy_observation'])==137 for c in cycles)
                contact=lambda c:c['result']['trace_row']['contact_count']>0
                effect=lambda c:any(abs(x)>1e-15 for x in c['result']['action_log']['effective_command_delta'])
                permitted=lambda c:c['before']['residual_enabled']
                request=lambda c:any(c['requested'])
                counts=dict(cycles=len(cycles),permitted_cycles=sum(map(permitted,cycles)),
                            contact_cycles=sum(map(contact,cycles)),
                            contact_permitted_cycles=sum(contact(c) and permitted(c) for c in cycles),
                            script_nonzero_cycles=sum(map(request,cycles)),
                            contact_effect_cycles=sum(contact(c) and effect(c) for c in cycles),
                            nonzero_without_permission=sum(request(c) and not permitted(c) for c in cycles))
                for key in ['contact_cycles','script_nonzero_cycles','contact_effect_cycles']:
                    assert counts[key]==old[key], (name,key)
                assert counts['nonzero_without_permission']==0
                first_contact=next(i for i,c in enumerate(cycles) if c['before']['state']['contact_count']>0)
                first=event(cycles[first_contact],first_contact,schema)
                assert first['time_s']==old['observation']['first_contact']['time_s']
                assert first['features']==old['observation']['first_contact']['features']
                integrals=[sum(abs(c['result']['action_log']['effective_command_delta'][k])*c['result']['dt'] for c in cycles) for k in AXES]
                assert all(math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-16) for x,y in zip(integrals,old['axis_command_effect_integral']))
                peaks={}
                for key in ['force_N','torque_G_Nm','penetration_m']:
                    i=max(range(len(cycles)),key=lambda n:cycles[n]['result']['cycle_peaks'][key])
                    e=event(cycles[i],i,schema);e['peak_value']=cycles[i]['result']['cycle_peaks'][key]
                    assert math.isclose(e['peak_value'],raw['peaks'][key],rel_tol=1e-12,abs_tol=1e-15)
                    peaks[key]=e
                pulse_windows=windows(cycles,request)
                for w in pulse_windows:
                    selected=cycles[w['first_index']:w['last_index']+1]
                    w.update(phase=selected[0]['before']['controller_state']['phase'],
                             contact_cycles=sum(map(contact,selected)),
                             command_effect_integral=[sum(abs(c['result']['action_log']['effective_command_delta'][k])*c['result']['dt'] for c in selected) for k in AXES])
                phases=[]
                for phase in ['INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED']:
                    for w in windows(cycles,lambda c:c['before']['controller_state']['phase']==phase):
                        selected=cycles[w['first_index']:w['last_index']+1]
                        w.update(phase=phase,permitted_cycles=sum(map(permitted,selected)),contact_cycles=sum(map(contact,selected)),
                                 peak_force_N=max(c['result']['cycle_peaks']['force_N'] for c in selected),
                                 nonzero_cycles=sum(map(request,selected)))
                        phases.append(w)
                phases.sort(key=lambda w:w['first_index'])
                observed_motion=[0.,0.,0.,0.];rows=[];all_clips=0;max_clip=0;effect_rows=0
                for i,c in enumerate(cycles):
                    b=c['before'];a=c['after'];res=c['result'];tr=res['trace_row'];log=res['action_log']
                    clip=clipped(b,schema);all_clips+=clip;max_clip=max(max_clip,clip);effect_rows+=effect(c)
                    for k in range(2):observed_motion[k]+=abs(a['state']['position_m'][k]-b['state']['position_m'][k])
                    for k in range(2):observed_motion[k+2]+=abs(tr['velocity_world'][k+3]*res['dt'])
                    record=dict(id=name,cycle=i,t0_s=b['time_s'],t1_s=a['time_s'],phase=b['controller_state']['phase'],
                                physical_phase=b['state']['phase'],enabled=int(b['residual_enabled']),contact_before=b['state']['contact_count'],
                                contact_after=tr['contact_count'],force_peak_N=res['cycle_peaks']['force_N'],
                                torque_peak_Nm=res['cycle_peaks']['torque_G_Nm'],clipped_components=clip)
                    record.update(zip(['request_x','request_y','request_roll','request_pitch'],c['requested']))
                    record.update(zip(['effect_x','effect_y','effect_roll','effect_pitch'],[log['effective_command_delta'][k] for k in AXES]))
                    record.update(zip(['x_m','y_m','z_m'],a['state']['position_m']));writer.writerow(record)
                    # Retained in memory only for pair checks. All comparisons are observed data, no policy inference.
                    rows.append(dict(t=b['time_s'],obs=b['policy_observation'],features=features(b),
                                     state_hash=signature({k:b['state'][k] for k in ['position_m','quaternion_wxyz','velocity_world','contact_wrench_M','contact_count']}),
                                     position=b['state']['position_m'],rotation=b['policy_raw']['relative_rotation_world_rad'],
                                     request=c['requested']))
                assert all(math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-14) for x,y in zip(observed_motion,old['axis_observed_motion']))
                force_limit=raw['parameters']['dynamic_config']['stop_force_N']
                recoveries=[e for e in raw['events'] if e.get('phase')=='RECOVERING' or 'RECOVERY' in e.get('reason','')]
                s=dict(id=name,case=raw['spec']['case'],counts=counts,first_contact=first,
                       initial_vector=cycles[0]['before']['policy_observation'],peak_intervals=peaks,pulses=pulse_windows,
                       phase_windows=phases,controller_events=raw['controller_events'],recovery_events=recoveries,
                       physical_phase_counts={p:sum(c['before']['state']['phase']==p for c in cycles) for p in sorted({c['before']['state']['phase'] for c in cycles})},
                       permission_windows=windows(cycles,permitted),task_end_time_s=raw['task_end_time_s'],
                       effect_cycles=effect_rows,command_effect_integral=integrals,observed_motion_integral=observed_motion,
                       clipped_component_occurrences=all_clips,max_clipped_components_per_vector=max_clip,
                       force_limit_N=force_limit,force_margin_N=force_limit-raw['peaks']['force_N'],
                       force_margin_percent=100*(force_limit-raw['peaks']['force_N'])/force_limit,
                       outcome=raw['outcome'],source_archive_sha256=sha(path))
                compact[name]=rows;summaries.append(s)
                reconciliations.append(dict(id=name,receipt_counts_match=True,first_contact_matches=True,
                                            command_integral_matches=True,motion_integral_matches=True,peak_values_match=True))
                print(json.dumps(dict(id=name,counts=counts,first_contact_s=first['time_s'],
                     peak_force_N=peaks['force_N']['peak_value'],peak_interval=[peaks['force_N']['time_s'],peaks['force_N']['end_time_s']],
                     peak_enabled=peaks['force_N']['enabled'],peak_request=peaks['force_N']['requested'],pulses=pulse_windows),ensure_ascii=False),flush=True)
                del raw,cycles
    byid={s['id']:s for s in summaries};arm_pairs=[];symmetric=[]
    for case in ['J01','J02','J03','J04']:
        zero=compact[case+'_zero'];script=compact[case+'_script']
        n=next(i for i,r in enumerate(script) if any(r['request']))
        # Current-cycle state and observation precede that cycle's action.
        prefix_equal=all(zero[i]['state_hash']==script[i]['state_hash'] and zero[i]['obs']==script[i]['obs'] for i in range(n+1))
        assert prefix_equal
        end=min(byid[case+'_zero']['task_end_time_s'],byid[case+'_script']['task_end_time_s'])
        common=[(z,s) for z,s in zip(zero,script) if z['t']<=end and s['t']<=end]
        assert all(abs(z['t']-s['t'])<1e-9 for z,s in common)
        arm_pairs.append(dict(case=case,identical_prefix_through_first_action_input=True,
                        first_action_index=n,first_action_s=script[n]['t'],prefix_input_vectors=n+1,
                        common_time_end_s=end,max_common_time_xy_difference_m=[max(abs(z['position'][k]-s['position'][k]) for z,s in common) for k in range(2)],
                        max_common_time_relative_rotation_difference_rad=[max(abs(z['rotation'][k]-s['rotation'][k]) for z,s in common) for k in range(2)],
                        task_time_delta_s=byid[case+'_script']['task_end_time_s']-byid[case+'_zero']['task_end_time_s'],
                        causal_axis_identification=False,learned_policy_benefit_claim=False))
    for left,right in [('J01','J03'),('J02','J04')]:
        for arm in ['zero','script']:
            l=byid[left+'_'+arm];r=byid[right+'_'+arm];a=compact[l['id']];b=compact[r['id']]
            different=next((i for i,(x,y) in enumerate(zip(a,b)) if x['obs']!=y['obs']),None)
            d=[x-y for x,y in zip(l['first_contact']['features'],r['first_contact']['features'])]
            normalized=[x-y for x,y in zip(l['first_contact']['normalized_features'],r['first_contact']['normalized_features'])]
            symmetric.append(dict(left=l['id'],right=r['id'],initial_different_components=sum(x!=y for x,y in zip(l['initial_vector'],r['initial_vector'])),
                                  first_contact_times_s=[l['first_contact']['time_s'],r['first_contact']['time_s']],
                                  event_aligned_feature_difference=d,normalized_feature_difference=normalized,
                                  feature_difference_count=sum(x!=0 for x in d),max_normalized_feature_difference=max(map(abs,normalized)),
                                  first_common_time_vector_difference_index=different,
                                  first_common_time_vector_difference_s=None if different is None else a[different]['t'],
                                  first_common_time_max_vector_difference=None if different is None else max(abs(x-y) for x,y in zip(a[different]['obs'],b[different]['obs'])),
                                  event_aligned_is_not_same_time=True,observability_or_significance_proven=False))
    result=dict(stage_id='B2-SCOPE-07',status='OFFLINE_REVIEW_COMPLETE',source_manifest_sha256=SOURCE_PIN,
                episodes=summaries,arm_pairs=arm_pairs,symmetric_pairs=symmetric,reconciliation=reconciliations,
                input_archives=input_hashes,total_existing_cycles=sum(s['counts']['cycles'] for s in summaries),
                new_physics=0,new_policy_forwards=0,new_updates=0,new_replay_publications=0,cumulative_dynamic=225,
                training_admitted=False,full_B2_accepted=False,C_accepted=False,
                method_limits=['substep peak time bounded by control interval','contact cycles use post-step contact_count as sealed assessment',
                               'event-aligned contacts are at unequal times','first exact difference is not a noise/observability threshold',
                               'paired scripts vary four correlated axes and may have different contact histories',
                               'no repeated noise trials, independent tests, recovery events or full action domain'])
    assert not any(k.split('.')[0] in {'numpy','mujoco','torch','stable_baselines3'} for k in sys.modules)
    save('analysis.json',result)
    print(json.dumps(dict(status=result['status'],episodes=len(summaries),existing_cycles=result['total_existing_cycles'],arm_pairs=arm_pairs,symmetric_pairs=symmetric),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
