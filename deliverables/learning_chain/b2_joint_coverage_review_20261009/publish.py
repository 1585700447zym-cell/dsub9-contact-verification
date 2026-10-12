"""Publish the completed development review without changing old rules or runtime."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(OUT))
from analyze import read,sha,write

def main():
    if (OUT/'route_decision.json').exists():raise PermissionError('Review already published')
    data=read(OUT/'coverage_comparison.json');assert not data['recommended_per_case_endpoint_gaps']
    keep=['共同模型、几何、成功和保护阈值、2ms控制周期、F50动作范围及137维观测',
        '每个J点均有接触中的四轴正负有效命令；快速和长保持两种时序仍都要有证据',
        '全部原始回合的有效性、物理停稳、保护与峰值审核，以及4项真实回撤／恢复证据',
        '逐项A/B覆盖统计、全部失败、旧判据结论与独立评价边界']
    change=['只把时序覆盖汇总层级从“每个J点的每种A/B测试各自满足”改为“每个J点合并A/B满足”',
        '周期末接触判据保持；周期内部峰值单列用于诊断，不拿瞬时峰值替代全部覆盖',
        '允许复用已经审核并绑定来源的开发证据，取消为填满测试类型×时序表而默认追加物理回合']
    next_task='准备四个离散J点上的普通F50残差SAC小规模训练与共同参照：接入既有学习／检查点代码，冻结数据用途、训练与评价顺序、具体次数／更新／墙钟上限和停止规则，完成离线接线检查后交付一次具体执行申请。覆盖专项补验建议0；运行来源或接口改变时重新判断受影响检查。'
    decision=dict(stage_id='B2-SCOPE-11',status='OFFLINE_REVIEW_COMPLETE',route='PREPARE_LIMITED_JOINT_SAC_PILOT_NO_COVERAGE_RERUN',
        adopted_recommendation='per_joint_case_endpoint_coverage_v2',gate_status='DEVELOPMENT_RECOMMENDATION_NOT_RUNTIME_ADMISSION',
        development_driven_post_hoc_revision=True,old_gate_regraded=False,old_route=data['old_route_preserved'],
        recommended_extra_coverage_episodes=0,training_admitted=False,full_B2_accepted=False,C_accepted=False,
        new_physical_attempts=0,new_training=0,cumulative_dynamic=237,automatic_tracking='PAUSED',
        retained=keep,revised=change,next_task=next_task,
        scope='Only the four fixed J01-J04 initial poses at XY±75um and roll/pitch±0.25deg; no interpolation or original±1.5deg qualification',
        limits=['Representative engineering evidence only, not a safety proof for arbitrary actions',
            'No learned policy, statistical success rate or independent test conclusion',
            'A new learning execution must bind this recommendation explicitly; no old grant or qualification is reopened'])
    write(OUT/'route_decision.json',decision)
    gate=dict(version='per_joint_case_endpoint_coverage_v2',status=decision['gate_status'],purpose='Evidence for preparing a bounded ordinary-SAC pilot',
        scope=decision['scope'],input_episodes='All fixed SCOPE10 episodes; no deletion or cherry-picking',
        all_attempts_require='audited, simulation_valid, physically_stopped, no hard guard violation; task failures trigger separate route review',
        each_joint_case_require=['across A/B, original permission + endpoint contact_count>0 + any abs(effective_command_delta)>1e-15 in each hold duration 50 and 1',
            'a nonzero newest wrench in the subsequent recorded policy observation for at least one such cycle per hold duration',
            'each of X,Y,roll,pitch has both effective command signs during endpoint contact across A/B',
            'existing recorded observation differences, with no claim of full observability'],
        per_episode_require='original maximum-force overlap; torque and penetration overlap reported separately',
        recovery_require='each J engineered recovery audit covered, actual retraction>=200um, masks/reanchor/net-origin/resume effect/stop retained',
        removed_requirement='both hold durations in every individual A/B profile, regardless of coverage in the other profile for the same J case',
        original_endpoint_rule_preserved=True,substep_peak_rule_used_for_qualification=False,
        old_gate_unchanged=True,runtime_implementation_changed=False,training_admitted=False)
    write(OUT/'recommended_gate_v2.json',gate)
    baseline=[]
    folder=OUT.parent/'b2_rebound_execution_20261008/run'
    for p in sorted(folder.glob('J0*_zero.audit.json')):
        a=read(p);baseline.append(dict(file=str(p.relative_to(ROOT)).replace('\\','/'),sha256=sha(p),
            archive_sha256=a['archive_sha256'],outcome=a['assessment']['outcome'],
            task_time_s=a['assessment']['failure_penalized_task_time_s'],reuse_status='CANDIDATE_SUBJECT_TO_PILOT_COMMON_SOURCE_EQUIVALENCE'))
    write(OUT/'pilot_preparation_scope.json',dict(stage_id='B2-SCOPE-11',scope='four fixed discrete J cases only',
        new_coverage_preflight_recommended=0,baseline_reuse_candidates=baseline,execution_authorized=False,
        ordinary_SAC_only=True,new_case_matched_training=True,old_weights_not_automatically_inherited=True,
        required_before_execution=['bind common physical/control/observation/reward/runtime sources and check affected baseline equivalence',
            'specify zero-start learner or explicitly justified origin, matched collection/replay, and all learning hyperparameters',
            'freeze exact counts of environments/resets/steps/updates/forwards/loads, wall limit and closed no-retry exits',
            'verify joint-case mapping, masks, terminal/replay boundaries, complete checkpoint and independent-process resume using existing code',
            'declare development use; freeze main metric and failure accounting before seeing pilot results; no reuse of untouched final tests'],
        suggested_primary_metric='failure-penalized task time, conditional on reporting functional success and guard failures; loads also reported',
        metric_status='suggestion for next registration, no new effect threshold chosen from pilot outcomes',
        later_B2_requirements=['repeatable small-scale learning and matched task evaluation','frozen independent evaluation','formal treatment of original wider range']))
    table='\n'.join(f"| {k} | {c['holds']['50']['endpoint_effect_cycles']} | {c['holds']['1']['endpoint_effect_cycles']} | {c['holds']['1']['next_observation_nonzero_wrench_cycles']} | 四轴均有正负 |" for k,c in data['cases'].items())
    report=f'''# B2-SCOPE-11｜接触覆盖条件复核与最小处理方案

2026-10-09。当前阶段：B.2第2项；任务：接触工况覆盖条件的离线复核，已完成。本轮没有运行仿真或训练。

**建议采用按初始工况合并A/B证据的覆盖条件，下一项直接准备四点普通SAC小规模训练；新增覆盖专项回合建议0。** 这是查看开发结果后的公开修订，不是预先冻结的独立验证，也不把SCOPE10按原判据判成通过。当前执行器、原始档案、旧合同和旧授权都未改；训练仍未准入。

## 为什么可以调整

原清单要求每个J点的单轴A和组合B分别在50周期与1周期段出现接触作用。代表性动作、接触信息和工程恢复是准备学习所需的证据，但“测试类型×保持时间”的每格都非零，是SCOPE08为这轮预检选定的保守检查设计，并非训练合同要求的普遍物理定律。

A/B使用同一F50会话、动作合成、权限、驱动保护和137维观测。测试配置只改变送入同一接口的指令序列，因此同一J点的A/B可以共同提供代表性证据。该判断只支持有限开发试训，不支持任意连续动作安全、各轴在各种频率下均被穷尽，或扩大初始化范围。

## 全部档案复算结果

重新读取8份A/B完整档案，逐周期结果与原审核一致。下表计数仍严格使用“原权限开放＋周期末有接触＋非零有效命令”，未用周期内峰值放宽条件。

| 初始工况 | 长保持段接触有效命令周期 | 快速段接触有效命令周期 | 快速段后续观测有非零六维力／力矩信号 | 接触方向 |
|---|---:|---:|---:|---|
{table}

四点合计快速115周期，长保持8046周期；这些周期的下一次观测均记录到非零六维接触力／力矩。该结果只证明记录中存在信号，不证明充分可观测性、统计显著性或学习收益。有效命令增量是同状态零残差命令的差值，不是对插入效率的因果贡献。

原12项审核／物理停稳和功能结果、4项工程恢复、24项力／力矩／穿透峰值重叠均保留。恢复夹具不进入训练经验或自然恢复成功率。原3处逐profile快速覆盖缺口原样保留，逐项计数见[机器复算](coverage_comparison.json)。

## 三种处理路线比较

| 方案 | 现有证据 | 取舍 |
|---|---|---|
| 仅把周期末接触改为周期内峰值 | 仍有J02_B快速缺口；J03/J04各仅新增1个非零有效命令共现周期 | 不优先；接触峰值和控制可用反馈不应混成一项 |
| 按每个J点合并A/B，保留原周期末定义 | 四点均有两种时序、四轴正负方向与实测反馈 | 推荐；删除重复的交叉覆盖要求，保留物理条件 |
| 保留原逐profile要求，重新安排脉冲并补测 | 三处旧缺口仍需新证据，补测也不保证发生目标接触 | 仅在研究问题确实需要逐profile频率覆盖时采用；本次不推荐 |

## 保留与修改

保留：{'；'.join(keep)}。

修改：{'；'.join(change)}。

新条件见[recommended_gate_v2.json](recommended_gate_v2.json)。它是下一次小规模训练登记采用的建议，不是把旧runner的资格开关改成true。本次没有理由放宽力、运动保护或插入成功标准，也不改变动作幅度、频率、观测、奖励、模型或基线。

## 进入训练前还需要什么

{next_task}

现有SCOPE06四个J零残差档案可作为共同参照的复用候选；必须先核对接入后的共同来源、初始点、计时和评价口径，不能只凭4/4成功跨版本比较。四点均是开发工况；不把重复这四点称为独立泛化测试，也不把当前成功比例当成未来策略收益。

下一登记要一次明确：四点采样与数据用途、学习起点／超参数、预热与更新、检查点保存／独立进程恢复、训练和评价的全部次数及停止条件。现有成熟实现可复用，不应重建整套训练系统。指标建议以失败惩罚任务用时为主，同时报告成功、保护、载荷；具体门槛在新试验前确定。完成这些接入和登记工作，才执行小规模训练与评价。

若后续改变物理范围、公共接口或观测定义，只复验受影响部分；本次“覆盖专项0”不等于豁免未来改变的检查。

## 范围与来源

本次为开发数据驱动的条件修订建议，原3处缺口与旧路线不改；不作为论文方法效果。新物理／训练均0，累计237，自动跟踪PAUSED，完整B.2/C未验收。四个离散±75μm／±0.25°点不代表原±1.5°连续范围。

来源：[本轮原结果](../b2_joint_preflight_execution_20261009/结果说明.md)、[接触口径更正](../b2_joint_coverage_clarification_20261009/更正说明.md)、[训练合同v3](../../../docs/stage_b/训练合同_v3.md)、[当前计划](../../../研究推进计划_当前版.md)。源码位置和SHA见[registration.json](registration.json)，[训练准备边界](pilot_preparation_scope.json)记录仍需完成的具体事项。
'''
    (OUT/'结果说明.md').write_text(report,encoding='utf-8')
    print('Review recommendation and pilot-preparation boundary published; no runtime change.')

if __name__=='__main__':main()
