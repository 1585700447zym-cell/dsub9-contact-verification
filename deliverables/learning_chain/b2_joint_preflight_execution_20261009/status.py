"""Read only small ledger/receipt files and gzip headers; no archive replay."""
from pathlib import Path
import datetime
import gzip
import json
import re
OUT=Path(__file__).resolve().parent
def main():
    p=OUT/'run/ledger.json'
    if not p.exists():print(json.dumps({'status':'NO_LEDGER'}));return
    l=json.loads(p.read_text(encoding='utf-8'));entries=[]
    for e in l['attempts']:
        row={k:e.get(k) for k in ('id','status','audit_passed','outcome','error')}
        row['wall_seconds']=e.get('ended_at',datetime.datetime.now().timestamp())-e['started_at']
        if e['status']=='running':
            files=[OUT/'run'/(e['id']+suffix) for suffix in ('.json.gz','.error.json.gz','.partial.json.gz')]
            source=next((f for f in files if f.exists()),None)
            if source:
                with gzip.open(source,'rt',encoding='utf-8') as stream:head=stream.read(32768)
                m=re.search(r'"control_cycles":(\d+)',head)
                row.update(archive=source.name,checkpoint_cycles=int(m.group(1)) if m else None,
                    archive_updated=datetime.datetime.fromtimestamp(source.stat().st_mtime).isoformat())
        entries.append(row)
    finished=[dict(id=e['id'],status=e['status'],audit=e['audit_passed'],outcome=(e['outcome'] or {}).get('task_outcome'),error=e['error']) for e in entries if e['status']!='running']
    print(json.dumps(dict(status=l['status'],reserved=l['dynamic_attempts'],finished=finished,
        active=[e for e in entries if e['status']=='running']),ensure_ascii=False))
if __name__=='__main__':main()
