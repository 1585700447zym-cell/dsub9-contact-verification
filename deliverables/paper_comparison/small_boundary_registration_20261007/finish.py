"""Seal a completed draft; no execution capability is created."""
from pathlib import Path
import datetime,shutil,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
import build_draft as b

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Already sealed')
    v=b.read(OUT/'verification.json');r=b.read(OUT/'review.json');c=b.read(OUT/'draft_contract.json')
    assert v['passed'] and v['checks']==71 and r['critical']==r['important']==0 and r['minor']==r['minor_author_closed']==1
    assert c['training_admitted'] is False and c['execution_authorized'] is False and b.sources()==v['source_proof']
    pairs={
        'design_snapshot.md':ROOT/'docs/superpowers/specs/2026-10-07-small-boundary-fair-comparison-design.md',
        'implementation_plan_snapshot.md':ROOT/'docs/superpowers/plans/2026-10-07-small-boundary-fair-comparison.md'}
    for rel,p in pairs.items():shutil.copyfile(p,OUT/rel)
    assert '- [x]' not in (OUT/'implementation_plan_snapshot.md').read_text(encoding='utf8')
    b.write(OUT/'closure_verification.json',dict(**v,independent_review='limited design C0/I0/M1, minor wording author-corrected; no second review',
        future_implementation_steps_completed=0,status='DRAFT_COMPLETE_EXECUTION_NOT_ADMITTED'))
    with (OUT/'progress.md').open('a',encoding='utf8') as f:
        f.write('\nStage complete: 71静态来源/预算/状态/链接核对通过，独立设计C0/I0/M1已关闭表述歧义，五份资料快照与原文件一致。草案封存，不代表用户已批准预算或新代码已准入；累计208、新计算0、PAUSED、旧预算关闭，完整B.2/C仍待。可交付阶段完成后暂停汇报。\n')
    (OUT/'closure_summary.md').write_text('# PC-11登记草案收口\n\n'+
        '条件继承25份历史评价，只新增F12.5匹配训练的推荐方案。拟21新动态/2000正式批（累计上限229）及单列4合成事务/32测试状态；当前未授权、未准入、未执行，实际累计208。\n\n'+
        '旧S/F0.39%继续门失败保持；F12.5收益/精度/接触判定、预算不足/继承失败/物理故障停止分支已写明。历史执行外推2.10h、规划窗口2–4h、拟硬限6h，不能保证完成全部矩阵。\n\n'+
        '71静态核对和限定独立设计审查通过，M1预算文字已更正；704旧文件与1057共享输入保持。完整B.2/C和论文证据未验收，五份滚动资料已同步。下一项仅新适配及离线门，实现候选后再申请新计算。\n\n'+
        '只读复核可运行verify_draft.py；生成/更新脚本不得在封存目录重复执行，重生成须使用完整副本。阶段完成暂停汇报。\n',encoding='utf8')
    files={}
    for p in sorted(OUT.rglob('*')):
        if not p.is_file() or any(x in p.parts for x in ('__pycache__','.pytest_cache')):continue
        rel=p.relative_to(OUT).as_posix()
        if rel=='delivery_manifest.json':continue
        files[rel]=dict(sha256=b.sha(p),bytes=p.stat().st_size)
    b.write(OUT/'delivery_manifest.json',dict(status='SEALED_DRAFT_ONLY',created_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
        scope='PC-11 proposed small-boundary fair comparison; not implementation/admission/compute authorization',
        training_admitted=False,execution_authorized=False,actual_new_computation=0,files=files))
    print('SEALED DRAFT ONLY',len(files),'files; actual cumulative 208; proposed cap 229 is not enabled')

if __name__=='__main__':main()
