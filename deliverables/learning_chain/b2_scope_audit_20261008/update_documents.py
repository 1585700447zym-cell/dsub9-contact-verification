"""One-time rolling documentation update; preserve byte snapshots and old logs."""
from pathlib import Path
import json

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
DOCS = ['项目当前入口.md', '项目进度跟踪.md', '项目交付总览.md',
        '研究推进计划_当前版.md', 'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
REL = 'deliverables/learning_chain/b2_scope_audit_20261008/'
REPORT = REL + '范围审计与最小预检方案.md'
PLAN = 'docs/superpowers/plans/2026-10-08-b2-pose-scope-preflight.md'
SUMMARY = ('B2-SCOPE-01范围审计与最小预检方案完成，属于离线证据整理与规划，未新增物理或学习能力。'
           'PC-06/07/09的63份当前版本原始新回合均为初始零倾角；当前每轴初始输入限为±0.5°，'
           '旧pilot入口还把roll/pitch写死为0。原±1.5°目标不能直接套用，完整B.2仍待验收。')
NEXT = ('下一项优先实现B.2小倾角范围预检的离线运行器与准入检查，显式贯通实际初始角，'
        '保留当前v4模型/控制/保护。候选为每轴±0.25°的8个开发点，拟9次无积分初始化、'
        '最多16个零残差/脚本配对动态；先完成纯检查和审查，再申请具体新物理预算。'
        '运行器未实现，候选未授权，当前不执行。C的F12.5物理接入暂缓，既有PC-11～14成果保留。')
LIMIT = ('本轮物理引擎加载、初始化、动态/子步、神经网络推理、张量读取、优化和经验发布均0；'
         '实际累计动态208，自动跟踪PAUSED，旧预算关闭。拟16动态若以后全部获准执行，累计上限224，'
         '现在不计入实绩。完整B.2/C未验收；±0.25°预检不能覆盖±0.5°边界或原±1.5°目标。')
EVIDENCE = ('只读核验950个PC-06～14封存成员及1057共享输入；63原始档案按旧账本SHA复核。'
            'S/F0.39%未过原继续门、四首次位置附加精度均0/4、PC-12两个停止上下文缺口均保持。')


def insert_after(text, marker, addition):
    assert text.count(marker) == 1, marker
    return text.replace(marker, marker + '\n\n' + addition, 1)


def replace_section_intro(text, heading, end_marker, replacement):
    start = text.index(heading) + len(heading)
    end = text.index(end_marker, start)
    return text[:start] + '\n\n' + replacement + '\n\n' + text[end:]


def main():
    edits = {}
    for name in DOCS:
        raw = (ROOT / name).read_bytes()
        assert raw == (OUT / 'before_documents' / name).read_bytes(), name
        text = raw.decode('utf-8').replace('\r\n', '\n')
        assert '<!-- b2-scope-current -->' not in text
        prefix = '../../../' if name.startswith('deliverables/') else ''
        links = f'[范围审计与预检方案]({prefix}{REPORT})、[实现计划]({prefix}{PLAN})、[机器候选]({prefix}{REL}candidate.json)'
        block = (f'<!-- b2-scope-current -->\n**2026-10-08｜当前优先项转为B.2姿态/联合范围。** {SUMMARY}\n\n'
                 f'{NEXT}\n\n{LIMIT}\n\n{EVIDENCE} {links}。以下PC-14及更早记录保留当时状态；'
                 '其历史“下一项”不作为当前执行顺序或授权。\n<!-- /b2-scope-current -->\n\n')
        first = text.index('\n') + 1
        text = text[:first] + '\n' + block + text[first:].lstrip('\n')
        if name == '项目进度跟踪.md':
            lines = text.splitlines()
            replacements = {
                '| B.2 小规模学习与评价包 |': f'| B.2 小规模学习与评价包 | 位置里程碑完成；姿态/联合优先补证，全范围待验收 | [范围审计]({REPORT})、PC-07位置评价 | 当前输入限±0.5°；先准备±0.25°预检，原±1.5°仍待；三种子属D |',
                '| C 候选约束与消融 |': '| C 候选约束与消融 | 待验收；PC-14数值成果保留，物理接入暂缓 | [PC-14](deliverables/paper_comparison/small_boundary_numeric_execution_20261008/结果说明.md) | 优先B.2范围；没有新匹配训练或收益结论 |',
                '| 1 开发适用性 |': '| 1 开发适用性 | 当前63份相关原始新回合均为零初始倾角；新姿态/联合范围需补证 |',
                '| 2 统一闭环/SAC接口 |': '| 2 统一闭环/SAC接口 | 既有137维/4维与保存恢复证据保留；新范围需显式贯通初始角 |',
                '| 3 动态闭环/成本 |': '| 3 动态闭环/成本 | 本轮新增物理/学习0，累计208；9静态/16动态仅为未授权提案 |',
                '| 5 B2与批量评价 |': '| 5 B2与批量评价 | 零残差/脚本8点配对方案已登记；运行器及实际预检待完成 |',
                '| 6 普通残差SAC |': '| 6 普通残差SAC | 优先补姿态/联合准入与匹配学习评价；原更大范围未验收，不要求必须战胜B2才承认工程闭环 |',
                '| 7 阶段与进展约束 |': '| 7 阶段与进展约束 | PC-11～14保留，C物理接入暂缓；完整机制/公平消融未验收 |',
                '| 8 正式证据与展示 |': '| 8 正式证据与展示 | 本轮交付范围证据表与预检方案；多种子/统计/最终测试属后续D |'
            }
            for beginning, replacement in replacements.items():
                indexes = [i for i, line in enumerate(lines) if line.startswith(beginning)]
                assert len(indexes) == 1, beginning
                lines[indexes[0]] = replacement
            text = '\n'.join(lines) + '\n'
            stale = '当前PC-13完成数值门脚本准备；PC-12适配实现已留证，真实数值门、准入及新性能评价未发生。历史G失败/S旧成功保持。'
            assert stale in text
            text = text.replace(stale, 'PC-14真实合成数值门已通过且额度关闭；物理接入及新性能评价尚未发生。本轮B2-SCOPE-01只补范围审计与方案，历史G失败/S旧成功保持。', 1)
            text = replace_section_intro(text, '## 当前风险和准入门', '下表保留历史限制',
                SUMMARY + '\n\n' + LIMIT + '\n\n风险：守卫输入范围不是训练资格；旧pilot写死零角，新范围若继续复用将产生虚假扩展。'
                '新scope须独立绑定；原±1.5°涉及当前±0.5°初始限制的版本讨论。普通失败/保护与无效仿真分列，不能把脚本效果当学习收益。')
            text = replace_section_intro(text, '## 下一项交付', '## 追加式阶段记录', NEXT + '\n\n' + LIMIT + f'\n\n[实施方案]({PLAN})。')
            text += (f'\n### 2026-10-08｜B2-SCOPE-01范围审计与优先级调整\n\n{SUMMARY}\n\n{EVIDENCE}\n\n'
                     f'{NEXT}\n\n{LIMIT} 本项只验收离线审计和方案交付，不新增B.2/C能力验收。'
                     f'[证据]({REPORT})、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n')
        elif name == '项目交付总览.md':
            text = insert_after(text, '## 快速查找', f'当前先看[B2-SCOPE-01范围缺项与预检]({REPORT})；后续实现按[计划]({PLAN})。')
            text = insert_after(text, '## 基线与接口交付',
                f'### B2-SCOPE-01｜姿态/联合范围审计与最小预检方案（2026-10-08）\n\n{SUMMARY}\n\n'
                f'使用方式：先读[范围证据表与固定8点矩阵]({REPORT})，再按[实现计划]({PLAN})准备运行器；'
                f'[candidate.json]({REL}candidate.json)是未授权候选，不能交给旧学习入口执行。\n\n{EVIDENCE} {LIMIT}\n\n{NEXT}')
        elif name == '研究推进计划_当前版.md':
            text = insert_after(text, '### B.2 小规模学习与评价包',
                f'2026-10-08执行优先级补充：{NEXT} 这不是把完整B.2缩小为±0.25°；更大范围与原任务6仍待。'
                f'按[范围审计]({REPORT})补证，B.2工程验收与SAC相对B2的收益判断分开。以下原要求保留。')
            text = insert_after(text, '## 能力 C 阶段与进展相关残差约束',
                '2026-10-08：C已有离线与数值成果保留，当前物理接入暂缓，先补B.2范围。'
                '此调整是投入优先级，不把下述入口条件改写为“B.2全范围验收前禁止C”。')
        elif name.startswith('deliverables/'):
            text = text.replace('统计截至：2026-10-08（北京时间，PC-14合成数值门真实执行）。',
                                '统计截至：2026-10-08（北京时间，B2-SCOPE-01离线范围审计；最近数值执行为PC-14）。', 1)
            text = insert_after(text, '## 一、本月综合摘要', SUMMARY + '\n\n' + NEXT + '\n\n' + LIMIT + '\n\n以下为各前轮交付的历史摘要：')
            text = insert_after(text, '## 二、关键数字与证据',
                'B2-SCOPE-01：63份原始新回合均初始零倾角；当前输入限每轴±0.5°，拟预检±0.25°。'
                '950封存成员、1057共享输入核验；本轮新物理/学习0、累计208。拟9静态/16动态未授权，'
                '历史墙时均值外推1.04h，规划1–3h、拟监督硬限6h，均非本轮实测。')
            text = insert_after(text, '## 三、负结果与限制',
                '当前版本尚无非零初始倾角训练/评价证据；旧入口角度写死0，且初始守卫为±0.5°，'
                '原±1.5°不能直接继承。小范围脚本通过不证明学习收益或完整B.2；原S/F负结果与精度限制保持。')
            text = insert_after(text, '## 四、图表与讲稿',
                f'本轮使用[要求—证据—缺项及8点矩阵表](../../../{REPORT})，没有新实验曲线。'
                '当前讲稿：“普通残差学习已有位置范围证据，但姿态和联合范围还没有当前版本依据。'
                '我们先用守卫内的小倾角预检检查初始化、接触、动作和停止，再决定匹配训练；'
                '旧C数值成果保留，完整B.2/C仍未验收。”以下讲稿保留前轮时点：')
            text = replace_section_intro(text, '## 五、下一项', '## 六、来源记录', NEXT + '\n\n' + LIMIT)
            text += f'\n### 2026-10-08｜B2-SCOPE-01范围审计来源\n\n{SUMMARY} {EVIDENCE}\n\n[审计与方案](../../../{REPORT})、[候选](../../../{REL}candidate.json)、[实现计划](../../../{PLAN})。{LIMIT}\n'
        edits[name] = text
    for name, text in edits.items():
        data = text.encode('utf-8')
        (ROOT / name).write_bytes(data)
        target = OUT / 'document_snapshots' / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as f:
            f.write(data)
    target = OUT / 'document_snapshots' / PLAN
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as f:
        f.write((ROOT / PLAN).read_bytes())
    print(json.dumps(dict(updated_documents=DOCS, snapshots=6, runtime_code_changes=0), ensure_ascii=False))


if __name__ == '__main__':
    main()
