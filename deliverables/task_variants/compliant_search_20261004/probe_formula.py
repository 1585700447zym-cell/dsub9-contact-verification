"""Compare formulas at archived states, never replay the physics."""
from pathlib import Path
import json,gzip,math,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
    old=OUT.parent/'admittance_rebase_20261004'
    d=json.loads(gzip.decompress((old/'run/y_neg_150.json.gz').read_bytes()));rows=d['trace']
    c=json.loads((old/'configuration.json').read_text(encoding='utf-8'))['b2_config']
    from tools.control.compliant_search import bounded_target
    e=next(x for x in d['controller_events'] if x['reason']=='LOW_LOAD_SEARCH' and x['time_s']>8)
    start=min(rows,key=lambda r:abs(r['time_s']-e['time_s']))
    origin=np.array(start['position_m']);offset0=np.array(start['commanded_correction'][:2]);examples=[]
    for prev,r in zip(rows,rows[1:]):
        if prev['time_s']<e['time_s']+.002 or r['policy_phase']!='SEARCH' or prev['policy_phase']!='SEARCH' or r['time_s']>d['summary']['stop_time']+1e-9:continue
        theta=prev['spiral_theta_rad'];b=c['spiral_pitch_m']/(2*math.pi);radius=b*theta
        rate=c['spiral_speed_m_s']/math.hypot(radius,b)
        tangent=np.array([b*math.cos(theta)-radius*math.sin(theta),b*math.sin(theta)+radius*math.cos(theta)])*rate
        spiral=radius*np.array([math.cos(theta),math.sin(theta)])
        adm=np.array(r['admittance_velocity'][:2]);delta=(np.array(prev['position_m'])-origin)[:2]
        old_raw=np.clip(adm+tangent+c['search_tracking_gain_s']*(spiral-delta),-.0003,.0003)
        if prev['contact_wrench_M'][1]>.005 and adm[1]>1e-5 and old_raw[1]<0 and r['commanded_correction'][1]<.000499:
            target=spiral+np.array(prev['commanded_correction'][:2])-offset0
            checked_target,checked_ff=bounded_target(target,adm+tangent,c['spiral_radius_m'])
            ff=adm+tangent;norm=np.linalg.norm(target);R=c['spiral_radius_m']
            if norm>R:
                n=target/norm;target=n*R;ff=R/norm*(ff-n*np.dot(n,ff))
            elif norm==R:
                n=target/norm;ff=ff-n*max(0.,np.dot(n,ff))
            assert np.array_equal(target,checked_target) and np.array_equal(ff,checked_ff)
            new=np.clip(ff+c['search_tracking_gain_s']*(target-delta),-.0003,.0003)
            examples.append(dict(time_s=prev['time_s'],old_y_mm_s=float(old_raw[1]*1000),new_y_mm_s=float(new[1]*1000),target_norm_um=float(np.linalg.norm(target)*1e6)))
    report=dict(scope='Frozen archived states, algebra only, no controller/physics/training calls; does not predict actual success',counterexamples=len(examples),
        new_positive_y=sum(e['new_y_mm_s']>0 for e in examples),new_negative_y=sum(e['new_y_mm_s']<0 for e in examples),
        max_target_radius_um=max(e['target_norm_um'] for e in examples),representative=examples[-1],
        remaining_negative=[e for e in examples if e['new_y_mm_s']<0],implemented_projection_exact=True)
    (OUT/'offline_formula_probe.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
