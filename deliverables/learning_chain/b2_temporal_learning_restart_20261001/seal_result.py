"""Terminal original-input preservation, evidence and immutable document snapshots."""
import json,os,shutil
import validation_contract as C
OUT=C.HERE/'result_analysis';pins=C.read(C.HERE/'execution_pins.json');a=C.read(OUT/'assessment.json')
C.require_authorization(pins['binding_sha256'],pins['authorization_sha256']);binding=C.verify_binding(pins['binding_sha256']);C.verify_files(a['result_input_sha256'])
if a['status']=='healthy' or any(a['offline_actual_calls'].values()) or a['b2_complete'] or a['automatic_tracking']!='PAUSED':raise ValueError('Clean terminal audit required')
review=C.read(OUT/'review_assessment.json')
if not review['ready'] or review['critical'] or review['important']:raise ValueError('Terminal interpretation review not closed')
docs=[C.ROOT/'项目进度跟踪.md',C.ROOT/'项目交付总览.md',C.ROOT/'项目当前入口.md',C.ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
snap=OUT/'document_snapshot';snap.mkdir(exist_ok=False)
for p in docs:
    t=p.read_text(encoding='utf-8')
    if '**100ms预热重启验证已收口（2026-10-01）：**' not in t or 'B.2未完成' not in t:raise ValueError('Rolling document not reconciled')
    shutil.copyfile(p,snap/p.name)
files={p.relative_to(C.ROOT).as_posix():C.digest(p) for p in C.HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and not any(s.endswith('_work') for s in p.parts) and p.name!='delivery_verification.json'}
record=dict(version='temporal_restart_delivery_v1',actual_status=a['status'],judgement=a['judgement'],
    limited_candidate_target_passed=a['limited_candidate_target_passed'],comparison_complete=a['comparison_complete'],
    accounting=a['accounting'],actual_costs=a['actual_costs'],offline_actual_calls=a['offline_actual_calls'],
    zero_checkpoint_gate=a['zero_checkpoint_gate'],failed_attempts=a['failed_attempts'],protocol_tests=a['protocol_tests'],
    source_binding_sha256=pins['binding_sha256'],authorization_sha256=pins['authorization_sha256'],bound_input_count=len(binding['input_sha256']),
    failed_parent_sha256=C.FAILED_SEAL_PIN,writer_fix_sha256=C.FIX_SEAL_PIN,sha256=files,b2_complete=False,retry_allowed=False,
    automatic_tracking='PAUSED',rolling_originals_not_frozen=True)
with (OUT/'delivery_verification.json').open('x',encoding='utf-8') as f:json.dump(record,f,ensure_ascii=False,allow_nan=False,indent=2);f.flush();os.fsync(f.fileno())
C.verify_files(files);print(json.dumps(dict(status=a['status'],judgement=a['judgement'],files=len(files),delivery_sha256=C.digest(OUT/'delivery_verification.json')),ensure_ascii=False))
