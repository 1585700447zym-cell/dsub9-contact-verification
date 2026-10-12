"""Offline saved-state diagnosis; zero physics and zero network calls."""
from pathlib import Path
import gzip,json,sys
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
from tools.control.fixed_admittance import FixedAdmittance

if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
d=json.loads(gzip.decompress((OUT/'run/y_neg_150.json.gz').read_bytes()))
search=[r for r in d['trace'] if r['policy_phase']=='SEARCH' and r['phase']=='RUNNING']
sat=[r for r in search if r['commanded_correction'][1]>=.0005-1e-12 and r['contact_wrench_M'][1]>0 and abs(r['admittance_velocity'][1])<1e-12]
conflict=[r for r in sat if r['limited_command_world'][1]<0]
last=max((r for r in search if r['time_s']<d['summary']['stop_time']-1e-10),key=lambda r:r['time_s'])
a=FixedAdmittance();a.velocity=np.array(last['admittance_velocity']);a.offset=np.array(last['commanded_correction'])
b=FixedAdmittance();b.velocity=a.velocity.copy();b.offset=a.offset.copy();b.offset[1]=0.
out_a=a.command(last['contact_wrench_M'],.002);out_b=b.command(last['contact_wrench_M'],.002)

def sample(r):
    return dict(time_s=r['time_s'],search_count=r['search_count'],y_um=r['position_m'][1]*1e6,
        actual_y_displacement_um=(r['position_m'][1]-d['trace'][0]['position_m'][1])*1e6,
        admittance_y_offset_um=r['commanded_correction'][1]*1e6,admittance_y_velocity_m_s=r['admittance_velocity'][1],
        contact_Fy_mN=r['contact_wrench_M'][1]*1000,total_command_y_m_s=r['limited_command_world'][1],
        reference_y_error_um=(r['reference_qpos'][1]-r['position_m'][1])*1e6)

result=dict(search_control_samples=len(search),positive_y_budget_saturated_with_positive_force=len(sat),
    saturated_but_total_y_command_negative=len(conflict),first=sample(sat[0]),last_before_stop=sample(last),
    same_state_force_formula_probe=dict(recorded_integral_output_y_m_s=float(out_a[1]),hypothetical_zeroed_y_offset_output_m_s=float(out_b[1]),
        scope='one offline controller formula call per cloned state; no physics; not a validated reset fix'),
    stop=dict(reason=d['summary']['reason'],time_s=d['summary']['stop_time'],search_count=last['search_count']),
    conclusion='Drive reference release worked, but force-admittance accumulated Y correction remained capped; spiral/tracking continued opposite positive unloading force. This identifies a specific contributor, not sole causality or an approved wider budget.')
(OUT/'failure_diagnosis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
