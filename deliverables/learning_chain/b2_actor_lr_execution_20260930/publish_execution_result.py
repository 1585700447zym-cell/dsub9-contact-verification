"""Publish the stopped run; retain every sealed preparation and historical file."""
import datetime
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent;OUT=HERE/'run_analysis'
STAGE='deliverables/learning_chain/b2_actor_lr_execution_20260930'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
audit=read(OUT/'execution_audit.json');dist=read(OUT/'distribution_summary.json')
assert audit['status']=='controlled_stop_evidence_verified' and audit['physical_by_branch']==dict(A=1,B=0)
assert not any(audit['forbidden_call_counts'].values())
assessment=dict(status='implementation_validated_effect_not_established_controlled_stop',date='2026-10-01',
    real_validation_passed=True,a_learning_exact=True,formal_batches=dict(A=500,B=500),
    new_dynamic_starts=1,physical_evaluation=dict(A='x_pos_100_force_failure',B='not_started'),
    candidate_effect_verified=False,b2_complete=False,execution_complete=False,
    stop_reason='evaluation_guard',exit_code=20,unused_new_dynamic=7,old_unused_consumed=0,
    automatic_retry=False,automatic_tracking='PAUSED',
    fixed_state_x_saturation_mean={k:dist['roles'][k]['per_axis'][0]['saturation_probability_mean'] for k in ('initial','A','B')},
    fixed_state_kl_mean={k:dist['roles'][k]['kl_to_initial_mean'] for k in ('A','B')},
    limitation='B physical outcomes absent; fixed archived state distributions cannot establish physical efficacy or unseen-state safety')
with (OUT/'assessment.json').open('x',encoding='utf-8') as stream:
    json.dump(assessment,stream,ensure_ascii=False,indent=2);stream.write('\n')
report='''# actor学习率有限对照：受控停止结果

2026-10-01。用户明确批准封存候选后执行；同一工作树、共同起点、固定500抽样、共同物理/保护/奖励保持。A的actor率3e-4，B为3e-5，critic/温度3e-4。**实现与精确复现通过；修复效果尚未证实，完整A/B动态对照未完成。**

## 实际执行与停止

4个私有数值事务、8个测试状态验证通过；首次actor参数变化B/A范数比0.09999992，critic/温度一致；无权限更新屏蔽、注入错误回滚、保存恢复、跨分支拒绝通过。随后A/B各500正式批完成并冻结。A与历史500批检查点的权重、3个Adam状态、温度、回放/档案、全部随机流及学习历史逐项一致，仅排除版本/资格身份和耗时；收口独立重读再核对通过。

A新进程确定性评价第一个正X100μm工况时触发力保护。根据预登记“任何评价保护停止整组”规则，评价失败档案完整保存后退出20；B未启动物理评价。不是原生崩溃、入口拒绝、文件写入失败或无效仿真。通用监督器process_exit的非零退出被标为failed，最终必须结合[语义分类](../exit_classification.json)和账本stopped/evaluation_guard解释为受控停止。

| A已评价的一点 | 实际结果 |
|---|---:|
| 工况/结局 | 正X100μm / CONTACT_GUARD，失败 |
| 仿真/实际停止 | 有效 / 已停稳 |
| 周期/检查子步 | 6287 / 62870 |
| 周期峰值力 | 0.025000445216226738 N（阈值0.025 N） |
| 周期峰值力矩 | 0.0003536676711298647 Nm |
| 周期末采样峰值穿透 | 7.006985831530398 μm；不是所有子步峰值 |
| 最大累计转角 | 0.19873583066271355° |
| 越限事件 / 停止命令 / 审核终点 | 10.573 / 10.574 / 12.574 s |
| 终末XY误差 / 完整回报 | 100.67314534494379 μm / −11.706062021823936 |

9.174s搜索耗尽，9.260s接受恢复，9.809s达到回撤距离，9.832s恢复运行，10.573s触发FORCE_LIMIT。这条轨迹支持“恢复后又失败”的行为事实，不隔离唯一学习根因。停止后活动动作归零、两套停稳窗口、完整奖励/时序/动作映射、唯一末端−10均独立重审通过。虽符合force_only失败类型，评价经验仍未入训练池：提交0、丢弃6287；评价前后学习状态不变。

## 固定状态分布不是物理成绩

固定四预热中256个ACTIVE状态，每个角色一次读取均值/方差；共768状态，无额外critic评分。图中贴边指随机动作分布P(|tanh(U)|≥0.95)，不是物理危险或成功概率；确定性动作是tanh(μ)，不是E[tanh(U)]。

| 256状态的平均指标 | 初始 | A500 | B500 |
|---|---:|---:|---:|
| X随机贴边概率 | 5.63% | 36.77% | 57.35% |
| roll随机贴边概率 | 6.94% | 3.46% | 约2.27e-20% |
| pitch随机贴边概率 | 8.41% | 0.0503% | 约2.00e-20% |
| X确定性动作均值 | +0.0406 | +0.0556 | −0.9480 |
| 相对初始的KL(candidate∥initial)，四轴相加 | 0 | 7.0596 | 8.0518 |

![固定状态分布](fixed_state_distribution_comparison.png)

B旋转分布贴边降低，但X出现持续负偏、平均贴边概率更大，整体KL更高。因此“学习率降低十倍必然使策略更保守”不受本次结果支持。A的X均值接近0掩盖状态间相反方向的大动作，不能只凭均值认为A已稳定。没有B动态成绩，既不能称B保住初始4/4，也不能称B物理失败已证实；不能据旋转指标单独宣布修复成功。

## 成本、完整性与验收范围

| 成本 | 实际 / 批准上限 | 收口处置 |
|---|---|---|
| 正式学习 | A500+B500 / 1000批 | 不加训 |
| 私有数值验证 | 4 / 16事务 | 未用12不追加 |
| 测试前向 | 8 / 128状态 | 未用120不追加 |
| 固定分布诊断 | 768 / 768状态 | 无额外模型调用 |
| 新动态 | A1+B0 / 8 | 未用7不补足、不转为重跑 |
| 跨轮累计动态 | 58 / 本候选累计上限65 | 旧57保留 |
| 旧轮未用 | 19动态/2000批 | 消耗0，不结转 |

收口独立审核新增前向/优化/物理全部0；1011绑定输入、286旧源、45起点产物、49准备文件、4149旧封存、929历史源原字节复核通过。之前216纯协议是9月30日准备证据，本次未重跑，也不与数值/物理数量混加。fault.log仅字体缓存权限提示；保留原日志，后续真实事务与物理归档正常完成，未将其归为运行失败。

**本阶段收口：真实数值实现、A学习复现和失败证据审核通过；效果验收未通过完整证据门，B.2未完成。** 自动跟踪PAUSED，不重试、不续旧预算。历史准备README/assessment/verification、9月月报保持原字节；当前三份滚动资料同步更新。

下一项建议先讨论如何在单独范围和预算下评价已冻结B，再决定是否修正数据覆盖与控制时间尺度；现有证据不足以继续认定仅降低actor率为最有效修复，不建议盲目加训或反复扫描学习率。不得更改已封存停止规则、奖励或保护阈值来追认本轮通过。

## 证据

- [独立执行审核](execution_audit.json)、[效果范围判定](assessment.json)、[固定状态汇总](distribution_summary.json)、[分布图PDF](fixed_state_distribution_comparison.pdf)
- [数值验证](../run/real_validation.json)、[A复现](../run/a_reproduction.json)、[A/B冻结](../run/frozen.json)、[实际成本](../run/accounting.json)、[完整账本](../run/ledger.json)
- [A逐点结果](../run/evaluation_A/results.json)、[尝试收据](../run/evaluation_A/attempts.json)、[原始轨迹](../run/evaluation_A/episodes/x_pos_100/episode.json.gz)、[状态](../run/evaluation_A/episodes/x_pos_100/status.json)、[评价隔离](../run/evaluation_A/verification.json)
- [授权](../authorization.json)、[候选](../candidate_pin.json)、[准备说明（历史）](../README.md)、[启动快照](../startup_assessment.json)

启动日志中“A复现进行中”的 prose 与12:22:57快照阶段B_training不一致；该历史文字保持，现注明：该时刻A已500，B341，物理0，后续最终A/B500均完成；不改快照、预算或实验数据。
'''
with (OUT/'停止结果说明.md').open('x',encoding='utf-8') as stream:stream.write(report)
summary=f'**actor率有限对照已受控停止（2026-10-01）：** [真实数值验证]({STAGE}/run/real_validation.json)4事务/8测试状态通过，[A500精确复现]({STAGE}/run/a_reproduction.json)通过、B500冻结，768固定状态诊断完成。A第一个正X100μm评价力峰值0.025000445 N触发保护，6287周期有效且停稳；按预登记规则停止整组，B动态未执行，完整A/B效果未知。[分布图与结果]({STAGE}/run_analysis/停止结果说明.md)：B旋转贴边降低，但X贴边均值57.35%高于A36.77%，相对初始KL8.052高于A7.060，不能称降率必然更稳。实际1000正式批/1新动态，累计58，余新7次和旧19/2000不执行、自动跟踪PAUSED；实现/复现通过，修复效果未证实，B.2未完成。'
progress=ROOT/'项目进度跟踪.md';text=progress.read_text(encoding='utf-8')
text,n=re.subn(r'^\*\*actor率有限对照执行中（2026-10-01）.*$',summary,text,count=1,flags=re.M);assert n==1
text=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；有限actor率对照受控停止，效果未证实 | [结果与分布图]({STAGE}/run_analysis/停止结果说明.md)、[独立审核]({STAGE}/run_analysis/execution_audit.json)；数值4事务/8状态、A500精确复现、B500冻结 | A首点评价力保护有效停稳，B未动态评价；修复/最终/恢复/独立研究验收仍缺，余新7及旧19/2000不执行 |',text,count=1,flags=re.M)
text=re.sub(r'^\| 6 普通残差SAC \|.*$', '| 6 普通残差SAC | 新授权1000批实际完成，A精确复现、B冻结；768固定分布完成，A首点评价力保护受控停止，B物理未测。B旋转改善/X偏置更大，修复效果未证实，B.2未完成；余新7和旧19/2000不执行 |',text,count=1,flags=re.M)
text=re.sub(r'^\| 8 正式证据与展示 \|.*$','| 8 正式证据与展示 | 10月结果、分布PNG/PDF与完整失败轨迹交付；B动态效果缺失、B.2及恢复/独立研究证据未完成；4个95μm独立点仍未动态执行，原64测试不取用 |',text,count=1,flags=re.M)
text=text.replace('本次独立actor学习率实现与纯协议准备完成；技术导读入口保留，不新增策略收益或A/B/C/D研究阶段验收。',
    '本次真实数值验证、A500复现、B500冻结与停止证据收口完成；未取得修复收益，不新增B.2或C/D研究阶段验收。',1)
text=text.replace('技术导读支持原任务2与8；本次实现与协议准备支持原任务6，不增加实验计数或研究阶段验收。',
    '技术导读支持原任务2与8；本次实际执行支持原任务6与8，新增1000正式批/1动态，收益及B.2仍未验收。',1)
text=re.sub(r'^\| 修复归因与验收范围 \|.*$','| 修复归因与验收范围 | 降率B旋转贴边降低但X偏置/整体KL更大；A首点力保护，B动态未测，完整效果无法判定 | 不把低学习率或旋转改善当修复；先讨论已冻结B的单独评价范围，再决定覆盖/时间尺度候选；500批不覆盖2500批在线阶段 |',text,count=1,flags=re.M)
text=re.sub(r'^\| 单变量与有限对照可比性 \|.*$','| 单变量与有限对照可比性 | 同起点/抽样/全部随机流一致，A真实500学习精确复现；A保护触发预登记整组停止，B未评价 | 不补跑7次，不改旧规则；如需测B须另立范围/预算，不用未配对结果推断收益 |',text,count=1,flags=re.M)
text=re.sub(r'^\| 原项目全量测试 \|.*$','| 原项目全量测试 | 216准备协议为历史已过；本次实际4事务/8状态验证、A500复现和6287周期失败档案独立审核通过 | 非全量测试；B物理效果、4/4能力保持、最终/恢复/独立评价未证实 |',text,count=1,flags=re.M)
next_text=f'''## 下一项交付

本次已批准执行按预登记评价保护门停止，[收口结果]({STAGE}/run_analysis/停止结果说明.md)已归档；当前暂停汇报，不继续训练或补足评价。余新7动态及旧19/2000保持未用，自动跟踪PAUSED。

下一项建议先讨论已冻结B的单独有限评价范围与预算，再根据物理结果决定数据覆盖/控制时间尺度修复；不把仅降低actor率继续当作已证实最有效方案，不盲目加训或扫描学习率。B须保持初始4/4，500固定数据筛选不证明2500批在线失败已修复。新计算/停止规则变化须另行明确；[10月月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)已同步。

'''
text=re.sub(r'## 下一项交付\n.*?(?=## 追加式阶段记录)',next_text,text,count=1,flags=re.S)
log=f'''### 2026-10-01 B.2｜有限actor率实际执行与受控停止收口

{summary}

- 本阶段真实实现/精确复现审核通过，完整效果门未完成，不标策略已验收。原始A轨迹force_only重审、两套停稳、62870子步、学习隔离与全部收据/摘要一致；收口新前向/优化/物理0。
- 1011绑定输入、286旧源、45前项、49准备、4149旧封存和929旧源原字节复核；[执行审查]({STAGE}/run_analysis/独立结果审查.md)，[机器审核]({STAGE}/run_analysis/execution_audit.json)。当前同工作树/分支和未提交资产保留，历史准备与9月月报未改。
- 启动历史prose“A复现进行中”更正说明：12:22:57快照实为A500/B341、B_training、物理0；最终A/B500均完成，不改历史快照。
- 更新同一进度/总览/10月月报的综合状态、数字、负结果、图表和讲稿；阶段收口后暂停汇报，后续另立范围。

'''
text=text.replace('## 追加式阶段记录\n\n','## 追加式阶段记录\n\n'+log,1)
progress.write_text(text,encoding='utf-8')
overview=ROOT/'项目交付总览.md';text=overview.read_text(encoding='utf-8')
text=re.sub(r'^\| actor率有限对照已获批并启动（2026-10-01）.*$',f'| actor率有限对照停止结果（2026-10-01） | [结果与图]({STAGE}/run_analysis/停止结果说明.md)、[独立审核]({STAGE}/run_analysis/execution_audit.json)、[真实验证]({STAGE}/run/real_validation.json) | A500精确复现/B500冻结；A首点力保护停稳、B未动态评价。X偏置增大，不能宣称修复；1新动态/1000批，余新7/旧19与2000不执行 |',text,count=1,flags=re.M)
text=re.sub(r'^\| 下一候选改哪里、有限对照如何限制成本 \|.*$',f'| 下一项如何评估已冻结候选、限制成本 | [实际结果]({STAGE}/run_analysis/停止结果说明.md)、[账本]({STAGE}/run/ledger.json) | 本轮授权已使用1000批/1动态并受控停止；B效果未知。单独评价B需新范围/预算，不补跑、不加训、不追改停止门 |',text,count=1,flags=re.M)
block=f'''### B.2最新实际执行｜actor率有限对照受控停止（2026-10-01）

- **产出：** 独立actor率真实实现验证、A500历史学习精确复现、固定A/B500检查点及768状态分布；A正X评价保护失败6287周期有效停稳，完整轨迹/收据/预算保存。
- **使用与证据：** [结果说明及分布PNG/PDF]({STAGE}/run_analysis/停止结果说明.md)、[独立机器审核]({STAGE}/run_analysis/execution_audit.json)、[效果范围]({STAGE}/run_analysis/assessment.json)、[独立审查]({STAGE}/run_analysis/独立结果审查.md)。只读结果与冻结检查点，不重跑独占入口。
- **限制：** A保护按预登记规则终止整轮，B物理未评价，完整A/B效果与初始4/4保持未知；B旋转贴边改善不能抵消X偏置和KL增大来宣称修复。实际新1动态/1000批、4合成/8测试/768诊断，余新7及旧19/2000未用；PAUSED，无重试，B.2未完成。

'''
text=text.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n'+block,1)
overview.write_text(text,encoding='utf-8')
monthly=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md'
source_log=monthly.read_text(encoding='utf-8').split('## 六、来源记录\n',1)[1]
M='../../learning_chain/b2_actor_lr_execution_20260930'
monthly_text=f'''# D-sub9｜2026年10月滚动月报素材

统计截至：2026-10-01。10月维护同一文件。实时状态见[项目进度跟踪](../../../项目进度跟踪.md)，成果入口见[项目交付总览](../../../项目交付总览.md)；[9月材料](../2026-09/月报素材_2026-09.md)保持历史口径。

## 一、本月综合摘要

{summary.replace(STAGE,M)}

## 二、关键数字与证据

| 内容 | 实际完成 | 上限与解释 |
|---|---|---|
| 真实数值验证 | 4私有事务/8测试状态；首actor差分B/A=0.09999992，其余一致 | 16/128；实现通过不等于策略有效 |
| 正式固定数据学习 | A500精确历史复现、B500冻结，共1000批 | 已达正式上限，不加训 |
| 固定分布诊断 | 初始/A/B各256，共768状态 | 同归档ACTIVE状态，无额外critic评分 |
| 新物理 | A正X1点力保护失败、有效停稳；B0 | 1/8，余7不补；累计58/65 |
| A力/穿透/转角 | 0.025000445 N / 7.00699μm周期末采样 / 0.198736° | 真越限，穿透采样不是子步峰值 |
| A完整轨迹 | 6287周期/62870子步，10.573s力保护、12.574s审核终点 | 评价经验入池0，训练状态不变 |
| X贴边概率/相对初始KL | A36.77%/7.060，B57.35%/8.052 | 固定状态随机分布，非物理危险概率 |
| 历史未用预算 | 19动态/2000批消耗0 | 不结转，跟踪PAUSED |

## 三、负结果与限制

原学习率500批策略在第一个确定性正X评价发生真实力保护；按预登记任何评价保护整组停止，B没有物理成绩，不能称本候选恢复初始4/4或证明B物理失败。降率旋转分布改善，却出现更强X偏置和更大整体KL，不能认定“学习率更低必然更稳”。这次早期固定数据筛选不覆盖2500批在线问题，不支持B.2完成或独立泛化。

通用process_exit对20标failed，账本和最终语义分类确认受控停止，无原生崩溃/写盘失败。日志字体缓存权限提示保留，后续真实验证与物理有效完成；没有将缓存警告归为任务根因。完整失败样本和成本保留，未选择性剔除。

## 四、图表与讲稿

<a id="figures"></a>

![固定状态分布](../../learning_chain/b2_actor_lr_execution_20260930/run_analysis/fixed_state_distribution_comparison.png)

[PNG]({M}/run_analysis/fixed_state_distribution_comparison.png)与[PDF]({M}/run_analysis/fixed_state_distribution_comparison.pdf)：初始/A500/B500在256归档状态的X/Y/roll/pitch随机贴边概率和确定性动作分布。图只能支持固定状态行为差异；不能当完整物理A/B性能图。9月危险价值与停止图继续标历史日期。

讲稿：“独立降低actor学习率的实现通过真实验证，两支500批已固定，原学习率学习状态精确复现。原学习率第一个物理评价触发力保护，所以按既定规则整组停止，候选尚未物理测试。离线诊断显示候选旋转更平缓但X偏置加重，修复效果尚未证实。我们保留全部负结果，不补跑或盲目加训。”

## 五、下一项

本阶段收口后暂停汇报。先讨论单独评价已冻结B的范围与预算，再决定数据覆盖/控制时间尺度修复；不追改本轮停止规则，不用未使用额度自动启动，不以旋转局部改善宣称修复。

## 六、来源记录
'''+source_log+f'''\n2026-10-01收口：[原始轨迹]({M}/run/evaluation_A/episodes/x_pos_100/episode.json.gz)、[实际账本]({M}/run/ledger.json)、[独立审核]({M}/run_analysis/execution_audit.json)、[结果与图]({M}/run_analysis/停止结果说明.md)、[范围判定]({M}/run_analysis/assessment.json)、[独立审查]({M}/run_analysis/独立结果审查.md)。4事务/8测试/1000正式批/768诊断/1新动态；A首点力保护按门停止，B未测，修复未证实。收口审核新前向/优化/物理0，旧字节保持。启动旧文字“A复现进行中”与快照B_training不符，此处注明当时A500/B341、物理0；快照本身正确且未改。
'''
monthly.write_text(monthly_text,encoding='utf-8')
print(json.dumps(dict(published=3,status=assessment['status'],new_dynamic=1,formal_batches=1000),ensure_ascii=False))
