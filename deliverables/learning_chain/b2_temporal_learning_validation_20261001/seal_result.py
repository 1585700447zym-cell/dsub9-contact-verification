"""Seal terminal evidence plus immutable snapshots of rolling documents."""
import json,os,re,shutil
from pathlib import Path
import validation_contract as C
OUT=C.HERE/'result_analysis';a=C.read(OUT/'assessment.json');pins=C.read(C.HERE/'execution_pins.json')
C.require_authorization(pins['binding_sha256'],pins['authorization_sha256']);binding=C.verify_binding(pins['binding_sha256'])
C.verify_files(a['result_input_sha256'])
if a['status']=='healthy' or any(a['offline_actual_calls'].values()) or a['b2_complete'] or a['automatic_tracking']!='PAUSED':raise ValueError('Terminal clean offline audit required')
review=C.read(OUT/'review_assessment.json')
if not review.get('ready') or review.get('critical') or review.get('important'):raise ValueError('Result interpretation review not closed')
fix=C.HERE.with_name('b2_temporal_checkpoint_write_fix_20261001')/'delivery_verification.json'
fix_record=C.read(fix);C.verify_files(fix_record['sha256'])
if fix_record['tests']!=7 or fix_record['policy_effect_validated'] or fix_record['retry_allowed']:raise ValueError('Offline repair boundary violated')
docs=[C.ROOT/'项目进度跟踪.md',C.ROOT/'项目交付总览.md',C.ROOT/'项目当前入口.md',C.ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
snap=OUT/'document_snapshot';snap.mkdir(exist_ok=False)
for path in docs:
    text=path.read_text(encoding='utf-8')
    if '**100ms预热学习验证已收口（2026-10-01）：**' not in text or 'B.2未完成' not in text:raise ValueError('Rolling document not reconciled: '+path.name)
    shutil.copyfile(path,snap/path.name)
files={p.relative_to(C.ROOT).as_posix():C.digest(p) for p in C.HERE.rglob('*') if p.is_file() and
    not any(part.endswith('_work') for part in p.parts) and '__pycache__' not in p.parts and p.name!='delivery_verification.json'}
record=dict(version='temporal_learning_delivery_verification_v1',actual_status=a['status'],judgement=a['judgement'],
    limited_candidate_target_passed=a['limited_candidate_target_passed'],comparison_complete=a['comparison_complete'],accounting=a['accounting'],
    actual_costs=a['actual_costs'],offline_actual_calls=a['offline_actual_calls'],protocol_tests=a['protocol_tests'],
    bound_source_count=len(binding['input_sha256']),source_binding_sha256=pins['binding_sha256'],authorization_sha256=pins['authorization_sha256'],
    parent_preflight_sha256=C.PREFLIGHT_PIN,sha256=files,rolling_originals_not_frozen=True,automatic_tracking='PAUSED',b2_complete=False,retry_allowed=False,
    separate_offline_repair_sha256=C.digest(fix),separate_offline_repair_file=fix.relative_to(C.ROOT).as_posix(),actual_C500_recoverable=False,learned_policy_dynamic_attempts=0)
with (OUT/'delivery_verification.json').open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,allow_nan=False,indent=2);f.flush();os.fsync(f.fileno())
C.verify_files(files)
print(json.dumps(dict(status=a['status'],judgement=a['judgement'],files=len(files),delivery_sha256=C.digest(OUT/'delivery_verification.json')),ensure_ascii=False))
