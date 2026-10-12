"""Read-only trajectory analysis; no controller calls or physics steps."""
from pathlib import Path
import gzip,json,math
import numpy as np
OUT=Path(__file__).resolve().parent


def read(p):return json.loads(gzip.decompress(p.read_bytes()))


def sample(r):
    return dict(time_s=r['time_s'],phase=r['policy_phase'],search_count=r['search_count'],
        actual_y_um=r['position_m'][1]*1e6,advance_mm=(r['position_m'][2]+.004)*1000,
        integral_y_um=r['commanded_correction'][1]*1e6,admittance_y_mm_s=r['admittance_velocity'][1]*1000,
        command_y_mm_s=r['limited_command_world'][1]*1000,Fy_mN=r['contact_wrench_M'][1]*1000,
        force_mN=math.sqrt(sum(x*x for x in r['contact_wrench_M'][:3]))*1000,
        reference_y_error_um=(r['reference_qpos'][1]-r['position_m'][1])*1e6)


def stats(rows):
    search=[r for r in rows if r['policy_phase']=='SEARCH']
    saturated=[r for r in search if r['commanded_correction'][1]>=.0005-1e-12 and r['contact_wrench_M'][1]>0 and abs(r['admittance_velocity'][1])<1e-12]
    opposed=[r for r in search if r['contact_wrench_M'][1]>0 and r['admittance_velocity'][1]>0 and r['limited_command_world'][1]<0]
    return dict(search_samples=len(search),saturated_y_positive_force_zero_admittance=len(saturated),
        positive_y_admittance_but_negative_limited_command=len(opposed),
        first_saturated=None if not saturated else sample(saturated[0]),
        last_saturated=None if not saturated else sample(saturated[-1]),
        first_opposed=None if not opposed else sample(opposed[0]))


def composition(d):
    rows=d['trace'];c=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'))['b2_config']
    e=next(x for x in d['controller_events'] if x['reason']=='LOW_LOAD_SEARCH' and x['time_s']>8)
    origin=np.array(min(rows,key=lambda r:abs(r['time_s']-e['time_s']))['position_m'])
    examples=[];error=0.;n=0
    for prev,r in zip(rows,rows[1:]):
        if prev['time_s']<e['time_s']+.002 or r['policy_phase']!='SEARCH' or prev['policy_phase']!='SEARCH' or r['time_s']>d['summary']['stop_time']+1e-9:continue
        theta=prev['spiral_theta_rad'];b=c['spiral_pitch_m']/(2*math.pi);radius=b*theta
        rate=c['spiral_speed_m_s']/math.hypot(radius,b)
        tangent=np.array([b*math.cos(theta)-radius*math.sin(theta),b*math.sin(theta)+radius*math.cos(theta)])*rate
        target=radius*np.array([math.cos(theta),math.sin(theta)])
        tracking=c['search_tracking_gain_s']*(target-(np.array(prev['position_m'])-origin)[:2])
        adm=np.array(r['admittance_velocity'][:2])
        raw=np.clip(adm+tangent+tracking,-c['search_xy_component_speed_m_s'],c['search_xy_component_speed_m_s'])
        error=max(error,float(np.max(np.abs(raw-r['raw_command_world'][:2]))));n+=1
        if prev['contact_wrench_M'][1]>.005 and adm[1]>1e-5 and raw[1]<0 and r['commanded_correction'][1]<.000499:
            examples.append(dict(command_time_s=prev['time_s'],trace_time_s=r['time_s'],input_Fy_mN=prev['contact_wrench_M'][1]*1000,
                admittance_y_mm_s=adm[1]*1000,tangent_y_mm_s=tangent[1]*1000,tracking_y_mm_s=tracking[1]*1000,
                raw_y_mm_s=raw[1]*1000,limited_y_mm_s=r['limited_command_world'][1]*1000,
                integral_y_um=r['commanded_correction'][1]*1e6,actual_y_um=r['position_m'][1]*1e6))
    assert error<1e-12
    return dict(reconstructed_commands=n,max_abs_error_m_s=error,unsaturated_opposition_samples=len(examples),
        example=max(examples,key=lambda r:r['input_Fy_mN']) if examples else None,
        scope='Algebra reconstruction of archived raw command from prior sensor sample, recorded applied admittance, known spiral origin/theta; zero physics and controller calls.')


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
    d=read(OUT/'run/y_neg_150.json.gz');assert d['status']=='finished'
    old=read(OUT.parent/'search_load_20261004/run/y_neg_150.json.gz')
    events=[e for e in d['controller_events'] if e['reason']=='XY_ADMITTANCE_REBASED']
    after=events[0]['time_s'] if events else float('inf')
    rows=[r for r in d['trace'] if r['time_s']>after+1e-9]
    stop=d['summary']['stop_time'];before=[r for r in d['trace'] if r['time_s']<stop-1e-9]
    result=dict(events=events,whole_run=stats(d['trace']),after_rebase=stats(rows),
        previous_after_same_time=stats([r for r in old['trace'] if r['time_s']>after+1e-9]),
        first_after_rebase=sample(rows[0]) if rows else None,last_before_stop=sample(before[-1]),
        minimum_y_um=min(r['position_m'][1] for r in rows)*1e6 if rows else None,
        maximum_advance_mm=max((r['position_m'][2]+.004)*1000 for r in d['trace']),
        scope='Archived per-control samples; limited command is post-slew; values alone do not isolate sole causality.')
    (OUT/'diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (OUT/'composition_probe.json').write_text(json.dumps(composition(d),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
