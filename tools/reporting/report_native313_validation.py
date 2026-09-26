"""Read-only outcome report from audited data; original ERROR indices remain preserved."""
import json
import math
import numpy as np
from matplotlib import pyplot as plt
from tools.reporting.report_training_readiness import font
from tools.reporting.report_contact_candidate import common_rows
from tools.validation.validate_dynamic_actuator import orientation_difference
from tools.validation.validate_training_readiness import verify_hashes
from tools.validation.run_b2_search import read_run
from tools.validation.run_native313_validation import ROOT, OUT, sha, write
from tools.validation.run_native313_stop import verify_static_dependencies


def main():
    verify_static_dependencies()
    static=json.loads((OUT/'static_extended.json').read_text(encoding='utf-8'))
    audits=[];runs=[];tails=[];traces=[];sources=[OUT/'static_extended.json',OUT/'时间步判读补充.md',
                                              ROOT/'tools/reporting/report_native313_validation.py']
    for tag in ('stop_dt0p2_v1','stop_dt0p1_v1'):
        folder=OUT/tag;path=folder/'audited_results.json';audit=json.loads(path.read_text(encoding='utf-8'))
        verify_hashes(ROOT,audit['source_sha256']);verify_hashes(ROOT,audit['corrected_protected_inputs'])
        run=read_run(folder/'original_duration.json.gz');tail=read_run(folder/'stop_extension.json.gz')
        audits.append(audit);runs.append(run);tails.append(tail);traces.append(run['trace']+tail['trace'][1:]);sources.append(path)
    ma,mb=[json.loads(json.dumps(r['environment'])) for r in runs]
    for m in (ma,mb):m['config'].pop('timestep');m['effective_options'].pop('timestep')
    assert ma==mb and runs[0]['case']==runs[1]['case'] and runs[0]['controller']==runs[1]['controller']
    a,b=common_rows(*traces)
    assert len(a)>1
    distances=[float(np.linalg.norm(np.array(x['position_m'])-y['position_m'])) for x,y in zip(a,b)]
    angle=math.degrees(orientation_difference(a[-1]['quaternion_wxyz'],b[-1]['quaternion_wxyz']))
    forces=[r['peaks']['force_N'] for r in audits]
    relative=abs(forces[0]-forces[1])/max(forces) if max(forces)>.001 else None
    events_equal=[e['reason'] for e in audits[0]['events']]==[e['reason'] for e in audits[1]['events']]
    end_position=float(np.linalg.norm(np.array(audits[0]['final']['position_m'])-audits[1]['final']['position_m'])*1e6)
    end_angle=math.degrees(orientation_difference(audits[0]['final']['quaternion_wxyz'],audits[1]['final']['quaternion_wxyz']))
    compare=dict(common_time_s=a[-1]['time_s'],common_samples=len(a),unmatched_samples=[len(t)-len(a) for t in traces],
                 common_end_position_difference_um=distances[-1]*1e6,maximum_common_path_difference_um=max(distances)*1e6,
                 common_end_angle_difference_deg=angle,full_episode_peak_force_relative_difference=relative,
                 same_event_reasons=events_equal,separate_end_position_difference_um=end_position,
                 separate_end_angle_difference_deg=end_angle)
    compare['historical_strict_pass']=bool(distances[-1]*1e6<20 and angle<.1 and events_equal and (relative is None or relative<.2))
    compare['initial_protocol_end_pass']=bool(end_position<=25 and end_angle<=.2 and
                       (runs[0]['termination']=='GEOMETRIC_SUCCESS')==(runs[1]['termination']=='GEOMETRIC_SUCCESS'))
    ready=bool(static['passed'] and all(i['passed'] for i in audits) and compare['historical_strict_pass'] and compare['initial_protocol_end_pass'])
    result=dict(status='READY_FOR_PAIRED_BASELINE_REEVALUATION' if ready else 'CANDIDATE_NOT_ADMITTED',
                static_passed=static['passed'],static_checks=static['historical_checks']+static['new_checks'],
                stop_passes=[r['passed'] for r in audits],terminations=[r['original_termination'] for r in audits],
                comparison=compare,training_admitted=False,production_upgraded=False,
                archive_status='Raw data independently audited after preserved archive-reference ERROR',
                source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sources})
    dest=OUT/'report_v1'
    if dest.exists():raise FileExistsError(dest)
    write(dest/'assessment.json',result)
    font();fig,axes=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    for i,(audit,run,tail,trace,label) in enumerate(zip(audits,runs,tails,traces,['0.2 ms','0.1 ms'])):
        color=['#25758c','#da8543'][i]
        t=[r['time_s'] for r in trace]
        axes[0,0].plot(t,[(r['position_m'][2]-run['case']['start_origin_z_m'])*1000 for r in trace],label=label,color=color)
        axes[0,1].plot(t,[np.linalg.norm(r['contact_wrench_G'][:3])*1000 for r in trace],label=label,color=color,lw=.7)
        stop=audit['stop_time_s']
        if stop is not None:
            rows=[r for r in tail['physical_stop_samples'] if r['time_s']>=stop-1e-9]
            elapsed=[r['time_s']-stop for r in rows]
            axes[1,0].plot(elapsed,[max(r['linear_m_s']*1e6,1e-4) for r in rows],label=label,color=color,lw=.8)
            axes[1,1].plot(elapsed,[max(r['angular_rad_s'],1e-8) for r in rows],label=label,color=color,lw=.8)
    axes[0,0].axhline(4,color='gray',ls='--',lw=.8)
    axes[0,0].set(xlabel='仿真时间 / s',ylabel='插入推进量 / mm',title='完整闭环轨迹（2 ms 控制采样）')
    axes[0,1].axhline(25,color='#b34242',ls='--',label='原保护阈值')
    axes[0,1].set(xlabel='仿真时间 / s',ylabel='接触合力 / mN',title='接触载荷（曲线为控制采样，验收使用全步峰值）')
    for ax,limit,ylabel,title in [(axes[1,0],10,'线速度 / μm/s','停止后的线速度'),(axes[1,1],.001,'角速度 / rad/s','停止后的角速度')]:
        ax.axhline(limit,color='#b34242',ls='--',label='原停止阈值')
        ax.set(xlabel='距最终停止命令 / s',ylabel=ylabel,title=title,yscale='log')
    for ax in axes.flat:ax.legend(fontsize=9);ax.grid(alpha=.2)
    title='新版 native：静态回归、完整插入与停止验收'
    verdict='两回合停止通过；步长一致性'+('通过' if compare['historical_strict_pass'] else '未通过') if all(result['stop_passes']) else '仍有停止或全回合安全门槛未通过'
    fig.suptitle(title+'\n'+verdict,fontsize=16)
    fig.supxlabel('仅固定开发 Y 工况；未升级正式环境、未开始训练。停止曲线记录每个物理步；极小值仅为对数显示截断。',fontsize=10)
    fig.savefig(dest/'月报_新版完整回归与停止.png',dpi=150);plt.close(fig)
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
