"""Quantify actual search excursion and recovered-search advance from archives."""
from pathlib import Path
import json,gzip,math
import numpy as np
OUT=Path(__file__).resolve().parent


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
    d=json.loads(gzip.decompress((OUT/'run/y_neg_150.json.gz').read_bytes()));rows=d['trace']
    events=d['controller_events'];config=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'))['b2_config']
    starts=[e for e in events if e['reason']=='LOW_LOAD_SEARCH'];phases=[]
    at=lambda t:min(rows,key=lambda r:abs(r['time_s']-t))
    for i,start in enumerate(starts):
        end=next(e for e in events if e['time_s']>start['time_s'] and e['phase']!='SEARCH')
        origin=at(start['time_s']);p0=np.array(origin['position_m'])
        samples=[r for r in rows if start['time_s']<r['time_s']<=end['time_s']+1e-9 and r['search_composition'] is not None]
        actual=max(float(np.linalg.norm(np.array(r['position_m'][:2])-p0[:2])) for r in samples)
        target=max(float(np.linalg.norm(r['search_composition']['target_xy_m'])) for r in samples)
        spiral=max(config['spiral_pitch_m']*r['search_composition']['theta_rad']/(2*math.pi) for r in samples)
        phases.append(dict(search_number=i+1,start_s=start['time_s'],end_s=end['time_s'],end_reason=end['reason'],
            start_z_mm=p0[2]*1000,end_z_mm=at(end['time_s'])['position_m'][2]*1000,
            max_actual_xy_excursion_um=actual*1e6,max_composed_target_um=target*1e6,max_nominal_spiral_um=spiral*1e6,
            max_total_force_mN=max(float(np.linalg.norm(r['contact_wrench_M'][:3])*1000) for r in samples)))
    representative=at(8.)
    comp=representative['search_composition'];theta=comp['theta_rad'];radius=config['spiral_pitch_m']*theta/(2*math.pi)
    spiral=radius*np.array([math.cos(theta),math.sin(theta)])
    advanced=next(e for e in events if e['reason']=='SEARCH_ADVANCED')
    first_deepest=max(r['position_m'][2] for r in rows if r['time_s']<=phases[0]['end_s'])
    advance=at(advanced['time_s'])
    result=dict(searches=phases,environment_events=d['events'],
        cancellation_example=dict(trace_time_s=representative['time_s'],nominal_spiral_xy_um=(spiral*1e6).tolist(),
            admittance_correction_xy_um=(np.array(comp['correction_xy_m'])*1e6).tolist(),
            composed_target_xy_um=(np.array(comp['target_xy_m'])*1e6).tolist(),
            actual_position_xy_um=(np.array(representative['position_m'][:2])*1e6).tolist()),
        recovered_advance=dict(time_s=advanced['time_s'],second_search_start_z_mm=phases[1]['start_z_mm'],
            advance_z_mm=advance['position_m'][2]*1000,advance_from_second_start_um=(advance['position_m'][2]-phases[1]['start_z_mm']/1000)*1e6,
            deepest_before_recovery_z_mm=first_deepest*1000,still_before_prior_depth_um=(first_deepest-advance['position_m'][2])*1e6),
        final_y_um=rows[-1]['position_m'][1]*1e6,final_advance_mm=(rows[-1]['position_m'][2]+.004)*1000,
        scope='Archived kinematics and command decomposition; no extra physics. Does not uniquely isolate contact friction from all other causes.')
    (OUT/'diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
