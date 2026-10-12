"""Seal this offline preparation delivery after evidence and document checks."""
from pathlib import Path
import hashlib,json,re,shutil,sys
from datetime import datetime,timezone,timedelta

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(OUT))
from prepare_and_audit import verify_prior
from tools.evaluation.paper_comparison import comparison_key,summarize

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name):return json.loads((OUT/name).read_text(encoding='utf-8'))
def write(name,value):(OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def main():
    manifest=OUT/'delivery_manifest.json'
    if manifest.exists():raise RuntimeError('Already sealed')
    protocol=read('protocol.json');common=protocol['common'];audit=read('residual_integration_audit.json')
    assert protocol['comparison_key']==comparison_key(common)
    assert protocol['training_admitted'] is False and protocol['stage_B2_complete'] is False
    assert protocol['current_budget']==dict(dynamic_episodes=0,physical_substeps=0,network_calls=0,training_updates=0,cumulative_episodes=130)
    assert sha(ROOT/'tools/evaluation/paper_comparison.py')==common['evaluator_source_sha256']
    source=common['frozen_common_source_sha256']
    for name,digest in source.items():assert sha(ROOT/name)==digest,name
    prior=verify_prior();assert sum(v['files_verified'] for v in prior.values())==2112
    assert prior==read('prior_seals_verified.json')
    records=read('baseline_records.json')
    assert summarize(records,[c['id'] for c in common['cases']])==read('baseline_metrics.json')
    for record in records:assert sha(ROOT/record['archive_path'])==record['archive_sha256']
    assert audit['search_commands']==16563 and audit['counterfactual_actions']==132504 and audit['envelope_violations']==6
    assert all(audit[k]==0 for k in ['new_dynamic_episodes','new_physical_steps','network_calls','training_updates'])
    test_text=(OUT/'tests_final.txt').read_text(encoding='utf-8')
    assert re.search(r'272 passed',test_text) and not re.search(r'\d+ failed|\d+ error',test_text)
    review=read('review_result.json');assert review['fixed_important']==2 and review['unresolved_important']==0
    assert review['fresh_context'] and review['independent_author']
    documents=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md',
        'deliverables/monthly_progress/2026-10/月报素材_2026-10.md','docs/stage_b/论文对照协议_v4.md',
        'docs/stage_b/训练合同_v3.md','docs/superpowers/plans/2026-10-04-paper-protocol-v4.md']
    links=0
    for name in documents:
        p=ROOT/name;text=p.read_text(encoding='utf-8')
        if name in documents[:5]:
            assert 'protocol_v4_20261004' in text,name
            if name!=documents[3]:assert text.count('<!-- paper-protocol-current -->')==1,name
        target=OUT/'document_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    # Check every link in the new report and current summary blocks; unrelated
    # historical links are preserved and do not become new claims here.
    for p in [OUT/'结果说明.md']+[ROOT/n for n in documents[:5]]:
        text=p.read_text(encoding='utf-8')
        if p!=OUT/'结果说明.md':
            if p.name=='研究推进计划_当前版.md':
                text=text.split('\n## ',2)[1]
            else:text=text.split('<!-- paper-protocol-current -->')[1].split('<!-- /paper-protocol-current -->')[0]
        for link in re.findall(r'\]\(([^)]+)\)',text):
            if link.startswith(('http:','https:','#')):continue
            assert (p.parent/link.split('#')[0]).resolve().exists(),(str(p),link)
            links+=1
    snap_names=[n for n in source if n.endswith('.py')]
    snap_names+=['tools/evaluation/paper_comparison.py','tests/task_variants/test_paper_comparison.py']
    for name in snap_names:
        target=OUT/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
    with (OUT/'progress.md').open('a',encoding='utf-8') as f:
        f.write('\nFinal: verification complete — 272相关检查通过；2 Important均经RED→GREEN修复，独立审查为全新上下文；无延期Minor。共同输入、2112历史文件、5归档指标和新链接均通过。\n')
    verification=dict(created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),tests_passed=272,
        whole_project_suite=False,review=review,prior_sealed_files_verified=2112,
        common_bound_inputs=len(source),source_snapshots=len(snap_names),document_snapshots=len(documents),links_checked=links,
        common_key=protocol['comparison_key'],baseline_cases=5,baseline_functional_successes=5,
        new_dynamic_episodes=0,physical_substeps=0,network_calls=0,training_updates=0,cumulative_episodes=130,
        protocol_and_offline_evaluation_complete=True,residual_v4_integration_complete=False,
        stage_B2_complete=False,training_admitted=False,automatic_tracking='PAUSED')
    write('verification.json',verification)
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
           for p in sorted(OUT.rglob('*')) if p.is_file() and p!=manifest and '__pycache__' not in p.parts}
    write('delivery_manifest.json',dict(status='SEALED',created_at=verification['created_at'],
        scope='v4 common comparison preparation and offline command audit; no dynamics or training',files=files))
    for name,record in files.items():assert sha(OUT/name)==record['sha256']
    print(json.dumps(dict(status='SEALED',files=len(files),manifest_sha256=sha(manifest),verification=verification),ensure_ascii=False))

if __name__=='__main__':main()
