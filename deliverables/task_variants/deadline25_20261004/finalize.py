"""Freeze bounded validation evidence and rolling-document snapshots."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,hashlib,shutil,re
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Already sealed')
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
now=lambda:datetime.now(timezone(timedelta(hours=8))).isoformat()
a=read(OUT/'assessment.json');ledger=read(OUT/'run/ledger.json');config=read(OUT/'configuration.json')
assert ledger['status'] in ['complete','controlled_stop']
assert 1<=a['episodes']==len(ledger['episodes'])<=5
assert a['cumulative']==124+a['episodes'] and a['unused_closed']==5-a['episodes']
assert a['control_cycles']==sum(e['control_cycles'] for e in ledger['episodes'])
assert a['physical_substeps']==sum(e['physical_substeps'] for e in ledger['episodes'])
assert '199 passed' in (OUT/'tests_final.txt').read_text(encoding='utf-8')
assert config['task_id']=='dsub9_clearance120_functional_25s_v3' and config['b2_config']['total_action_time_s']==25.
cc=read(OUT/'configuration_comparison.json');assert not cc['unexpected_paths'] and cc['model_equal'] and cc['controller_id_equal']
prior={}
for name in ['clearance120_20261003','functional_b2_20261003','search_load_20261004','admittance_rebase_20261004','compliant_search_20261004','axis_search_20261004','reference_search_20261004']:
    p=OUT.parent/name;m=read(p/'delivery_manifest.json')
    for f,item in m['files'].items():assert sha(p/f)==item['sha256'] and (p/f).stat().st_size==item['bytes']
    prior[name]=len(m['files'])
assert sum(prior.values())==1599
changed=[]
for name,digest in config['input_sha256'].items():
    p=ROOT/name
    if sha(p)!=digest:changed.append(name)
    if p.suffix.lower()!='.stl':assert sha(OUT/'source_snapshot'/name)==digest,name
assert changed==['docs/superpowers/plans/2026-10-04-deadline25-preflight.md'],changed
for name,digest in read(OUT/'preparation_binding.json').items():assert sha(OUT/name)==digest
for e in ledger['episodes']:assert sha(OUT/'run'/f"{e['id']}.json.gz")==e['archive_sha256']
comparisons=read(OUT/'trajectory_comparisons.json');prefix=comparisons['y_neg_150']
assert prefix['samples']==10001 and prefix['before_time_s']==20. and all(prefix['fields_equal'].values())
diag=read(OUT/'diagnosis.json')
geometry=read(OUT/'layered_geometry_validation.json')
assert geometry['settling_samples_checked']==501 and geometry['dense_final_layers_checked']==18
assert geometry['max_dense_vs_analytic_difference_um']<.001 and geometry['recorded_verdict_unchanged']=='TASK_FAILURE'
for d in diag.values():
    assert d['max_command_error_m_s']<1e-12 and d['max_limited_command_error_m_s']<1e-12
    assert d['xy_offset_freeze_error_m']==d['xy_velocity_freeze_error_m_s']==0.
    assert d['max_actual_reference_radius_um']<=120.+1e-6
docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md','docs/superpowers/plans/2026-10-04-deadline25-preflight.md']
for name in docs:
    p=ROOT/name;s=p.read_text(encoding='utf-8')
    assert 'deadline25_20261004' in s or name.endswith('2026-10-04-deadline25-preflight.md'),name
    dest=OUT/'document_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
for name in [docs[0],docs[1],docs[2],docs[4]]:assert (ROOT/name).read_text(encoding='utf-8').count('<!-- deadline25-current -->')==1
links=0
for p in [OUT/'结果说明.md']+[ROOT/name for name in docs]:
    for target in re.findall(r'\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        if p.parent!=OUT and 'deadline25_20261004' not in target and '2026-10-04-deadline25-preflight' not in target:continue
        if re.match(r'^[a-zA-Z]+://',target) or target.startswith('#'):continue
        dest=(p.parent/target.split('#')[0]).resolve()
        if dest not in [OUT/'verification.json',OUT/'delivery_manifest.json']:assert dest.exists(),str(dest)
        links+=1
v=dict(created_at=now(),tests_passed=199,full_project_suite=False,
    review=dict(critical=0,important=0,minor=0,independent_author=True,fresh_context=False,limitation='agent thread limit; reused prior read-only reviewer'),
    prior_sealed_files_verified=prior,execution_inputs=len(config['input_sha256']),
    source_snapshots=sum(p.is_file() for p in (OUT/'source_snapshot').rglob('*')),
    document_snapshots=6,links_checked=links,inputs_unchanged_during_execution=ledger['inputs_unchanged'],
    live_changes_since_execution=changed,plan_change='closeout checklist and actual result; original frozen in source_snapshot',
    archives_verified=True,stop_independently_rechecked=True,first_20s_exact_samples=prefix['samples'],
    first_20s_fields=prefix['fields_equal'],figures_visually_checked=['results.png','search_diagnosis.png','completion.png'],
    reconstructed_search_commands=sum(d['reconstructed_commands'] for d in diag.values()),
    max_search_command_error_m_s=max(d['max_command_error_m_s'] for d in diag.values()),
    max_actual_reference_radius_um=max(d['max_actual_reference_radius_um'] for d in diag.values()),
    offline_layered_geometry_audit=geometry,
    implementation_complete=True,bounded_verification_complete=True,
    development_matrix_all_success=a['episodes']==5 and a['functional_success']==5,
    episodes=a['episodes'],functional_success=a['functional_success'],strict_precision_success=a['strict_precision_success'],
    unused_closed=a['unused_closed'],cumulative_episodes=a['cumulative'],training_updates=0,network_calls=0,independent_tests=0,
    stage_B2_complete=False,training_admitted=False,automatic_tracking='PAUSED')
(OUT/'verification.json').write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (OUT/'progress.md').open('a',encoding='utf-8') as f:f.write('\nTask 3: complete — 1599 prior files unchanged; inputs/archive/prefix/controller/stop checked; three figures inspected; six doc snapshots and new links verified; sealed manifest read back.\n')
files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json'}
(OUT/'delivery_manifest.json').write_text(json.dumps(dict(status='SEALED',created_at=now(),scope='25s common task bounded preflight; not training or B.2 acceptance',files=files),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
for name,item in read(OUT/'delivery_manifest.json')['files'].items():assert sha(OUT/name)==item['sha256'] and (OUT/name).stat().st_size==item['bytes']
print(json.dumps(dict(sealed_files=len(files),manifest_sha256=sha(OUT/'delivery_manifest.json'),verification=v),ensure_ascii=False))
