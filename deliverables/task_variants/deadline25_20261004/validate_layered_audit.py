"""Independent dense surface check and saved settling-window diagnostic only."""
from pathlib import Path
import importlib.util,json,gzip,math
import numpy as np
OUT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('layered_audit',OUT/'layered_geometry_audit.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
d=json.loads(gzip.decompress((OUT/'run/y_neg_150.json.gz').read_bytes()));e=d['summary'];row=d['trace'][-1]
rot=m.rotation(row);angles=np.linspace(0,2*np.pi,65536,endpoint=False)
errors=[];validated=[]
for i,(p,size) in enumerate(zip(m._pin_centers,m._pin_sizes)):
    center=rot@p+row['position_m']
    base=center+np.outer(size[0]*np.cos(angles),rot[:,0])+np.outer(size[0]*np.sin(angles),rot[:,1])
    for layer,bore,zlo,zhi in [('entry',.000675,0.,.00025),('main',.0006,.00025,.0045)]:
        low=np.maximum(-size[1],(zlo-base[:,2])/rot[2,2])
        high=np.minimum(size[1],(zhi-base[:,2])/rot[2,2]);valid=low<=high
        points=np.r_[base[valid]+np.outer(low[valid],rot[:,2]),base[valid]+np.outer(high[valid],rot[:,2])]
        xy=points[:,:2]-p[:2];radii=np.linalg.norm(xy,axis=1)
        angle=np.arctan2(xy[:,1],xy[:,0]);nearest=np.round(angle/(2*np.pi/256))*(2*np.pi/256)
        polygon=float((bore-np.max(radii*np.cos(angle-nearest)))*1e6)
        circular=float((bore-np.max(radii))*1e6)
        analytic=m.layer_margin(center,rot,size[0],size[1],zlo,zhi,p[:2],bore)
        delta=[polygon-analytic['margin_um'],circular-analytic['circular_margin_um']]
        assert min(delta)>-1e-7 and max(delta)<.001,delta
        errors+=delta
        validated.append(dict(pin=i,layer=layer,dense_polygon_margin_um=polygon,dense_circular_margin_um=circular,analytic_minus_dense_error_um=[-x for x in delta]))
window=[r for r in d['trace'] if e['stop_time']-1e-9<=r['time_s']<=e['stop_time']+1+1e-9]
minimum=math.inf;minimum_circular=math.inf;ready_start=None;best_hold=0.;first_ready=None;series=[]
for r in window:
    check=m.audit(r);margin=check['exact_polygon_layer_margin_um'];circle=check['exact_circular_layer_margin_um']
    minimum=min(minimum,margin);minimum_circular=min(minimum_circular,circle)
    series.append(dict(time_s=r['time_s'],polygon_margin_um=margin,circular_margin_um=circle))
    # Same original depth/speed/wrench/penetration criteria; only geometry is
    # compared diagnostically. This is NOT the recorded session adjudicator.
    ready=(abs(r['position_m'][2])<=20e-6 and np.linalg.norm(r['velocity_world'][:3])<=1e-5
       and np.linalg.norm(r['velocity_world'][3:])<=.001 and np.linalg.norm(r['contact_wrench_G'][:3])<.025
       and np.linalg.norm(r['contact_wrench_G'][3:])<.0005 and r['penetration_m']<30e-6 and margin>=0)
    if ready:
        if ready_start is None:ready_start=r['time_s']
        if first_ready is None:first_ready=r['time_s']
        best_hold=max(best_hold,r['time_s']-ready_start)
    else:ready_start=None
record=dict(no_new_physics=True,recorded_verdict_unchanged='TASK_FAILURE',angles_per_dense_circle=65536,
    dense_final_layers_checked=len(validated),max_dense_vs_analytic_difference_um=max(abs(x) for x in errors),
    settling_samples_checked=len(window),minimum_polygon_layer_margin_um=minimum,minimum_circular_layer_margin_um=minimum_circular,
    diagnostic_ready_first_s=first_ready,diagnostic_longest_hold_s=best_hold,required_hold_s=.1,
    scope='Read-only counterfactual geometry diagnostic, not new runtime acceptance or robust margin proof',dense_checks=validated)
(OUT/'layered_geometry_validation.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
(OUT/'layered_geometry_window.json').write_text(json.dumps(series,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in record.items() if k!='dense_checks'}))
