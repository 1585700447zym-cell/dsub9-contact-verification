"""Chinese figures and claims tied to all prespecified paired B1 runs."""
import hashlib
import json
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from tools.validation.run_b1_baseline import OUTPUT, hashes, cases, read_checkpoint, dump
from tools.validation.diagnose_v1_applicability import fingerprint
from tools.visualization.font_support import find_chinese_font

LABELS=['同轴','X +100 μm','Y −100 μm','Roll +1.5°','联合 A ×0.75','联合 B ×0.75','联合 A 全幅']
REASONS={'GEOMETRIC_SUCCESS':'几何完成','TIME_LIMIT':'到达时限','NO_PROGRESS':'推进停滞',
         'TARGET_POSE_NOT_SETTLED':'目标位姿未稳定','FORCE_LIMIT':'合力超限',
         'PENETRATION_LIMIT':'穿透超限','TORQUE_LIMIT':'力矩超限'}
COLORS=['#778391','#18799C']


def read_verified():
    code=hashes();historical=fingerprint()
    index=read_checkpoint(OUTPUT/'results_index.json',code,historical)
    expected=[f'runs/{c.name}_{suffix}.json' for c in cases() for suffix in ('reference','b1')]
    if [r['file'] for r in index['runs']]!=expected:
        raise RuntimeError('Expected all 14 prespecified runs, in protocol order')
    runs=[read_checkpoint(OUTPUT/file,code,historical) for file in expected]
    for k,(entry,r) in enumerate(zip(index['runs'],runs)):
        if entry['termination']!=r['termination'] or entry['case']!=r['case']['name']:
            raise RuntimeError('Run and index disagree')
        if not np.isfinite(np.array([x['position_m']+x['quaternion_wxyz']+x['contact_wrench_G'] for x in r['trace']])).all():
            raise RuntimeError('Nonfinite trace')
        if r['controller']['name']!=('zero_feedback_reference' if k%2==0 else 'B1_fixed_admittance'):
            raise RuntimeError('Unexpected controller order')
    for a,b in zip(runs[::2],runs[1::2]):
        if a['case']!=b['case'] or a['environment']!=b['environment'] or a['controller']['config']!=b['controller']['config']:
            raise RuntimeError('Paired conditions differ')
    return index,runs


def depth(run):return (run['final']['position_m'][2]-run['case']['start_origin_z_m'])*1000


def angles(trace):
    q=np.array([r['quaternion_wxyz'] for r in trace])
    return np.degrees(2*np.arccos(np.clip(np.abs(q[:,0])/np.linalg.norm(q,axis=1),0,1)))


def reason(run):return REASONS.get(run['termination'],run['termination'])


def main():
    index,runs=read_verified()
    font_manager.fontManager.addfont(str(find_chinese_font()))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(find_chinese_font())).get_name(),
                         'axes.unicode_minus':False,'font.size':11,'figure.dpi':150})
    representative=runs[8:10]
    fig,axes=plt.subplots(3,1,figsize=(10,9),sharex=True,layout='constrained')
    for r,label,color in zip(representative,['零反馈参考','B1 固定导纳'],COLORS):
        t=np.array([x['time_s'] for x in r['trace']]);z=np.array([x['position_m'][2] for x in r['trace']])
        axes[0].plot(t,(z-r['case']['start_origin_z_m'])*1000,label=f'{label}（{reason(r)}）',color=color)
        axes[1].plot(t,[np.linalg.norm(x['contact_wrench_M'][:3])*1000 for x in r['trace']],color=color)
        axes[2].plot(t,angles(r['trace']),color=color)
        for a in axes:
            if r['stop_time_s'] is not None:a.axvline(r['stop_time_s'],ls=':',color=color,alpha=.7)
    axes[0].set(ylabel='实际推进量 / mm',title='预定代表工况：联合 A ×0.75 的接触反馈对照')
    axes[0].legend(loc='best')
    axes[1].set(ylabel='接触合力 / mN');axes[1].axhline(25,ls='--',color='#A25045',label='模型开发停止阈值')
    axes[1].legend()
    axes[2].set(xlabel='仿真时间 / s（虚线为撤销推进时刻）',ylabel='相对目标总姿态角 / °')
    for a in axes:a.grid(alpha=.18)
    fig.savefig(OUTPUT/'01_B1与零反馈对照.png');plt.close(fig)

    values=np.array([[depth(r) for r in runs[::2]],[depth(r) for r in runs[1::2]]])
    fig,ax=plt.subplots(figsize=(12,6),layout='constrained');x=np.arange(7)
    for k,(label,color) in enumerate(zip(['零反馈参考','B1 固定导纳'],COLORS)):
        bars=ax.bar(x+(k-.5)*.34,values[k],width=.32,label=label,color=color)
        ax.bar_label(bars,fmt='%.3f',fontsize=9,padding=4)
    ax.axhline(4,ls='--',color='#A25045',label='名义目标推进量 4 mm')
    ax.set(xticks=x,xticklabels=LABELS,ylabel='回合结束时实际推进量 / mm',ylim=(0,4.65),
           title='全部 7 个固定开发工况：推进量不等于装配成功')
    ax.legend(loc='upper center',ncol=3);ax.grid(axis='y',alpha=.18)
    fig.savefig(OUTPUT/'02_全部工况推进对比.png');plt.close(fig)

    rows=[];records=[]
    for i,label in enumerate(LABELS):
        for j,cname in enumerate(['零反馈','B1']):
            r=runs[2*i+j]
            rows.append(f"| {label} | {cname} | {depth(r):.4f} | {r['peaks']['force_N']*1000:.3f} | {r['peaks']['penetration_m']*1e6:.3f} | {reason(r)} | {'是' if r['contact_observed'] else '否'} |")
            records.append({'case':r['case']['name'],'label':label,'controller':cname,'advance_mm':depth(r),
                            'termination':r['termination'],'termination_zh':reason(r),'contact_observed':r['contact_observed']})
    successful=[[LABELS[i] for i,r in enumerate(runs[k::2]) if r['termination']=='GEOMETRIC_SUCCESS'] for k in (0,1)]
    a,b=representative;delta=depth(b)-depth(a)
    limitations=['7 个固定开发工况，未开展随机误差统计试验。',
                 '几何完成不代表电连接、锁止或实机插装成功。',
                 '孔离散精度仍影响部分组合偏差，256 段仅作为开发配置。',
                 '质量、夹持关系、接触参数及保护阈值尚未实物标定。']
    next_steps=['B2：加入受限搜索和条件回撤，先处理 B1 停滞工况。',
                '冻结评价协议，划分开发集与独立测试集。',
                '再接入四维残差 SAC，并与固定基线比较。']
    evidence=f'联合 A ×0.75：零反馈推进 {depth(a):.3f} mm，B1 推进 {depth(b):.3f} mm，差值 {delta:+.3f} mm。'
    summary=f'完成 7 个预定工况、14 个配对回合。零反馈几何完成 {len(successful[0])} 项，B1 几何完成 {len(successful[1])} 项。'
    facts={'as_of':'2026-09-16','status_title':'D-sub9 接触驱动仿真与固定导纳基线',
           'experiment_summary':summary,'representative_case':'combined_a_scale_0.75',
           'improvement_statement':evidence,'limitations':limitations,'next_steps':next_steps,
           'successful_cases':successful,'cases':LABELS,'advance_mm':values.tolist(),'records':records,
           'source_files':{e['file']:hashlib.sha256((OUTPUT/e['file']).read_bytes()).hexdigest() for e in index['runs']}}
    dump(OUTPUT/'monthly_facts.json',facts)
    text=f'''# B1 固定导纳开发对照（截至 2026-09-16）

{summary} 本轮结果用于建立可复现的控制基线，不能作为总体成功率或论文效果证明。

## 当前发现

{evidence} 两个回合分别为“{reason(a)}”和“{reason(b)}”。预定代表工况不会因其他工况表现更好而替换。

零反馈几何完成工况：{'、'.join(successful[0]) or '无'}。B1 几何完成工况：{'、'.join(successful[1]) or '无'}。同轴工况若无接触，其完成只证明自由推进，不能证明导纳有效。

## 协议与判据

全部配对使用同一 256 段孔模型、MPR 碰撞后端、0.2 ms 物理时间步、2 ms 控制周期和 1 mm/s 名义 Z 推进速度。推进最多 6 s，撤销推进后最多观察 1 s。每回合重置环境与控制器，参数在工况间不调整。预试验保存在 pilot/，不混入正式本轮 14 个回合。

B1 根据插合原点 M 处、世界坐标下的 Fx、Fy、Tx、Ty 计算 XY 与 roll/pitch 方向的修正速度。方程为 M_a dv/dt + D_a v = wrench。虚拟质量为 (0.2,0.2,0.0002,0.0002)，阻尼为 (20,20,0.01,0.01)，采用 SI 单位。修正速度上限分别为 (0.5 mm/s,0.5 mm/s,0.02 rad/s,0.02 rad/s)，累计命令修正预算为 (0.5 mm,0.5 mm,0.08 rad,0.08 rad)。底层执行器另有限速、加速度、驱动力与独立保护。预算限制命令积分，不直接限制实际位移。

控制器不读取真实针孔偏差。真实初始误差仅用于场景设置和离线评价。零反馈对照使用相同驱动、Z 命令与保护，关闭上述四维反馈。它不是 B2 搜索控制器。

达到目标平面仅触发停止。几何完成还要求 Z 误差 ≤20 μm、XY 合误差 ≤50 μm、含偏航的总姿态误差 ≤0.5°、线速度 ≤10 μm/s、角速度 ≤0.001 rad/s，连续满足至少 0.1 s。全回合峰值合力须 <25 mN、G 处合力矩 <0.5 mN·m、最大穿透 <30 μm。这些是模型开发条件。保护触发后，实际状态仍由动力学积分产生。

## 全部结果

| 工况 | 控制 | 最终推进/mm | 峰值合力/mN | 最大穿透/μm | 终止原因 | 观察到接触 |
|---|---|---:|---:|---:|---|---|
{chr(10).join(rows)}

联合 A 全幅为 (x,y,roll,pitch)=(+60 μm,−40 μm,+1.5°,−1.5°)，B 为反向；0.75 倍工况相应为 (45 μm,30 μm,1.125°,1.125°) 的有符号组合。起始 M 原点 z=−4 mm，目标 z=0。最终推进量包含停止后的实际运动，不是只截取最佳瞬间。

图中的力来自 2 ms 控制采样；表中峰值来自每个物理子步。合力是接触力的矢量和，不能当作所有接触法向载荷之和。姿态图表示相对目标的总旋转角。

## 继承的限制

此前动态开发门槛未全部通过，原报告 DYNAMIC_DEVELOPMENT_GATE_FAIL 保留。两项 128 段半幅工况在停止后 0.2 s 未达到旧低速阈值，延长观察至 2 s 后达到阈值，但不修改旧结果。相同实际位姿的 128/256 接触对照仍显示局部分辨率敏感，不能把 256 段解释为物理真值。限定诊断见 configuration_review.json。

{chr(10).join('- '+v for v in limitations)}

当前不含完整 CR5、手指柔性、夹持滑移与真实六维传感器噪声。本轮也不含学习、主动搜索或自动重试。精细接触模型本身不构成论文算法创新。

## 下一步

{chr(10).join('- '+v for v in next_steps)}

## 月报使用

可汇报“已建立接触影响运动的动态仿真和固定导纳对照，保存全部工况结果及失败原因”。展示 01_B1与零反馈对照.png 与 02_全部工况推进对比.png，并区分推进改善、几何完成和实机装配。不得把固定样本计数换算为正式成功率。

复现：`python -m tools.validation.run_b1_baseline --resume`，然后 `python -m tools.reporting.report_b1`。每个回合与索引保存源码及 {len(index['historical_source_sha256'])} 项历史输入指纹；生成图表前检查一致性与配对条件。
'''
    (OUTPUT/'B1固定导纳_开发报告.md').write_text(text,encoding='utf-8',newline='\n')
    print(summary);print(evidence)


if __name__=='__main__':main()
