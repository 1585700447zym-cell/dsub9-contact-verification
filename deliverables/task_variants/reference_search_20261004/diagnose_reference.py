"""Explain search-target versus integrated drive-reference divergence from archives."""
from pathlib import Path
import gzip,json,math,os
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
d=json.loads(gzip.decompress((OUT/'run/y_neg_150.json.gz').read_bytes()));rows=d['trace'];events=d['controller_events']
config=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'));c=config['b2_config']
at=lambda t:min(rows,key=lambda r:abs(r['time_s']-t))
starts=[e for e in events if e['reason']=='LOW_LOAD_SEARCH'];segments=[];all_samples=[]
for i,start in enumerate(starts):
    p0=np.array(at(start['time_s'])['position_m'][:2]);samples=[]
    end=next((e for e in events if e['time_s']>start['time_s'] and e['phase']!='SEARCH'),None)
    end_time=end['time_s'] if end else rows[-1]['time_s']
    for prev,row in zip(rows,rows[1:]):
        comp=row['search_composition']
        if comp is None or not start['time_s']-1e-9<=comp['time_s']<end_time-1e-9:continue
        target=p0+np.array(comp['target_xy_m']);ref=np.array(row['reference_qpos'][:2]);p=np.array(row['position_m'][:2])
        # Exact drive-reference kinematics when no per-substep lead clipping acts.
        predicted=np.array(prev['reference_qpos'][:2])+np.array(row['limited_command_world'][:2])*config['dynamic_config']['control_period']
        samples.append(dict(time_s=row['time_s'],target_xy_um=(target*1e6).tolist(),actual_xy_um=(p*1e6).tolist(),
            reference_xy_um=(ref*1e6).tolist(),target_radius_um=float(np.linalg.norm(target-p0)*1e6),
            reference_radius_um=float(np.linalg.norm(ref-p0)*1e6),actual_radius_um=float(np.linalg.norm(p-p0)*1e6),
            reference_target_error_um=float(np.linalg.norm(ref-target)*1e6),reference_actual_lead_um=float(np.linalg.norm(ref-p)*1e6),
            integration_error_um=float(np.max(np.abs(ref-predicted))*1e6),
            lateral_force_mN=float(np.linalg.norm(row['contact_wrench_M'][:2])*1000),
            total_force_mN=float(np.linalg.norm(row['contact_wrench_M'][:3])*1000),raw_xy_mm_s=(np.array(row['raw_command_world'][:2])*1000).tolist()))
    peak=max(samples,key=lambda x:x['reference_radius_um']);maxerror=max(samples,key=lambda x:x['reference_target_error_um'])
    segments.append(dict(search_number=i+1,samples=len(samples),max_target_radius_um=max(s['target_radius_um'] for s in samples),
        max_reference_radius_um=peak['reference_radius_um'],max_reference_target_error_um=maxerror['reference_target_error_um'],
        max_reference_actual_lead_um=max(s['reference_actual_lead_um'] for s in samples),
        max_reference_integration_error_um=max(s['integration_error_um'] for s in samples),
        peak_reference_example=peak,end_example=samples[-1]))
    all_samples.append(samples)
result=dict(searches=segments,
    mechanism='Search now tracks its own drive reference. This report measures residual tracking error and actual motion separately.',
    implication='Interpret task outcome and loads separately; a bounded reference alone does not establish insertion success.',
    limitations='This is archived trajectory evidence, not a general success or causality guarantee. No friction/geometry tuning or extra physics executed.')
(OUT/'reference_diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_reference_search'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axes=plt.subplots(1,max(1,len(all_samples)),figsize=(5*max(1,len(all_samples)),5.1),squeeze=False)
for ax,samples,i in zip(axes[0],all_samples,range(1,len(all_samples)+1)):
    for key,label in [('target_xy_um','Spiral target'),('reference_xy_um','Drive reference'),('actual_xy_um','Actual pose')]:
        xy=np.array([s[key] for s in samples]);ax.plot(xy[:,0],xy[:,1],label=label)
    ax.set(xlabel='X (um)',ylabel='Y (um)',title=f'Search {i}');ax.axis('equal');ax.grid(alpha=.2);ax.legend(fontsize=8)
fig.suptitle('Spiral target, bounded drive reference and actual motion',fontsize=11)
fig.tight_layout(rect=(0,0,1,.95));fig.savefig(OUT/'reference_diagnosis.png',dpi=150);fig.savefig(OUT/'reference_diagnosis.pdf');plt.close(fig)
