"""Collect independently rerun pairs and audit the frozen seven-case protocol."""
import hashlib
import json
import shutil
from dataclasses import asdict
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager

from tools.reporting.report_b2 import verified, CASE_LABELS, REASONS, figures, replay
from tools.reporting.report_b1 import read_verified
from tools.validation.run_b2_search import OUT, hashes
from tools.validation.run_b1_baseline import dump, geometric_finish, FINISH, cases
from tools.visualization.font_support import find_chinese_font

TARGET=OUT/'matrix_v1_7cases'


def collect():
    frozen=json.loads((TARGET/'frozen_protocol.json').read_text(encoding='utf-8'))
    assert frozen['source_sha256']==hashes(), 'Controller changed after protocol freeze'
    assert frozen['case_names']==[c.name for c in cases()]
    merged=None;all_runs=[]
    for expected_case,worker in zip(cases(),frozen['workers']):
        case=expected_case.name
        folder,index,runs=verified(worker)
        assert index['case_names']==[case] and index['paired']
        assert index['source_sha256']==frozen['source_sha256'] and index['config']==frozen['config']
        assert runs[0]['controller']['name']=='B1_fixed_admittance'
        assert runs[1]['controller']['name']=='B2_bounded_search_recovery'
        assert runs[1]['controller']['config']==frozen['config']
        assert runs[1]['controller']['admittance']==runs[0]['controller']
        for run in runs:
            assert run['case']==asdict(expected_case)
            assert run['finish_criteria']==FINISH
            if all_runs:assert run['environment']==all_runs[0]['environment']
        for relative,expected in index['source_sha256'].items():
            assert hashlib.sha256((folder/'source_snapshot'/relative).read_bytes()).hexdigest()==expected
        if merged is None:
            merged={**index,'case_names':frozen['case_names'],'runs':[],'execution':'seven independent, freshly rerun pairs; three process queues'}
            for relative in index['source_sha256']:
                dest=TARGET/'source_snapshot'/relative;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(folder/'source_snapshot'/relative,dest)
        assert index['historical_source_sha256']==merged['historical_source_sha256']
        for entry in index['runs']:
            merged['runs'].append({**entry,'file':f'../{worker}/{entry["file"]}','worker':worker})
        all_runs.extend(runs)
    assert len(all_runs)==14
    dump(TARGET/'results_index.json',merged)
    verified(TARGET.name)
    return merged,all_runs


def metrics(run):
    row=run['final'];p=np.asarray(row['position_m']);q=np.asarray(row['quaternion_wxyz'])
    assert len(run['trace'])==run['control_steps']+1
    assert all(run['trace'][-1].get(k)==v for k,v in row.items()), 'Final state differs from final sample'
    times=np.array([s['time_s'] for s in run['trace']]);period=run['environment']['config']['control_period']
    deltas=np.diff(times)
    if row['phase']=='TERMINAL':
        assert np.allclose(deltas[:-1],period,rtol=0,atol=1e-9)
        assert 0<=deltas[-1]<=period+1e-9
    else:assert np.allclose(deltas,period,rtol=0,atol=1e-9), 'Missing control samples'
    step=run['environment']['config']['timestep']
    lag=run['physical_steps']*step-row['time_s']
    if row['phase']=='TERMINAL' and run['termination']=='INVALID_SIMULATION':
        # Core counts a failed integration step before retaining last_finite.
        assert -1e-8<=lag<=step+1e-8
    else:assert abs(lag)<1e-8
    angle=np.degrees(2*np.arccos(np.clip(abs(q[0])/np.linalg.norm(q),0,1)))
    unmet=[]
    if run['termination'].startswith('INVALID') or run['termination']=='SIMULATION_ERROR':unmet.append('数值有效性')
    if abs(p[2])>FINISH['z_tolerance_m']:unmet.append('Z 未到位')
    if np.linalg.norm(p[:2])>FINISH['xy_tolerance_m']:unmet.append('XY 精度')
    if np.radians(angle)>FINISH['angle_tolerance_rad']:unmet.append('姿态精度')
    if np.linalg.norm(row['velocity_world'][:3])>FINISH['linear_speed_m_s']:unmet.append('线速度未稳定')
    if np.linalg.norm(row['velocity_world'][3:])>FINISH['angular_speed_rad_s']:unmet.append('角速度未稳定')
    for key,limit,label in [('force_N','force_N','力保护'),('torque_G_Nm','torque_Nm','力矩保护'),('penetration_m','penetration_m','穿透保护')]:
        if run['peaks'][key]>=FINISH[limit]:unmet.append(label)
    # Recheck every claimed success, including the uninterrupted 0.1 s hold.
    if run['termination']=='GEOMETRIC_SUCCESS':
        assert not unmet
        valid_since=None
        for sample in run['trace']:
            if sample['phase']=='STOPPING' and geometric_finish(sample):
                if valid_since is None:valid_since=sample['time_s']
            else:valid_since=None
        assert valid_since is not None and row['time_s']-valid_since>=FINISH['hold_s']-1e-9
    assert run['max_time_s']==20 and run['settle_time_s']==1
    assert row['time_s']<=21.002000001
    # Logged sampling peaks may be below physical-step peaks, never above them.
    assert max(np.linalg.norm(r['contact_wrench_M'][:3]) for r in run['trace'])<=run['peaks']['force_N']+1e-12
    assert max(r['penetration_m'] for r in run['trace'])<=run['peaks']['penetration_m']+1e-12
    if 'search_count' in run:
        assert run['search_count']<=2 and run['recovery_count']<=1
        resumes=[e for e in run['events'] if e['reason']=='B2_RECOVERY_RESUMED']
        assert len(resumes)<=1
        guards=[e['time_s'] for e in run['events'] if any(s in e['reason'] for s in ('FORCE_LIMIT','TORQUE_LIMIT','PENETRATION_LIMIT'))]
        assert not any(e['time_s']>g for e in resumes for g in guards)
    return {'case':run['case']['name'],'policy':'B2' if 'search_count' in run else 'B1',
            'advance_mm':(p[2]-run['case']['start_origin_z_m'])*1000,'z_error_um':abs(p[2])*1e6,
            'xy_error_um':float(np.linalg.norm(p[:2])*1e6),'angle_deg':float(angle),
            'peak_force_mN':run['peaks']['force_N']*1000,'peak_torque_mNm':run['peaks']['torque_G_Nm']*1000,
            'peak_penetration_um':run['peaks']['penetration_m']*1e6,'termination':run['termination'],
            'success':run['termination']=='GEOMETRIC_SUCCESS','stop_time_s':run['stop_time_s'],
            'success_time_s':row['time_s'] if run['termination']=='GEOMETRIC_SUCCESS' else None,
            'searches':run.get('search_count',0),'recoveries':run.get('recovery_count',0),'unmet':unmet}


def outcome(m):
    if m['success']:return '完整达标'
    if '数值有效性' in m['unmet']:return '仿真无效'
    if any('保护' in x for x in m['unmet']):return '保护停止'
    if m['z_error_um']<=20:return '深度到位\n其他条件未满足'
    return '未到目标深度'


def plots(ms,old):
    font_manager.fontManager.addfont(str(find_chinese_font()))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(find_chinese_font())).get_name(),
                         'axes.unicode_minus':False,'font.size':10,'figure.dpi':160})
    labels=[CASE_LABELS[m['case']] for m in ms[::2]];x=np.arange(7)
    fig,ax=plt.subplots(figsize=(13,6),layout='constrained')
    groups=[old,[m['advance_mm'] for m in ms[::2]],[m['advance_mm'] for m in ms[1::2]]]
    for j,(values,label,color) in enumerate(zip(groups,['原 B1：6 s 预算','本轮 B1：20 s 预算','本轮 B2：20 s 预算'],['#b7bec5','#617b92','#187d94'])):
        bars=ax.bar(x+(j-1)*.25,values,width=.23,label=label,color=color)
        ax.bar_label(bars,fmt='%.3f',fontsize=8,padding=3)
    ax.axhline(4,color='#a85447',ls='--',label='名义目标推进 4 mm')
    ax.set(xticks=x,xticklabels=labels,ylabel='回合结束实际推进 / mm',ylim=(min(-.15,min(sum(groups,[]))-.15),4.75),
           title='B2-4｜全部七个开发工况：推进量与完整达标分别评价')
    ax.legend(ncol=2,loc='upper center');ax.grid(axis='y',alpha=.16)
    fig.savefig(TARGET/'01_七工况推进对照.png');plt.close(fig)
    fig,ax=plt.subplots(figsize=(12,5.8),layout='constrained');ax.axis('off')
    texts=[[CASE_LABELS[ms[i*2]['case']],outcome(ms[i*2]),outcome(ms[i*2+1]),'、'.join(ms[i*2+1]['unmet']) or '无'] for i in range(7)]
    table=ax.table(cellText=texts,colLabels=['开发工况','B1 完成情况','B2 完成情况','B2 终点/峰值未满足项'],loc='center',cellLoc='center',colWidths=[.22,.2,.23,.35])
    table.auto_set_font_size(False);table.set_fontsize(10);table.scale(1,2.8)
    colors={'完整达标':'#dcefdc','保护停止':'#f5dada','深度到位\n其他条件未满足':'#fff0cd','未到目标深度':'#e8edf1','仿真无效':'#e0dce8'}
    for i in range(7):
        for j in (1,2):table[(i+1,j)].set_facecolor(colors[texts[i][j]])
    for j in range(4):table[(0,j)].set_facecolor('#d5e4ec')
    ax.set_title('完整达标：深度、横向位置、姿态、稳定保持及全程接触保护均满足',pad=15,fontsize=14)
    fig.savefig(TARGET/'02_完整完成标准检查.png');plt.close(fig)
    fig,axes=plt.subplots(2,1,figsize=(12,8),sharex=True,layout='constrained')
    for ax,key,limit,ylabel in zip(axes,['peak_force_mN','peak_penetration_um'],[25,30],['接触合力峰值 / mN','最大穿透 / μm']):
        for j,(lab,col) in enumerate([('B1','#617b92'),('B2','#187d94')]):
            ax.bar(x+(j-.5)*.33,[m[key] for m in ms[j::2]],width=.3,label=lab,color=col)
        ax.axhline(limit,ls='--',color='#a85447',label='原保护阈值');ax.set(ylabel=ylabel);ax.grid(axis='y',alpha=.16);ax.legend(ncol=3)
    within=all(m['peak_force_mN']<25 and m['peak_torque_mNm']<.5 and m['peak_penetration_um']<30 for m in ms)
    axes[0].set_title('相同保护阈值下的物理步峰值；'+('本轮所有回合均未超限' if within else '包含超限失败回合'))
    axes[-1].set(xticks=x,xticklabels=labels)
    fig.savefig(TARGET/'03_接触载荷与穿透对照.png');plt.close(fig)


def report(ms,old,index):
    successful={policy:[CASE_LABELS[m['case']] for m in ms if m['policy']==policy and m['success']] for policy in ('B1','B2')}
    lines=['# B2-4 七工况配对实验报告','',
           '本轮沿用 B2-3 审查修正后的控制代码和候选参数，完成 7 个固定开发工况、14 次全新动力学运行。原模型、原 B1 与原试运行数据保留。','',
           f"完整达标：B1 {len(successful['B1'])}/7；B2 {len(successful['B2'])}/7。这是规定开发工况的计数，不是随机成功率。",'',
           'B1 达标工况：'+('、'.join(successful['B1']) or '无')+'。',
           'B2 达标工况：'+('、'.join(successful['B2']) or '无')+'。','',
           '## 全部结果','',
           '| 工况 | 策略 | 推进/mm | 完成时间/s | 停止时间/s | 峰值力/mN | 峰值力矩/mN·m | 穿透/μm | 搜索/回撤次数 | 正式结束原因 |',
           '|---|---|---:|---:|---:|---:|---:|---:|---|---|']
    for m in ms:
        completed='—' if m['success_time_s'] is None else f"{m['success_time_s']:.3f}"
        stopped='—' if m['stop_time_s'] is None else f"{m['stop_time_s']:.3f}"
        lines.append(f"| {CASE_LABELS[m['case']]} | {m['policy']} | {m['advance_mm']:.6f} | {completed} | {stopped} | {m['peak_force_mN']:.3f} | {m['peak_torque_mNm']:.6f} | {m['peak_penetration_um']:.3f} | {m['searches']}/{m['recoveries']} | {REASONS.get(m['termination'],m['termination'])} |")
    lines+=['','完成时间仅对真正达标回合填写，包含稳定保持；停止时间是撤销动作的时刻。终点图中看见针插入，不等于满足全部标准。','',
            '## B2 最终误差与未满足项','',
            '| 工况 | Z误差/μm | XY误差/μm | 总姿态误差/° | 终点或全程峰值未满足项 |','|---|---:|---:|---:|---|']
    for m in ms[1::2]:lines.append(f"| {CASE_LABELS[m['case']]} | {m['z_error_um']:.3f} | {m['xy_error_um']:.3f} | {m['angle_deg']:.6f} | {'、'.join(m['unmet']) or '无'} |")
    lines+=['','门槛保持原值：Z≤20 μm、XY≤50 μm、总姿态≤0.5°、低速度持续≥0.1 s；全程合力<25 mN、G点力矩<0.5 mN·m、穿透<30 μm。正式失败原因来自原运行状态机，未满足项是补充分析。','',
            '## 延长时间是否影响原 B1','',
            '| 工况 | 原B1 6s推进/mm | 本轮B1 20s推进/mm | 本轮B2 20s推进/mm |','|---|---:|---:|---:|']
    for i in range(7):lines.append(f"| {CASE_LABELS[ms[2*i]['case']]} | {old[i]:.6f} | {ms[2*i]['advance_mm']:.6f} | {ms[2*i+1]['advance_mm']:.6f} |")
    lines+=['','双方动作总预算均20 s，最终稳定观察最长1 s。B1原有停滞提前结束规则仍保留，因此比较的是原B1策略与搜索恢复组合策略，不是去掉B1停滞规则的额外消融。',
            'B2还包括减载和条件回撤，不能把全部差异单独归因于螺旋搜索。工况、参数和代码在运行前冻结，中途未按结果调参。','',
            '## 月报图片与原始证据','',
            '- [七工况推进对照](01_七工况推进对照.png)',
            '- [完整完成标准检查](02_完整完成标准检查.png)',
            '- [接触载荷与穿透对照](03_接触载荷与穿透对照.png)',
            '- [联合 B 真实轨迹回放](真实轨迹回放.gif)：深度到位但精度未达标的代表回合，不是成功案例',
            '- [回撤后搜索退出条件诊断](回撤后搜索退出条件诊断.md)',
            '- [汇总指标](matrix_metrics.json)、[完整回合索引](results_index.json)、[运行前冻结协议](frozen_protocol.json)','',
            'results_index.json 的每个 file 指向同级 matrix_v1_case_01～07 中的无损压缩轨迹；这些文件夹应随本目录一起保存。各工况保留源代码快照，汇总不复用旧试运行。','',
            '## 使用与复现','',
            '在项目工作目录执行。重新生成本轮汇总（不重跑动力学）：','',
            '```powershell',"& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.reporting.report_b2_matrix",'```','',
            '用冻结版本代码重新串行运行全部14回合（换用未使用过的tag，避免覆盖）：','',
            '```powershell',"& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.validation.run_b2_search --tag reproduce_matrix_01",'```','',
            '本轮原始计算采用3个进程队列、各工况独立成对运行；每回合算法与串行入口相同。运行耗时受并行负载影响，不作为控制策略效率指标。','',
            '## 结论边界和下一步','',
            '当前仍是未实物标定的简化接触/笛卡尔驱动环境，非CR5整机夹持仿真。256段开发模型的历史收敛缺口仍存在；本轮没有修复原SDF，也没有验证真实连接器摩擦参数。',
            '下一细分B2-5：根据全部结果整理剩余缺口与训练接口草案，先区分到深度、完整位姿达标和保护停止；独立测试集及消融协议另行冻结。不能把本轮开发工况当作独立测试或实机成功率。','']
    (TARGET/'B2-4七工况对照报告.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    dump(TARGET/'matrix_metrics.json',{'success_cases':successful,'metrics':ms,'old_B1_6s_advance_mm':old,'source_sha256':index['source_sha256']})


def recovery_diagnosis(runs):
    records=[]
    for r in runs[1::2]:
        def advance_at(t):
            row=min(r['trace'],key=lambda sample:abs(sample['time_s']-t))
            return (row['position_m'][2]-r['case']['start_origin_z_m'])*1000
        for event in r['policy_events']:
            if event['reason']!='SEARCH_ADVANCED':continue
            resume=[e for e in r['events'] if e['reason']=='B2_RECOVERY_RESUMED' and e['time_s']<=event['time_s']]
            stalls=[e for e in r['policy_events'] if e['reason']=='AXIAL_STALL' and e['time_s']<event['time_s']]
            if not resume or not stalls:continue
            advanced=advance_at(event['time_s']);blocked=advance_at(stalls[-1]['time_s'])
            records.append({'case':r['case']['name'],'time_s':event['time_s'],'exit_search_advance_mm':advanced,
                            'previous_stall_advance_mm':blocked,'still_before_previous_stall':advanced<blocked,
                            'termination':r['termination']})
    dump(TARGET/'recovery_transition_diagnosis.json',records)
    lines=['# 回撤后退出搜索的状态诊断','',
           '以下是本轮冻结策略的轨迹分析，不修改本轮策略、不重新判定任何成功。','',
           '| 工况 | 回撤后退出搜索时推进/mm | 之前受阻时推进/mm | 是否尚未回到受阻位置 | 最终结果 |','|---|---:|---:|---|---|']
    for r in records:lines.append(f"| {CASE_LABELS[r['case']]} | {r['exit_search_advance_mm']:.6f} | {r['previous_stall_advance_mm']:.6f} | {'是' if r['still_before_previous_stall'] else '否'} | {REASONS.get(r['termination'],r['termination'])} |")
    lines+=['','当前退出搜索条件是“相对这次搜索起点净前进0.10 mm”。如果起点位于回撤后的低处，这0.10 mm可能只是重新接近入口，并不能证明已经越过之前的受阻位置。',
            '这不是虚构运动：前进量来自真实积分；问题在于该进度条件是否足以代表搜索获得有效对准。',
            '对出现上述现象且随后再次受阻的回合，一个待检验解释是：第二次搜索过早退出，随后又因两次搜索预算已用尽而结束。此解释需要新版本或消融验证；不能只凭本表断言修正后一定成功。',
            '建议下一细分先设计区分“回到接触区域”和“超越历史受阻深度”的条件；仍只用可测相对位移、力和接触历史，不能直接读取真实孔中心。然后用新版本保留对照，不能覆盖本轮。','']
    (TARGET/'回撤后搜索退出条件诊断.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')


def main():
    index,runs=collect();_,historical=read_verified()
    for old_run,new_run in zip(historical[1::2],runs[::2]):
        assert old_run['controller']==new_run['controller']
        end=min(old_run['stop_time_s'],new_run['stop_time_s'])
        old_prefix=[r for r in old_run['trace'] if r['time_s']<=end+1e-10]
        new_prefix=[r for r in new_run['trace'] if r['time_s']<=end+1e-10]
        assert old_prefix==new_prefix, 'B1 changed before either stopping time'
    _,_,pilot=verified('pilot_v1_reviewfix_x100')
    ignore={'wall_seconds','physical_steps_per_second'}
    assert {k:v for k,v in runs[3].items() if k not in ignore}=={k:v for k,v in pilot[1].items() if k not in ignore}, 'X pilot not reproduced'
    old=[(r['final']['position_m'][2]-r['case']['start_origin_z_m'])*1000 for r in historical[1::2]]
    ms=[metrics(r) for r in runs];plots(ms,old);report(ms,old,index);recovery_diagnosis(runs)
    figures(TARGET,runs)
    replay(TARGET,runs[11])
    dump(TARGET/'verification_summary.json',{'completed_runs':len(runs),'fresh_paired_cases':7,'source_and_config_frozen':True,
         'all_claimed_successes_rechecked_including_hold':True,'paired_conditions_equal':True,'time_and_budget_checks':True,
         'historical_B1_verified':True,'B1_prefix_matches_original_6s_runs':True,'X_B2_matches_pilot_except_wall_timing':True,'phase':'B2-4_COMPLETE'})
    print(json.dumps(ms,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
