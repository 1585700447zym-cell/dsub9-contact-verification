"""Publish audited actual evidence and reconcile the same rolling documents."""
import json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=HERE/'result_analysis'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
a=read(OUT/'assessment.json');cost=a['accounting'];rows=a['rows'];n=len(rows);success=a['success'];g=a['gates']
S='deliverables/learning_chain/b2_temporal_warmup_execution_20261001';M='../../learning_chain/b2_temporal_warmup_execution_20261001'
byid={r['id']:r for r in rows};episode={x['id']:x for x in a['episodes']}
labels={'FULL_SUCCESS':'成功','TASK_FAILURE':'普通任务失败','CONTACT_GUARD':'接触保护失败','MOTION_VIOLATION':'运动保护失败'}
status={'complete':'完成8回合','stopped':'保护后受控停止','failed':'运行异常后停止'}[a['status']]
passed=g['candidate_collection_preflight_passed']
gate_text='采集机制预检通过，但不授予训练或证明策略修复' if passed else ('完整8回合门未满足，覆盖准入不判通过' if not g['coverage_evaluated'] else '完整回合通过，但双向持续请求或接触命令作用门未达标')
summary=f'**100ms预热配对预检已收口（2026-10-01）：** {status}，实际{cost["new_dynamic_starts"]}/8新动态、完成{n}回合、成功{success}，训练/网络前向/经验入池均0。{gate_text}。[实际结果与图]({S}/result_analysis/结果说明.md)、[独立离线核验]({S}/result_analysis/assessment.json)。{n}/{n}完成回合有效且停稳；累计动态{cost["cumulative_dynamic"]}/68，本轮未执行{cost["unused_new_dynamic"]}次和旧余2/7/19、2000批不结转。103协议通过、入口3处审查问题已修复，历史字节保持，自动跟踪PAUSED，B.2未完成。'
report=f'# 100 ms时间相关预热：真实配对预检结果\n\n2026-10-01。{status}。用户批准最多8次新动态、0训练和0网络前向；保护/故障停止余量，不自动重试。\n\n{summary.replace(S,"..")}\n\n## 全部预定回合\n\n| 回合 | 结果 | 周期 | 抽样向量数 | 周期峰值力 N | 最终XY误差 μm |\n|---|---|---:|---:|---:|---:|\n'
for name in ('x_pos_100_A','x_pos_100_C','x_neg_100_A','x_neg_100_C','y_pos_100_A','y_pos_100_C','y_neg_100_A','y_neg_100_C'):
    if name not in byid:report+=f'| {name} | 未执行 | — | — | — | — |\n';continue
    r=byid[name];e=episode[name]
    report+=f'| [{name}](../run/episodes/{name}/status.json) | {labels.get(r["task_outcome"],r["task_outcome"])} | {r["cycles"]} | {r["draw_count"]} | {r["force_peak_N"]:.9f} | {e["final_xy_error_m"]*1e6:.3f} |\n'
report+='\n两臂使用完整的新入口，同方向初始PCG64状态相同；A=2 ms独立抽样，C=100 ms保持。随机流消费随保持长度和轨迹分叉，不能宣称逐样本配对，也不能将旧预热作为新A臂。停止审核及原始2 ms转移均保存；禁用权限时动作归零且不抽样。\n\n'
if n==8:
    arm_success={arm:sum(r['success'] for r in rows if r['arm']==arm) for arm in ('A','C')}
    report+=f'**新A对照{arm_success["A"]}/4成功，C候选{arm_success["C"]}/4成功。** '
    if 'x_neg_100_C' in byid and not byid['x_neg_100_C']['success']:
        e=episode['x_neg_100_C'];r=byid['x_neg_100_C']
        report+=f'C负X回合以 `{e["final_reason"]}` 结束，末端XY误差{e["final_xy_error_m"]*1e6:.3f} μm超50 μm成功门；峰值力{r["force_peak_N"]:.9f} N低于0.025 N，不是力保护或仿真无效。'
    report+=' 这不是学习策略评价，不能将随机预热成功率当作训练收益，也没有证据称C优于A。\n\n![负X失败配对](negative_x_comparison.png)\n\n[负X图PDF](negative_x_comparison.pdf)。\n\n'
if rows and rows[-1]['guard_hit']:
    last=rows[-1];e=episode[last['id']]
    report+=f'最后回合 **{last["id"]}** 的锁存保护原因：{e["guard_facts"]["contact_reasons"]+e["guard_facts"]["motion_reasons"]}；最终原因 `{e["final_reason"]}`。按照预登记任一保护规则停止，不补齐剩余回合。该回合经过真实停止审核，有效失败未被删除或改为无效仿真。\n\n'
report+='## 请求持续性与预登记门\n\n| 臂/轴 | 完整100 ms窗口数 | 窗口均值RMS | 正向≥0.8窗口数 | 负向≤−0.8窗口数 |\n|---|---:|---:|---:|---:|\n'
for arm in ('A','C'):
    for axis,r in zip(('X','Y','roll','pitch'),a['pooled_request_windows'][arm]['0.1']['axes']):
        rms='—' if r['rms_mean'] is None else f'{r["rms_mean"]:.5f}'
        report+=f'| {arm}/{axis} | {r["count"]} | {rms} | {r["positive_threshold_count"]} | {r["negative_threshold_count"]} |\n'
report+=f'\n预登记门：**{gate_text}**。只在8份全部有效停稳且无保护后，才将C四轴双向≥0.8请求和接触有权限窗口中X/Y双向≥1 μm/s命令有效改变量用于准入。已执行子集的统计只作描述；20/100/400 ms统计、事件、首次保存接触、真实运动和参考领先都见机器审核。没有因结果临时放宽阈值。\n\n'
report+='![实际预检结果](preflight_results.png)\n\n[可导出PDF](preflight_results.pdf)。图包括全部未执行项；请求持续性不是状态空间覆盖率、物理反事实或策略收益。\n\n## 实现修复、核验和局限\n\n'
report+=f'103项相关协议全部通过，实际调用0。独立审查发现的子步forward误当初始化、故障尾段缺逐周期监督、尾段结果丢失均经先失败后通过的反例修复；[审查记录](../review.md)。本轮实际物理子步{a["physics_calls"]["total_substeps_attempted"]}，离线复核新增物理/模型/优化0；完整随机状态恢复、采样转录、物理停稳、指标和账本逐项重算一致。每次启动前预留13000总周期，正常完成实际消耗与保守预留分别报告。\n\n'
report+='预检只检验新数据采集机制，没有加载或更新actor/critic。失败不证明“持续动作一定错误”或已确认唯一学习根因。旧学习率候选的负结果和价值高估证据保持；共同物理、成功阈值、保护、奖励、观测及训练合同没有放宽。未使用独立测试。\n\n'
report+='## 下一步边界\n\n'
report+=('采集机制预检达到预先条件。后续学习比较仍须另行冻结共同零更新起点、两套新预热、相同网络种子与批数，以及完整固定评价；本轮不自动训练。' if passed else '本候选尚未取得采集机制准入。保持停止，先依据本次完整档案定位保护发生时的持续请求、命令限幅和接触反馈；不要追加回合、延长保持或盲目训练。任何下一候选需先形成具体机制与新的有限预算。')+'\n'
with (OUT/'结果说明.md').open('x',encoding='utf-8') as f:f.write(report)
def replace_latest(t,text):
    return re.sub(r'^\*\*100ms预热配对预检已准入并开始执行（2026-10-01）：\*\*.*$',text,t,count=1,flags=re.M)
p=ROOT/'项目进度跟踪.md';t=replace_latest(p.read_text(encoding='utf-8'),summary)
t=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；100ms预热预检{status} | [真实预检与图]({S}/result_analysis/结果说明.md)、[审核]({S}/result_analysis/assessment.json)；{n}完成/{cost["unused_new_dynamic"]}未执行，训练0 | {gate_text}；学习收益与最终/恢复/独立研究证据仍缺 |',t,count=1,flags=re.M)
t=re.sub(r'^\| 6 普通残差SAC \|.*$',f'| 6 普通残差SAC | 降率未保持初始4/4；100ms采样入口已接通并完成本次有界预检，{n}回合完成、训练0；{gate_text}，B.2未完成 |',t,count=1,flags=re.M)
next_text=('本次预检通过，但后续共同起点学习对照未签发预算，不自动训练。' if passed else '当前候选预检未取得准入，保留全部负结果；下一项先离线分析本次保护/覆盖不足并提出具体候选，未经新预算不重跑或训练。')
t=re.sub(r'## 下一项交付\n.*?(?=\n## )','## 下一项交付\n\n'+next_text+f' 本轮未执行{cost["unused_new_dynamic"]}和旧余2/7/19及2000批不结转；PAUSED，独立测试不参与调参。\n',t,count=1,flags=re.S)
t=t.replace('## 追加式阶段记录\n\n',f'## 追加式阶段记录\n\n### 2026-10-01 B.2｜100ms预热配对真实预检收口\n\n{summary}\n\n- 入口103协议、独立只读审查及3项反例修复通过，资格和预算封存；旧源/资产保持。\n- 原始2ms轨迹、完整PCG/保持状态、全部尝试、真实双重停稳及保守预算逐项复核；新增审核计算0。\n- {gate_text}；图与同一10月月报已更新。没有训练、入池或B.2验收。\n\n',1)
t=re.sub(r'^\| 修复归因与验收范围 \|.*$',f'| 修复归因与验收范围 | 新100ms配对预检{status}，{n}完成/训练0；{gate_text} | {next_text} 不以请求持续性冒称物理覆盖或策略修复；[真实证据]({S}/result_analysis/assessment.json) |',t,count=1,flags=re.M)
p.write_text(t,encoding='utf-8')
p=ROOT/'项目当前入口.md';t=replace_latest(p.read_text(encoding='utf-8'),summary);p.write_text(t,encoding='utf-8')
p=ROOT/'项目交付总览.md';t=replace_latest(p.read_text(encoding='utf-8'),summary)
t=t.replace('### B.2｜100ms预热预检执行（2026-10-01）','### B.2｜100ms预热真实预检收口（2026-10-01）',1)
t=re.sub(r'^\| 下一项机制与有限预算 \|.*$',f'| 100ms预热机制的真实有限预检 | [结果与图]({S}/result_analysis/结果说明.md)、[机器审核]({S}/result_analysis/assessment.json) | {n}完成回合、{cost["unused_new_dynamic"]}未执行、训练0；{gate_text}；旧余不结转 |',t,count=1,flags=re.M)
t=t.replace('## 基线与接口交付\n\n',f'## 基线与接口交付\n\n使用范围：本阶段入口/协议可复核，已经尝试的独占执行目录不可重跑；[原始成本]({S}/run/accounting.json)和[完整轨迹索引]({S}/run/attempts.json)。{next_text}\n\n',1);p.write_text(t,encoding='utf-8')
p=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';t=replace_latest(p.read_text(encoding='utf-8'),summary.replace(S,M))
t=re.sub(r'^\| 下一修复方案与内核准备 \|.*$',f'| 100ms预热真实预检 | {n}完成、{success}成功、{cost["unused_new_dynamic"]}未执行；训练/网络0 | {status}，累计{cost["cumulative_dynamic"]}/68；{gate_text} |',t,count=1,flags=re.M)
t=t.replace('## 三、负结果与限制\n\n',f'## 三、负结果与限制\n\n{gate_text}。本次预检已实际接通采样/物理入口，但不是学习效果验收；协议修复与物理负结果分别保留。\n\n',1)
t=t.replace('<a id="figures"></a>\n\n',f'<a id="figures"></a>\n\n![真实预检]({M}/result_analysis/preflight_results.png)\n\n[PNG]({M}/result_analysis/preflight_results.png)/[PDF]({M}/result_analysis/preflight_results.pdf)：新A/C请求和真实轨迹，全部未执行项保留。\n\n本阶段讲稿：“100ms保持预热入口已实现，通过103项协议及独立复审。真实预检完成{n}个回合，{status}；训练和网络前向均0，{gate_text}。我们保留全部尝试和真实停止证据，没有借协议通过或窗口统计宣称策略修复。”\n\n',1)
t=re.sub(r'## 五、下一项\n.*?(?=## 六、来源记录)','## 五、下一项\n\n'+next_text+f' 累计动态{cost["cumulative_dynamic"]}，本轮未执行{cost["unused_new_dynamic"]}和旧余不结转，PAUSED，B.2未完成。\n\n',t,count=1,flags=re.S)
t+='\n2026-10-01｜100ms预热真实预检收口：'+summary.replace(S,M)+'\n';p.write_text(t,encoding='utf-8')
p=HERE/'progress.md';t=p.read_text(encoding='utf-8');t+=f'\nTask 3: complete as bounded execution/closeout — {status}, {n} completed, training/model0; candidate gate passed={passed}, unused starts={cost["unused_new_dynamic"]} not reused. Physical outcome is not a learning repair or B.2 acceptance.\n';p.write_text(t,encoding='utf-8')
print(json.dumps(dict(status=a['status'],documents_updated=4,candidate_preflight_passed=passed),ensure_ascii=False))
