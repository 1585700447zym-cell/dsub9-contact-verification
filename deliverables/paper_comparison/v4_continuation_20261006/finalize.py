"""Seal evidence; prior deliveries and original source snapshots stay intact."""
import sys,json,hashlib,shutil,re
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'deliverables/paper_comparison/protocol_v4_20261004'))
from prepare_and_audit import verify_prior

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def main():
    manifest=OUT/'delivery_manifest.json'
    if manifest.exists():raise RuntimeError('Already sealed')
    earlier=verify_prior();count=sum(v['files_verified'] for v in earlier.values())
    for relative,expected in [('deliverables/paper_comparison/protocol_v4_20261004','ed7d406236741eeefdb0b78983bb531d49c35e0f6bb901930418bd86e2dd7bd6'),
        ('deliverables/paper_comparison/v4_adapter_20261004','ea040c19632830c9ba30ada23683825973c507396f4f52de4de0387d1f869b73')]:
        p=ROOT/relative;assert sha(p/'delivery_manifest.json')==expected
        for name,rec in read(p/'delivery_manifest.json')['files'].items():
            assert sha(p/name)==rec['sha256'] and (p/name).stat().st_size==rec['bytes']
            count+=1
    assert count==2588
    config=read(OUT/'configuration.json');assessment=read(OUT/'assessment.json');ledger=read(OUT/'run/ledger.json')
    assert ledger['status'] in ('complete','controlled_stop','error') and ledger['unused_closed']==1-len(ledger['episodes'])
    assert assessment['attempts']==len(ledger['episodes']) and assessment['cumulative']==139+len(ledger['episodes'])
    assert assessment['training_updates']==assessment['policy_calls']==assessment['replay_published']==assessment['independent_tests']==0
    for name,digest in read(OUT/'preparation_binding.json').items():assert sha(OUT/name)==digest
    changed=[]
    for name,digest in config['input_sha256'].items():
        if sha(ROOT/name)!=digest:changed.append(name)
        p=OUT/'source_snapshot'/name
        if p.exists():assert sha(p)==digest
    plan='docs/superpowers/plans/2026-10-06-v4-continuation-preflight.md'
    assert changed==[plan],changed
    for e in ledger['episodes']:
        if e['status']=='finished':assert sha(OUT/'run'/(e['id']+'.json.gz'))==e['archive_sha256']
        elif e.get('error_archive_sha256'):assert sha(OUT/'run'/(e['id']+'.error.json.gz'))==e['error_archive_sha256']
    assert '310 passed' in (OUT/'tests_final.txt').read_text(encoding='utf8')
    assert read(OUT/'offline_check.json')['search_zero_rows']==16563
    docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md',
        'deliverables/monthly_progress/2026-10/月报素材_2026-10.md',plan,'docs/stage_b/论文对照协议_v4.md','docs/stage_b/训练合同_v3.md']
    for name in docs:
        p=OUT/'document_snapshot'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,p)
    for name in ['tests/task_variants/test_v4_continuation.py','tests/task_variants/test_v4_continuation_preflight.py']:
        p=OUT/'source_snapshot'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,p)
    links=0
    for p in [OUT/'结果说明.md']+[ROOT/n for n in docs[:5]]:
        text=p.read_text(encoding='utf8')
        if p.name=='研究推进计划_当前版.md':text=text.split('\n## ',2)[1]
        elif p!=OUT/'结果说明.md':
            assert text.count('<!-- v4-continuation-current -->')==1
            text=text.split('<!-- v4-continuation-current -->')[1].split('<!-- /v4-continuation-current -->')[0]
        for link in re.findall(r'\]\(([^)]+)\)',text):
            if link.startswith(('http:','https:','#')):continue
            assert (p.parent/link.split('#')[0]).resolve().exists(),(p,link)
            links+=1
    verification=dict(created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),tests_passed=310,full_project_suite=False,
        review=dict(independent_author=True,fresh_context=True,critical=0,important=0,minor_deferred=2),prior_sealed_files_verified=count,
        bound_inputs=len(config['input_sha256']),source_snapshots=len([p for p in (OUT/'source_snapshot').rglob('*') if p.is_file()]),
        document_snapshots=len(docs),links_checked=links,live_changes_since_execution=changed,
        bounded_preflight_passed=assessment['bounded_preflight_passed'],attempts=assessment['attempts'],completed=assessment['completed'],
        cumulative=assessment['cumulative'],physical_substeps=assessment['physical_substeps'],training_updates=0,policy_calls=0,
        replay_published=0,independent_tests=0,training_admitted=False,stage_B2_complete=False,automatic_tracking='PAUSED')
    with (OUT/'progress.md').open('a',encoding='utf8') as f:
        f.write('\nFinal verification — 310相关检查；0 Critical/0 Important/2暂缓Minor；2588历史文件、原始动态归档、源/文档快照及链接通过。B.2及训练未验收。\n')
    write('verification.json',verification)
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
        for p in sorted(OUT.rglob('*')) if p.is_file() and p!=manifest and '__pycache__' not in p.parts}
    write('delivery_manifest.json',dict(status='SEALED',created_at=verification['created_at'],
        scope='finite next-zero-action reference fix and one development rollout; no learning',files=files))
    for name,rec in files.items():assert sha(OUT/name)==rec['sha256']
    print(json.dumps(dict(status='SEALED',files=len(files),manifest_sha256=sha(manifest),verification=verification),ensure_ascii=False))

if __name__=='__main__':main()
