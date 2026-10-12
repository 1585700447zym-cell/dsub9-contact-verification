"""Independent algebra checks of archived commands and reference bounds."""
from pathlib import Path
import json,gzip,math
import numpy as np
OUT=Path(__file__).resolve().parent


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
    ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf-8'))
    c=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'))['b2_config']
    results={}
    for entry in ledger['episodes']:
        d=json.loads(gzip.decompress((OUT/'run'/f"{entry['id']}.json.gz").read_bytes()))
        assert d['status']=='finished'
        rows=d['trace'];starts=[e for e in d['controller_events'] if e['reason']=='LOW_LOAD_SEARCH']
        error=0.;target_max=0.;offset_error=0.;n=0;opposed=[]
        for prev,r in zip(rows,rows[1:]):
            composition=r['search_composition']
            if r['phase']!='RUNNING':assert composition is None
            if composition is None:continue
            t=composition['time_s'];assert abs(t-prev['time_s'])<1e-9
            start=max((e for e in starts if e['time_s']<=t+1e-9),key=lambda e:e['time_s'])
            origin=min(rows,key=lambda x:abs(x['time_s']-start['time_s']))
            correction=np.array(prev['commanded_correction'][:2])-np.array(start['admittance_origin_xy_m'])
            offset_error=max(offset_error,float(np.max(np.abs(correction-composition['correction_xy_m']))))
            b=c['spiral_pitch_m']/(2*math.pi);theta=composition['theta_rad'];radius=b*theta
            spiral=radius*np.array([math.cos(theta),math.sin(theta)])
            rate=c['spiral_speed_m_s']/math.hypot(radius,b)
            tangent=np.array([b*math.cos(theta)-radius*math.sin(theta),b*math.sin(theta)+radius*math.cos(theta)])*rate
            target=spiral+correction;ff=tangent+np.array(r['admittance_velocity'][:2]);norm=np.linalg.norm(target);R=c['spiral_radius_m']
            if norm>R:
                direction=target/norm;target=direction*R;ff=R/norm*(ff-direction*np.dot(direction,ff))
            elif norm==R:
                direction=target/norm;ff-=direction*max(0.,np.dot(direction,ff))
            delta=np.array(prev['position_m'][:2])-np.array(origin['position_m'][:2])
            command=np.clip(ff+c['search_tracking_gain_s']*(target-delta),-c['search_xy_component_speed_m_s'],c['search_xy_component_speed_m_s'])
            error=max(error,float(np.max(np.abs(command-r['raw_command_world'][:2]))))
            assert np.max(np.abs(target-composition['target_xy_m']))<1e-12
            target_max=max(target_max,float(np.linalg.norm(target)));n+=1
            if prev['contact_wrench_M'][1]>.005 and r['admittance_velocity'][1]>1e-5 and command[1]<0:
                opposed.append(dict(time_s=t,Fy_mN=prev['contact_wrench_M'][1]*1000,admittance_y_mm_s=r['admittance_velocity'][1]*1000,command_y_mm_s=command[1]*1000))
        assert error<1e-12 and offset_error<1e-12 and target_max<=c['spiral_radius_m']+1e-12
        results[entry['id']]=dict(reconstructed_commands=n,max_command_error_m_s=error,max_offset_origin_error_m=offset_error,
            max_target_radius_um=target_max*1e6,strong_positive_y_admittance_but_negative_command=len(opposed),
            example_opposed=None if not opposed else max(opposed,key=lambda x:x['Fy_mN']),
            stop_tail_composition_is_null=True,scope='Saved-cycle algebra only; no physics or controller calls')
    (OUT/'composition_audit.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False))


if __name__=='__main__':main()
