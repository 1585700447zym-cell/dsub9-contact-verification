"""Seal offline repair files while verifying the original failed evidence."""
import hashlib,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OLD=HERE.with_name('b2_temporal_learning_validation_20261001');sys.path.insert(0,str(OLD))
import validation_contract as C
p=C.read(OLD/'execution_pins.json');C.require_authorization(p['binding_sha256'],p['authorization_sha256']);C.verify_binding(p['binding_sha256'])
a=C.read(OLD/'result_analysis/assessment.json');C.verify_files(a['result_input_sha256'])
f=C.read(HERE/'assessment.json');g=C.read(HERE/'writer_final_green.json')
if g['tests']!=7 or g['failures'] or g['errors'] or any(g['actual_calls'].values()) or f['policy_effect_validated'] or f['retry_allowed']:raise ValueError('Unclean or misclassified repair')
if f['original_runtime_sha256']!=C.digest(OLD/'learning_runtime.py') or f['parent_assessment_sha256']!=C.digest(OLD/'result_analysis/assessment.json'):raise ValueError('Changed parent')
files={x.relative_to(ROOT).as_posix():C.digest(x) for x in HERE.rglob('*') if x.is_file() and '__pycache__' not in x.parts and not any(s.endswith('_work') for s in x.parts) and x.name!='delivery_verification.json'}
v=dict(version='checkpoint_write_fix_delivery_v1',sha256=files,original_binding_sha256=p['binding_sha256'],actual_calls=g['actual_calls'],tests=7,policy_effect_validated=False,retry_allowed=False,b2_complete=False)
with (HERE/'delivery_verification.json').open('x',encoding='utf-8') as out:json.dump(v,out,ensure_ascii=False,indent=2);out.flush();os.fsync(out.fileno())
C.verify_files(files);print(json.dumps(dict(files=len(files),delivery_sha256=C.digest(HERE/'delivery_verification.json')),ensure_ascii=False))
