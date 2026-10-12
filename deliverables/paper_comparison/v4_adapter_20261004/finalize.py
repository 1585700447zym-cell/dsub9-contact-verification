"""Seal finished adapter evidence without changing old frozen deliveries."""
from pathlib import Path
import json,hashlib,re,shutil,sys
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'deliverables/paper_comparison/protocol_v4_20261004'))
from prepare_and_audit import verify_prior
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def main():
    manifest=OUT/'delivery_manifest.json'
    if manifest.exists():raise RuntimeError('Already sealed')
    prior=verify_prior();previous=ROOT/'deliverables/paper_comparison/protocol_v4_20261004'
    assert sha(previous/'delivery_manifest.json')=='ed7d406236741eeefdb0b78983bb531d49c35e0f6bb901930418bd86e2dd7bd6'
    for name,record in read(previous/'delivery_manifest.json')['files'].items():
        assert sha(previous/name)==record['sha256'] and (previous/name).stat().st_size==record['bytes']
    old_count=sum(v['files_verified'] for v in prior.values())+len(read(previous/'delivery_manifest.json')['files']);assert old_count==2334
    ledger=read(OUT/'run/ledger.json');assessment=read(OUT/'assessment.json');config=read(OUT/'configuration.json')
    assert ledger['status'] in ('complete','controlled_stop','error','input_changed') and ledger['unused_closed']==9-len(ledger['episodes'])
    assert assessment['attempts']==len(ledger['episodes']) and assessment['cumulative']==130+len(ledger['episodes'])
    assert assessment['training_updates']==assessment['network_calls']==assessment['independent_tests']==0
    binding=read(OUT/'preparation_binding.json')
    for name,digest in binding.items():assert sha(OUT/name)==digest
    changed=[]
    for name,digest in config['input_sha256'].items():
        if sha(ROOT/name)!=digest:changed.append(name)
        if (OUT/'source_snapshot'/name).exists():assert sha(OUT/'source_snapshot'/name)==digest
    assert changed==['docs/superpowers/plans/2026-10-04-v4-residual-adapter.md'],changed
    for e in ledger['episodes']:
        if e['status']=='finished':assert sha(OUT/'run'/(e['id']+'.json.gz'))==e['archive_sha256']
        elif e.get('error_archive_sha256'):assert sha(OUT/'run'/(e['id']+'.error.json.gz'))==e['error_archive_sha256']
    assert '297 passed' in (OUT/'tests_final.txt').read_text(encoding='utf8')
    assert read(OUT/'offline_replay.json')['filtered_actions']==6
    docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md',
        'deliverables/monthly_progress/2026-10/月报素材_2026-10.md','docs/superpowers/plans/2026-10-04-v4-residual-adapter.md',
        'docs/stage_b/论文对照协议_v4.md','docs/stage_b/训练合同_v3.md']
    for name in docs:
        target=OUT/'document_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    for name in ['tests/task_variants/test_v4_adapter.py','tests/task_variants/test_v4_adapter_preflight.py']:
        target=OUT/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    links=0
    for p in [OUT/'结果说明.md']+[ROOT/n for n in docs[:5]]:
        text=p.read_text(encoding='utf8')
        if p!=OUT/'结果说明.md':
            if p.name=='研究推进计划_当前版.md':text=text.split('\n## ',2)[1]
            else:
                assert text.count('<!-- v4-adapter-current -->')==1
                text=text.split('<!-- v4-adapter-current -->')[1].split('<!-- /v4-adapter-current -->')[0]
        for link in re.findall(r'\]\(([^)]+)\)',text):
            if link.startswith(('http:','https:','#')):continue
            assert (p.parent/link.split('#')[0]).resolve().exists(),(p,link)
            links+=1
    with (OUT/'progress.md').open('a',encoding='utf8') as f:
        f.write('\nFinal verification complete — 297相关检查；4 Important修复，实际结果按assessment；2334历史文件与新档案/源快照/文档链接校验通过。无训练准入或学习收益结论。\n')
    verification=dict(created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),tests_passed=297,full_project_suite=False,
        review=dict(independent_author=True,fresh_context=True,initial_critical=0,initial_important=4,fixed_important=4,deferred_minor=0),
        prior_sealed_files_verified=old_count,input_files=len(config['input_sha256']),
        source_snapshots=len(list((OUT/'source_snapshot').rglob('*.py')))+len(list((OUT/'source_snapshot').rglob('*.md'))),
        document_snapshots=len(docs),links_checked=links,live_changes_since_execution=changed,
        bounded_preflight_passed=assessment['bounded_preflight_passed'],attempts=assessment['attempts'],completed=assessment['completed'],
        unused_closed=assessment['unused_closed'],cumulative=assessment['cumulative'],physical_substeps=assessment['physical_substeps'],
        training_updates=0,network_calls=0,independent_tests=0,training_admitted=False,stage_B2_complete=False,automatic_tracking='PAUSED')
    write('verification.json',verification)
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
        for p in sorted(OUT.rglob('*')) if p.is_file() and p!=manifest and '__pycache__' not in p.parts}
    write('delivery_manifest.json',dict(status='SEALED',created_at=verification['created_at'],scope='v4 bounded adapter/B1 development preflight; no learning admission',files=files))
    for name,record in files.items():assert sha(OUT/name)==record['sha256']
    print(json.dumps(dict(status='SEALED',files=len(files),manifest_sha256=sha(manifest),verification=verification),ensure_ascii=False))

if __name__=='__main__':main()
