"""Pure command-reference integration, no model or physics stepping."""
from pathlib import Path
import sys,json,gzip,copy,math
import numpy as np
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT))
from tools.control.reference_search import ReferenceSearchRecovery,DriveObservation
from tools.control.axis_search import AxisSearchRecovery
from tools.dynamics.safety import limit_command


def run(cls):
    c=cls();obs=lambda t,ref,prev:DriveObservation(t,(0.,0.,0.),(0.,)*6,0.,tuple(ref),tuple(prev[:2]))
    c._start_search(obs(0.,np.zeros(3),np.zeros(6)))
    ref=np.zeros(3);previous=np.zeros(6);radius=error=0.;n=0
    for i in range(4100):
        u=c.command(obs(i*.002,ref,previous),.002)
        if c.phase!='SEARCH':break
        previous=limit_command(u,previous,.002,np.array([.001]*3+[.03]*3),np.array([.005]*3+[.3]*3))
        ref[:2]+=previous[:2]*.002;n+=1;radius=max(radius,float(np.linalg.norm(ref[:2])))
        error=max(error,float(np.linalg.norm(ref[:2]-c.search_composition['target_xy_m'])))
    return dict(phase=c.phase,cycles=n,event=c.events[-1],max_reference_radius_um=radius*1e6,max_target_error_um=error*1e6)


if __name__=='__main__':
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
    result=dict(old=run(AxisSearchRecovery),new=run(ReferenceSearchRecovery),physics_steps=0,training_updates=0,
        scope='Fixed blocked pose; arithmetic drive-reference integration only, not task success evidence')
    print(json.dumps(result,ensure_ascii=False))
    dest=OUT/('offline_probe.json' if '--save' in sys.argv else 'continuous_feedforward_boundary.json')
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
