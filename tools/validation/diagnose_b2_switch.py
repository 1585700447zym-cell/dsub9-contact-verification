"""Read preserved B2 records; reconstruct commands, never advance dynamics."""
import argparse
import json
import math
from pathlib import Path

import numpy as np
from matplotlib import pyplot as plt

from tools.control.search_recovery import Observation, SearchConfig, SearchRecovery
from tools.control.search_exit_v2 import ExitGateConfig, SearchRecoveryV2
from tools.dynamics.safety import limit_command
from tools.reporting.report_b2_exit_gate import collect, configure_font
from tools.validation.run_b1_baseline import dump
from tools.validation.run_b2_exit_gate import sha
from tools.validation.run_contact_cases import ROOT


TAGS = ('verified_frozen_x100', 'verified_frozen_y100')
OUT = ROOT / 'deliverables/b2_switch_diagnosis'


def at(run, time):
    row = min(run['trace'], key=lambda s: abs(s['time_s']-time))
    assert abs(row['time_s']-time) < 1e-8
    return row


def reconstruct(run, check, version):
    """Logged row is post-step: its state generates the NEXT row's command."""
    i = check['identical_trace_prefix_samples']-1
    row, following = run['trace'][i:i+2]
    event = next(e for e in run['policy_events'] if e['reason'] == 'LOW_LOAD_SEARCH'
                 and e['time_s'] > 9.2)
    origin = np.array(run['trace'][0]['position_m'])
    c = SearchConfig(**run['controller']['config'])
    controller = (SearchRecovery(c) if version == 'old' else
                  SearchRecoveryV2(c, ExitGateConfig(**run['controller']['exit_gate'])))
    controller.phase = 'SEARCH'
    controller.phase_start = event['time_s']
    controller.search_count = 2
    controller.search_origin = np.array(at(run, event['time_s'])['position_m'])-origin
    controller.theta = row['spiral_theta_rad']
    controller.admittance.velocity = np.array(row['admittance_velocity'])
    controller.admittance.offset = np.array(row['commanded_correction'])
    if version == 'new':
        controller.recovered_search = True
        controller.blocked_z_m = check['new_recovery_progress']['blocked_z_m']
    env = run['environment']['config']
    dt = env['control_period']
    obs = Observation(row['time_s'], tuple(np.array(row['position_m'])-origin),
                      tuple(row['contact_wrench_M']))
    command = controller.command(obs, dt)
    limited = limit_command(command, row['limited_command_world'], dt,
                            [env['linear_speed']]*3+[env['angular_speed']]*3,
                            [env['linear_acceleration']]*3+[env['angular_acceleration']]*3)
    np.testing.assert_allclose(command, following['raw_command_world'], rtol=0, atol=1e-14)
    np.testing.assert_allclose(limited, following['limited_command_world'], rtol=0, atol=1e-14)
    assert controller.phase == following['policy_phase']
    return {'raw_command_world': command.tolist(), 'limited_command_world': limited.tolist(),
            'phase': controller.phase, 'reconstruction_max_error': float(max(
                np.max(np.abs(command-following['raw_command_world'])),
                np.max(np.abs(limited-following['limited_command_world']))))}


def window(run, fork, duration):
    rows = [s for s in run['trace'] if fork-1e-8 <= s['time_s'] <= fork+duration+1e-8]
    assert abs(rows[-1]['time_s']-rows[0]['time_s']-duration) < 1e-8
    assert all(s['phase'] == 'RUNNING' for s in rows)
    p = np.array([s['position_m'] for s in rows])
    return {'duration_s': duration, 'advance_um': float((p[-1, 2]-p[0, 2])*1e6),
            'xy_path_um': float(np.linalg.norm(np.diff(p[:, :2], axis=0), axis=1).sum()*1e6),
            'endpoint_advance_mm': float((p[-1, 2]-run['case']['start_origin_z_m'])*1000)}


def search_law(run, check):
    c = run['controller']['config']
    rows = run['trace']
    pairs = [(a, b) for a, b in zip(rows, rows[1:])
             if a['time_s'] >= check['identical_through_s']-1e-8
             and b['policy_phase'] == 'SEARCH' and b['phase'] == 'RUNNING']
    predicted = np.array([np.clip(c['axial_gain_m_s_N']*(c['search_force_N']+a['contact_wrench_M'][2]),
                                  -c['unload_speed_m_s'], c['search_forward_speed_m_s']) for a, _ in pairs])
    recorded = np.array([b['raw_command_world'][2] for _, b in pairs])
    np.testing.assert_allclose(predicted, recorded, rtol=0, atol=1e-14)
    start = next(e for e in run['policy_events'] if e.get('recovered_search'))
    stop = next(e for e in run['policy_events'] if e['reason'] == 'SEARCH_BUDGET_EXHAUSTED')
    radius = at(run, stop['time_s'])['spiral_theta_rad']*c['spiral_pitch_m']/(2*math.pi)
    assert abs(radius-c['spiral_radius_m']) < 1e-12
    assert stop['time_s']-start['time_s'] < c['search_time_s']
    return {'checked_command_count': len(pairs), 'max_error_m_s': float(np.max(np.abs(predicted-recorded))),
            'fraction_nonpositive_z_commands': float(np.mean(recorded <= 0)),
            'fraction_abs_z_at_most_10um_s': float(np.mean(np.abs(recorded) <= 10e-6)),
            'second_search_duration_s': stop['time_s']-start['time_s'],
            'radius_at_stop_m': radius, 'binding_budget': 'spiral_radius',
            'note': 'Fractions cover post-fork SEARCH commands; force input is the preceding trace row.'}


def figures(target, pairs, evidence):
    configure_font()
    for (_, old, new), e in zip(pairs, evidence):
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
        fork = e['fork_time_s']
        duration = 2.0 if e['case'].startswith('x_') else .7
        for run, label, color in ((old, '旧版：退出搜索', '#687a8b'), (new, 'V2：继续搜索', '#008c95')):
            rows = [s for s in run['trace'] if fork-.1 <= s['time_s'] <= fork+duration]
            t = np.array([s['time_s']-fork for s in rows])
            p = np.array([s['position_m'] for s in rows])
            raw = np.array([s['raw_command_world'] for s in rows])
            limited = np.array([s['limited_command_world'] for s in rows])
            axes[0, 0].plot(t, (p[:, 2]-run['case']['start_origin_z_m'])*1000, color=color, label=label)
            axes[0, 1].plot(t, raw[:, 2]*1000, color=color, label=label+' 原始指令')
            axes[0, 1].plot(t, limited[:, 2]*1000, '--', color=color, lw=.9, label=label+' 限速后')
            axes[1, 0].plot(t, np.linalg.norm(raw[:, :2], axis=1)*1e6, color=color, label=label)
            axes[1, 1].plot(t, [s['contact_wrench_M'][2]*1000 for s in rows], color=color, label=label)
        axes[0, 0].axhline(.25, color='#ac7849', ls=':', label='约 0.25 mm 台阶深度')
        axes[0, 0].set(title='实际推进来自已有动力学记录', ylabel='推进 / mm')
        axes[0, 1].set(title='轴向速度指令也随状态切换改变', ylabel='Z 速度指令 / mm/s')
        axes[1, 0].set(title='横向总指令：导纳修正与额外搜索共同作用', ylabel='XY 原始指令模长 / μm/s')
        axes[1, 1].axhline(-8, color='#ac7849', ls=':', label='搜索 Z 指令为零的载荷')
        axes[1, 1].set(title='接触轴向力（负值阻碍正向插入）', ylabel='Fz / mN')
        for ax in axes.flat:
            ax.axvline(0, color='#999999', ls=':', lw=.8)
            ax.set_xlabel(f'相对共同状态时刻 {fork:.3f} s 的时间 / s')
            ax.grid(alpha=.15); ax.legend(fontsize=8)
        fig.suptitle('B2-5.2｜'+e['label']+'｜离线诊断：两类动作同时变化', fontsize=15)
        fig.supxlabel('曲线是既有回合的局部窗口；指令不等于实际速度，未开展新的动力学消融试验。', fontsize=10)
        fig.savefig(target/(e['case']+'_切换诊断.png')); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.5), layout='constrained')
    for ax, key, title in ((axes[0], 'advance_um', '共同状态后 0.6 s 内实际推进 / μm'),
                           (axes[1], 'xy_path_um', '同一窗口内实际横向路程 / μm')):
        for j, (version, label, color) in enumerate((('old', '旧版退出搜索', '#687a8b'), ('new', 'V2 继续搜索', '#008c95'))):
            values = [e['windows']['0.6'][version][key] for e in evidence]
            bars = ax.bar(np.arange(2)+(j-.5)*.32, values, .3, color=color, label=label)
            ax.bar_label(bars, fmt='%.1f', padding=3)
        ax.set(xticks=[0, 1], xticklabels=[e['label'] for e in evidence], title=title)
        ax.margins(y=.2); ax.legend(); ax.grid(axis='y', alpha=.15)
    fig.suptitle('月报增量｜已定位切换分叉，下一步拆开验证横向与轴向作用', fontsize=15)
    fig.supxlabel('两个固定工况的已有记录；局部推进不代表完整装配成功，也不能单独证明因果。', fontsize=10)
    fig.savefig(target/'01_月报诊断进展.png'); plt.close(fig)


def report(target, evidence):
    lines = ['# B2-5.2 搜索与推进切换诊断', '', '2026-09-21。只读四份已有动力学记录，重建分叉处指令并核对完整后续搜索轴向规则；没有新增动力学试验，没有修改控制器、模型、阈值或完成标准。', '',
             '## 结论', '',
             '目前确认的是：收紧退出条件让系统继续停留在 SEARCH，而 SEARCH 与 INSERT 同时采用不同的横向和轴向动作。因此，不能把 X 推进退步单独归因于“横向搜索把针带偏”。还需要单变量试验。', '',
             '## 共同状态与下一条动作', '',
             '轨迹每行保存一个控制步完成后的状态；本报告用共同状态这一行作为输入，重建下一行的动作。每个控制周期为 2 ms。重建仅调用控制律及限速函数，不进行 MuJoCo 积分。', '',
             '| 工况 | 最后共同状态/s | 当时整体推进/mm | 旧版下一条 XY 指令模长/μm·s⁻¹ | V2 下一条 XY 指令模长/μm·s⁻¹ | 旧版/V2 原始 Z 指令/mm·s⁻¹ | 旧版/V2 限速后 Z 指令/mm·s⁻¹ |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for e in evidence:
        o, n = e['commands']['old'], e['commands']['new']
        lines.append(f"| {e['label']} | {e['fork_time_s']:.3f} | {e['advance_at_fork_mm']:.6f} | {np.linalg.norm(o['raw_command_world'][:2])*1e6:.3f} | {np.linalg.norm(n['raw_command_world'][:2])*1e6:.3f} | {o['raw_command_world'][2]*1000:.3f}/{n['raw_command_world'][2]*1000:.3f} | {o['limited_command_world'][2]*1000:.3f}/{n['limited_command_world'][2]*1000:.3f} |")
    lines += ['', '两例共同状态的六维接触力/力矩均为零；新旧下一条角速度指令相同。旧版此时横向原始指令接近零，但受加速度限制和惯性影响，横向运动不会瞬间停止；旧版原始 Z 指令升到 1 mm/s，限速后第一步只到 0.410 mm/s，不能写成实际速度瞬间达到 1 mm/s。', '',
              '旧版的“推进 0.10 mm”是相对第二次搜索起点计算，触发时整体推进仍只有约 0.07–0.08 mm，尚未越过此前约 0.25 mm 的受阻位置。退出搜索不等于已经脱困。', '',
              '## 等长窗口对照', '', '| 工况 | 分叉后窗口/s | 旧版/V2 实际新增推进/μm | 旧版/V2 实际 XY 路程/μm |', '|---|---:|---:|---:|']
    for e in evidence:
        for duration, w in e['windows'].items():
            lines.append(f"| {e['label']} | {duration} | {w['old']['advance_um']:.3f}/{w['new']['advance_um']:.3f} | {w['old']['xy_path_um']:.3f}/{w['new']['xy_path_um']:.3f} |")
    lines += ['', 'XY 路程为各 2 ms 采样位移模长之和，不是最终位置误差。窗口在两条记录仍运行时截取，避免把停止后的静止区间混入比较。', '',
              '## 搜索为什么可能在接触处停止推进', '',
              '搜索状态的 Z 原始速度为 `clip(0.05 × (0.008 + Fz), −0.00025, 0.0005)`，单位 m/s、N。无接触时为 0.4 mm/s；阻碍插入的轴向力达到 −8 mN 时指令为零，更负时请求后退。这是速度反馈规则，不是强制把实际接触力固定成 8 mN。正常 INSERT 则请求 Z 速度 1 mm/s，由执行器和原保护逻辑限制。', '',
              '这提供了“新版持续搜索时轴向推进更容易受载荷抑制”的控制层解释，但几何接触、横向轨迹和姿态变化相互耦合，现有对照不能确定各因素的独立贡献，也不能据此提高力阈值。', '']
    for e in evidence:
        s = e['search_law']
        lines.append(f"- {e['label']}：核对 {s['checked_command_count']} 条分叉后的搜索指令；其中 {s['fraction_nonpositive_z_commands']:.1%} 请求 Z 不前进，{s['fraction_abs_z_at_most_10um_s']:.1%} 的 Z 指令绝对值不超过 10 μm/s。第二次搜索持续 {s['second_search_duration_s']:.3f} s，结束时螺旋半径达到 {s['radius_at_stop_m']*1e6:.1f} μm 上限，早于 8 s 单次时限。因此本次最终停止是搜索半径预算耗尽，不是 20 s 回合时限到达。")
    lines += ['', '上述比例包括振荡时的前后交替，不能当作实际静止时间比例。', '',
              '## Y 工况给出的限制', '',
              '旧版 Y 同样在退出搜索后未能完成插入，所以“退出搜索就能成功”不成立。共同状态中其 Y 导纳累计指令修正已为 +500 μm，达到该通道预算；这是后续应注意的限制，不等于实际 Y 位移达到 500 μm，也不能单凭这一点确定失败主因。当前不调整该预算。', '',
              '## 下一项细分：仅暂停额外横向搜索的 X 定点试验', '',
              '先形成独立候选与协议，在第二次搜索相对起点前进 0.10 mm（与旧版相同触发点）时，短暂暂停额外的螺旋切向/轨迹跟踪分量；继续保留力导纳的 XY/姿态修正，以及 V2 原有的轴向力反馈速度。限定试探时长并继续计算原搜索总预算，不重置已用预算。试探结束后按预先约定恢复规则处理，不能永久锁住搜索。', '',
              '该下一项需要先明确暂停时长、恢复螺旋轨迹的连续性和退出规则，再做一例 X 动力学验证，与本次冻结 V2 对照。暂停时长属于待确定的开发参数。本轮尚未实施，也未声称它会改善。若单变量无改善，再单独研究轴向规则；不要一次同时改两类动作。', '',
              '保留模型、初始位置姿态、导纳参数、保护阈值、4 mm 目标和完整完成标准。评估须同时看推进、XY/姿态、载荷、穿透、停止原因；深度改善仍不等于装配完成。Y 的独立作用验证排在 X 试验之后。', '',
              '## 文件与复现', '',
              '- [月报诊断图](01_月报诊断进展.png)',
              '- [X 切换曲线](x_offset_pos_100um_切换诊断.png)',
              '- [Y 切换曲线](y_offset_neg_100um_切换诊断.png)',
              '- [精确数据、验证和输入索引](diagnosis.json)',
              '- [月报小结](月报小结.md)', '',
              '工作目录为本项目 worktree 根目录。只读重建命令如下，输出标签必须是新的目录名，保留旧报告：', '', '```powershell',
              "& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.validation.diagnose_b2_switch --tag reproduce_01", '```', '',
              '结果写入 `deliverables/b2_switch_diagnosis/reproduce_01/`。可在 VS Code 打开本报告与 PNG；本细分没有新仿真动画，已有真实轨迹仍从原 B2/V2 回放入口查看。', '',
              '适用边界：两个固定工况、未标定的开发仿真。不能推广成随机成功率或实机 CR5 性能。']
    (target/'B2-5.2切换诊断报告.md').write_text('\n'.join(lines)+'\n', encoding='utf-8', newline='\n')
    (target/'月报小结.md').write_text('# 2026-09-21 月报增量\n\n已从“观察到推进退步”进一步定位到控制状态切换：旧版退出搜索时，同时停用额外横向搜索并改变轴向推进规则。两工况分叉处的指令已用冻结源码重建核对；完整后续搜索轴向规则也与记录一致。\n\n这次完成的是失败机制诊断，没有新增成功工况。下一步采用单变量定点试验，先分离额外横向搜索的作用；原模型、保护阈值和完整达标标准保留。\n\n展示建议：使用 [等长窗口对照图](01_月报诊断进展.png)，必要时补充 [X 切换曲线](x_offset_pos_100um_切换诊断.png)。图中局部推进不是完整装配成功，不应宣传为性能提升。\n', encoding='utf-8', newline='\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', default='diagnosis_v1')
    args = parser.parse_args()
    if not args.tag or any(ch not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for ch in args.tag):
        parser.error('Use a new simple directory name')
    target = OUT/args.tag
    if target.exists():
        raise FileExistsError('Preserve existing diagnostic outputs; use a new --tag')
    pairs, audits = collect(TAGS)
    evidence = []
    for (_, old, new), check in zip(pairs, audits):
        row = old['trace'][check['identical_trace_prefix_samples']-1]
        commands = {v: reconstruct(r, check, v) for v, r in (('old', old), ('new', new))}
        np.testing.assert_allclose(row['contact_wrench_M'], np.zeros(6), atol=0, rtol=0)
        np.testing.assert_allclose(commands['old']['raw_command_world'][3:], commands['new']['raw_command_world'][3:], atol=0, rtol=0)
        evidence.append({'case': check['case'], 'label': 'X +100 μm' if check['case'].startswith('x_') else 'Y −100 μm',
                         'fork_time_s': row['time_s'], 'advance_at_fork_mm': (row['position_m'][2]-old['case']['start_origin_z_m'])*1000,
                         'fork_state': row, 'commands': commands,
                         'windows': {str(d): {v: window(r, row['time_s'], d) for v, r in (('old', old), ('new', new))} for d in (.3, .6)},
                         'search_law': search_law(new, check)})
    target.mkdir(parents=True)
    dump(target/'diagnosis.json', {'method': 'offline recorded-state command reconstruction; no dynamics steps',
                                 'tags': TAGS, 'provenance_audit': audits, 'evidence': evidence})
    figures(target, pairs, evidence)
    report(target, evidence)
    source = Path(__file__)
    (target/source.name).write_bytes(source.read_bytes())
    inputs = {}
    for folder, _, _ in pairs:
        index_path = folder/'results_index.json'
        index = json.loads(index_path.read_text(encoding='utf-8'))
        paths = [index_path, ROOT/index['reference']['file']]+[folder/r['file'] for r in index['runs']]
        inputs.update({p.relative_to(ROOT).as_posix(): sha(p) for p in paths})
    dump(target/'delivery_manifest.json', {'inputs_sha256': inputs,
         'outputs_sha256': {p.relative_to(ROOT).as_posix(): sha(p) for p in target.iterdir() if p.is_file()},
         'script_sha256': sha(source), 'validation': 'All assertions passed; frozen inputs verified by collect()'})
    print(json.dumps({'output': str(target), 'evidence': [{k: e[k] for k in ('case','windows','search_law')} for e in evidence]}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
