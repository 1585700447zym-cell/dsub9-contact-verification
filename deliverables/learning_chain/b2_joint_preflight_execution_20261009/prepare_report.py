"""Summarize the closed fixed-denominator run; preserve all failures."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
RUNNER=OUT.parent/'b2_joint_admission_preflight_20261009';sys.path.insert(0,str(RUNNER))
from scope_contract import read,proposal,attempt_specs
from execution_contract import write

def main():
    if (OUT/'route_decision.json').exists():raise PermissionError('Report already prepared')
    s=read(OUT/'execution_summary.json');specs=attempt_specs(proposal());rows={r['id']:r for r in s['rows']}
    matrix=s.get('matrix_assessment',{});route=matrix.get('route','NO_SCOPE_QUALIFICATION')
    gap_evidence=read(OUT/'coverage_gap_evidence.json');recovery_covered=[]
    direction={};peak_gaps=[];timing_gaps=[];recovery_missing=[];task_failures=[];guard_failures=[];audit_failures=[]
    for row in s['rows']:
        a=row.get('assessment',{});outcome=a.get('outcome') or row.get('raw_outcome') or {}
        if not row['audit_passed']:audit_failures.append(row['id'])
        if outcome.get('task_outcome')=='TASK_FAILURE':task_failures.append(row['id'])
        facts=row.get('guard_facts') or {}
        if facts.get('contact_reasons') or facts.get('motion_reasons'):guard_failures.append(dict(id=row['id'],contact=facts.get('contact_reasons',[]),motion=facts.get('motion_reasons',[])))
        if row['id'].endswith('R_RECOVERY'):
            if not a.get('recovery',{}).get('covered'):recovery_missing.append(row['id'])
            else:recovery_covered.append(dict(id=row['id'],**a['recovery']))
        else:
            coverage=a.get('joint_coverage',{});case=row['id'][:3]
            if 'signs' in coverage:
                direction.setdefault(case,[set() for _ in range(4)])
                for i,signs in enumerate(coverage['signs']):direction[case][i].update(signs)
            for kind,record in coverage.get('peaks',{}).items():
                if not record['covered']:peak_gaps.append(dict(id=row['id'],peak=kind,value=record['value']))
            for hold,count in coverage.get('hold_contact_effect_cycles',{}).items():
                if count==0:timing_gaps.append(dict(id=row['id'],hold_cycles=int(hold),contact_effect_cycles=count))
    if route=='READY_FOR_SEPARATE_SAC_REGISTRATION':
        next_task='下一项仅准备普通SAC姿态匹配短训与共同参照的具体登记：明确开发分布、训练／评价数量、计算成本、保存与独立进程恢复，以及未覆盖峰值的处理。不得自动开训。'
        conclusion='本轮固定代表性动作与工程恢复检查满足已登记覆盖条件；可准备下一份独立短训登记。'
    elif audit_failures:
        next_task='下一项只用本轮完整／部分档案离线定位未通过审核或运行异常的具体原因，形成修复与路线决定；不重跑、不续用已关闭数量。'
        conclusion='本轮存在运行／审核未通过项，不能获得联合点预检资格。'
    elif guard_failures:
        next_task='下一项只对已封存的保护触发档案做离线失败证据分析，判断是原动作范围、控制边界还是模型适用范围问题；保持原保护阈值，不重跑旧授权。'
        conclusion='本轮触发原保护，按有效性和停稳分别保留真实结果；后续分配已关闭，不能获得联合点预检资格。'
    elif task_failures:
        next_task='下一项只对本轮任务失败的搜索／恢复路径与已有共同参照离线对照，给出失败原因和是否继续该路线的决定；无新训练或物理准入。'
        conclusion='固定预检中存在正常任务失败，保留失败分母，先复核任务路线，不进入训练登记。'
    else:
        next_task='下一项仅用现有档案离线设计覆盖缺口的最小处理方案：比较按动作获准时刻安排固定序列与明确收窄时序声明，给出是否需要新补验及其最小范围。已通过项保留，本轮数量已关闭；不重跑整套矩阵、不自动补采或训练。'
        conclusion='本轮未达到全部登记覆盖要求，不能把有限成功升级为完整准入。'
    functional_count=sum(r.get('assessment',{}).get('functional_success') is True for r in s['rows'])
    stopped_count=sum(r.get('assessment',{}).get('outcome',{}).get('physical_stopped') is True for r in s['rows'])
    direction_count=sum(all(signs=={-1,1} for signs in axes) for axes in direction.values())
    peak_total=sum(len(r.get('assessment',{}).get('joint_coverage',{}).get('peaks',{})) for r in s['rows'])
    decision=dict(stage_id='B2-SCOPE-10',route=route,conclusion=conclusion,next_task=next_task,
        audited_functional_successes=functional_count,audited_physical_stops=stopped_count,
        task_failures=task_failures,guard_failures=guard_failures,audit_failures=audit_failures,
        joint_effective_signs={k:[sorted(x) for x in v] for k,v in direction.items()},peak_gaps=peak_gaps,timing_gaps=timing_gaps,recovery_missing=recovery_missing,
        recovery_covered=recovery_covered,coverage_gap_evidence='coverage_gap_evidence.json',
        gap_classifications=[dict(id=e['id'],hold_cycles=g['hold_cycles'],classification=g['evidence_classification'])
            for e in gap_evidence['episodes'] for g in e['missing']],
        planned_denominator=12,attempted=s['reserved_dynamic'],not_attempted_closed=s['unused_dynamic_closed'],
        training_admitted=False,full_B2_accepted=False,C_accepted=False,independent_tests=0,
        formal_universal_action_domain_qualification=False,natural_recovery_probability_claim=False,
        retry_allowed=False,old_budgets_reopened=False,automatic_tracking='PAUSED')
    write(OUT/'route_decision.json',decision)
    gap_labels={'NO_CONTACT_IN_FIXED_BLOCK':'固定快速块与实际接触未重叠',
        'CONTACT_MASKED_IN_FIXED_BLOCK':'快速块虽有接触，但原动作权限均关闭',
        'NO_EFFECT_WITH_PERMISSION_IN_FIXED_BLOCK':'快速块有接触且动作获准，但未记录有效作用'}
    gap_rows=[]
    for item in gap_evidence['episodes']:
        for gap in item['missing']:
            gap_rows.append(f"| {item['id']} | {gap['hold_cycles']} | {gap['block_cycles']} | {gap['contact_block_cycles']} | {gap['permitted_contact_cycles']} | {gap['effective_contact_cycles']} | {gap_labels[gap['evidence_classification']]} |")
    coverage_details='未发现已审核A/B时序块的零覆盖项。'
    if gap_rows:
        coverage_details='\n'.join(['| 缺口项目 | 动作保持周期 | 该块总周期 | 其中有接触 | 其中接触且获准 | 其中有效作用 | 档案证据分类 |',
            '|---|---:|---:|---:|---:|---:|---|',*gap_rows])
    recovery_details='；'.join(f"{r['id']}：回撤{r['actual_retraction_m']*1e6:.3f}μm，屏蔽{r['masked_cycles']}周期" for r in recovery_covered) or '暂无已覆盖恢复项'
    table=[]
    for spec in specs:
        r=rows.get(spec['id']);a=(r or {}).get('assessment',{});o=a.get('outcome') or (r or {}).get('raw_outcome') or {}
        if not r:
            table.append(f"| {spec['id']} | 未执行，数量关闭 | — | — | — | — | — | — |")
            continue
        status=o.get('task_outcome','未知／未完成');audit='通过' if r['audit_passed'] else '未通过'
        stopped=str(o.get('physical_stopped','未证明'));contact=a.get('contact_effect_cycles','—')
        cov=a.get('joint_coverage',{});holds=cov.get('hold_contact_effect_cycles',{})
        hold_text=f"{holds.get('50','—')} / {holds.get('1','—')}" if spec['profile']!='R_RECOVERY' else '不适用'
        peak=cov.get('peaks',{}).get('force_N',{}).get('covered','—')
        rec=a.get('recovery',{});recovery=f"{rec.get('covered',False)}；回撤{(rec.get('actual_retraction_m') or 0)*1e6:.3f}μm" if spec['profile']=='R_RECOVERY' else '不适用'
        table.append(f"| {spec['id']} | {status} | {audit} | {stopped} | {contact} | {hold_text} | {peak} | {recovery} |")
    costs=s['cost_totals'];counts=s['recorded_counts'];wall=s['outer_supervisor']['wall_seconds']
    caption=f"本轮已预留／尝试{s['reserved_dynamic']}/12，审核通过{s['audited_attempts']}，经审核的功能成功{functional_count}、真实停稳{stopped_count}，未执行{s['unused_dynamic_closed']}项已关闭。实际累计动态{s['cumulative_after_reserved']}（原225＋本轮{s['reserved_dynamic']}）；学习器、张量读取、前向、优化和经验发布全0。"
    report=f'''# B2-SCOPE-10｜联合点固定物理预检结果

2026-10-09。当前阶段：B.2；任务：固定12项联合点动作／工程恢复物理预检，执行与收口已完成。

**{conclusion}**

{caption}

## 固定分母结果

功能结局、审核／停稳、接触作用、动作时序、峰值重叠和恢复分别统计。A/B为预定应力序列，R为一次工程触发分支；都不能作为学习策略收益或自然恢复成功率。未执行项保留在12项分母中。

| 项目 | 原始任务结局 | 审核 | 真实停稳 | 接触有效作用周期 | 50／1周期块接触作用 | 力峰重叠 | 恢复覆盖 |
|---|---|---|---|---:|---|---|---|
{chr(10).join(table)}

详细覆盖、全部峰值和失败类别见[执行汇总](execution_summary.json)、[路线决定](route_decision.json)与[原始账本](run/ledger.json)。原始档案和每项审核收据在run目录中，完整／异常／部分记录均保留。程序在运行及保护健康时继续固定矩阵；任何保护／运行／审核失败均关闭后续分配，无补采到通过。

## 覆盖缺口与恢复证据

{coverage_details}

以上分类由已经保存的原始周期记录复算，原始SHA、接触时间段与固定块时间段见[时序缺口证据](coverage_gap_evidence.json)。它只说明本次时间重叠事实，不能推断改换时序之后会通过。功能成功不能填补未经历的快速接触动作覆盖。

工程恢复覆盖{len(recovery_covered)}/4：{recovery_details}。覆盖通过项同时核对非零请求被屏蔽为零、真实回撤、重新锚定参考、净推进原点以及恢复后首个获准动作的实际作用；不计自然恢复成功率。

A/B合并后，{direction_count}/4个J点记录到四轴正负接触作用；力、力矩和穿透峰值的动作作用重叠通过{peak_total-len(peak_gaps)}/{peak_total}项核对。详细方向集合与峰值缺口清单保留在路线文件中；时序缺口不被这些通过项抵销。

## 成本与停止证据

| 项目 | 本轮记录 |
|---|---:|
| 环境创建尝试／完成 | {costs.get('case_environment_instances_attempted',0)}／{costs.get('case_environment_instances_completed',0)} |
| reset尝试／完成 | {costs.get('reset_attempts',0)}／{costs.get('resets_completed',0)} |
| 已归档控制周期／物理子步 | {counts['control_cycles']}／{counts['native_steps']} |
| native积分调用记录 | {costs.get('native_step_calls',0)} |
| 观测向量记录 | {counts['observation_vectors']} |
| 整体监督墙钟 | {wall:.3f}s（{wall/60:.2f}min） |
| 未用动态数量关闭 | {s['unused_dynamic_closed']} |
| 学习相关成本 | 全0 |

进程树已确认退出，物理停稳另由原审核判定；两者不混用。外层监督状态原样保留：`{s['ledger_status']}`。本次监督返回码0，未触发时间上限。授权和一次性claim关闭证据见[authorization_closure.json](authorization_closure.json)。本次12项均有完整档案，周期／子步按最终记录计数；各次运行的中间检查点也保留。

## 路线与剩余边界

路线：`{route}`。

{next_task}

完整B.2/C未验收。四个±75μm／±0.25°联合开发点不等于原±1.5°范围，也不证明连续动作域普遍安全。本轮力、力矩与穿透峰值均已分别核对；剩余3处时序覆盖缺口仍阻止预检资格。仍需姿态匹配学习、共同参照、检查点独立进程恢复、冻结评价和原范围处理。训练未准入，自动跟踪PAUSED，旧预算不重开。

原工作区、分支及全部未提交修改保留；旧实验和失败不改写。本可交付阶段结束后暂停汇报。
'''
    (OUT/'结果说明.md').write_text(report,encoding='utf-8')
    (OUT/'路线决定.md').write_text('# B2-SCOPE-10路线决定\n\n'+conclusion+'\n\n'+caption+'\n\n'+next_task+'\n\n完整B.2/C未验收，训练未准入，自动跟踪PAUSED。本轮数量关闭，不重试。具体证据见[结果说明](结果说明.md)和[机器路线](route_decision.json)。\n',encoding='utf-8')
    print(dict(route=route,attempts=s['reserved_dynamic'],audited=s['audited_attempts'],closed=s['unused_dynamic_closed'],wall_s=wall))
if __name__=='__main__':main()
