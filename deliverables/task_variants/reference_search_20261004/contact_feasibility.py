"""Geometric closest approach and load statistics from all archived search phases."""
from pathlib import Path
import gzip,json,sys
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.model.clearance_task import pin_clearance_m
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf-8'));results={}
for entry in ledger['episodes']:
    d=json.loads(gzip.decompress((OUT/'run'/f"{entry['id']}.json.gz").read_bytes()));rows=d['trace']
    starts=[e for e in d['controller_events'] if e['reason']=='LOW_LOAD_SEARCH'];phases=[]
    for i,start in enumerate(starts):
        next_end=next((e['time_s'] for e in d['controller_events'] if e['time_s']>start['time_s'] and e['phase']!='SEARCH'),entry['stop_time'])
        samples=[r for r in rows if r['search_composition'] is not None and start['time_s']-1e-9<=r['search_composition']['time_s']<next_end-1e-9]
        if not samples:continue
        closest=min(samples,key=lambda r:np.linalg.norm(r['position_m'][:2]));best=max(samples,key=pin_clearance_m)
        state=lambda r:dict(time_s=r['time_s'],position_um=(np.array(r['position_m'])*1e6).tolist(),xy_um=float(np.linalg.norm(r['position_m'][:2])*1e6),
            pin_clearance_um=pin_clearance_m(r)*1e6,wrench_M=r['contact_wrench_M'],
            reference_xy_um=(np.array(r['reference_qpos'][:2])*1e6).tolist(),
            actual_reference_lead_um=float(np.linalg.norm(np.array(r['reference_qpos'][:2])-r['position_m'][:2])*1e6))
        loaded=[r for r in samples if r['contact_wrench_M'][2]<-.003]
        phases.append(dict(search_number=i+1,cycles=len(samples),closest_xy=state(closest),best_pin_clearance=state(best),
            loaded_cycles=len(loaded),median_compressive_axial_mN=None if not loaded else float(np.median([-r['contact_wrench_M'][2]*1000 for r in loaded])),
            median_lateral_mN=None if not loaded else float(np.median([np.linalg.norm(r['contact_wrench_M'][:2])*1000 for r in loaded])),
            median_reference_actual_lead_um=None if not loaded else float(np.median([np.linalg.norm(np.array(r['reference_qpos'][:2])-r['position_m'][:2])*1e6 for r in loaded]))))
    results[entry['id']]=dict(searches=phases,deepest_advance_mm=max((r['position_m'][2]-rows[0]['position_m'][2])*1000 for r in rows),
        scope='All saved search cycles; geometric truth is offline referee only. Load statistics do not isolate friction causality.')
(OUT/'contact_feasibility.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(results,ensure_ascii=False))
