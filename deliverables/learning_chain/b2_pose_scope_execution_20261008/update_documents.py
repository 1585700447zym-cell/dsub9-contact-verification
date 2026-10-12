"""One-time closeout of the five rolling documents; preserve dated history."""
import json
from pathlib import Path
import re

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = Path(__file__).resolve().parent
DOCS = ['项目当前入口.md', '项目进度跟踪.md', '项目交付总览.md', '研究推进计划_当前版.md',
        'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
PLAN = 'docs/superpowers/plans/2026-10-08-b2-pose-scope-preflight.md'
LEDGER = '.superpowers/sdd/2026-10-08-b2-pose-scope-preflight/progress.md'
REL = 'deliverables/learning_chain/b2_pose_scope_execution_20261008/'

SUMMARY = ('B2-SCOPE-03获批一次性预检后，9/9静态初始化通过；P01_zero运行完成后，审核器标量类型比较报错，'
           '按规则关闭余下15个动态。动态尝试1/16、原运行审核通过0/16，动态范围未验收。')
EVIDENCE = ('本轮10次环境创建/复位、3045控制周期、30450物理子步，全程监督260.759s，进程退出确认；'
            '学习器/张量/网络前向/优化/经验发布全0。累计动态209，自动跟踪PAUSED，旧预算关闭。')
DIAGNOSIS = ('生产奖励独立复算3045/3045一致。原审核器误拒同值的float/NumPy标量；3个同值反例复现，'
             '仅在诊断进程统一标量类型后，命令/奖励/3046个137维观测/守卫/几何/停止复核通过，4个异常反例仍拒绝。'
             '封存代码与原失败状态不改。')
LIMIT = ('P01零残差原始记录及只读诊断支持功能成功、4.330s任务时间和物理停稳，但接触0、脚本未执行；'
         '联合动态、对称配对、恢复及匹配训练仍缺。完整B.2/C未验收，无新训练准入；'
         '±0.25°静态通过不覆盖±0.5°边界或原±1.5°目标。')
NEXT = ('下一项仅离线修复审核器标量比较，补真实内存NumPy奖励与JSON往返命令的回归，并保留对真实数值差异、'
        '非有限值和布尔混用的拒绝。新候选及绑定可审阅后，再登记明确的新物理预算；'
        '本轮关闭的15动态不恢复，不重试，C的F12.5物理接入继续暂缓。')

def section(text, heading, end_marker, body):
    start = text.index(heading) + len(heading)
    end = text.index(end_marker, start)
    return text[:start] + '\n\n' + body + '\n\n' + text[end:]

def lead(text, heading, body):
    start = text.index(heading) + len(heading)
    rest = text[start:].lstrip('\n')
    end = rest.index('\n\n')
    return text[:start] + '\n\n' + body + rest[end:]

def after(text, heading, body):
    assert text.count(heading) == 1
    return text.replace(heading, heading + '\n\n' + body, 1)

def main():
    closure = json.loads((OUT / 'authorization_closure.json').read_text(encoding='utf-8'))
    assert closure['status'] == 'CLOSED_AUDIT_ERROR' and closure['cumulative_dynamic_after'] == 209
    edited = {}
    for name in DOCS:
        before = (ROOT / name).read_bytes()
        assert before == (OUT / 'before_documents' / name).read_bytes(), name
        text = before.decode('utf-8').replace('\r\n', '\n')
        prefix = '../../../' if name.startswith('deliverables/') else ''
        links = (f'[执行与故障说明]({prefix}{REL}结果说明.md)、[授权收口]({prefix}{REL}authorization_closure.json)、'
                 f'[根因证据]({prefix}{REL}audit_diagnosis.json)、[路线决定]({prefix}{REL}路线决定.md)')
        block = (f'<!-- b2-scope-current -->\n**2026-10-08｜B.2预检9静态通过，首个动态审核报错后关闭。** {SUMMARY}\n\n'
                 f'{EVIDENCE}\n\n{DIAGNOSIS}\n\n{LIMIT}\n\n{NEXT}\n\n{links}。'
                 '以下旧阶段记录保留当时状态，其历史“下一项”不代表当前授权。\n<!-- /b2-scope-current -->')
        text, count = re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->', lambda _: block,
                             text, count=1, flags=re.S)
        assert count == 1
        if name == '项目进度跟踪.md':
            text = text.replace('最后更新：2026-10-07。', '最后更新：2026-10-08。', 1)
            text = lead(text, '## 当前状态', SUMMARY + '\n\n' + EVIDENCE + '\n\n' + DIAGNOSIS + '\n\n' + NEXT)
            replacements = {
                '| B.2 小规模学习与评价包 |': f'| B.2 小规模学习与评价包 | 位置里程碑完成；姿态/联合范围待验收 | [9静态及首个动态故障证据]({REL}结果说明.md) | 审核器离线修复优先；动态1/16后关闭，完整范围与匹配训练仍缺 |',
                '| 1 开发适用性 |': '| 1 开发适用性 | 原63份PC-06/07/09原始档案初始倾角0；本轮8个非零倾角点静态通过，动态仅P01_zero，不能外推联合域 |',
                '| 2 统一闭环/SAC接口 |': '| 2 统一闭环/SAC接口 | 真实初始角贯通已核对；首动态审核类型错误已定位，原运行审核未通过 |',
                '| 3 动态闭环/成本 |': '| 3 动态闭环/成本 | 新9静态＋1动态、10次复位、3045周期/30450子步；累计209，学习开销0，余15动态关闭 |',
                '| 5 B2与批量评价 |': '| 5 B2与批量评价 | 静态9/9通过；动态尝试1/16、原审核通过0/16；只读诊断复核P01，完整矩阵未验收 |',
                '| 8 正式证据与展示 |': '| 8 正式证据与展示 | 本轮留档授权/实耗/完整轨迹/类型错误反例/路线决定；无新SAC收益或独立测试 |'}
            lines = text.splitlines()
            for marker, replacement in replacements.items():
                indexes = [i for i, line in enumerate(lines) if line.startswith(marker)]
                assert len(indexes) == 1, marker
                lines[indexes[0]] = replacement
            text = '\n'.join(lines) + '\n'
            text = text.replace('本轮B2-SCOPE-02已完成预检离线实现，未新增物理或策略性能证据；历史G失败/S旧成功保持。',
                '本轮B2-SCOPE-03新增9静态/1动态及审核故障证据，未新增SAC性能结论；历史G失败/S旧成功保持。', 1)
            text = section(text, '## 当前风险和准入门', '下表保留历史限制', SUMMARY + '\n\n' + DIAGNOSIS + '\n\n' + LIMIT +
                '\n\n原S/F0.39%未过10%继续门、首次位置附加精度0/4及旧两个STOP上下文缺口保持。原批准已消费并关闭，不能据离线诊断恢复执行。')
            text = section(text, '## 下一项交付', '## 追加式阶段记录', NEXT + '\n\n' + EVIDENCE + '\n\n' + LIMIT + '\n\n' + links)
            text += f'\n### 2026-10-08｜B2-SCOPE-03执行与审核故障收口\n\n{SUMMARY}\n\n{EVIDENCE}\n\n{DIAGNOSIS}\n\n{LIMIT}\n\n{NEXT}\n\n{links}、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name == '项目交付总览.md':
            text = lead(text, '## 快速查找', f'当前先看[B2-SCOPE-03执行、根因及路线]({REL}结果说明.md)。'
                '本轮授权已关闭；B2-SCOPE-01/02保留原方案和离线准备时点，不能把旧请求当作可用额度。')
            text = after(text, '## 基线与接口交付', f'### B2-SCOPE-03｜姿态预检执行与审核故障（2026-10-08）\n\n'
                f'{SUMMARY}\n\n{EVIDENCE}\n\n{DIAGNOSIS}\n\n{LIMIT}\n\n{links}。'
                '使用原档案和诊断证据只读核查；原grant已消费，执行入口不得再次调用。\n\n' + NEXT)
        elif name == '研究推进计划_当前版.md':
            text, count = re.subn(r'2026-10-08执行优先级更新：.*?以下原要求保留。',
                lambda _: '2026-10-08执行优先级更新：' + SUMMARY + ' ' + NEXT + ' ' + LIMIT + ' 以下原要求保留。', text, count=1)
            assert count == 1
        elif name.startswith('deliverables/'):
            text = text.replace('B2-SCOPE-02预检离线实现；最近数值执行为PC-14', 'B2-SCOPE-03预检执行与审核故障收口', 1)
            text = lead(text, '## 一、本月综合摘要', SUMMARY + ' ' + EVIDENCE + ' ' + DIAGNOSIS + ' ' + LIMIT + ' 以下为此前阶段摘要：')
            text = lead(text, '## 二、关键数字与证据',
                '| 本轮B2-SCOPE-03项目 | 实际值 |\n|---|---:|\n| 静态检查 | 9/9通过 |\n| 动态尝试／原审核通过 | 1/16／0/16 |\n'
                '| 创建环境／真实复位 | 10／10 |\n| 控制周期／子步 | 3045／30450 |\n| 全程监督 | 260.759s |\n'
                '| 累计动态 | 209 |\n| 未用动态 | 15，已关闭 |\n| 学习开销 | 全0 |\n\n'
                '单独奖励复算3045/3045；仅在诊断进程统一标量类型后3046个137维观测等审核通过。原运行失败账本与26s记账项保留，诊断任务时间4.330s单列。')
            text = lead(text, '## 三、负结果与限制', '本轮首动态因审核器误拒同值NumPy/Python标量而关闭，动态矩阵未验收。'
                + LIMIT + ' 旧S/F收益继续门失败与位置附加精度限制保持；不因诊断通过恢复15个关闭额度。')
            text = lead(text, '## 四、图表与讲稿', f'本轮图表使用[实际执行与成本表](../../../{REL}结果说明.md)，'
                '不新增策略收益曲线。讲稿：“我们已实际检查小倾角初始化，9个静态点通过。首个动态运行后暴露审核器数值类型问题，'
                '按规则关闭余量并定位根因；累计209，下一步先离线修审核，不进入C或训练。”')
            text = section(text, '## 五、下一项', '## 六、来源记录', NEXT + '\n\n' + LIMIT)
            text += f'\n### 2026-10-08｜B2-SCOPE-03执行与故障来源\n\n{SUMMARY}\n\n{EVIDENCE}\n\n{DIAGNOSIS}\n\n{links}。{LIMIT}\n'
        edited[name] = text

    plan_raw = (ROOT / PLAN).read_bytes()
    assert plan_raw == (OUT / 'before_documents' / PLAN).read_bytes()
    plan = plan_raw.decode('utf-8').replace('\r\n', '\n')
    plan = plan.replace('本次记录离线实现完成状态；物理执行仍待明确新授权。', '本次记录获批执行后提前关闭状态；不得复用关闭额度。', 1)
    plan = plan.replace('当前状态 `PREPARED_NOT_AUTHORIZED`。', '原候选保留 `PREPARED_NOT_AUTHORIZED` 历史状态；本次新grant已获批、消费并关闭，见B2-SCOPE-03。', 1)
    old = '- [ ] 获得该具体新物理授权且实现准入通过后，才执行固定矩阵一次；原始有效普通失败保留，停止规则照候选，不追加重试。'
    assert old in plan
    plan = plan.replace(old, '- [x] 获得具体新物理授权后执行一次固定顺序；9静态通过，首动态审核错误按规则关闭余15动态。执行收口不代表16项全部完成或动态范围通过，无重试。', 1)
    plan += '\n## 2026-10-08获批执行收口\n\n' + SUMMARY + '\n\n' + EVIDENCE + '\n\n' + DIAGNOSIS + '\n\n' + NEXT + '\n\n' + LIMIT + '\n'
    edited[PLAN] = plan
    ledger_path = ROOT / LEDGER
    before_ledger = OUT / 'before_documents' / LEDGER
    before_ledger.parent.mkdir(parents=True, exist_ok=True)
    with before_ledger.open('xb') as stream:
        stream.write(ledger_path.read_bytes())
    edited[LEDGER] = ledger_path.read_text(encoding='utf-8') + (
        '\nTask 3 physical execution: explicit user approval received 2026-10-08. '
        'Grant ccf21cb187103a504009cfa4ea9a3a73cc8b4b61869345e269321430847a698a consumed once. '
        '9/9 static audits passed, 1/16 dynamic attempted; audit comparator rejected equal NumPy/Python scalar values. '
        'CLOSED_SUPERVISOR_ERROR, 15 unused dynamics closed, no retry; 30450 physical substeps, cumulative209.\n'
        'Read-only diagnosis: original archive error reproduced; 3045/3045 rewards numerically equal; '
        'type-normalization hypothesis passes complete archive with 4 negative controls, no engine/learning imports. '
        'Sealed runner and failed ledger unchanged. Full B.2/C and dynamic matrix unaccepted. '
        'Next deliverable: offline comparator repair and real archive regression before any new physical registration.\n')
    for name, text in edited.items():
        (ROOT / name).write_text(text, encoding='utf-8', newline='\n')
        dest = OUT / 'document_snapshots' / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open('xb') as stream:
            stream.write((ROOT / name).read_bytes())
    print('Updated five rolling documents, plan and progress ledger; seven before/after snapshots preserved.')

if __name__ == '__main__':
    main()
