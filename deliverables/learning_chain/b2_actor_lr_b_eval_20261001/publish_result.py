"""Publish independently audited results and update the same rolling documents."""
import json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=HERE/'result_analysis'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
a=read(OUT/'assessment.json');cost=a['accounting'];rows=a['rows'];n=len(rows);success=a['successful_points']
S='deliverables/learning_chain/b2_actor_lr_b_eval_20261001';P='deliverables/learning_chain/b2_actor_lr_execution_20260930'
complete=a['status']=='complete';stopped='完成四点评价' if complete else '保护后受控停止'
initial=read(ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/run/initial/results.json')
prior=read(ROOT/P/'run/evaluation_A/results.json')
names=['x_pos_100','x_neg_100','y_pos_100','y_neg_100'];titles=['正X100','负X100','正Y100','负Y100']
outcomes={'FULL_SUCCESS':'成功','TASK_FAILURE':'普通任务失败','CONTACT_GUARD':'力保护失败'}
def by_name(items):return {r['case']:r for r in items}
imap,amap,bmap=map(by_name,(initial,prior,rows))
outcome_table='| 开发点（μm，零倾角） | 初始策略（历史） | A500（上一轮） | B500（本轮） |\n|---|---|---|---|\n'
for name,title in zip(names,titles):
    columns=[outcomes[m[name]['task_outcome']] if name in m else '未执行' for m in (imap,amap,bmap)]
    outcome_table+='| '+title+' | '+' | '.join(columns)+' |\n'
metric_table='| B工况 | 峰值力 N | 终末XY μm | 周期 | 停止原因 |\n|---|---:|---:|---:|---|\n'
behaviors=by_name(a['behavior'])
for r in rows:
    metric_table+=f'| {r["case"]} | {r["force_peak_N"]:.9f} | {r["final_xy_error_m"]*1e6:.3f} | {r["cycles"]} | {behaviors[r["case"]]["final_reason"]} |\n'
all_valid=all(r['simulation_valid'] and r['physical_stopped'] for r in rows)
required_met=a['retains_initial_four_successes']
verdict='保持了历史初始四点成功数，但未证明学习收益' if required_met else '未保持历史初始四点全成功，单独降低actor学习率未通过本轮修复目标'
bfirst=rows[0];afirst=prior[0];details=behaviors['x_pos_100'];end=details['final_position_m']
direction_table='| 初始偏差 | 活动周期X负请求占比 | 平均X请求 | 最终X μm | 结果 |\n|---|---:|---:|---:|---|\n'
for r in rows:
    b=behaviors[r['case']]
    direction_table+=f'| {r["case"]} | {b["active_x_negative_fraction"]*100:.2f}% | {b["active_x_mean"]:.6f} | {b["final_position_m"][0]*1e6:.3f} | {outcomes[r["task_outcome"]]} |\n'
summary=f'**冻结B500独立评价已收口（2026-10-01）：** 本轮{stopped}，实际{n}/4新动态、训练0，{success}/{n}个已执行点成功；'+('四点均已评价。' if complete else f'其余{4-n}点未执行。')+f'{verdict}。正X峰值力降至{bfirst["force_peak_N"]:.8f} N，但终末XY误差{bfirst["final_xy_error_m"]*1e6:.1f} μm高于50 μm；'+f'冻结B从+100 μm越过中心，最终X={end[0]*1e6:.1f} μm/Y={end[1]*1e6:.1f} μm，出现持续同向修正后的过冲。'+f'[逐点结果与两图]({S}/result_analysis/结果说明.md)、[独立审核]({S}/result_analysis/assessment.json)。{n}/{n}有效停稳，评价学习状态不变、经验入池0；累计动态{cost["cumulative_dynamic"]}/62，余本轮{cost["unused_new_dynamic"]}与旧7及19/2000不追加，自动跟踪PAUSED，B.2未完成。'
report=f'''# 冻结B500独立评价结果

2026-10-01。用户确认“完成独立入口适配、协议验证，再直接执行最多4次B评价并收口”后回复“继续”。新账本/授权独立，原冻结A/B轮保持stopped。原工作树和全部未提交修改保留，物理/奖励/成功及保护阈值保持。

**{verdict}。** 本轮{stopped}，实际{n}/4动态，已执行{success}/{n}成功，训练0。{'完整四点已执行。' if complete else '未执行点：'+', '.join(a['unexecuted_points'])+'；不得记成已测失败或成功。'} B.2未完成。

## 逐点成绩

{outcome_table}
初始四点是同一既有版本下的历史上下文，未在本轮新增重放。A只有正X点，其他点未评价，不能将其填成0/4或构造完整配对成功率。完整成功数保持要求为B的4/4。

{metric_table}
本轮完成点全部有效且实际停稳，所有原始轨迹和失败保留。没有用载荷下降替代成功指标，也未把较早失败时间解释为效率提升。

![逐点结果](development_results.png)

## 正X点的直接行为证据

与A同点相比，B周期峰值力从{afirst['force_peak_N']:.9f} N降至{bfirst['force_peak_N']:.9f} N；A力保护失败，B普通任务失败。B到达目标平面后未满足姿态/位置收敛条件，原始终止原因为`{details['final_reason']}`。

B初始X=+100 μm，第一次越过中心发生在{details['first_x_center_crossing_s']:.3f}s；最后位于X={end[0]*1e6:.3f} μm、Y={end[1]*1e6:.3f} μm，合成XY={bfirst['final_xy_error_m']*1e6:.3f} μm，超过50 μm。最后有权限周期的X请求为{details['last_active_raw_action'][0]:.6f}，活动周期X负向占比{details['active_x_negative_fraction']*100:.2f}%，均值{details['active_x_mean']:.6f}。这些是保存轨迹中的动作和运动事实，不是新模型评分或反事实回放。

该点在横向越过中心后继续同向修正，最终因几何条件未收敛而失败。冻结数据诊断中B的X负偏在真实轨迹中也有表现；这加强了持续横向偏置/末段收敛问题的证据，但尚未证明唯一学习原因。不能因此改写原critic价值核对，也不能断言某个替代动作一定能救回。

## 正负X对照暴露的共同问题

{direction_table}
初始偏差的符号相反，两个实测点的活动周期X残差请求却始终为负。负X点从−100 μm开始，最终X约−115.8 μm，XY约115.8 μm，并触发0.025001521 N的力保护。它没有出现纠偏成功；这比单看正X载荷下降更能暴露持续同向请求的问题。动作请求不是独立位移命令，运动还受基线控制与接触约束影响，因此这些证据仍不足以将所有失败唯一归因于一个学习参数。

![正X轨迹](x_positive_trajectories.png)

虚线50 μm为原成功横向容差，25 mN为原力保护线。X请求只画有权限周期，停止后没有主动残差；竖点线是各策略停止命令时刻。力是控制周期峰值，终末误差是原始位置复算；非安全概率图。

## 实现、成本及核验

- 独立适配仅新增阶段内代码，原1011绑定输入保持；149项相关协议全过，实际前向/Adam/物理0；独立源码审查与53项封存输入核对通过。
- 完整B500检查点恢复预检通过，四类优化计数均500；本轮不更新参数，不重新训练或挑选中间检查点。
- 新动态{n}/4，累计{cost['cumulative_dynamic']}/62；保守预约actor状态{cost['actor_states_reserved']}，完整确认实际状态{cost['actor_states_confirmed']}，上限52000。每点最多13000控制周期，含异常停止尾段。
- 正式/合成训练、额外静态诊断、critic评分及独立测试0；评价经验入池0，完整学习状态不变。
- 独立离线复算{n}条完整档案的结果、奖励、动作映射、保护、两套停稳窗口和身份摘要。复核阶段新增前向/优化/物理0；4149历史封存、929旧源码原字节、22父轮运行文件和12父轮交付文件保持。
- 退出{'0为本轮有限评价完整完成' if complete else '20为保护后的受控停止'}；这不等同于修复成功或B.2验收。未自动重试，自动跟踪PAUSED；本轮余{cost['unused_new_dynamic']}和旧7及19/2000不结转。
- 通用进程监督记录将非零退出码20标成`failed`；本轮专用退出分类与账本均确认为保护后的`controlled_stop`。故障日志为空，两条原始档案均有效停稳，不能把该通用标签误报成程序崩溃。

## 下一项

不再将“仅降actor学习率”视为本问题已证实有效的修复。后续优先围绕横向持续偏置、越过中心后的修正方向及接近目标深度时的收敛设计小范围候选，先明确机制与公平基线；不据局部载荷改善扩展训练。改变残差约束、动作更新节奏或终止/奖励规则均属于新方案，需要说明影响和单独预算，当前不实施。原共同成功/保护阈值保持。

本阶段实际有限评价及证据收口完成，策略效果未通过预定保持能力目标，B.2仍未完成；按项目约定报告后暂停。

## 原始证据与导出

- [独立机器审核](assessment.json)、[最终运行结果](../run/results.json)、[实际成本](../run/accounting.json)、[逐次账本](../run/ledger.json)、[尝试收据](../run/attempts.json)
- [新授权](../authorization.json)、[外部摘要](../execution_pins.json)、[完整恢复](../restoration_preflight.json)、[149协议](../related_green_results.json)、[独立审查](../review.md)、[最终退出语义](../exit_classification.json)
- [逐点图PDF](development_results.pdf)、[正X轨迹PDF](x_positive_trajectories.pdf)
'''
with (OUT/'结果说明.md').open('x',encoding='utf-8') as stream:stream.write(report)
p=ROOT/'项目进度跟踪.md';t=p.read_text(encoding='utf-8')
t=re.sub(r'^\*\*冻结B单独评价已获批并启动（2026-10-01）.*$',summary,t,count=1,flags=re.M)
t=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；冻结B独立评价已收口，修复目标未达 | [结果与两图]({S}/result_analysis/结果说明.md)、[独立审核]({S}/result_analysis/assessment.json)；{success}/{n}个已执行点成功、{4-n}未执行，{n}/{n}有效停稳 | 未保持初始4/4，不能宣称降率修复；原2500批在线、最终/恢复/独立研究验收仍缺；旧剩额不执行 |',t,count=1,flags=re.M)
t=re.sub(r'^\| 6 普通残差SAC \|.*$',f'| 6 普通残差SAC | 固定B500单独评价已收口，{success}/{n}已执行点成功、{4-n}点未执行；本轮{n}动态/0训练，未保持初始4/4；正X载荷下降但横向过冲仍失败，修复目标未达，B.2未完成 |',t,count=1,flags=re.M)
t=re.sub(r'^\| 8 正式证据与展示 \|.*$',f'| 8 正式证据与展示 | 新增B逐点结果与正X实际轨迹两图（PNG/PDF）、{n}完整原始档案和预算审核；研究级恢复/独立证据未全，95μm独立点与原64测试不取用 |',t,count=1,flags=re.M)
t=re.sub(r'^\| 修复归因与验收范围 \|.*$','| 修复归因与验收范围 | B实际正X从+100μm越过中心停至X约−72.4μm、XY75.1μm，持续X负请求；降率未保持原初始4/4 | 围绕横向持续偏置/末段收敛提出新机制和有限验证；不以载荷下降当成功、不推断唯一学习根因 |',t,count=1,flags=re.M)
t=re.sub(r'^\| 单变量与有限对照可比性 \|.*$',f'| 单变量与有限对照可比性 | A500精确复现/B500冻结保持；B单独新授权{n}动态/0训练完成收口，父轮账本未解锁 | A只有正X点，其他A点不能填失败构造完整配对；初始4/4是历史上下文，独立泛化未验证 |',t,count=1,flags=re.M)
t=re.sub(r'## 下一项交付\n.*?(?=## 追加式阶段记录)',f'## 下一项交付\n\n[冻结B单独评价]({S}/result_analysis/结果说明.md)已收口，当前暂停汇报。本轮{n}新动态/0训练，累计{cost["cumulative_dynamic"]}，余本轮{cost["unused_new_dynamic"]}及旧7、19/2000不追加，自动跟踪PAUSED。\n\n后续优先针对横向持续偏置、越过中心后的修正方向和接近目标深度时的收敛设计新候选；先明确机制、共同基线与有限预算，不继续把仅降学习率当已验证修复。改变残差约束/更新节奏/终止或奖励须另行沟通，当前不实施；独立测试不参与调参。\n\n',t,count=1,flags=re.S)
t=t.replace('## 追加式阶段记录\n\n',f'## 追加式阶段记录\n\n### 2026-10-01 B.2｜冻结B独立实际评价收口\n\n{summary}\n\n- 用户确认的最多4动态/0训练范围内完成；149协议与完整恢复预检通过，独立审查/最终53输入核对通过。每点完整归档、预算独立、停止规则保持。\n- [机器审核]({S}/result_analysis/assessment.json)逐点复算通过；入池0、学习状态不变，审核新增计算0。当前1011源、4149历史封存、929原源字节及父轮资料保持。\n- 两图及原始数据真实保留正负结果；同一总览/10月月报已更新，阶段收口后暂停，B.2未完成。\n\n',1)
p.write_text(t,encoding='utf-8')
p=ROOT/'项目交付总览.md';t=p.read_text(encoding='utf-8')
t=re.sub(r'^\| 已冻结B单独评价实际执行（2026-10-01）.*$',f'| 冻结B独立评价结果（2026-10-01） | [结果与两图]({S}/result_analysis/结果说明.md)、[独立审核]({S}/result_analysis/assessment.json) | {success}/{n}已执行点成功、{4-n}未执行，{n}新动态/0训练；未保持初始4/4，正X横向过冲，降率未通过修复目标；有效停稳和历史字节保持 |',t,count=1,flags=re.M)
t=t.replace('## 基线与接口交付\n\n',f'## 基线与接口交付\n\n### B.2最新实际结果｜冻结B500独立评价（2026-10-01）\n\n- **产出与使用：** [逐点结果与两图PNG/PDF]({S}/result_analysis/结果说明.md)、[完整审核]({S}/result_analysis/assessment.json)、[成本]({S}/run/accounting.json)；只读已封存记录，不重跑独占入口。\n- **结果：** {stopped}，{success}/{n}已执行点成功、{4-n}未执行、{n}/{n}有效停稳。正X力较低但末端75.1μm超50μm，持续负X修正产生过冲。\n- **限制：** 未保持初始4/4，不等于学习修复或B.2完成；A只有一个实测点，缺完整配对。新训练0，累计动态{cost["cumulative_dynamic"]}，余本轮{cost["unused_new_dynamic"]}和旧剩额不结转，PAUSED。\n\n',1)
p.write_text(t,encoding='utf-8')
p=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';t=p.read_text(encoding='utf-8');M='../../learning_chain/b2_actor_lr_b_eval_20261001'
t=re.sub(r'^\*\*冻结B单独评价已获批并启动（2026-10-01）.*$',summary.replace(S,M),t,count=1,flags=re.M)
t=re.sub(r'^\| 独立B评价启动 \|.*$',f'| 独立B实际评价结果 | {success}/{n}已执行点成功、{4-n}未执行，{n}/{n}有效停稳 | {n}/4新动态、训练0；累计{cost["cumulative_dynamic"]}/62，未保持初始4/4 |',t,count=1,flags=re.M)
t=t.replace('单独B评价现已获批、适配/协议/完整恢复通过并运行；尚无最终物理结果，不能把实现通过计为修复收益。',f'单独B实际评价已收口，{success}/{n}已执行点成功、{4-n}点未执行，未保持初始四点全成功。正X载荷下降但持续负X修正造成越过中心后的75.1μm终末误差，超过50μm；不能把更低载荷或更早失败称为性能修复。',1)
figure_block=f'\n新增[逐点结果PNG]({M}/result_analysis/development_results.png)/[PDF]({M}/result_analysis/development_results.pdf)与[正X轨迹PNG]({M}/result_analysis/x_positive_trajectories.png)/[PDF]({M}/result_analysis/x_positive_trajectories.pdf)，区分成功/普通失败/保护失败/未执行；初始与A为历史上下文，B为本轮实测。\n\n本阶段讲稿：“冻结B独立评价实际完成{n}点，成功{success}点，未执行{4-n}点。降低actor学习率改善了正X接触载荷，但持续同向纠偏产生过冲，未满足初始四点全成功的保持要求。下一项需要针对横向偏置与接近完成时的收敛提出有针对性的候选，现阶段不宣称修复或B.2完成。”\n'
t=t.replace('## 五、下一项\n',figure_block+'\n## 五、下一项\n',1)
t=re.sub(r'## 五、下一项\n.*?(?=## 六、来源记录)',f'## 五、下一项\n\n本阶段收口后暂停。优先围绕横向持续偏置和末段收敛设计新候选，先明确机制、共同基线和有限预算；不盲目追加学习率扫描，不放宽保护或成功阈值。本轮余{cost["unused_new_dynamic"]}及旧7、19/2000不结转，PAUSED，独立测试未使用。\n\n',t,count=1,flags=re.S)
t+='\n2026-10-01独立B实际评价收口：'+summary.replace(S,M)+'\n'
p.write_text(t,encoding='utf-8')
print(json.dumps(dict(status=a['status'],success=success,completed=n,unexecuted=4-n,documents_updated=3),ensure_ascii=False))
