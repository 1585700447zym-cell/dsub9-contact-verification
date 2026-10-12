"""Render the evidence review; does not mutate production or historical stages."""
import json
from pathlib import Path

OUT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation\deliverables\learning_chain\b2_joint_learning_review_20261009')

def main():
    assert not (OUT/'delivery_manifest.json').exists()
    a=json.loads((OUT/'analysis.json').read_text(encoding='utf-8'))
    info=json.loads((OUT/'information_refinement.json').read_text(encoding='utf-8'))
    episodes=a['episodes'];zero=[s for s in episodes if s['id'].endswith('_zero')]
    assert a['total_existing_cycles']==42656 and info['total_vectors_checked']==42664
    stall=sum(e['clipped_fields'].get('stall_span_s[0]',{}).get('occurrences',0) for e in info['episodes'])
    stop=sum(e['clipped_fields'].get('hold_elapsed_s[0]',{}).get('occurrences',0) for e in info['episodes'])
    assert (stall,stop)==(2468,3440)
    route=dict(stage_id='B2-SCOPE-07',status='OFFLINE_REVIEW_COMPLETE',
       decision='JOINT_CANDIDATE_PREPARATION_SUPPORTED_TRAINING_NOT_ADMITTED',
       supports_limited_joint_candidate_preparation=True,new_training_scope_qualified=False,
       training_admitted=False,new_physical_authorization=False,new_training_authorization=False,
       full_B2_accepted=False,C_accepted=False,automatic_tracking='PAUSED',cumulative_dynamic=225,
       new_physics=0,new_policy_forwards=0,new_updates=0,new_replay_publications=0,
       retained_candidates=['J01','J02','J03','J04'],no_contact_functional_controls=['P01','P02','P03','P04'],
       old_scope06_route_unchanged='INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS',
       positive_evidence=['contact feature differences in zero arms','permission at contact and force peaks',
                          'four-axis command effect in 50 contact cycles per joint script','all eight valid and physically stopped'],
       gaps=['no nonzero action at observed force/torque/penetration peak intervals',
             'correlated action magnitude 0.1 does not cover full F50 or proposed exploration',
             'no joint-pose recovery events','stall_span clipping during 2468 permitted SEARCH vectors',
             'case-signed scripts cannot establish deployable inference of correction direction',
             'no noise/repetition/statistical identifiability or learned benefit evidence',
             'discrete 0.25-degree points do not accept original 1.5-degree scope'],
       next_deliverable='B.2联合点动作域与恢复准入登记：先审查时长饱和语义，复用共同守卫和既有恢复证据，登记最少新增缺口预检；通过后才允许另行登记姿态匹配普通SAC短训。',
       unchanged=['137-dimensional observation','physics','controller permissions','reward','protection and success thresholds','closed budgets'],
       scope_note='This is an additional interpretation of sealed development evidence, not an upgrade of SCOPE-06 acceptance.')
    (OUT/'route_decision.json').write_text(json.dumps(route,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text='''# B2-SCOPE-07｜联合姿态点接触信息与作用窗口复核

2026-10-09。当前阶段：B.2；任务：J01～J04离线复核，已完成。本项交付验收只针对证据提取与路线决定，完整B.2/C未验收。

**结论：保留J01～J04作为限定姿态匹配学习的候选开发点，先补动作域、峰值作用和恢复准入；目前不能启动训练。** 零残差档案已提供接触后的信息差异，权限也覆盖接触和峰值时段，无依据把问题归为“观测完全没有信息”或“权限开得太晚”。但小幅脚本只检验了一小段接触作用，未覆盖载荷峰值时段的非零动作和恢复。新发现部分SEARCH观测时长饱和，须审查其状态语义，不能直接扩大观测或修改归一化。

本轮仅读取8份既有完整档案，复核42,656个控制周期及42,664个137维观测；新增物理、策略推理、训练更新、经验发布全0。累计动态225；旧预算关闭，自动跟踪PAUSED。SCOPE-06原路线`INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS`保持，未追认其为完整范围准入。

## 1. 范围、来源与口径

来源为[B2-SCOPE-06封存](../b2_rebound_execution_20261008/delivery_manifest.json)中的J01～J04各zero/script。XY为各±75μm的四联合开发点，roll/pitch为各±0.25°、yaw为0；全部同一F50会话和共同控制器。P01～P04保留为无接触功能对照，不用追加尝试填补接触覆盖。原±1.5°目标、输入±0.5°守卫与本轮离散±0.25°证据是三个不同范围。

控制周期2ms，周期内10个物理子步。力/力矩/穿透峰值只能定位到已有周期区间；本文不虚构具体子步时刻。接触周期按周期末contact_count>0计，与原审核相同；观测和权限取周期开始。原始档案全部开发用途，未新增独立评价。

复现脚本[analyze.py](analyze.py)与[refine_information.py](refine_information.py)只用标准库读取JSON/gzip；不导入仿真或学习库。首次接触、周期/脚本/接触计数、力载荷峰值、命令作用积分和实际运动积分与原收据逐项核对。原始数据、结论和局限分别见[analysis.json](analysis.json)、[information_refinement.json](information_refinement.json)、[逐周期表](joint_cycles.csv)。完整保护/停稳审核继承原封存，不将本次摘要提取冒称重跑物理审核。

## 2. 接触信息存在，但不能把非零数值当成可辨识性证明

8份档案的初始137维向量完全相同。两组zero对称对在共同无接触前159个向量中最大分量差仅约1.10×10⁻¹⁸；首个精确非零差在2ms、约1.32×10⁻¹⁹，不能当作可靠姿态信息。观测以起点为参考，没有直接提供孔位/初始倾角真值。

首次接触为318ms或324ms，均有残差权限且137维向量无裁剪。对称点按各自首次接触事件对齐时，12个选定原始分量（当前六维接触力矩＋相对位姿）中zero为7个不同，script为12个不同；两事件相差6ms，因此Z运动差异不能单独归因于姿态信息。

另按共同324ms对齐两组zero对：两侧均接触、均有权限，12个已归一化分量的最大差分别0.087245和0.098056，主要来自接触力矩；这说明差异并非仅由脚本赋予。它支持保留这些接触开发点，不证明单步能唯一恢复四维误差，不证明有噪声时可分或能选出有效纠偏动作。未训练分类器、扫描阈值或新增观测。

脚本方向由登记工况的`script_sign`指定，首次动作发生在回合22ms，早于318～324ms的首次接触。因此script对称差异包含预先指定的不同动作及历史；不能把它当作可部署策略已从观测辨认方向，也不能在后续actor输入中加入case标签、初始误差真值或该符号。

## 3. 权限、峰值和实际脚本作用

| 档案 | 首接触ms | 力峰所在区间s | 力峰mN | 距25mN保护阈值mN | 峰值权限/请求 | 接触且有权限周期 |
|---|---:|---|---:|---:|---|---:|
'''
    for s in episodes:
        p=s['peak_intervals']['force_N']
        text+=f"| {s['id']} | {s['first_contact']['time_s']*1000:.0f} | {p['time_s']:.3f}～{p['end_time_s']:.3f} | {p['peak_value']*1000:.6f} | {s['force_margin_N']*1000:.6f} | 开放／0 | {s['counts']['contact_permitted_cycles']} |\n"
    text+='''
全部8份档案的力峰发生于INSERT，原残差权限已开放，四维请求均为0。力矩峰在SEARCH、穿透峰在INSERT，也全部有权限但请求为0。这与PC-08历史SEARCH-only策略“峰值早于许可”的现象不同，不能把旧归因移植到当前F50档案。脚本前序动作可能改变后续峰值；这里仅说明峰值当周期未测试非零作用，并非声明脚本对峰值没有因果影响。

最小已观察载荷余量是J02_zero的0.419032mN，即阈值的1.676%。这是单条轨迹的差值，既不是鲁棒安全裕度，也不是失败概率；不据此放宽25mN保护。当前通过只覆盖零残差和规定小幅脚本，不能外推完整探索动作。

四个script各有149个非零周期，分成三段：首次INSERT 49周期（22～120ms，无接触）；SEARCH 50周期（100ms，有接触）；重回INSERT后50周期（无接触）。四轴请求为±[0.1,−0.1,0.1,−0.1]，物理请求幅度5μm/s、0.05mrad/s，四轴相关。四个接触脉冲如下：

| 工况 | SEARCH接触作用区间s | 周期数 | 有效X/Y命令绝对积分μm | roll/pitch命令绝对积分μrad |
|---|---|---:|---|---|
'''
    for s in episodes:
        if not s['id'].endswith('_script'):continue
        p=next(p for p in s['pulses'] if p['phase']=='SEARCH');v=p['command_effect_integral']
        text+=f"| {s['case']['id']} | {p['begin_s']:.3f}～{p['end_s']:.3f} | {p['cycles']} | {v[0]*1e6:.3f}／{v[1]*1e6:.3f} | {v[2]*1e6:.3f}／{v[3]*1e6:.3f} |\n"
    text+='''
合计18,250个周期末有接触，15,122个同时有权限；script非零596周期，其中200周期与接触有效命令作用重合。命令积分不是实际位移，四轴同时非零也不是四个独立方向验证；没有证据支持提高幅度、持续时长或任意探索分布。

每对zero/script的位姿、速度、接触读数及观测在首次动作输入前（含22ms输入）12个向量完全一致。之后实际运动发生差异，按两者共同任务时间内同一时刻的状态对比：

| 工况 | 最大X/Y位置差μm | 最大相对旋转向量X/Y分量差mrad | script−zero任务时间ms |
|---|---|---|---:|
'''
    for p in a['arm_pairs']:
        v=p['max_common_time_xy_difference_m'];w=p['max_common_time_relative_rotation_difference_rad']
        text+=f"| {p['case']} | {v[0]*1e6:.3f}／{v[1]*1e6:.3f} | {w[0]*1000:.4f}／{w[1]*1000:.4f} | {p['task_time_delta_s']*1000:+.0f} |\n"
    text+='''
J03的差异可达约41.94μm；不能因脚本命令很小就认定实际轨迹影响可以忽略。时间差有正有负，且是预定脚本、单次开发配对；不作SAC收益、统计显著性或某一轴的因果效果声明。8/8任务与精度成功沿用原审核，不新增成功样本。

## 4. 全轨迹归一化裁剪与恢复缺口

逐值核对全部42,664个观测的原值/尺度、±10裁剪和已存向量，未发现与冻结变换不一致。**首次接触无裁剪，但整段并非无裁剪。**

| 档案 | SEARCH中stall_span_s饱和向量 | 其中接触向量 | 停止尾段hold_elapsed_s饱和向量 |
|---|---:|---:|---:|
'''
    for e in info['episodes']:
        f=e['clipped_fields'];s=f.get('stall_span_s[0]',{});h=f.get('hold_elapsed_s[0]',{})
        text+=f"| {e['id']} | {s.get('occurrences',0)} | {s.get('contact',0)} | {h.get('occurrences',0)} |\n"
    text+='''
SEARCH受阻时长以0.4s归一化，超过4s后在+10饱和；共2,468个有权限的SEARCH向量，其中2,214个有接触，涉及6/8档案。最大原时长约5.626s。停止尾段保持时长另有3,440次饱和，全部无残差权限且无接触。两者不能混为“活动状态全无损”或“全部都是停止尾段无关项”。本次尚未证明SEARCH饱和是否丢失不可由其他137维字段恢复的决策信息；这是下一准入设计需审查的具体语义问题，不能仅凭饱和认定已有控制错误，也不自动授权改尺度或扩维。

8份联合档案均有UNLOAD，但真实RECOVERING/恢复事件为0；卸载不是回撤恢复。原停止审核8/8通过，不能替代联合姿态下的恢复成功、回撤不足、拒绝/超时和恢复期间残差屏蔽证据。先核对既有恢复资格可继承的来源与范围，只补无法继承的缺项，避免重复整个矩阵。

## 5. 路线决定与完成边界

采用[路线决定](路线决定.md)：保留四个J点作为**待准入的开发候选**，先准备一份B.2联合点动作域与恢复准入登记。优先明确SEARCH时长饱和的状态语义，再登记覆盖接触峰值窗口、拟用探索幅度/时长/方向和真实恢复的最少预检。实际预检需新的具体登记和授权；有普通失败按原规则记录，不无限补采直到通过。通过后才另行登记同姿态分布的普通残差SAC、共同零残差/零更新参照、保存恢复和冻结评价。

不追加P点补接触，不重开旧预算，不启动C，不更改137维观测、保护、成功阈值、物理范围或奖励。原±1.5°完整目标继续列为未完成；如果将来要把完整B.2目标正式收缩到离散小倾角，需要单独明确范围变更，不能用本报告替代。候选设计、物理准入、学习效果、冻结后独立评价分别验收。

本项最终封存和来源保护检查见[verification.json](verification.json)，历史文件与生产来源摘要保持。按项目协作约定，本可交付阶段完成后暂停汇报。
'''
    (OUT/'结果说明.md').write_text(text,encoding='utf-8')
    (OUT/'路线决定.md').write_text('''# B2-SCOPE-07｜路线决定

2026-10-09。当前阶段：B.2；任务：联合姿态点离线复核，已完成。

**决定：保留J01～J04作为限定姿态匹配学习的候选开发点；先补准入设计，不启动训练。**

支持保留的事实：zero档案在接触后具有可记录的信息差异；原权限覆盖首次接触和峰值；四个script均有50个接触周期的四轴有效命令作用；8/8有效停稳。没有依据宣称必须先扩大137维观测或把现有权限改为更早开启。

暂不准入的具体原因：

1. 小幅脚本未覆盖力、力矩和穿透峰值当周期的非零作用；力峰最小余量只有0.419mN（25mN阈值的1.676%）。四轴相关的0.1幅度、100ms接触脉冲不代表完整F50或预热探索域。
2. 联合点真实恢复事件0；UNLOAD和停止合格不能代替回撤/恢复覆盖。
3. 2,468个有权限SEARCH向量的受阻时长饱和，其中2,214个有接触。需审查其他既有字段能否保留所需状态信息，未证明必须改观测。
4. script方向由工况指定，且先于接触；其差异不能证明可部署纠偏判断。零残差信息差异没有噪声、重复或统计辨识证据，配对脚本也没有一致用时收益。

下一交付为**B.2联合点动作域与恢复准入登记**：先核对时长饱和语义和可继承的旧恢复证据，再固定最少新增预检、原保护下的停止条件、完整成本及失败出口。只有该具体方案获新的执行授权才可运行；预检通过后另行登记普通SAC的姿态匹配短训、共同参照及冻结评价。这里没有签发任何新额度。

P01～P04保留无接触功能对照；不为填覆盖追加它们。当前±0.25°离散点不能验收原±1.5°目标，也不等于±0.5°输入边界合格。完整B.2/C未验收，C物理接入继续暂缓。

新增物理/推理/更新/经验发布0，累计动态225，自动跟踪PAUSED，旧预算关闭。SCOPE-06原路线与历史失败不改写。详见[证据与口径](结果说明.md)、[机器决定](route_decision.json)、[观测复核](information_refinement.json)。本阶段结束暂停汇报。
''',encoding='utf-8')
    print(json.dumps(dict(status='REPORTS_WRITTEN',existing_cycles=42656,vectors=42664,active_clipping=stall,stop_clipping=stop),ensure_ascii=False))

if __name__=='__main__':main()
