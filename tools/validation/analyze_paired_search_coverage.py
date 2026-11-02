"""Read saved observations to locate the two search disks and existing relief gates."""
import gzip
import json
import math
from pathlib import Path
import sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.learning.five_axis_contract import field_slices
from tools.validation.run_yaw_pilot import read,write,sha,NoLearning
BATCH=ROOT/'deliverables/learning_chain/five_axis_entropy_closed_loop_20261026'
OUT=ROOT/'deliverables/learning_chain/five_axis_entropy_postmortem_20261027'


def main():
    sys.meta_path.insert(0,NoLearning())
    results={};fields=field_slices()
    for arm in ('A0','A2'):
        for folder in sorted((BATCH/'run'/arm).glob('*development*')):
            receipt=read(folder/'receipt.json');path=folder/'episode.json.gz'
            if sha(path)!=receipt['archive_sha256']:raise ValueError('Archive changed')
            raw=json.loads(gzip.decompress(path.read_bytes()));tr=raw['trace'];rows=raw['transitions']
            scales={s['name']:np.array(s['scale']) for s in raw['observation_schema']}
            initial=np.array(tr[0]['position_m']);segments=[];i=0
            while i<len(rows):
                row=rows[i]
                if not row['action_active'] or row['action_log']['composition_inputs']['phase']!='SEARCH':i+=1;continue
                start=i;origin=np.array(row['observation'])[fields['search_origin_m']]*scales['search_origin_m']+initial
                while i<len(rows) and rows[i]['action_active'] and rows[i]['action_log']['composition_inputs']['phase']=='SEARCH':i+=1
                selected=tr[start:i+1];pos=np.array([r['position_m'][:2] for r in selected]);ref=np.array([r['reference_qpos'][:2] for r in selected])
                wrench=np.array([r['contact_wrench_M'] for r in tr[start:i]])
                loaded=(np.linalg.norm(wrench[:,:2],axis=1)>=2.) & (np.linalg.norm(wrench[:,:3],axis=1)>=4.4)
                run=longest=0
                for value in loaded:
                    run=run+1 if value else 0;longest=max(run,longest)
                segments.append(dict(start_s=tr[start]['time_s'],end_s=tr[i]['time_s'],
                    global_origin_xy_mm=(origin[:2]*1000).tolist(),origin_distance_mm=float(np.linalg.norm(origin[:2])*1000),
                    search_radius_mm=.4,disk_nearest_global_origin_mm=max(0.,float(np.linalg.norm(origin[:2])*1000-.4)),
                    actual_path_minimum_radial_mm=float(np.linalg.norm(pos,axis=1).min()*1000),
                    reference_path_minimum_radial_mm=float(np.linalg.norm(ref,axis=1).min()*1000),
                    both_load_thresholds_met_fraction=float(loaded.mean()),
                    longest_sampled_loaded_span_s=max(0,longest-1)*.002,
                    relief_rule='lateral>=2N and total>=4.4N continuously20ms; other priority gates retained'))
            key=arm+'_'+raw['case']['name'];yaw=[r.get('yaw_admittance',{}) for r in tr]
            results[key]=dict(search_segments=segments,
                yaw_admittance_limited_steps=yaw[-1].get('limited_steps'),
                maximum_abs_yaw_admittance_offset_rad=max(abs(s.get('offset_rad',0.)) for s in yaw),
                archive_sha256=receipt['archive_sha256'])
            print(key,json.dumps(results[key],ensure_ascii=False),flush=True)
    write(OUT/'search_coverage_diagnosis.json',dict(results=results,new_initializations=0,new_physical_substeps=0,
        new_neural_inference=0,new_optimizer_updates=0,
        limitation='Disk distances refer to connector/reference origin, not pinwise clearance; exact pin geometry is separate'))
    (OUT/'analysis_source_snapshot'/Path(__file__).name).write_bytes(Path(__file__).read_bytes())


if __name__=='__main__':main()
