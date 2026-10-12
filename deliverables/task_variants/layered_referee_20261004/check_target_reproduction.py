from pathlib import Path
import json,gzip,hashlib
OUT=Path(__file__).resolve().parent
p=OUT/'run/y_neg_150.json.gz';oldp=OUT.parent/'deadline25_20261004/run/y_neg_150.json.gz'
a=json.loads(gzip.decompress(oldp.read_bytes()));b=json.loads(gzip.decompress(p.read_bytes()))
fields=['position_m','quaternion_wxyz','velocity_world','contact_wrench_M','limited_command_world','reference_qpos']
equal={k:all(x[k]==y[k] for x,y in zip(a['trace'],b['trace'])) for k in fields}
assert len(a['trace'])==len(b['trace'])==11271 and all(equal.values())
assert a['summary']['outcome']['task_outcome']=='TASK_FAILURE' and b['summary']['outcome']['task_outcome']=='FULL_SUCCESS'
result=dict(samples=11271,fields_equal=equal,old_outcome='TASK_FAILURE',new_outcome='FULL_SUCCESS',
    old_task_end_time=a['summary']['task_end_time'],new_task_end_time=b['summary']['task_end_time'],
    old_sha256=hashlib.sha256(oldp.read_bytes()).hexdigest(),new_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
    meaning='Actual run with new referee; all compared physical states and commands identical to the archived old-referee run',new_physics=0)
(OUT/'target_reproduction.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
