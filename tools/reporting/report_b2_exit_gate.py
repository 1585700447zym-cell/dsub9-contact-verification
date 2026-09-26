"""Audit and present the bounded V2 exit-gate experiment without rerunning it."""
import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
import numpy as np

from tools.reporting.report_b2 import CASE_LABELS, REASONS, replay
from tools.reporting.report_b2_matrix import metrics
from tools.validation.run_b1_baseline import dump
from tools.validation.run_b2_search import read_run
from tools.validation.run_b2_exit_gate import OUT, CASE_NAMES, sha, source_hashes
from tools.validation.run_contact_cases import ROOT
from tools.validation.diagnose_v1_applicability import fingerprint
from tools.visualization.font_support import find_chinese_font


def check_output(target, input_folders):
    if target.resolve() in [p.resolve() for p in input_folders]:
        raise FileExistsError('A report cannot overwrite an input trial')
    if not target.exists():
        return
    if (target/'runs').exists() or (target/'source_snapshot').exists():
        raise FileExistsError('Preserve raw experiment directories')
    index_path = target/'results_index.json'
    if not index_path.exists():
        raise FileExistsError('Existing output is not a recognized comparison')
    index = json.loads(index_path.read_text(encoding='utf-8'))
    if (index.get('method') != 'two new V2 dynamics runs vs preserved V1 records'
            or index.get('input_tags') != [p.name for p in input_folders]):
        raise FileExistsError('Regenerate only the same explicitly identified comparison')


def collect(tags):
    pairs, audit = [], []
    for tag, name in zip(tags, CASE_NAMES):
        folder = OUT / tag
        index = json.loads((folder / 'results_index.json').read_text(encoding='utf-8'))
        assert index['status'] == 'COMPLETE' and len(index['runs']) == 1
        assert index['case']['name'] == name
        assert index['source_sha256'] == source_hashes()
        assert index['historical_source_sha256'] == fingerprint()
        for relative, digest in index['source_sha256'].items():
            assert sha(folder / 'source_snapshot' / relative) == digest
        entry = index['runs'][0]
        assert sha(folder / entry['file']) == entry['sha256']
        assert sha(ROOT / index['reference']['file']) == index['reference']['sha256']
        old = read_run(ROOT / index['reference']['file'])
        new = read_run(folder / entry['file'])
        assert new['source_sha256'] == index['source_sha256']
        assert new['historical_source_sha256'] == old['historical_source_sha256'] == index['historical_source_sha256']
        assert all(new['source_sha256'][k] == v for k, v in old['source_sha256'].items())
        assert new['controller']['config'] == old['controller']['config'] == index['config']
        assert new['controller']['exit_gate'] == index['exit_gate']
        assert new['controller']['admittance'] == old['controller']['admittance']
        assert new['termination'] == entry['termination']
        for key in ('case', 'environment', 'finish_criteria', 'max_time_s', 'settle_time_s'):
            assert new[key] == old[key], key
        for r in (old, new):
            assert np.isfinite(np.array([s['position_m'] + s['quaternion_wxyz'] + s['velocity_world'] + s['contact_wrench_M'] for s in r['trace']])).all()
            metrics(r)
        # The recorded old recovery exit is the earliest intended divergence.
        recovered_at = next(e['time_s'] for e in old['events'] if e['reason'] == 'B2_RECOVERY_RESUMED')
        old_exit = next(e['time_s'] for e in old['policy_events'] if e['reason'] == 'SEARCH_ADVANCED' and e['time_s'] >= recovered_at)
        prefix = 0
        for a, b in zip(old['trace'], new['trace']):
            if a != b:
                break
            prefix += 1
        assert prefix and old['trace'][prefix - 1]['time_s'] >= old_exit - 1e-9
        evidence = []
        def recorded_z(t):
            sample = min(new['trace'], key=lambda s: abs(s['time_s']-t))
            assert abs(sample['time_s']-t) < 1e-9
            return sample['position_m'][2]-new['case']['start_origin_z_m']

        for event in new['policy_events']:
            if 'exit_evidence' not in event:
                continue
            proof = event['exit_evidence']
            blocked = max(recorded_z(e['time_s']) for e in new['policy_events']
                          if e['reason'] == 'AXIAL_STALL' and e['time_s'] <= event['time_s'])
            search_start = max(e['time_s'] for e in new['policy_events']
                               if e['reason'] == 'LOW_LOAD_SEARCH' and e['time_s'] <= event['time_s'])
            threshold = max(blocked, recorded_z(search_start)) + index['config']['search_exit_advance_m']
            assert abs(blocked-proof['blocked_z_m']) < 1e-12
            assert abs(threshold-proof['threshold_z_m']) < 1e-12
            start, end = event['time_s'] - proof['duration_s'], event['time_s']
            window = [s for s in new['trace'] if start-1e-9 <= s['time_s'] <= end+1e-9]
            z = np.array([s['position_m'][2] - new['case']['start_origin_z_m'] for s in window])
            forces = np.array([np.linalg.norm(s['contact_wrench_M'][:3]) for s in window])
            gate = index['exit_gate']
            assert window[-1]['time_s'] - window[0]['time_s'] >= gate['hold_s']-1e-9
            assert np.all(z >= proof['threshold_z_m']-1e-12) and np.all(np.diff(z) >= -1e-12)
            assert z[-1]-z[0] >= gate['min_progress_m']-1e-12
            assert forces.max() <= gate['max_force_N']+1e-12
            assert abs(z[-1]-proof['exit_z_m']) < 1e-12
            assert abs((z[-1]-z[0])-proof['advance_m']) < 1e-12
            assert abs((window[-1]['time_s']-window[0]['time_s'])-proof['duration_s']) < 1e-9
            assert abs(forces.max()-proof['max_observed_force_N']) < 1e-12
            evidence.append(event)
        recovered_search_event = next(e for e in new['policy_events'] if e.get('recovered_search'))
        blocked_z = max(recorded_z(e['time_s']) for e in new['policy_events']
                        if e['reason'] == 'AXIAL_STALL' and e['time_s'] <= recovered_search_event['time_s'])
        exit_depth = max(blocked_z, recorded_z(recovered_search_event['time_s'])) + index['config']['search_exit_advance_m']
        second_search_z = [s['position_m'][2]-new['case']['start_origin_z_m'] for s in new['trace']
                           if s['search_count'] == 2 and s['policy_phase'] == 'SEARCH' and s['phase'] == 'RUNNING']
        pairs.append((folder, old, new))
        audit.append({'case': name, 'old_reference': index['reference'],
                      'new_index': (folder / 'results_index.json').relative_to(ROOT).as_posix(),
                      'identical_trace_prefix_samples': prefix,
                      'identical_through_s': old['trace'][prefix-1]['time_s'],
                      'old_recovery_exit_s': old_exit, 'verified_new_exit_events': evidence,
                      'new_recovery_progress': {'blocked_z_m':blocked_z, 'exit_threshold_z_m':exit_depth,
                                                'maximum_second_search_z_m':max(second_search_z)},
                      'old_metrics': metrics(old), 'new_metrics': metrics(new)})
    return pairs, audit


def configure_font():
    font_manager.fontManager.addfont(str(find_chinese_font()))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=str(find_chinese_font())).get_name(),
                         'axes.unicode_minus': False, 'font.size': 10, 'figure.dpi': 160})


def plots(target, pairs, audit):
    configure_font()
    for (_, old, new), check in zip(pairs, audit):
        fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
        for r, label, color in ((old, '旧退出条件', '#87949f'), (new, '新退出条件', '#007e8a')):
            t = np.array([s['time_s'] for s in r['trace']])
            p = np.array([s['position_m'] for s in r['trace']])
            z = (p[:, 2]-r['case']['start_origin_z_m'])*1000
            f = np.array([np.linalg.norm(s['contact_wrench_M'][:3])*1000 for s in r['trace']])
            axes[0, 0].plot(t, z, color=color, label=label)
            axes[0, 1].plot(t, z, color=color, label=label)
            axes[1, 0].plot(t, f, color=color, label=label, lw=.8)
            axes[1, 1].plot(t, np.linalg.norm(p[:, :2], axis=1)*1e6, color=color, label=label)
        blocked = next(e['blocked_z_m'] for e in new['policy_events'] if e['reason'] == 'AXIAL_STALL')*1000
        axes[0, 0].axhline(4., ls='--', color='#bd5445', label='名义目标 4 mm')
        axes[0, 0].set(ylabel='实际数值积分推进 / mm', title='完整回合：深度到位不等于完整达标')
        axes[0, 1].axhline(blocked, ls=':', color='#7658a8', label='历史受阻深度')
        axes[0, 1].axhline(blocked+.1, ls='--', color='#bd5445', label='新版退出深度门槛')
        axes[0, 1].axvline(check['old_recovery_exit_s'], ls=':', color='#87949f', label='旧版恢复正常推进')
        for e in check['verified_new_exit_events']:
            axes[0, 1].axvline(e['time_s'], ls=':', color='#007e8a', label='新版恢复正常推进')
        axes[0, 1].set(xlim=(check['old_recovery_exit_s']-.6, min(new['final']['time_s'], check['old_recovery_exit_s']+3)),
                       ylim=(-.08, .55), ylabel='实际推进 / mm', title='回撤后局部放大：退出门槛与实际推进')
        axes[1, 0].axhline(25, ls='--', color='#bd5445', label='原力保护阈值')
        axes[1, 0].set(ylabel='接触合力 / mN', title='2 ms 采样曲线；报告另核对全部物理步峰值')
        axes[1, 1].axhline(50, ls='--', color='#bd5445', label='完整达标 XY 容差')
        axes[1, 1].set(ylabel='相对目标 XY 误差 / μm', title='目标位置仅用于离线评价')
        for ax in axes.flat:
            ax.set_xlabel('时间 / s'); ax.legend(fontsize=8); ax.grid(alpha=.15)
        fig.suptitle('B2-5.1｜'+CASE_LABELS[new['case']['name']]+'｜'+REASONS.get(new['termination'], new['termination']), fontsize=14)
        fig.savefig(target / (new['case']['name']+'_旧新轨迹对照.png')); plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(11, 5.3), layout='constrained')
    x = np.arange(2)
    for ax, key, title, limit in ((axes[0], 'advance_mm', '回合最终推进 / mm', 4),
                                 (axes[1], 'xy_error_um', '终点 XY 误差 / μm', 50)):
        for i, (field, label, color) in enumerate((('old_metrics', '旧退出条件', '#87949f'), ('new_metrics', '新退出条件', '#007e8a'))):
            values = [a[field][key] for a in audit]
            bars = ax.bar(x+(i-.5)*.32, values, .3, label=label, color=color)
            ax.bar_label(bars, fmt='%.3f', padding=3)
        ax.axhline(limit, ls='--', color='#bd5445', label='名义目标' if key=='advance_mm' else '原完成容差')
        ax.set(xticks=x, xticklabels=['X +100 μm', 'Y −100 μm'], ylabel=title)
        ax.set_ylim(0, max(limit, max(a[f][key] for a in audit for f in ('old_metrics','new_metrics')))*1.3)
        ax.legend(loc='upper center', fontsize=9); ax.grid(axis='y', alpha=.15)
    fig.suptitle('B2-5.1 两例定点复测｜仅改变回撤后退出搜索条件', fontsize=15)
    fig.supxlabel('完整达标同时检查深度、XY、姿态、稳定保持和载荷；开发仿真结果，不是实机结论。', fontsize=10)
    fig.savefig(target/'01_两工况进展对比.png'); plt.close(fig)


def report(target, pairs, audit):
    lines = ['# B2-5.1 回撤后退出搜索条件复测', '', '2026-09-18。仅改变回撤后第二次搜索的退出资格；完成两次新动力学运行，旧对照直接引用已核验的 B2-4 记录。', '',
             '新版需越过历史受阻深度 0.10 mm，随后在阈值以上连续至少 0.05 s 维持采样合力 ≤10 mN、无后退且推进 ≥5 μm。首次搜索、模型、导纳和搜索参数、保护阈值、完成标准保持原样。', '',
             '## 完整结果', '', '| 工况 | 版本 | 推进/mm | XY/μm | 姿态/° | 力/mN | 力矩/mN·m | 穿透/μm | 完整达标 | 结束原因 |',
             '|---|---|---:|---:|---:|---:|---:|---:|---|---|']
    for check in audit:
        for field, label in (('old_metrics', '旧版'), ('new_metrics', '新版')):
            m = check[field]
            lines.append(f"| {CASE_LABELS[m['case']]} | {label} | {m['advance_mm']:.6f} | {m['xy_error_um']:.3f} | {m['angle_deg']:.4f} | {m['peak_force_mN']:.3f} | {m['peak_torque_mNm']:.6f} | {m['peak_penetration_um']:.3f} | {'是' if m['success'] else '否'} | {REASONS.get(m['termination'],m['termination'])} |")
    if all(a['new_metrics']['advance_mm'] < a['old_metrics']['advance_mm'] for a in audit):
        lines += ['', '**本轮结论：两例最终推进均下降，不能把这一版提升为改进基线。** 旧条件确实不能证明已经越过受阻位置，但“把退出条件收紧即可改善插入”的假设没有得到支持。旧版 X 也只满足深度要求，未满足 XY 完成容差。',
                  '两例新版均未达到约 0.350 mm 的退出深度门槛，因此这两次动力学试验尚不能单独评价新增 0.05 s 持续低载荷判据的效果。下一细分应先对比退出前后横向搜索和轴向推进的作用，不能直接断言横向搜索是卡阻的唯一原因。', '']
    lines += ['', '## 条件修改是否实际生效', '']
    for check in audit:
        name = CASE_LABELS[check['case']]
        lines.append(f"- {name}：新旧轨迹前 {check['identical_trace_prefix_samples']} 个采样完全一致，直至 {check['identical_through_s']:.3f} s；旧版此时提前退出搜索。")
        for e in check['verified_new_exit_events']:
            p = e['exit_evidence']
            lines.append(f"  新版在 {e['time_s']:.3f} s、推进 {p['exit_z_m']*1000:.6f} mm 才退出；此前受阻深度 {p['blocked_z_m']*1000:.6f} mm。窗口 {p['duration_s']:.3f} s 推进 {p['advance_m']*1e6:.3f} μm，最大采样合力 {p['max_observed_force_N']*1000:.3f} mN。")
        if not check['verified_new_exit_events']:
            lines.append('  新版未触发回撤后退出搜索；不能表述为已经越过原受阻区。')
            progress = check['new_recovery_progress']
            lines.append(f"  第二次搜索期间最大推进 {progress['maximum_second_search_z_m']*1000:.6f} mm，退出深度门槛 {progress['exit_threshold_z_m']*1000:.6f} mm。")
        m = check['new_metrics']
        lines.append('  新版未满足项：'+('、'.join(m['unmet']) or '无')+f"；搜索 {m['searches']} 次、回撤 {m['recoveries']} 次，停止时刻 {m['stop_time_s']:.3f} s。")
    lines += ['', '## 证据边界', '',
              '这是两个固定开发工况的定点检验，不能据此宣称随机成功率或全部七工况改善。退出条件修正有效与完整装配成功是两个不同评价。0.05 s、5 μm 为本轮开发判据，并非已标定参数。',
              '全部实际运动来自 MuJoCo 数值积分。现有模型并非完整 CR5/真实夹持与传感器系统；本报告不构成实物性能或物理安全验证。',
              '保留 first_frozen_x100 和 first_frozen_y100 两个预检失败记录：参数 JSON 列表/元组比较失败，实际动力学步数为零。修正仅涉及参数核对表示，正式两次运行使用同一控制器及冻结参数。', '',
              '## 查看与复现', '',
              '- [两工况进展图](01_两工况进展对比.png)',
              '- [X 旧新轨迹](x_offset_pos_100um_旧新轨迹对照.png)',
              '- [Y 旧新轨迹](y_offset_neg_100um_旧新轨迹对照.png)',
              '- [原始指标与审计](comparison_audit.json)',
              '- [实验协议](../实验协议.md)', '',
              '在项目工作目录运行（下列重跑 tag 必须未使用；旧结果不可覆盖）：', '', '```powershell',
              "& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.validation.run_b2_exit_gate --case x_offset_pos_100um --tag reproduce_x100_01",
              "& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.validation.run_b2_exit_gate --case y_offset_neg_100um --tag reproduce_y100_01", '```', '',
              '只读现有结果重新生成本报告、图和回放，不重跑动力学：', '', '```powershell',
              "& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.reporting.report_b2_exit_gate --replay", '```', '',
              '对自己重跑的结果出报告时加 `--x-tag reproduce_x100_01 --y-tag reproduce_y100_01 --out-tag reproduce_comparison_01`。每次运行目录的 `runs/*.json.gz` 保存全部 2 ms 轨迹，`source_snapshot/` 保存控制及执行代码副本；复现须使用相同依赖环境、模型与源码。', '']
    for folder, _, run in pairs:
        lines.append(f"- [{CASE_LABELS[run['case']['name']]}新版轨迹回放](../{folder.name}/真实轨迹回放.gif)；[完整运行索引](../{folder.name}/results_index.json)")
    (target/'B2-5.1退出条件复测报告.md').write_text('\n'.join(lines), encoding='utf-8', newline='\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--x-tag', default='verified_frozen_x100')
    parser.add_argument('--y-tag', default='verified_frozen_y100')
    parser.add_argument('--out-tag', default='comparison_first_frozen')
    parser.add_argument('--replay', action='store_true')
    args = parser.parse_args()
    for tag in (args.x_tag, args.y_tag, args.out_tag):
        if Path(tag).name != tag or tag in ('.','..'):
            raise ValueError('Use plain folder names')
    target = OUT / args.out_tag
    check_output(target, [OUT/args.x_tag, OUT/args.y_tag])
    pairs, audit = collect((args.x_tag, args.y_tag))
    target.mkdir(exist_ok=True)
    dump(target/'comparison_audit.json', audit)
    dump(target/'results_index.json', {'status':'COMPLETE', 'comparisons':audit,
                                     'input_tags':[args.x_tag,args.y_tag],
                                     'method':'two new V2 dynamics runs vs preserved V1 records'})
    plots(target, pairs, audit)
    report(target, pairs, audit)
    if args.replay:
        for folder, _, run in pairs:
            replay(folder, run)
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
