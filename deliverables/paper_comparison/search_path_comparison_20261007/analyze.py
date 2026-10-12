"""PC-10 pure archive analysis. No environment, actor, checkpoint or rollout imports."""
from pathlib import Path
import csv,gzip,hashlib,json,math
import numpy as np

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
BASE=ROOT/'deliverables/paper_comparison'
PHASES=('INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED')
SEALS={
    'contact_gate_probe_20261007':'c123f8f1f445c856e04222156f519e7b39e5cb8097e00bd646720f95858d3038',
    'residual_effect_diagnosis_20261007':'1500e169da44e364c33dc01e84b30538b3de2abedb37c9486055d6fe4687a76f',
    'frozen_comparison_20261007':'8c64d623247c31e217f71e90cbb473c3d21a05c49360f10872dab4eddd36596c',
    'v4_learning_requalification_20261006':'fd98d247484e919c3c4e099d03575b1d4d40e977a5da939efc088759c84b9ed5'}
ARCHIVES={
    'F50':('contact_gate_probe_20261007/run/probe_F50_y_neg_150.json.gz','534392e109e661d0c165bbeb1165a6c9f29b454c5d8e7690e0dd88f21ea15877'),
    'F12.5':('contact_gate_probe_20261007/run/probe_F12p5_y_neg_150.json.gz','05672e155e7b5e8875bf73c6e6f6f5ff6857f833978131ec7649676a9f4e58b2'),
    'G50':('contact_gate_probe_20261007/run/probe_G50_y_neg_150.json.gz','a8d47576247bfc635dce783413e641aca00e6bc4f1758b9547791ccf27bb3563'),
    'S50':('v4_learning_requalification_20261006/run/final_S50_y_neg_150.json.gz','e043f85a4c37869e996aaba0777783027130dec03b63b0b3b4b4a4ce0dcce3d6')}

def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def vector(v,n):
    a=np.asarray(v,dtype=float)
    if a.shape!=(n,) or not np.isfinite(a).all():raise ValueError('Finite vector shape required')
    return a

def phase(raw,t):
    s=[s for s in raw['observation_schema'] if s['name']=='policy_phase']
    if len(s)!=1 or s[0]['width']!=5:raise ValueError('Unique five-phase schema required')
    ob=vector(t['observation'],137);i=s[0]['start'];one=ob[i:i+5]
    if sum(one)!=1. or not all(v in (0.,1.) for v in one):raise ValueError('Invalid phase onehot')
    return PHASES[int(one.argmax())]

def search_segments(raw):
    n=raw['control_cycles']
    if n<=0 or len(raw['actions'])!=n or len(raw['transitions'])!=n or len(raw['trace'])!=n+1:
        raise ValueError('Actions/transitions/trace must be aligned')
    result=[];start=None
    for i,t in enumerate(raw['transitions']):
        active=phase(raw,t)=='SEARCH'
        if active and start is None:start=i
        if not active and start is not None:result.append((start,i));start=None
    if start is not None:result.append((start,n))
    return result

def state(r):
    q=vector(r['quaternion_wxyz'],4);q=q/np.linalg.norm(q);w,x,y,z=q
    return dict(time_s=r['time_s'],actual_position_um=(vector(r['position_m'],3)*1e6).tolist(),
        reference_position_um=(vector(r['reference_qpos'],7)[:3]*1e6).tolist(),
        roll_pitch_deg=[math.degrees(math.atan2(2*(w*x+y*z),1-2*(x*x+y*y))),
            math.degrees(math.asin(np.clip(2*(w*y-z*x),-1,1)))],
        velocity_world=r['velocity_world'],contact_wrench_M=r['contact_wrench_M'])

def segment_metrics(raw,start,end):
    search_segments(raw)
    if not 0<=start<end<=raw['control_cycles']:raise ValueError('Invalid half-open segment')
    traces=raw['trace'][start:end+1];actions=raw['actions'][start:end];ts=raw['transitions'][start:end]
    dt=np.asarray([t['dt'] for t in ts],float)
    if not np.isfinite(dt).all() or np.any(dt<=0):raise ValueError('Positive finite dt required')
    if not np.allclose(np.diff([r['time_s'] for r in traces]),dt,atol=1e-12,rtol=0):raise ValueError('dt mismatch')
    p=np.asarray([vector(r['position_m'],3) for r in traces]);ref=np.asarray([vector(r['reference_qpos'],7)[:3] for r in traces])
    requests=np.asarray([vector(a['applied_residual'],6) for a in actions]);cmd=np.asarray([vector(a['actual_end_limited_command'],6) for a in actions])
    raw_action=np.asarray([vector(a['raw_action'],4) for a in actions]);initial=np.asarray(raw['trace'][0]['position_m'])
    origin=traces[-1].get('search_progress_origin_z_m')
    return dict(start_cycle=start,end_cycle_exclusive=end,cycles=end-start,duration_s=float(dt.sum()),
        start_time_s=traces[0]['time_s'],end_time_s=traces[-1]['time_s'],entry=state(traces[0]),exit=state(traces[-1]),
        active_cycles=sum(bool(t['action_active']) for t in ts),
        actual_xy_net_um=((p[-1,:2]-p[0,:2])*1e6).tolist(),
        actual_xy_path_um=float(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1).sum()*1e6),
        reference_xy_net_um=((ref[-1,:2]-ref[0,:2])*1e6).tolist(),
        reference_xy_path_um=float(np.linalg.norm(np.diff(ref[:,:2],axis=0),axis=1).sum()*1e6),
        min_actual_global_xy_um=float(np.linalg.norm(p[:,:2],axis=1).min()*1e6),
        end_actual_global_xy_um=float(np.linalg.norm(p[-1,:2])*1e6),
        segment_z_net_um=float((p[-1,2]-p[0,2])*1e6),
        max_net_depth_beyond_frozen_peak_um=None if origin is None else float((p[:,2].max()-initial[2]-origin)*1e6),
        end_net_depth_beyond_frozen_peak_um=None if origin is None else float((p[-1,2]-initial[2]-origin)*1e6),
        total_command_xy_integral_um=(np.sum(cmd[:,:2]*dt[:,None],axis=0)*1e6).tolist(),
        request_xy_integral_um=(np.sum(requests[:,:2]*dt[:,None],axis=0)*1e6).tolist(),
        request_rotation_integral_mrad=(np.sum(requests[:,3:5]*dt[:,None],axis=0)*1000).tolist(),
        total_command_rotation_integral_mrad=(np.sum(cmd[:,3:5]*dt[:,None],axis=0)*1000).tolist(),
        mean_four_dimensional_action=np.average(raw_action,weights=dt,axis=0).tolist(),
        reference_filtered_cycles=sum(a['reference_filter_fraction']<1. for a in actions),
        max_cycle_force_mN=max(t['cycle_force_N'] for t in ts)*1000,
        reference_theta_end_rad=traces[-1]['spiral_theta_rad'])

def boundary_recheck(event,last_row):
    ref=vector(event['reference_xy_m'],2);pred=vector(event['predicted_reference_xy_m'],2);radius=float(event['radius_limit_m'])
    if not math.isfinite(radius) or radius<=0:raise ValueError('Positive radius required')
    return dict(current_radius_um=float(np.linalg.norm(ref)*1e6),next_radius_um=float(np.linalg.norm(pred)*1e6),
        current_inside=bool(np.linalg.norm(ref)<=radius+1e-12),next_outside=bool(np.linalg.norm(pred)>radius+1e-12),
        next_excess_nm=float((np.linalg.norm(pred)-radius)*1e9),
        actual_global_xy_um=float(np.linalg.norm(vector(last_row['position_m'],3)[:2])*1e6))

def reference_integration_error(raw,i):
    before,after=raw['trace'][i:i+2];a=raw['actions'][i];dt=raw['transitions'][i]['dt']
    resumed=before.get('phase')=='STOPPING' and after.get('phase')=='RUNNING' and any(
        e['reason']=='B2_RECOVERY_RESUMED' and math.isclose(e['time_s'],before['time_s'],abs_tol=1e-9)
        for e in raw.get('events',[]))
    start=before['position_m'] if resumed else before['reference_qpos'][:3]
    return float(np.max(np.abs(np.asarray(after['reference_qpos'][:3])-start-np.asarray(a['actual_end_limited_command'][:3])*dt)))

def reference_next(theta,ref,previous,dt):
    ref=vector(ref,2);previous=vector(previous,2);b=40e-6/(2*math.pi)
    if not math.isfinite(theta) or not math.isfinite(dt) or theta<0 or dt<=0:raise ValueError('Invalid theta/dt')
    radius=b*theta;target=radius*np.asarray([math.cos(theta),math.sin(theta)])
    next_theta=min(120e-6/b,theta+150e-6/math.hypot(radius,b)*dt)
    next_target=b*next_theta*np.asarray([math.cos(next_theta),math.sin(next_theta)])
    tangent=(next_target-target)/dt;tracking=5.*(target-ref)
    cmd=np.clip(np.clip(tangent+tracking,-300e-6,300e-6),-1e-3,1e-3)
    cmd=np.clip(cmd,previous-.005*dt,previous+.005*dt)
    return dict(theta_rad=theta,next_theta_rad=next_theta,target_radius_um=radius*1e6,
        target_xy_um=(target*1e6).tolist(),tracking_xy_um_s=(tracking*1e6).tolist(),
        feedforward_xy_um_s=(tangent*1e6).tolist(),limited_xy_um_s=(cmd*1e6).tolist(),next_reference_xy_um=((ref+cmd*dt)*1e6).tolist())

def verify_sources():
    counts={}
    for name,pin in SEALS.items():
        folder=BASE/name;p=folder/'delivery_manifest.json'
        assert sha(p)==pin,('manifest changed',name)
        files=read(p)['files'];counts[name]=len(files)
        for rel,meta in files.items():
            f=folder/rel;assert f.stat().st_size==meta['bytes'] and sha(f)==meta['sha256'],str(f)
    inputs=read(BASE/'v4_learning_requalification_20261006/configuration.json')['input_sha256']
    for rel,pin in inputs.items():assert sha(ROOT/rel)==pin,('production input changed',rel)
    return dict(sealed_file_counts=counts,production_inputs_unchanged=len(inputs))

def cycle_row(raw,label,k,i,start):
    before,after=raw['trace'][i:i+2];a=raw['actions'][i];t=raw['transitions'][i];composition=after['search_composition']
    assert composition is not None and math.isclose(composition['time_s'],before['time_s'],abs_tol=1e-12)
    row=dict(method=label,search=k,cycle=i,time_s=before['time_s'],elapsed_s=before['time_s']-raw['trace'][start]['time_s'],dt=t['dt'],
        theta_rad=composition['theta_rad'],actual_z_um=before['position_m'][2]*1e6,
        net_depth_um=(before['position_m'][2]-raw['trace'][0]['position_m'][2]-after['search_progress_origin_z_m'])*1e6,
        force_mN=t['cycle_force_N']*1000,filter_fraction=a['reference_filter_fraction'])
    for prefix,values,scale in [('actual',before['position_m'][:2],1e6),('reference_global',before['reference_qpos'][:2],1e6),
        ('reference_local',a['reference_xy_m'],1e6),('spiral_target',composition['target_xy_m'],1e6),
        ('feedforward',composition['feedforward_xy_m_s'],1e6),('tracking',composition['tracking_xy_m_s'],1e6),
        ('request_xy',a['applied_residual'][:2],1e6),('command_xy',a['actual_end_limited_command'][:2],1e6)]:
        for axis,value in zip(('x','y'),values):row[prefix+'_'+axis]=value*scale
    for j,name in enumerate(('x','y','roll','pitch')):row['action_'+name]=a['raw_action'][j]
    for j,name in [(3,'roll'),(4,'pitch')]:
        row['request_'+name+'_mrad_s']=a['applied_residual'][j]*1000
        row['command_'+name+'_mrad_s']=a['actual_end_limited_command'][j]*1000
    ref=vector(a['reference_xy_m'],2);req=vector(a['applied_residual'],6)[:2]
    row['request_radial_um_s']=float(np.dot(req,ref)/np.linalg.norm(ref)*1e6) if np.linalg.norm(ref)>1e-15 else 0.
    return row

def save_csv(path,rows):
    with path.open('w',encoding='utf8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed; verify only or run in a complete copy')
    proof=verify_sources();records=[];rows=[];raws={};common=None;checks=0;reference_error=0.
    for label,(relative,pin) in ARCHIVES.items():
        p=BASE/relative;assert sha(p)==pin
        raw=json.loads(gzip.decompress(p.read_bytes()));raws[label]=raw
        if common is None:common=raw['comparison_key']
        assert raw['comparison_key']==common and raw['case_id']=='y_neg_150'
        assert raw['physical_substeps']==10*raw['control_cycles']
        if label=='S50':
            assert raw['scope']=='frozen_development_evaluation' and raw['stage']=='final'
            assert raw['optimizer_steps_start']==raw['optimizer_steps']==2000
        else:assert raw['published_transitions']==0 and raw['training_admitted'] is False
        assert raw['outcome']['physical_stopped'] and raw['outcome']['simulation_valid']
        assert not any(raw['outcome']['guard_violations'].values()) and not raw.get('fault')
        ranges=search_segments(raw);segments=[]
        for i,(a,t) in enumerate(zip(raw['actions'],raw['transitions'])):
            assert a['enabled']==t['action_active']
            if a['enabled']:
                assert np.allclose(a['predicted_limited_command'],a['actual_end_limited_command'],rtol=0,atol=1e-15)
                checks+=1
        for k,(start,end) in enumerate(ranges,1):
            m=segment_metrics(raw,start,end);subset=[]
            for i in range(start,end):
                a=raw['actions'][i];before,after=raw['trace'][i:i+2];dt=raw['transitions'][i]['dt']
                assert a['enabled'] and a['reference_checked'] and 'reference_xy_m' in a
                err=reference_integration_error(raw,i)
                reference_error=max(reference_error,float(err));assert err<1e-14
                assert np.linalg.norm(a['predicted_reference_xy_m'])<=120e-6+1e-12
                row=cycle_row(raw,label,k,i,start);subset.append(row);rows.append(row)
            dt=np.asarray([r['dt'] for r in subset]);rad=np.asarray([r['request_radial_um_s'] for r in subset])
            m['mean_radial_requested_um_s']=float(np.average(rad,weights=dt))
            m['outward_request_fraction']=float(dt[rad>0].sum()/dt.sum())
            exits=[e for e in raw['controller_events'] if math.isclose(e['time_s'],m['end_time_s'],abs_tol=1e-9)]
            assert len(exits)==1;m['exit_event']=exits[0]
            if exits[0].get('reference_boundary_end'):
                m['boundary_recheck']=boundary_recheck(exits[0],raw['trace'][end])
                assert m['boundary_recheck']['current_inside'] and m['boundary_recheck']['next_outside']
                last=raw['trace'][end];local=np.asarray(last['reference_qpos'][:2])-raw['trace'][start]['position_m'][:2]
                assert np.allclose(local,exits[0]['reference_xy_m'],rtol=0,atol=1e-15)
                rederived=reference_next(last['spiral_theta_rad'],local,last['limited_command_world'][:2],raw['transitions'][end]['dt'])
                assert np.allclose(np.asarray(rederived['next_reference_xy_um'])*1e-6,exits[0]['predicted_reference_xy_m'],rtol=0,atol=1e-15)
                m['boundary_command_rederived']=rederived
                m['unused_search_time_s']=8.-m['duration_s']
            segments.append(m)
        records.append(dict(method=label,path=p.relative_to(ROOT).as_posix(),sha256=pin,
            actor_sha256=raw['policy_sha256'],outcome=raw['outcome']['task_outcome'],task_end_time_s=raw['task_end_time_s'],
            archive_cycles=raw['control_cycles'],segments=segments))
        print(label,len(ranges),'SEARCH segments',sum(e-s for s,e in ranges),'cycles',flush=True)
    alignment=[]
    for r in records:
        for seg in r['segments']:
            subset=[x for x in rows if x['method']==r['method'] and x['search']==r['segments'].index(seg)+1]
            for kind,points,key in [('elapsed_s',range(8),'elapsed_s'),('theta_rad',range(0,19,2),'theta_rad')]:
                for value in points:
                    if value>subset[-1][key]+1e-10:continue
                    match=min(subset,key=lambda x:abs(x[key]-value))
                    alignment.append(dict(alignment_kind=kind,requested_value=value,**match))
    g,s=raws['G50'],raws['S50'];gs,ss=search_segments(g)[0][0],search_segments(s)[0][0]
    initial_delta=vector(g['trace'][gs]['position_m'],3)-vector(s['trace'][ss]['position_m'],3)
    diff=next((i for i,(a,b) in enumerate(zip(g['trace'],s['trace'])) if a!=b),None)
    result=dict(scope='four existing negative-Y development archives, descriptive offline comparison only',
        source_proof=proof,common_key=common,records=records,archive_count=4,archive_cycles=sum(r['archive_cycles'] for r in records),
        search_segments=sum(len(r['segments']) for r in records),search_cycles=len(rows),
        active_command_prediction_checks=checks,max_reference_integration_error_m=reference_error,
        G_S_first_search_entry_position_delta_um=(initial_delta*1e6).tolist(),G_S_first_different_trace_row=diff,
        costs=dict(new_dynamics=0,new_physical_substeps=0,new_policy_inferences=0,new_optimizer_updates=0,new_published_transitions=0,cumulative_dynamic=208),
        state=dict(training_admission=False,automatic_tracking='PAUSED',old_budgets='closed'),
        definitions=dict(actual_motion='saved physical position, not integrated command',reference='saved drive reference, not actual position',
            requests='permission-applied XY/roll/pitch request; F12.5 already includes 0.25 deployment multiplier',
            mean_action='time-weighted deployed normalized 4-vector',net_depth='sensed Z beyond frozen historical peak; recovery retraction is not fresh progress'))
    assert verify_sources()==proof
    write(OUT/'configuration.json',dict(seals=SEALS,archives=ARCHIVES,common_key=common,scope=result['scope'],costs=result['costs']))
    write(OUT/'diagnosis.json',result);save_csv(OUT/'search_cycles.csv',rows);save_csv(OUT/'alignment.csv',alignment)
    print(json.dumps(dict(archives=4,archive_cycles=result['archive_cycles'],search_segments=result['search_segments'],search_cycles=len(rows),sources=proof,new_dynamics=0)),flush=True)

if __name__=='__main__':main()
