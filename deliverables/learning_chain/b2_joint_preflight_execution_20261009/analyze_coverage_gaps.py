"""Read failed timing coverage from existing closed archives; zero new physics."""
from pathlib import Path
import gzip
import json
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(OUT.parent/'b2_joint_admission_preflight_20261009'))
from scope_contract import read,sha,schedule_position
from execution_contract import write

def spans(indices,rows):
    runs=[]
    for i in indices:
        if runs and runs[-1][1]+1==i:runs[-1][1]=i
        else:runs.append([i,i])
    return [dict(first_cycle=a,last_cycle=b,start_s=rows[a]['before']['time_s'],end_s=rows[b]['after']['time_s']) for a,b in runs]

def main():
    summary=read(OUT/'execution_summary.json');results=[]
    for entry in summary['rows']:
        a=entry.get('assessment',{});cov=a.get('joint_coverage',{})
        missing=[int(h) for h,n in cov.get('hold_contact_effect_cycles',{}).items() if n==0]
        if not missing:continue
        path=OUT/'run'/entry['raw_source'];raw=json.loads(gzip.decompress(path.read_bytes()));rows=raw['cycles'];profile=raw['spec']['profile']
        contact=[i for i,c in enumerate(rows) if c['result']['trace_row']['contact_count']>0]
        record=dict(id=entry['id'],archive_sha256=sha(path),control_cycles=len(rows),contact_cycles=len(contact),
            task_end_time_s=raw['task_end_time_s'],contact_intervals=spans(contact,rows),missing=[])
        for hold in missing:
            indices=[i for i in range(len(rows)) if schedule_position(profile,i)[1]==hold]
            contacts=[i for i in indices if rows[i]['result']['trace_row']['contact_count']>0]
            permitted=[i for i in contacts if rows[i]['before']['residual_enabled']]
            effective=[i for i in permitted if any(abs(x)>1e-15 for x in rows[i]['result']['action_log']['effective_command_delta'])]
            if effective:raise AssertionError('Published gap contradicts raw archive')
            cause='NO_CONTACT_IN_FIXED_BLOCK' if not contacts else 'CONTACT_MASKED_IN_FIXED_BLOCK' if not permitted else 'NO_EFFECT_WITH_PERMISSION_IN_FIXED_BLOCK'
            record['missing'].append(dict(hold_cycles=hold,block_cycles=len(indices),permitted_block_cycles=sum(rows[i]['before']['residual_enabled'] for i in indices),
                contact_block_cycles=len(contacts),permitted_contact_cycles=len(permitted),effective_contact_cycles=0,
                first_blocks=spans(indices,rows)[:4],evidence_classification=cause))
        results.append(record);del raw
    write(OUT/'coverage_gap_evidence.json',dict(stage_id='B2-SCOPE-10',read_only=True,new_physics=0,episodes=results,
        limitation='Observed temporal overlap classification only; no schedule revision, new run, learning effect, or counterfactual success inference'))
    print(json.dumps(dict(episodes=len(results),gaps=[{'id':r['id'],'missing':r['missing']} for r in results]),ensure_ascii=False))
if __name__=='__main__':main()
