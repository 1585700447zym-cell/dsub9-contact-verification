"""Seal actual outcomes and immutable inputs; never claim missing validation."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import hashlib,json,re,shutil,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT/'deliverables/paper_comparison/protocol_v4_20261004'))
from prepare_and_audit import verify_prior
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def main():
    manifest=OUT/'delivery_manifest.json'
    if manifest.exists():raise RuntimeError('Already sealed')
    count=sum(r['files_verified'] for r in verify_prior().values())
    for name,pin in [('protocol_v4_20261004','ed7d406236741eeefdb0b78983bb531d49c35e0f6bb901930418bd86e2dd7bd6'),
        ('v4_adapter_20261004','ea040c19632830c9ba30ada23683825973c507396f4f52de4de0387d1f869b73'),
        ('v4_continuation_20261006','536a599cd5b8baaab8fbb8951f8b1557a6eb40bc2d215f12603103d0a07a4673')]:
        folder=ROOT/'deliverables/paper_comparison'/name;assert sha(folder/'delivery_manifest.json')==pin
        for rel,record in read(folder/'delivery_manifest.json')['files'].items():assert sha(folder/rel)==record['sha256']
        count+=len(read(folder/'delivery_manifest.json')['files'])
    assert count==2827
    cfg=read(OUT/'configuration.json');binding=read(OUT/'execution_source_binding.json')
    for rel,digest in binding['files'].items():assert sha(ROOT/rel)==sha(OUT/'source_snapshot'/rel)==digest,rel
    assert read(OUT/'verification.json')['passed'] and read(OUT/'verification.json')['source_sha256']==cfg['input_sha256']
    assert '420 passed' in (OUT/'verification.txt').read_text(encoding='utf8')
    a=read(OUT/'assessment.json');ledger=read(OUT/'run/ledger.json')
    assert a['attempts']==len(ledger['episodes']) and a['cumulative']==140+a['attempts'] and a['unused_closed']==28-a['attempts']
    assert a['formal_update_attempts']<=4000 and a['formal_updates']<=a['formal_update_attempts']
    for e in ledger['episodes']:
        if e['status']=='finished':assert sha(OUT/'run'/(e['id']+'.json.gz'))==e['archive_sha256']
    docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md',
        'docs/superpowers/plans/2026-10-06-v4-learning-pilot.md','docs/stage_b/论文对照协议_v4.md','docs/stage_b/训练合同_v3.md']
    for name in docs:
        dest=OUT/'document_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dest)
    links=0
    for p in [OUT/'结果说明.md']+[ROOT/name for name in docs[:5]]:
        content=p.read_text(encoding='utf8')
        if p!=OUT/'结果说明.md':content=content.split('<!-- v4-learning-pilot-current -->')[1].split('<!-- /v4-learning-pilot-current -->')[0]
        for link in re.findall(r'\]\(([^)]+)\)',content):
            if link.startswith(('http:','https:','#')):continue
            assert (p.parent/link.split('#')[0]).resolve().exists(),(p,link)
            links+=1
    verification=dict(tests_passed=420,full_project_suite=False,prior_sealed_files_verified=count,bound_inputs=len(binding['files']),
        source_snapshots=len(binding['files']),document_snapshots=len(docs),links_checked=links,
        review=dict(fresh_context=True,reported_important=5,unresolved_important=0,fix_passes=1,second_review=False,minor_deferred=1),
        attempts=a['attempts'],completed=a['completed'],cumulative=a['cumulative'],formal_updates=a['formal_updates'],
        training_admitted=True,stage_B2_complete=False,independent_tests=0,automatic_tracking='PAUSED',audit_errors=a['audit_errors'])
    write('final_verification.json',verification)
    with (OUT/'progress.md').open('a',encoding='utf8') as f:
        f.write('\nTask4: 准入/一次性执行已结束，实际结果依assessment；未执行额度关闭。\nTask5: 实际档案与完整检查点只读核验、五份文档/滚动月报同步、2827历史文件/1057绑定输入及链接核验完成。B.2未完成，未把缺失/失败当收益。\n')
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*'))
        if p.is_file() and p!=manifest and '__pycache__' not in p.parts}
    write('delivery_manifest.json',dict(status='SEALED',created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        scope='137D qualified learning chain and registered finite development pilot; actual outcome in assessment',files=files))
    for rel,record in files.items():assert sha(OUT/rel)==record['sha256']
    print(json.dumps(dict(status='SEALED',files=len(files),manifest_sha256=sha(manifest),verification=verification),ensure_ascii=False))
if __name__=='__main__':main()
