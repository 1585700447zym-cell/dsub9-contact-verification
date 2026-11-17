"""Read-only phasewise actual displacement and command accounting."""
from pathlib import Path
import ast,gzip,sys,importlib.util
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
BASE=OUT.parent/'threeway_online_yaw025_20261112'
spec=importlib.util.spec_from_file_location('run',BASE/'run_experiment.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
run.helper.select();run.verify(run.sha(BASE/'registration.json'))
from tools.validation.analyze_g1_recovery import JsonStream
source=OUT.parent/'threeway_diagnosis_20261113/analyze.py'
tree=ast.parse(source.read_text(encoding='utf8'));reader=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='read_archive')
exec(compile(ast.Module(body=[reader],type_ignores=[]),str(source),'exec'))
result={}
for g in 'ABC':
    p=BASE/'resume_C' if g=='C' else BASE
    for case in ('E01','E02'):
        key=g+'_'+case;trace,rows=read_archive(p/'run'/key/'episode.json.gz')
        end=run.read(p/'run'/key/'receipt.json')['task_end_time_s']
        t=np.array([r['time_s'] for r in trace]);xyz=np.array([r['position_m'] for r in trace])*1000
        dt=np.diff(t);delta=np.diff(xyz,axis=0);valid=t[:-1]<end-1e-9
        zero=np.array([r['zero'][:2] for r in rows]);eff=np.array([r['effective'][:2] for r in rows]);pred=np.array([r['predicted'][:2] for r in rows]);phase=np.array([r['phase'] for r in rows])
        assert np.allclose(zero+eff,pred,atol=1e-12,rtol=0)
        def summary(m):
            return dict(duration_s=float(dt[m].sum()),actual_delta_mm=delta[m,:2].sum(0).tolist(),
                zero_command_integral_mm=(zero[m]*dt[m,None]*1000).sum(0).tolist(),
                residual_command_integral_mm=(eff[m]*dt[m,None]*1000).sum(0).tolist(),
                composed_command_integral_mm=(pred[m]*dt[m,None]*1000).sum(0).tolist(),
                actual_minus_composed_mm=(delta[m,:2]-pred[m]*dt[m,None]*1000).sum(0).tolist())
        changes=np.r_[0,np.flatnonzero(phase[1:]!=phase[:-1])+1,len(rows)]
        segments=[]
        for a,b in zip(changes[:-1],changes[1:]):
            if phase[a]!='SEARCH' or not valid[a]:continue
            idx=np.arange(a,b);idx=idx[valid[idx]];b=int(idx[-1]+1)
            segments.append(dict(start_s=float(t[a]),end_s=float(t[b]),start_xyz_mm=xyz[a].tolist(),end_xyz_mm=xyz[b].tolist(),**summary(idx)))
        result[key]=dict(all_task=summary(valid),by_phase={str(k):summary(valid&(phase==k)) for k in sorted(set(phase)) if (valid&(phase==k)).any()},search_segments=segments)
        print(key,'searches',len(segments),flush=True)
run.write(OUT/'diagnostics.json',result)
