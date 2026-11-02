"""Close confirmed-ended A0/A2 trials from saved evidence; no model/environment calls."""
from collections import Counter
from datetime import datetime
import gzip
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.learning.five_axis_preparation import read,sha,verify_inputs
from tools.learning.paired_entropy_trial import ARMS,summarize_run
from tools.validation.run_yaw_pilot import write
OUT=ROOT/'deliverables/learning_chain/five_axis_entropy_closed_loop_20261026'
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md',
      'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']


def rpy_degrees(q):
    w,x,y,z=np.asarray(q)/np.linalg.norm(q)
    return [math.degrees(math.atan2(2*(w*x+y*z),1-2*(x*x+y*y))),
            math.degrees(math.asin(float(np.clip(2*(w*y-z*x),-1,1)))),
            math.degrees(math.atan2(2*(w*z+x*y),1-2*(y*y+z*z)))]


def main():
    if (OUT/'completion_verification.json').exists():
        print('Already closed; existing immutable completion retained.');return
    exit_proof=read(OUT/'process_exit.json')
    if not exit_proof.get('process_exit_confirmed'):raise RuntimeError('Wait for confirmed batch exit')
    reg=read(OUT/'registration.json');verify_inputs(reg['inputs'])
    launch=read(OUT/'launch_manifest.json')
    if (launch['registration_sha256']!=sha(OUT/'registration.json')
            or launch['evaluation_plan_sha256']!=sha(OUT/'evaluation_plan.json')):
        raise ValueError('Preregistered analysis changed')
    costs=summarize_run(OUT/'run');rows=[];pins={}
    for e in costs['episodes']:
        folder=OUT/'run'/e['arm']/e['job']
        proof=read(folder/'supervisor.json') if (folder/'supervisor.json').exists() else {}
        if not proof.get('process_exit_confirmed'):
            raise RuntimeError('Worker exit not confirmed: '+e['arm']+' '+e['job'])
        receipt=read(folder/'receipt.json') if (folder/'receipt.json').exists() else {}
        row=dict(e)
        row['guard_reasons']=receipt.get('guard_facts',{}).get('contact_reasons',[])+receipt.get('guard_facts',{}).get('motion_reasons',[])
        row['invalid_reasons']=receipt.get('guard_facts',{}).get('invalid_reasons',[])
        row['actuator_counters']=receipt.get('actuator_counters',{})
        path=folder/'episode.json.gz'
        if path.exists():
            if sha(path)!=receipt.get('archive_sha256'):raise ValueError('Archive bytes changed')
            if e['completed']:
                audit=read(folder/'audit.json')
                if not audit['verified'] or audit['archive_sha256']!=receipt['archive_sha256']:
                    raise ValueError('Episode audit binding differs')
            raw=json.loads(gzip.decompress(path.read_bytes()))
            trace=raw.get('trace',[])
            if trace and receipt.get('valid') is True:
                end=raw.get('evidence',{}).get('task_end_time_s')
                end=trace[-1]['time_s'] if end is None else end
                index=min(range(len(trace)),key=lambda i:abs(trace[i]['time_s']-end))
                task=trace[:index+1];last=task[-1]
                contact=next((i for i,t in enumerate(task) if t['contact_count']),None)
                angles=rpy_degrees(last['quaternion_wxyz'])
                row.update(task_simulation_s=end,audit_simulation_s=trace[-1]['time_s'],
                    task_end_position_m=last['position_m'],task_end_rpy_deg=angles,
                    terminal_radial_error_mm=math.hypot(*last['position_m'][:2])*1000,
                    terminal_rpy_component_norm_deg=float(np.linalg.norm(angles)),
                    advance_mm=(last['position_m'][2]-trace[0]['position_m'][2])*1000,
                    post_contact_maximum_advance_um=(max(t['position_m'][2] for t in task[contact:])-task[contact]['position_m'][2])*1e6 if contact is not None else None,
                    peak_force_N=max((p['force_N'] for p in raw.get('cycle_peaks',[])),default=None),
                    peak_torque_G_Nm=max((p['torque_G_Nm'] for p in raw.get('cycle_peaks',[])),default=None),
                    force_exceed_duration_control_upper_s=.002*sum(p['force_N']>reg['common']['dynamic_config']['stop_force_N'] for p in raw.get('cycle_peaks',[])),
                    torque_exceed_duration_control_upper_s=.002*sum(p['torque_G_Nm']>reg['common']['dynamic_config']['stop_torque_Nm'] for p in raw.get('cycle_peaks',[])),
                    event_counts=dict(Counter(t['reason'] for t in raw.get('evidence',{}).get('controller_events',[]))))
                if e['stage']=='development':
                    active=[t for t in raw.get('transitions',[]) if t['action_active']]
                    if active:
                        row['mean_abs_normalized_action_percent']=(np.abs(np.array([t['action'] for t in active])).mean(0)*100).tolist()
            del raw
        for f in folder.iterdir():
            if f.is_file() and f.suffix in ('.json','.gz','.xml'):
                pins[f.relative_to(OUT).as_posix()]=sha(f)
        if (folder/'checkpoint/manifest.json').exists():
            m=read(folder/'checkpoint/manifest.json')
            result=read(folder/'job_result.json')
            if sha(folder/'checkpoint/manifest.json')!=result.get('checkpoint_sha256'):
                raise ValueError('Completed checkpoint binding differs')
            if sha(folder/'checkpoint/state.pt')!=m['state_sha256']:raise ValueError('Checkpoint bytes changed')
            pins[(folder/'checkpoint/manifest.json').relative_to(OUT).as_posix()]=sha(folder/'checkpoint/manifest.json')
            pins[(folder/'checkpoint/state.pt').relative_to(OUT).as_posix()]=sha(folder/'checkpoint/state.pt')
        rows.append(row)
    arms={}
    for arm in ARMS:
        selected=[r for r in rows if r['arm']==arm]
        dev=[r for r in selected if r['stage']=='development' and r['completed']]
        arms[arm]=dict(development_completed=len(dev),
            development_full_successes=sum(r.get('outcome')=='FULL_SUCCESS' for r in dev),
            all_new_guard_failure_episodes=sum(bool(r['guard_reasons']) for r in selected),
            all_new_invalid_episodes=sum(bool(r['invalid_reasons']) or r.get('outcome')=='INVALID_SIMULATION' for r in selected),
            development_guard_failure_episodes=sum(bool(r['guard_reasons']) for r in dev),
            online_updates=costs['updates_by_arm'][arm])
    ledger=read(OUT/'ledger.json')
    complete=(ledger['status']=='COMPLETED' and exit_proof['exit_code']==0 and costs['completed_jobs']==24)
    a0,a2=arms['A0'],arms['A2']
    guards_ok=(a2['all_new_guard_failure_episodes']<=a0['all_new_guard_failure_episodes']
               and a2['all_new_invalid_episodes']<=a0['all_new_invalid_episodes'])
    candidate=(complete and a2['development_completed']==4 and a0['development_completed']==4
               and a2['development_full_successes']>a0['development_full_successes']
               and a2['development_full_successes']>=2 and guards_ok)
    decision=('A2仅列为后续确认候选' if candidate else
              '两支成功数相同，未检出A2优势' if complete and a2['development_full_successes']==a0['development_full_successes'] else
              'A2未达到预登记采用条件；不自动采用')
    summary=dict(status='COMPLETED' if complete else 'STOPPED',costs=costs,arms=arms,rows=rows,
        selection=decision,A2_confirmation_candidate=candidate,new_final_test_episodes=0,
        elapsed_wall_s=ledger.get('elapsed_wall_s'),
        main_process_exit_code=exit_proof['exit_code'],costs_are_lower_bounds=not costs['counts_exact'])
    write(OUT/'result_summary.json',summary)
    date=datetime.now().strftime('%Y-%m-%d');state='已完成' if complete else '已停批'
    lines=['# A0/A2五维残差SAC闭环对照结果','',f'{date}，B.2第3项；启动于2026-10-26。', '',
        f'**本批{state}。{decision}。**', '',
        '| 分支 | 熵初值 | 实际更新 | 已完成开发点 | 完整插入 | 全部新回合保护失败 | 全部新回合无效 |',
        '|---|---:|---:|---:|---:|---:|---:|']
    for arm in ARMS:
        v=arms[arm];alpha=reg['configs'][arm]['learning']['entropy_initial']
        lines.append(f'| {arm} | {alpha} | {v["online_updates"]} | {v["development_completed"]}/4 | {v["development_full_successes"]} | {v["all_new_guard_failure_episodes"]} | {v["all_new_invalid_episodes"]} |')
    lines+=['','只改变熵系数初值。共同旧4预热54000行、未训练网络/RNG起点、2 ms控制、N2/450、奖励/保护/成功标准；后续经验和RNG消耗可随闭环策略分化。评价不发布回放，未做最终测试。','',
        '## 逐点开发表现','',
        '| 分支/工况 | 结果/原因 | 任务秒 | 推进mm | 接触后最大新增推进μm | 末端径向误差mm | 末端RPY范数deg | 峰力N |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    def fmt(v):return '未记录' if v is None else f'{v:.4f}'
    for r in rows:
        if r['stage']=='development':
            lines.append(f'| {r["arm"]}/{r["job"]} | {r.get("outcome")}/{r.get("final_reason")} | '+
                ' | '.join(fmt(r.get(k)) for k in ('task_simulation_s','advance_mm','post_contact_maximum_advance_um',
                    'terminal_radial_error_mm','terminal_rpy_component_norm_deg','peak_force_N'))+' |')
    lines+=['','## 成本与解释范围','',
        f'- 本批新初始化{costs["initialization_attempts"]}，科研累计{costs["cumulative_initializations"]}；物理子步{costs["physical_substeps"]:,}，实际更新{costs["training_updates"]}，在线神经控制调用{costs["policy_calls"]}。',
        f'- 台账记录墙钟耗时{(ledger.get("elapsed_wall_s") or 0)/60:.1f}分钟；异常硬退出时记录可能只到最后一次落盘。',
        f'- 成本是否为精确值：{costs["counts_exact"]}。未知硬退出的成本只能视作下界，不用暂存0否定消耗。',
        '- 旧预热只作共享逻辑导入，不重复计算新物理成本。诊断使用预登记固定旧状态；收口未新增仿真、推理或优化。',
        '- 四个已知开发点、单种子、每支4000更新不证明收敛或泛化。与旧2000更新批次比较还包含闭环回合数等共同变化。',
        '- 预登记成功数/保护规则优先；连续指标或动作变大不能在成功数平局后挑选A2。完整B.2/C仍需另行验收。','',
        '受力/力矩越阈持续时间在result_summary中按出现越阈峰值的2 ms控制周期累计，属于时间上界估计，不能称为原生子步的精确持续时间。','',
        '## 全部尝试与失败','']
    for r in rows:
        lines.append(f'- {r["arm"]}/{r["job"]}：{r["status"]}，{r.get("outcome")}/{r.get("final_reason")}；'
            f'新初始化{r["initialization_attempts"]}、物理子步{r["physical_substeps"]}、更新{r["training_updates"]}；'
            f'事件{r.get("event_counts",{})}，错误{r.get("error")}。')
    lines+=['','证据：[登记](registration.json)、[初始预热来源](shared_warmup_receipts.json)、[台账](ledger.json)、'
        '[退出](process_exit.json)、[结果数据](result_summary.json)、[收口核验](completion_verification.json)。','']
    (OUT/'闭环对照结果.md').write_text('\n'.join(lines),encoding='utf-8')
    block=f'''<!-- paired-entropy-closed-loop-final -->
**{date}｜B.2第3项：A0/A2五维残差SAC同期闭环对照{state}。** A0完整成功{a0['development_full_successes']}/{a0['development_completed']}个已完成开发点，A2为{a2['development_full_successes']}/{a2['development_completed']}；{decision}。未完成评价不补记失败。

实际新增初始化{costs['initialization_attempts']}、科研累计{costs['cumulative_initializations']}，物理子步{costs['physical_substeps']:,}、更新{costs['training_updates']}（A0/A2分别{costs['updates_by_arm']['A0']}/{costs['updates_by_arm']['A2']}），计数精确={costs['counts_exact']}。同源旧4预热未重复消耗物理，2 ms/N2/450/奖励/保护保持；不增加历史或保持策略训练，无最终测试或自动扩量。

第3/4项获得真实闭环训练与共同条件证据；第7项按预登记成功数/保护规则汇总开发结果；第8项全部尝试、失败、成本、检查点及五份滚动资料保存。执行完成、策略有效及完整B.2验收仍是不同状态，完整B.2/C未验收。

**下一项待决定：**依据本批逐点结果复盘，不自动重跑、恢复、换系数、加历史或进入C。本阶段按项目约定收口。

[闭环结果与全部证据](deliverables/learning_chain/five_axis_entropy_closed_loop_20261026/闭环对照结果.md)。下方保留历史。
<!-- /paired-entropy-closed-loop-final -->

'''
    log=f'\n\n### {date}｜B.2第3项：A0/A2闭环对照收口\n\n本批{state}；{decision}。新增初始化{costs["initialization_attempts"]}、累计{costs["cumulative_initializations"]}、物理子步{costs["physical_substeps"]:,}、实际更新{costs["training_updates"]}；精确计数={costs["counts_exact"]}。证据为本批闭环对照结果、result_summary、process_exit及completion_verification。开发点/单种子/有限更新不证明泛化或收敛；后续不自动扩量或加模块。\n'
    docs=[]
    for name in DOCS:
        path=ROOT/name;before=path.read_bytes();snapshot=OUT/'rolling_documents_before_completion'/name
        snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(before)
        prefix=block.replace('(deliverables/learning_chain/','(../../learning_chain/') if name.startswith('deliverables/') else block
        after=prefix.encode('utf-8')+before
        if name in ('项目进度跟踪.md',DOCS[-1]):after+=log.encode('utf-8')
        path.write_bytes(after);snapshot=OUT/'rolling_documents_after_completion'/name
        snapshot.parent.mkdir(parents=True,exist_ok=True);snapshot.write_bytes(after)
        docs.append(dict(path=name,sha256=sha(snapshot),original_bytes_preserved=before in after))
    for name in ('registration.json','admission.json','launch_manifest.json','evaluation_plan.json',
                 'ledger.json','process_exit.json','result_summary.json','闭环对照结果.md'):
        pins[name]=sha(OUT/name)
    source=OUT/'analysis_source_snapshot'/Path(__file__).name
    source.parent.mkdir(parents=True,exist_ok=True);source.write_bytes(Path(__file__).read_bytes())
    pins[source.relative_to(OUT).as_posix()]=sha(source)
    verify_inputs(reg['inputs'])
    write(OUT/'completion_verification.json',dict(verified=True,batch_completed=complete,
        selection=decision,A2_confirmation_candidate=candidate,artifacts=pins,rolling_documents=docs,
        closeout_new_physics=0,closeout_new_neural_inference=0,closeout_new_updates=0))
    print(json.dumps(dict(status=summary['status'],arms=arms,costs={k:v for k,v in costs.items() if k!='episodes'},decision=decision),ensure_ascii=False))


if __name__=='__main__':main()
