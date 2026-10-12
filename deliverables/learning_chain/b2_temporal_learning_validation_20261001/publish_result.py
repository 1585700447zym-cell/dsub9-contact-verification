"""Terminal outcome and reconciliation of existing project/monthly documents."""
import json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=HERE/'result_analysis'
a=json.loads((OUT/'assessment.json').read_text(encoding='utf-8'));c=a['accounting'];rows=a['rows'];judgement=a['judgement']
S='deliverables/learning_chain/b2_temporal_learning_validation_20261001';M='../../learning_chain/b2_temporal_learning_validation_20261001'
texts=dict(limited_target_passed='候选在本次限定修复目标通过',method_not_resolved='本方法尚未解决已观察到的训练后失效问题',baseline_verification_blocked='共同起点未通过四点要求，本轮修复判定受阻',operational_verification_blocked='运行故障阻止完成修复判定')
outcome=texts[judgement];last=rows[-1] if rows else None
stages=('initial','C_online','C_final','C_restored','A_online','A_final')
counts={stage:dict(completed=sum(r['stage']==stage for r in rows),success=sum(r['success'] for r in rows if r['stage']==stage)) for stage in stages}
description=''
if last and last['guard_hit']:
    e=next(e for e in a['episodes'] if e['id']==last['id']);reasons=e['guard_facts']['contact_reasons']+e['guard_facts']['motion_reasons']+e['guard_facts']['invalid_reasons']
    description=f'最后回合{last["id"]}在{last["training_batches"]}批后触发{reasons}，周期峰值力{last["force_peak_N"]:.9f} N；回合有效并停稳后按任一保护规则停止。'
elif a['status']=='method_failed':description='候选固定四点或独立恢复未达到预登记要求，结束余量。'
elif a['status']=='complete':description='候选和对照均完成2500批及固定四点，候选独立进程恢复轨迹逐项一致。'
elif a['status']=='failed':description='本轮运行故障与策略任务失败分开记录，不能强行判定修复有效或无效。'
summary=f'**100ms预热学习验证已收口（2026-10-01）：** {outcome}。{description} 实际新增{c["new_dynamic_starts"]}/24动态、完成{c["formal_batches_completed"]}/5000正式批（C={c["updates"]["C"]["completed"]}、A={c["updates"]["A"]["completed"]}），累计动态{c["cumulative_dynamic"]}/92；余{c["unused_dynamic"]}次/{5000-c["formal_batches_attempted"]}批不执行、不结转。174项相关协议与源字节复核通过，离线审核物理/模型/优化0；原学习率、保护与成功门保持，自动跟踪PAUSED，B.2未完成。[结果与图]({S}/result_analysis/结果说明.md)、[机器审核]({S}/result_analysis/assessment.json)。'
report=f'# 100ms预热学习修复：有限验证结果\n\n2026-10-01。**{outcome}。**\n\n{description}\n\n用户授权直接做到验证结束。此轮按新增24动态/5000批上限执行，任何保护或故障完成停稳/留档后终止；未执行余量不补跑。保护停止是预登记验证终点，不是漏做后续测试。\n\n## 预先判据与实测\n\n'
report+='| 阶段 | 已完成/预定 | 成功/已完成 | 批次与作用 |\n|---|---:|---:|---|\n'
for stage in stages:
    count=counts[stage];purpose={'initial':'共同零更新固定评价','C_online':'100ms预热候选：500批间隔随机策略在线','C_final':'C2500固定策略','C_restored':'C2500独立进程完整恢复，同轨迹复验','A_online':'2ms预热对照：相同训练预算','A_final':'A2500固定策略'}[stage]
    report+=f'| {stage} | {count["completed"]}/4 | {count["success"]}/{count["completed"]} | {purpose} |\n'
report+='\nC必须完成2500批、固定四点4/4及独立恢复四点4/4/完整轨迹一致才通过限定目标。普通在线任务失败不删除；任一保护停止全轮。C固定评价普通失败在该四点评价收口后停止，不能补做回合挑结果。A在C复验之后运行，避免对照的早停遮蔽候选。\n\n'
if judgement=='method_not_resolved':
    report+='**修复效果未达标。** 100ms预热改变了数据采集持续性，但本次仍出现训练后保护或固定任务失败，因此它不足以解决已观察到的问题。不能据此断言预热完全无价值、critic的高估已消除、唯一根因已找到，或对照一定更好。\n\n'
elif judgement=='limited_target_passed':
    report+='**本次有限目标通过。** 候选保持了这四个已观察开发点的能力，并由另一进程完整恢复复验。结论不扩展为2500批之后稳定、多随机种子、独立泛化、任意状态价值准确或全部B.2验收。\n\n'
else:report+='本轮未取得完整修复效果判据，先将运行/起点故障与策略失效区别记录；不得把未完成的评价当作成功或失败的策略证据。\n\n'
report+='## 全部登记动态与未执行项\n\n| 回合 | 结果 | 批次 | 周期 | 周期峰值力 N | 末端XY μm |\n|---|---|---:|---:|---:|---:|\n'
byid={r['id']:r for r in rows};labels={'FULL_SUCCESS':'成功','TASK_FAILURE':'普通任务失败','CONTACT_GUARD':'接触保护失败','MOTION_VIOLATION':'运动保护失败'}
import validation_contract as C
for identity in C.attempts():
    r=byid.get(identity['id'])
    if r is None:
        attempt=next((x for x in json.loads((HERE/'run/ledger.json').read_text(encoding='utf-8'))['attempts'] if x['identity']['id']==identity['id']),None)
        report+=f'| {identity["id"]} | '+('故障尝试，预算已占用' if attempt else '未执行')+' | — | — | — | — |\n';continue
    receipt=Path(r['archive_path']).relative_to(HERE.relative_to(ROOT)).parent/'status.json'
    report+=f'| [{r["id"]}](../{receipt.as_posix()}) | {labels.get(r["task_outcome"],r["task_outcome"])} | {r["training_batches"]} | {r["cycles"]} | {r["force_peak_N"]:.9f} | {r["final_xy_error_m"]*1e6:.3f} |\n'
report+='\n![实际验证](validation_results.png)\n\n[图PDF](validation_results.pdf)。全部普通失败、保护失败与未执行项均保留。原始完整2ms轨迹、锁存子步保护、停止样本及任务原因见机器审核和各回合档案。\n\n'
if last:
    report+='![末个实测回合](last_episode_trace.png)\n\n[轨迹PDF](last_episode_trace.pdf)：实际位置/请求/载荷，不是反事实重跑。\n\n'
report+='## 数据、起点与完整状态\n\n'
report+='此前8次预检仍保持 `training_admitted=false`、原receipt入池0。本阶段以当前明确授权重新审核采样、物理停稳、资格及整回合连续性，创建单独当前清单/receipt；不重写历史权限、不追认旧信用，也不使用旧失败策略评价或独立测试。两组分别使用A=2ms/C=100ms新预热，共同零网络/空Adam/温度/Torch随机状态；不导入旧origin的replay或500批抽样计划。\n\n'
report+='两个分组使用同抽样算法和初始种子。轨迹和数据长度随处理不同，所以抽样索引不宣称逐样本相同。四个当前预热产生500批信用，每一新完整在线回合增加500；正式策略每2ms重新决策，100ms仅用于预热。actor/critic/温度学习率均3e−4，完整物理、保护、奖励、观测、动作尺度与成功门不改。\n\n'
report+='| 完整检查点 | 批次 | 入池回合 | 经验行 | 审核 |\n|---|---:|---:|---:|---|\n'
for checkpoint in a['checkpoints']:
    rel=Path(checkpoint['path']).relative_to(HERE.relative_to(ROOT));report+=f'| [{rel.name}](../{rel.as_posix()}/manifest.json) | {checkpoint["batches"]} | {checkpoint["episodes"]} | {checkpoint["replay_rows"]} | 网络/Adam/温度/索引/经验/抽样/Torch随机状态完整 |\n'
report+='\n每500批后、下一在线回合前保存完整状态，失败不会丢失触发策略。工作/恢复进程由登记父进程监督；已确认死亡关闭账本，停止不确定则保留保守预留。保护后仅执行必要零动作停稳，禁止继续推理/学习或新回合。\n\n'
report+='## 成本、实现与限制\n\n'
report+=f'新增动态{c["new_dynamic_starts"]}，已完成{len(rows)}；累计{c["cumulative_dynamic"]}/92。正式批尝试/完成{c["formal_batches_attempted"]}/{c["formal_batches_completed"]}，实际Adam调用{a["actual_costs"]["optimizer_steps_attempted"]}，模型模块调用{a["actual_costs"]["model_module_calls_attempted"]}；完整物理子步{a["actual_costs"]["physical_substeps_attempted"]}。控制周期确认{c["control_cycles_confirmed"]}、保守预留{c["control_cycles_reserved"]}，两种成本分别报告。新验证余{c["unused_dynamic"]}动态/{5000-c["formal_batches_attempted"]}批及旧余2/7/19、2000批均不消费。\n\n'
report+='174项相关协议通过；独立审查指出换行摘要、提前停止检查点、确认进程死亡后的账本三个问题，均经一次先失败后通过修复，并补保护尾段禁推理反例。离线重新验证全部完整回合、来源字节、训练信用/抽样轨迹和检查点，实际物理/网络/优化均0。[入口审查](../review.md)、[离线机器证据](assessment.json)。协议和数据存取修复成立，不替代策略效果验收。\n\n'
next_text=('本次限定目标通过，下一研究阶段再设计多种子/独立开发评价及公平消融，未经新授权不扩展。' if judgement=='limited_target_passed' else
    ('此候选在预先终点未解决问题；保持停止。下一项依据完整触发策略与轨迹离线定位持续偏置/目标拟合等机制，形成新单变量方案后再决定新预算，不盲目加训或放宽保护。' if judgement=='method_not_resolved' else '先依据本轮故障档案修复运行/起点问题，保留已消耗预算；未经新授权不重跑。'))
report+='## 后续边界\n\n'+next_text+' B.2未完成，自动跟踪保持PAUSED，独立测试不参与调参。\n'
with (OUT/'结果说明.md').open('x',encoding='utf-8') as f:f.write(report)
def replace_latest(t,text):return re.sub(r'^\*\*100ms预热学习验证已启动（2026-10-01）：\*\*.*$',text,t,count=1,flags=re.M)
p=ROOT/'项目进度跟踪.md';t=replace_latest(p.read_text(encoding='utf-8'),summary)
t=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；100ms预热学习验证收口 | [实际结果]({S}/result_analysis/结果说明.md)、[完整审核]({S}/result_analysis/assessment.json)；新增{c["new_dynamic_starts"]}动态/{c["formal_batches_completed"]}批 | {outcome}；独立泛化和全部B.2证据仍缺 |',t,count=1,flags=re.M)
t=re.sub(r'^\| 6 普通残差SAC \|.*$',f'| 6 普通残差SAC | 100ms预热候选完成本次有界学习验证：{outcome}；C{c["updates"]["C"]["completed"]}批/A{c["updates"]["A"]["completed"]}批，保留全部失败和未执行，B.2未完成 |',t,count=1,flags=re.M)
t=re.sub(r'^\| 修复归因与验收范围 \|.*$',f'| 修复归因与验收范围 | {outcome}；任一保护终止、完整状态保存，未扩大外推 | {next_text} [实际证据]({S}/result_analysis/assessment.json) |',t,count=1,flags=re.M)
t=re.sub(r'^\| 原项目全量测试 \|.*$',f'| 原项目全量测试 | 本阶段174相关协议、所有实测档案与完整检查点重新审核通过 | 非项目全量测试；{outcome}，不能把协议通过当学习收益 |',t,count=1,flags=re.M)
t=re.sub(r'^\| 训练状态恢复 \|.*$',f'| 训练状态恢复 | 本阶段每500批前置保存完整不可变状态，离线结构/来源/信用/RNG/Adam复核；C独立动态恢复完成{counts["C_restored"]["completed"]}/4 | 仅本轮实际执行范围成立，未执行恢复不冒称通过；失败不重试/预算不重置 |',t,count=1,flags=re.M)
t=re.sub(r'^\| 熵项与奖励尺度 \|.*$',f'| 熵项与奖励尺度 | 本阶段新增{c["formal_batches_completed"]}正式批，学习率/熵设置/奖励保持；旧诊断保留历史日期 | {outcome}；未做额外价值推理，不冒称critic高估消除或唯一根因确定 |',t,count=1,flags=re.M)
t=re.sub(r'## 下一项交付\n.*?(?=\n## )','## 下一项交付\n\n'+next_text+f' 新余{c["unused_dynamic"]}动态/{5000-c["formal_batches_attempted"]}批及旧余不结转；PAUSED，独立测试不使用。\n',t,count=1,flags=re.S)
t=t.replace('## 追加式阶段记录\n\n','## 追加式阶段记录\n\n### 2026-10-01 B.2｜100ms预热有限学习验证收口\n\n'+summary+'\n\n- 174相关协议、独立入口审查与3项反例修复通过；当前授权/来源封存，旧未提交修改与资产保留。\n- 真实结果按预先门收口，全部已完成回合、成本、抽样信用和完整检查点重新审核；离线新增实际计算0。\n- 更新同一10月滚动月报的综合摘要/数字/负结果/图和讲稿；未冒称B.2验收。\n\n',1);p.write_text(t,encoding='utf-8')
p=ROOT/'项目当前入口.md';p.write_text(replace_latest(p.read_text(encoding='utf-8'),summary),encoding='utf-8')
p=ROOT/'项目交付总览.md';t=replace_latest(p.read_text(encoding='utf-8'),summary)
t=t.replace('### B.2｜100ms预热学习有限验证（2026-10-01）','### B.2｜100ms预热学习有限验证收口（2026-10-01）',1)
t=re.sub(r'^\| 当前100ms预热学习验证 \|.*$',f'| 最新100ms预热学习验证结果 | [结果与图]({S}/result_analysis/结果说明.md)、[机器审核]({S}/result_analysis/assessment.json) | {outcome}；新增{c["new_dynamic_starts"]}动态/{c["formal_batches_completed"]}批，余量关闭，B.2未完成 |',t,count=1,flags=re.M)
t=t.replace(summary,summary+f'\n\n使用：只读结果、原始账本/档案与检查点；独占执行目录不可再次运行。[完整状态索引]({S}/result_analysis/assessment.json)。{next_text}',1)
t+='\n2026-10-01｜100ms预热有限学习验证收口：结果和同一10月月报已整合，旧资料与全部未提交成果保留。\n';p.write_text(t,encoding='utf-8')
p=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';t=replace_latest(p.read_text(encoding='utf-8'),summary.replace(S,M))
t=re.sub(r'^\| 100ms预热学习验证 \|.*$',f'| 100ms预热学习验证 | 新增{c["new_dynamic_starts"]}动态、{c["formal_batches_completed"]}批；C{c["updates"]["C"]["completed"]}/A{c["updates"]["A"]["completed"]} | {outcome}；余{c["unused_dynamic"]}动态/{5000-c["formal_batches_attempted"]}批不执行，累计{c["cumulative_dynamic"]}/92 |',t,count=1,flags=re.M)
t=t.replace('## 三、负结果与限制\n\n','## 三、负结果与限制\n\n'+outcome+'。'+description+' 本轮没有为追求完成次数补回合、追加更新或改保护。即使限定目标通过，也不能外推为独立泛化、唯一机制或完整B.2。\n\n',1)
t=t.replace('<a id="figures"></a>\n\n',f'<a id="figures"></a>\n\n![学习验证实际结果]({M}/result_analysis/validation_results.png)\n\n[PNG]({M}/result_analysis/validation_results.png)/[PDF]({M}/result_analysis/validation_results.pdf)：所有24个登记回合及未执行项，保护和普通任务失败区分。\n\n![末个实际回合]({M}/result_analysis/last_episode_trace.png)\n\n[PNG]({M}/result_analysis/last_episode_trace.png)/[PDF]({M}/result_analysis/last_episode_trace.pdf)：位置、残差与载荷完整归档轨迹，不是重跑。\n\n本轮讲稿：“我们保持原学习率和保护，只改变预热时间持续性。相关协议174项通过后实际验证，新增{c["new_dynamic_starts"]}回合、{c["formal_batches_completed"]}批。{outcome}。{description} 全部失败、完整检查点与余量关闭记录保留，没有把程序检查通过当作学习收益。”\n\n',1)
t=re.sub(r'## 五、下一项\n.*?(?=## 六、来源记录)','## 五、下一项\n\n'+next_text+f' 本轮新增{c["new_dynamic_starts"]}动态/{c["formal_batches_completed"]}批；余量和旧余不结转，PAUSED，B.2未完成。\n\n',t,count=1,flags=re.S)
t+='\n2026-10-01｜100ms预热有限学习验证终点：'+summary.replace(S,M)+'\n';p.write_text(t,encoding='utf-8')
p=HERE/'progress.md';t=p.read_text(encoding='utf-8');t+=f'\nTask3 complete as registered terminal validation: status={a["status"]}, judgement={judgement}, new dynamics={c["new_dynamic_starts"]}, batches={c["formal_batches_completed"]}; unused={c["unused_dynamic"]}/{5000-c["formal_batches_attempted"]} closed, not reused. Full offline result/state audit calls0; rolling project and sameOctober evidence updated. B.2 remains incomplete.\n';p.write_text(t,encoding='utf-8')
print(json.dumps(dict(judgement=judgement,documents_updated=4,new_dynamic=c['new_dynamic_starts'],batches=c['formal_batches_completed']),ensure_ascii=False))
