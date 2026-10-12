"""Turn the recorded offline evidence into a result and route decision."""
import sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from analyze import read,write,sha
def tables(d):
    result='| 点 | F0→F2000任务时间（秒） | INSERT差值 | UNLOAD差值 | SEARCH差值 | 总差值 |\n|---|---:|---:|---:|---:|---:|\n'
    precision='| 点 | F0终末XY（μm） | F2000终末XY（μm） | F2000终末角（°） | 80μm/0.5°附加精度 |\n|---|---:|---:|---:|---|\n'
    for c in d['comparisons']:
        delta=c['phase_delta_s'];r=next(r for r in d['records'] if r['case_id']==c['case_id'] and r['model']=='F2000')
        result+=f'| {c["case_id"]} | {c["F0_task_s"]:.3f}→{c["F2000_task_s"]:.3f} | {delta.get("INSERT",0):+.3f} | {delta.get("UNLOAD",0):+.3f} | {delta.get("SEARCH",0):+.3f} | {c["task_delta_s"]:+.3f} |\n'
        precision+=f'| {c["case_id"]} | {c["F0_xy_um"]:.2f} | {c["F2000_xy_um"]:.2f} | {r["archive_end_state"]["angle_to_identity_deg"]:.3f} | F0通过／F2000未通过 |\n'
    return result,precision
def main():
    if (OUT/'结果说明.md').exists() or (OUT/'delivery_manifest.json').exists():raise FileExistsError('Preserve first result report')
    d=read(OUT/'diagnosis.json');time_table,precision_table=tables(d)
    if d['archive_count']!=8 or d['additional_precision_successes']!={'F0':4,'F2000':0}:raise ValueError('Unexpected result')
    r0=next(r for r in d['records'] if r['model']=='F0' and r['case_id']=='J01');r2=next(r for r in d['records'] if r['model']=='F2000' and r['case_id']=='J01')
    s0=next(s for s in r0['segments'] if s['phase']=='SEARCH');s2=next(s for s in r2['segments'] if s['phase']=='SEARCH')
    post='| 点／演员 | 最后INSERT入口XY（μm） | 最后INSERT出口XY（μm） | 该段真实XY路径（μm） |\n|---|---|---|---:|\n'
    for r in d['records']:
        s=[s for s in r['segments'] if s['phase']=='INSERT'][-1]
        fmt=lambda p:', '.join(f'{x:.2f}' for x in p[:2])
        post+=f'| {r["case_id"]}／{r["model"]} | ({fmt(s["entry"]["position_um"])}) | ({fmt(s["exit"]["position_um"])}) | {s["actual_xy_path_um"]:.2f} |\n'
    reward='| 点 | 总奖励变化 | 时间项变化 | 力项变化 | 扭矩项变化 | 终末项变化 |\n|---|---:|---:|---:|---:|---:|\n'
    for c in d['comparisons']:
        v=c['reward_delta'];reward+=f'| {c["case_id"]} | {v["total"]:+.4f} | {v["time"]:+.4f} | {v["force"]:+.4f} | {v["torque"]:+.4f} | {v["terminal"]:+.1f} |\n'
    report='# B2-SCOPE-21｜四点耗时与精度变化的离线归因\n\n当前阶段：B.2第3项；本次仅分析既有档案，不执行新训练或物理。\n\n'
    report+=('**结论：当前F2000仍不适合作为已达到预期效果的普通SAC基线。** 平均耗时改善2.77%未达10%；J02绕开卸载/搜索的收益被J01搜索变慢抵消。'
             '更重要的是，既有80μm/0.5°附加精度由F0的4/4降至F2000的0/4，四点均因XY偏差未通过。'
             '功能成功4/4保持原判据；不能把它解释为精细对中保持。下一项优先准备共同精度目标与奖励的一致性候选，暂不加训或扩展C机制。\n\n')
    report+='## 耗时差在哪一段\n\n'+time_table
    report+=('\n正值为F2000更慢。STOPPING成功确认约0.240秒，四对差值近0；每份task_end后的审核尾段约1.760秒，单列而未混入任务时间。'
             '同周期输入观测定义阶段；左侧trace的policy_phase在切换边界可滞后一周期，不用它分配时间。\n\n'
             'J01总增加3.096秒，其中SEARCH增加3.084秒（约99.61%），其他段合计仅0.012秒。'
             'F0搜索1.680→3.970秒，F2000搜索1.682→7.056秒；两者都由SEARCH_ADVANCED正常返回INSERT，没有边界耗尽、保护或运行故障。\n\n'
             'J02减少4.068秒：免去0.782秒卸载和2.814秒搜索，再减少0.472秒INSERT。F0出现AXIAL_STALL→LOW_LOAD_SEARCH→SEARCH_ADVANCED；'
             'F2000没有这三个控制事件，始终INSERT至目标平面4.098秒，随后成功确认至4.338秒。这个改进发生在进入搜索之前，不能只靠修改搜索解释它。\n')
    report+='\n## J01搜索路径与命令证据\n\n'
    report+=f'J01实际XY路径{s0["actual_xy_path_um"]:.2f}→{s2["actual_xy_path_um"]:.2f}μm，参考路径{s0["reference_xy_path_um"]:.2f}→{s2["reference_xy_path_um"]:.2f}μm；退出螺旋角{s0["exit_theta_rad"]:.3f}→{s2["exit_theta_rad"]:.3f}rad。实际绕行更多，退出更晚。\n\n'
    report+=f'搜索XY请求积分F0为({s0["requested_xy_integral_um"][0]:.2f}, {s0["requested_xy_integral_um"][1]:.2f})μm，F2000为({s2["requested_xy_integral_um"][0]:.2f}, {s2["requested_xy_integral_um"][1]:.2f})μm；实际总命令层即时干预积分X为{s0["effective_command_delta_xy_integral_um"][0]:.2f}→{s2["effective_command_delta_xy_integral_um"][0]:.2f}μm。共享速度/变化率限制令请求与即时干预不同；这些积分均不是物理位移或零残差物理反事实。\n\n'
    report+=('全部启用动作的预测与执行总命令一致，所有周期权限核对通过；搜索参考逐周期积分核对通过，7段搜索的reference/continuation过滤次数均0。'
             '数据没有显示残差未执行或参考审核误截断，不能优先归因于实现丢动作。已训演员改变了搜索与接触轨迹。\n\n'
             '不能把上述差异简化为“径向向外导致失败”：J01已训演员相对局部搜索参考的平均径向请求为负，实际最终也正常通过搜索。'
             'INSERT后的两次搜索入口位置和姿态不同；相同elapsed/theta对照仅对齐记录坐标，不能隔离演员、入口状态和接触响应的独立因果贡献。\n')
    report+='\n## 功能与附加精度分别统计\n\n'+precision_table
    report+=('\n上表终末为完成审核后的载体原点全局XY范数，以及单位四元数相对目标正姿的总转角。任务结束时同样为F0 4/4、F2000 0/4，故结果不是1.760秒审核尾段造成。'
             '四个F2000末态角均小于0.5°，未通过项均为XY。载体偏差不是针孔最小几何裕度，不能据此否认九针已有功能装配判定。\n\n'
             '冻结tools/model/layered_task.py::functional_finish使用层内针脚几何、Z、速度、载荷和穿透，未把finish_criteria中的xy_tolerance_m或angle_tolerance_rad作为额外门槛。'
             '这是已登记功能判据的既有实现；本轮不修改它、不重贴SCOPE20功能标签。80μm/0.5°附加指标在此前PC-09已单列使用，本次只复算其现有档案值，不能把它事后替换为原10%主判据。\n')
    report+='\n### 精度退化发生在何处\n\n'+post
    report+=('\nJ01/J03/J04在搜索退出时已到约47.13/34.71/38.03μm的全局XY偏差，随后有权限的INSERT阶段末态升到100.49/98.09/100.21μm。'
             '因此精度退化不能全部归因于搜索纠偏不足。J02没有搜索，直插更快且接触峰值降低，但停稳XY仍84.23μm。'
             '这支持“学习到的INSERT运动没有保持附加对中精度”，不证明某一个动作通道或训练机制是唯一原因。\n')
    report+='\n## 奖励为何没有直接排除这种结果\n\n'+reward
    report+=('\n逐周期复算42,171条奖励：累计最大Z进展5×增量/4mm，时间−0.1×dt，力−0.2×dt×(F/0.025)²，扭矩−0.2×dt×(T/0.0005)²，功能成功终末+10。'
             '奖励全档案累计，包括审核尾段；diagnosis另列任务和尾段贡献。所有回合终末奖励均+10、进展项约5，无终末XY/角度精度项。'
             'J02总奖励增加0.6201，主要来自时间和接触力改善；其84.23μm末态没有独立扣分。J01总奖励下降0.4693，说明既有目标本身也不奖励这次变慢；'
             '不能据此说奖励完全反向，更不能断言改奖励必然解决学习。\n\n'
             '这构成可验证的目标缺项：如果论文目标还包含80μm精细对中，现有功能终末奖励不足以表达该目标。'
             '同时，8档案137维初始输入逐值一致，同一演员四点初始动作逐值一致；初始绝对联合位姿是环境/裁判输入，当前相对观测在复位瞬间不直接区分四个点。'
             '这限制了对“首步按象限纠偏”的期待，但接触后反馈可以区分状态，不能据此认定整轮不可学习或立即扩观测。\n')
    report+='\n## 路线与证据边界\n\n'
    report+=('已确认：耗时差的阶段来源、J01真实绕行和晚退出、J02直插避开停滞、末段XY漂移、既有奖励/功能口径未包含附加精度。'
             '未确认：critic误差、熵项、数据顺序或单通道作用是否为唯一学习成因；没有critic评分、动作消融、物理反事实或新种子证据。\n\n'
             '路线决定见[路线决定](路线决定.md)：下一项只做普通SAC共同精度目标与奖励一致性候选的离线准备；保留137维/4维、物理与功能判据，先写明附加精度的开发用途、候选精度奖励、同版本公平对照和一次有限执行方案。'
             '实质目标变更先提交可审阅方案，当前不修改执行版本、不签发新科学授权。独立测试仍0，完整B.2/C未验收，累计动态254，自动跟踪PAUSED。\n\n'
             '本轮新增模型构造/张量加载/策略及critic前向/物理/优化/经验发布均0。8项标准库边界测试先失败后通过，原始8档案全周期权限、预测/执行、奖励和来源核对通过。'
             '这只验收本次离线归因，不是全项目运行时测试。SCOPE20的2000更新和功能4/4、原覆盖缺口及所有旧失败保持。\n\n'
             '证据：[诊断JSON](diagnosis.json)、[阶段明细](phase_summary.csv)、[完整周期](cycles.csv)、[搜索对齐](search_alignment.csv)、[来源登记](registration.json)、[限定审查](review.md)、[收口核验](verification.json)。'
             'analyze.py拒绝覆盖首次分析；verify_delivery.py只读核验，滚动文档推进后省略--current-docs。本阶段完成后暂停汇报。\n')
    (OUT/'结果说明.md').write_text(report,encoding='utf8')
    route='# B2-SCOPE-21｜路线决定\n\n当前阶段：B.2第3项；本次离线路线决定已形成，下一候选尚未开始。\n\n'
    route+=('**先准备普通SAC共同精度目标与奖励的一致性候选，暂不追加现有目标下的训练，也不直接扩展C机制。**\n\n'
            '依据：J01增加3.096秒，99.61%来自搜索；J02免去卸载/搜索而快4.068秒，四点平均仅改善2.77%，未达10%。'
            'F0附加80μm/0.5°为4/4，F2000为0/4；J01/J03/J04在搜索后INSERT再次漂离中心，J02直插快但精度仍不合格。'
            '既有奖励没有终末精度项，功能判据容许这些末态；所以应先明确普通SAC要达到的共同目标，而不是将功能成功当作精细对中或只加训练量。\n\n'
            '下一项仅离线：保留137维/4维、物理模型、共同保护及旧功能判据，设计单一、可核验的终末精度奖励候选；'
            '把80μm/0.5°作为明示的开发目标，明确其与10%耗时条件的并列用途、实现位置和共同版本。'
            '预先列同版本F0/训练后F/必要B2对照、旧开发数据可复用范围和一次有限预算。先审阅目标改变的影响，不直接执行。\n\n'
            '该建议针对已确认的目标缺项；未证明新奖励必胜。对时间差尚只能说明已训策略改变了轨迹，不能唯一归因critic、熵、数据顺序或观测缺失。'
            '不改变旧成功标签、10%主判据或覆盖缺口；旧预算不重开，独立测试0，累计254，自动跟踪PAUSED。\n')
    (OUT/'路线决定.md').write_text(route,encoding='utf8')
    write(OUT/'route_decision.json',dict(stage_id='B2-SCOPE-21',decision='prepare_common_precision_reward_candidate_offline',
        basis=['J01 extra SEARCH duration','J02 avoids unload and search','2.77 percent below 10 percent','additional precision F0 4/4 versus F2000 0/4','post-search INSERT drift','existing reward omits terminal precision'],
        candidate_implemented=False,next_task_started=False,new_scientific_execution_authorized=False,old_outcomes_changed=False,primary_threshold_changed=False,
        only_learning_cause_identified=False,full_B2_accepted=False,C_accepted=False,independent_tests=0))
    print('Result report and route decision prepared from fixed archive evidence.')
if __name__=='__main__':main()
