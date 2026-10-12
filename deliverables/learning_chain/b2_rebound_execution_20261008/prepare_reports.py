"""Describe the closed fixed-denominator result; no simulation or learning imports."""
import json
from pathlib import Path

OUT=Path(__file__).resolve().parent

def read(p): return json.loads(p.read_text(encoding='utf-8'))
def write_new(p,text):
    with p.open('x',encoding='utf-8',newline='\n') as f: f.write(text)
def number(x): return '—' if x is None else f'{x:.6g}'

def main():
    c=read(OUT/'authorization_closure.json'); a=read(OUT/'run/assessment.json'); t=c['actual']
    rows=a['dynamic']; scripts=[r for r in rows if r['id'].endswith('_script')]
    metrics=dict(contact_episodes=sum(r.get('contact_cycles',0)>0 for r in rows),
                 script_effect_covered=sum(r.get('effect_coverage')=='OBSERVED' for r in scripts),
                 script_contact_effect_covered=sum(r.get('contact_coverage')=='OBSERVED' for r in scripts),
                 recovery_episodes=sum(r.get('recovery_coverage')=='EVENTS_OBSERVED_REQUIRES_REVIEW' for r in rows),
                 verified_observation_vectors=sum(r.get('observation',{}).get('vectors_verified',0) for r in rows),
                 symmetric_contact_pairs_with_recorded_difference=sum(r['status']=='RECORDED_DIFFERENCE_REQUIRES_REVIEW' for r in a['information']['symmetric_pairs']))
    by_id={r['id']:r for r in rows}; paired=[]
    for point in ('P01','P02','P03','P04','J01','J02','J03','J04'):
        zero=by_id[point+'_zero']; script=by_id[point+'_script']
        z=zero.get('failure_penalized_task_time_s'); q=script.get('failure_penalized_task_time_s')
        paired.append(dict(case_id=point,zero_task_s=z,script_task_s=q,
                           script_minus_zero_s=None if z is None or q is None else q-z,
                           zero_success=zero.get('functional_success'),script_success=script.get('functional_success')))
    metrics['paired_task_times']=paired
    summary=(f"B2-SCOPE-06一次执行已收口：静态审核{c['registered_static_audit_passes']}/9；动态尝试{t['dynamic_attempts']}/16、"
             f"审核通过{c['registered_dynamic_audit_passes']}/16、功能成功{c['functional_successes']}/16、80μm/0.5°附加精度成功{c['strict_precision_successes']}/16。"
             f"运行状态{c['status']}；本轮未用动态{c['unused_dynamic_closed']}，新授权已关闭。")
    evidence=(f"本轮环境创建/复位完成各{t['resets_completed']}次，{t['control_cycles']}控制周期/{t['physical_substeps']}物理子步，"
              f"整轮监督{c['whole_supervised_wall_seconds']:.3f}s；进程退出确认，学习器/张量读取/网络前向/优化/经验发布全0。"
              f"实际累计动态{c['cumulative_dynamic_after']}，自动跟踪PAUSED，原旧15回合未重开。")
    limit=(f"本轮接触覆盖{metrics['contact_episodes']}/16、script四轴命令作用覆盖{metrics['script_effect_covered']}/8、"
           f"接触时作用覆盖{metrics['script_contact_effect_covered']}/8、对称接触信息差异覆盖{metrics['symmetric_contact_pairs_with_recorded_difference']}/8，"
           f"恢复事件覆盖{metrics['recovery_episodes']}/16。±0.25°离散开发点不覆盖±0.5°边界、原±1.5°目标或连续域；"
           "固定0.1幅度且四轴相关的脚本不覆盖完整F50动作域，脚本不是SAC，非零差异不等于可辨识性或学习收益。完整B.2/C未验收，无新训练准入，独立测试0。")
    route=a['route']
    gate_explanation=(
        '固定路线的接触覆盖条件要求8个script臂均记录接触时的命令作用；缺口点为：'+
        '、'.join(r['id'] for r in scripts if r.get('contact_coverage')!='OBSERVED')+'。'+
        '这些点没有相应接触证据时，不能记成接触控制或接触信息通过。恢复覆盖另外分列，不是本次choose_route的判定项。'
        if route=='INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS' else
        '路线按固定分母、关闭规则及记录的命令作用/接触信息判定，原始执行状态不回写。')
    next_map={
      'NO_SCOPE_QUALIFICATION':'下一项只用本轮完整/部分记录定位提前关闭原因，先区分物理保护、停止问题与审核/进程故障，提出B.2离线修正或范围决定；不重试、不恢复未用回合，不进入C或训练。',
      'INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS':'下一项只离线复核J01～J04的现有接触信息、动作许可与作用时序，判断4个有接触联合点是否支持限定姿态匹配学习候选，并列出恢复及动作域缺口。P01～P04保留为无接触功能对照；不追加它们填接触覆盖，不扩137维观测或物理范围，不进入C或训练。原±1.5°目标与当前±0.25°开发验证的验收边界须另行明确。',
      'INSUFFICIENT_INFORMATION_NO_EXTRA_ATTEMPTS':'下一项只离线分析8组对称点的137维记录、接触差异与裁剪信息，判断B.2可辨识性限制；不扩大观测、不追加回合、不进入C或训练。',
      'INFORMATION_REVIEW_REQUIRED_BEFORE_TRAINING_REGISTRATION':'下一项先解释8组对称点及zero/script配对的信息差异，审查是否足以支持限定的B.2匹配训练候选；当前不生成训练授权、不进入C，不把差异自动升级为可学习证据。'}
    next_text=next_map[route]
    with (OUT/'report_summary.json').open('x',encoding='utf-8',newline='\n') as f:
        json.dump(dict(summary=summary,evidence=evidence,limit=limit,next=next_text,route=route,gate_explanation=gate_explanation,metrics=metrics),f,ensure_ascii=False,indent=2);f.write('\n')
    table=['| 动态点/臂 | 执行/审核 | 任务结果 | 附加精度 | 罚时任务s | 峰值力mN | 接触周期 | 非零请求周期 | 四轴作用/接触作用 |',
           '|---|---|---|---|---:|---:|---:|---:|---|']
    for r in rows:
        out=r.get('outcome',{}).get('task_outcome','—')
        force=r.get('peak_loads',{}).get('force_N')
        table.append(f"| {r['id']} | {r['status']}/{r['audit_passed']} | {out} | {r.get('strict_precision_success','—')} | {number(r.get('failure_penalized_task_time_s'))} | {number(None if force is None else force*1000)} | {r.get('contact_cycles','—')} | {r.get('script_nonzero_cycles','—')} | {r.get('effect_coverage','—')}/{r.get('contact_coverage','—')} |")
    pairs=['| 对称配对 | 初始137维不同分量数 | 首接触特征不同分量数 | 信息覆盖 |','|---|---:|---:|---|']
    for p in a['information']['symmetric_pairs']:
        count=lambda v: '—' if v is None else sum(x!=0 for x in v)
        pairs.append(f"| {p['left']} ↔ {p['right']} | {count(p['initial_observation_delta'])} | {count(p['first_contact_feature_delta'])} | {p['status']} |")
    times=['| 配对点 | zero任务s | script任务s | script−zero ms |','|---|---:|---:|---:|']
    for p in paired:
        delta=p['script_minus_zero_s']
        shown=None if delta is None else (0.0 if abs(delta)<1e-9 else delta*1000)
        times.append(f"| {p['case_id']} | {number(p['zero_task_s'])} | {number(p['script_task_s'])} | {number(shown)} |")
    write_new(OUT/'结果说明.md',f"# B2-SCOPE-06｜小倾角姿态预检实际执行\n\n2026-10-08。**当前阶段：B.2“小规模学习与评价”；当前任务：已批准的一次姿态预检执行与结果收口，已完成。**\n\n{summary}\n\n{evidence}\n\n"
       f"## 原始证据与授权关闭\n\n用户明确批准新9静态/最多16动态方案，生成本轮独立grant并绑定封存B2-SCOPE-05；仅执行一次。9静态全部通过才开启动态，顺序与停止规则保持。每动态14500周期/145000子步、每项1200s，整轮6h；训练/推理0，重试0。旧15回合与旧错误账本保持。\n\n"
       f"[授权登记](registration.json)、[新grant](grant.json)、[原始关闭账本](run/ledger.json)、[完整矩阵审核](run/assessment.json)、[实耗与监督证据](authorization_closure.json)。"
       f"本轮2173项输入核对，封存程序61成员保持。关闭账本的保守子步界限{c['original_ledger_step_bounds']}，完整档案精确成本重核={c['exact_final_counts_reconciled']}。"
       "物理停稳依据完整raw的停止尾段及worker/整轮审核outcome.physical_stopped；supervisor.json的physical_stop_confirmed为初始化后未回填的保守字段，不用它证明停稳。\n\n"
       "## 固定16项结果\n\n普通有效停稳任务失败保持26s罚时；NOT_ATTEMPTED保留空值，不计成功、不从固定分母删除。接触周期和脚本作用为控制周期统计，峰值/保护来自全部物理子步。\n\n"+'\n'.join(table)+'\n\n'
       "## 配对任务时间\n\n"+'\n'.join(times)+'\n\n表中小于1ns的浮点时间差显示为0，原始差保留在report_summary.json。每个登记点只有一次zero/script开发配对；数值差异不提供统计区间或SAC收益证据。\n\n'
       "## 对称点信息与动作作用\n\n"+'\n'.join(pairs)+f"\n\n完整审核观测向量{metrics['verified_observation_vectors']}条；[配对详细差异](run/assessment.json)同时保存初始观测、首接触特征、裁剪与zero/script运动积分差。初始观测相同只说明这些登记记录未直接提供初始角信息；没有接触时不能据此证明任意接触状态不可辨识。脚本后的运动差须结合配对记录解释。\n\n"
       f"## 限制与路线\n\n{limit}\n\n固定审核路线：`{route}`。{gate_explanation}\n\n{next_text}\n\n[路线决定](路线决定.md)、[交付核验](verification.json)。阶段结束后暂停汇报。\n")
    write_new(OUT/'路线决定.md',f"# B2-SCOPE-06｜路线决定\n\n2026-10-08。**当前阶段B.2；当前任务：本轮姿态预检结果与路线收口，已完成。**\n\n{summary}\n\n{limit}\n\n"
       f"审核器按封存规则给出的路线是`{route}`。{gate_explanation}\n\n{next_text}\n\n"
       "验收区分：初始化贯通、有效停稳、功能成功、附加精度、残差实际作用、接触信息、恢复覆盖、匹配训练与独立评价分别计证据，不能以其中一项代替全部B.2。"
       "程序修复后的真实运行结果也不回写升级原B2-SCOPE-03失败状态。\n\n"
       f"{evidence}\n\n新grant已关闭，剩余不能结转；不把本轮批准延伸至训练、扩范围或再次运行。C的F12.5接入继续暂缓。"
       "历史PC-09 G负Y失败、PC-10无执行错误证据、旧S/F 0.39%未过10%继续门均保持。\n\n"
       "证据：[实际结果](结果说明.md)、[矩阵审核](run/assessment.json)、[授权与实耗关闭](authorization_closure.json)。\n")
    print(json.dumps(dict(status='REPORTS_PREPARED_FROM_CLOSED_EVIDENCE',route=route,metrics=metrics),ensure_ascii=False))

if __name__=='__main__': main()
