"""Offline archived counterexamples and compatibility checks; no physics steps."""
from pathlib import Path
import copy,gzip,json,math,sys,types,importlib.util
import numpy as np
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tools.control.axis_search import AxisSearchRecovery
from tools.control.compliant_search import CompliantSearchRecovery
from tools.control.risk_search import PoseObservation
from tools.control.search_recovery import SearchRecovery,Observation


def module(name,source):
    mod=types.ModuleType(name);sys.modules[name]=mod;exec(source,mod.__dict__);return mod


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
    d=json.loads(gzip.decompress((ROOT/'deliverables/task_variants/compliant_search_20261004/run/y_neg_150.json.gz').read_bytes()))
    rows=d['trace'];events=d['controller_events'];at=lambda t:min(rows,key=lambda r:abs(r['time_s']-t))
    starts=[e for e in events if e['reason']=='LOW_LOAD_SEARCH']
    sample=at(8.);r=at(sample['search_composition']['time_s']);origin=at(starts[0]['time_s'])
    sensed=lambda row:PoseObservation(row['time_s'],tuple(np.array(row['position_m'])-rows[0]['position_m']),tuple(row['contact_wrench_M']),0.)
    c=AxisSearchRecovery();c._start_search(sensed(origin));c.theta=sample['search_composition']['theta_rad']
    c.admittance.offset[:2]=r['commanded_correction'][:2];c.admittance.velocity[:2]=r['admittance_velocity'][:2]
    u=c.command(sensed(r),.002)
    assert np.linalg.norm(c.search_composition['target_xy_m'])>5*np.linalg.norm(sample['search_composition']['target_xy_m'])
    adv=next(e for e in events if e['reason']=='SEARCH_ADVANCED');a=at(adv['time_s']);start=at(starts[1]['time_s'])
    peak=max(x['position_m'][2]-rows[0]['position_m'][2] for x in rows if x['time_s']<=starts[1]['time_s'])
    new=AxisSearchRecovery();new.episode_peak_z_m=peak;new._start_search(sensed(start))
    old=CompliantSearchRecovery();old._start_search(sensed(start))
    assert old._search_advanced(sensed(a)) and not new._search_advanced(sensed(a))
    # Reconstitute the old inheritance chain from saved pre-edit sources.
    legacy_base=module('axis_probe_old_base',(OUT/'before/search_recovery.py').read_text(encoding='utf-8'))
    legacy_risk=module('axis_probe_old_risk',(ROOT/'tools/control/risk_search.py').read_text(encoding='utf-8').replace('from tools.control.search_recovery import','from axis_probe_old_base import'))
    legacy_load=module('axis_probe_old_load',(OUT/'before/load_search.py').read_text(encoding='utf-8').replace('from tools.control.risk_search import','from axis_probe_old_risk import'))
    legacy_compliant=module('axis_probe_old_compliant',(ROOT/'tools/control/compliant_search.py').read_text(encoding='utf-8').replace('from tools.control.load_search import','from axis_probe_old_load import'))
    n=0
    for phase in ['INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED']:
        for i in range(600):
            t=i*.002;p=(2e-6*math.sin(i),3e-6*math.cos(i),(i%60)*2e-6)
            w=(.001*math.sin(i),.002*math.cos(i),-.008,1e-5,-1e-5,0.)
            x=CompliantSearchRecovery();y=legacy_compliant.CompliantSearchRecovery()
            x._start_search(PoseObservation(0.,(0.,0.,0.),(0.,)*6,0.));y._start_search(legacy_risk.PoseObservation(0.,(0.,0.,0.),(0.,)*6,0.))
            x.phase=y.phase=phase;x.theta=y.theta=i*.035;x.load_since=y.load_since=None
            ux=x.command(PoseObservation(t,p,w,0.),.002);uy=y.command(legacy_risk.PoseObservation(t,p,w,0.),.002)
            assert np.array_equal(ux,uy) and x.phase==y.phase and x.reason==y.reason
            assert x.events==y.events and np.array_equal(x.admittance.offset,y.admittance.offset)
            n+=1
    result=dict(archived_search_time_s=r['time_s'],old_target_xy_um=(np.array(sample['search_composition']['target_xy_m'])*1e6).tolist(),
        new_target_xy_um=(np.array(c.search_composition['target_xy_m'])*1e6).tolist(),new_raw_xy_mm_s=(u[:2]*1000).tolist(),
        old_return_exit_time_s=a['time_s'],return_advance_from_start_um=(a['position_m'][2]-start['position_m'][2])*1e6,
        return_net_advance_um=(sensed(a).displacement_m[2]-peak)*1e6,old_exits=True,new_exits=False,
        legacy_shared_hook_comparisons=n,legacy_commands_states_exact=True,dynamic_episodes=0,
        scope='Pure controller/archive checks only; not physical efficacy evidence')
    (OUT/'offline_probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
