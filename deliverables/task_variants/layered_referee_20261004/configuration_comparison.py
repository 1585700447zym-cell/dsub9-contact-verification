from pathlib import Path
import json,hashlib
OUT=Path(__file__).resolve().parent
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
a=read(OUT.parent/'deadline25_20261004/configuration.json');b=read(OUT/'configuration.json')
def diff(a,b,p=''):
    if isinstance(a,dict) and isinstance(b,dict):
        result=[]
        for k in sorted(a.keys()|b.keys()):
            if k not in a or k not in b:result.append(p+k)
            else:result+=diff(a[k],b[k],p+k+'.')
        return result
    return [] if a==b else [p.rstrip('.')]
changed=diff(a,b)
allowed=['task_id','parent_task_id','common_task_change','geometry_referee','success_mode','input_sha256','runtime_proof']
unexpected=[p for p in changed if not any(p==x or p.startswith(x+'.') for x in allowed)]
record=dict(changed_paths=changed,unexpected_paths=unexpected,
            old_total_s=a['b2_config']['total_action_time_s'],new_total_s=b['b2_config']['total_action_time_s'],
            model_equal=a['model_sha256']==b['model_sha256'],
            controller_id_equal=a['controller_id']==b['controller_id'],
            rule='Version/ledger/source-binding metadata differences permitted; only referee version changes; controller and all physics parameters identical')
(OUT/'configuration_comparison.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
assert not unexpected,unexpected
assert record['model_equal'] and record['controller_id_equal']
print(json.dumps(record,ensure_ascii=False))
