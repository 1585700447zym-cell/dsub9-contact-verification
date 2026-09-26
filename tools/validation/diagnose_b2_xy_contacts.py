"""Offline X/Y contact diagnosis: saved forces, reconstructed geometry, no mj_step."""
import argparse
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path
import mujoco
import numpy as np
from matplotlib import pyplot as plt
from tools.dynamics.cartesian import CartesianEnvironment
from tools.validation.diagnose_b2_contacts import snapshot, projected_tip_overhang
from tools.validation.run_contact_cases import ROOT, FORMAL_MODEL
from tools.validation.run_b1_baseline import dump
from tools.validation.run_b2_y_probe import new_target, sha
from tools.reporting.report_b2_exit_gate import configure_font
from tools.reporting.report_b2_xy_probe import audit as audit_x, OUT as X_OUT
from tools.reporting.report_b2_y_probe import audit as audit_y, OUT as Y_OUT

OUT=ROOT/'deliverables/b2_xy_contact_diagnosis'
OFFSETS=(-.1,0.,.2,.4,.6,.726,1.,1.1,1.5,2.)


def sample_at(run,time):
    row=min(run['trace'],key=lambda s:abs(s['time_s']-time))
    if abs(row['time_s']-time)>1e-8:raise ValueError('Requested time is not a saved control sample')
    return row


def contact_summary(contacts):
    per_pin={};layers=set()
    for c in contacts:
        pin=next((n for n in c['geoms'] if n.startswith('pin_')),None)
        if pin is None:continue
        hole=next((n for n in c['geoms'] if n.startswith('hole_convex')),None)
        layer=hole.split('_')[-2] if hole else 'other'
        layers.add(layer)
        entry=per_pin.setdefault(pin,{'points':0,'max_penetration_um':0.})
        entry['points']+=1;entry['max_penetration_um']=max(entry['max_penetration_um'],c['penetration_m']*1e6)
    z=[c['position_m'][2]*1000 for c in contacts]
    return {'active_pins':sorted(per_pin),'contact_points':len(contacts),'per_pin':per_pin,'layers':sorted(layers),
            'z_range_mm':[min(z),max(z)] if z else None}


def rim_z_range(center_z,rotation,radius):
    extent=float(radius*np.linalg.norm(np.asarray(rotation)[2,:2]))
    return [float(center_z-extent),float(center_z+extent)]


def inspect(env,run,row,holes,params):
    s=snapshot(env,row,holes,params)
    assert env.data.time==0., 'Geometry reconstruction must not advance physics'
    s['advance_mm']=(row['position_m'][2]-run['case']['start_origin_z_m'])*1000
    s['xy_um']=(np.array(row['position_m'][:2])*1e6).tolist()
    s['policy_phase']=row['policy_phase'];s['contact_summary']=contact_summary(s['contacts'])
    s['saved_raw_command_world']=row['raw_command_world']
    for pin in s['pins']:
        pin['tip_rim_z_range_m']=rim_z_range(pin['tip_center_m'][2],pin['rotation'],pin['radius_m'])
        pin['rotation_contribution_xy_um']=((np.array(pin['tip_xy_offset_m'])-row['position_m'][:2])*1e6).tolist()
    # Pure geometric counterfactual, not a motion command or physics prediction.
    s['identity_rotation_overhang_um']=projected_tip_overhang(np.array(row['position_m'][:2]),np.eye(3),.0005,params['bore_radius'])*1e6
    return s


def evidence():
    root=ET.parse(FORMAL_MODEL).getroot()
    params={c.get('key'):float(c.get('value')) for c in root.findall('.//extension/plugin/instance/config')}
    holes={g.get('name')[-2:]:np.fromstring(g.get('pos'),sep=' ') for g in root.findall('.//geom[@type="sdf"]')}
    env=CartesianEnvironment(segments=256);cases=[];runs={};inputs={}
    for label,base,tag,audit in [('X',X_OUT,'first_frozen_x100',audit_x),('Y',Y_OUT,'first_frozen_y100',audit_y)]:
        old,new,a,index=audit(base/tag);t0=a['identical_through_s']
        assert env.metadata()==new['environment']
        e={'label':label,'case':new['case']['name'],'trigger_time_s':t0,'candidate_metrics':a['candidate_metrics'],
           'reference_metrics':a['reference_metrics'],'snapshots':{},'first_contact_after_trigger':{},'probe_execution':a['probe_execution']}
        for version,run in [('reference',old),('candidate',new)]:
            runs[(label,version)]=run
            e['snapshots'][version]={str(d):inspect(env,run,sample_at(run,t0+d),holes,params) for d in OFFSETS}
            later=[s for s in run['trace'] if s['time_s']>t0+1e-9 and s['phase']=='RUNNING' and s['contact_count']>0]
            e['first_contact_after_trigger'][version]=inspect(env,run,later[0],holes,params) if later else None
        # Align force input at row k with the resulting command saved at row k+1.
        pairs=[(u,v) for u,v in zip(new['trace'],new['trace'][1:]) if t0-1e-9<=u['time_s']<=t0+2+1e-9 and v['policy_phase']=='SEARCH']
        c=new['controller']['config']
        predicted=[float(np.clip(c['axial_gain_m_s_N']*(c['search_force_N']+u['contact_wrench_M'][2]),-c['unload_speed_m_s'],c['search_forward_speed_m_s'])) for u,v in pairs]
        np.testing.assert_allclose(predicted,[v['raw_command_world'][2] for u,v in pairs],rtol=0,atol=1e-14)
        e['checked_axial_commands']=len(pairs)
        e['axial_law']={'gain_m_s_N':c['axial_gain_m_s_N'],'zero_command_Fz_mN':-c['search_force_N']*1000}
        e['next_z_commands_mm_s']={str(d):sample_at(new,t0+d+new['environment']['config']['control_period'])['raw_command_world'][2]*1000 for d in OFFSETS}
        cases.append(e)
        paths=[base/tag/'results_index.json',base/tag/index['runs'][0]['file'],ROOT/index['reference']['file'],ROOT/index['reference']['index'],base/'delivery_manifest.json']
        for p in paths:inputs[p.relative_to(ROOT).as_posix()]=sha(p)
    return cases,runs,params,inputs


def figures(target,cases,runs,params):
    configure_font()
    colors={'X':'#008d91','Y':'#bb6953'}
    fig,axes=plt.subplots(1,3,figsize=(14,4.8),layout='constrained')
    for e in cases:
        label=e['label'];s=e['snapshots']['candidate']['0.0'];x=np.arange(1,10)
        values=[p['main_aperture_overhang_m']*1e6 for p in s['pins']]
        axes[0].plot(x,values,'o-',color=colors[label],label=label+' 工况')
        rows=[r for r in runs[(label,'candidate')]['trace'] if e['trigger_time_s']-1e-9<=r['time_s']<=e['trigger_time_s']+1+1e-9]
        t=np.array([r['time_s']-e['trigger_time_s'] for r in rows])
        axes[1].plot(t,[(r['position_m'][2]+.004)*1000 for r in rows],color=colors[label],label=label+' 工况')
        axes[2].plot(t,[r['contact_wrench_M'][2]*1000 for r in rows],color=colors[label],label=label+' 工况')
    axes[0].axhline(0,color='#555555',ls=':');axes[0].set(title='触发时：针尖投影与主孔边界',xlabel='针编号',ylabel='投影超界 / μm（正值超出边界）',xticks=np.arange(1,10))
    axes[1].axhline(.35,color='#777777',ls=':',label='退出深度门槛约 0.35 mm')
    axes[1].set(title='暂停后的真实推进',xlabel='相对触发时间 / s',ylabel='整体推进 / mm')
    axes[2].axhline(-8,color='#777777',ls=':',label='SEARCH 轴向指令零点 −8 mN')
    axes[2].set(title='记录的轴向接触力',xlabel='相对触发时间 / s',ylabel='Fz / mN')
    for ax in axes:ax.grid(alpha=.15);ax.legend(fontsize=8)
    fig.suptitle('B2-5.5 月报诊断｜无接触不等于已对准',fontsize=16)
    fig.supxlabel('投影超界不是当前穿透；几何来自保存位姿，受力和推进来自原始轨迹。X 在 +0.726 s 后进入 INSERT。',fontsize=10)
    fig.savefig(target/'01_月报受阻差异.png');plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    y=next(e for e in cases if e['label']=='Y')
    for d in (0.,.4,.6,1.,1.1,2.):
        s=y['snapshots']['candidate'][str(d)]
        axes[0,0].plot(range(1,10),[p['main_aperture_overhang_m']*1e6 for p in s['pins']],'o-',label=f'+{d:g} s')
    axes[0,0].axhline(0,color='#555555',ls=':');axes[0,0].set(title='Y：九针投影超界随时间变化',xlabel='针编号',ylabel='投影超界 / μm',xticks=range(1,10))
    ds=(.4,.6,1.,1.1,2.)
    counts=np.array([[y['snapshots']['candidate'][str(d)]['contact_summary']['per_pin'].get(f'pin_{i:02}',{}).get('points',0) for i in range(1,10)] for d in ds])
    im=axes[0,1].imshow(counts,aspect='auto',cmap='Blues')
    for j in range(len(ds)):
        for k in range(9):axes[0,1].text(k,j,str(counts[j,k]),ha='center',va='center',fontsize=8,color='white' if counts[j,k]>counts.max()*.5 else 'black')
    axes[0,1].set(title='Y：重建接触点按针归组（不是受力）',xlabel='针编号',ylabel='相对触发时间 / s',xticks=range(9),xticklabels=range(1,10),yticks=range(len(ds)),yticklabels=ds)
    for version,style,label in [('reference','--','原 V2'),('candidate','-','暂停候选')]:
        r=runs[('Y',version)];rows=[s for s in r['trace'] if y['trigger_time_s']-1e-9<=s['time_s']<=y['trigger_time_s']+2+1e-9]
        t=np.array([s['time_s']-y['trigger_time_s'] for s in rows]);p=np.array([s['position_m'] for s in rows])*1e6
        axes[1,0].plot(t,p[:,1],style,label=label+' Y 位置')
        axes[1,1].plot(t,[s['contact_wrench_M'][2]*1000 for s in rows],style,label=label+' Fz')
    axes[1,0].set(title='Y：暂停期间仍有导纳修正',xlabel='相对触发时间 / s',ylabel='M 点 Y 位置 / μm')
    axes[1,1].axhline(-8,color='#777777',ls=':');axes[1,1].set(title='Y：暂停及恢复后的轴向载荷',xlabel='相对触发时间 / s',ylabel='Fz / mN')
    for ax in (axes[1,0],axes[1,1]):
        ax.axvspan(0,1.002,color='#008d91',alpha=.07);ax.axvline(1.1,color='#835b8a',ls=':',label='额外搜索完全恢复')
    for ax in (axes[0,0],axes[1,0],axes[1,1]):ax.grid(alpha=.15);ax.legend(fontsize=8)
    fig.suptitle('Y 受阻证据｜几何残差、接触针与恢复时序',fontsize=16)
    fig.supxlabel('每根针可能接触多个凸分段；接触点数不能用作载荷大小。离线重建没有推进动力学。',fontsize=10)
    fig.savefig(target/'02_Y逐针接触与修正.png');plt.close(fig)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--tag',default='diagnosis_v1');args=parser.parse_args()
    target=new_target(OUT,args.tag)
    cases,runs,params,inputs=evidence()
    target.mkdir(parents=True)
    dump(target/'diagnosis.json',{'method':'saved-state geometry reconstruction; saved aggregate forces; no integration',
                                'geometry_parameters':params,'offsets_s':OFFSETS,'evidence':cases,'inputs_sha256':inputs})
    figures(target,cases,runs,params)
    report(target,cases,params)
    source=Path(__file__);(target/source.name).write_bytes(source.read_bytes())
    for p,h in inputs.items():assert sha(ROOT/p)==h
    dump(target/'delivery_manifest.json',{'inputs_sha256':inputs,'outputs_sha256':{p.relative_to(ROOT).as_posix():sha(p) for p in target.iterdir() if p.is_file()},'script_sha256':sha(source)})
    print(json.dumps({'output':str(target),'cases':[{'case':e['case'],'first_contact':{k:v['time_s'] if v else None for k,v in e['first_contact_after_trigger'].items()},'checked_axial_commands':e['checked_axial_commands']} for e in cases]},ensure_ascii=False))


def report(target,cases,params):
    x,y=cases
    lines=['# B2-5.5 X/Y 受阻差异离线诊断','',
           '2026-09-22。只读 X/Y 暂停候选及各自原 V2 的四份动力学记录；没有新增回合，没有修改控制器、模型、参数、保护或完整达标标准。','',
           '## 核心结论','',
           'X 与 Y 的暂停触发条件相同，但触发时的几何状态不同。X 的九根针尖圆盘投影均在主孔边界内，Y 的九根均部分超出。两者触发时接触力都是零：此时还未到主孔台阶，无接触不能证明已对准。',
           '暂停保留了 X 当时的可推进状态；Y 则重新接触主孔入口附近，原轴向力反馈随阻力增大而减速。这个证据链解释了记录中的差异，但不证明某一个位置或角度是唯一原因，也不证明暂停恢复本身独立导致了最终恶化。','',
           '## 触发时的实际状态','',
           '| 工况 | 整体推进/mm | M点 X/Y偏差/μm | 总姿态角/° | 九针投影超界范围/μm | 接触点数 |','|---|---:|---|---:|---|---:|']
    for e in cases:
        s=e['snapshots']['candidate']['0.0'];o=[p['main_aperture_overhang_m']*1e6 for p in s['pins']]
        lines.append(f"| {e['label']} | {s['advance_mm']:.6f} | {s['xy_um'][0]:.3f} / {s['xy_um'][1]:.3f} | {s['angle_deg']:.4f} | {min(o):.3f}～{max(o):.3f} | {len(s['contacts'])} |")
    lines+=['','针半径 0.500 mm，主孔内切半径 0.575 mm；同轴径向余量为 75 μm。正的投影超界量表示：固定当前 XY 与姿态，仅沿世界 Z 平移时，针尖圆盘投影不能完全通过主孔。负值表示该投影在边界内。它不是当前穿透量，不是整根针的全程间隙，也不等于完整装配精度。',
            '孔采用实际 256 段半平面边界计算，没有把孔替换成理想圆。针尖投影计算包含姿态旋转、阵列位置以及 4 mm 针长的作用；M 点 XY 偏差不能直接当成每根针尖的 XY 偏差。','',
            '## 逐针接触与轴向反馈','',
            '| Y 相对触发/s | 推进/mm | 重建活动针 | 接触点 Z 范围/mm | 最大针尖投影超界/μm | 原始记录 Fz/mN | 下一条 Z 指令/mm·s⁻¹ |','|---|---:|---|---|---:|---:|---:|']
    for d in (.4,.6,1.,1.1,1.5,2.):
        s=y['snapshots']['candidate'][str(d)];c=s['contact_summary'];z=c['z_range_mm'];o=max(p['main_aperture_overhang_m'] for p in s['pins'])*1e6
        lines.append(f"| {d:g} | {s['advance_mm']:.6f} | {', '.join(p[-2:] for p in c['active_pins']) or '无'} | {f'{z[0]:.6f}～{z[1]:.6f}' if z else '无'} | {o:.3f} | {s['saved_force_M_N'][2]*1000:.3f} | {y['next_z_commands_mm_s'][str(d)]:.6f} |")
    first=y['first_contact_after_trigger']['candidate']
    lines+=['',f"Y 在触发后 {first['time_s']-y['trigger_time_s']:.3f} s 重新接触。上表接触属于 main 主孔凸块，位置集中在 z≈0.250 mm 的入口台阶附近；不是孔底接触。+0.4 s 为针 09 接触，随后分布扩展到其他下排针。针 01 投影超界最大，不等于它最先接触：姿态也改变各针端面的高度，详见数据中的针尖边缘 Z 范围。",
            '每根针可能与多个相邻凸分段形成多个接触点，点数不能当作独立接触针数或受力大小。重建只使用实际保存的位姿，逐快照核对接触点数和最大穿透与原记录一致；没有恢复逐针接触力。',
            'SEARCH 的轴向指令为 clip(0.05 × (0.008 + Fz), −0.00025, +0.0005)，单位 m/s。Fz 趋近 −8 mN 时，Z 指令趋近零。核对使用当前行的力计算下一行保存的命令；原始命令不等于实际推进速度。',
            f"X/Y 分别核对 {x['checked_axial_commands']} / {y['checked_axial_commands']} 条该窗口内 SEARCH 轴向命令。X 暂停后未重新产生记录到的接触，先以 0.4 mm/s 的 SEARCH 规则推进；+0.726 s 取得 V2 退出资格后才转入 INSERT。Y 在 +1.0 s 时 Fz 已为 −7.378 mN，下一条 Z 指令仅约 0.031 mm/s，推进仍停留在约 0.235 mm。",
            '观察到的低推进包含受阻、力反馈减速与执行器动力学共同作用，不能仅从指令小就断定没有物理卡阻，也不能据此提高力阈值。','',
            '## 姿态不能单独看总角度','']
    sy=y['snapshots']['candidate']['0.0']
    effect=[p['rotation_contribution_xy_um'][1] for p in sy['pins']]
    lines += [f"Y 触发时 M 点 Y 偏差约 −121.84 μm；姿态引起各针尖的 Y 方向偏移约 +{min(effect):.2f}～+{max(effect):.2f} μm，抵消了一部分负 Y 偏差。这里的姿态贡献包含全部刚体旋转和阵列力臂，不能称为某一个倾斜轴的独立贡献。",
              f"只在几何计算中保持 M 点位置、把姿态置为单位旋转，针尖投影超界反而约为 {sy['identity_rotation_overhang_um']:.2f} μm。此项是几何反事实，不是控制试验，不代表机器人会按该路径运动；它说明不能简单把“更小的总姿态角”当作当前状态下更易插入的充分条件。",
              '原有四轴导纳确实在修改 XY 和两个转动方向；Y 在暂停 1 s 内投影最大超界从约 22.38 μm 降至 2.75 μm，说明修正仍在发生，但此时尚未全部消除，完整位姿也未满足。','',
              '## 下一项单变量检验建议（本轮未运行）','',
              '仅在 Y −100 μm 工况，将额外 XY 搜索暂停上限由 1.0 s 改为 2.0 s；恢复坡道仍为 0.1 s。触发条件、模型、初始状态、导纳、原 Z/转动规则、退出资格、力/力矩/穿透阈值、搜索时间与半径预算全部保持。',
              '要回答的问题是：原导纳在额外搜索停用时持续修正，给它多 1 s 是否足以改变 Y 的受阻和推进。选择 2 s 是一个有界敏感性检验，不是由现有数据推导出的最优时长，更不是保证成功。',
              '与当前 1 s 的完整 Y 记录对照，候选应一致到原策略开始恢复额外搜索的时刻；保留所有负结果。评估原退出资格、完整深度与 XY/姿态、峰值载荷和穿透、停止原因，不能只比较局部推进。暂停仍消耗原搜索预算，提前满足退出资格或触发保护时照常结束。',
              '螺旋相位在暂停期间仍推进。延长暂停后，重新加入额外搜索时的相位也会不同；这是暂停时长干预带来的后续变化，不能把结果解释成单纯多静止 1 s。',
              '当前日志没有“不恢复搜索后会怎样”的轨迹，所以不能直接认定恢复太早。若 2 s 仍不改善，不自动连续加长或扫参；再依据证据考虑受力对中或状态切换设计。几何超界指标仅用于仿真诊断，不直接当作真实机器人可观测的控制输入。','',
              '## 文件、复现和展示','',
              '- [月报受阻差异图](01_月报受阻差异.png)',
              '- [Y逐针接触与修正图](02_Y逐针接触与修正.png)',
              '- [全部快照、受力与输入校验](diagnosis.json)',
              '- [月报小结](月报小结.md)','',
              '在项目 worktree 根目录运行以下命令，仅重建已有轨迹的几何与报告；tag 必须是新目录名：','',
              '```powershell',
              r"& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.diagnose_b2_xy_contacts --tag reproduce_01",
              '```','',
              '本轮无新动力学动画；继续使用 X/Y 原真实轨迹回放。此次结论仅适用于这两个固定开发工况及当前未标定模型。']
    (target/'B2-5.5受阻差异诊断报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')
    (target/'月报小结.md').write_text('# 月报增量：从结果差异定位到接触机制\n\n2026-09-22。第一阶段仍在仿真平台与传统控制基线完善，本轮没有新增动力学试验。\n\n完成 X/Y 四份已有轨迹的离线对照。发现相同暂停触发条件并不对应相同几何状态：X 九针投影已落在主孔边界内，Y 九针仍超界；两者当时都无接触。Y 随后在主孔入口附近重新接触，轴向阻力使原控制律减速；暂停期间导纳仍在修正，但 1 s 末仍存在少量投影超界。\n\n汇报可强调“已将失败现象细化为几何对准状态、逐针接触位置和轴向反馈的证据链，并形成下一项单变量试验”。不能说“已证明唯一原因”“已经修复卡阻”“装配成功率提高”。投影超界不是穿透，重建接触点不是逐针受力记录。\n\n展示 [月报受阻差异图](01_月报受阻差异.png)，需要技术细节时补充 [Y逐针接触与修正图](02_Y逐针接触与修正.png)。下一项拟仅将 Y 的暂停上限从 1 s 改为 2 s，保留原预算和保护，检验多给导纳修正时间是否有效；尚未运行。\n',encoding='utf-8',newline='\n')


if __name__=='__main__':main()
