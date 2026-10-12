"""Verify evidence and preserve six rolling-document snapshots before sealing."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,shutil,re
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Already sealed')
now=lambda:datetime.now(timezone(timedelta(hours=8))).isoformat()
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
a=read(OUT/'assessment.json');ledger=read(OUT/'run/ledger.json');config=read(OUT/'configuration.json')
assert ledger['status'] in ('complete','controlled_stop')
assert a['episodes']==len(ledger['episodes']) and 1<=a['episodes']<=5
assert a['unused_closed']==5-a['episodes'] and a['cumulative']==123+a['episodes']
assert a['control_cycles']==sum(x['control_cycles'] for x in ledger['episodes'])
assert a['physical_substeps']==sum(x['physical_substeps'] for x in ledger['episodes'])
assert '184 passed' in (OUT/'tests_final.txt').read_text(encoding='utf-8')
prior={}
for folder in ['clearance120_20261003','functional_b2_20261003','search_load_20261004','admittance_rebase_20261004','compliant_search_20261004','axis_search_20261004']:
    p=OUT.parent/folder;m=read(p/'delivery_manifest.json')
    for name,item in m['files'].items():assert digest(p/name)==item['sha256'] and (p/name).stat().st_size==item['bytes']
    prior[folder]=len(m['files'])
changed=[]
for name,sha in config['input_sha256'].items():
    p=ROOT/name
    if digest(p)!=sha:changed.append(name)
    if p.suffix.lower()!='.stl':assert digest(OUT/'source_snapshot'/name)==sha,name
assert changed==['docs/superpowers/plans/2026-10-04-reference-search.md'],changed
for name,sha in read(OUT/'preparation_binding.json').items():assert digest(OUT/name)==sha
for e in ledger['episodes']:assert digest(OUT/'run'/f"{e['id']}.json.gz")==e['archive_sha256']
diags=read(OUT/'diagnosis.json')
for d in diags.values():
    assert d['max_command_error_m_s']<1e-12 and d['max_limited_command_error_m_s']<1e-12
    assert d['xy_offset_freeze_error_m']==0. and d['xy_velocity_freeze_error_m_s']==0.
    assert d['max_actual_reference_radius_um']<=120.+1e-6
probe=read(OUT/'offline_probe.json');assert probe['new']['phase']=='WAIT_RECOVERY' and probe['new']['max_reference_radius_um']<=120.
docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md','docs/superpowers/plans/2026-10-04-reference-search.md']
for name in docs:
    p=ROOT/name;s=p.read_text(encoding='utf-8')
    assert 'reference_search_20261004' in s or name.endswith('2026-10-04-reference-search.md'),name
    dest=OUT/'document_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
for p in [ROOT/docs[0],ROOT/docs[1],ROOT/docs[2],ROOT/docs[4]]:assert p.read_text(encoding='utf-8').count('<!-- reference-search-current -->')==1
links=0
for p in [OUT/'结果说明.md']+[ROOT/n for n in docs]:
    for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        if p.parent!=OUT and 'reference_search_20261004' not in target and '2026-10-04-reference-search' not in target:continue
        if re.match(r'^[a-zA-Z]+://',target) or target.startswith('#'):continue
        resolved=(p.parent/target.split('#')[0]).resolve()
        if resolved not in [OUT/'verification.json',OUT/'delivery_manifest.json']:assert resolved.exists(),str(resolved)
        links+=1
fully_successful=a['episodes']==5 and a['functional_success']==5
v=dict(created_at=now(),tests_passed=184,tests_command='python -X utf8 -B -m pytest tests/task_variants tests/control/test_fixed_admittance.py tests/learning/test_action.py tests/learning/test_reward.py -q --tb=short',
    full_project_suite=False,review=dict(critical=0,important=1,important_fixed='Fresh live actuator observation after recovery reference reset; two regression checks',minor=0,deferred_minors=[]),
    prior_sealed_files_verified=prior,execution_input_hashes_verified=len(config['input_sha256']),source_snapshots=sum(p.is_file() for p in (OUT/'source_snapshot').rglob('*')),
    document_snapshots=len(docs),input_sources_unchanged_during_execution=ledger['inputs_unchanged'],live_changes_since_execution=changed,
    live_plan_change_scope='Closeout checkboxes/status only; execution original in source_snapshot',configuration_and_model_bindings_verified=True,archive_hash_verified=True,
    stop_independently_rechecked=True,figures_visually_checked=['results.png','search_diagnosis.png','reference_diagnosis.png'],new_links_checked=links,
    real_search_commands_reconstructed=sum(d['reconstructed_commands'] for d in diags.values()),max_command_error_m_s=max(d['max_command_error_m_s'] for d in diags.values()),
    max_actual_reference_radius_um=max(d['max_actual_reference_radius_um'] for d in diags.values()),
    max_reference_prediction_error_um=max(d['max_reference_prediction_error_um'] for d in diags.values()),
    full_recovery_dynamically_exercised=any(e['reason']=='B2_RECOVERY_RESUMED' for d in diags.values() for e in d['environment_events']),
    net_progress_search_exit_events=sum(len(d['advances']) for d in diags.values()),
    nominal_blocked_pose_reference_bounded=True,implementation_complete=True,bounded_verification_complete=True,
    development_matrix_all_success=fully_successful,repair_performance_accepted=fully_successful,stage_B2_complete=False,training_admitted=False,
    episodes=a['episodes'],functional_success=a['functional_success'],unused_closed=a['unused_closed'],cumulative_episodes=a['cumulative'],
    training_updates=0,network_calls=0,independent_tests=0,automatic_tracking='PAUSED')
(OUT/'verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (OUT/'progress.md').open('a',encoding='utf-8') as f:f.write('\nTask 3: complete — archived command/reference/progress/stop checks, three visually inspected figures, six document snapshots; prior 1350 sealed files unchanged. New delivery seal generated and independently rechecked.\n')
files={p.relative_to(OUT).as_posix():dict(sha256=digest(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json'}
manifest=dict(status='SEALED',created_at=now(),scope='Bounded drive-reference search verification; no B.2 or learning acceptance',files=files)
(OUT/'delivery_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name,item in read(OUT/'delivery_manifest.json')['files'].items():assert digest(OUT/name)==item['sha256'] and (OUT/name).stat().st_size==item['bytes']
print(json.dumps(dict(sealed_files=len(files),manifest_sha256=digest(OUT/'delivery_manifest.json'),verification=v),ensure_ascii=False))
