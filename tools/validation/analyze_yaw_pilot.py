"""Read-only physics analysis of closed yaw records; emits derived evidence."""
import csv
import gzip
import json
import math
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'deliverables/learning_chain/b2_yaw_pilot_v2_20261023'


def analyze():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation.run_yaw_pilot import read,sha,write,check_common,PARENT
    from tools.validation.yaw_pilot import pin_diagnostics,rotation_matrix,pilot_cases
    from tools.validation.run_contact_cases import _quaternion
    from tools.model.layered_task import functional_finish,layered_pin_clearance_m,_layer_margin,_LAYERS
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    ledger=read(OUT/'ledger.json');reg=read(OUT/'registration.json')
    if ledger['status'] not in ('COMPLETED','STOPPED'):raise ValueError('Read only closed batch')
    for name,pin in reg['inputs'].items():
        if sha(OUT/'source_snapshot'/name)!=pin:raise ValueError('Source snapshot changed: '+name)
    rows=[];plots=[]
    for case,receipt in zip(pilot_cases(),ledger['episodes']):
        folder=OUT/'run'/case.name
        disk=read(folder/'receipt.json')
        if sha(folder/'episode.json.gz')!=disk['archive_sha256']:raise ValueError('Archive hash mismatch')
        raw=json.loads(gzip.decompress((folder/'episode.json.gz').read_bytes()))
        trace=raw['trace'];peaks=raw['cycle_peaks'];n=receipt['control_cycles']
        if not receipt['process_exit_confirmed']:raise ValueError('Worker not confirmed exited')
        check_common(disk,read(PARENT))
        if len(trace)!=n+1 or len(peaks)!=n or receipt['physical_substeps']!=10*n:
            raise ValueError('Raw/counter mismatch')
        if sum(p['samples'] for p in peaks)!=receipt['physical_substeps']:
            raise ValueError('Physical cycle samples mismatch')
        np.testing.assert_allclose(trace[0]['quaternion_wxyz'],_quaternion(case),rtol=0,atol=1e-15)
        np.testing.assert_allclose(trace[0]['position_m'],[.0003,.0003,-.005],rtol=0,atol=1e-15)
        times=np.array([r['time_s'] for r in trace])
        np.testing.assert_allclose(np.diff(times),.002,rtol=0,atol=1e-11)
        for r in trace:
            for field in ('position_m','quaternion_wxyz','velocity_world','contact_wrench_M',
                          'contact_wrench_G','raw_command_world','limited_command_world'):
                if not np.isfinite(r[field]).all():raise ValueError('Nonfinite trace')
            if abs(r['raw_command_world'][5])>.02+1e-12 or abs(r['yaw_admittance']['offset_rad'])>.08:
                raise ValueError('Yaw command/correction exceeded limit')
        stopped=actual_stop_pass(raw['stop_samples'],disk['environment_events'],disk['stop_time_s'],
                                 disk['audit_end_time_s'],.0002)
        stopped=bool(stopped and physical_tail_pass(raw['stop_samples'],disk['audit_end_time_s'],.0002))
        if stopped!=disk['stopped']:raise ValueError('Stop audit disagrees')
        task_index=int(np.argmin(abs(times-disk['task_time_s'])))
        task=trace[task_index]
        if disk['outcome']=='FULL_SUCCESS' and not functional_finish(task,disk['finish_criteria']):
            raise ValueError('Successful task does not satisfy nine-pin referee')
        contact_first={str(i):next((r['time_s'] for r in trace if i in r.get('diagnostic_contact_pins',[])),None)
                       for i in range(1,10)}
        entry_first={str(i):None for i in range(1,10)}
        diagnostic=[]
        for r in trace[::10]+[task,trace[-1]]:
            for pin in pin_diagnostics(r):
                if pin['tip_past_entry_plane'] and entry_first[str(pin['pin'])] is None:
                    entry_first[str(pin['pin'])]=r['time_s']
                diagnostic.append(dict(time_s=r['time_s'],pin=pin['pin'],
                    tip_x_offset_um=pin['tip_xy_offset_m'][0]*1e6,
                    tip_y_offset_um=pin['tip_xy_offset_m'][1]*1e6,
                    tip_z_mm=pin['tip_world_m'][2]*1e3))
        with (folder/'pin_tip_diagnostics.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(diagnostic[0]));writer.writeheader();writer.writerows(diagnostic)
        geometry=[]
        # Exact clipped-cylinder margins at initialization, task end and stop end.
        import tools.model.layered_task as model
        for label,r in [('initial',trace[0]),('task_end',task),('stop_end',trace[-1])]:
            R=rotation_matrix(r['quaternion_wxyz']);p=np.array(r['position_m']);pins=[]
            for i,(center,size,hole) in enumerate(zip(model._pin_centers,model._pin_sizes,model._holes)):
                margins={name:_layer_margin(R@center+p,R,size[0],size[1],a,b,hole[:2],radius)
                         for name,radius,a,b in _LAYERS}
                pins.append(dict(pin=i+1,**margins))
            geometry.append(dict(label=label,time_s=r['time_s'],pins=pins))
        write(folder/'pin_geometry.json',dict(exact_layer_margins=geometry,first_pin_contact_s=contact_first,
            first_observed_tip_past_entry_plane_s=entry_first,
            note='20ms plane-crossing samples are geometry diagnostics, not proof of full pin insertion; contact IDs observed at control samples.'))
        euler_yaw=lambda r:math.degrees(math.atan2(rotation_matrix(r['quaternion_wxyz'])[1,0],
                                                  rotation_matrix(r['quaternion_wxyz'])[0,0]))
        nonzero=sum(abs(r['raw_command_world'][5])>1e-10 for r in trace)
        initial_offsets=[np.linalg.norm(p['tip_xy_offset_m'])*1e6 for p in pin_diagnostics(trace[0])]
        r=dict(case_id=case.name,yaw_initial_deg=math.degrees(case.yaw_rad),outcome=disk['outcome'],
               task_time_s=disk['task_time_s'],reason=disk['final_reason'],
               yaw_task_end_deg=euler_yaw(task),yaw_stop_end_deg=euler_yaw(trace[-1]),
               radial_task_end_um=float(np.linalg.norm(task['position_m'][:2])*1e6),
               z_task_end_mm=task['position_m'][2]*1e3,
               peak_force_N=disk['peaks']['force_N'],peak_torque_G_Nm=disk['peaks']['torque_G_Nm'],
               guard_facts=disk['guard_facts'],yaw_nonzero_command_samples=nonzero,
               initial_pin_tip_radial_min_max_um=[min(initial_offsets),max(initial_offsets)],
               physical_substeps=disk['physical_substeps'],stopped=stopped,valid=disk['valid'],
               archive_sha256=disk['archive_sha256'],record_audit_passed=True)
        rows.append(r)
        plots.append((case.name,times,np.array([euler_yaw(t) for t in trace]),
                      np.array([np.linalg.norm(t['contact_wrench_M'][:3]) for t in trace])))
    total=sum(r['physical_substeps'] for r in rows)
    if total!=ledger['physical_substeps']:raise ValueError('Batch physical count mismatch')
    assessment=dict(version='yaw_four_closed_audit_v1',verified=True,batch_status=ledger['status'],rows=rows,
        initialization_attempts=ledger['actual_initialization_attempts'],physical_substeps=total,
        cumulative_initialization_attempts=ledger['cumulative_initialization_attempts'],
        successes=sum(r['outcome']=='FULL_SUCCESS' for r in rows),policy_calls=0,training_updates=0,
        registration_sha256=sha(OUT/'registration.json'),ledger_sha256=sha(OUT/'ledger.json'),
        limits='Four deterministic development records; no estimated success probability or learning superiority.')
    write(OUT/'assessment.json',assessment)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(11,7),sharex=True,layout='constrained')
    for ax,(name,t,yaw,force),r in zip(axes.flat,plots,rows):
        ax.plot(t,yaw,color='#185a9d',label='yaw (deg)');ax.axhline(0,color='gray',lw=.6)
        ax.set(title=f"{name}: {r['outcome']}",ylabel='Yaw (deg)',xlabel='Simulation time (s)')
        ax.grid(alpha=.2);ax.axvline(r['task_time_s'],color='gray',ls='--',lw=.7)
        other=ax.twinx();other.plot(t,force,color='#cc7c2b',alpha=.5,lw=.7)
        other.set_ylabel('Contact force (N)',color='#a06020');other.set_ylim(0,5.5)
    fig.savefig(OUT/'yaw_force_traces.png',dpi=180);plt.close(fig)
    lines=['# B.2第3项｜首组四工况yaw小试结果','',
        'X/Y均为公头装配原点相对母头原点的初始+0.30 mm，roll−1°、pitch+1°；各针错位由整件刚体姿态计算。',
        '采用固定Mz导纳，没有主动yaw扫描；N2动力学、450 μm/s搜索、25 s时限和原保护/九针成功条件保持。','',
        '| 初始yaw | 结果 | 任务记录时间(s) | 任务结束yaw | 峰值合力(N) | 原因 |',
        '|---|---|---:|---:|---:|---|']
    for r in rows:
        lines.append(f"| {r['yaw_initial_deg']:+.1f}° | {r['outcome']} | {r['task_time_s']:.3f} | {r['yaw_task_end_deg']:+.3f}° | {r['peak_force_N']:.3f} | {r['reason']} |")
    lines+=['',f"完成{assessment['successes']}/{len(rows)}；新增初始化{assessment['initialization_attempts']}，物理子步{total:,}，累计初始化{assessment['cumulative_initialization_attempts']}；策略调用/训练更新0。",'',
        '任务记录时间包含原有结束观察窗口；具体TIME_LIMIT事件时刻见各回合environment_events/controller_events。各回合还保留2秒停稳审核尾段。',
        '四点均为一次确定性开发记录，不能估计成功概率，也不能据此认定所有传统固定控制失效；未训练或评价SAC。','',
        '## 证据与查看','',
        '- `registration.json`、`source_snapshot/`：批准范围、冻结来源与运行时。',
        '- `run/<工况>/episode.json.gz`：逐控制周期姿态、力矩、命令、阶段与逐物理子步峰值及停止采样。',
        '- `run/<工况>/pin_tip_diagnostics.csv`、`pin_geometry.json`：逐针偏差、孔口平面关系、接触首次采样及精确分层配合余量。',
        '- `assessment.json`：闭合后独立重算初始位姿、记录计数、命令限幅、九针成功及停稳。','',
        '![yaw与合力随时间](yaw_force_traces.png)','',
        '本轮结束后暂停汇报，第二组待讨论；SAC保持暂停，完整B.2/C未验收。']
    (OUT/'四工况结果.md').write_bytes(('\n'.join(lines)+'\n').encode('utf-8'))
    print(json.dumps(assessment,ensure_ascii=False,indent=2))


if __name__=='__main__':
    sys.path.insert(0,str(ROOT));analyze()
