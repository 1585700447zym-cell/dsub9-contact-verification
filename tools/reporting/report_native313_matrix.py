"""Paired development results with explicit task, safety, and simulation-validity outcomes."""
import json
import math
import numpy as np
from matplotlib import pyplot as plt
from tools.reporting.report_training_readiness import font
from tools.validation.validate_training_readiness import sha,verify_hashes
from tools.validation.run_native313_matrix import ROOT,OUT,classify_episode
from tools.validation.run_b2_search import read_run
from tools.validation.run_b1_baseline import geometric_finish
from tools.validation.run_contact_candidate_stop import physical_tail_pass
from tools.validation.measure_readiness_stop import stop_qualified
from tools.validation.native313_matrix_audit import actual_stop_pass,actual_stop_start,samples_finite


def main():
    destination=OUT/'report_v1'
    if destination.exists():raise FileExistsError(destination)
    rows=[];raw={};indices={};protected={};case_order=None
    for policy in ('b1','b2'):
        folder=OUT/(policy+'_v1');idxpath=folder/'results_index.json'
        idx=json.loads(idxpath.read_text(encoding='utf-8'))
        assert idx['status']=='COMPLETE' and len(idx['runs'])==7
        verify_hashes(ROOT,idx['protected_inputs']);verify_hashes(ROOT,idx['historical_source_sha256'])
        protected[idxpath.relative_to(ROOT).as_posix()]=sha(idxpath);indices[policy]=idx
        names=[c['name'] for c in idx['cases']]
        assert names==[r['case'] for r in idx['runs']]
        if case_order is None:case_order=names
        else:assert names==case_order
        for entry in idx['runs']:
            path=folder/entry['file'];assert sha(path)==entry['sha256']
            audit=json.loads(path.read_text(encoding='utf-8'));verify_hashes(path.parent,audit['files'])
            run=read_run(path.parent/'original.json.gz');tail=read_run(path.parent/'stop_extension.json.gz')
            assert run['case']==audit['case'] and run['final']==tail['trace'][0]
            final=tail['trace'][-1];assert final==audit['final']
            stop=audit['stop_time_s'];end=final['time_s']
            hold=samples_finite(tail['physical_stop_samples']) and physical_tail_pass(tail['physical_stop_samples'],end,.0002)
            actual=actual_stop_start(tail['events'],stop)
            budget_pass=actual_stop_pass(tail['physical_stop_samples'],tail['events'],stop,end,.0002)
            stopped=bool(budget_pass and final['phase']=='STOPPING' and hold)
            safe=bool(actual is not None and stop_qualified(phase=final['phase'],events=tail['events'],recorded_time_s=end,
                         deadline_s=actual+2.,confirmed=budget_pass,final_stable=hold,peaks=tail['peaks']))
            classification=classify_episode(termination=run['termination'],phase=final['phase'],events=tail['events'],
                        finite=audit['finite'],stopped=stopped,safe=safe,final_geometry=geometric_finish(final))
            # Preserve original audit; the final verdict uses the actual STOPPING clock.
            trace=run['trace']+tail['trace'][1:];commands=np.asarray([r['limited_command_world'] for r in trace])
            tv=np.abs(np.diff(commands,axis=0)).sum(axis=0)
            pos=np.asarray(final['position_m']);q=np.asarray(final['quaternion_wxyz'])
            angle=math.degrees(2*math.acos(min(1.,abs(float(q[0]))/float(np.linalg.norm(q)))))
            row=dict(case=entry['case'],policy=policy,termination=run['termination'],**classification,
                     physical_stopped=stopped,strict_safe_stop=safe,original_success=run['termination']=='GEOMETRIC_SUCCESS',
                     actual_stop_start_s=actual,recorded_stop_decision_s=stop,actual_two_second_budget_pass=budget_pass,
                     initial_audit_category=audit['category'],
                     advance_mm=float((pos[2]-run['case']['start_origin_z_m'])*1000),xy_error_um=float(np.linalg.norm(pos[:2])*1e6),
                     z_error_um=float(abs(pos[2])*1e6),orientation_error_deg=angle,
                     original_end_time_s=run['final']['time_s'],end_time_including_stop_audit_s=end,
                     peak_force_mN=tail['peaks']['force_N']*1000,peak_torque_mNm=tail['peaks']['torque_G_Nm']*1000,
                     peak_penetration_um=tail['peaks']['penetration_m']*1e6,
                     search_count=audit['search_count'],recovery_count=audit['recovery_count'],
                     command_total_variation_by_axis=tv.tolist(),wall_seconds=audit['wall_seconds'],
                     audit_path=path.relative_to(ROOT).as_posix())
            rows.append(row);raw[(entry['case'],policy)]=run,tail,trace
    reference=None
    for case in case_order:
        a,b=[raw[(case,p)][0] for p in ('b1','b2')]
        for key in ('case','environment','finish_criteria','max_time_s','settle_time_s'):assert a[key]==b[key],(case,key)
        if reference is None:reference=a['environment']
        else:assert a['environment']==reference
    counts={p:{k:sum(bool(r[k]) for r in rows if r['policy']==p) for k in
                  ('full_success','original_success','physical_stopped','strict_safe_stop','candidate_data_valid')} for p in ('b1','b2')}
    blockers=[dict(case=r['case'],policy=r['policy'],category=r['category']) for r in rows if not r['candidate_data_valid']]
    result=dict(status='READY_FOR_RESIDUAL_INTERFACE_IMPLEMENTATION' if not blockers else 'TRAINING_READINESS_BLOCKED',
                matrix_complete=True,scope='seven_fixed_development_cases_not_generalization_success_rate',
                training_started=False,training_admitted=False,interface_implementation_admitted=not blockers,
                counts=counts,blockers=blockers,rows=rows,
                pending_before_first_training=['zero_residual_equivalence','reset_and_observation_action_reward_tests',
                                              'invalid_experience_isolation','conditional_recovery_and_stage_mask_smoke',
                                              'training_distribution_initialization_preflight',
                                              'save_load_evaluation_smoke'],
                environment=reference,source_sha256={**protected,**{p.relative_to(ROOT).as_posix():sha(p) for p in [
                    ROOT/'tools/reporting/report_native313_matrix.py',ROOT/'tools/validation/run_native313_matrix.py',
                    ROOT/'tools/validation/native313_matrix_audit.py']}})
    destination.mkdir();(destination/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    labels=['同轴','X +100μm','Y −100μm','roll +1.5°','联合A ×0.75','联合B ×0.75','联合A ×1.0']
    font();fig,axes=plt.subplots(1,3,figsize=(15,5.8),layout='constrained');x=np.arange(7)
    for offset,p,color in [(-.18,'b1','#447e99'),(.18,'b2','#dc8746')]:
        ordered=[next(r for r in rows if r['case']==c and r['policy']==p) for c in case_order]
        for ax,key in zip(axes,['advance_mm','peak_force_mN','peak_penetration_um']):
            bars=ax.bar(x+offset,[r[key] for r in ordered],width=.36,label=p.upper(),color=color)
            if key=='advance_mm':ax.bar_label(bars,labels=['成功' if r['full_success'] else '停止未过' if not r['physical_stopped'] else '失败' for r in ordered],rotation=90,padding=3,fontsize=8)
    for ax,ylabel,title in zip(axes,['推进量 / mm','全物理步峰值力 / mN','最大穿透 / μm'],['推进不等于成功','接触载荷','接触穿透']):
        ax.set_xticks(x,labels,rotation=30,ha='right');ax.set(ylabel=ylabel,title=title);ax.legend();ax.grid(axis='y',alpha=.2)
    axes[0].set_ylim(0,5.2);axes[1].axhline(25,color='#af4141',ls='--');axes[2].axhline(30,color='#af4141',ls='--')
    fig.suptitle(f"同一新版环境：B1 / B2 七工况配对重评\n完整成功 {counts['b1']['full_success']}/7 对 {counts['b2']['full_success']}/7；停止合格 {counts['b1']['physical_stopped']}/7 对 {counts['b2']['physical_stopped']}/7",fontsize=16)
    fig.supxlabel('固定开发清单，不是独立测试成功率；失败保留，控制参数未针对工况调优。',fontsize=11)
    fig.savefig(destination/'01_七工况方法对照.png',dpi=150);plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for col,case in enumerate(case_order[1:3]):
        for p,color in [('b1','#447e99'),('b2','#dc8746')]:
            run,tail,trace=raw[(case,p)];t=[r['time_s'] for r in trace]
            axes[0,col].plot(t,[(r['position_m'][2]-run['case']['start_origin_z_m'])*1000 for r in trace],label=p.upper(),color=color)
            stop=actual_stop_start(tail['events'],run['stop_time_s'])
            if stop is not None:
                samples=[r for r in tail['physical_stop_samples'] if r['time_s']>=stop-1e-9]
                axes[1,col].plot([r['time_s']-stop for r in samples],[max(r['linear_m_s']*1e6,1e-4) for r in samples],label=p.upper(),color=color,lw=.8)
        axes[0,col].set(title=labels[col+1],xlabel='仿真时间 / s',ylabel='推进量 / mm')
        axes[1,col].set(xlabel='距最终停止 / s',ylabel='线速度 / μm/s',yscale='log')
        axes[1,col].axhline(10,color='#af4141',ls='--')
    for ax in axes.flat:ax.legend();ax.grid(alpha=.2)
    fig.suptitle('预定 X/Y 代表工况：真实轨迹与停止记录',fontsize=16)
    fig.supxlabel('仅展示线速度；验收同时检查角速度与全回合保护。极小速度仅为对数显示截断。',fontsize=10)
    fig.savefig(destination/'02_代表工况真实轨迹.png',dpi=150);plt.close(fig)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','environment','source_sha256')},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
