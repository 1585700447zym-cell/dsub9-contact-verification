"""Read saved G0/G1 evidence; never import an environment, model or learner.

Run only after the launcher has exited. All writes go to a new derived folder.
Geometry describes centerline entry necessity and axial occupancy, not success.
"""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'deliverables/learning_chain/global_residual_authority_20261028'
PULSES = (('+yaw', 4, 1), ('-yaw', 4, -1), ('+X', 0, 1),
          ('-X', 0, -1), ('+Y', 1, 1), ('-Y', 1, -1))
COMMAND_AXES = ['X', 'Y', 'Z', 'roll', 'pitch', 'yaw']


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def rotations(quaternions):
    """Same wxyz rotation convention as analyze_paired_entropy_failure.rotations.

    Kept here to avoid that module's imports of runtime-selection helpers.
    """
    q = np.asarray(quaternions, dtype=float)
    q = q / np.linalg.norm(q, axis=1)[:, None]
    w, x, y, z = q.T
    return np.stack((1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w),
                     2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w),
                     2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)), axis=1).reshape(-1, 3, 3)


def read_pin_geometry(path=None):
    path = Path(path or ROOT / 'models/dsub9_pair.xml')
    source = ET.parse(path).getroot()
    pins = source.findall('.//geom[@class="pin_collision"]')
    centers = np.array([[float(v) for v in g.get('pos').split()] for g in pins])
    sizes = np.array([[float(v) for v in g.get('size').split()] for g in pins])
    if centers.shape != (9, 3) or sizes.shape != (9, 2):
        raise ValueError('Nine cylinder pins required in source XML')
    parameters = {x.get('key'): float(x.get('value')) for x in source.findall('.//extension/plugin/instance/config')}
    return dict(centers=centers, sizes=sizes, entry_radius=parameters['entry_radius'],
                entry_depth=parameters['entry_depth'], bore_depth=parameters['bore_depth'],
                source_path=str(path), source_sha256=sha(path))


def finite_pose(row):
    try:
        p, q = np.asarray(row['position_m'], float), np.asarray(row['quaternion_wxyz'], float)
        return (p.shape == (3,) and q.shape == (4,) and np.isfinite(np.r_[p, q, row['time_s']]).all()
                and np.linalg.norm(q) > 0 and rotations([q])[0, 2, 2] >= .99)
    except (KeyError, TypeError, ValueError):
        return False


def geometry_snapshot(row, geometry):
    if not finite_pose(row):
        return None
    rotation = rotations([row['quaternion_wxyz']])[0]
    axis = rotation[:, 2]
    pins, sizes = geometry['centers'], geometry['sizes']
    centers = pins @ rotation.T + row['position_m']
    tips = centers + axis * sizes[:, 1, None]
    rim = sizes[:, 0] * np.sqrt(max(0., 1-axis[2]**2))
    zhi = tips[:, 2] + rim
    zlo = centers[:, 2] - axis[2] * sizes[:, 1] - rim
    mouth = centers[:, :2] - centers[:, 2, None] / axis[2] * axis[:2]
    errors = np.linalg.norm(mouth-pins[:, :2], axis=1)
    necessary_margin = geometry['entry_radius'] - sizes[:, 0] - errors
    main_overlap = (zhi > geometry['entry_depth'] + 1e-9) & (zlo < geometry['bore_depth'] - 1e-9)
    rpy = [math.atan2(rotation[2, 1], rotation[2, 2]),
           math.asin(float(np.clip(-rotation[2, 0], -1, 1))),
           math.atan2(rotation[1, 0], rotation[0, 0])]
    return dict(time_s=float(row['time_s']), position_m=list(row['position_m']),
        rpy_deg=np.degrees(rpy).tolist(),
        maximum_mouth_centerline_error_um=float(errors.max()*1e6),
        all_nine_entry_centerline_necessary_condition=bool(np.all(necessary_margin >= -1e-9)),
        main_plane_overlap_pin_count=int(main_overlap.sum()),
        pins=[dict(pin=i+1, mouth_centerline_error_um=float(errors[i]*1e6),
                   entry_centerline_clearance_um=float(necessary_margin[i]*1e6),
                   entry_centerline_necessary_condition=bool(necessary_margin[i] >= -1e-9),
                   axis_tip_z_um=float(tips[i, 2]*1e6), rim_top_z_um=float(zhi[i]*1e6),
                   main_plane_overlap=bool(main_overlap[i])) for i in range(9)])


def vector(value, size):
    try:
        a = np.asarray(value, float)
        return a if a.shape == (size,) and np.isfinite(a).all() else None
    except (ValueError, TypeError):
        return None


def _first_search_time(raw):
    trace = raw.get('trace', [])
    state = raw.get('global_residual', {}).get('script_final', {})
    cycle = state.get('first_search_cycle')
    if isinstance(cycle, int) and 0 <= cycle < len(trace):
        return float(trace[cycle]['time_s'])
    for event in raw.get('evidence', {}).get('controller_events') or []:
        if event.get('reason') == 'LOW_LOAD_SEARCH':
            return float(event['time_s'])
    for i, row in enumerate(raw.get('transitions', [])):
        if row.get('action_log', {}).get('composition_inputs', {}).get('phase') == 'SEARCH' and i < len(trace):
            return float(trace[i]['time_s'])
    return None


def _command_metrics(selected, trace):
    fields = {'physical_request': lambda log: log.get('requested_residual'),
        'applied_residual': lambda log: log.get('applied_residual'),
        'baseline': lambda log: log.get('composition_inputs', {}).get('base_command'),
        'pre_stage_total': lambda log: log.get('pre_stage_total'),
        'stage_before_disk': lambda log: log.get('unfiltered_stage_limited_total'),
        'stage_after_disk': lambda log: log.get('stage_limited_total'),
        'predicted_drive': lambda log: log.get('predicted_limited_command'),
        'auxiliary_command_delta': lambda log: log.get('effective_command_delta')}
    integrals = {name: np.zeros(6) for name in fields}
    observed = {name: 0. for name in fields}
    stage_duration, drive_duration, reference_duration = np.zeros(6), np.zeros(6), np.zeros(6)
    final_integral = np.zeros(6); final_duration = 0.; filter_duration = 0.
    for index, row, dt in selected:
        log = row.get('action_log', {})
        for name, get in fields.items():
            value = vector(get(log), 6)
            if value is not None:
                integrals[name] += value*dt
                observed[name] += dt
        stage = vector(log.get('stage_clip_delta'), 6)
        drive = vector(log.get('drive_clip_delta'), 6)
        if stage is not None:
            stage_duration += (abs(stage) > 1e-12)*dt
        if drive is not None:
            drive_duration += (abs(drive) > 1e-12)*dt
        before = vector(log.get('unfiltered_stage_limited_total'), 6)
        after = vector(log.get('stage_limited_total'), 6)
        if log.get('reference_filter_fraction', 1.) < 1-1e-10:
            filter_duration += dt
            if before is not None and after is not None and drive is not None:
                # Compare to the unfiltered drive, excluding ordinary drive
                # clipping already counted above from the disk contribution.
                reference_duration += (abs(before-drive-after) > 1e-12)*dt
        final = vector(trace[index+1].get('limited_command_world'), 6)
        if final is not None:
            final_integral += final*dt
            final_duration += dt
    result = {name+'_integral': integrals[name].tolist() if observed[name] else None for name in fields}
    result.update(field_observed_duration_s=observed,
        final_drive_integral=final_integral.tolist() if final_duration else None,
        final_drive_observed_duration_s=final_duration, stage_clip_duration_s=stage_duration.tolist(),
        drive_clip_duration_s=drive_duration.tolist(), reference_filter_duration_s=filter_duration,
        reference_changed_axis_duration_s=reference_duration.tolist())
    return result


def _motion_metrics(selected, trace, cycle_peaks):
    first, last = selected[0][0], selected[-1][0]+1
    window = trace[first:last+1]
    good = [row for row in window if finite_pose(row)]
    result = dict(start_time_s=trace[first]['time_s'], end_time_s=trace[last]['time_s'],
                  displacement_xy_um=None, yaw_change_deg=None)
    if finite_pose(trace[first]) and finite_pose(trace[last]):
        rotation = rotations([trace[first]['quaternion_wxyz'], trace[last]['quaternion_wxyz']])
        yaw = np.unwrap(np.arctan2(rotation[:, 1, 0], rotation[:, 0, 0]))
        result.update(displacement_xy_um=((np.array(trace[last]['position_m'])[:2]-trace[first]['position_m'][:2])*1e6).tolist(),
                      yaw_change_deg=float(np.degrees(yaw[1]-yaw[0])))
    for field, size in (('velocity_world', 6), ('contact_wrench_M', 6), ('drive_wrench_M', 6)):
        values = [vector(row.get(field), size) for row in window]
        values = np.array([v for v in values if v is not None])
        result[field+'_peak_absolute'] = abs(values).max(0).tolist() if len(values) else None
        if field == 'contact_wrench_M' and len(values):
            result.update(control_sample_peak_force_N=float(np.linalg.norm(values[:, :3], axis=1).max()),
                          control_sample_peak_torque_M_Nm=float(np.linalg.norm(values[:, 3:], axis=1).max()))
    native = [cycle_peaks[i] for i, _, _ in selected if i < len(cycle_peaks)]
    for output, source in (('peak_force_N', 'force_N'), ('peak_torque_Nm', 'torque_G_Nm')):
        values = [row.get(source) for row in native]
        values = [v for v in values if isinstance(v, (float, int)) and math.isfinite(v)]
        result[output] = max(values) if values else None
    result['load_peak_source'] = 'cycle_peaks: per-physics-substep force_N and torque_G_Nm maxima'
    result['native_peak_cycles_observed'] = len(native)
    leads, angle_errors = [], []
    for row in good:
        ref = vector(row.get('reference_qpos'), 7)
        if ref is not None:
            leads.append(ref[:3]-row['position_m'])
            if np.linalg.norm(ref[3:]) > 0:
                matrices = rotations([ref[3:], row['quaternion_wxyz']])
                angle_errors.append(math.acos(float(np.clip((np.trace(matrices[0].T@matrices[1])-1)/2, -1, 1))))
    result['maximum_reference_position_error_um'] = (abs(np.array(leads)).max(0)*1e6).tolist() if leads else None
    result['maximum_reference_rotation_error_deg'] = math.degrees(max(angle_errors)) if angle_errors else None
    return result


def analyze_episode(raw, *, geometry, receipt=None):
    receipt = receipt or {}
    trace, transitions = raw.get('trace') or [], raw.get('transitions') or []
    evidence = raw.get('evidence') or {}
    stop = evidence.get('stop_time_s')
    if stop is None:
        stop = receipt.get('stop_time_s')
    usable = [r for r in trace if finite_pose(r)]
    task = [r for r in usable if stop is None or r['time_s'] <= stop+1e-8]
    result = dict(profile=raw.get('global_residual', {}).get('profile', receipt.get('profile')),
        outcome=raw.get('outcome', receipt.get('outcome', {})), final_reason=receipt.get('final_reason'),
        diagnostic_status='no_trace' if not trace else 'complete_trace' if len(usable) == len(trace) else 'partial_trace',
        trace_rows=len(trace), trace_rows_rejected=len(trace)-len(usable), transition_rows=len(transitions),
        control_stop_time_s=stop, settle_end_time_s=evidence.get('task_end_time_s', receipt.get('task_time_s')),
        audit_end_time_s=evidence.get('audit_end_time_s', receipt.get('audit_end_time_s')),
        guard_facts=evidence.get('guard_facts', receipt.get('guard_facts', {})),
        controller_events=evidence.get('controller_events') or [],
        environment_events=evidence.get('environment_events') or [],
        script_final=raw.get('global_residual', {}).get('script_final', receipt.get('script', {})),
        snapshots={'at_25s': None, 'task_stop': None}, pulses=[], unexpected_action_rows=[],
        new_initializations=0, new_physical_substeps=0, new_neural_inference=0, new_optimizer_updates=0)
    def at(target):
        return next((geometry_snapshot(r, geometry) for r in task if abs(r['time_s']-target) < 1e-7), None)
    if stop is not None:
        if stop >= 25.-1e-8:
            result['snapshots']['at_25s'] = at(25.)
        result['snapshots']['task_stop'] = at(stop)
    if task:
        positions = np.array([r['position_m'] for r in task])
        result.update(maximum_advance_mm=float((positions[:, 2].max()-positions[0, 2])*1000),
                      final_recorded_advance_mm=float((positions[-1, 2]-positions[0, 2])*1000),
                      last_recorded_task_time_s=task[-1]['time_s'])
    start = _first_search_time(raw)
    result['first_search_time_s'] = start
    selected = [[] for _ in PULSES]
    rows = []
    for i, row in enumerate(transitions[:max(0, len(trace)-1)]):
        t = trace[i].get('time_s'); dt = row.get('dt')
        if not isinstance(t, (float, int)) or not isinstance(dt, (float, int)) or not math.isfinite(t+dt) or dt <= 0:
            continue
        if stop is not None and t >= stop-1e-8:
            continue
        rows.append((i, row, dt))
        action = vector(row.get('action_log', {}).get('raw_action', row.get('action')), 5)
        if action is None:
            result['unexpected_action_rows'].append(dict(index=i, reason='missing_or_invalid_action'))
            continue
        active_axes = np.flatnonzero(abs(action) > 1e-9)
        if not len(active_axes):
            continue
        matched = False
        if len(active_axes) == 1 and start is not None:
            axis = int(active_axes[0])
            for j, (_, expected_axis, sign) in enumerate(PULSES):
                pstart = start+.2+j*1.2
                if axis == expected_axis and action[axis]*sign > 0 and pstart-1e-8 <= t < pstart+1.-1e-8:
                    selected[j].append((i, row, dt)); matched = True; break
        if not matched or row.get('action_active') is not True:
            result['unexpected_action_rows'].append(dict(index=i, time_s=t, reason='outside_script_or_permission', action=action.tolist()))
    for j, (name, axis, sign) in enumerate(PULSES):
        pstart = None if start is None else start+.2+j*1.2
        part = selected[j]
        pulse = dict(name=name, normalized_axis=axis, sign=sign, expected_start_s=pstart,
                     expected_end_s=None if pstart is None else pstart+1., status='not_covered',
                     observed_nonzero_cycles=len(part), observed_nonzero_duration_s=sum(x[2] for x in part))
        if part:
            expected_rows = [(i, r, dt) for i, r, dt in rows if pstart-1e-8 <= trace[i]['time_s'] < pstart+1.-1e-8]
            uninterrupted = all(r.get('action_active') is True and r.get('action_log', {}).get('composition_inputs', {}).get('phase') == 'SEARCH' for _, r, _ in expected_rows)
            reached = any(trace[i+1]['time_s'] >= pstart+1.-1e-8 for i, _, _ in expected_rows)
            waveform_valid = True
            for i, row, _ in expected_rows:
                elapsed = trace[i]['time_s']-pstart
                wanted = np.zeros(5)
                wanted[axis] = sign*max(0., min(elapsed/.2, 1., (1.-elapsed)/.2))
                actual = vector(row.get('action_log', {}).get('raw_action', row.get('action')), 5)
                if actual is None or not np.allclose(actual, wanted, rtol=0., atol=1e-7):
                    waveform_valid = False
            full_duration = sum(dt for _, _, dt in expected_rows) >= 1.-1e-7
            pulse.update(status='completed' if uninterrupted and reached and waveform_valid and full_duration else 'interrupted',
                script_waveform_valid=waveform_valid,
                normalized_request_integral_s=float(sum(vector(r.get('action_log', {}).get('raw_action', r.get('action')), 5)[axis]*dt for _, r, dt in part)),
                command=_command_metrics(part, trace), motion=_motion_metrics(part, trace, raw.get('cycle_peaks') or []))
            lo, hi = trace[part[0][0]]['time_s'], trace[part[-1][0]+1]['time_s']
            pulse['events'] = [dict(e, source=source) for source in ('controller_events', 'environment_events')
                               for e in result[source] if lo-1e-8 <= e.get('time_s', -math.inf) <= hi+1e-8]
        result['pulses'].append(pulse)
    result['interface_recording_valid'] = (bool(trace) and len(trace) == len(transitions)+1 and
        not result['unexpected_action_rows'] and all(
            all(duration >= p['observed_nonzero_duration_s']-1e-8
                for duration in p['command']['field_observed_duration_s'].values())
            and p['command']['final_drive_observed_duration_s'] >= p['observed_nonzero_duration_s']-1e-8
            and p['script_waveform_valid']
            for p in result['pulses'] if p['status'] != 'not_covered'))
    return result


def read_verified_archive(folder):
    folder = Path(folder)
    receipt = read(folder / 'receipt.json')
    archive = folder / 'episode.json.gz'
    digest = sha(archive)
    if digest != receipt.get('archive_sha256'):
        raise ValueError('Archive hash differs from receipt: '+str(archive))
    if (folder / 'audit.json').exists():
        audit = read(folder / 'audit.json')
        if audit.get('archive_sha256') not in (None, digest):
            raise ValueError('Archive hash differs from audit: '+str(archive))
    return json.loads(gzip.decompress(archive.read_bytes())), receipt, digest


def render_report(summary):
    lines = ['# 全局残差权限与30秒共同限时：保存轨迹结果', '',
        '本报告只读取已保存证据，新增初始化、物理子步、神经推理及优化更新均为0。', '',
        '仅比较同初始yaw工况的G0/G1残差权限组合；固定正负脉冲次序不能隔离方向因果。'
        '命令辅助差分不代表残差单独造成的真实运动，不据此选择训练参数或声称SAC收益。', '',
        '25秒截面仅在任务仍运行且有该时刻记录时报告；不足25秒不以终点替代。'
        '任务停止时刻与其后的停稳/审核分别列出。逐针中心线≤175 μm只是入口必要条件；'
        '针缘超过250 μm只表示与主孔层轴向重叠，不能据此认定孔内配合或完整成功。', '',
        '逐脉冲峰值力/力矩来自对应cycle_peaks中物理子步的最大值（力矩为G点口径）；'
        '控制采样载荷另存为control_sample_peak字段，M点控制采样力矩不与G点峰值混同。', '',
        f"批次状态：{summary['batch_status']}；台账实际记录{len(summary['episodes'])}个尝试；未运行点不补记失败。", '',
        '实际成本与计数精度取自原台账：', '', '```json',
        json.dumps(summary['costs'], ensure_ascii=False, indent=2), '```', '']
    def fmt(value, digits=4):
        if value is None:
            return '未记录'
        if isinstance(value, list):
            return '['+', '.join(fmt(v, digits) for v in value)+']'
        if isinstance(value, (float, int)):
            return f'{value:.{digits}g}'
        return str(value)
    for job, result in summary['episodes'].items():
        lines += [f'## {job}', '', f"诊断状态：{result['diagnostic_status']}；接口记录有效：{result.get('interface_recording_valid', False)}。",
            f"原裁决：{fmt(result.get('outcome'))}；任务停止={fmt(result.get('control_stop_time_s'))} s，"
            f"停稳结束={fmt(result.get('settle_end_time_s'))} s，审核结束={fmt(result.get('audit_end_time_s'))} s。",
            f"保护事实：{fmt(result.get('guard_facts'))}。脚本终态：{fmt(result.get('script_final'))}。", '',
            '|脉冲|覆盖|非零时长s|归一化积分s|物理请求积分(μm/deg)|实际ΔX/ΔY μm|实际Δyaw °|物理子步峰值力N/G点力矩N·m|参考误差XYZ μm|',
            '|---|---|---|---|---|---|---|---|---|']
        for pulse in result['pulses']:
            cmd, motion = pulse.get('command', {}), pulse.get('motion', {})
            axis = {0: 0, 1: 1, 4: 5}[pulse['normalized_axis']]
            request = cmd.get('physical_request_integral')
            request = None if request is None else request[axis]*(1e6 if axis < 3 else 180/math.pi)
            lines.append('|'+ '|'.join([pulse['name'], pulse['status'], fmt(pulse['observed_nonzero_duration_s']),
                fmt(pulse.get('normalized_request_integral_s')), fmt(request), fmt(motion.get('displacement_xy_um')),
                fmt(motion.get('yaw_change_deg')), fmt([motion.get('peak_force_N'), motion.get('peak_torque_Nm')]),
                fmt(motion.get('maximum_reference_position_error_um'))])+'|')
        lines += ['', '各轴命令积分单位为m/rad；时长向量轴序为X、Y、Z、roll、pitch、yaw。', '',
            '|脉冲|基线积分|限幅前合成积分|阶段/盘后积分|最终驱动积分|阶段限幅时长s|驱动限幅时长s|盘过滤时长s|',
            '|---|---|---|---|---|---|---|---|']
        for pulse in result['pulses']:
            c = pulse.get('command', {})
            lines.append('|'+ '|'.join([pulse['name']]+[fmt(c.get(k)) for k in (
                'baseline_integral', 'pre_stage_total_integral', 'stage_after_disk_integral',
                'final_drive_integral', 'stage_clip_duration_s', 'drive_clip_duration_s', 'reference_filter_duration_s')])+'|')
        lines += ['', f"最大推进={fmt(result.get('maximum_advance_mm'))} mm；末条任务记录推进={fmt(result.get('final_recorded_advance_mm'))} mm。", '']
        for label, snap in result['snapshots'].items():
            if snap is None:
                lines += [f'{label}：未达到该时刻或无有效记录。', '']; continue
            lines += [f"{label}：t={fmt(snap['time_s'])} s，XYZ={fmt(snap['position_m'])} m，RPY={fmt(snap['rpy_deg'])}°。", '',
                '|针|入口中心线误差 μm|入口必要余量 μm|针缘最高Z μm|主孔层轴向重叠|', '|---|---|---|---|---|']
            for pin in snap['pins']:
                lines.append('|'+ '|'.join(fmt(pin[k]) for k in ('pin', 'mouth_centerline_error_um',
                    'entry_centerline_clearance_um', 'rim_top_z_um', 'main_plane_overlap'))+'|')
            lines.append('')
        lines += ['阶段及保护事件：', '', '```json', json.dumps(dict(controller=result.get('controller_events'),
            environment=result.get('environment_events')), ensure_ascii=False, indent=2), '```', '']
    lines += ['全部逐脉冲载荷、速度、参考角误差、命令链和输入哈希见summary.json。', '']
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', type=Path, default=OUT)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    batch = args.batch.resolve(); output = (args.output or batch / 'analysis').resolve()
    if output.exists():
        raise FileExistsError('Use a new derived output directory: '+str(output))
    proof = read(batch / 'process_exit.json')
    if not proof.get('process_exit_confirmed'):
        raise RuntimeError('Wait for confirmed launcher exit before analysis')
    reg, ledger = read(batch / 'registration.json'), read(batch / 'ledger.json')
    pins = {str((batch / name).relative_to(ROOT)): sha(batch / name)
            for name in ('process_exit.json', 'registration.json', 'ledger.json')}
    # Verify frozen inputs without importing the runner or selecting a runtime.
    for name, digest in reg.get('inputs', {}).items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or sha(path) != digest:
            raise ValueError('Frozen input hash differs: '+name)
    geometry = read_pin_geometry()
    episodes = {}
    for record in ledger.get('episodes', []):
        case_id = record['case_id']
        if Path(case_id).name != case_id:
            raise ValueError('Unsafe episode ID')
        folder = batch / 'run' / case_id
        supervisor = read(folder / 'supervisor.json') if (folder / 'supervisor.json').exists() else {}
        if supervisor.get('started') and not supervisor.get('process_exit_confirmed'):
            raise RuntimeError('Worker exit is not confirmed: '+case_id)
        if (folder / 'episode.json.gz').exists():
            raw, receipt, digest = read_verified_archive(folder)
            result = analyze_episode(raw, geometry=geometry, receipt=receipt)
            pins[str((folder / 'episode.json.gz').relative_to(ROOT))] = digest
        else:
            result = analyze_episode({}, geometry=geometry, receipt=record)
            result['missing_archive'] = True
        for name in ('receipt.json', 'audit.json', 'supervisor.json'):
            if (folder / name).exists():
                pins[str((folder / name).relative_to(ROOT))] = sha(folder / name)
        episodes[case_id] = result
    costs = {key: value for key, value in ledger.items() if key not in ('episodes', 'registration_sha256')}
    summary = dict(version='global_residual_saved_trace_analysis_v1', batch_status=ledger.get('status'),
        launcher_exit_code=proof.get('returncode', proof.get('exit_code')), costs=costs, episodes=episodes,
        planned_but_not_recorded=[job['id'] for job in reg.get('schedule', []) if job['id'] not in episodes],
        command_axis_order=COMMAND_AXES, input_sha256=pins,
        geometry=dict(source=geometry['source_path'], source_sha256=geometry['source_sha256'],
            entry_necessary_centerline_limit_um=175., main_layer_start_um=geometry['entry_depth']*1e6,
            meaning='Centerline necessity and axial overlap only; neither is a fit/success verdict'),
        new_initializations=0, new_physical_substeps=0, new_neural_inference=0, new_optimizer_updates=0,
        limits='Four engineering script attempts do not establish SAC benefit, success-rate change, or axis-specific causality')
    # Refuse nonfinite derived values instead of silently publishing NaN JSON.
    payload = json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False)
    output.mkdir(parents=True)
    (output / 'summary.json').write_text(payload, encoding='utf-8')
    (output / '结果.md').write_text(render_report(summary), encoding='utf-8')
    print(json.dumps(dict(output=str(output), recorded_attempts=len(episodes), new_physical_substeps=0), ensure_ascii=False))


if __name__ == '__main__':
    main()
