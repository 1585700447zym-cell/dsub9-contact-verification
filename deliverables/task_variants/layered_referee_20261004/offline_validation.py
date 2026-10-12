"""Frozen-trajectory referee comparison plus independent dense geometry checks."""
from pathlib import Path
import os,sys,json,gzip,math,hashlib
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_layered_referee'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.model.layered_task import _layer_margin,layered_pin_clearance_m,layered_pin_fit,functional_finish,referee_metadata
from tools.model.clearance_task import finish_criteria,pin_clearance_m
from tools.model.functional_task import functional_finish as old_finish

def dense_margin(center,rot,radius,half,zlo,zhi,hole,bore):
    theta=np.arange(65536)*2*np.pi/65536
    base=center+np.outer(radius*np.cos(theta),rot[:,0])+np.outer(radius*np.sin(theta),rot[:,1])
    low=np.maximum(-half,(zlo-base[:,2])/rot[2,2]);high=np.minimum(half,(zhi-base[:,2])/rot[2,2]);valid=low<=high
    if not np.any(valid):return None
    points=np.r_[base[valid]+np.outer(low[valid],rot[:,2]),base[valid]+np.outer(high[valid],rot[:,2])]
    xy=points[:,:2]-hole;angle=np.arctan2(xy[:,1],xy[:,0]);nearest=np.round(angle/(2*np.pi/256))*(2*np.pi/256)
    return bore-float(np.max(np.linalg.norm(xy,axis=1)*np.cos(angle-nearest)))

checks=[]
for rx,ry in [(0,0),(.007,0),(0,-.009),(.023,-.031),(-.044,.017)]:
    X=np.array([[1,0,0],[0,np.cos(rx),-np.sin(rx)],[0,np.sin(rx),np.cos(rx)]])
    Y=np.array([[np.cos(ry),0,np.sin(ry)],[0,1,0],[-np.sin(ry),0,np.cos(ry)]]);R=Y@X
    for center in [np.array([85e-6,-30e-6,.002]),np.array([0.,0.,-.00185]),np.array([0.,0.,.0002])]:
        for label,bore,zlo,zhi in [('entry',.000675,0,.00025),('main',.0006,.00025,.0045)]:
            analytic=_layer_margin(center,R,.0005,.002,zlo,zhi,np.zeros(2),bore)
            dense=dense_margin(center,R,.0005,.002,zlo,zhi,np.zeros(2),bore)
            assert (analytic is None)==(dense is None)
            error=None if analytic is None else dense-analytic
            # Dense sampling underestimates the maximum, so its margin is higher.
            if error is not None:assert -1e-13<=error<=2e-9,(rx,ry,center,label,error)
            checks.append(dict(roll=rx,pitch=ry,center=center.tolist(),layer=label,analytic_m=analytic,dense_m=dense,error_m=error))

archive=ROOT/'deliverables/task_variants/deadline25_20261004/run/y_neg_150.json.gz'
d=json.loads(gzip.decompress(archive.read_bytes()));e=d['summary'];criteria=finish_criteria()
window=[r for r in d['trace'] if e['stop_time']-1e-9<=r['time_s']<=e['stop_time']+1+1e-9]
out=[];start=None;best=0.;first_hold=None
for r in window:
    old=old_finish(r,criteria);new=functional_finish(r,criteria)
    if new:
        if start is None:start=r['time_s']
        best=max(best,r['time_s']-start)
        if first_hold is None and r['time_s']-start>=criteria['hold_s']-1e-12:first_hold=r['time_s']
    else:start=None
    out.append(dict(time_s=r['time_s'],old_ready=old,new_ready=new,
                    old_margin_um=pin_clearance_m(r)*1e6,new_margin_um=layered_pin_clearance_m(r)*1e6))
assert first_hold is not None and not any(r['old_ready'] for r in out)
last=d['trace'][-1];p=np.array(last['position_m']);unit=p[:2]/np.linalg.norm(p[:2]);sensitivity=[]
for shift in [0.,1e-9,10e-9,100e-9,1e-6]:
    rr=dict(last);pp=p.copy();pp[:2]+=unit*shift;rr['position_m']=pp.tolist()
    sensitivity.append(dict(outward_shift_nm=shift*1e9,margin_um=layered_pin_clearance_m(rr)*1e6,fit=layered_pin_fit(rr)))
assert sensitivity[0]['fit'] and not sensitivity[-1]['fit']
result=dict(no_new_physics=True,training=0,network=0,referee=referee_metadata(),
    dense_checks=checks,max_dense_error_m=max(abs(r['error_m']) for r in checks if r['error_m'] is not None),
    archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),historical_outcome='TASK_FAILURE',historical_unchanged=True,
    saved_samples=len(window),old_ready_samples=sum(r['old_ready'] for r in out),new_ready_samples=sum(r['new_ready'] for r in out),
    first_new_100ms_hold_time_s=first_hold,longest_new_hold_s=best,sensitivity=sensitivity,
    scope='Offline development diagnostic under new version, not a replacement of original recorded outcome')
(OUT/'offline_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
(OUT/'offline_replay_window.json').write_text(json.dumps(out,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k not in ['dense_checks','referee']},ensure_ascii=False))
