"""Read completed V1 metrics and close rolling records; no simulation/inference."""
from collections import Counter
from pathlib import Path
import sys
import csv
import io
import gzip
import json
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.validation.run_exploration_execution import OUT, read, write, sha, validate

DOCS = ['项目当前入口.md', '项目进度跟踪.md', '项目交付总览.md', '研究推进计划_当前版.md',
        'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']


def main():
    reg = read(OUT / 'registration.json'); validate(reg)
    ledger = read(OUT / 'ledger.json'); exit_proof = read(OUT / 'process_exit.json')
    if not exit_proof['process_exit_confirmed'] or ledger['status'] not in ('COMPLETED', 'STOPPED'):
        raise ValueError('Require ended ledger and confirmed process exit')
    if (OUT / 'completion_verification.json').exists():
        raise ValueError('Refuse to rewrite an existing closeout')
    rows = []; metrics = {}; pins = {}
    for receipt in ledger['episodes']:
        name = receipt['case_id']; folder = OUT / 'run' / name
        for path in folder.iterdir():
            if path.is_file() and path.name in ('receipt.json', 'progress.json', 'episode.json.gz',
                    'audit.json', 'metrics.json', 'model_used.xml', 'supervisor.json'):
                pins[path.relative_to(OUT).as_posix()] = sha(path)
        if not (folder / 'metrics.json').exists(): continue
        m = metrics[name] = read(folder / 'metrics.json'); a = m['all']; p = m['physical']
        # Read the already audited bytes for a direct measured-velocity check;
        # this adds no simulation, policy inference or repeated archive audit.
        raw=json.loads(gzip.decompress((folder/'episode.json.gz').read_bytes()))
        active=np.array([r['action_active'] for r in raw['transitions']], dtype=bool)
        velocity=np.array([r['velocity_world'] for r in raw['trace'][1:]])[active]
        command=np.array([r['limited_command_world'] for r in raw['trace'][1:]])[active]
        physical_error=abs(velocity-command).mean(axis=0)
        m['measured_velocity_tracking']=dict(mean_absolute_error=physical_error.tolist(),
            interpretation='Measured actual velocity minus drive-limited command; contains lag/contact effects, not causal residual displacement')
        del raw
        rows.append(dict(case=name, cycles=receipt['control_cycles'], reason=receipt['final_reason'],
            Gx=a['gain'][0], Gy=a['gain'][1], Ex=a['tracking_error'][0], Ey=a['tracking_error'][1],
            local_x=a['local_gain_auxiliary'][0], local_y=a['local_gain_auxiliary'][1],
            mean_actual_vx_um_s=p['active_mean_abs_velocity'][0]*1e6,
            mean_actual_vy_um_s=p['active_mean_abs_velocity'][1]*1e6,
            mean_actual_command_error_x_um_s=physical_error[0]*1e6,
            mean_actual_command_error_y_um_s=physical_error[1]*1e6,
            z_advance_mm=p['z_advance_m']*1e3, peak_force_N=p['peak_force_N'],
            peak_torque_Nm=p['peak_torque_G_Nm'], gain_admissible=m['gain_admissible']))
    gates = []
    for pose in ('YAW_P15', 'YAW_M15'):
        names = ['H01_' + pose, 'H10_' + pose]
        if not all(name in metrics for name in names):
            gates.append(dict(pose=pose, passed=False, reason='incomplete_pair')); continue
        a, b = [metrics[name] for name in names]
        admissible = a['gain_admissible'] and b['gain_admissible']
        old_guards = a['physical']['guard_facts']; new_guards = b['physical']['guard_facts']
        guard_keys = ['contact_reasons', 'motion_reasons', 'invalid_reasons']
        no_new_guard = all(set(new_guards[k]).issubset(set(old_guards[k])) for k in guard_keys)
        axes = []
        for i, axis in enumerate(('X', 'Y')):
            g0, g1 = a['all']['gain'][i], b['all']['gain'][i]
            e0, e1 = a['all']['tracking_error'][i], b['all']['tracking_error'][i]
            gr = g1/g0 if g0 is not None and g0 > 1e-12 and g1 is not None else None
            er = e1/e0 if e0 is not None and e0 > 1e-12 and e1 is not None else None
            passed = bool(admissible and gr is not None and er is not None and gr >= 1.5 and er <= .8)
            axes.append(dict(axis=axis, G20_over_G2=gr, E20_over_E2=er, passed=passed))
        gates.append(dict(pose=pose, gain_admissible=admissible, no_new_guard=no_new_guard,
                          axes=axes, passed=no_new_guard and all(r['passed'] for r in axes)))
    completed = ledger['status'] == 'COMPLETED' and exit_proof['exit_code'] == 0
    passed = completed and all(r['audit_passed'] for r in ledger['episodes']) and all(g['passed'] for g in gates)
    summary = dict(status=ledger['status'], process_exit=exit_proof,
        initialization_attempts=ledger['initialization_attempts'],
        cumulative_initializations=ledger['cumulative_initializations'],
        physical_substeps=ledger['physical_substeps'], elapsed_wall_s=ledger['elapsed_wall_s'],
        training_updates=0, neural_policy_calls=0, replay_publications=0,
        engineering_gate_passed=passed, gates=gates, rows=rows,
        measured_velocity_tracking={name:m['measured_velocity_tracking'] for name,m in metrics.items()},
        limitations=['scripted uniform actions, not trained policy', 'four development trials, one seed',
                     'shadow commands share recorded baseline, not causal physical displacement',
                     'no entropy strength or learning outcome comparison yet'])
    write(OUT / 'result_summary.json', summary)
    buffer = io.StringIO(newline='')
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    (OUT / '四回合统计.csv').write_text(buffer.getvalue(), encoding='utf-8-sig')
    def fmt(x): return '不可判' if x is None else f'{x:.3f}'
    lines = ['# 探索动作执行验证结果', '', '2026-10-26，B.2第3项，V1零更新诊断。', '',
        f'**执行{ledger["status"]}；20 ms候选工程筛查{"通过" if passed else "未通过或不可判"}。** '
        '本轮只检验脚本探索的执行，不训练策略，不据此宣布插入成功率提高。', '',
        '| 回合 | Gx | Gy | Ex | Ey | 实际平均绝对vx/vy（μm/s） | 推进（mm） | 峰力（N） | 结束原因 |',
        '|---|---:|---:|---:|---:|---|---:|---:|---|']
    for row in rows:
        lines.append(f'| {row["case"]} | {fmt(row["Gx"])} | {fmt(row["Gy"])} | {fmt(row["Ex"])} | {fmt(row["Ey"])} | '
            f'{row["mean_actual_vx_um_s"]:.2f}/{row["mean_actual_vy_um_s"]:.2f} | '
            f'{row["z_advance_mm"]:.4f} | {row["peak_force_N"]:.3f} | {row["reason"]} |')
    lines += ['', 'G是在共同20 ms窗口内，实际命令相对于逐步传播的零残差影子命令的绝对差，按请求绝对积分归一。'
        'E是命令对静态限速后目标的跟踪误差，同样归一；E越小表示命令跟踪越好。'
        '阶段/权限变化即拆窗。它们不是实际位移因果增益，也不能将G解释成插入成功率。', '',
        '## 预登记工程门槛', '', '两工况的X/Y分别要求G20/G2≥1.5且E20/E2≤0.8，无新增保护、无效或保持/停稳审核失败。'
        '参考过滤/影子参考越界时G不可用于判门；接近零的分母不可判，不补小常数。', '',
        '| 工况 | 轴 | G20/G2 | E20/E2 | 门槛 |', '|---|---|---:|---:|---|']
    for g in gates:
        for a in g.get('axes', []):
            lines.append(f'| {g["pose"]} | {a["axis"]} | {fmt(a["G20_over_G2"])} | {fmt(a["E20_over_E2"])} | '
                         f'{"通过" if a["passed"] else "未通过/不可判"} |')
    lines += ['', '## 分阶段及角向诊断', '',
        '| 回合 | 阶段 | 启用周期 | G：X/Y/roll/pitch/yaw | E：X/Y/roll/pitch/yaw |',
        '|---|---|---:|---|---|']
    for name, m in metrics.items():
        for stage in ('all', 'INSERT', 'SEARCH'):
            if stage in m:
                a=m[stage]
                lines.append(f'| {name} | {stage} | {a["rows"]} | '+
                    '/'.join(fmt(x) for x in a['gain'])+' | '+
                    '/'.join(fmt(x) for x in a['tracking_error'])+' |')
    lines += ['', '逐轴静态裁剪/基线速度余量、旧局部增量辅助指标、实际运动绝对积分、参考前导峰值、六维载荷及全部搜索/恢复事件，'
        '分别保存在每回合metrics.json及episode.json.gz；原有独立字节档案审核与保持序列重放核对见audit.json。', '',
        '## 实际速度是否跟上受限命令', '',
        '| 回合 | X平均绝对速度误差（μm/s） | Y平均绝对速度误差（μm/s） |',
        '|---|---:|---:|']
    for r in rows:
        lines.append(f'| {r["case"]} | {r["mean_actual_command_error_x_um_s"]:.3f} | {r["mean_actual_command_error_y_um_s"]:.3f} |')
    lines += ['', '该误差比较实测速度和同周期受限驱动命令，包含执行滞后和接触影响；不是以另一条物理轨迹作反事实对照。', '',
        '## 成本、验证与解释范围', '',
        f'- 实际新增初始化{ledger["initialization_attempts"]}，科研累计{ledger["cumulative_initializations"]}；'
        f'物理子步{ledger["physical_substeps"]:,}；墙钟{ledger["elapsed_wall_s"]/60:.1f}分钟。',
        '- 网络控制调用0、优化更新0、回放发布0；没有最终测试或额外资格仿真。',
        '- 6项相关离线检查通过；集中审查修复中断成本核对。旧241份冻结输入不变，动态配置及保护逐回合核对，实际结束与停稳另审计。',
        '- 脚本请求的保持改善不等于已训练策略中心变大；本轮也不能解释2000更新后的小均值全部来自哪一项。', '',
        '## 下一项', '',
        '继续第二目标：同为2 ms的A0/A1探索奖励（熵）强度对照，只改变熵强度，暂不加入动作保持训练或历史。'
        '原提案A0/A1的alpha_eff初值为0.01/0.00002；两支必须同期、同初始网络/经验/预算，且不能以输出变大代替任务收益。'
        '本次阶段收口不启动追加训练；28次初始化/8000总更新仍是原候选预算，需在下一阶段按效率收敛实际试验范围。', '']
    (OUT / '探索动作执行验证结果.md').write_text('\n'.join(lines), encoding='utf-8')
    outcome = '通过' if passed else '未通过或不可判'
    block = f'''<!-- exploration-execution-20261026-completed -->
**2026-10-26｜B.2第3项：探索动作执行验证已结束，20 ms候选工程筛查{outcome}（B2-SAC-F5-EXPLORATION-20261026）。** 最多4次零更新诊断已按台账收口，进程退出确认；未训练、未加入历史。结果只评价脚本探索能否执行，不改变原学习策略开发0/4结论。

实际新增初始化{ledger['initialization_attempts']}，科研累计{ledger['cumulative_initializations']}，物理子步{ledger['physical_substeps']:,}，优化更新/网络控制调用/回放发布均0。6项离线检查通过，保持/阶段/权限/重置及原字节档案审核均留证；241份原冻结输入、N2/450、奖励及全部保护不变。

| 原任务对应 | 本轮产出 | 限制及下一项 |
|---|---|---|
| 第3项控制 | 2 ms与20 ms请求执行、影子命令跟踪和实际运动对照 | 不是保持策略训练或物理因果位移证明 |
| 第4项学习 | 无新增更新，排查执行层时间尺度 | 熵强度对照尚未开始；暂不加历史 |
| 第7项评价 | 正负1.5°的限定脚本试验及停稳审核 | 非新策略成功率评价，无最终测试 |
| 第8项记录 | 预算/全部尝试/成本/负结果及五份滚动资料同步 | 完整B.2/C尚未验收 |

**下一项待开始：**同为2 ms的同期熵强度对照，只改该因素；不将20 ms保持、历史、奖励重构同时加入。原28次初始化/8000更新是候选预算，不自动按上限追加。本阶段按项目约定收口汇报。

[本轮结果及证据](deliverables/learning_chain/five_axis_exploration_execution_20261026/探索动作执行验证结果.md) · [滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。下方保留历史。
<!-- /exploration-execution-20261026-completed -->

'''
    log = (f'\n\n### 2026-10-26｜B.2第3项：探索执行V1阶段记录\n\n'
        f'产出：2 ms/20 ms零更新执行对照，工程筛查{outcome}。实际新增初始化{ledger["initialization_attempts"]}，'
        f'累计{ledger["cumulative_initializations"]}，物理子步{ledger["physical_substeps"]:,}，更新0。'
        '证据：本轮探索动作执行验证结果、登记、每回合回执/原始档案/审核、process_exit及completion_verification。'
        '限制：脚本四点、单种子，不能认定学习收益或B.2验收。下一项：同期熵强度对照，历史关闭。\n')
    documents = []
    for name in DOCS:
        p=ROOT/name; before=p.read_bytes()
        snap=OUT/'rolling_documents_before_completion'/name
        snap.parent.mkdir(parents=True,exist_ok=True); snap.write_bytes(before)
        text=block
        if name.startswith('deliverables/'):
            text=text.replace('(deliverables/learning_chain/', '(../../learning_chain/').replace(
                '(deliverables/monthly_progress/2026-10/', '(')
        after=text.encode('utf-8') + before
        if name in ('项目进度跟踪.md', DOCS[-1]): after += log.encode('utf-8')
        p.write_bytes(after)
        snapshot=OUT/'rolling_documents_after_completion'/name
        snapshot.parent.mkdir(parents=True,exist_ok=True); snapshot.write_bytes(after)
        documents.append(dict(path=name, before_sha256=sha(snap), after_sha256=sha(p),
                              original_bytes_preserved=before in after))
    for name in ('registration.json', 'ledger.json', 'process_exit.json', 'result_summary.json',
                 '探索动作执行验证结果.md', '四回合统计.csv', 'offline_verification.json', '集中审查记录.md'):
        pins[name]=sha(OUT/name)
    snap=OUT/'analysis_source_snapshot'/Path(__file__).name
    snap.parent.mkdir(); snap.write_bytes(Path(__file__).read_bytes())
    pins[snap.relative_to(OUT).as_posix()]=sha(snap)
    validate(reg)
    write(OUT/'completion_verification.json', dict(verified=True, batch_completed=completed,
        engineering_gate_passed=passed, original_source_pins_verified=241,
        inputs_verified=len(reg['inputs']), artifacts=pins, rolling_documents=documents))
    print(summary)


if __name__ == '__main__': main()
