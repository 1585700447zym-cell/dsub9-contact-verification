"""Read saved stop diagnostics and render Chinese monthly figures; no integration."""
import argparse
import json
from pathlib import Path
import numpy as np
from matplotlib import pyplot as plt
from tools.reporting.report_training_readiness import font
from tools.validation.run_b2_search import read_run
from tools.validation.validate_training_readiness import ROOT, verify_hashes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    destination = Path(args.output_dir)
    if destination.exists():
        raise FileExistsError('Use a new output directory to preserve the previous report')
    source = ROOT/'deliverables/stop_reliability'
    index = json.loads((source/'diagnosis_v1/results_index.json').read_text(encoding='utf-8'))
    assert index['status'] == 'COMPLETE' and index['prefix_exact']
    verify_hashes(source/'diagnosis_v1', index['files'])
    verify_hashes(ROOT, index['historical_source_sha256'])
    geometry = json.loads((source/'frozen_pose_v1/results.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT, geometry['source_sha256'])
    destination.mkdir(parents=True)
    font()
    labels = ['原步长 0.2 ms', '步长减半 0.1 ms', '步长四分之一 0.05 ms', '关闭接触（诊断反事实）']
    colors = ['#28618c', '#d58631', '#8c64a4', '#35876c']
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout='constrained')
    for i, (entry, label, color) in enumerate(zip(index['branches'], labels, colors)):
        run = read_run(source/'diagnosis_v1'/entry['file'])
        rows = run['trace']
        t = np.array([r['time_s']-index['checkpoint_time_s'] for r in rows])
        velocity = np.array([r['velocity_world'] for r in rows])
        axis = axes[0, 0] if i < 3 else axes[0, 1]
        axis.plot(t, np.linalg.norm(velocity[:, :3], axis=1)*1e6, label=label, color=color, lw=.9, alpha=.8)
    for axis in axes[0]:
        axis.axhline(10, ls='--', color='#aa3737', label='线速度阈值 10 μm/s')
        axis.set(xlabel='距共同检查点 / s', ylabel='线速度 / μm/s')
        axis.legend(fontsize=9); axis.grid(alpha=.2)
    axes[0, 0].set_title('减小时间步，仍未持续停稳')
    axes[0, 1].set_title('去掉接触后可以停稳：仅作定位对照')
    spans = [v['summary']['longest_stable_span_s'] for v in index['branches']]
    bars = axes[1, 0].bar(range(4), spans, color=colors)
    axes[1, 0].bar_label(bars, labels=[f'{x:.3f}' for x in spans], padding=3)
    axes[1, 0].set_xticks(range(4), ['原步长', '减半', '四分之一', '无接触'])
    axes[1, 0].axhline(.1, ls='--', color='#aa3737', label='要求连续 0.1 s')
    axes[1, 0].set(ylabel='线速度和角速度同时达标 / s', title='最后 1 s 内最长连续达标采样跨度', ylim=(0, 1.0))
    axes[1, 0].legend(fontsize=9)
    axes[1, 1].axis('off')
    axes[1, 1].text(.02, .96, '本轮交付：停止问题的可复现诊断证据\n\n'
        '• 原完整回合、原参数延续逐样本复现\n'
        '• 保持目标固定，停止后的外部命令为零\n'
        '• 三种时间步均有接触附近速度波动\n'
        '• 下一重点：入口擦边接触的几何一致性\n\n'
        '状态：诊断完成，修复未验收，训练仍暂缓\n'
        '无接触分支不能作为装配成功或正式模型', va='top', fontsize=12, linespacing=1.6)
    fig.suptitle('D-sub9 训练前可靠性检查：定位停止速度波动', fontsize=17)
    fig.supxlabel('同一完整动力学检查点延续 1 s；保持控制周期 2 ms。均为诊断分支，无新训练配置。', fontsize=10)
    fig.savefig(destination/'01_月报_停止问题定位.png', dpi=160); plt.close(fig)

    results = geometry['results']
    keys = ['original_mpr', 'single_contact_mpr', 'tolerance_1e12', 'iterations_350', 'native_ccd']
    values = [results[k]['max_penetration_m']*1e6 for k in keys]
    bound = max(c['axial_separation_upper_bound_m'] for c in results['original_mpr']['pair_contacts'])*1e6
    fig, axis = plt.subplots(figsize=(11, 6), layout='constrained')
    bars = axis.bar(range(5), values, color=['#28618c']*4+['#d58631'])
    axis.bar_label(bars, labels=[f'{v:.6f}' for v in values], padding=4)
    axis.set_yscale('log'); axis.set_ylim(.01, 10)
    axis.axhline(bound, color='#35876c', ls='--', label=f'沿负 Z 分离位移上界 {bound:.6f} μm')
    axis.set_xticks(range(5), ['原 MPR', '关闭多点接触', '容差 1e−12', '迭代上限 350', 'native CCD'])
    axis.set(ylabel='返回的最大接触穿透 / μm（对数坐标）', title='冻结同一入口擦边姿态：接触深度对照')
    axis.legend(loc='upper right'); axis.grid(axis='y', alpha=.2)
    fig.supxlabel('针 07 / 主孔入口，单个冻结姿态；几何上界不等于接触法向深度。\n'
                  'native 在此点较接近该上界，但历史另一姿态曾异常，尚未采用；不能据此宣布全模型修复。', fontsize=10)
    fig.savefig(destination/'02_入口接触深度核查.png', dpi=160); plt.close(fig)
    print(destination)


if __name__ == '__main__':
    main()
