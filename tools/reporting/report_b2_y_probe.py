"""Audit one preserved XY probe, compare with frozen V2, export Chinese results."""
import argparse
import json
import math
import numpy as np
from matplotlib import pyplot as plt
from tools.control.fixed_admittance import FixedAdmittance
from tools.reporting.report_b2_exit_gate import collect, configure_font
from tools.reporting.report_b2_matrix import metrics
from tools.reporting.report_b2 import replay, REASONS
from tools.validation.run_b1_baseline import dump
from tools.validation.run_b2_search import read_run
from tools.validation.run_b2_y_probe import OUT, ROOT, X_OUT, source_hashes, sha, new_target, select_inputs
from tools.validation.diagnose_v1_applicability import fingerprint


def window(run, fork, duration):
    rows=[s for s in run['trace'] if fork-1e-8<=s['time_s']<=fork+duration+1e-8]
    assert rows and abs(rows[0]['time_s']-fork)<1e-8
    actual=rows[-1]['time_s']-rows[0]['time_s']
    complete=abs(actual-duration)<1e-8
    p=np.array([s['position_m'] for s in rows])
    advance=float((p[-1,2]-p[0,2])*1e6)
    path=float(np.linalg.norm(np.diff(p[:,:2],axis=0),axis=1).sum()*1e6)
    return {'requested_duration_s':duration,'available_duration_s':actual,'complete_window':complete,
            'contains_nonrunning':any(s['phase']!='RUNNING' for s in rows),
            'policy_phases':sorted({s.get('policy_phase','UNKNOWN') for s in rows}),
            'advance_um':advance if complete else None,'xy_path_um':path if complete else None,
            'observed_advance_um':advance,'observed_xy_path_um':path}


def execution_profile(events, commands, dt):
    return {'triggered':any(e['event']=='XY_PROBE_START' for e in events),
            'zero_gain_command_duration_s':sum(p['extra_xy_gain']==0 for p in commands)*dt,
            'resume_ramp_command_duration_s':sum(0<p['extra_xy_gain']<1 for p in commands)*dt,
            'resume_ramp_executed':any(0<p['extra_xy_gain']<1 for p in commands),
            'full_search_restored':any(e['event']=='XY_SEARCH_FULLY_RESTORED' for e in events),
            'ended_by_parent':next((e for e in events if e['event']=='XY_PROBE_ENDED_BY_PARENT'),None)}


def audit(folder):
    pairs,_=collect(('verified_frozen_x100','verified_frozen_y100'))
    _,historical,reference=pairs[1]
    select_inputs()
    index=json.loads((folder/'results_index.json').read_text(encoding='utf-8'))
    assert index['x_trial_index_sha256']==sha(X_OUT/'first_frozen_x100/results_index.json')
    assert index['status']=='COMPLETE' and len(index['runs'])==1
    assert index['source_sha256']==source_hashes()
    assert index['historical_source_sha256']==fingerprint()
    assert sha(folder/'实验协议.md')==index['protocol_sha256']
    for name,digest in index['source_sha256'].items():assert sha(folder/'source_snapshot'/name)==digest
    ref=index['reference'];assert sha(ROOT/ref['file'])==ref['sha256']
    assert sha(ROOT/ref['index'])==ref['index_sha256']
    assert read_run(ROOT/ref['file'])==reference
    entry=index['runs'][0];assert sha(folder/entry['file'])==entry['sha256']
    run=read_run(folder/entry['file'])
    assert run['source_sha256']==index['source_sha256']
    assert run['historical_source_sha256']==index['historical_source_sha256']
    assert run['controller']==index['controller']
    assert run['case']['name']=='y_offset_neg_100um'
    assert run['termination']==entry['termination']
    for key in ('case','environment','finish_criteria','max_time_s','settle_time_s'):
        assert run[key]==reference[key],key
    for key in ('config','exit_gate','admittance'):
        assert run['controller'][key]==reference['controller'][key]
    starts=[e for e in run['probe_events'] if e['event']=='XY_PROBE_START']
    if not starts:
        assert run['trace']==reference['trace'] and not run['probe_trace']
        result={'identical_prefix_samples':len(run['trace']), 'identical_through_s':run['trace'][-1]['time_s'],
                'checked_probe_commands':0,'probe_execution':execution_profile(run['probe_events'],[],run['environment']['config']['control_period']),
                'probe_events':run['probe_events'],'verified_exit_events':[],
                'reference_metrics':metrics(reference),'candidate_metrics':metrics(run),'historical_v1_metrics':metrics(historical),'windows':{}}
        return reference,run,result,index
    assert len(starts)==1
    t0=starts[0]['time_s'];rows=run['trace'];dt=run['environment']['config']['control_period']
    prefix=0
    for a,b in zip(reference['trace'],rows):
        if a!=b:break
        prefix+=1
    assert prefix and abs(rows[prefix-1]['time_s']-t0)<1e-9
    assert run['probe_trace'] and abs(run['probe_trace'][0]['input_time_s']-t0)<1e-9
    c=run['controller']['config'];probe=run['controller']['probe']
    search_event=next(e for e in run['policy_events'] if e.get('recovered_search'))
    origin=np.array(rows[round(search_event['time_s']/dt)]['position_m'])
    checked=0
    for item in run['probe_trace']:
        k=round(item['input_time_s']/dt);a,b=rows[k:k+2]
        assert abs(a['time_s']-item['input_time_s'])<1e-9
        assert b['policy_phase']=='SEARCH'
        adm=FixedAdmittance();adm.velocity=np.array(a['admittance_velocity']);adm.offset=np.array(a['commanded_correction'])
        base=adm.command(a['contact_wrench_M'],dt)
        np.testing.assert_allclose(adm.velocity,b['admittance_velocity'],rtol=0,atol=1e-14)
        np.testing.assert_allclose(adm.offset,b['commanded_correction'],rtol=0,atol=1e-14)
        elapsed=a['time_s']-t0
        fraction=np.clip((elapsed-probe['pause_s'])/probe['resume_s'],0,1)
        gain=0. if elapsed<=probe['pause_s']+1e-10 else (1. if elapsed>=probe['pause_s']+probe['resume_s']-1e-10 else float(fraction*fraction*(3-2*fraction)))
        assert abs(gain-item['extra_xy_gain'])<1e-8
        theta=a['spiral_theta_rad'];pitch=c['spiral_pitch_m']/(2*math.pi);r=pitch*theta
        rate=c['spiral_speed_m_s']/math.hypot(r,pitch)
        tangent=np.array([pitch*math.cos(theta)-r*math.sin(theta),pitch*math.sin(theta)+r*math.cos(theta)])*rate
        target=r*np.array([math.cos(theta),math.sin(theta)])
        delta=np.array(a['position_m'])-origin
        extra=tangent+c['search_tracking_gain_s']*(target-delta[:2])
        np.testing.assert_allclose(extra,item['extra_xy_m_s'],rtol=0,atol=1e-14)
        np.testing.assert_allclose(base[:2],item['base_xy_m_s'],rtol=0,atol=1e-14)
        base[:2]=np.clip(base[:2]+gain*extra,-c['search_xy_component_speed_m_s'],c['search_xy_component_speed_m_s'])
        base[2]=np.clip(c['axial_gain_m_s_N']*(c['search_force_N']+a['contact_wrench_M'][2]),-c['unload_speed_m_s'],c['search_forward_speed_m_s'])
        np.testing.assert_allclose(base,b['raw_command_world'],rtol=0,atol=1e-12)
        np.testing.assert_array_equal(item['command_world'],b['raw_command_world'])
        assert abs(b['spiral_theta_rad']-min(c['spiral_radius_m']/pitch,theta+rate*dt))<1e-12
        checked+=1
    gate=run['controller']['exit_gate'];verified_exits=[]
    for e in run['policy_events']:
        if 'exit_evidence' not in e:continue
        proof=e['exit_evidence'];threshold=max(search_event['blocked_z_m'],origin[2]-run['case']['start_origin_z_m'])+c['search_exit_advance_m']
        assert abs(proof['threshold_z_m']-threshold)<1e-12
        held=[s for s in rows if e['time_s']-proof['duration_s']-1e-9<=s['time_s']<=e['time_s']+1e-9]
        z=np.array([s['position_m'][2]-run['case']['start_origin_z_m'] for s in held])
        forces=np.array([np.linalg.norm(s['contact_wrench_M'][:3]) for s in held])
        assert np.all(z>=threshold-1e-12) and np.all(np.diff(z)>=-1e-12)
        assert z[-1]-z[0]>=gate['min_progress_m']-1e-12 and forces.max()<=gate['max_force_N']+1e-12
        assert held[-1]['time_s']-held[0]['time_s']>=gate['hold_s']-1e-9
        assert abs(proof['exit_z_m']-z[-1])<1e-12
        assert abs(proof['advance_m']-(z[-1]-z[0]))<1e-12
        assert abs(proof['max_observed_force_N']-forces.max())<1e-12
        assert abs(proof['duration_s']-(held[-1]['time_s']-held[0]['time_s']))<1e-9
        verified_exits.append(e)
    result={'identical_prefix_samples':prefix,'identical_through_s':t0,'checked_probe_commands':checked,
            'probe_execution':execution_profile(run['probe_events'],run['probe_trace'],dt),
            'probe_events':run['probe_events'],'verified_exit_events':verified_exits,
            'reference_metrics':metrics(reference),'candidate_metrics':metrics(run),'historical_v1_metrics':metrics(historical),
            'windows':{str(d):{'reference':window(reference,t0,d),'candidate':window(run,t0,d)} for d in (.6,1.)}}
    return reference,run,result,index



def plots(target,old,new,a):
    configure_font()
    fig,axes=plt.subplots(1,4,figsize=(14,4.8),layout='constrained')
    for ax,key,title,limit in ((axes[0],'advance_mm','最终推进 / mm',4),
                             (axes[1],'xy_error_um','终点 XY 误差 / μm',50),
                             (axes[2],'angle_deg','终点姿态误差 / °',.5),
                             (axes[3],'peak_force_mN','全回合峰值合力 / mN',25)):
        values=[a[k][key] for k in ('reference_metrics','candidate_metrics')]
        bars=ax.bar([0,1],values,color=['#7c8c9c','#008d91'],width=.6)
        ax.bar_label(bars,fmt='%.3f',padding=3)
        ax.axhline(limit,color='#bb6953',ls=':')
        ax.set(xticks=[0,1],xticklabels=['原 V2','同参数暂停候选'],title=title,ylim=(0,max(limit,*values)*1.3))
        ax.grid(axis='y',alpha=.15)
    fig.suptitle('B2-5.4 月报增量｜Y −100 μm 同参数检验',fontsize=15)
    fig.supxlabel('完整达标：'+('是' if a['candidate_metrics']['success'] else '否')+'。单个固定开发工况，不能当作随机成功率。',fontsize=10)
    fig.savefig(target/'01_月报Y工况对照.png');plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for r,label,color in ((old,'原 V2','#7c8c9c'),(new,'同参数暂停候选','#008d91')):
        t=np.array([s['time_s'] for s in r['trace']]);p=np.array([s['position_m'] for s in r['trace']])
        axes[0,0].plot(t,(p[:,2]-r['case']['start_origin_z_m'])*1000,label=label,color=color)
        axes[1,0].plot(t,np.linalg.norm(p[:,:2],axis=1)*1e6,label=label,color=color)
        axes[1,1].plot(t,[np.linalg.norm(s['contact_wrench_M'][:3])*1000 for s in r['trace']],label=label,color=color)
    depths=[(s['position_m'][2]-r['case']['start_origin_z_m'])*1000 for r in (old,new) for s in r['trace']]
    axes[0,0].set_ylim(min(0,min(depths))-.02,max(depths)*1.12+.01)
    axes[0,0].text(.98,.95,'名义目标 4.000 mm',ha='right',va='top',transform=axes[0,0].transAxes,color='#bb6953')
    axes[0,0].set(title='完整动力学推进',ylabel='推进 / mm')
    axes[1,0].axhline(50,color='#bb6953',ls=':',label='XY 误差标准 50 μm')
    axes[1,0].set(title='实际横向误差',ylabel='XY 误差 / μm')
    axes[1,1].axhline(25,color='#bb6953',ls=':',label='接触力保护 25 mN')
    axes[1,1].set(title='接触合力（2 ms 采样）',ylabel='合力 / mN')
    items=new['probe_trace']
    if items:
        t0=items[0]['input_time_s']
        for ax in (axes[0,0],axes[1,0],axes[1,1]):
            ax.axvspan(t0,t0+a['probe_execution']['zero_gain_command_duration_s'],color='#008d91',alpha=.08,label='暂停额外搜索窗口')
        axes[0,1].step([p['input_time_s']-t0 for p in items],[p['extra_xy_gain'] for p in items],where='post',color='#008d91',label='额外 XY 搜索增益')
        axes[0,1].axvline(1.,ls=':',color='#bb6953',label='名义暂停结束 1 s')
        axes[0,1].axvline(1.1,ls='--',color='#835b8a',label='计划恢复完成 1.1 s')
        end=a['probe_execution']['ended_by_parent']
        if end:axes[0,1].axvline(end['time_s']-t0,color='#526f38',ls='--',label='原逻辑提前结束：'+end['phase'])
        axes[0,1].set_xlim(-.05,max(1.2,min(2.,items[-1]['input_time_s']-t0+.1)))
    else:axes[0,1].text(.5,.5,'本例未触发暂停',ha='center',va='center',transform=axes[0,1].transAxes)
    axes[0,1].set(title='真实执行的暂停与恢复',xlabel='相对触发时间 / s',ylabel='额外搜索增益',ylim=(-.05,1.1))
    for ax in (axes[0,0],axes[1,0],axes[1,1]):ax.set_xlabel('时间 / s')
    for ax in axes.flat:
        handles,_=ax.get_legend_handles_labels()
        if handles:ax.legend(fontsize=8)
        ax.grid(alpha=.15)
    fig.suptitle('Y −100 μm｜保留原退出、力反馈与保护规则',fontsize=15)
    fig.supxlabel('额外 XY 搜索暂停不等于冻结实际 XY；力导纳与执行器持续作用。峰值统计取全部物理子步。',fontsize=9)
    fig.savefig(target/'02_Y工况完整轨迹与增益.png');plt.close(fig)


def report(target,a,input_tag):
    old,new=a['reference_metrics'],a['candidate_metrics'];ex=a['probe_execution']
    x=json.loads((X_OUT/'comparison_first_frozen_x100/comparison_audit.json').read_text(encoding='utf-8'))
    lines=['# B2-5.4 Y 工况同参数检验','',
           '2026-09-22。本细分新增一次 Y −100 μm 动力学运行；控制器和参数与冻结 X 完全相同。参考 V2 与旧 B2 均直接读取已有记录。本次没有参数扫描。','',
           f"完整达标：{'是' if new['success'] else '否'}；结束原因：{REASONS.get(new['termination'],new['termination'])}；未满足项：{'、'.join(new['unmet']) or '无'}。",'',
           '| 指标 | 原 V2 Y | 同参数暂停候选 Y |','|---|---:|---:|']
    for key,label in (('advance_mm','最终推进/mm'),('xy_error_um','XY误差/μm'),('angle_deg','姿态误差/°'),('peak_force_mN','峰值合力/mN'),('peak_torque_mNm','峰值G力矩/mN·m'),('peak_penetration_um','最大穿透/μm'),('stop_time_s','动作停止/s'),('searches','搜索次数'),('recoveries','回撤次数')):
        lines.append(f"| {label} | {old[key]:.6f} | {new[key]:.6f} |")
    change=new['advance_mm']-old['advance_mm']
    lines+=['',f"相对原 V2，最终推进变化 {change:+.6f} mm。"+('本 Y 工况未恢复插入，不能推广 X 的深度改善。' if change<=0 else '推进有所改善，完整成功仍按上表标准判断。'),
            f"姿态误差由 {old['angle_deg']:.3f}° 变为 {new['angle_deg']:.3f}°；XY 标准 50 μm、姿态标准 0.5°保持不变。"]
    lines+=['','## 实现与审计','',
            '继承同一 SearchPauseProbe：相对 V2 只改变额外 XY 螺旋与跟踪项的增益；保留力导纳、原 Z/转动规则、退出标准、搜索预算与保护。运行前核验冻结 X 文件清单与完整控制器配置。',
            f"前 {a['identical_prefix_samples']} 个轨迹采样与原 V2 一致，直至 {a['identical_through_s']:.3f} s；逐条复核 {a['checked_probe_commands']} 条干预搜索命令。",'',
            f"触发暂停：{'是' if ex['triggered'] else '否'}；零增益命令累计 {ex['zero_gain_command_duration_s']:.3f} s；平滑恢复实际执行：{'是' if ex['resume_ramp_executed'] else '否'}；完全恢复额外搜索：{'是' if ex['full_search_restored'] else '否'}。",
            '参数仍为暂停 1.0 s、恢复 0.1 s。冻结实现包含暂停端点，因此若运行到该端点，零增益命令累计可能为 1.002 s；这是 2 ms 控制离散化，未为 Y 调参。','']
    if not ex['resume_ramp_executed']:lines.append('本回合不能作为平滑恢复阶段的动力学验证。')
    for event in a['probe_events']:lines.append(f"- {event['time_s']:.3f} s：{event['event']}"+(f"（{event['phase']}）" if 'phase' in event else '')+'。')
    for event in a['verified_exit_events']:
        p=event['exit_evidence'];lines.append(f"- {event['time_s']:.3f} s 满足原 V2 退出资格：深度 {p['exit_z_m']*1000:.6f} mm、持续 {p['duration_s']:.3f} s、推进 {p['advance_m']*1e6:.3f} μm、最大采样力 {p['max_observed_force_N']*1000:.3f} mN。")
    if not a['verified_exit_events']:lines.append('- 未取得原 V2 恢复后退出资格。')
    lines+=['','## 等长窗口','', '| 触发后窗口/s | 原 V2推进/μm | 候选推进/μm | 原V2 XY路程/μm | 候选XY路程/μm | 候选策略阶段 |','|---|---:|---:|---:|---:|---|']
    def fmt(v):return '未覆盖' if v is None else f'{v:.3f}'
    for d,w in a['windows'].items():
        lines.append(f"| {d} | {fmt(w['reference']['advance_um'])} | {fmt(w['candidate']['advance_um'])} | {fmt(w['reference']['xy_path_um'])} | {fmt(w['candidate']['xy_path_um'])} | {'、'.join(w['candidate']['policy_phases'])} |")
    for d,w in a['windows'].items():
        for key,label in (('reference','原 V2'),('candidate','候选')):
            if w[key]['contains_nonrunning']:lines.append(f"{d} s 窗口的{label}含非 RUNNING 物理阶段，不能视为持续搜索。")
    lines+=['','XY 路程不是终点误差。等长窗口若不足则标记未覆盖；发生状态切换后的推进包括原 Z 规则切换的作用，不能当作全程保持同一轴向公式的纯横向效果。','',
            '## X/Y 开发证据','',
            '| 固定工况 | 原V2推进/mm | 候选推进/mm | 候选XY误差/μm | 完整达标 |','|---|---:|---:|---:|---|']
    for label,data in [('X +100 μm',x),('Y −100 μm',a)]:
        m=data['candidate_metrics'];lines.append(f"| {label} | {data['reference_metrics']['advance_mm']:.3f} | {m['advance_mm']:.3f} | {m['xy_error_um']:.3f} | {'是' if m['success'] else '否'} |")
    historical=a['historical_v1_metrics']
    lines+=['',f"旧 B2 Y 历史结果：推进 {historical['advance_mm']:.6f} mm，XY 误差 {historical['xy_error_um']:.3f} μm，完整达标 {'是' if historical['success'] else '否'}。相对失败 V2 的改善不自动意味着优于旧 B2。",
            '两例均为用于开发的固定工况，不能计算随机成功率，也未验证其余五工况。深度到位不等于完整装配成功；本候选尚未提升为正式基线或进入 SAC。模型未实物标定，未加入完整 CR5 与实际夹持。','',
            '## 查看与复现','',
            '- [月报对照图](01_月报Y工况对照.png)、[轨迹与增益](02_Y工况完整轨迹与增益.png)、[真实轨迹回放](真实轨迹回放.gif)',
            '- [数值与审计](comparison_audit.json)、[该次冻结协议](../'+input_tag+'/实验协议.md)','',
            r'工作目录：`D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation`。新建输出 tag，不能覆盖原试验。','',
            '```powershell',
            r"& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.run_b2_y_probe --tag reproduce_y100_01",
            r"& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.reporting.report_b2_y_probe --tag reproduce_y100_01 --out-tag reproduce_y_report_01 --replay",
            '```','',
            'VS Code 06 可回放本例保存的 runs/y_offset_neg_100um_xy_probe.json.gz；05 仍运行原 V2，不会运行本候选。']
    (target/'B2-5.4同参数Y工况报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',default='first_frozen_y100')
    parser.add_argument('--out-tag',default='comparison_first_frozen_y100')
    parser.add_argument('--replay',action='store_true');args=parser.parse_args()
    target=new_target(OUT,args.out_tag)
    if not args.tag or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.tag):parser.error('Simple folder name required')
    old,new,a,index=audit(OUT/args.tag)
    target.mkdir()
    dump(target/'comparison_audit.json',a)
    dump(target/'results_index.json',{'method':'one new Y XY probe vs preserved Y V2; frozen X treatment',
                                     'input_index':f'{args.tag}/results_index.json',
                                     'input_index_sha256':sha(OUT/args.tag/'results_index.json'),
                                     'x_trial_index_sha256':index['x_trial_index_sha256'],'reference':index['reference']})
    plots(target,old,new,a);report(target,a,args.tag)
    if args.replay:replay(target,new)
    dump(target/'delivery_manifest.json',{p.relative_to(ROOT).as_posix():sha(p) for p in target.iterdir() if p.is_file()})
    print(json.dumps({'candidate_metrics':a['candidate_metrics'],'probe_execution':a['probe_execution'],'checked_probe_commands':a['checked_probe_commands']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
