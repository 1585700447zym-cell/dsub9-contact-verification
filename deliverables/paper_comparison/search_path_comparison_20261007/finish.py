"""Seal this completed offline deliverable; never alters prior seals."""
from pathlib import Path
import datetime,json,shutil
import analyze
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Already sealed')
    verification=analyze.read(OUT/'verification.json');review=analyze.read(OUT/'review.json')
    assert verification['passed'] and sum(review[k] for k in ('critical','important','minor'))==0
    assert '27 passed' in (OUT/'final_tests.log').read_text(encoding='utf8')
    assert analyze.verify_sources()==verification['source_proof']
    plan=ROOT/'docs/superpowers/plans/2026-10-07-search-path-comparison.md'
    plan.write_text(plan.read_text(encoding='utf8').replace('- [ ]','- [x]'),encoding='utf8')
    shutil.copyfile(plan,OUT/'plan_snapshot.md')
    qa=dict(passed=True,method='author visually inspected both PNG figures, rechecked path figure after endpoint completion',
        figures=['search_paths.png','actions_commands.png'],source_rows=15626,
        notes='Chinese labels/units/legends readable; endpoint included; XY clearance circle is illustration only, not a functional geometry judgment')
    analyze.write(OUT/'figure_qa.json',qa)
    close=dict(**verification,tests=27,independent_review='one limited read-only C0/I0/M0; raw arithmetic and 6 tests independently checked',figure_qa=True)
    analyze.write(OUT/'closure_verification.json',close)
    config=analyze.read(OUT/'configuration.json')
    files=['analyze.py','test_analysis.py','build_report.py','verify.py','update_documents.py','finish.py','plan_snapshot.md']
    config['analysis_input_sha256']={rel:analyze.sha(OUT/rel) for rel in files}
    config['source_proof']=verification['source_proof'];config['training_admission']=False;config['automatic_tracking']='PAUSED'
    analyze.write(OUT/'configuration.json',config)
    with (OUT/'progress.md').open('a',encoding='utf8') as f:
        f.write('\nTask 2: complete — 原始算术15,626周期、两边界独立复算、27/27相关检查、1057输入与658旧文件核验通过；两图QA及限定独立审查C0/I0/M0。五份资料/快照一致，路线决定停止直接F→G；当前无新训练准入、PAUSED，累计208。阶段完成后暂停汇报。\n')
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
    (OUT/'closure_summary.md').write_text('# PC-10离线交付收口\n\n'+
        '4档案28,465旧周期、5段SEARCH15,626周期；27项相关纯档案检查、独立原始算术、两边界公式及限定审查通过。1057生产输入与658旧封存文件保持。\n\n'+
        'G两段净深度未超历史峰值，当前参考规则正常耗尽；未定位执行错误，唯一训练成因未证。停止直接F演员套G门控，下一项只准备匹配训练S与合理小固定边界的公平登记草案。\n\n'+
        '本轮新物理/子步/推理/训练/发布0，累计208；关闭旧预算、PAUSED、新准入无。完整B.2/C和论文证据未验收，阶段完成暂停汇报。\n\n'+
        '只读重核：`python verify.py`；重新生成须使用完整副本，不在封存目录运行analyze/build/update/finish。\n',encoding='utf8')
    sealed={}
    for p in sorted(OUT.rglob('*')):
        if not p.is_file() or any(x in p.parts for x in ('__pycache__','plot_cache','.pytest_cache')):continue
        rel=p.relative_to(OUT).as_posix()
        if rel=='delivery_manifest.json':continue
        sealed[rel]=dict(sha256=analyze.sha(p),bytes=p.stat().st_size)
    analyze.write(OUT/'delivery_manifest.json',dict(status='SEALED',created_at=now,
        scope='PC-10 pure offline search-path evidence and route decision; no new physics/inference/training admission',files=sealed))
    print('Sealed offline deliverable',len(sealed),'files; cumulative dynamics 208; new computation 0')

if __name__=='__main__':main()
