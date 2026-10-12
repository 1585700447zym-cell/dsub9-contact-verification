"""Freeze reviewed results and rolling-document snapshots; verify every seal."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,shutil,re
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Already sealed')
now=lambda:datetime.now(timezone(timedelta(hours=8))).isoformat()
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
a=read(OUT/'assessment.json');ledger=read(OUT/'run/ledger.json');config=read(OUT/'configuration.json')
assert ledger['status']=='controlled_stop' and a['episodes']==1 and a['unused_closed']==4 and a['cumulative']==123
assert a['functional_success']==0 and a['control_cycles']==4483 and a['physical_substeps']==44830
assert a['rows'][0]['physical_stopped'] and a['rows'][0]['simulation_valid']
assert not a['rows'][0]['guard_facts']['contact_reasons'] and not a['rows'][0]['guard_facts']['motion_reasons']
assert '154 passed' in (OUT/'tests_final.txt').read_text(encoding='utf-8')
prior={}
for folder in ['clearance120_20261003','functional_b2_20261003','search_load_20261004','admittance_rebase_20261004','compliant_search_20261004']:
    p=OUT.parent/folder;m=read(p/'delivery_manifest.json')
    for name,item in m['files'].items():assert digest(p/name)==item['sha256'] and (p/name).stat().st_size==item['bytes']
    prior[folder]=len(m['files'])
changed=[]
for name,sha in config['input_sha256'].items():
    p=ROOT/name
    if digest(p)!=sha:changed.append(name)
    snapshot=OUT/'source_snapshot'/name
    if p.suffix.lower()!='.stl':assert snapshot.exists() and digest(snapshot)==sha,name
assert changed==['docs/superpowers/plans/2026-10-04-axis-search.md'],changed
for name,sha in read(OUT/'preparation_binding.json').items():assert digest(OUT/name)==sha
for entry in ledger['episodes']:assert digest(OUT/'run'/f"{entry['id']}.json.gz")==entry['archive_sha256']
diag=read(OUT/'diagnosis.json')['y_neg_150']
assert diag['reconstructed_commands']==2675 and diag['max_command_error_m_s']==0.
assert diag['xy_offset_freeze_error_m']==0. and diag['xy_velocity_freeze_error_m_s']==0.
assert 70.<diag['max_target_radius_um']<71. and diag['advances']==[]
assert read(OUT/'offline_probe.json')['legacy_shared_hook_comparisons']==3000
docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md','docs/superpowers/plans/2026-10-04-axis-search.md']
for name in docs:
    p=ROOT/name;s=p.read_text(encoding='utf-8')
    assert 'axis_search_20261004' in s or name.endswith('2026-10-04-axis-search.md'),name
    target=OUT/'document_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
for p in [ROOT/docs[0],ROOT/docs[1],ROOT/docs[2],ROOT/docs[4]]:
    assert p.read_text(encoding='utf-8').count('<!-- axis-search-current -->')==1
links=[]
for p in [OUT/'结果说明.md']+[ROOT/n for n in docs]:
    for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        if p.parent!=OUT and 'axis_search_20261004' not in target and '2026-10-04-axis-search' not in target:continue
        if re.match(r'^[a-zA-Z]+://',target) or target.startswith('#'):continue
        target=target.split('#')[0];resolved=(p.parent/target).resolve()
        if resolved not in [OUT/'verification.json',OUT/'delivery_manifest.json']:assert resolved.exists(),str(resolved)
        links.append(dict(source=p.relative_to(ROOT).as_posix(),target=target))
verification=dict(created_at=now(),tests_passed=154,
    tests_command='python -X utf8 -B -m pytest tests/task_variants tests/control/test_fixed_admittance.py tests/learning/test_action.py tests/learning/test_reward.py -q --tb=short',
    full_project_suite=False,review=dict(critical=0,reviewer_important=0,reviewer_minor=1,regraded_important=1,
        fixed='Public recovery validation before mutation: 5 RED-to-GREEN cases',deferred_minors=[]),
    prior_sealed_files_verified=prior,execution_input_hashes_verified=len(config['input_sha256']),
    source_snapshots=len(list((OUT/'source_snapshot').rglob('*.*'))),document_snapshots=len(docs),
    input_sources_unchanged_during_execution=ledger['inputs_unchanged'],live_changes_since_execution=changed,
    live_plan_change_scope='Closeout checkboxes/status only; execution original in source_snapshot',
    configuration_and_model_bindings_verified=True,archive_hash_verified=True,stop_independently_rechecked=True,
    figures_visually_checked=['results.png','search_diagnosis.png','reference_diagnosis.png'],new_links_checked=len(links),
    legacy_shared_hook_pure_control_comparisons=3000,legacy_commands_states_exact=True,
    real_search_commands_reconstructed=2675,max_command_error_m_s=0.,xy_admittance_memory_frozen=True,
    recovered_return_false_positive_offline_rejected=True,full_recovery_dynamically_exercised=False,
    implementation_complete=True,bounded_verification_complete=True,repair_performance_accepted=False,
    stage_B2_complete=False,training_admitted=False,episodes=1,unused_closed=4,cumulative_episodes=123,
    training_updates=0,network_calls=0,independent_tests=0,automatic_tracking='PAUSED')
(OUT/'verification.json').write_text(json.dumps(verification,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (OUT/'progress.md').open('a',encoding='utf-8') as f:f.write('\nTask 3: complete — independent archived checks and three visually checked figures, six rolling-document snapshots; previous 1113 sealed files unchanged. New issue: integrated drive reference drifts outside intended spiral; no additional run/training. Final seal created and verified.\n')
files={p.relative_to(OUT).as_posix():dict(sha256=digest(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json'}
manifest=dict(status='SEALED',created_at=now(),scope='Bounded axis search: one valid stopped functional failure; B.2 not accepted',files=files)
(OUT/'delivery_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name,item in read(OUT/'delivery_manifest.json')['files'].items():assert digest(OUT/name)==item['sha256'] and (OUT/name).stat().st_size==item['bytes']
print(json.dumps(dict(sealed_files=len(files),manifest_sha256=digest(OUT/'delivery_manifest.json'),verification=verification),ensure_ascii=False))
