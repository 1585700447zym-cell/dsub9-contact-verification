"""Offline completion-component checks on saved physical states; never step simulation."""
from pathlib import Path
import os,sys,json,gzip,math
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT));os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_deadline25'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.model.clearance_task import finish_criteria,pin_clearance_m,_pin_centers,_pin_sizes
from tools.model.functional_task import functional_finish
c=finish_criteria()
def components(r):
    return dict(depth=bool(abs(r['position_m'][2])<=c['z_tolerance_m']),
        nine_pin_fit=bool(pin_clearance_m(r)>=-1e-9),
        linear_stable=bool(np.linalg.norm(r['velocity_world'][:3])<=c['linear_speed_m_s']),
        angular_stable=bool(np.linalg.norm(r['velocity_world'][3:])<=c['angular_speed_rad_s']),
        force=bool(np.linalg.norm(r['contact_wrench_G'][:3])<c['force_N']),
        torque=bool(np.linalg.norm(r['contact_wrench_G'][3:])<c['torque_Nm']),
        penetration=bool(r['penetration_m']<c['penetration_m']))

def longest(rows,predicate):
    start=None;best=0.
    for r in rows:
        if predicate(r):
            if start is None:start=r['time_s']
            best=max(best,r['time_s']-start)
        else:start=None
    return best

def surface_witness(row):
    # Sample true cylindrical surface points. Any point outside the ideal
    # radius inside the main-bore Z slab is a constructive violation, even
    # when the all-shaft sufficient bound alone could be conservative.
    w,x,y,z=np.array(row['quaternion_wxyz'])/np.linalg.norm(row['quaternion_wxyz'])
    rot=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                  [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                  [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
    angle=np.linspace(0,2*np.pi,4096,endpoint=False)
    worst=None
    for i,(center,size) in enumerate(zip(_pin_centers,_pin_sizes)):
        for axial in np.linspace(-size[1],size[1],33):
            local=center+np.c_[size[0]*np.cos(angle),size[0]*np.sin(angle),np.full(len(angle),axial)]
            points=local@rot.T+row['position_m']
            points=points[(points[:,2]>=.00025)&(points[:,2]<=.0045)]
            if not len(points):continue
            radial=np.linalg.norm(points[:,:2]-center[:2],axis=1);j=int(np.argmax(radial))
            margin=(.0006-radial[j])*1e6
            if worst is None or margin<worst['margin_um']:
                worst=dict(pin_index=i,margin_um=float(margin),point_world_m=points[j].tolist(),
                    ideal_main_bore_radius_m=.0006,scope='sampled exact cylinder surface point inside main bore, not a contact-solver penetration estimate')
    return worst

ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf-8'));results={};traces={}
for e in ledger['episodes']:
    d=json.loads(gzip.decompress((OUT/'run'/f"{e['id']}.json.gz").read_bytes()));rows=d['trace'];traces[e['id']]=rows
    window=[r for r in rows if e['stop_time']-1e-9<=r['time_s']<=e['stop_time']+1+1e-9]
    vals=[components(r) for r in window]
    result=dict(reason=e['reason'],stop_time_s=e['stop_time'],task_end_time_s=e['task_end_time'],
        first_depth_ready_s=next((r['time_s'] for r in rows if abs(r['position_m'][2])<=c['z_tolerance_m']),None),
        final_components=components(rows[-1]),failed_at_final=[k for k,v in components(rows[-1]).items() if not v],
        settling_samples=len(window),settling_fail_counts={k:sum(not x[k] for x in vals) for k in vals[0]},
        settling_best_pin_margin_um=max(pin_clearance_m(r)*1e6 for r in window),
        settling_worst_pin_margin_um=min(pin_clearance_m(r)*1e6 for r in window),
        longest_functional_hold_s=longest(window,lambda r:functional_finish(r,c)),
        required_hold_s=c['hold_s'],final_pin_margin_um=pin_clearance_m(rows[-1])*1e6,
        final_velocity_linear_um_s=float(np.linalg.norm(rows[-1]['velocity_world'][:3])*1e6),
        final_velocity_angular_rad_s=float(np.linalg.norm(rows[-1]['velocity_world'][3:])),
        final_force_mN=float(np.linalg.norm(rows[-1]['contact_wrench_G'][:3])*1000),
        final_penetration_um=rows[-1]['penetration_m']*1e6,
        final_surface_witness=surface_witness(rows[-1]),no_new_physics=True)
    results[e['id']]=result
(OUT/'completion_diagnosis.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(results,ensure_ascii=False))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
rows=traces['y_neg_150'];e=ledger['episodes'][0];tail=[r for r in rows if r['time_s']>=19.5]
fig,ax=plt.subplots(3,1,figsize=(9,8),sharex=True)
t=[r['time_s'] for r in tail]
ax[0].plot(t,[r['position_m'][2]*1e6 for r in tail],label='Actual Z')
ax[0].axhspan(-20,20,color='green',alpha=.15,label='Depth acceptance')
ax[0].set_ylabel('Z (um)')
ax[1].plot(t,[pin_clearance_m(r)*1e6 for r in tail],label='Nine-pin sufficient fit margin')
if (OUT/'layered_geometry_window.json').exists():
    window=json.loads((OUT/'layered_geometry_window.json').read_text(encoding='utf-8'))
    ax[1].plot([r['time_s'] for r in window],[r['polygon_margin_um'] for r in window],label='Offline actual-layer audit (unchanged verdict)')
ax[1].axhline(-.001,color='red',ls='--',label='Acceptance threshold')
ax[1].set_ylabel('Pin margin (um)')
ax[2].plot(t,[np.linalg.norm(r['velocity_world'][:3])*1e6 for r in tail],label='Actual linear speed')
ax[2].axhline(10,color='red',ls='--',label='Stable speed threshold')
ax[2].set_ylabel('Speed (um/s)');ax[2].set_xlabel('Simulation time (s)')
for axis in ax:
    axis.axvline(e['stop_time'],color='black',ls=':',label='Stop request')
    axis.grid(alpha=.2);axis.legend(fontsize=8)
fig.suptitle('25 s task: insertion depth, fit, and actual settling')
fig.tight_layout();fig.savefig(OUT/'completion.png',dpi=150);fig.savefig(OUT/'completion.pdf');plt.close(fig)
