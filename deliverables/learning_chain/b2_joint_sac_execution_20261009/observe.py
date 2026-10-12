"""Read compact live status; does not import runtime or alter the experiment."""
from pathlib import Path
import datetime
import json
OUT=Path(__file__).resolve().parent
def read(path):return json.loads(path.read_text(encoding='utf-8'))
run=OUT/'execution';counter=read(run/'counter.json');ledger=read(run/'run/ledger.json') if (run/'run/ledger.json').exists() else {}
rows=ledger.get('episodes',[])
journal=run/'run/chain/update_journal.jsonl'
updates=[]
if journal.exists():
    for line in journal.read_text(encoding='utf-8').splitlines():
        try:
            e=json.loads(line)
            if e.get('event')=='complete':updates.append(e)
        except json.JSONDecodeError:pass # A currently-writing final line is not a completed update.
summary=dict(now=datetime.datetime.now().astimezone().isoformat(),status=counter['status'],ledger_status=ledger.get('status'),
    elapsed_s=round(datetime.datetime.now().timestamp()-counter['started'],1),zero_restore=ledger.get('zero_state_restore_verified',False),
    registered_rows=len(rows),physical_attempts=counter['attempted']['dynamic_episodes'],completed=sum(r.get('status')=='finished' and r.get('healthy') is True for r in rows),
    formal_updates_completed=len(updates),latest=rows[-1] if rows else None,
    episodes=[dict(id=r['id'],status=r['status'],healthy=r.get('healthy'),outcome=r.get('outcome',{}).get('task_outcome'),cycles=r.get('control_cycles')) for r in rows],
    reserved_upper_bounds=counter['attempted'])
if (run/'authorization_closure.json').exists():summary['closure']=read(run/'authorization_closure.json')
print(json.dumps(summary,ensure_ascii=False))
