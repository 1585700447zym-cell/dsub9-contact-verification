"""Close the bounded pilot and update the existing five rolling documents."""
from pathlib import Path
import json, re, shutil
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
def read(p): return json.loads(p.read_text(encoding='utf8'))
def write(p,s): p.write_text(s,encoding='utf8',newline='\n')
def replace_section(s,title,body):
    pattern=r'(## '+re.escape(title)+r'\n).*?(?=\n## |\Z)'
    assert re.search(pattern,s,re.S), title
    return re.sub(pattern,lambda m:m.group(1)+'\n'+body.strip()+'\n',s,count=1,flags=re.S)
def main():
    assert not (OUT/'delivery_manifest.json').exists(), 'Sealed'
    a=read(OUT/'assessment.json'); l=read(OUT/'run/ledger.json'); v=read(OUT/'closure_verification.json')
    assert v['passed'] and a['audit_errors']==[] and a['completed']==28 and a['status']=='complete'
    f=a['metrics']['F50']; s=a['metrics']['S50']; comp=a['comparisons']['S_vs_F']
    gain=comp['time_reduction_fraction']*100
    signal='达到' if comp['pilot_signal'] else '未达到'
    final_rows={m:{r['case_id']:r for r in a['rows'] if r['mode']==m and r['stage']=='final'} for m in ('F50','S50')}
    off_axis_load={m:sum(r['peak_force_mN'] for k,r in final_rows[m].items() if k!='aligned')/4 for m in ('F50','S50')}
    off_axis_gain=100*(1-off_axis_load['S50']/off_axis_load['F50'])
    load_note=(f'五点平均峰值力下降主要来自对中点：S该点策略调用0、峰值力0，而F为5.383mN。'
               f'四个偏置点的平均峰值力仅改善{off_axis_gain:.2f}%；这是解释数据构成，不替代预登记五点主指标，也不证明学习收益。')
    per_case='\n'.join(f"| {k} | {r['task_end_time_s']:.3f} | {final_rows['S50'][k]['task_end_time_s']:.3f} | {r['peak_force_mN']:.3f} | {final_rows['S50'][k]['peak_force_mN']:.3f} |" for k,r in final_rows['F50'].items())
    stamp='2026-10-07'
    base='deliverables/paper_comparison/v4_learning_requalification_20261006/'
    scope=(f'本轮修复及有限学习pilot已验收；完整B.2未验收。F/S各2000批，冻结开发点各5/5功能成功；'
           f'独立进程代表复现2/2逐值一致，28/28有效停稳，参考故障/硬保护0。'
           f'S相对F平均用时改善{gain:.2f}%，{signal}预登记的10%开发继续信号。')
    cost=(f'新动态28/28，累计173；190,882控制周期/1,908,820物理子步；正式更新尝试/完成4000/4000；'
          f'策略控制调用78,520，发布117,108条经验（F54,776/S62,332），未用预算0。'
          f'两次普通搜索耗尽失败均发布，评价/恢复不入池。原关闭余量不重开，自动跟踪PAUSED。')
    next_text=('下一项优先冻结当前控制器、137维学习器和超参数，预登记同一共同版本的B2配对评价、'
               '未用范围评价及必要的重复训练种子；据成功、用时和接触载荷判断是否值得扩展阶段约束。'
               '先补公平比较和学习贡献证据，不因本轮无运行故障就新增观测或算法层。'
               '本轮预算已全部消费并收口，下一物理/训练执行需新的登记，不能复用关闭余量。')
    paths=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md',
           'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    for name in paths:
        p=ROOT/name; text=p.read_text(encoding='utf8'); prefix='../../../' if name.startswith('deliverables/') else ''
        block=f'''<!-- v4-requalification-current -->
**PC-06收口（{stamp}）：{scope}**

{cost}

441项关联离线检查通过；一次限定独立审查0 Critical/Important/Minor；28份原始档案的停稳、几何、奖励逐条复算通过；18次完整检查点读取门通过。1057项输入及源码ZIP逐项核验未变，PC-03/04/05与复杂度审查原封存保持。只重绑两个登记文件，137维/4维动作、网络、奖励、几何、保护和超参数保持；没有新增学习模块。

五点均为已用开发点、单训练种子，正式独立测试0；两次恢复复现不增加性能样本。旧B2控制指纹不同，未重新贴标签比较；本轮没有证明学习贡献、S优于B2、历史critic高估消除或完整C能力。{next_text}

[结果与图]({prefix}{base}结果说明.md)、[原始复核]({prefix}{base}assessment.json)、[收口检查]({prefix}{base}closure_verification.json)、[冻结计划]({prefix}docs/superpowers/plans/2026-10-06-v4-learning-requalification.md)。本可交付阶段完成，按协作约定暂停汇报。
<!-- /v4-requalification-current -->'''
        pattern=r'<!-- v4-requalification-current -->.*?<!-- /v4-requalification-current -->'
        assert re.search(pattern,text,re.S);text=re.sub(pattern,lambda _:block,text,count=1,flags=re.S)
        text=text.replace('最后更新：2026-10-06。','最后更新：2026-10-07。',1)
        write(p,text)
    p=ROOT/'项目进度跟踪.md'; text=p.read_text(encoding='utf8')
    replacements={
      '| B.1 接口与训练准入包 | 既有137维能力保持；新控制来源资格待签发 | [边界验收](deliverables/paper_comparison/search_boundary_fix_20261006/结果说明.md) | 旧PC-04源绑定不适用于变更后控制器；不得直接启动训练 |':
      f'| B.1 接口与训练准入包 | 已验收（PC-06限定新控制来源） | [新资格]({base}qualification.json)、441关联检查 | 不扩展连续域或硬件；旧PC-04资格仍失效 |',
      '| B.2 小规模学习与评价包 | 未验收；边界中断局部修复通过，新正式学习0 | [PC-05](deliverables/paper_comparison/search_boundary_fix_20261006/结果说明.md) | 重新准入后完成真实学习、冻结评价及独立/重复证据 |':
      f'| B.2 小规模学习与评价包 | 待验收；本轮有限pilot已验收 | [PC-06]({base}结果说明.md)：F/S各2000批，各5/5成功，恢复2/2 | 同版本B2配对、未用范围及重复证据；学习贡献未证明 |',
      '| C 候选约束与消融 | 受阻；SEARCH-only实现与协议通过 | [计划书](docs/superpowers/plans/2026-10-03-stage-permission-resume.md)、[结果与图](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/结果说明.md) | 保护触发后受控停止，完整配对效果尚不能判断；连续进展约束尚未实现，不等于完整C验收 |':
      f'| C 候选约束与消融 | 待验收；SEARCH-only本轮可评价 | [F/S实测]({base}assessment.json) | S相对F{signal}10%继续信号；连续进展约束未实现，方法优势未证明 |'
    }
    for old,new in replacements.items(): assert old in text; text=text.replace(old,new,1)
    body=f'''| 原任务 | 本次核对状态 |
|---|---|
| 1 开发适用性 | 五个已用开发点、单训练种子；不扩展连续域/硬件 |
| 2 统一闭环/SAC接口 | 137维/4维冻结，新控制来源资格及441项检查通过 |
| 3 动态闭环/成本 | {cost} |
| 4 B1 | 新任务原5点结果保持，未补跑或改历史标签 |
| 5 B2与批量评价 | 旧B2控制指纹不同，五点不重绑成本轮基线；需当前共同版本配对 |
| 6 普通残差SAC | F真实2000批、冻结5/5成功；现有边界重采样/尾目标修正，不称原样标准SAC |
| 7 阶段与进展约束 | S真实2000批、冻结5/5成功；S相对F用时改善{gain:.2f}%，{signal}10%继续信号，完整进展约束未实现 |
| 8 正式证据与展示 | 28档案、完整检查点、逐条复核及两图已交付；独立测试/多种子/论文优势未完成 |

PC-06工程修复、实际学习、冻结开发评价和代表复现已完成；不得等同完整B.2、完整C或论文结论。'''
    text=replace_section(text,'原八项任务对应',body)
    risk='当前风险：本轮参考错误未重现，28/28有效停稳；S相对F'+signal+'预登记开发继续信号。单种子开发成功不能证明泛化或学习贡献，同版本B2配对尚缺。137维冗余与SAC复制为维护债务，本轮保持冻结；不以整理代码替代实验结论。'
    start=text.index('当前风险：',text.index('## 当前风险和准入门'));end=text.index('\n\n',start)
    text=text[:start]+risk+text[end:]
    row_updates={
      '修复归因与验收范围':('PC-06训练/冻结评价/恢复完成，参考故障0','只验收本轮有限修复；旧120维失败与critic高估不能一并宣称解决'),
      '训练覆盖与目标':('F预热活动23,384条、S16,288条，各四个方向；正式各2000批','正式独立测试0，覆盖门通过不等于统计充分'),
      '工程范围可观测性与动作作用':('F/S冻结开发各5/5成功，策略控制调用78,520','同版本B2配对、初始确定性策略对照及未用范围仍缺'),
      '学习时间尺度':('2ms策略/控制、100ms预热保持不变；1,908,820物理子步','实际耗时和保存/审核开销分列，不把模拟步数称更新数'),
      '周期峰值/停止尾段事件':('本轮28/28有效停稳且无硬保护，逐条峰值/奖励/尾段复核通过','有限范围不保证任意策略安全'),
      '熵项与奖励尺度':('本轮F2000/S2000批；加权熵与物理奖励量级曲线已保存','活动行熵与全部样本奖励分母不同；比例不证明唯一根因；额外critic核对0'),
      '训练状态恢复':('18次完整数值读取门通过；两次独立物理复现逐值一致','代表复现不是新增独立性能样本或跨机验证'),
      '创新与外推':(f'S相对F用时改善{gain:.2f}%，{signal}10%开发继续信号','同版本B2配对、未用范围、多训练种子未完成；完整B.2/C未验收')}
    for label,(fact,gate) in row_updates.items():
        text,n=re.subn(r'^\| '+re.escape(label)+r' \|.*$',f'| {label} | {fact} | {gate} |',text,count=1,flags=re.M);assert n==1,label
    text=replace_section(text,'下一项交付',next_text+f'\n\n[PC-06结果]({base}结果说明.md)。本轮已收口；短训完成不自动等于方法优于基线。')
    text+=f'\n### {stamp}｜PC-06新控制来源学习pilot收口\n\n{scope}\n\n{cost}\n\n验收：441关联检查、限定审查0重要问题、28原始档案逐条复核及18读取门、2独立物理复现通过；1057源码输入及ZIP保持，四份原封存完整。本轮仅登记来源重绑，未新增维数/算法层。\n\n限制与下一项：{next_text} [结果与证据]({base}结果说明.md)、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
    write(p,text)
    p=ROOT/'项目交付总览.md';text=p.read_text(encoding='utf8')
    entry=f'''### PC-06｜新控制来源准入、真实学习与冻结评价（{stamp}）

- **获得能力：** {scope}
- **成本和数据：** {cost}
- **证据：** 441关联离线检查，一次限定审查0重要问题；1057输入不变；28档案逐条独立复核；18完整读取门及两次物理复现通过。
- **使用：** [结果、统计与图]({base}结果说明.md)、[复核]({base}assessment.json)、[收口检查]({base}closure_verification.json)、[执行清单]({base}执行清单.md)、[最终封存]({base}delivery_manifest.json)。保存F/S各2000批完整检查点；本轮执行一次性预算已消费，不重新运行执行入口。
- **限制：** 五点已用、单训练种子；旧B2不重绑；学习贡献、独立泛化、完整B.2/C及论文优势未证明。下一项先补同版本B2与未用范围/重复证据。

'''
    assert '### PC-06｜' not in text; text=text.replace('### PC-05｜',entry+'### PC-05｜',1)
    anchor='|---|---|---|\n';index=text.index(anchor,text.index('## 快速查找'))+len(anchor)
    text=text[:index]+f'| 最新真实学习与冻结评价 | [PC-06结果]({base}结果说明.md) | F/S各5/5成功，恢复2/2；完整B.2与方法优势未证明 |\n'+text[index:]
    write(p,text)
    p=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';text=p.read_text(encoding='utf8');mb='../../paper_comparison/v4_learning_requalification_20261006/'
    additions={
      '一、本月综合摘要':f'截至{stamp}，{scope}\n\n{cost} [本轮结论]({mb}结果说明.md)。下面保留此前时点摘要，历史“下一项”不作为当前任务。',
      '二、关键数字与证据':f'''PC-06截至{stamp}：

| 指标 | F | S | 口径 |
|---|---:|---:|---|
| 正式更新批数 | 2000 | 2000 | 尝试与完成各4000，无重复优化 |
| 冻结功能成功 | 5/5 | 5/5 | 已用开发点，复现不重复计数 |
| 附加80μm/0.5°成功 | {f['strict_precision_successes']}/5 | {s['strict_precision_successes']}/5 | 附加指标，不替代功能成功 |
| 平均任务用时/s | {f['mean_penalized_time_s']:.4f} | {s['mean_penalized_time_s']:.4f} | 所有冻结点，失败罚26s |
| 平均峰值力/mN | {f['mean_peak_force_N']*1000:.4f} | {s['mean_peak_force_N']*1000:.4f} | 每点子步峰值的平均 |
| 发布经验条数 | 54776 | 62332 | 只来自新预热/在线回合 |
| 独立进程代表复现 | 1/1 | 1/1 | 完整检查点；逐值一致 |

28/28有效停稳、参考故障/硬保护0；累计173；190,882周期/1,908,820子步，实际回合墙时合计{a['wall_seconds']/3600:.3f}h，整轮含更新/保存/审核{v['total_elapsed_seconds']/3600:.3f}h；策略控制调用78,520。正式独立测试0。 [完整复核]({mb}assessment.json)。以下数字保留原统计时点。''',
      '三、负结果与限制':f'PC-06：S负Y随机预热和零更新在线各一次普通搜索耗尽失败，两轮均有效停稳并进入回放，未漏用。冻结S负Y成功不单独证明学习贡献：采样模式从随机变为确定性，初始确定性策略对照尚缺。S相对F用时改善{gain:.2f}%，{signal}10%继续信号；旧B2来源不同，不作本轮优势比较。{load_note} 单种子、已用开发点、未标定简化执行器；没有机械臂/夹爪或完整C证据。历史负结果保持。以下为此前时点限制。',
      '四、图表与讲稿':f'''PC-06当前图表：[冻结五点用时]({mb}frozen_development.png)、[真实更新曲线]({mb}actual_learning_curves.png)、[图表数据]({mb}figure_data.json)。图中恢复复现不计入成功率，损失下降和熵/奖励比例不证明策略收益。

讲稿：“共同参考故障的修复通过了本轮真实学习检验。F和S各完成2000批更新，冻结五点均插入成功，两次完整检查点恢复逐值一致。不过S相对F的平均用时改善{gain:.2f}%，{signal}预登记10%信号；当前还不能证明学习贡献或优于B2。接下来保持实现冻结，先补同版本公平基线和未用范围、重复证据，再决定是否扩展新约束。”

以下图表与讲稿保留当时口径。'''}
    for title,addition in additions.items():text=text.replace('## '+title+'\n','## '+title+'\n\n'+addition+'\n',1)
    text=replace_section(text,'五、下一项',next_text)
    text+=f'\n### {stamp}｜PC-06真实学习与冻结评价收口\n\n{scope} {cost}\n\n441关联检查通过、一次限定审查0重要问题，28档案逐条复核，18读取门及2独立物理复现通过；1057来源/ZIP与四份历史封存保持。 [结果]({mb}结果说明.md)、[完整复核]({mb}assessment.json)、[收口证据]({mb}closure_verification.json)。下一项为同版本B2公平对照及未用范围/必要重复；本轮结束暂停汇报，不重开旧预算。\n'
    write(p,text)
    report=f'''# PC-06修复与有限学习验证结果

截至{stamp}。**{scope}**

## 已解决到什么程度

上一轮S负Y在8.756s因共同搜索参考不可行而报错。本轮使用PC-05共同边界修复与continuation_v2，重新绑定新资格，沿用原学习器和算法设置。从同一新零网络起点真实采集、审核、训练、冻结评价及新进程恢复全部执行结束；28/28仿真有效、实际停稳，参考错误和硬保护均0。已登记故障路径在本轮没有重现，有限工程修复及pilot验收通过；不是任意未来动作安全保证。

{cost}

两次S负Y普通任务失败（随机预热、首个零更新在线）均完整归档并发布，终末奖励−2；训练16回合合计14成功/2普通失败。冻结评价和恢复数据均不进入回放。初始F/S网络一致，最后actor指纹均变化，正式更新数由尝试日志、完成日志、优化器状态和完整检查点共同核对。

## 冻结评价与方法信号

| 指标 | F：固定50权限 | S：仅SEARCH开放 | 解释 |
|---|---:|---:|---|
| 正式更新 | 2000 | 2000 | 同起点、同超参数，各自新采集数据 |
| 功能成功 | 5/5 | 5/5 | 五个已用开发点 |
| 附加80μm/0.5°成功 | {f['strict_precision_successes']}/5 | {s['strict_precision_successes']}/5 | 保留附加精度指标 |
| 平均任务用时/s | {f['mean_penalized_time_s']:.4f} | {s['mean_penalized_time_s']:.4f} | 全部冻结点，失败罚26s |
| 平均峰值力/mN | {f['mean_peak_force_N']*1000:.4f} | {s['mean_peak_force_N']*1000:.4f} | 子步峰值，非周期末载荷 |
| 平均峰值力矩/mN·m | {f['mean_peak_torque_Nm']*1000:.5f} | {s['mean_peak_torque_Nm']*1000:.5f} | 力矩在G系 |
| 独立进程逐值复现 | 1/1 | 1/1 | 代表负Y，恢复不增加性能样本 |

逐工况如下，全部功能成功；150表示初始横向偏置150μm。

| 工况 | F用时/s | S用时/s | F峰值力/mN | S峰值力/mN |
|---|---:|---:|---:|---:|
{per_case}

{load_note}

S相对F用时改善{gain:.2f}%，{signal}预登记继续信号（至少10%用时改善、成功数不减、保护不增、平均峰值力不增超过5%）。这是开发筛查规则，不是论文发表阈值。相同成功率与小幅指标差异不等于方法优势，不能为了有优势而事后改规则。

旧B2来源指纹不同，保留历史档案，S_vs_B2/pilot_signal为null，表示公平比较尚缺，不能解释为失败或成功。S_vs_F_signal为{str(comp['pilot_signal']).lower()}。训练时随机失败、冻结时确定性成功存在采样方式差异，不能据此单独归因于学习。正式未用范围测试和重复训练种子尚未执行，完整B.2及C未验收。

![冻结开发评价](frozen_development.png)

![真实更新曲线](actual_learning_curves.png)

损失或熵/奖励量级仅为诊断数据。图中熵已乘alpha且按活动行统计，奖励绝对值来自全部抽样行；比例不能证明唯一根因。本轮没有额外critic评分，不能宣称历史危险边界Q约+9.364对尾段−8.359的高估已消除。

## 实现与验证范围

本轮只修改原合同及原执行器两个登记文件，重新绑定PC-05控制来源、资格v2与预算145→173；相应测试更新。137维/4维动作、网络、学习率、奖励、几何和保护不变，没有新增v5学习包装或算法层。当前残差SAC含原critic边界采样/尾段目标修正，不称原样标准SAC；零残差是B2。

441项关联离线检查通过；一次限定独立审查0 Critical/Important/Minor，范围见[review.md](review.md)。28份原始档案SHA/停稳/几何成功/逐条dt奖励折扣/发布收据独立复算无错误，18完整检查点读取门通过；两次真实恢复逐值一致。独立复核奖励行{v['independent_archive_reward_rows']:,}。1057项输入与源码ZIP逐项核对未变，四份前项封存全部保持。原项目全量测试、跨机/GPU、连续域安全和硬件标定不在本次验收范围。

实际物理回合墙时合计{a['wall_seconds']/3600:.3f}h，整轮含更新、保存、读取及审核{v['total_elapsed_seconds']/3600:.3f}h。JSON原子替换短暂占用恢复{len(v['json_replace_recoveries'])}次，仅重试同一文件，不重复物理或优化动作。检查点完整读回时已核对Adam步数、抽样索引、回放、RNG与持久化尝试/完成记录。

## 使用与下一项

[执行清单](执行清单.md)、[资格](qualification.json)、[实际账本](run/ledger.json)、[原始独立复核](assessment.json)、[收口验证](closure_verification.json)、[最终封存](delivery_manifest.json)。最终完整检查点：[F](run/checkpoints/F50_online_3/manifest.json)、[S](run/checkpoints/S50_online_3/manifest.json)，同目录state.pt包含模型/优化器/回放/RNG和尝试记录。

运行目录的一次性领取已关闭，不重新执行run_v4_learning_pilot --execute。分析/图表脚本会写输出，封存后只在完整副本中复核；执行需要已登记的项目来源、CPU runtime、历史schema依赖，不能把单个state.pt当作跨机独立部署包。滚动文档保存本次快照，原滚动文件随后更新不影响交付清单。

{next_text} 当前机械臂/夹爪尚未加入，仍为简化笛卡尔执行器和刚性多针接触仿真；论文优势需要真实、同条件的比较证据。本可交付阶段完成，暂停汇报。
'''
    write(OUT/'结果说明.md',report)
    write(OUT/'执行清单.md',f'''# PC-06执行清单（{stamp}收口）

冻结计划[原计划](../../../docs/superpowers/plans/2026-10-06-v4-learning-requalification.md)的源码绑定保持，不改历史勾选；实际完成情况在此记录。

- [x] 新版本/来源/预算反例RED，登记修改GREEN，11专项通过。
- [x] 441关联套件、完整合成数值独立恢复、有效普通失败发布、一次限定只读审查通过。
- [x] 1057输入及ZIP/904共同来源冻结，新资格v2签发。
- [x] 新28动态/4000正式批实际执行结束；旧余量未重开。
- [x] F/S各5冻结开发点，功能成功均5/5；S相对F{signal}10%开发继续信号。
- [x] 两次完整检查点独立物理恢复，逐值一致。
- [x] 28档案/逐条奖励/发布/18完整读取门及四份历史封存复核通过。
- [x] 五份滚动文档、月报与两图更新，保存当时快照。
- [ ] 同版本B2公平配对、未用范围及重复训练种子（下一阶段，未执行）。

有限修复/pilot已验收，完整B.2/C未验收；新增执行需独立新登记，自动跟踪PAUSED。
''')
    snap=OUT/'documents_snapshot'
    for name in paths:
        dest=snap/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
    print('Result, five rolling documents, execution checklist and snapshots updated')
if __name__=='__main__':main()
