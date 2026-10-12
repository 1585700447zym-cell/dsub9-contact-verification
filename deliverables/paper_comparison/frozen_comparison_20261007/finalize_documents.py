"""Report actual fixed evaluation results and update the five existing documents."""
from pathlib import Path
import json,re,shutil
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
def read(p):return json.loads(p.read_text(encoding='utf8'))
def write(p,s):p.write_text(s,encoding='utf8',newline='\n')
def section(s,title,body):
    pattern=r'(## '+re.escape(title)+r'\n).*?(?=\n## |\Z)'
    assert re.search(pattern,s,re.S)
    return re.sub(pattern,lambda m:m.group(1)+'\n'+body.strip()+'\n',s,count=1,flags=re.S)
def comparison_text(c):
    if c is None:return '矩阵不完整，无法判断'
    change=c['time_reduction_fraction'];b=c['baseline'];a=c['candidate']
    time_text=f'用时改善{100*change:.2f}%' if change>=0 else f'用时增加{-100*change:.2f}%'
    reasons=[]
    if change<.1:reasons.append('用时改善不足10%')
    if a['successes']<b['successes']:reasons.append('成功数减少')
    if a['guarded_attempts']>b['guarded_attempts']:reasons.append('保护次数增加')
    if a['mean_peak_force_N']>1.05*b['mean_peak_force_N']:
        increase=100*(a['mean_peak_force_N']/b['mean_peak_force_N']-1) if b['mean_peak_force_N'] else None
        reasons.append('峰值力均值由0增大' if increase is None else f'峰值力均值增加{increase:.2f}%超过5%')
    assert c['pilot_signal']==(not reasons)
    return time_text+'，综合继续信号'+('满足' if c['pilot_signal'] else '未满足（'+'、'.join(reasons)+'）')
def main():
    assert not (OUT/'delivery_manifest.json').exists()
    a=read(OUT/'assessment.json');l=read(OUT/'run/ledger.json');v=read(OUT/'closure_verification.json')
    assert v['passed']
    closed=a['status']=='complete' and not a['audit_errors']
    scope='同版本公平对照与冻结后首次位置评价完成' if closed else '本轮按实际故障/停止结果收口'
    base='deliverables/paper_comparison/frozen_comparison_20261007/';dev=a['comparisons']['development'];test=a['comparisons']['first_use_frozen_position_test']
    statements=[f"开发F相对B2：{comparison_text(dev['B2_to_F2000'])}",f"开发S相对B2：{comparison_text(dev['B2_to_S2000'])}",f"开发S相对F：{comparison_text(dev['F2000_to_S2000'])}",
        f"F学习贡献对照：{comparison_text(dev['F0_to_F2000'])}",f"S学习贡献对照：{comparison_text(dev['S0_to_S2000'])}",
        f"新位置F相对B2：{comparison_text(test['B2_to_F2000'])}",f"新位置S相对B2：{comparison_text(test['B2_to_S2000'])}",f"新位置S相对F：{comparison_text(test['F2000_to_S2000'])}"]
    promising=all(c is not None and c['pilot_signal'] for c in (test['B2_to_S2000'],test['F2000_to_S2000']))
    next_text=('首次位置出现有限继续信号；下一项预登记必要的重复训练种子和保留的新最终测试，再判断统计稳定性。'
        if promising else '本轮未支持简单SEARCH-only约束相对合理对照的稳定优势。下一项先用现有档案做离线归因：核对分阶段动作、裁剪、残差实际运动和各工况时间贡献，再确定最多一次有依据的机制调整及较小固定边界对照；暂不追加训练、扩维或降低判据。')
    if not closed:next_text='先处理本轮记录的运行/审核问题，保留失败与关闭余量；不重试已发生回合。'+next_text
    next_text+=' 本轮四点已消费，后续调参不能复用它们作为未见最终测试；旧预算及自动跟踪保持关闭/PAUSED。'
    cost=f"新启动{a['new_attempts']}/27，采样结束{a['finished']}，累计{a['cumulative']}/200；{a['control_cycles']:,}控制周期/{a['physical_substeps']:,}物理子步，真实网络控制{a['network_policy_calls']:,}次；新梯度/经验发布0，未用{a['unused_closed']}关闭。"
    summary='；'.join(statements)+ '。'
    paths=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    for name in paths:
        p=ROOT/name;s=p.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else ''
        block=f'''<!-- pc07-current -->
**PC-07收口（2026-10-07）：{scope}；完整B.2/C及论文优势不据此标已验收。** {cost}

{summary}

F0/S0是同种子随机初始化、0更新的确定性策略，动作并非全零；B2才是全零残差。10份训练后开发档案只读继承PC-06；新位置四象限各一点，仿真前固定，单训练种子小样本。63关联检查通过；独立审查1 Important经两种故障RED/GREEN关闭，未二次独立复审；生产1057输入保持。原始奖励/停稳/几何、计数、状态保持及来源按实际收口复核。

{next_text} [结果与图]({prefix}{base}结果说明.md)、[完整比较]({prefix}{base}assessment.json)、[收口检查]({prefix}{base}closure_verification.json)、[首次使用登记]({prefix}{base}first_use_registration.json)。本阶段完成暂停汇报，旧PC-06及前序记录保留当时状态。
<!-- /pc07-current -->'''
        s=re.sub(r'<!-- pc07-current -->.*?<!-- /pc07-current -->',lambda _:block,s,count=1,flags=re.S);write(p,s)
    p=ROOT/'项目进度跟踪.md';s=p.read_text(encoding='utf8')
    s=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 位置范围里程碑完成；全范围待验收 | [PC-07]({base}结果说明.md) | 短训、保存/加载与冻结位置评价完成；姿态/联合范围及原任务6仍待；三种子属论文D要求 |',s,count=1,flags=re.M)
    s=re.sub(r'^\| C 候选约束与消融 \|.*$',f'| C 候选约束与消融 | 待验收；简单SEARCH-only有限比较已完成 | [实际比较]({base}assessment.json) | 当前假设继续信号见结果；连续进展约束未实现 |',s,count=1,flags=re.M)
    s=section(s,'原八项任务对应',f'''| 原任务 | 本次核对状态 |
|---|---|
| 1 开发适用性 | 同版本五开发点及四个冻结后首次使用位置；单训练种子，未扩展姿态/硬件 |
| 2 统一闭环/SAC接口 | 原137维/4维及1057生产输入保持；本轮仅只读评价适配 |
| 3 动态闭环/成本 | {cost} |
| 4 B1 | 历史五点结果保持；本轮未补采B1 |
| 5 B2与批量评价 | 新同版本B2与固定策略配对，开发/首次位置分别统计；首例全轨迹与PC-05精确一致 |
| 6 普通残差SAC | 原F2000冻结评价与F0初始对照；{comparison_text(dev['F0_to_F2000'])}；原critic技巧保持，不称原样标准SAC |
| 7 阶段与进展约束 | {comparison_text(dev['F2000_to_S2000'])}；新位置{comparison_text(test['F2000_to_S2000'])}；完整进展约束未实现 |
| 8 正式证据与展示 | 固定矩阵、首次使用、原始复核与两图留存；新最终测试和三个训练种子的论文证据未完成 |

本轮只收口限定固定对照/首次位置评价，不以方法打平或运行通过标论文方法有效。''')
    start=s.index('当前风险：',s.index('## 当前风险和准入门'));end=s.index('\n\n',start)
    s=s[:start]+'当前风险：'+summary+' 单种子小样本，四点已消费；无多种子/姿态/联合扰动/硬件标定证据。初始确定性策略不能混称零残差，恢复复现不增加性能样本。'+s[end:]
    s=section(s,'下一项交付',next_text+f'\n\n[本轮证据]({base}结果说明.md)。')
    s+=f'\n### 2026-10-07｜PC-07公平对照与首次位置评价收口\n\n{scope}。{cost}\n\n{summary}\n\n63关联检查通过；一次审查1 Important计数问题经两故障反例RED/GREEN关闭，未二次独立复审。来源、原始奖励/几何/停稳与完整状态保持按收口证据核对；生产代码0修改。{next_text} [证据]({base}结果说明.md)、[10月月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n';write(p,s)
    p=ROOT/'项目交付总览.md';s=p.read_text(encoding='utf8');assert '### PC-07｜' not in s
    entry=f'''### PC-07｜同版本公平对照、初始策略及首次位置评价（2026-10-07）

- **获得：** {scope}。{cost}
- **比较：** {summary}
- **使用：** [结果、两图和下一项]({base}结果说明.md)、[固定矩阵]({base}configuration.json)、[首次使用]({base}first_use_registration.json)、[原始复核]({base}assessment.json)、[封存]({base}delivery_manifest.json)。执行一次性领取，不重跑；分析只在完整副本中复核。
- **边界：** 生产来源/算法/奖励0变化；新训练/发布0；单种子四新位置，使用后不再是后续未见测试；没有完整C、硬件或论文优势验收。

''';s=s.replace('### PC-06｜',entry+'### PC-06｜',1);write(p,s)
    # Monthly/report/snapshot closure is appended below.
    return a,l,paths,cost,summary,next_text,scope

if __name__=='__main__':
    a,l,paths,cost,summary,next_text,scope=main()
    base='deliverables/paper_comparison/frozen_comparison_20261007/';mb='../../paper_comparison/frozen_comparison_20261007/'
    def number(value,scale=1):return '未执行' if value is None else f'{value*scale:.4f}'
    tables={}
    for group,methods in a['metrics'].items():
        rows=['| 方法 | 功能成功/尝试 | 附加精度成功 | 平均罚时/s | 平均峰值力/mN | 保护 | 缺失 |',
              '|---|---:|---:|---:|---:|---:|---|']
        for m,v in methods.items():
            rows.append(f"| {m} | {v['successes']}/{v['attempts']} | {v['strict_precision_successes']} | {number(v['mean_penalized_time_s'])} | {number(v['mean_peak_force_N'],1000)} | {v['guarded_attempts']} | {','.join(v['missing_cases']) or '无'} |")
        tables[group]='\n'.join(rows)
    b2={r['case_id']:r for r in a['records']['development']['B2']}
    trained_s={r['case_id']:r for r in a['records']['development']['S2000']}
    contribution='矩阵不完整，不计算工况收益贡献。'
    if a['status']=='complete':
        saved={k:b2[k]['task_end_time_s']-trained_s[k]['task_end_time_s'] for k in b2}
        contribution=f"开发S相对B2共节省{sum(saved.values()):.3f}s，其中负Y点贡献{saved['y_neg_150']:.3f}s（{100*saved['y_neg_150']/sum(saved.values()):.2f}%）；收益主要集中在一个已使用开发点。该描述来自已有逐点记录，不作为新的调参或验收门槛。"
    positions=read(OUT/'first_use_registration.json')['positions']
    position_table='\n'.join(['| 预登记点 | X/μm | Y/μm |','|---|---:|---:|']+[f"| {p['id']} | {p['x_um']:.6f} | {p['y_um']:.6f} |" for p in positions])
    conclusion=('本轮判断：学习链和插入功能能够工作，开发点可见学习收益；当前简单SEARCH阶段约束尚无稳定优势。初始F/S分别4/5成功，训练后分别5/5；但四个新位置B2/F/S均4/4，F/S略慢于B2。位置范围的短训、保存/加载与冻结评价里程碑已完成，完整B.2范围及原任务6仍待验收。下一项先利用现有档案做离线归因，暂不追加大训练。' if a['status']=='complete' and not a['audit_errors'] else '本轮有未完成或审核问题，按真实记录收口，不据此判断方法收益。')
    report=f'''# PC-07冻结策略公平对照结果

截至2026-10-07。**{scope}。完整B.2/C及论文优势不据此标已验收。**

{conclusion}

{cost}

B2是无学习的参考搜孔/插入控制器；F是固定边界残差对照；S仅在SEARCH阶段开放残差。0/2000表示优化批数，初始策略并非零残差；当前F/S保留已记录的critic处理，不称未经修改的标准SAC。

## 实际比较

{summary}

开发五点：F2000/S2000十份记录来自PC-06原封存，不重采；其余均为本轮新采集。

{tables['development']}

冻结后首次使用的四个位置，roll/pitch/yaw=0，其他物理条件保持。B2/F2000/S2000同点配对。

{tables['first_use_frozen_position_test']}

“功能成功”表示当前几何和停稳裁判下完成插入，附加精度另按80μm/0.5°统计。四新位置三种方法附加精度均0/4，不能把功能成功解释为达到该附加精度。

{contribution}

{position_table}

F0/S0为同种子随机初始化、0更新的确定性策略；它们不是全零动作。B2才是全零残差，无网络推理。F/S两组训练预算均为此前2000批，本轮新优化0；所有策略确定性。学习贡献在开发点与各自初始策略比较，新位置没有额外初始策略评价，不据此单独证明泛化的学习贡献。

继续信号沿用至少10%平均罚时改善、成功不减、保护不增、平均峰值力增幅不超过5%。该信号只是预登记开发筛查规则，不是发表阈值或统计显著性。每个工况的力/时间原值见assessment.json；尤其对中点没有接触时会拉低全组平均力，不能把总均值下降直接解释为偏置点载荷改善。

![开发公平对照](development_comparison.png)

![首次位置对照](first_use_positions.png)

## 已核对的证据与局限

63项关联检查通过，原新增14反例RED后GREEN；一次独立审查发现1 Important：故障回合网络调用漏计，分别注入rollout/audit错误，两例RED实际0对期望7，再修正为从实际entry统一派生计数，最终63 GREEN。未二次独立复审。审查范围与作者修正见[review.md](review.md)。

生产1057项输入及PC-06原封存保持。B2负Y新回合11,271点、控制器事件及结果与PC-05完整逐值一致；零残差适配没有改变该基线轨迹。原完整检查点只读，评价前后完整模型/优化器/RNG逐值比较通过的事实按回合evaluation_checks记录，故障回合不冒充审核通过。本轮没有经验发布或优化入口。

原始档案按SHA、真实停稳、几何成功、周期峰值下界、逐条dt/推进/奖励/折扣、冻结方法指纹和调用计数复核。新奖励行复核{a['independent_reward_rows_new']:,}，继承10份原始开发资料另复核；审查未判定的物理与分析事项由这些实际记录补齐，不称独立审查已验证未运行结果。

固定27矩阵的有效普通失败和合格保护都保留；无效/未停稳/运行/来源/参考错误整轮停，未执行不填零力或失败。状态{a['status']}，错误：{a['error']!r}；独立档案审核错误：{a['audit_errors']!r}。全部尝试和关闭余量在[账本](run/ledger.json)中保存。

实际回合墙时合计{a['wall_seconds']/3600:.3f}h，整轮含读取与审核{a['execution_elapsed_seconds']/3600:.3f}h；物理周期、网络接口调用和优化批数分列。原rollout的policy_calls为提供器接口调用，本轮network_policy_calls才表示真实网络控制次数，B2固定0。故障路径也记已发生调用，未重试物理或优化。

这是一个训练种子、五开发点和四个首次位置的有限证据；不覆盖姿态/联合扰动、连续域、三个训练种子、硬件标定或机械臂/夹爪。四点已记录首次使用，后续方案调试不能再将它们作为未见最终测试。历史120维失败与critic高估并未由本次评价被统一解释或宣称消除。

## 下一项与复核

{next_text}

[预登记计划](../../../docs/superpowers/plans/2026-10-07-v4-frozen-comparison.md)、[资格](qualification.json)、[首次使用登记](first_use_registration.json)、[完整结果](assessment.json)、[收口复核](closure_verification.json)、[封存清单](delivery_manifest.json)。分析/绘图会写输出，封存后只能在完整副本中复核；不重启已领取run目录，原检查点及依赖runtime/source/schema仍需保留。

执行选择：复用原工作区；先做27次无训练固定评价、暂不盲目增加多种子；适配和测试仅放交付目录以保持原资格；原采集字段保持语义而新增真实网络计数；常规步骤沿用自主授权，未自动提交或清理。完整决定与审查保留事项见[计划](../../../docs/superpowers/plans/2026-10-07-v4-frozen-comparison.md)和[阶段记录](progress.md)。阶段完成暂停汇报。
'''
    write(OUT/'结果说明.md',report)
    p=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';s=p.read_text(encoding='utf8')
    additions={
        '一、本月综合摘要':f'截至2026-10-07，PC-07{scope}。{cost}\n\n{summary} 以下保留以前时点摘要。',
        '二、关键数字与证据':f"PC-07开发公平对照（原10份训练后开发档案只读继承）：\n\n{tables['development']}\n\n首次使用四位置比较：\n\n{tables['first_use_frozen_position_test']}\n\n真实成本：{cost} 下方历史数字保留统计时点。",
        '三、负结果与限制':f'PC-07：{summary} {contribution} 初始0更新策略并非零残差；新位置评价仅单训练种子，四点使用后已消费，不能用于后续调参后的未见测试。未执行不伪装失败，合格保护不删除，运行故障不当普通失败。本轮优化/发布0，生产代码0变化；完整C与论文优势未完成。以下为前序时点限制。',
        '四、图表与讲稿':f'PC-07当前图：[开发初始/训练后/B2比较]({mb}development_comparison.png)、[四首次位置比较]({mb}first_use_positions.png)、[图表数据]({mb}figure_data.json)。\n\n讲稿：“我们保持共同物理和检查点冻结，新增同版本B2及初始确定性策略，避免把初始网络表现当学习收益。{summary} 目前仅一个训练种子和四个首次位置，下一项按证据决定继续研究或收缩假设，尚未证明论文优势。”以下为历史图表与讲稿。'}
    for title,body in additions.items():s=s.replace('## '+title+'\n','## '+title+'\n\n'+body+'\n',1)
    s=section(s,'五、下一项',next_text)
    s+=f'\n### 2026-10-07｜PC-07公平对照及首次位置收口\n\n{scope}。{cost} {summary}\n\n63关联检查通过；一次审查1 Important经RED/GREEN关闭，未二次独立复审。生产来源及原封存保持。 [结果]({mb}结果说明.md)、[实际复核]({mb}assessment.json)、[首次使用]({mb}first_use_registration.json)。{next_text}\n';write(p,s)
    for name in paths:
        dest=OUT/'documents_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
    with (OUT/'progress.md').open('a',encoding='utf8') as f:f.write(f'\nTask2: closed — {scope}. {cost} {summary} Raw/source/count/stop/geometry/reward audit and figure QA recorded; five existing documents/snapshots maintained, no new monthly report.\n')
    print('PC-07 report, five rolling documents, monthly synthesis and snapshots updated')
