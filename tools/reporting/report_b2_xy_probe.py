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
from tools.validation.run_b2_xy_probe import OUT, ROOT, source_hashes, sha
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


def audit(folder):
    pairs,_=collect(('verified_frozen_x100','verified_frozen_y100'))
    _,historical,reference=pairs[0]
    index=json.loads((folder/'results_index.json').read_text(encoding='utf-8'))
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
    assert run['termination']==entry['termination']
    for key in ('case','environment','finish_criteria','max_time_s','settle_time_s'):
        assert run[key]==reference[key],key
    for key in ('config','exit_gate','admittance'):
        assert run['controller'][key]==reference['controller'][key]
    starts=[e for e in run['probe_events'] if e['event']=='XY_PROBE_START']
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
        gain=float(fraction*fraction*(3-2*fraction))
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
    end_event=next((e for e in run['probe_events'] if e['event']=='XY_PROBE_ENDED_BY_PARENT'),None)
    zero_duration=sum(p['extra_xy_gain']==0 for p in run['probe_trace'])*dt
    result={'identical_prefix_samples':prefix,'identical_through_s':t0,'checked_probe_commands':checked,
            'probe_execution':{'scheduled_pause_s':probe['pause_s'],'zero_gain_command_duration_s':zero_duration,
                               'resume_ramp_executed':any(0<p['extra_xy_gain']<1 for p in run['probe_trace']),
                               'ended_by_parent':end_event},
            'probe_events':run['probe_events'],'verified_exit_events':verified_exits,
            'reference_metrics':metrics(reference),'candidate_metrics':metrics(run),'historical_v1_metrics':metrics(historical),
            'windows':{str(d):{'reference':window(reference,t0,d),'candidate':window(run,t0,d)} for d in (.6,1.)}}
    return reference,run,result,index


def plots(target,old,new,a):
    configure_font();t0=a['identical_through_s']
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for r,label,color in ((old,'原 V2','#7c8c9c'),(new,'暂停额外 XY 搜索','#008d91')):
        times=np.array([s['time_s'] for s in r['trace']]);p=np.array([s['position_m'] for s in r['trace']])
        z=(p[:,2]-r['case']['start_origin_z_m'])*1000
        axes[0,0].plot(times,z,color=color,label=label)
        axes[0,1].plot(times-t0,z,color=color,label=label)
        axes[1,0].plot(times[1:]-r['environment']['config']['control_period']-t0,
                       [s['raw_command_world'][2]*1000 for s in r['trace'][1:]],color=color,label=label)
        axes[1,1].plot(times-t0,[np.linalg.norm(s['contact_wrench_M'][:3])*1000 for s in r['trace']],color=color,label=label)
    axes[0,0].axhline(4,color='#bb6953',ls=':',label='名义目标 4 mm')
    axes[0,0].set(title='全回合实际推进',xlabel='时间 / s',ylabel='推进 / mm')
    axes[0,1].axhline(.350013,color='#bb6953',ls=':',label='V2 退出深度门槛约 0.350 mm')
    axes[0,1].set(title='试探窗口推进与退出资格',ylabel='推进 / mm')
    axes[1,0].set(title='Z 指令受力反馈及原状态机切换共同影响',ylabel='原始 Z 指令 / mm/s')
    axes[1,1].axhline(25,color='#bb6953',ls=':',label='原接触力保护阈值')
    axes[1,1].set(title='接触合力：曲线采样 2 ms',ylabel='合力 / mN')
    for ax in (axes[0,1],axes[1,0],axes[1,1]):
        ax.set_xlim(-.1,2.);ax.set_xlabel('相对试探触发时间 / s')
        ax.axvspan(0,a['probe_execution']['zero_gain_command_duration_s'],color='#008d91',alpha=.07,label='实际零增益窗口')
        for event in a['verified_exit_events']:
            ax.axvline(event['time_s']-t0,color='#835b8a',ls='--',lw=.9,label='原 V2 资格成立，转 INSERT')
    local_max=max((s['position_m'][2]-r['case']['start_origin_z_m'])*1000
                  for r in (old,new) for s in r['trace'] if t0-.1<=s['time_s']<=t0+1.1)
    axes[0,1].set(xlim=(-.1,1.1),ylim=(-.02,max(.4,local_max)*1.1))
    for ax in axes.flat:ax.legend(fontsize=8);ax.grid(alpha=.15)
    fig.suptitle('B2-5.3｜X +100 μm 单变量试验｜额外横向搜索预定最多暂停 1 s',fontsize=15)
    fig.supxlabel('状态按采样时刻，速度命令按输入观测时刻绘制；物理执行后记录比输入晚 2 ms。',fontsize=9)
    fig.savefig(target/'02_控制与推进对照.png');plt.close(fig)
    fig,axes=plt.subplots(1,3,figsize=(12,4.8),layout='constrained')
    for ax,key,title,limit in ((axes[0],'advance_mm','最终推进 / mm',4),
                               (axes[1],'xy_error_um','终点 XY 误差 / μm',50),
                               (axes[2],'peak_force_mN','全回合峰值合力 / mN',25)):
        values=[a[k][key] for k in ('reference_metrics','candidate_metrics')]
        bars=ax.bar([0,1],values,color=['#7c8c9c','#008d91'],width=.6)
        ax.bar_label(bars,fmt='%.3f',padding=3);ax.axhline(limit,color='#bb6953',ls=':',label='目标或阈值')
        ax.set(xticks=[0,1],xticklabels=['原 V2','XY 暂停候选'],title=title,ylim=(0,max(limit,*values)*1.3));ax.grid(axis='y',alpha=.15)
    fig.suptitle('月报增量｜单独检验额外横向搜索的作用',fontsize=15)
    complete='是' if a['candidate_metrics']['success'] else '否'
    fig.supxlabel(f'候选完整达标：{complete}。一例固定开发工况；深度到位不等于完整装配成功，未验证随机成功率。',fontsize=10)
    fig.savefig(target/'01_月报单变量对照.png');plt.close(fig)


def report(target,a,input_tag):
    old,new=a['reference_metrics'],a['candidate_metrics']
    change=new['advance_mm']-old['advance_mm']
    lines=['# B2-5.3 短时暂停额外横向搜索试验','',
           '2026-09-22。新增一次 X +100 μm 动力学运行，与冻结 V2 历史回合对照；预定最多暂停 1.0 s、平滑恢复 0.1 s，在运行前确定；原退出或保护可提前结束。本细分没有参数扫描。','',
           f"最终推进由 {old['advance_mm']:.6f} mm 变为 {new['advance_mm']:.6f} mm，差值 {change:+.6f} mm。候选完整达标：{'是' if new['success'] else '否'}；结束原因：{REASONS.get(new['termination'],new['termination'])}。",'',
           '| 指标 | 原 V2 | XY 暂停候选 |','|---|---:|---:|']
    for key,label in (('advance_mm','最终推进/mm'),('xy_error_um','XY误差/μm'),('angle_deg','总姿态误差/°'),('peak_force_mN','峰值合力/mN'),('peak_torque_mNm','峰值G力矩/mN·m'),('peak_penetration_um','最大穿透/μm'),('stop_time_s','停止时刻/s'),('searches','搜索次数'),('recoveries','回撤次数')):
        lines.append(f"| {label} | {old[key]:.6f} | {new[key]:.6f} |")
    lines+=['',f"候选未满足项：{'、'.join(new['unmet']) or '无'}。峰值来自全部物理子步，曲线来自 2 ms 采样。",'',
            '## 改动与证据','',
            '仅调整额外 XY 螺旋切向与轨迹跟踪项的增益；原力导纳、Z 力反馈规则、转动控制、V2 退出资格与各保护条件保持。暂停时搜索相位继续推进，时间和半径照常消耗；恢复阶段也属于本次干预。',
            f"新旧前 {a['identical_prefix_samples']} 个状态采样完全一致，直至 {a['identical_through_s']:.3f} s。之后逐条核对 {a['checked_probe_commands']} 条搜索命令：XY 增益、导纳状态、轴向反馈、转动命令与相位推进均符合预定规则。",'',
            '| 相对触发窗口/s | 原 V2 新增推进/μm | 候选新增推进/μm | 原 V2 XY路程/μm | 候选XY路程/μm |','|---|---:|---:|---:|---:|']
    def fmt(v):return '未覆盖' if v is None else f'{v:.3f}'
    for d,w in a['windows'].items():lines.append(f"| {d} | {fmt(w['reference']['advance_um'])} | {fmt(w['candidate']['advance_um'])} | {fmt(w['reference']['xy_path_um'])} | {fmt(w['candidate']['xy_path_um'])} |")
    lines+=['','XY 路程为采样位移模长的累计，不是最终误差。完整窗口可包含停止后的实际运动；提前终止造成不足时标为“未覆盖”，不拿较短窗口当作等长比较。','保持 Z 规则不变不等于后续 Z 指令相同：XY 改变后接触力不同，原力反馈会产生不同命令。','', '## 干预与退出事件','']
    for d,w in a['windows'].items():
        for name,label in (('reference','原 V2'),('candidate','候选')):
            if w[name]['contains_nonrunning']:lines.append(f"- {d} s 窗口的{label}记录包含非 RUNNING 阶段。")
    for e in a['probe_events']:lines.append(f"- {e['time_s']:.3f} s：{e['event']}。")
    for e in a['verified_exit_events']:
        v=e['exit_evidence'];lines.append(f"- {e['time_s']:.3f} s：满足原 V2 恢复后退出资格，深度 {v['exit_z_m']*1000:.6f} mm，持续 {v['duration_s']:.3f} s 推进 {v['advance_m']*1e6:.3f} μm，最大采样合力 {v['max_observed_force_N']*1000:.3f} mN。该资格已用原始轨迹复核。")
    if not a['verified_exit_events']:lines.append('- 本回合未取得原 V2 恢复后退出资格。')
    execution=a['probe_execution']
    lines+=['',f"实际零增益命令累计执行 {execution['zero_gain_command_duration_s']:.3f} s；0.1 s 恢复坡道本回合{'有' if execution['resume_ramp_executed'] else '没有'}动态执行。"]
    if not execution['resume_ramp_executed']:
        lines.append('恢复坡道只完成单元测试覆盖，不能把本回合写成验证了恢复过程。')
    for d,w in a['windows'].items():
        lines.append(f"{d} s 窗口候选包含策略阶段：{'、'.join(w['candidate']['policy_phases'])}。")
    if execution['ended_by_parent'] and execution['ended_by_parent'].get('phase')=='INSERT':
        elapsed=execution['ended_by_parent']['time_s']-a['identical_through_s']
        lines.append(f"触发后 {elapsed:.3f} s 按原 V2 资格进入 INSERT；因此 1.0 s 窗口中约 {max(0,1-elapsed):.3f} s 已包含正常插入及其 Z 规则切换。0.6 s 窗口用于观察持续 SEARCH 阶段内的差异；1.0 s 与全回合反映含后续状态转换的总效果，不能写成全程保持同一个 SEARCH 轴向公式的纯横向效果。")
    lines+=['','## 如何解释','',
            ('本例支持“短时减弱额外 XY 搜索可以改善这一固定条件下的推进”。不说明全部偏差工况改善，也不能推出永久关闭搜索有效。' if change>0 else '本例未支持用当前暂停窗口改善最终推进；保留负结果，不在本细分内调整时长挑选成功。'),
            '比较使用相同初始条件与冻结基础实现，因此是一个预定动作干预的对照；结论限于该工况和该暂停/恢复设计，不是普遍物理因果或随机成功率。旧 B2 的深度到位结果只作历史背景，不能把旧版同时改变 XY/Z 的效果混算为本次收益。',
            f"历史旧 B2 本例推进 {a['historical_v1_metrics']['advance_mm']:.6f} mm、XY 误差 {a['historical_v1_metrics']['xy_error_um']:.3f} μm。本次主要检验能否在保留更严格退出资格时恢复推进，不能仅凭相对失败 V2 的改善宣称优于旧 B2。",
            '无论结果如何，本候选不自动替代正式基线。模型仍未实物标定，未包含完整 CR5、实际夹爪和传感器。','',
            '## 查看与复现','',
            '- [月报图](01_月报单变量对照.png)；[控制曲线](02_控制与推进对照.png)',
            '- [审计与指标](comparison_audit.json)；[真实轨迹回放](真实轨迹回放.gif)',
            f'- [该次运行冻结协议](../{input_tag}/实验协议.md)','',
            '工作目录为项目 worktree。重跑时使用未存在的新 tag，不能覆盖旧结果：','','```powershell',
            "& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.validation.run_b2_xy_probe --tag reproduce_x100_01",
            "& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.reporting.report_b2_xy_probe --tag reproduce_x100_01 --out-tag reproduce_comparison_01 --replay",'```','',
            '当前 VS Code 的 05 仍是旧 V2，不会运行本候选。要在窗口查看本例，选择 06 并载入本例 runs/x_offset_pos_100um_xy_probe.json.gz；回放不重跑动力学。']
    (target/'B2-5.3单变量试验报告.md').write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',default='first_frozen_x100')
    parser.add_argument('--out-tag',default='comparison_first_frozen_x100')
    parser.add_argument('--replay',action='store_true');args=parser.parse_args()
    for tag in (args.tag,args.out_tag):
        if not tag or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in tag):parser.error('Simple folder names required')
    target=OUT/args.out_tag
    if target.exists():raise FileExistsError('Preserve report and experiment outputs; use a new out-tag')
    old,new,a,index=audit(OUT/args.tag)
    target.mkdir()
    dump(target/'comparison_audit.json',a)
    dump(target/'results_index.json',{'method':'one new XY probe vs preserved V2','input_index':f'{args.tag}/results_index.json',
                                    'input_index_sha256':sha(OUT/args.tag/'results_index.json'),'reference':index['reference']})
    plots(target,old,new,a);report(target,a,args.tag)
    if args.replay:replay(target,new)
    dump(target/'delivery_manifest.json',{p.relative_to(ROOT).as_posix():sha(p) for p in target.iterdir() if p.is_file()})
    print(json.dumps(a,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
