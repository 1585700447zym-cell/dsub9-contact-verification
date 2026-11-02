"""Read-only evidence collection and prespecified baseline selection."""
import argparse
import json
import math
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from tools.visualization.font_support import find_chinese_font
from tools.reporting.report_b2 import verified, CASE_LABELS
from tools.reporting.report_b2_matrix import metrics
from tools.validation.run_b1_baseline import dump, cases
from tools.validation.run_b2_search import read_run
from tools.validation.validate_training_readiness import OUT, ROOT, sha, verify_hashes, new_target


def counts(rows):
    return {'success':sum(r['success'] for r in rows),
            'invalid':sum(r['termination'].startswith('INVALID') or r['termination']=='SIMULATION_ERROR' for r in rows),
            'overload':sum(r['peak_force_mN']>=25 or r['peak_torque_mNm']>=.5 or r['peak_penetration_um']>=30 for r in rows)}


def select_baseline(old,new):
    if [r['case'] for r in old]!=[r['case'] for r in new]:raise ValueError('Different case sets')
    a,b=counts(old),counts(new)
    safe=b['invalid']==0 and b['invalid']<=a['invalid'] and b['overload']<=a['overload']
    improves=safe and b['success']>a['success']
    reason='additional_complete_success' if improves else 'no_primary_task_improvement'
    if safe and not improves and b['success']==a['success'] and b['success']:
        subset=all(not x['success'] or y['success'] for x,y in zip(old,new))
        pairs=[(x,y) for x,y in zip(old,new) if x['success'] and y['success']]
        keys=('success_time_s','peak_force_mN','peak_torque_mNm')
        nonworse=all(y[k]<=x[k]+1e-9 for x,y in pairs for k in keys)
        better=any(y[k]<x[k]-1e-9 for x,y in pairs for k in keys)
        improves=subset and nonworse and better
        if improves:reason='same_success_set_with_pareto_improvement'
    if not safe:reason='invalid_or_increased_overload'
    return {'selected':'B2_pause2_candidate' if improves else 'B2_original','reason':reason,
            'old_counts':a,'candidate_counts':b,'development_only':True}


def extra_metrics(r):
    m=metrics(r)
    v=np.asarray(r['final']['velocity_world'])
    m.update(final_linear_um_s=float(np.linalg.norm(v[:3])*1e6),final_angular_rad_s=float(np.linalg.norm(v[3:])),
             final_stopped=bool(np.linalg.norm(v[:3])<=1e-5 and np.linalg.norm(v[3:])<=.001))
    t=np.array([s['time_s'] for s in r['trace']]);u=np.array([s['limited_command_world'] for s in r['trace']])
    good=np.diff(t)>0;rates=np.diff(u,axis=0)[good]/np.diff(t)[good,None]
    m['max_linear_command_change_m_s2']=float(np.max(np.linalg.norm(rates[:,:3],axis=1)))
    m['max_angular_command_change_rad_s2']=float(np.max(np.linalg.norm(rates[:,3:],axis=1)))
    probe=r.get('probe_trace',[]);period=r['environment']['config']['control_period']
    m['probe_triggered']=bool(probe)
    m['zero_extra_xy_command_duration_s']=sum(s['extra_xy_gain']==0 for s in probe)*period
    m['partial_restore_command_duration_s']=sum(0<s['extra_xy_gain']<1 for s in probe)*period
    m['full_xy_restore_observed']=any(s['extra_xy_gain']==1 for s in probe)
    # Check velocities/commands as well as positions and contact loads.
    for s in r['trace']:
        values=s['position_m']+s['quaternion_wxyz']+s['velocity_world']+s['contact_wrench_M']+s['contact_wrench_G']+s['limited_command_world']
        if not np.isfinite(values).all():raise ValueError('Nonfinite recorded observation')
    return m


def load_candidates(prefix):
    folder,index,old=verified('matrix_v1_7cases');new=[];refs=[]
    for i,c in enumerate(cases(),1):
        p=OUT/f'{prefix}_{i:02d}'/'results_index.json';v=json.loads(p.read_text(encoding='utf-8'))
        if v['status']!='COMPLETE' or len(v['runs'])!=1:raise ValueError('Incomplete candidate matrix')
        verify_hashes(ROOT,v['protected_inputs'])
        verify_hashes(p.parent/'source_snapshot',v['source_sha256'])
        e=v['runs'][0];verify_hashes(p.parent,{e['file']:e['sha256']})
        r=read_run(p.parent/e['file'])
        if r['case']['name']!=c.name or r['source_sha256']!=v['source_sha256']:raise ValueError('Candidate index mismatch')
        if r['historical_source_sha256']!=index['historical_source_sha256']:raise ValueError('Mixed model versions')
        if new and r['controller']!=new[0]['controller']:raise ValueError('Mixed candidate configurations')
        reference=old[2*(i-1)+1]
        for key in ('case','environment','finish_criteria','max_time_s','settle_time_s'):
            if r[key]!=reference[key]:raise ValueError('Unfair field: '+key)
        new.append(r);refs.append({'index':p.relative_to(ROOT).as_posix(),'sha256':sha(p),
                                  'run':(p.parent/e['file']).relative_to(ROOT).as_posix(),'run_sha256':e['sha256']})
    return old,new,refs


def font():
    path=find_chinese_font();font_manager.fontManager.addfont(str(path))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(path)).get_name(),
                         'axes.unicode_minus':False,'font.size':10,'figure.dpi':150})


def numerical_report(tag):
    target=OUT/tag;p=target/'results_index.json';v=json.loads(p.read_text(encoding='utf-8'))
    if v['status']!='COMPLETE':raise ValueError('Incomplete numerical audit')
    verify_hashes(ROOT,v['protected_inputs'])
    for e in v['runs']:verify_hashes(target,{e['file']:e['sha256']})
    rows=v['comparisons'];font();fig,axes=plt.subplots(1,3,figsize=(13,5),layout='constrained')
    labels=['同轴','联合 A ×0.5','联合 A ×0.75','联合 B ×0.5','联合 B ×0.75','联合 A 全幅','X +100 μm','Y −100 μm']
    settings=[('end_drive_position_difference_m',1e6,20,'位置差 / μm'),
              ('end_drive_angle_difference_rad',180/math.pi,.1,'姿态差 / °'),
              ('peak_force_relative_difference',100,20,'峰值力相对差 / %')]
    for ax,(key,scale,limit,label) in zip(axes,settings):
        values=[r[key]*scale if r[key] is not None else 0 for r in rows]
        bars=ax.barh(labels,values,color=['#278596' if r['pass'] else '#c36a4e' for r in rows]);ax.axvline(limit,c='#c36a4e',ls='--')
        ax.bar_label(bars,labels=['不计' if r[key] is None else f'{x:.3g}' for r,x in zip(rows,values)],padding=3,fontsize=8)
        ax.set(xlabel=label,xlim=(0,max(limit*1.15,max(values)*1.1)));ax.grid(axis='x',alpha=.2);ax.invert_yaxis()
    fig.suptitle('256 段当前路径：0.2 ms 与 0.1 ms 时间步比较（短回合）',fontsize=15)
    fig.supxlabel('虚线为原有门槛；同轴峰值力 ≤1 mN，相对差不计。结论不外推到全部长回合或真实设备。')
    fig.savefig(target/'当前路径时间步比较.png');plt.close(fig)
    lines=['# 当前路径数值复验','',f"结果：**{v['verdict']}**。新增九回合，与历史七回合组成八组比较；旧全局验收失败记录保持不变。",'',
           '| 工况 | 位置差/μm | 姿态差/° | 峰值力相对差/% | 事件一致 | 比较通过 |',
           '|---|---:|---:|---:|---|---|']
    for label,r in zip(labels,rows):
        f='不计' if r['peak_force_relative_difference'] is None else f"{r['peak_force_relative_difference']*100:.6f}"
        lines.append(f"| {label} | {r['end_drive_position_difference_m']*1e6:.6f} | {r['end_drive_angle_difference_rad']*180/math.pi:.6f} | {f} | {r['same_events']} | {r['pass']} |")
    lines+=['','此外逐项检查短回合有限数、停止线/角速度和驱动限幅，详见 results_index.json 的 all_run_checks。',
            '本轮只能评价当前 256 段、MPR、指定短回合的时间步一致性。128/256 差异、长搜索轨迹敏感性、未标定接触参数仍须明确保留。',
            '', '![数值复验](当前路径时间步比较.png)','']
    (target/'数值复验报告.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')


def matrix_report(prefix,output_tag=None):
    if output_tag is None and prefix!='candidate_pause2':
        raise ValueError('A new reproduction requires a new output tag')
    target=OUT if output_tag is None else new_target(OUT,output_tag)
    old,new,refs=load_candidates(prefix)
    target.mkdir(parents=True,exist_ok=True)
    groups=[[extra_metrics(r) for r in old[::2]],[extra_metrics(r) for r in old[1::2]],[extra_metrics(r) for r in new]]
    selection=select_baseline(groups[1],groups[2]);names=['B1 固定导纳','原 B2','V2 + 2 s 暂停候选']
    dump(target/'统一开发评价.json',{'groups':dict(zip(names,groups)),'selection':selection,'candidate_references':refs})
    font();fig,axes=plt.subplots(2,1,figsize=(13,9),layout='constrained');x=np.arange(7)
    for i,(name,group,color) in enumerate(zip(names,groups,['#8391a0','#24879b','#bd7545'])):
        axes[0].bar(x+(i-1)*.25,[m['advance_mm'] for m in group],.23,label=name,color=color)
        axes[1].bar(x+(i-1)*.25,[m['peak_force_mN'] for m in group],.23,color=color)
    labels=[CASE_LABELS[r['case']] for r in groups[0]]
    axes[0].set(ylabel='最终推进 / mm',title='同一环境、预算和完成标准下的全部七个开发工况');axes[0].legend(ncol=3)
    axes[0].axhline(4,c='#888888',ls='--');axes[1].axhline(25,c='#c35c49',ls='--')
    axes[1].set(ylabel='物理步峰值力 / mN')
    for ax in axes:ax.set(xticks=x,xticklabels=labels);ax.grid(axis='y',alpha=.2)
    fig.supxlabel('完整成功数：'+ '；'.join(f"{n} {counts(g)['success']}/7" for n,g in zip(names,groups))+'。推进量到位不等于完整成功。')
    fig.savefig(target/'月报_基线完整对照.png');plt.close(fig)
    lines=['# 基线统一开发评价','',f"按预先规则选择：**{selection['selected']}**；原因：{selection['reason']}。",'',
           '| 工况 | 策略 | 完整成功 | 推进/mm | XY/μm | 姿态/° | 峰值力/mN | 终点已静止 | 结束原因 |',
           '|---|---|---|---:|---:|---:|---:|---|---|']
    for i in range(7):
        for name,g in zip(names,groups):
            m=g[i];lines.append(f"| {CASE_LABELS[m['case']]} | {name} | {m['success']} | {m['advance_mm']:.4f} | {m['xy_error_um']:.3f} | {m['angle_deg']:.4f} | {m['peak_force_mN']:.4f} | {m['final_stopped']} | {m['termination']} |")
    lines+=['','## 暂停实际执行情况','',
            '配置的 2 s 是上限，父控制器可以提前退出。下列时长按实际下发的 2 ms 指令周期计数；含端点时可能为 2.002 s。不是刚体完全静止时长。','',
            '| 工况 | 触发暂停 | 额外 XY 为零的指令时长/s | 部分恢复/s | 完全恢复出现 |',
            '|---|---|---:|---:|---|']
    for m in groups[2]:
        lines.append(f"| {CASE_LABELS[m['case']]} | {m['probe_triggered']} | {m['zero_extra_xy_command_duration_s']:.3f} | {m['partial_restore_command_duration_s']:.3f} | {m['full_xy_restore_observed']} |")
    lines+=['','全部成功时间、力矩/穿透峰值、停止后速度、恢复次数与命令变化率见统一开发评价.json。',
            '十四个对照回合经哈希和同环境检查后复用；七个候选为本轮新运行。开发计数不代表独立随机测试成功率。',
            '原 B2 Y 回合最终未完全停稳仍保留，不能称为静止状态，也不允许据此自动回撤。',
            '', '![月报图](月报_基线完整对照.png)','']
    (target/'基线统一开发评价.md').write_text('\n'.join(lines),encoding='utf-8',newline='\n')
    return selection


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--numerical',default='numerical_gate_v1');p.add_argument('--candidate-prefix');p.add_argument('--output-tag')
    args=p.parse_args();numerical_report(args.numerical)
    if args.candidate_prefix:print(json.dumps(matrix_report(args.candidate_prefix,args.output_tag),ensure_ascii=False))
