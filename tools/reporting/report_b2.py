"""Rebuild B2 plots from verified compressed traces; never generate motion."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from tools.validation.run_b2_search import OUT, read_run
from tools.validation.run_b1_baseline import dump
from tools.visualization.font_support import find_chinese_font

CASE_LABELS={'x_offset_pos_100um':'单独 X +100 μm','y_offset_neg_100um':'单独 Y −100 μm',
             'aligned':'同轴','combined_a_scale_0.75':'联合 A ×0.75','combined_b_scale_0.75':'联合 B ×0.75',
             'combined_a':'联合 A 全幅','roll_pos_1.5deg':'Roll +1.5°'}
REASONS={'GEOMETRIC_SUCCESS':'满足几何完成标准','TARGET_POSE_NOT_SETTLED':'到达目标深度，但完整位姿标准未满足',
         'NO_PROGRESS':'推进停滞','TIME_LIMIT':'动作时间用尽','FORCE_LIMIT':'接触力保护停止',
         'SEARCH_BUDGET_EXHAUSTED':'搜索预算用尽','UNLOAD_TIMEOUT':'减载超时'}
PHASES={'INSERT':'正常推进','UNLOAD':'减载','SEARCH':'局部搜索','WAIT_RECOVERY':'等待恢复','FAILED':'策略结束',
        'STOPPING':'停止中','RUNNING':'运行中','RETRACT':'回撤中','TERMINAL':'终止'}


def verified(tag):
    target=OUT/tag;index=json.loads((target/'results_index.json').read_text(encoding='utf-8'))
    if index['status']!='COMPLETE':raise RuntimeError('Incomplete experiment')
    expected=[(c,p) for c in index['case_names'] for p in (['b1','b2'] if index['paired'] else ['b2'])]
    if [(r['case'],r['policy']) for r in index['runs']]!=expected:raise RuntimeError('Unexpected case list')
    runs=[]
    for entry in index['runs']:
        file=target/entry['file']
        if hashlib.sha256(file.read_bytes()).hexdigest()!=entry['sha256']:raise RuntimeError('Changed run')
        r=read_run(file)
        if r['source_sha256']!=index['source_sha256'] or r['historical_source_sha256']!=index['historical_source_sha256']:
            raise RuntimeError('Mixed source versions')
        if r['termination']!=entry['termination'] or r['case']['name']!=entry['case']:raise RuntimeError('Index mismatch')
        if not np.isfinite(np.array([x['position_m']+x['quaternion_wxyz']+x['contact_wrench_M'] for x in r['trace']])).all():
            raise RuntimeError('Nonfinite trace')
        runs.append(r)
    if index['paired']:
        for a,b in zip(runs[::2],runs[1::2]):
            for key in ('case','environment','finish_criteria','max_time_s','settle_time_s'):
                if a[key]!=b[key]:raise RuntimeError('Unfair paired field: '+key)
    return target,index,runs


def figures(target,runs):
    font_manager.fontManager.addfont(str(find_chinese_font()))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(find_chinese_font())).get_name(),
                         'axes.unicode_minus':False,'font.size':10,'figure.dpi':150})
    for r in runs:
        if r['controller']['name']!='B2_bounded_search_recovery':continue
        ts=np.array([x['time_s'] for x in r['trace']]);p=np.array([x['position_m'] for x in r['trace']])
        w=np.array([x['contact_wrench_M'] for x in r['trace']]);q=np.array([x['quaternion_wxyz'] for x in r['trace']])
        angles=np.degrees(2*np.arccos(np.clip(abs(q[:,0])/np.linalg.norm(q,axis=1),0,1)))
        fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
        fig.suptitle(f"B2 候选试验｜{CASE_LABELS.get(r['case']['name'],r['case']['name'])}\n{REASONS.get(r['termination'],r['termination'])}",fontsize=15)
        axes[0,0].plot(ts,(p[:,2]-p[0,2])*1000,color='#18799C');axes[0,0].axhline(4,color='#888888',ls='--')
        axes[0,0].set(xlabel='时间 / s',ylabel='真实推进 / mm',title='推进与控制阶段')
        for e in r['policy_events']:
            axes[0,0].axvline(e['time_s'],color='#c78144',alpha=.5,ls=':')
        axes[0,1].plot((p[:,0]-p[0,0])*1e6,(p[:,1]-p[0,1])*1e6,color='#18799C',lw=1)
        axes[0,1].scatter([0,(p[-1,0]-p[0,0])*1e6],[0,(p[-1,1]-p[0,1])*1e6],c=['#18799C','#bd4f3c'])
        axes[0,1].set(xlabel='相对起点 X / μm',ylabel='相对起点 Y / μm',title='实际横向轨迹（非理想指令轨迹）',aspect='equal')
        axes[1,0].plot(ts,np.linalg.norm(w[:,:3],axis=1)*1000,label='接触合力')
        axes[1,0].axhline(25,color='#bd4f3c',ls='--',label='保护阈值');axes[1,0].legend()
        axes[1,0].set(xlabel='时间 / s',ylabel='接触合力 / mN',title=f"物理步峰值 {r['peaks']['force_N']*1000:.3f} mN")
        axes[1,1].plot(ts,angles,color='#18799C')
        axes[1,1].set(xlabel='时间 / s',ylabel='相对目标总姿态角 / °',title='姿态仅用于离线评价')
        for ax in axes.flat:ax.grid(alpha=.2)
        fig.supxlabel('竖线为策略状态转换；完整状态与失败原因见试运行记录。开发试验，未做实机标定。',fontsize=10)
        fig.savefig(target/(r['case']['name']+'_轨迹诊断.png'));plt.close(fig)


def replay(target,r):
    import mujoco
    from PIL import Image,ImageDraw,ImageFont
    from tools.dynamics.cartesian import CartesianEnvironment
    from tools.visualization.render_scenes import style_model_for_display,_scene_option,CameraPreset
    env=CartesianEnvironment(segments=256);m=env.model;d=env.data
    style_model_for_display(m,'collision_overlay')
    m.vis.global_.offwidth=1000;m.vis.global_.offheight=600
    m.vis.headlight.ambient[:]=(.5,.5,.5);m.vis.headlight.diffuse[:]=(.65,.65,.65)
    m.geom_group[:]=3
    for i in range(m.ngeom):
        name=mujoco.mj_id2name(m,mujoco.mjtObj.mjOBJ_GEOM,i) or ''
        if name=='pin_05' or (name.startswith('hole_convex256_05_') and
                              np.cos(int(name.split('_')[-1])*2*np.pi/256-np.radians(125))>.2):
            m.geom_group[i]=0
            if name.startswith('hole_'):m.geom_rgba[i,3]=.3
            else:m.geom_rgba[i,:]=(1.,.48,.08,1.)
    option=_scene_option('collision_overlay');camera=CameraPreset((.00554,.00142,.001),.015,125,-12).build()
    renderer=mujoco.Renderer(m,height=460,width=760)
    font=ImageFont.truetype(str(find_chinese_font()),20);titlefont=ImageFont.truetype(str(find_chinese_font()),24)
    frames=[];mapping=[];times=np.array([x['time_s'] for x in r['trace']])
    try:
        for t in np.linspace(0,times[-1],101):
            i=max(0,int(np.searchsorted(times,t,side='right')-1));row=r['trace'][i]
            d.qpos[:]=row['position_m']+row['quaternion_wxyz'];mujoco.mj_kinematics(m,d)
            renderer.update_scene(d,camera=camera,scene_option=option)
            canvas=Image.new('RGB',(1000,650),'#f6f8fa');canvas.paste(Image.fromarray(renderer.render().copy()),(0,125));draw=ImageDraw.Draw(canvas)
            draw.text((20,18),'B2 真实动力学轨迹回放｜'+CASE_LABELS.get(r['case']['name'],r['case']['name']),font=titlefont,fill='#172b4d')
            draw.text((20,58),f"记录时间 {row['time_s']:.3f} s  阶段 {PHASES.get(row['policy_phase'],row['policy_phase'])} / {PHASES.get(row['phase'],row['phase'])}",font=font,fill='#172b4d')
            draw.text((20,90),f"推进 {(row['position_m'][2]-r['case']['start_origin_z_m'])*1000:.3f} mm  合力 {np.linalg.norm(row['contact_wrench_M'][:3])*1000:.2f} mN",font=font,fill='#172b4d')
            draw.text((780,190),'回合最终结果',font=font,fill='#172b4d')
            result_label=('推进深度到位\n位姿标准未满足' if r['termination']=='TARGET_POSE_NOT_SETTLED'
                          else REASONS.get(r['termination'],r['termination']).replace('_','\n'))
            draw.text((780,225),result_label,font=font,fill='#a34d3a')
            draw.text((20,600),'针 05 局部剖视；隐藏前侧孔壁仅用于展示；位姿来自积分记录，无插值。',font=font,fill='#445568')
            frames.append(canvas);mapping.append({'trace_index':i,'recorded_time_s':row['time_s']})
        frames[0].save(target/'真实轨迹回放.gif',save_all=True,append_images=frames[1:],duration=90,loop=0,optimize=False)
        frames[-1].save(target/'真实轨迹终态.png')
    finally:renderer.close()
    dump(target/'replay_manifest.json',{'case':r['case']['name'],'frames':mapping,'semantics':'recorded pose replay, no dynamics rerun, no interpolation',
         'playback_duration_s':len(frames)*.09,'simulated_duration_s':float(times[-1]),'motion_scale':1,
         'input_index_sha256':hashlib.sha256((target/'results_index.json').read_bytes()).hexdigest()})


def summary(target,index,runs):
    lines=['# B2-3 单工况试运行小结','',f"记录：{target.name}；候选参数：{index['candidate']}。",'',
           '完整轨迹保存在 runs/*.json.gz（无损压缩，保留每 2 ms 采样）；source_snapshot 保存该次实验的代码副本。','',
           '| 控制策略 | 结束推进 / mm | 动作停止 / s | 峰值力 / mN | 最大穿透 / μm | 结束原因 |',
           '|---|---:|---:|---:|---:|---|']
    for r in runs:
        name='B2 受限搜索' if r['controller']['name']=='B2_bounded_search_recovery' else 'B1 固定导纳'
        lines.append(f"| {name} | {(r['final']['position_m'][2]-r['case']['start_origin_z_m'])*1000:.6f} | {r['stop_time_s']:.3f} | {r['peaks']['force_N']*1000:.3f} | {r['peaks']['penetration_m']*1e6:.3f} | {REASONS.get(r['termination'],r['termination'])} |")
    r=next(r for r in runs if r['controller']['name']=='B2_bounded_search_recovery');row=r['final']
    p=np.asarray(row['position_m']);q=np.asarray(row['quaternion_wxyz']);v=np.asarray(row['velocity_world']);w=np.asarray(row['contact_wrench_G'])
    a=float(np.degrees(2*np.arccos(np.clip(abs(q[0])/np.linalg.norm(q),0,1))))
    criteria=[('Z 位置误差',abs(p[2])*1e6,20,'μm'),('XY 位置误差',np.linalg.norm(p[:2])*1e6,50,'μm'),
              ('总姿态误差',a,.5,'°'),('线速度',np.linalg.norm(v[:3])*1e6,10,'μm/s'),
              ('角速度',np.linalg.norm(v[3:]),.001,'rad/s'),('全程接触合力峰值',r['peaks']['force_N']*1000,25,'mN'),
              ('全程 G 点力矩峰值',r['peaks']['torque_G_Nm']*1000,.5,'mN·m'),('全程穿透峰值',r['peaks']['penetration_m']*1e6,30,'μm')]
    lines+=['','## 完整完成标准逐项检查','',
            '终点静止并不保证位置误差达标；`TARGET_POSE_NOT_SETTLED` 是沿用的综合分类，不应一律解释为仍在振动。成功还要求条件连续保持 0.1 秒。','',
            '| 指标 | 本次 B2 | 原定上限 | 终点/峰值检查 |','|---|---:|---:|---|']
    for name,value,limit,unit in criteria:lines.append(f'| {name} | {value:.6g} {unit} | {limit:g} {unit} | {"满足" if value<limit else "未满足"} |')
    lines+=['','## 策略动作记录','',f"搜索 {r['search_count']} 次；条件回撤 {r['recovery_count']} 次。",'',
            '| 时间 / s | 策略阶段 | 触发原因 |','|---:|---|---|']
    for e in r['policy_events']:lines.append(f"| {e['time_s']:.3f} | {PHASES.get(e['phase'],e['phase'])} | {e['reason']} |")
    lines+=['','## 本次可以说明什么','',
            '这是一个固定开发工况的机制试验。按统一几何完成标准保留判定，不因为推进量增加而放宽位置容差。',
            ('B1/B2 已使用相同模型、初始条件、20 秒动作预算、1 秒最终观察和完成标准；B1 原停滞判定保持不变。' if index['paired'] else '此记录只运行 B2，不单独构成同条件配对证据。'),
            '同条件比较仍比较的是“原 B1 策略”与“搜索和恢复组合策略”，不能单独归因于螺旋搜索。要区分减载、横向搜索和回撤的各自贡献，需要后续消融试验。',
            '本细分结束后暂停；尚未开展七工况矩阵或训练。下一步是 B2-4 的统一参数七工况对照，先确认效果分布和失败原因。','',
            '## 展示与复现','',f"- [真实轨迹诊断图]({r['case']['name']}_轨迹诊断.png)",
            '- [真实轨迹动画](真实轨迹回放.gif)','- [实验索引](results_index.json)','',
            '重新绘制（只读记录，不重跑动力学）：','',
            '```powershell',f"& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.reporting.report_b2 --tag {target.name} --replay",'```','',
            '重新执行动力学时另选新 tag，避免覆盖原尝试；参数与代码必须与该次 source_snapshot 一致。','']
    (target/'试运行小结.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tag',required=True);parser.add_argument('--replay',action='store_true')
    args=parser.parse_args();target,index,runs=verified(args.tag);figures(target,runs)
    if args.replay:replay(target,next(r for r in runs if r['controller']['name']=='B2_bounded_search_recovery'))
    summary(target,index,runs)
    print(json.dumps(index['runs'],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
