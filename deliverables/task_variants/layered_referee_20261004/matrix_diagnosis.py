"""Completion and failure components from bounded saved trajectories."""
from pathlib import Path
import os,sys,json,gzip,math
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_layered_referee'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.model.layered_task import layered_pin_clearance_m,layered_pin_fit,functional_finish
from tools.model.clearance_task import finish_criteria,pin_clearance_m
c=finish_criteria()
ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf-8'));results={};series={}

def components(r):
    return dict(depth=bool(abs(r['position_m'][2])<=c['z_tolerance_m']),nine_pin_fit=layered_pin_fit(r),
        linear_stable=bool(np.linalg.norm(r['velocity_world'][:3])<=c['linear_speed_m_s']),
        angular_stable=bool(np.linalg.norm(r['velocity_world'][3:])<=c['angular_speed_rad_s']),
        force=bool(np.linalg.norm(r['contact_wrench_G'][:3])<c['force_N']),
        torque=bool(np.linalg.norm(r['contact_wrench_G'][3:])<c['torque_Nm']),
        penetration=bool(r['penetration_m']<c['penetration_m']))

for e in ledger['episodes']:
    d=json.loads(gzip.decompress((OUT/'run'/f"{e['id']}.json.gz").read_bytes()));rows=d['trace'];final=rows[-1]
    window=[r for r in rows if e['stop_time']-1e-9<=r['time_s']<=e['stop_time']+1+1e-9]
    margins=[layered_pin_clearance_m(r)*1e6 for r in window];ready=[functional_finish(r,c) for r in window]
    comp=components(final)
    results[e['id']]=dict(final_components=comp,failed_at_final=[k for k,v in comp.items() if not v],
        final_margin_um=layered_pin_clearance_m(final)*1e6,legacy_margin_um=pin_clearance_m(final)*1e6,
        settling_min_margin_um=min(margins),settling_max_margin_um=max(margins),settling_ready_samples=sum(ready),settling_samples=len(window),
        first_depth_ready_s=next((r['time_s'] for r in rows if abs(r['position_m'][2])<=20e-6),None),
        final_linear_speed_um_s=float(np.linalg.norm(final['velocity_world'][:3])*1e6),
        final_force_mN=float(np.linalg.norm(final['contact_wrench_G'][:3])*1000),final_penetration_um=final['penetration_m']*1e6,
        final_advance_mm=(final['position_m'][2]-rows[0]['position_m'][2])*1000,reason=e['reason'],events=d['controller_events'])
    series[e['id']]=[dict(time_s=r['time_s'],z_um=r['position_m'][2]*1e6,margin_um=m,ready=ok,
         legacy_margin_um=pin_clearance_m(r)*1e6,speed_um_s=float(np.linalg.norm(r['velocity_world'][:3])*1e6)) for r,m,ok in zip(window,margins,ready)]
(OUT/'completion_diagnosis.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(OUT/'completion_window.json').write_text(json.dumps(series,indent=2)+'\n',encoding='utf-8')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,ax=plt.subplots(3,1,figsize=(10,9),sharex=True)
for name,samples in series.items():
    start=samples[0]['time_s'];t=[r['time_s']-start for r in samples]
    ax[0].plot(t,[r['z_um'] for r in samples],label=name)
    ax[1].plot(t,[r['margin_um'] for r in samples],label=name)
    ax[2].plot(t,[r['speed_um_s'] for r in samples],label=name)
ax[0].axhspan(-20,20,color='green',alpha=.12);ax[0].set_ylabel('Z (um)')
ax[1].axhline(-.001,color='red',ls='--');ax[1].set_ylabel('Layered pin clearance (um)')
ax[2].axhline(10,color='red',ls='--');ax[2].set_ylabel('Linear speed (um/s)');ax[2].set_xlabel('Time since final stop request (s)')
for a in ax:a.grid(alpha=.2);a.legend(fontsize=8)
fig.suptitle('New common referee: depth, layered geometry, and settling');fig.tight_layout()
fig.savefig(OUT/'completion.png',dpi=150);fig.savefig(OUT/'completion.pdf');plt.close(fig)
print(json.dumps({k:{n:v[n] for n in ['reason','final_margin_um','failed_at_final','final_advance_mm']} for k,v in results.items()},ensure_ascii=False))
