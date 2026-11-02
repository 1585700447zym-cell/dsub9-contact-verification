"""Produce Chinese evidence report from the completed dynamic matrix."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from tools.validation.validate_dynamic_actuator import OUTPUT, sources
from tools.validation.run_contact_cases import ROOT
from tools.validation.diagnose_v1_applicability import fingerprint
from tools.visualization.font_support import find_chinese_font


def read(path):return json.loads(path.read_text(encoding='utf-8'))


def main():
    results=read(OUTPUT/'dynamic_results.json')
    if results['source_sha256']!=sources() or results['historical_source_sha256']!=fingerprint():
        raise RuntimeError('Stale dynamic evidence: current sources do not match')
    runs={}
    for file in results['run_files']:
        batch=read(OUTPUT/file)
        if batch['source_sha256']!=results['source_sha256'] or batch['historical_source_sha256']!=results['historical_source_sha256']:
            raise RuntimeError('Batch fingerprints do not match')
        runs[file[:-5]]=batch['runs']
    auxiliary=read(OUTPUT/'auxiliary.json');summary=results['summary'];base=runs['n128_dt0.0002']
    if auxiliary['source_sha256']!=results['source_sha256'] or auxiliary['historical_source_sha256']!=results['historical_source_sha256']:
        raise RuntimeError('Auxiliary fingerprints do not match')
    font_manager.fontManager.addfont(str(find_chinese_font()))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(find_chinese_font())).get_name(),
                         'axes.unicode_minus':False,'font.size':11,'figure.dpi':150})
    contact=next(r for r in base if r['name']=='combined_a_scale_0.75')
    fig,ax=plt.subplots(2,1,figsize=(10,7),layout='constrained',sharex=True)
    for row,label in [(contact,'启用接触'),(auxiliary['contact_disabled'],'关闭接触的对照')]:
        t=np.array([x['time_s'] for x in row['trace']]);z=np.array([x['position_m'][2] for x in row['trace']])
        ax[0].plot(t,(z-z[0])*1e3,label=label)
        ax[1].plot(t,[np.linalg.norm(x['contact_wrench_M'][:3]) for x in row['trace']],label=label)
    ax[0].set(ylabel='实际推进量 / mm',title='相同命令与初始联合偏差：接触反力实际改变运动')
    ax[1].set(xlabel='仿真时间 / s',ylabel='接触合力 / N')
    for a in ax:a.legend();a.grid(alpha=.2)
    fig.savefig(OUTPUT/'01_接触反力改变运动.png');plt.close(fig)

    fig,axes=plt.subplots(2,1,figsize=(10,7),layout='constrained',sharex=True)
    for key,batch in runs.items():
        row=next(r for r in batch if r['name']=='combined_a_scale_0.75')
        t=[x['time_s'] for x in row['trace']]
        axes[0].plot(t,[(x['position_m'][2]+.004)*1e3 for x in row['trace']],label=key)
        axes[1].plot(t,[np.linalg.norm(x['contact_wrench_M'][:3]) for x in row['trace']],label=key)
    axes[0].set(ylabel='实际推进量 / mm',title='相同较强联合偏差：128/256段与物理时间步对照')
    axes[1].set(xlabel='仿真时间 / s',ylabel='接触合力 / N')
    for a in axes:a.legend(ncol=2);a.grid(alpha=.2)
    fig.savefig(OUTPUT/'02_动态分辨率与时间步.png');plt.close(fig)

    row=auxiliary['force_guard_probe'];t=np.array([x['time_s'] for x in row['trace']])
    fig,axes=plt.subplots(3,1,figsize=(10,8),layout='constrained',sharex=True)
    axes[0].plot(t,[np.linalg.norm(x['contact_wrench_M'][:3]) for x in row['trace']])
    axes[0].axhline(row['metadata']['config']['stop_force_N'],ls='--',color='red',label='本项保护功能测试阈值')
    axes[0].set(ylabel='接触合力 / N',title='保护触发、受限停止与条件回撤（阈值未经实物标定）');axes[0].legend()
    axes[1].plot(t,[x['velocity_world'][2]*1e3 for x in row['trace']]);axes[1].set(ylabel='实际Z速度 / mm/s')
    axes[2].plot(t,[(x['position_m'][2]+.004)*1e3 for x in row['trace']]);axes[2].set(ylabel='实际推进量 / mm',xlabel='仿真时间 / s')
    for e in row['events']:
        for a in axes:a.axvline(e['time_s'],ls=':',color='gray',alpha=.6)
    for a in axes:a.grid(alpha=.2)
    fig.savefig(OUTPUT/'03_保护停止与回撤.png');plt.close(fig)

    all_runs=[r for batch in runs.values() for r in batch]+auxiliary['free_axes']+[auxiliary['contact_disabled'],auxiliary['force_guard_probe']]
    rates=[r['timing']['physical_steps_per_second'] for r in all_runs]
    comparisons=[x for rows in summary['comparisons'].values() for x in rows]
    failed=[x for x in comparisons if not x['pass']]
    rows='\n'.join(f"| {r['name']} | {r['end_drive']['position_m'][2]*1e3+4:.3f} | {r['peaks']['force_N']:.5f} | {r['peaks']['penetration_m']*1e6:.3f} | {r['recovery']} |" for r in base)
    gates='\n'.join(f"- `{k}`：{'通过' if v else '未通过'}。" for k,v in summary['gates'].items())
    maxpos=max(x['end_drive_position_difference_m'] for x in comparisons)
    maxangle=max(x['end_drive_angle_difference_rad'] for x in comparisons)
    maxforce=max(x['peak_force_relative_difference'] or 0 for x in comparisons)
    maxstop=max(np.linalg.norm(r['stop_check_0p2']['velocity_world'][:3]) for r in all_runs if r['stop_check_0p2'])
    recovery_distances=[(r['stopped']['position_m'][2]-min(x['position_m'][2] for x in r['trace'] if x['time_s']>=r['stopped']['time_s'])) for r in all_runs if r['recovery']=='ACCEPTED']
    axis_moves=[]
    for i,r in enumerate(auxiliary['free_axes']):
        if i<3: axis_moves.append(r['end_drive']['position_m'][i]-r['trace'][0]['position_m'][i])
        else: axis_moves.append(2*np.arctan2(r['end_drive']['quaternion_wxyz'][i-2],r['end_drive']['quaternion_wxyz'][0]))
    text=f'''# 动态执行器开发验证（2026-09-16）

**本轮结论：{summary['verdict']}。** 动态执行器、受限停止、条件回撤与对照数据已实现；本轮未实现B1固定导纳、B2搜索、强化学习或完整CR5。所有力学参数均为仿真假设。

## 动态证据

公头只在初始化时设置实际位姿，此后每个物理子步施加受限力/力矩并调用MuJoCo动力学积分。目标轨迹不等于实际轨迹。较强联合偏差A（45μm、−30μm、+1.125°、−1.125°）与关闭接触对照相比，推进窗口结束时位置相差{summary['contact_counterfactual_position_difference_m']*1e6:.2f}μm，证明接触反力影响运动。

全矩阵含{len(all_runs)}回合：4组模型/时间步各7个工况、6个单轴自由运动、1个关闭接触对照、1个专门的低阈值保护测试。正常矩阵主推进速度1mm/s，参考加速度上限5mm/s²；同轴回合推进窗口4.1s，其余1.2s，停止观察0.25s，获准回撤再观察0.85s。较短窗口是底层接触验证，不是完整插入成功率试验，也不证明长时训练稳定。

六轴自由运动窗口的对应位移/转角为{[round(float(x),8) for x in axis_moves]}（前三项m、后三项rad）。同轴自由跟踪误差{base[0]['free_tracking_error_m']*1e6:.2f}μm；所有可用停止检查中，停止后约0.2s时最大线速度为{maxstop*1e6:.3f}μm/s。停止检查采用0.2s截止之前的最后控制采样（最多提前2ms），避免晚采样使门槛虚假通过；物理子步仍全部执行保护及峰值统计。首次停止与回撤结束停止分别保存。

| 128段、0.2ms工况 | 推进窗口末实际推进/mm | 全回合峰值合力/N | 全回合最大穿透/μm | 回撤状态 |
|---|---:|---:|---:|---|
{rows}

合力为所有接触在世界坐标下的矢量和，不等于逐接触法向力之和。力矩同时保存关于插合原点M和暂定夹持点G的值，G局部坐标为(0,0,−14.5mm)。质量0.05kg、三轴惯量2e-5kg·m²、重力0，不代表真实CR5负载等效惯量；无柔性手指或夹持滑移。

## 原生CCD异常与动态碰撞后端

首轮原生CCD动态试验在横向偏移100μm工况停止后报告约539.847μm穿透，保护将回合终止；完整失败基准保存在diagnostic_nativeccd/baseline_failed.json。冻结同一实际位姿后可复现异常，提高CCD迭代次数仍存在。切换为MuJoCo的MPR碰撞后端后，该姿态最大穿透约0.005952μm，且该横向动态试验能够停止和回撤。

因此最终动态矩阵使用MPR，并显式记录disableflags及配置。孔的128/256分块几何、接触响应参数、穿透保护阈值未因此放宽。独立的几何上界和接触覆盖复核见ccd_diagnostic.json；此修正针对已复现的数值异常，不能视为所有姿态的碰撞鲁棒性证明。原接触覆盖交付包仍保留原设置和结论，不回写历史结果。

## 分辨率和时间步

基准为128段、0.2ms；对照为256段、0.2ms，以及128段的0.1/0.4ms，控制周期均为2ms。21组成对比较中{len(failed)}组未通过预先设定的开发一致性门槛。推进窗口末位置差最大{maxpos*1e6:.3f}μm，姿态差最大{np.degrees(maxangle):.5f}°；有效峰值合力（至少一侧>0.001N）相对差最大{maxforce:.1%}。峰值取物理子步记录，曲线为控制周期采样。

门槛为位置差<20μm、姿态差<0.1°、有效峰值合力相对差<20%，并要求事件原因序列一致。其意义限于这些工况的数值一致性，不能解释成对实物误差小于20%。此外，当前比较未替代圆孔分块方向、接触参数、质量惯量和真实安装关系的敏感性验证。

## 保护与恢复的边界

正常矩阵力阈值0.025N，力矩阈值0.0005N·m，穿透停止阈值30μm；专门保护功能测试使用0.003N以验证触发路径。这些是模型内开发阈值，不是连接器或CR5安全额定值，不能据此操作实机。

每个物理子步检查状态、警告、接触载荷与穿透；异常数据先检查再进行坐标换算。检测到非有限值或严重异常即清驱动、终止；普通超限撤销推进、用受限驱动减速。停止命令可以立即改变参考速度，实际速度由有限力减速，不通过改qvel实现瞬停。

回撤要求状态有限、线速度<10μm/s、角速度<0.001rad/s、力低于恢复阈值且有剩余行程。仅允许一次；参考回撤预算250μm、速度0.5mm/s、时间上限1s。实际惯性超调另外统计，本轮获准回撤最大实际距离{max(recovery_distances,default=0)*1e6:.3f}μm；不能宣称物理位移严格不超过250μm。保护触发后仍可能出现载荷峰值，原始记录保留全部过程。

## 开发验收

{gates}

## 运行成本与下一步

本机完整驱动、保护及日志开销下，物理步吞吐范围{min(rates):.0f}—{max(rates):.0f}步/s，中位数{np.median(rates):.0f}步/s。原始文件另记每控制步吞吐和单回合耗时，计时不包含模型编译；这不是GPU强化学习吞吐，4060/5070Ti的训练速度仍需后续实测。

{'本轮门槛通过后可以继续实现B1固定导纳：Z受限推进，XY和倾角由接触力调节，再检验位姿联合误差下能否有效解除受阻。' if all(summary['gates'].values()) else '本轮仍有未通过项，下一步应先针对下列失败比较定位原因并修复，不能把当前配置冻结为已验收的训练环境：'+str(failed)}

同轴无接触推进达到目标平面仅用于自由运动验证，不计作导纳有效性或装配成功。实际电连接、簧片变形、锁止与插拔力不在当前模型范围内。

## 复现与追溯

```text
python -m tools.validation.validate_dynamic_actuator
python -m tools.reporting.report_dynamic_actuator
```

可用`--resume`复用指纹一致的完整批次。结果保存本次代码与{len(results['historical_source_sha256'])}项历史输入指纹，原覆盖模型与报告未修改。XML由既有生成器在内存构建，metadata记录实际时间步、分块数、驱动参数、质量、惯量及测量语义。

实现依据：[MuJoCo官方动力学与力施加API](https://mujoco.readthedocs.io/en/stable/APIreference/APIfunctions.html#mj-applyft)。驱动力通过等效力矩转换施加到G，实际位姿由mj_step积分；四元数目标使用mj_integratePos，姿态误差使用mj_differentiatePos。
'''
    (OUTPUT/'动态执行器验证报告.md').write_text(text,encoding='utf-8',newline='\n')
    (OUTPUT/'README.md').write_text('''# 动态执行器开发包

先阅读[动态执行器验证报告](动态执行器验证报告.md)。三张中文图分别展示接触反力改变运动、动态分辨率与时间步对照、保护停止与回撤。

dynamic_results.json保存总验收结论；n128/n256批次文件保存全部配置、曲线与子步峰值；auxiliary.json保存六轴运动、关闭接触及保护功能测试。当前只有底层驱动，不是固定导纳或强化学习环境。
''',encoding='utf-8',newline='\n')
    paths=[p for p in OUTPUT.rglob('*') if p.is_file() and p.name!='delivery_manifest.json']
    paths += [ROOT/p for p in results['source_sha256']]
    paths += [ROOT/'tools/reporting/report_dynamic_actuator.py',ROOT/'docs/superpowers/specs/2026-09-16-dynamic-actuator-design.md',ROOT/'docs/superpowers/plans/2026-09-16-dynamic-actuator.md']
    manifest={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}
    (OUTPUT/'delivery_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'verdict':summary['verdict'],'gates':summary['gates'],'comparisons_failed':len(failed),
                      'max_position_difference_um':maxpos*1e6,'max_force_relative_difference':maxforce,
                      'step_rate_median':float(np.median(rates))},ensure_ascii=False))


if __name__=='__main__':main()
