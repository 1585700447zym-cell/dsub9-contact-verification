"""Describe actual final insertion, without treating extrapolation as a rerun."""
from pathlib import Path
import sys,json,gzip
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.model.clearance_task import pin_clearance_m
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
d=json.loads(gzip.decompress((OUT/'run/y_neg_150.json.gz').read_bytes()));rows=d['trace'];entry=d['summary']
start=next(e for e in d['controller_events'] if e['reason']=='SEARCH_ADVANCED');stop=entry['stop_time']
at=lambda t:min(rows,key=lambda r:abs(r['time_s']-t));a=at(start['time_s']);b=at(stop)
segment=[r for r in rows if start['time_s']<r['time_s']<stop-1e-9]
elapsed=stop-start['time_s'];advance=b['position_m'][2]-a['position_m'][2];rate=advance/elapsed
result=dict(search_advanced_time_s=start['time_s'],search_advanced_z_mm=a['position_m'][2]*1000,
    insertion_time_available_s=elapsed,insertion_advance_mm=advance*1000,average_actual_z_speed_mm_s=rate*1000,
    pre_stop_z_mm=segment[-1]['position_m'][2]*1000,pre_stop_z_speed_mm_s=segment[-1]['velocity_world'][2]*1000,
    max_insertion_force_mN=max(float(np.linalg.norm(r['contact_wrench_M'][:3])*1000) for r in segment),
    minimum_insertion_step_advance_um=min((y['position_m'][2]-x['position_m'][2])*1e6 for x,y in zip(segment,segment[1:])),
    remaining_to_zero_mm=-b['position_m'][2]*1000,estimated_seconds_to_zero_at_recent_rate=-b['position_m'][2]/rate,
    final_pin_clearance_um=pin_clearance_m(rows[-1])*1e6,
    proposed_next_total_action_time_s=25.,scope='Time-budget candidate only. Extrapolation does not verify full geometry, success hold or safe continuation. Old 20s failure remains unchanged.')
(OUT/'deadline_analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
