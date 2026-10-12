"""Resolve historical labels and record the read-only terminal review."""
import json
import validation_contract as C
OUT=C.HERE/'result_analysis'
for rel in ('项目进度跟踪.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md'):
    p=C.ROOT/rel;t=p.read_text(encoding='utf-8')
    t=t.replace('**100ms预热学习验证已收口（2026-10-01）：**','**上一学习验证（历史保存故障，2026-10-01）：**',1)
    t=t.replace('**100ms预热配对预检已收口（2026-10-01）：**','**上一配对预检（历史，2026-10-01）：**',1)
    if '月报' in rel:
        t=t.replace('| 100ms预热学习验证 |','| 上一100ms学习验证（历史保存故障） |',1)
        t=t.replace('我新增的检查点代码把只接受字节/文本的', '上一保存故障阶段（历史，重启前）：我新增的检查点代码把只接受字节/文本的',1)
        t=t.replace('本轮讲稿：“我们保持原学习率和保护，只改变预热时间持续性。','上一保存故障阶段讲稿（历史）：“我们保持原学习率和保护，只改变预热时间持续性。',1)
    p.write_text(t,encoding='utf-8')
t=(C.ROOT/'项目交付总览.md').read_text(encoding='utf-8')
row=next(x for x in t.splitlines() if x.startswith('| 最新保存修复后的100ms效果结果 |'))
assert 'b2_temporal_learning_restart_20261001' in row and 'b2_temporal_learning_validation_20261001' not in row
report='''# 独立终点结果审查

2026-10-01；审查者：/root/restart_validation_review。此处按其只读最终回复整理，不冒称重新执行源代码审查或计算。

审查原结论：Critical 0 / Important 0 / Minor 1；Ready Yes；Declined to judge 无。

- 实际重算1246个绑定输入、38个结果输入SHA均一致；当前binding/auth及旧failed/fix父封存相符。
- 8个实际回合全部完成、有效停稳，无故障归档遗漏，fault.log为空。起点4/4成功；C500/1000/1500为TARGET_POSE_NOT_SETTLED普通失败；C2000为CONTACT_GUARD/FORCE_LIMIT，峰值0.025161399066734227 N。
- 四个检查点摘要和各回合使用的actor摘要对应。真实零状态独立reader成功，审核计算0。
- 新8动态/2000批/6000 Adam/427960物理子步/543960模块调用；累计80动态；方法累计2500批包含旧丢失500。余量关闭，PAUSED。
- returncode20与账本受控停止一致，通用process_exit.status=failed不能单独解释为保存故障或崩溃。

Minor：旧保存故障段落/讲稿和导航可能与最新终点混淆。作者已核验最新总览链接指向当前restart结果，并将进度与月报的旧摘要、旧数字行、旧负结果及旧讲稿明确标历史。本项为文档解释修正，没有改变任何绑定执行源码、历史归档或计算。

最终限定：100ms预热未达到本轮预登记修复目标；C2500固定评价、独立恢复动态、A及独立测试未执行。不能推断A更好、唯一根因或critic高估已经消除。B.2未完成。

审查者回复时最终交付封存尚未生成；其审查不等于最终封存核验。最终封存由独立的delivery_verification记录给出。
'''
(OUT/'独立结果审查.md').write_text(report,encoding='utf-8')
record=dict(ready=True,critical=0,important=0,minor=1,minor_resolved_by_author=True,
    reviewer='/root/restart_validation_review',review_scope='new_actual_terminal_evidence_read_only',
    reviewed_binding_inputs=1246,reviewed_result_inputs=38,declined=[],
    no_new_computation=True,no_source_re_review=True,final_delivery_seal_reviewed=False,
    minor_resolution='Latest delivery link verified current; prior progress/monthly summaries, numbers, negative result and talk explicitly labelled historical.')
(OUT/'review_assessment.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
with (C.HERE/'progress.md').open('a',encoding='utf-8') as f:
    f.write('\nTask3 terminal evidence review complete: Critical0/Important0/Minor1 ready; historical-label Minor resolved and latest navigation verified. Registered effect verification reached its controlled negative endpoint, not B.2 completion. No computation/retry; final delivery seal next.\n')
print('Terminal review recorded; history-label Minor resolved; no computation.')
