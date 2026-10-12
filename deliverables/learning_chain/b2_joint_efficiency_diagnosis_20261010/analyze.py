"""Pure archive analysis; no runtime, tensors, actor or physics imports."""
import csv,gzip,hashlib,json,math,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
POLICY=('INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED')
PHYSICAL=('RUNNING','STOPPING','RETRACT','TERMINAL')
AXES=(0,1,3,4);SCALE=(.00005,.00005,.0005,.0005)
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n',encoding='utf8')
def close(x,y,tol=1e-11):
    if not math.isfinite(x) or not math.isfinite(y) or abs(x-y)>tol:raise ValueError(('Numeric mismatch',x,y,tol))
def vector(x,n):
    if len(x)!=n or any(type(v) not in (int,float) or not math.isfinite(v) for v in x):raise ValueError('Finite vector required')
    return x
def phase_of(observation,schema):
    vector(observation,137)
    fields=schema if isinstance(schema,dict) else {f['name']:f for f in schema}
    def decode(name,options):
        f=fields[name]
        if f['width']!=len(options):raise ValueError('Wrong phase width')
        values=observation[f['start']:f['start']+f['width']]
        if any(x not in (0.,1.) for x in values) or sum(values)!=1.:raise ValueError('Invalid onehot '+name)
        return options[values.index(1.)]
    policy=decode('policy_phase',POLICY);physical=decode('physical_phase',PHYSICAL)
    return policy if physical=='RUNNING' else physical
def time_parts(times,labels,task_end):
    if len(times)!=len(labels)+1 or not times or not all(math.isfinite(x) for x in times) or not math.isfinite(task_end):raise ValueError('Invalid timeline')
    if task_end<times[0] or task_end>times[-1]+1e-10 or any(b<=a for a,b in zip(times,times[1:])):raise ValueError('Invalid time sequence')
    result={}
    for start,end,label in zip(times,times[1:],labels):
        dt=max(0.,min(end,task_end)-start)
        if dt>0:result[label]=result.get(label,0.)+dt
    return result
def reward_parts(maximum,advance,dt,force,torque,target,terminal=0.):
    if not all(math.isfinite(x) for x in (maximum,advance,dt,force,torque,target,terminal)) or dt<=0 or target<=0 or min(maximum,force,torque)<0:raise ValueError('Invalid reward inputs')
    new=max(maximum,min(target,max(0.,advance)))
    terms=dict(progress=5*(new-maximum)/target,time=-.1*dt,force=-.2*dt*(force/.025)**2,torque=-.2*dt*(torque/.0005)**2,terminal=terminal)
    terms['total']=math.fsum(terms.values())
    return dict(maximum=new,terms=terms)
def motion_stats(trace,actions,transitions):
    if len(trace)!=len(actions)+1 or len(actions)!=len(transitions) or not actions:raise ValueError('Empty or misaligned segment')
    p=[vector(r['position_m'],3) for r in trace];ref=[r['reference_qpos'][:3] for r in trace]
    return dict(actual_xy_net_um=[(p[-1][j]-p[0][j])*1e6 for j in (0,1)],
         actual_xy_path_um=math.fsum(math.dist(a[:2],b[:2]) for a,b in zip(p,p[1:]))*1e6,
         reference_xy_net_um=[(ref[-1][j]-ref[0][j])*1e6 for j in (0,1)],
         reference_xy_path_um=math.fsum(math.dist(a[:2],b[:2]) for a,b in zip(ref,ref[1:]))*1e6,
         total_command_xy_integral_um=[math.fsum(a['actual_end_limited_command'][j]*t['dt'] for a,t in zip(actions,transitions))*1e6 for j in (0,1)])
def validate_alignment(raw):
    n=raw['control_cycles'];times=[r['time_s'] for r in raw['trace']]
    if type(n) is not int or n<=0 or len(raw['actions'])!=n or len(raw['transitions'])!=n or len(times)!=n+1:raise ValueError('Archive sequence lengths differ')
    for start,end,t in zip(times,times[1:],raw['transitions']):
        if not math.isfinite(t['dt']) or t['dt']<=0 or end<=start:raise ValueError('Bad cycle duration')
        close(end-start,t['dt'],2e-12)
    return times
def state(row):
    p=vector(row['position_m'],3);q=vector(row['quaternion_wxyz'],4);norm=math.sqrt(math.fsum(v*v for v in q))
    if norm==0:raise ValueError('Zero quaternion')
    w,x,y,z=[v/norm for v in q]
    return dict(time_s=row['time_s'],position_um=[v*1e6 for v in p],xy_um=math.hypot(*p[:2])*1e6,
        roll_deg=math.degrees(math.atan2(2*(w*x+y*z),1-2*(x*x+y*y))),pitch_deg=math.degrees(math.asin(max(-1.,min(1.,2*(w*y-z*x))))),
        angle_to_identity_deg=math.degrees(2*math.acos(min(1.,abs(w)))))
def precise(row):
    s=state(row);return dict(**s,additional_80um_0p5deg=s['xy_um']<=80. and s['angle_to_identity_deg']<=.5)
def ranges(labels):
    result=[];start=0
    for i in range(1,len(labels)+1):
        if i==len(labels) or labels[i]!=labels[start]:result.append((start,i,labels[start]));start=i
    return result
def csv_write(path,rows):
    with Path(path).open('w',encoding='utf8',newline='') as f:
        if rows:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def verify_sources(reg):
    if sha(Path(reg['prior_directory'])/'delivery_manifest.json')!=reg['prior_manifest_sha256']:raise ValueError('Prior seal changed')
    for item in reg['archives']:
        if sha(item['path'])!=item['sha256']:raise ValueError('Archive changed '+item['case_id'])
    for name,pin in reg['source_code_sha256'].items():
        if sha(ROOT/name)!=pin:raise ValueError('Interpretation source changed '+name)
def segment(raw,labels,start,end):
    actions=raw['actions'][start:end];transitions=raw['transitions'][start:end];trace=raw['trace'][start:end+1]
    dt=math.fsum(t['dt'] for t in transitions);result=motion_stats(trace,actions,transitions)
    result.update(start_cycle=start,end_cycle_exclusive=end,phase=labels[start],duration_s=dt,entry=state(trace[0]),exit=state(trace[-1]),
        active_cycles=sum(t['action_active'] for t in transitions),max_cycle_force_mN=max(t['cycle_force_N'] for t in transitions)*1000,
        mean_action=[math.fsum(a['raw_action'][j]*t['dt'] for a,t in zip(actions,transitions))/dt for j in range(4)],
        requested_xy_integral_um=[math.fsum(a['applied_residual'][j]*t['dt'] for a,t in zip(actions,transitions))*1e6 for j in (0,1)],
        effective_command_delta_xy_integral_um=[math.fsum(a['effective_command_delta'][j]*t['dt'] for a,t in zip(actions,transitions))*1e6 for j in (0,1)],
        requested_rotation_integral_mrad=[math.fsum(a['applied_residual'][j]*t['dt'] for a,t in zip(actions,transitions))*1000 for j in (3,4)],
        reference_filtered_cycles=sum(a['reference_filter_fraction']<1. for a in actions),continuation_filtered_cycles=sum(a['continuation_filtered'] for a in actions),
        saturation_fraction_by_axis=[math.fsum(t['dt'] for a,t in zip(actions,transitions) if abs(a['raw_action'][j])>=.95)/dt for j in range(4)],
        policy_input_phase_differs_from_left_trace_cycles=sum(raw['trace'][i]['policy_phase']!=labels[i] for i in range(start,end) if labels[i] in POLICY))
    if labels[start]=='SEARCH':
        projected=[];error=0.
        for k,(a,t) in enumerate(zip(actions,transitions),start):
            ref=a['reference_xy_m'];length=math.hypot(*ref)
            projected.append(0. if length<=1e-15 else math.fsum(a['applied_residual'][j]*ref[j] for j in (0,1))/length*1e6)
            for j in range(3):error=max(error,abs(raw['trace'][k+1]['reference_qpos'][j]-raw['trace'][k]['reference_qpos'][j]-a['actual_end_limited_command'][j]*t['dt']))
        result.update(mean_requested_radial_um_s=math.fsum(v*t['dt'] for v,t in zip(projected,transitions))/dt,
            outward_requested_duration_fraction=math.fsum(t['dt'] for v,t in zip(projected,transitions) if v>0)/dt,
            max_reference_integration_error_m=error,entry_theta_rad=trace[0]['spiral_theta_rad'],exit_theta_rad=trace[-1]['spiral_theta_rad'])
        if error>1e-14:raise ValueError('SEARCH reference integration mismatch')
    return result
def cycle_row(raw,model,i,phase,task_n):
    b,c=raw['trace'][i:i+2];a=raw['actions'][i];t=raw['transitions'][i]
    row=dict(model=model,case_id=raw['case_id'],cycle=i,period='task' if i<task_n else 'audit_tail',phase=phase,
        start_time_s=b['time_s'],end_time_s=c['time_s'],dt=t['dt'],action_active=t['action_active'],
        actual_x_um=b['position_m'][0]*1e6,actual_y_um=b['position_m'][1]*1e6,actual_z_um=b['position_m'][2]*1e6,
        reference_x_um=b['reference_qpos'][0]*1e6,reference_y_um=b['reference_qpos'][1]*1e6,
        theta_rad=b['spiral_theta_rad'],force_peak_mN=t['cycle_force_N']*1000,torque_peak_G_mNm=t['cycle_torque_G_Nm']*1000,
        reference_filter_fraction=a['reference_filter_fraction'],continuation_filter_fraction=a['continuation_filter_fraction'])
    for j,name in enumerate(('x','y','roll','pitch')):
        scale=1e6 if j<2 else 1000.;axis=AXES[j]
        row['action_'+name]=a['raw_action'][j]
        for prefix,key in (('requested','applied_residual'),('effective_delta','effective_command_delta'),('executed','actual_end_limited_command')):row[prefix+'_'+name]=a[key][axis]*scale
    for key,value in t['reward_terms'].items():row['reward_'+key]=value
    return row
def study(raw,item):
    times=validate_alignment(raw);n=raw['control_cycles'];schema=raw['observation_schema'];fields={f['name']:f for f in schema};offset=0
    for f in schema:
        if f['start']!=offset or f['width']<1:raise ValueError('Noncontiguous schema')
        offset+=f['width']
    if offset!=137 or len(fields)!=len(schema):raise ValueError('Wrong observation schema')
    if raw['case_id']!=item['case_id'] or raw['mode']!='F50' or raw['scope']!='frozen_development_evaluation' or raw['optimizer_steps']!=(0 if item['model']=='F0' else 2000):raise ValueError('Wrong frozen evaluation')
    out=raw['outcome']
    if not out['physical_stopped'] or not out['simulation_valid'] or out['task_outcome']!='FULL_SUCCESS' or any(out['guard_violations'].values()) or raw['fault'] or raw['reference_problems'] or raw['actual_reference_failed']:raise ValueError('Unexpected outcome')
    labels=[];maximum=0.;reward_total={};reward_task={};reward_tail={};first_contact=None;permission_count=0;prediction_checks=0
    task_n=min(range(n+1),key=lambda i:abs(times[i]-raw['task_end_time_s']));close(times[task_n],raw['task_end_time_s'],1e-9)
    for i,(a,t) in enumerate(zip(raw['actions'],raw['transitions'])):
        phase=phase_of(t['observation'],fields);labels.append(phase)
        expected=phase in ('INSERT','SEARCH') and not t['observation'][fields['pending']['start']] and t['observation'][fields['simulation_valid']['start']]==1. and not any(t['observation'][fields['latched_guards']['start']:fields['latched_guards']['start']+fields['latched_guards']['width']]) and not t['observation'][fields['invalid_latched']['start']]
        if t['action_active']!=expected or a['enabled']!=expected:raise ValueError('Permission mismatch')
        permission_count+=1
        vector(a['raw_action'],4);vector(t['next_observation'],137)
        if any(abs(v)>1.+1e-12 for v in a['raw_action']):raise ValueError('Action outside bounds')
        mapped=[a['raw_action'][0]*SCALE[0],a['raw_action'][1]*SCALE[1],0.,a['raw_action'][2]*SCALE[2],a['raw_action'][3]*SCALE[3],0.]
        for j in range(6):
            close(a['requested_residual'][j],mapped[j],1e-15);close(a['applied_residual'][j],mapped[j] if expected else 0.,1e-15)
            close(a['effective_command_delta'][j],a['predicted_limited_command'][j]-a['zero_residual_limited_command'][j],1e-15)
            if expected:close(a['actual_end_limited_command'][j],a['predicted_limited_command'][j],1e-15)
        if expected:prediction_checks+=1
        if not expected and (any(a['applied_residual']) or any(a['experience_action'])):raise ValueError('Disabled residual not zero')
        terms=reward_parts(maximum,t['advance_m'],t['dt'],t['cycle_force_N'],t['cycle_torque_G_Nm'],raw['case']['target_depth_m'],10. if i==n-1 else 0.)
        maximum=terms['maximum']
        if set(t['reward_terms'])!=set(terms['terms']):raise ValueError('Unexpected reward fields')
        for key,value in terms['terms'].items():
            close(t['reward_terms'][key],value);reward_total[key]=reward_total.get(key,0.)+value
            dest=reward_task if i<task_n else reward_tail;dest[key]=dest.get(key,0.)+value
        close(t['reward'],terms['terms']['total'])
        if first_contact is None and t['cycle_force_N']>0:first_contact=dict(cycle=i,start_time_s=times[i],end_time_s=times[i+1],state=state(raw['trace'][i+1]),action=list(a['raw_action']))
    parts=time_parts(times,labels,raw['task_end_time_s']);close(sum(parts.values()),raw['task_end_time_s']-times[0],1e-9)
    close(times[-1],raw['audit_end_time_s'],1e-9)
    if raw['physical_substeps']!=10*n or raw['policy_calls']!=prediction_checks:raise ValueError('Archived cost mismatch')
    segments=[segment(raw,labels,start,end) for start,end,phase in ranges(labels[:task_n])]
    searches=[s for s in segments if s['phase']=='SEARCH']
    rows=[cycle_row(raw,item['model'],i,phase,task_n) for i,phase in enumerate(labels)]
    alignment=[]
    for index,s in enumerate(searches,1):
        indexes=range(s['start_cycle'],s['end_cycle_exclusive']);start=s['entry']['time_s']
        for kind,grid in (('elapsed_s',[i*.5 for i in range(17)]),('theta_rad',list(range(0,19,2)))):
            value=lambda i:times[i]-start if kind=='elapsed_s' else raw['trace'][i]['spiral_theta_rad']
            for point in grid:
                if point<value(s['start_cycle'])-1e-9 or point>value(s['end_cycle_exclusive']-1)+1e-9:continue
                best=min(indexes,key=lambda i:abs(value(i)-point));alignment.append(dict(search=index,alignment_kind=kind,requested_value=point,actual_alignment_value=value(best),**rows[best]))
    record=dict(model=item['model'],case_id=raw['case_id'],archive_path=item['path'],sha256=item['sha256'],case=raw['case'],seed=raw['seed'],comparison_key=raw['comparison_key'],
         policy_sha256=raw['policy_sha256'],initial_observation=raw['transitions'][0]['observation'],initial_action=raw['actions'][0]['raw_action'],
         control_cycles=n,task_cycles=task_n,task_time_s=raw['task_end_time_s'],audit_end_time_s=raw['audit_end_time_s'],audit_tail_s=times[-1]-times[task_n],
         phase_times_s=parts,segments=segments,first_contact=first_contact,task_end_state=precise(raw['trace'][task_n]),archive_end_state=precise(raw['trace'][-1]),
         controller_events=raw['controller_events'],environment_events=raw['events'],peaks=raw['peaks'],reward_all=reward_total,reward_task=reward_task,reward_audit_tail=reward_tail,
         permission_checks=permission_count,enabled_command_prediction_checks=prediction_checks,reward_cycle_checks=n)
    return record,rows,alignment
def main():
    if (OUT/'diagnosis.json').exists() or (OUT/'delivery_manifest.json').exists():raise FileExistsError('Preserve first analysis')
    reg=read(OUT/'registration.json');verify_sources(reg);records=[];cycle_rows=[];alignment=[];phase_rows=[];common=None
    for item in reg['archives']:
        raw=json.loads(gzip.decompress(Path(item['path']).read_bytes()));record,rows,align=study(raw,item)
        if common is None:common=record['comparison_key']
        if record['comparison_key']!=common:raise ValueError('Different common task')
        records.append(record);cycle_rows.extend(rows);alignment.extend(align)
        for s in record['segments']:phase_rows.append(dict(model=item['model'],case_id=item['case_id'],phase=s['phase'],start_cycle=s['start_cycle'],end_cycle_exclusive=s['end_cycle_exclusive'],duration_s=s['duration_s'],
              actual_xy_path_um=s['actual_xy_path_um'],reference_xy_path_um=s['reference_xy_path_um'],force_peak_mN=s['max_cycle_force_mN'],reference_filtered_cycles=s['reference_filtered_cycles']))
        print(item['model'],item['case_id'],record['task_time_s'],'seconds',record['archive_end_state']['xy_um'],'um',flush=True)
    comparisons=[]
    for i in range(1,5):
        zero=next(r for r in records if r['model']=='F0' and r['case_id']=='J0'+str(i));final=next(r for r in records if r['model']=='F2000' and r['case_id']==zero['case_id'])
        if zero['case']!=final['case'] or zero['seed']!=final['seed']:raise ValueError('Unmatched case or seed')
        delta={p:final['phase_times_s'].get(p,0.)-zero['phase_times_s'].get(p,0.) for p in dict.fromkeys(list(zero['phase_times_s'])+list(final['phase_times_s']))}
        close(sum(delta.values()),final['task_time_s']-zero['task_time_s'],1e-9)
        comparisons.append(dict(case_id=zero['case_id'],F0_task_s=zero['task_time_s'],F2000_task_s=final['task_time_s'],task_delta_s=final['task_time_s']-zero['task_time_s'],
             phase_delta_s=delta,reward_delta={k:final['reward_all'][k]-zero['reward_all'][k] for k in zero['reward_all']},
             F0_xy_um=zero['archive_end_state']['xy_um'],F2000_xy_um=final['archive_end_state']['xy_um'],F0_precision=zero['archive_end_state']['additional_80um_0p5deg'],F2000_precision=final['archive_end_state']['additional_80um_0p5deg']))
    f0=math.fsum(r['F0_task_s'] for r in comparisons)/4;f2=math.fsum(r['F2000_task_s'] for r in comparisons)/4
    assessment=read(Path(reg['prior_directory'])/'assessment.json');close(f0,assessment['scores']['zero']['metric']['mean_penalized_time_s']);close(f2,assessment['scores']['final']['metric']['mean_penalized_time_s'])
    proof=dict(stage_id='B2-SCOPE-21',archive_count=8,archive_cycles=sum(r['control_cycles'] for r in records),records=records,comparisons=comparisons,
         mean_F0_s=f0,mean_F2000_s=f2,relative_improvement=1-f2/f0,development_continue=False,
         initial_observation_identical_across_all_eight=all(r['initial_observation']==records[0]['initial_observation'] for r in records),
         initial_action_identical_within_each_actor={m:len({tuple(r['initial_action']) for r in records if r['model']==m})==1 for m in ('F0','F2000')},
         additional_precision_successes={m:sum(r['archive_end_state']['additional_80um_0p5deg'] for r in records if r['model']==m) for m in ('F0','F2000')},
         source_code_count=len(reg['source_code_sha256']),costs=reg['costs'],cumulative_dynamic=254,automatic_tracking='PAUSED',training_admitted=False,independent_tests=0,full_B2_accepted=False,C_accepted=False,
         definitions=dict(phases='same-cycle input observation; physical stop overrides policy phase',time='task_end includes stop confirmation; later audit tail separate',
           displacement='actual saved pose; command integral is not displacement or physical counterfactual',precision='additional 80um global carrier XY norm and 0.5deg identity quaternion angle, not historical functional outcome',
           reward='rederived frozen maximum-progress/time/force/torque/terminal formula; no tensor scoring',alignment='nearest recorded SEARCH cycle by elapsed time or theta; entry states not counterfactually equal'))
    verify_sources(reg)
    if any(k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3','gymnasium') for k in sys.modules):raise AssertionError('Unexpected scientific import')
    write(OUT/'diagnosis.json',proof);csv_write(OUT/'cycles.csv',cycle_rows);csv_write(OUT/'phase_summary.csv',phase_rows);csv_write(OUT/'search_alignment.csv',alignment)
    print(json.dumps({k:proof[k] for k in ('archive_count','archive_cycles','relative_improvement','additional_precision_successes')},ensure_ascii=False))
if __name__=='__main__':main()
