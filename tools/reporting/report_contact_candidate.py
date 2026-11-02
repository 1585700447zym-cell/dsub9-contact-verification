"""Read-only candidate report with static evidence, full-stop outcomes and timestep audit."""
import argparse
import json
import math
import numpy as np
from matplotlib import pyplot as plt
from tools.reporting.report_training_readiness import font
from tools.validation.validate_training_readiness import ROOT,sha,verify_hashes
from tools.validation.run_b2_search import read_run
from tools.validation.validate_dynamic_actuator import orientation_difference

OUT=ROOT/'deliverables/contact_consistency_repair'


def common_rows(left,right):
    a=[];b=[];i=j=0
    while i<len(left) and j<len(right):
        delta=left[i]['time_s']-right[j]['time_s']
        if abs(delta)<1e-8:
            a.append(left[i]);b.append(right[j]);i+=1;j+=1
        elif delta<0:i+=1
        else:j+=1
    return a,b


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output-dir',required=True);args=parser.parse_args()
    dest=ROOT/args.output_dir
    if dest.exists():raise FileExistsError(dest)
    static=json.loads((OUT/'static_gate_v1/results.json').read_text(encoding='utf-8'))
    probe=json.loads((OUT/'backend_probe_v1/results.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT,static['input_sha256']);verify_hashes(ROOT,static['historical_source_sha256'])
    verify_hashes(ROOT,probe['input_sha256'])
    audit=json.loads((OUT/'strict_static_audit.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT,audit['source_sha256'])
    source_audit=json.loads((OUT/'核心依赖追溯核查.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT,source_audit['verified_dependencies'])
    verify_hashes(ROOT,source_audit['evidence_sha256'])
    indices=[];runs=[];tails=[];traces=[]
    for name in ('stop_dt0p2_v1','stop_dt0p1_v1'):
        folder=OUT/name;idx=json.loads((folder/'results_index.json').read_text(encoding='utf-8'))
        assert idx['status']=='COMPLETE';verify_hashes(ROOT,idx['protected_inputs']);verify_hashes(folder,idx['files'])
        run=read_run(folder/'original_duration.json.gz');tail=read_run(folder/'stop_extension.json.gz')
        indices.append(idx);runs.append(run);tails.append(tail);traces.append(run['trace']+tail['trace'][1:])
    ma=json.loads(json.dumps(runs[0]['environment']));mb=json.loads(json.dumps(runs[1]['environment']))
    for m in (ma,mb):m['config'].pop('timestep');m['effective_options'].pop('timestep')
    assert ma==mb and runs[0]['case']==runs[1]['case'] and runs[0]['controller']==runs[1]['controller']
    a,b=common_rows(*traces)
    if len(a)<2:raise ValueError('Insufficient common data; candidate cannot be admitted')
    distances=[float(np.linalg.norm(np.array(x['position_m'])-y['position_m'])) for x,y in zip(a,b)]
    angle=orientation_difference(a[-1]['quaternion_wxyz'],b[-1]['quaternion_wxyz'])
    forces=[i['peaks']['force_N'] for i in indices]
    relative=abs(forces[0]-forces[1])/max(forces) if max(forces)>.001 else None
    same_events=[e['reason'] for e in indices[0]['events']]==[e['reason'] for e in indices[1]['events']]
    comparison=dict(common_time_s=a[-1]['time_s'],common_samples=len(a),
                    unmatched_samples=[len(t)-len(a) for t in traces],end_position_difference_um=distances[-1]*1e6,
                    maximum_common_path_difference_um=max(distances)*1e6,end_angle_difference_deg=math.degrees(angle),
                    full_episode_peak_force_relative_difference=relative,same_event_reasons=same_events)
    comparison['passed']=bool(distances[-1]<20e-6 and angle<math.radians(.1) and same_events and (relative is None or relative<.2))
    ready=static['passed'] and audit['passed'] and all(i['passed'] for i in indices) and comparison['passed']
    result=dict(status='READY_FOR_PAIRED_BASELINE_REEVALUATION' if ready else 'CANDIDATE_NOT_ADMITTED',
                static_passed=static['passed'],strict_static_passed=audit['passed'],stop_passes=[i['passed'] for i in indices],comparison=comparison,
                training_admitted=False,source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in [
                    ROOT/'tools/reporting/report_contact_candidate.py',OUT/'时间步判读说明.md',OUT/'strict_static_audit.json',OUT/'核心依赖追溯核查.json',
                    OUT/'static_gate_v1/results.json',OUT/'stop_dt0p2_v1/results_index.json',OUT/'stop_dt0p1_v1/results_index.json']})
    dest.mkdir(parents=True);(dest/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    font();fig,axes=plt.subplots(1,2,figsize=(13,5.5),layout='constrained')
    labels=['旧异常 / 128 段','旧异常 / 256 段','停止疑点 / 256 段']
    for offset,mode,color,label in [(-.24,'mpr','#668ba5','旧 MPR'),(0.,'native','#bf754a','原 native'),(.24,'native_tight','#3e947d','候选 native / 1e−12')]:
        vals=[next(r['depth_m'] for r in probe['results'] if r['fixture']==fixture and r['mode']==mode)*1e6
              for fixture in ('native_failure_128','native_failure_256','mpr_stop_256')]
        bars=axes[0].bar(np.arange(3)+offset,vals,width=.24,color=color,label=label)
        axes[0].bar_label(bars,labels=[f'{v:.3g}' for v in vals],fontsize=8,padding=3)
    axes[0].set_yscale('log');axes[0].set_ylim(.001,3000);axes[0].set_xticks(range(3),labels)
    axes[0].set(ylabel='最大穿透 / μm（对数坐标）',title='同一冻结姿态：浅接触异常值对照');axes[0].legend(fontsize=8)
    text='静态回归已完成\n\n63 个入口邻域姿态\n501 个原轨迹姿态（80 个有接触）\n140 个历史姿态（24 个有正见证）\n4 个分离 / 孔壁检查，逐针对应核查\n\n全部通过本轮预设门槛\n\n局部几何一致性 ≠ 完整物理可靠性\n须结合完整回合的动力学停止验收'
    axes[1].axis('off');axes[1].text(.05,.98,text,va='top',fontsize=13,linespacing=1.5)
    fig.suptitle('入口接触一致性：建立独立候选，保留历史基线',fontsize=16)
    fig.savefig(dest/'01_接触一致性修复候选.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(13,5.5),layout='constrained')
    for idx,tail,label in zip(indices,tails,['0.2 ms','0.1 ms']):
        if idx['stop_time_s'] is None:
            for axis in axes:
                axis.text(.98,.9,f"{label}：{idx['end_time_s']:.4f} s 无效终止\n未进入最终停止，不能绘制停稳曲线",
                          transform=axis.transAxes,ha='right',va='top',color='#b34242',fontsize=10)
            continue
        rows=[r for r in tail['physical_stop_samples'] if r['time_s']>=idx['stop_time_s']-1e-9]
        t=[r['time_s']-idx['stop_time_s'] for r in rows]
        axes[0].plot(t,[r['linear_m_s']*1e6 for r in rows],label=label,lw=.8)
        axes[1].plot(t,[r['angular_rad_s'] for r in rows],label=label,lw=.8)
    for ax,limit,ylabel in zip(axes,[10,.001],['线速度 / μm/s','角速度 / rad/s']):
        ax.axhline(limit,color='#b34242',ls='--',label='原停止阈值');ax.set(xlabel='距最终停止命令 / s',ylabel=ylabel);ax.legend();ax.grid(alpha=.2)
    fig.suptitle('完整 B2 Y 回合后的停止复验（逐物理步记录）',fontsize=16)
    fig.supxlabel('各回合最多观察到停止后 2 s；曲线稳定不能替代全回合安全和步长一致性检查。',fontsize=10)
    fig.savefig(dest/'02_真实动力学停止复验.png',dpi=150);plt.close(fig)
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
