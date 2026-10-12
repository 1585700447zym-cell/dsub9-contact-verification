"""Read-only reduction of this bounded run; no reset, forward, step or policy."""
from pathlib import Path
import gzip
import hashlib
import json
import math
import os
import sys
from collections import deque

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT))
OUT=Path(__file__).resolve().parent
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/mpl_clearance120')
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.validation.native313_matrix_audit import actual_stop_pass
from tools.validation.run_contact_candidate_stop import physical_tail_pass
from tools.model.clearance_task import finish_criteria,pin_fit,pin_clearance_m
from tools.validation.run_b1_baseline import geometric_finish
import numpy as np


def diagnose_stall(data,config,source_hash):
    history=deque();eligible=[];triggers=[]
    for row in data['trace']:
        if row['phase']!='RUNNING' or row['policy_phase']!='INSERT':continue
        t=row['time_s'];z=row['position_m'][2];history.append((t,z))
        while len(history)>1 and history[1][0]<=t-config['stall_window_s']:history.popleft()
        old_t,old_z=history[0]
        if t>=config['stall_earliest_s'] and t-old_t>=config['stall_window_s']-1e-9:
            advance=z-old_z;force=row['contact_wrench_M'][2]
            eligible.append(dict(time_s=t,window_advance_um=advance*1e6,axial_force_N=force))
            if advance<config['stall_advance_m'] and force < -config['stall_axial_force_N']:triggers.append(t)
    final=data['trace'][-1];q=np.array(final['quaternion_wxyz'])
    return dict(case=data['case']['name'],guard_events=data['events'],
        max_rotation_deg=math.degrees(data['guard_facts']['max_rotation_from_start_rad']),
        final_angle_deg=math.degrees(2*math.acos(min(1.,abs(q[0])/np.linalg.norm(q)))),
        final_z_mm=final['position_m'][2]*1000,observed_INSERT_stall_triggers=triggers,
        eligible_window_count=len(eligible),min_eligible_window_advance_um=min(e['window_advance_um'] for e in eligible),
        stall_advance_threshold_um=config['stall_advance_m']*1e6,last_eligible_window=eligible[-1],
        source_sha256=source_hash,analysis_dynamic_calls=0)


def main():
    ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf-8'))
    config=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'))
    assert ledger['status'] in ('complete','controlled_stop','error')
    rows=[]
    for entry in ledger['episodes']:
        if entry['status']!='finished':
            rows.append(entry);continue
        path=OUT/'run'/(entry['id']+'.json.gz')
        raw=path.read_bytes();assert hashlib.sha256(raw).hexdigest()==entry['archive_sha256']
        data=json.loads(gzip.decompress(raw));trace=data['trace'];last=trace[-1]
        if entry['id']=='y_pos_150':
            diagnosis=diagnose_stall(data,config['b2_config'],entry['archive_sha256'])
            (OUT/'guard_diagnosis.json').write_text(json.dumps(diagnosis,ensure_ascii=False,indent=2),encoding='utf-8')
        xy=float(np.linalg.norm(last['position_m'][:2])*1e6)
        assert abs(xy-entry['xy_um'])<1e-8
        assert len(trace)-1==entry['control_cycles']
        assert data['case']['name']==entry['id']
        stopped=actual_stop_pass(data['stop_samples'],data['events'],entry['stop_time'],entry['end_time'],.0002)
        stopped=stopped and physical_tail_pass(data['stop_samples'],entry['end_time'],.0002)
        assert stopped==entry['outcome']['physical_stopped']
        assert entry['physical_substeps']==entry['control_cycles']*10
        hold_start=None;hold_pass=False;functional_start=None;functional_hold=False
        # Exploratory task-definition check only: old official labels remain.
        functional_criteria={**finish_criteria(),'xy_tolerance_m':1.,'angle_tolerance_rad':math.pi}
        target_events=[r['time_s'] for r in data['events'] if r['reason']=='TARGET_PLANE_REACHED']
        start=target_events[0] if target_events else math.inf
        for r in trace:
            if r['time_s']<start-1e-12 or r['time_s']>entry['task_end_time']+1e-9:continue
            if geometric_finish(r,criteria=finish_criteria()) and pin_fit(r):
                if hold_start is None:hold_start=r['time_s']
                if r['time_s']-hold_start>=.1-1e-12:hold_pass=True
            else:hold_start=None
            if geometric_finish(r,criteria=functional_criteria) and pin_fit(r):
                if functional_start is None:functional_start=r['time_s']
                if r['time_s']-functional_start>=.1-1e-12:functional_hold=True
            else:functional_start=None
        success=entry['outcome']['task_outcome']=='FULL_SUCCESS'
        if success:assert stopped and hold_pass and not data['guard_facts']['contact_reasons'] and not data['guard_facts']['motion_reasons']
        contact_cycles=sum(r['contact_count']>0 for r in trace[1:]);search_cycles=sum(r['policy_phase']=='SEARCH' for r in trace[1:])
        assert contact_cycles==entry['contact_cycles'] and search_cycles==entry['search_cycles']
        q=np.array(last['quaternion_wxyz']);angle=math.degrees(2*math.acos(min(1.,abs(q[0])/np.linalg.norm(q))))
        gates=[]
        if xy>80:gates.append('XY>80um')
        if angle>.5:gates.append('angle>0.5deg')
        if abs(last['position_m'][2])>20e-6:gates.append('depth')
        if not pin_fit(last):gates.append('pin_fit')
        functional_screen=bool(functional_hold and stopped and entry['outcome']['simulation_valid'] and
            not data['guard_facts']['contact_reasons'] and not data['guard_facts']['motion_reasons'])
        rows.append(dict(id=entry['id'],success=success,reason=entry['reason'],xy_um=xy,angle_deg=angle,
            final_failed_pose_gates=gates,functional_pose_screen_only=functional_screen,
            force_peak_N=entry['peaks']['force_N'],penetration_peak_um=entry['peaks']['penetration_m']*1e6,
            pin_clearance_um=pin_clearance_m(last)*1e6,contact_cycles=contact_cycles,search_cycles=search_cycles,
            task_end_time=entry['task_end_time'],end_time=entry['end_time'],physical_stopped=stopped,
            simulation_valid=entry['outcome']['simulation_valid'],hold_pass=hold_pass,
            control_cycles=entry['control_cycles'],physical_substeps=entry['physical_substeps'],archive_sha256=entry['archive_sha256']))
    checked=dict(status=ledger['status'],rows=rows,completed=sum(e['status']=='finished' for e in ledger['episodes']),
        attempted=len(ledger['episodes']),unused_closed=9-len(ledger['episodes']),cumulative_attempts=109+len(ledger['episodes']),
        control_cycles=sum(e.get('control_cycles',0) for e in ledger['episodes']),
        physical_substeps=sum(e.get('physical_substeps',0) for e in ledger['episodes']),
        successful=sum(r.get('success',False) for r in rows),training_updates=0,policy_calls=0,
        reduction_dynamic_calls=0,peak_source='Saved substep-aggregated environment peaks; no separate substep force trace',
        all_recorded_inputs_unchanged=ledger.get('inputs_unchanged'),independent_test=False)
    pairs=[]
    for axis in ('x','y'):
        paths=[OUT/'run'/f'{axis}_{sign}_100.json.gz' for sign in ('pos','neg')]
        if not all(p.exists() for p in paths):continue
        pair=[json.loads(gzip.decompress(p.read_bytes())) for p in paths]
        if not all(p['status']=='finished' for p in pair):continue
        sensed=[]
        for run in pair:
            initial=np.array(run['trace'][0]['position_m'])
            sensed.append(np.array([r['contact_wrench_M']+list(np.array(r['position_m'])-initial)+r['quaternion_wxyz']+
                r['velocity_world']+r['limited_command_world'] for r in run['trace']]))
        pairs.append(dict(axis=axis,rows=[len(x) for x in sensed],
            max_sensed_command_difference=float(np.max(np.abs(sensed[0]-sensed[1]))) if sensed[0].shape==sensed[1].shape else None,
            source_sha256=[hashlib.sha256(p.read_bytes()).hexdigest() for p in paths]))
    checked['opposite_100um_observation_comparison']=pairs
    (OUT/'assessment.json').write_text(json.dumps(checked,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# 新任务纯B2开发预检结果','','结论与下一步见[诊断与下一步](诊断与下一步.md)：功能配合与额外精度标准不一致，以及正Y150孔口旋转保护；本轮不进入训练。','',f"实际启动{checked['attempted']}/9，完成{checked['completed']}；成功{checked['successful']}。训练0、策略网络0、独立测试0。",'',
        '孔径1.20 mm，XY阈值80 μm；九针保守配合、原姿态/深度/载荷/穿透与真实停稳共同裁决。旧失败未改判。','',
        '| 工况 | 成功 | XY μm | 角度 ° | 峰值力 N | 最小针孔余量 μm | 接触周期 | SEARCH周期 | 原因 |','|---|---|---:|---:|---:|---:|---:|---:|---|']
    for r in rows:
        if 'success' not in r:
            lines.append(f"| {r['id']} | 运行错误 | — | — | — | — | — | {r.get('error')} |");continue
        lines.append(f"| {r['id']} | {'是' if r['success'] else '否'} | {r['xy_um']:.3f} | {r['angle_deg']:.3f} | {r['force_peak_N']:.9f} | {r['pin_clearance_um']:.3f} | {r['contact_cycles']} | {r['search_cycles']} | {r['reason']} |")
    lines+=['',f"控制周期{checked['control_cycles']}、物理子步{checked['physical_substeps']}；新增累计{checked['cumulative_attempts']}。未用{checked['unused_closed']}回合关闭，不结转。",'',
        '以上是预登记开发点及纯B2结果，不能作为候选学习收益或正式成功率推断。峰值力来自运行时物理子步累计值；本次离线复核独立重算档案哈希、末端XY、接触/SEARCH周期、几何保持及物理停稳，未重建子步力。','',
        'assessment.json另列functional_pose_screen_only：仅作为下一任务定义的开发筛查，核对深度、九针配合、载荷、连续保持与真实停稳，不再额外要求80 μm和0.5°。它不是本轮成功标签，不追改既有结果，不构成新的动态评价或方法收益。','',
        '![开发结果](results.png)','']
    (OUT/'结果说明.md').write_text('\n'.join(lines),encoding='utf-8')
    valid=[r for r in rows if 'success' in r]
    if valid:
        import matplotlib
        matplotlib.use('Agg')
        from matplotlib import pyplot as plt
        fig,axes=plt.subplots(2,1,figsize=(10,7),layout='constrained')
        names=[r['id'] for r in valid]
        colors=['#238b45' if r['success'] else '#cf4446' for r in valid]
        axes[0].bar(names,[r['xy_um'] for r in valid],color=colors)
        axes[0].axhline(80,color='black',linestyle='--',label='XY criterion 80 um')
        axes[0].set_ylabel('Final XY error (um)');axes[0].legend()
        axes[1].bar(names,[r['force_peak_N']*1000 for r in valid],color=colors)
        axes[1].axhline(25,color='black',linestyle='--',label='Force guard 25 mN')
        axes[1].set_ylabel('Recorded substep peak force (mN)');axes[1].legend()
        for ax in axes:ax.tick_params(axis='x',rotation=25)
        fig.suptitle('B2 development preflight: bore 1.20 mm / XY 80 um (no learning)')
        fig.savefig(OUT/'results.png',dpi=180);fig.savefig(OUT/'results.pdf');plt.close(fig)
    print(json.dumps({k:v for k,v in checked.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__':main()
