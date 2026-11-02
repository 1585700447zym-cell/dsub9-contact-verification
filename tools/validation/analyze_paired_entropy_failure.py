"""Saved-trace postmortem only: no environment, neural forward or optimizer calls."""
from collections import Counter
from itertools import combinations
import gzip
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.learning.five_axis_preparation import read,sha,verify_inputs
from tools.validation.run_yaw_pilot import write,NoLearning

BATCH=ROOT/'deliverables/learning_chain/five_axis_entropy_closed_loop_20261026'
OUT=ROOT/'deliverables/learning_chain/five_axis_entropy_postmortem_20261027'


def rotations(quaternions):
    q=np.asarray(quaternions,dtype=float);q=q/np.linalg.norm(q,axis=1)[:,None]
    w,x,y,z=q.T
    return np.stack((1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w),
                     2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w),
                     2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)),axis=1).reshape(-1,3,3)


def minimum_enclosing_radius(points):
    # Nine points: the optimal enclosing circle has two or three boundary points.
    p=np.asarray(points)*1e6;origin=p.mean(0);p=p-origin
    centers=[np.zeros(2)]
    centers.extend((p[i]+p[j])/2 for i,j in combinations(range(len(p)),2))
    for i,j,k in combinations(range(len(p)),3):
        matrix=2*np.array([p[j]-p[i],p[k]-p[i]])
        if abs(np.linalg.det(matrix))<1e-12:continue
        centers.append(np.linalg.solve(matrix,np.array([p[j]@p[j]-p[i]@p[i],p[k]@p[k]-p[i]@p[i]])))
    radii=np.linalg.norm(p[None]-np.array(centers)[:,None],axis=2).max(1)
    best=int(np.argmin(radii))
    return dict(radius_um=float(radii[best]),optimal_common_xy_shift_um=(-(centers[best]+origin)).tolist())


def analyze(raw,referee,pins,sizes,layers):
    trace=raw['trace'];transitions=raw['transitions']
    stop=next(e['time_s'] for e in raw['evidence']['environment_events'] if e['reason']=='TIME_LIMIT')
    end=min(range(len(trace)),key=lambda i:abs(trace[i]['time_s']-stop))
    tr=trace[:end+1];rows=transitions[:end];times=np.array([r['time_s'] for r in tr])
    position=np.array([r['position_m'] for r in tr]);q=np.array([r['quaternion_wxyz'] for r in tr])
    rot=rotations(q);axis=rot[:,:,2]
    centers=np.einsum('nij,kj->nki',rot,pins)+position[:,None]
    tips=centers+axis[:,None]*sizes[None,:,1,None]
    rim=sizes[None,:,0]*np.sqrt(np.maximum(0,1-axis[:,2,None]**2))
    zmax=tips[:,:,2]+rim
    mouth=centers[:,:,:2]+axis[:,None,:2]*(0-centers[:,:,2,None])/axis[:,None,2,None]
    offsets=mouth-pins[None,:,:2]
    center_errors=np.linalg.norm(offsets,axis=2)
    yaw=np.degrees(np.arctan2(rot[:,1,0],rot[:,0,0]))
    rpy=np.c_[np.degrees(np.arctan2(rot[:,2,1],rot[:,2,2])),
              np.degrees(np.arcsin(np.clip(-rot[:,2,0],-1,1))),yaw]
    contact=np.array([r['contact_count']>0 for r in tr]);running=np.array([r['phase']=='RUNNING' for r in tr])
    first=int(np.flatnonzero(contact)[0]);best=int(np.argmin(np.where(running & (times>=times[first]),center_errors.max(1),np.inf)))
    start_search=next(e['time_s'] for e in raw['evidence']['controller_events'] if e['reason']=='LOW_LOAD_SEARCH')
    search_index=int(np.argmin(abs(times-start_search)))
    key_indices={'first_contact':first,'first_search':search_index,'best_mouth_center_alignment':best,'control_end':end}
    keyframes={}
    entry=layers[0];main=layers[1];tol=1e-9
    for name,index in key_indices.items():
        values=[]
        for i in range(9):
            c=centers[index,i];r=rot[index]
            zlo=c[2]-sizes[i,1]*axis[index,2]-rim[index,i]
            zhi=zmax[index,i]
            detail=dict(pin=i+1,axis_tip_z_um=float(tips[index,i,2]*1e6),rim_top_z_um=float(zhi*1e6),
                        mouth_centerline_error_um=float(center_errors[index,i]*1e6),layers={})
            for layer_name,radius,lo,hi in layers:
                depth=max(0.,min(hi,zhi)-max(lo,zlo))
                margin=referee(c,r,sizes[i,0],sizes[i,1],lo,hi,pins[i,:2],radius)
                detail['layers'][layer_name]=dict(overlap_z_um=depth*1e6,
                    clearance_um=None if margin is None else float(margin*1e6),
                    overlaps_and_fits=bool(depth>tol and margin is not None and margin>=-tol))
            values.append(detail)
        keyframes[name]=dict(time_s=float(times[index]),position_m=position[index].tolist(),
            rpy_deg=rpy[index].tolist(),pins=values,
            entry_overlaps_and_fits=sum(p['layers']['entry']['overlaps_and_fits'] for p in values),
            main_overlaps_and_fits=sum(p['layers']['main']['overlaps_and_fits'] for p in values),
            maximum_rim_entry_depth_um=float(max(0,zmax[index].max())*1e6),
            maximum_mouth_centerline_error_um=float(center_errors[index].max()*1e6),
            orientation_spread_optimal_xy=minimum_enclosing_radius(offsets[index]))
    active=np.array([r['action_active'] for r in rows]);phases=np.array([r['action_log']['composition_inputs']['phase'] for r in rows])
    base=np.array([r['action_log']['composition_inputs']['base_command'] for r in rows])
    request=np.array([r['action_log']['applied_residual'] for r in rows])
    local=np.array([r['action_log']['effective_command_delta'] for r in rows])
    commands=np.array([r['limited_command_world'] for r in tr[1:]])
    velocity=np.array([r['velocity_world'] for r in tr[1:]])
    ref=np.array([r['reference_qpos'][:3] for r in tr]);lead=ref[1:]-position[1:]
    drive=np.array([r['drive_wrench_M'] for r in tr[1:]])
    wrench=np.array([r['contact_wrench_M'] for r in tr[1:]])
    groups={};axes=[0,1,3,4,5]
    for name,mask in [('all_active',active),('search',active & (phases=='SEARCH')),
                      ('insert',active & (phases=='INSERT'))]:
        denominator=abs(request[mask][:,axes]).sum(0)
        ratio=np.divide(abs(local[mask][:,axes]).sum(0),denominator,out=np.full(5,np.nan),where=denominator>1e-12)
        groups[name]=dict(cycles=int(mask.sum()),
            mean_abs_request_micro_units=(abs(request[mask][:,axes]).mean(0)*1e6).tolist(),
            mean_signed_request_micro_units=(request[mask][:,axes].mean(0)*1e6).tolist(),
            local_command_gain_auxiliary=[None if not np.isfinite(x) else float(x) for x in ratio],
            mean_abs_base_micro_units=(abs(base[mask][:,axes]).mean(0)*1e6).tolist(),
            signed_yaw_request_integral_deg=float(np.degrees(request[mask,5].sum()*.002)),
            signed_yaw_base_integral_deg=float(np.degrees(base[mask,5].sum()*.002)),
            mean_Mz_Nm=float(wrench[mask,5].mean()),
            reference_xy_near_120um_fraction=np.mean(abs(lead[mask,:2])>=117e-6,axis=0).tolist(),
            reference_filter_cycles=sum(rows[i]['action_log']['reference_filter_fraction']<1 for i in np.flatnonzero(mask)))
    adjacent=active[1:] & active[:-1] & (phases[1:]==phases[:-1])
    changed=(request[1:,5]*request[:-1,5]<0)
    nonzero=adjacent & (abs(request[1:,5])>1e-10) & (abs(request[:-1,5])>1e-10)
    persistence=dict(yaw_sign_flip_fraction=float(changed[nonzero].mean()),
        yaw_net_over_absolute_integral=float(abs(request[active,5].sum())/abs(request[active,5]).sum()),
        correction_toward_xy_origin_fraction=float((np.sum(request[active,:2]*position[1:][active,:2],axis=1)<0).mean()))
    # Same 20 ms windows for actual displacement versus integrated command.
    window_errors=[];window_yaw=[];cursor=0
    while cursor<len(rows):
        if not active[cursor]:cursor+=1;continue
        j=cursor
        while j<len(rows) and j<cursor+10 and active[j] and phases[j]==phases[cursor]:j+=1
        duration=(j-cursor)*.002
        window_yaw.append((duration,abs(request[cursor:j,5].mean())))
        if np.any(contact[cursor:j+1]):
            measured=(position[j,:2]-position[cursor,:2])/duration
            intended=commands[cursor:j,:2].mean(0)
            window_errors.append((duration,abs(measured-intended)))
        cursor=j
    total=sum(x[0] for x in window_errors)
    errors=sum((dt*error for dt,error in window_errors),np.zeros(2))/total*1e6
    persistence['yaw_twenty_ms_abs_mean_over_cycle_abs_mean']=float(sum(dt*x for dt,x in window_yaw)/sum(dt for dt,x in window_yaw)/abs(request[active,5]).mean())
    action_array=np.array([r['action'] for r in rows])
    result=dict(control_deadline_s=stop,legacy_settle_end_s=raw['evidence']['task_end_time_s'],
        audit_end_s=raw['evidence']['audit_end_time_s'],keyframes=keyframes,groups=groups,
        initial_rpy_deg=rpy[0].tolist(),final_rpy_at_25s_deg=rpy[-1].tolist(),
        minimum_radial_center_error_mm=float(np.linalg.norm(position[running,:2],axis=1).min()*1000),
        minimum_reference_radial_error_mm=float(np.linalg.norm(ref[running,:2],axis=1).min()*1000),
        final_radial_center_error_mm=float(np.linalg.norm(position[-1,:2])*1000),
        maximum_advance_mm=float((position[:,2].max()-position[0,2])*1000),
        final_advance_mm=float((position[-1,2]-position[0,2])*1000),
        maximum_any_pin_rim_z_um=float(zmax.max()*1e6),
        any_pin_main_layer_overlap=bool(np.any(zmax>main[2]+tol)),
        minimum_maximum_mouth_centerline_error_um=float(center_errors[running].max(1).min()*1e6),
        time_all_nine_centerline_entry_necessary_condition_s=float(np.sum(running & (center_errors.max(1)<=entry[1]-sizes[0,0]))*.002),
        mean_abs_deterministic_action_percent=(abs(action_array[active]).mean(0)*100).tolist(),
        temporal_action_consistency=persistence,
        contact_window_velocity_error_um_s=errors.tolist(),
        peak_force_N=max(p['force_N'] for p in raw['cycle_peaks']),
        controller_events=raw['evidence']['controller_events'],environment_events=raw['evidence']['environment_events'])
    plot=dict(time=times[::20],position=position[::20],rpy=rpy[::20])
    return result,plot


def main():
    sys.meta_path.insert(0,NoLearning())
    from tools.validation.run_five_axis_training import select
    select()  # Select the bound DLL for geometry-module imports; no environment is made.
    from tools.model.layered_task import _layer_margin,_LAYERS,referee_metadata
    from tools.model.clearance_task import _pin_centers,_pin_sizes
    reg=read(BATCH/'registration.json');verify_inputs(reg['inputs'])
    if (OUT/'verification.json').exists():raise FileExistsError('Closed analysis exists')
    OUT.mkdir(exist_ok=True)
    # Hand-checked geometry sanity: aligned overlapping cylinders have 175/100 um clearance.
    r=np.eye(3);c=_pin_centers[0]+np.array([0,0,-.003])
    assert abs(_layer_margin(c,r,.0005,.002,0,.00025,_pin_centers[0,:2],.000675)-.000175)<1e-12
    assert abs(_layer_margin(c,r,.0005,.002,.00025,.0045,_pin_centers[0,:2],.0006)-.0001)<1e-12
    assert abs(minimum_enclosing_radius(np.array([[-.0001,0],[.0001,0],[0,.0001]]))['radius_um']-100)<1e-9
    results={};plots={};pins={}
    for arm in ('A0','A2'):
        for job in reg['schedule'][8:]:
            folder=BATCH/'run'/arm/job['id'];receipt=read(folder/'receipt.json')
            archive=folder/'episode.json.gz';digest=sha(archive)
            if digest!=receipt['archive_sha256']:raise ValueError('Raw archive changed')
            raw=json.loads(gzip.decompress(archive.read_bytes()))
            name=arm+'_'+job['case']['name']
            results[name],plots[name]=analyze(raw,_layer_margin,_pin_centers,_pin_sizes,_LAYERS)
            results[name]['actuator_counters']=receipt['actuator_counters']
            pins[archive.relative_to(ROOT).as_posix()]=digest
            del raw
            x=results[name]
            print(name,json.dumps({k:x[k] for k in ('final_rpy_at_25s_deg','minimum_radial_center_error_mm',
                'minimum_maximum_mouth_centerline_error_um','maximum_any_pin_rim_z_um','any_pin_main_layer_overlap',
                'time_all_nine_centerline_entry_necessary_condition_s')},ensure_ascii=False),flush=True)
    write(OUT/'development_trace_diagnosis.json',dict(results=results,input_sha256=pins,
        geometry=referee_metadata(),new_initializations=0,new_physical_substeps=0,new_neural_inference=0,new_optimizer_updates=0,
        qualifications='Pure geometry sanity checks only; no added physical qualification',
        limits='No archived contact-pair IDs; finite-cylinder layer occupancy is geometric diagnosis, not a new success verdict'))
    arrays={}
    for key,plot in plots.items():
        for field,value in plot.items():arrays[key+'_'+field]=value
    np.savez_compressed(OUT/'plot_arrays.npz',**arrays)
    (OUT/'analysis_source_snapshot').mkdir(exist_ok=True)
    (OUT/'analysis_source_snapshot'/Path(__file__).name).write_bytes(Path(__file__).read_bytes())


if __name__=='__main__':main()
