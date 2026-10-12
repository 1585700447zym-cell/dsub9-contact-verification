"""Update the five rolling documents for the verified offline repair."""
import json
from pathlib import Path
import re

ROOT = Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT = Path(__file__).resolve().parent
DOCS = ['项目当前入口.md', '项目进度跟踪.md', '项目交付总览.md', '研究推进计划_当前版.md',
        'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
REL = 'deliverables/learning_chain/b2_scope_auditor_fix_20261008/'
SUMMARY = ('B2-SCOPE-04审核器离线修复与真实档案回归完成：同值Python/NumPy标量可正确比较，'
           '布尔与数值仍区分，非有限值和真实差异继续拒绝；混合大整数/浮点采用确切差，原容差不变。')
EVIDENCE = ('最终14项新检查、6项原有审核回归通过；正式修订入口只读复核9份静态＋1份动态档案通过。'
            'P01的3045周期和3046个137维观测得到复核；一次只读审查的1项Important经作者反例及修复关闭。')
LIMIT = ('本轮新增仿真/初始化/子步/网络前向/优化/经验发布全0，累计动态209，自动跟踪PAUSED。'
         '原B2-SCOPE-03失败账本、NO_SCOPE_QUALIFICATION及15个未运行且已关闭的动态保持；'
         '完整B.2/C未验收，无新训练准入。现有P01无接触，脚本、联合动态及更大姿态范围仍缺。')
NEXT = ('下一项仅把修订审核器接入新的预检执行候选，核对来源绑定和停止规则，形成明确的仿真运行上限。'
        '旧物理入口仍保留旧审核器，不能直接再次调用；本项没有新增执行授权，旧15回合不恢复。C的F12.5接入继续暂缓。')

def section(text, heading, end_marker, body):
    start = text.index(heading) + len(heading)
    end = text.index(end_marker, start)
    return text[:start] + '\n\n' + body + '\n\n' + text[end:]

def lead(text, heading, body):
    start = text.index(heading) + len(heading)
    rest = text[start:].lstrip('\n')
    return text[:start] + '\n\n' + body + rest[rest.index('\n\n'):]

def main():
    result = json.loads((OUT / 'archive_reassessment_final.json').read_text(encoding='utf-8'))
    assert result['status'] == 'REPAIRED_OFFLINE_AUDIT_PASSED'
    assert result['original_dynamic_status'] == 'error' and result['original_unrun_dynamics'] == 15
    for name, count in [('final_tests.txt', 14), ('inherited_final.txt', 6)]:
        log = (OUT / name).read_text(encoding='utf-8')
        assert f'Ran {count} tests' in log and log.rstrip().endswith('OK')
    edited = {}
    for name in DOCS:
        data = (ROOT / name).read_bytes()
        assert data == (OUT / 'before_documents' / name).read_bytes(), name
        text = data.decode('utf-8').replace('\r\n', '\n')
        prefix = '../../../' if name.startswith('deliverables/') else ''
        links = (f'[修复与使用]({prefix}{REL}结果说明.md)、[正式档案复核]({prefix}{REL}archive_reassessment_final.json)、'
                 f'[最终回归]({prefix}{REL}final_tests.txt)、[审查与处置]({prefix}{REL}review.md)')
        block = (f'<!-- b2-scope-current -->\n**2026-10-08｜当前阶段B.2；任务：审核器离线修复与真实档案回归，已完成。** '
            f'{SUMMARY}\n\n{EVIDENCE}\n\n{LIMIT}\n\n{NEXT}\n\n{links}。以下历史记录保留当时状态，其旧下一项不代表当前授权。\n<!-- /b2-scope-current -->')
        text, count = re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->', lambda _: block, text, count=1, flags=re.S)
        assert count == 1
        if name == '项目进度跟踪.md':
            text = section(text, '## 当前状态', '下方保留此前阶段的日期和原结论', SUMMARY + '\n\n' + EVIDENCE + '\n\n' + LIMIT + '\n\n' + NEXT)
            replacements = {
                '| B.2 小规模学习与评价包 |': f'| B.2 小规模学习与评价包 | 位置里程碑完成；姿态/联合范围待验收 | [审核器修复与既有档案回归]({REL}结果说明.md) | 新执行候选尚待接入；旧动态1/16后关闭，完整范围与匹配训练仍缺 |',
                '| 2 统一闭环/SAC接口 |': '| 2 统一闭环/SAC接口 | 初始角贯通保持；审核器数值类型修复与既有档案回归通过，新物理入口尚待接入 |',
                '| 3 动态闭环/成本 |': '| 3 动态闭环/成本 | 本轮新增仿真与学习0、累计209；上一轮9静态＋1动态/30450子步保留，15未用动态关闭 |',
                '| 5 B2与批量评价 |': '| 5 B2与批量评价 | 修订审核器只读复核9静态＋1动态通过；原运行失败状态及16项分母不变，不补成完整矩阵 |',
                '| 8 正式证据与展示 |': '| 8 正式证据与展示 | 14新检查＋6继承回归、真实档案复核及审查留档；无新增独立实验或SAC收益结论 |'}
            lines = text.splitlines()
            for marker, value in replacements.items():
                indexes = [i for i, line in enumerate(lines) if line.startswith(marker)]
                assert len(indexes) == 1
                lines[indexes[0]] = value
            text = '\n'.join(lines) + '\n'
            text = text.replace('本轮B2-SCOPE-03新增9静态/1动态及审核故障证据，未新增SAC性能结论；历史G失败/S旧成功保持。',
                '本轮B2-SCOPE-04完成审核器修复及旧档案回归，新增仿真/学习0；历史G失败/S旧成功与原失败账本保持。', 1)
            text = section(text, '## 当前风险和准入门', '下表保留历史限制', LIMIT + '\n\n' + NEXT +
                '\n\n修复仅支持可还原为普通bool/int/float的NumPy标量，不宣称支持全部扩展类型。原S/F0.39%继续门失败、首次位置附加精度0/4及旧STOP上下文缺口保持。')
            text = section(text, '## 下一项交付', '## 追加式阶段记录', NEXT + '\n\n' + LIMIT + '\n\n' + links)
            text += f'\n### 2026-10-08｜B2-SCOPE-04审核器修复与档案回归\n\n{SUMMARY}\n\n{EVIDENCE}\n\n{LIMIT}\n\n{NEXT}\n\n{links}、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name == '项目交付总览.md':
            text = lead(text, '## 快速查找', f'当前先看[B2-SCOPE-04审核器修复与使用]({REL}结果说明.md)。'
                '支持只读检查现有档案；物理运行器接入待下一项，旧grant和15回合保持关闭。')
            heading = '## 基线与接口交付'
            text = text.replace(heading, heading + f'\n\n### B2-SCOPE-04｜审核器离线修复（2026-10-08）\n\n{SUMMARY}\n\n{EVIDENCE}\n\n{LIMIT}\n\n{links}。'
                f'使用audit_existing.py --check-only核对来源，省略该选项只读复核既有档案。\n\n{NEXT}', 1)
        elif name == '研究推进计划_当前版.md':
            text, count = re.subn(r'2026-10-08执行优先级更新：.*?以下原要求保留。', lambda _: '2026-10-08执行优先级更新：' + SUMMARY + ' ' + NEXT + ' ' + LIMIT + ' 以下原要求保留。', text, count=1)
            assert count == 1
        elif name.startswith('deliverables/'):
            text = text.replace('B2-SCOPE-03预检执行与审核故障收口', 'B2-SCOPE-04审核器修复与档案回归', 1)
            text = lead(text, '## 一、本月综合摘要', SUMMARY + ' ' + EVIDENCE + ' ' + LIMIT + ' 以下保留此前阶段摘要：')
            text = lead(text, '## 二、关键数字与证据', '| 本轮B2-SCOPE-04项目 | 实际值 |\n|---|---:|\n'
                '| 新回归／继承回归 | 14/14／6/6通过 |\n| 既有档案只读复核 | 9静态＋1动态通过 |\n'
                '| 既有动态周期／观测 | 3045／3046×137维 |\n| 新仿真／训练 | 0／0 |\n'
                '| 累计动态 | 209 |\n| 旧未用动态 | 15，保持关闭 |\n| 修订输入／继承输入绑定 | 20／2167 |')
            text = text.replace('单独奖励复算3045/3045；仅在诊断进程统一标量类型后', '前轮B2-SCOPE-03诊断时点：单独奖励复算3045/3045；仅在诊断进程统一标量类型后', 1)
            text = lead(text, '## 三、负结果与限制', LIMIT + ' 新物理运行器尚未接入修订审核器。'
                '一次审查发现混合大整数精度问题，已按真实差值拒绝反例修复；不把软件修复计作新策略性能。')
            text = lead(text, '## 四、图表与讲稿', f'本轮使用[修复与回归证据表](../../../{REL}结果说明.md)，无新实验曲线。'
                '讲稿：“目前仍在B.2补姿态范围。审核器的数值类型问题已修复，20项检查及已有10份档案复核通过，'
                '没有新增仿真或训练。下一步接入新的执行候选，原15个关闭回合不自动续跑。”')
            text = section(text, '## 五、下一项', '## 六、来源记录', NEXT + '\n\n' + LIMIT)
            text += f'\n### 2026-10-08｜B2-SCOPE-04修复来源\n\n{SUMMARY}\n\n{EVIDENCE}\n\n{links}。{LIMIT}\n'
        edited[name] = text
    for name, text in edited.items():
        (ROOT / name).write_text(text, encoding='utf-8', newline='\n')
        target = OUT / 'document_snapshots' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write((ROOT / name).read_bytes())
    with (OUT / 'document_snapshots/AGENTS.md').open('xb') as stream:
        stream.write((ROOT / 'AGENTS.md').read_bytes())
    progress = OUT / 'progress.md'
    text = progress.read_text(encoding='utf-8')
    text = text.replace('- 状态：回归测试已准备，RED待运行；新审核器尚未实现。', '- 准备时点：回归测试已准备，RED待运行；新审核器尚未实现。')
    text += ('\n- 最终状态：离线修复完成。原版RED10项/19子失败；初轮独立模块名修正后13项GREEN；'
        '单次审查1 Important经混合大整数4子失败RED及精确差修复，最终14新＋6继承检查通过。'
        '正式入口复核10份旧档案通过；新仿真/学习0，累计209、PAUSED。\n'
        '- 旧审核器及失败账本不变。新物理运行器接入尚未做，不能直接复用旧入口。'
        '下一项为新的执行候选与具体仿真运行上限准备。\n')
    progress.write_text(text, encoding='utf-8', newline='\n')
    print('Updated five rolling documents and saved six after snapshots.')

if __name__ == '__main__':
    main()
