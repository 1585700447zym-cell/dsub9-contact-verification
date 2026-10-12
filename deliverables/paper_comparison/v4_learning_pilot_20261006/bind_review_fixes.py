"""Record the one independent review and one author fix pass transparently."""
from pathlib import Path
from tools.validation.run_v4_learning_pilot import input_hashes
from tools.validation.run_clearance_preflight import write
from tools.learning.v4_pilot_contract import read
OUT=Path(__file__).resolve().parent
before=read(OUT/'reviewed_source.json');after=input_hashes()
delta={k:dict(before=before.get(k),after=after.get(k)) for k in sorted(set(before)|set(after)) if before.get(k)!=after.get(k)}
record=dict(critical=0,important=0,reported_critical=0,reported_important=5,minor_deferred=1,
    reviewer='/root/v4_learning_pilot_review',model='gpt-6-astra',reasoning='high',fresh_context=True,
    second_review=False,fix_passes=1,reviewed_source_sha256=before,validated_source_sha256=after,fix_delta=delta,
    resolution='author verified RED 6 failures -> GREEN 30 passed; final bound offline suite must still pass',
    findings=[dict(id=i,reported='Important',resolved=True,topic=t) for i,t in enumerate([
        '逐批尝试/结果持久化，失败关闭保存已完成历史与实际计数',
        '绑定CPU解释器/依赖锁/torch DLL并在执行与读取核对',
        '测试/审查版本与修复差异、最终验证源码摘要绑定',
        '合成资格消耗实际100ms预热随机流并恢复下一动作',
        '限定自然终末，拒绝成功终末奖励与截断并存'],1)],
    declined_rulings=['实际随机动态/学习收益交给有限执行，资格不是安全或成功保证',
        '代表逐轨迹复现需实际末次检查点，不预写通过','刚性模型外推留为模型限制',
        '指标/五份文档/封存由Task5按实际结果完成'],
    deferred_minor='400行数值probe未覆盖最多116000行检查点读取成本；预登记300秒超限则整轮停止，不补跑')
write(OUT/'review.json',record)
text='''# 唯一独立审查与一次修复

独立审查：GPT-6-astra/high、fresh-context、只读；0 Critical、5 Important、1 Minor。原审查对象摘要保存在reviewed_source.json。没有二次review；修复后0 Critical/0未解决Important是作者核实状态，不冒称审查员再次通过。

5项Important均经6个明确RED反例失败后修复；学习链整体30项GREEN。逐批尝试/完整结果fsync写journal、失败留history与实际count；学习runtime绑定；资格拒绝旧源码报告；数值预热实际抽样/保持并验证完整恢复；只接受自然完整终末。

审查还在纯内存中复现了预热抽样后旧合成恢复失败，以及“成功奖励+截断”被旧audit接受。修复期间捕获空bytes不能被torch weights_only读取，改为UTF-8文本journal；未放宽安全读取。

审查设置之外的实际动态安全性/成功率/收益交由登记pilot；真实代表复现、最终统计和文档按实测后补。模型对硬件/连续扰动的外推仍未证明。

暂缓Minor：最大116000行检查点的读取规模没有数值测量；300秒是预登记上限。超限即新问题、整轮停，不能追加时间或复跑。当前400行probe只能证明数值完整性。

修复前后摘要、差异和针对性证据见review.json、review_fix_red.txt、review_fix_green.txt；最终受检源码与结果由verification.json绑定。
'''
(OUT/'review.md').write_text(text,encoding='utf8')
with (OUT/'progress.md').open('a',encoding='utf8') as f:f.write('\nFinal review: 0 Critical/5 Important/1 Minor；5项确认后一次修复，6反例RED→30 GREEN，未二次审查。Minor读取规模暂缓；所有Declined依实际执行/Task5完成，不预写通过。资格尚未签发、实际动态/正式更新0。\n')
print('review/fix source binding written; changes='+str(len(delta)))
