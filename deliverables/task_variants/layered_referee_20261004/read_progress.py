from pathlib import Path
import json,gzip,math
OUT=Path(__file__).resolve().parent
ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf-8'))
summary=dict(status=ledger['status'],finished=[dict(id=e['id'],outcome=e['outcome']['task_outcome'],reason=e['reason']) for e in ledger['episodes'] if e['status']=='finished'])
pending=next((e for e in ledger['episodes'] if e['status']=='running'),None)
if pending:
    p=OUT/'run'/f"{pending['id']}.json.gz"
    if p.exists():
        d=json.loads(gzip.decompress(p.read_bytes()));r=d['trace'][-1]
        summary['checkpoint']=dict(id=pending['id'],time_s=r['time_s'],phase=r['phase'],policy_phase=r['policy_phase'],
            xy_um=math.hypot(*r['position_m'][:2])*1e6,z_um=r['position_m'][2]*1e6,events=d['controller_events'][-3:])
print(json.dumps(summary,ensure_ascii=False))
