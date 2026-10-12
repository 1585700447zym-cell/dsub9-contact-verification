"""Integrate the authorized offline preparation into five rolling documents."""
from pathlib import Path
import json
import re
import shutil

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
REPORT = 'b2_stratified_scope_preparation_20261011/结果说明.md'
M = 'deliverables/monthly_progress/2026-10/月报素材_2026-10.md'
REMINDER = '课题主方法继续应用强化学习；纯B2为共同对照。B.2达到验收条件、准备进入C之前，主动提醒阶段性成果总结和汇总。'
SUMMARY = '25点独立组合核对和针体入口筛查完成，21个新增组合静态筛查通过，最小入口余量下界44.1855μm；真实复位、完整碰撞、零残差动态及非零SAC范围资格仍待。'
KEYS = '共同物理配置保持；旧四点范围指纹保留，25点另登记范围指纹。旧3处逐profile无接触缺口保留，同点A/B聚合依据不能自动扩到新点。'
COST = '本项新增物理回合/模型构造/策略调用/学习器/张量/训练更新/经验发布均0，累计动态258，自动跟踪PAUSED，独立测试0，完整B.2/C未验收，无新物理或训练准入。'
NEXT = '下一项（待开始）：实现并离线核验独立21点零残差纯B2评价入口。在每个实际回合内检查初始化并取得基线数据，旧4点只读复用；入口交付后另有新有限物理授权和逐项准入才执行。随后准备冻结F0/F2000的分层开发评价，不追加原四点短训，不启动C。'
LIMITS = '未来提案仅21次纯B2，每次14500控制周期/145000子步/1200秒，全包304500周期/3045000子步/6小时；策略、学习器、张量、更新、经验池及独立测试0，重试0。DRAFT，入口未实现、真实执行未开始。'


def link(monthly=False):
    return ('../../learning_chain/' if monthly else 'deliverables/learning_chain/') + REPORT


def marker(monthly=False):
    return '\n'.join(['<!-- b2-scope-current -->',
        '**2026-10-11｜当前阶段B.2第3项；任务：21个新增组合的离线适用性与有限执行方案，已完成；新入口实现待开始。**',
        '', SUMMARY, '', KEYS, '', LIMITS, '', COST, '', NEXT, '', REMINDER, '',
        '[本项结果与路线](' + link(monthly) + ')。以下历史记录保留各自时点，当前下一项以本段为准。',
        '<!-- /b2-scope-current -->'])


def section(text, heading, content):
    assert text.count(heading + '\n') == 1, heading
    start = text.index(heading + '\n') + len(heading) + 1
    end = text.find('\n## ', start)
    if end == -1:
        end = len(text)
    return text[:start] + '\n' + content.strip() + '\n' + text[end:]


def main():
    docs = ['项目当前入口.md','项目进度跟踪.md','研究推进计划_当前版.md','项目交付总览.md',M]
    for name in docs:
        path = ROOT / name
        old = path.read_text(encoding='utf-8')
        text, n = re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',
                          lambda _: marker(name == M), old, count=1, flags=re.S)
        assert n == 1
        if name == '项目进度跟踪.md':
            old_row = next(l for l in text.splitlines() if l.startswith('| B.2 小规模学习与评价包 |'))
            new_row = '| B.2 小规模学习与评价包 | 待验收；原四点三组对照及21新组合离线准备完成 | [离线结果](' + link() + ')、[原四点实际结果](deliverables/learning_chain/b2_pure_baseline_execution_20261011/结果说明.md) | 先实现21点纯B2入口，再取得实际资格/分层开发；普通SAC及第4/5项验收仍待 |'
            text = text.replace(old_row, new_row, 1)
            table = '''| 原任务 | 当前对应 |
|---|---|
| 1 开发适用性 | 25点针体入口筛查通过；21新点真实复位/完整碰撞/动态仍待，旧3缺口保持 |
| 2 统一闭环/SAC接口 | 2254继承来源/200共同工具保持；共同配置与四点/25点范围指纹分开登记 |
| 3 动态闭环/成本 | 本项新物理0，累计258；未来仅21次零残差B2提案，DRAFT，旧预算关闭 |
| 4 B1 | 既有成果保持；静态筛查不升级非零动作或训练资格 |
| 5 B2与批量评价 | 原4纯B2+旧8 SAC开发配对保持；25点范围21新点入口待实现 |
| 6 普通残差SAC | 原四点2000批保持；冻结演员分层开发评价及必要SAC工作待，主方法必须用RL |
| 7 阶段与进展约束 | C暂缓，依据B.2数据与阶段总结确定含RL候选 |
| 8 正式证据与展示 | 离线准备报告/有限提案/范围表已归档；第4/5项、C前汇总与D正式多种子仍待 |'''
            text = section(text, '## 原八项任务对应', table)
            risk = SUMMARY + '\n\n' + KEYS + '\n\n原四点纯B2/F0/F2000功能各4/4；F2000相对纯B2快2.72%，附加精度0/4，不能主张整体提升或传统B2功能失败。新组合静态入口余量不与终末MAIN余量混称。\n\n' + COST + '\n\n' + REMINDER + '\n\n'
            start = text.index('## 当前风险和准入门\n') + len('## 当前风险和准入门\n')
            end = text.index('下表保留历史限制；最新下一项见上文。', start)
            text = text[:start] + '\n' + risk + text[end:]
            text = section(text, '## 下一项交付', NEXT+'\n\n'+LIMITS+'\n\n'+REMINDER+'\n\n[本项结果]('+link()+')、[当月月报]('+M+')。\n\n'+COST)
            text += '\n\n### 2026-10-11｜B.2第3项21新组合离线范围准备\n\n' + SUMMARY + '\n\n' + KEYS + '\n\n' + COST + '\n\n验收：仅本项离线准备完成，实际入口/物理/训练未执行，不新增B.2完整验收。' + NEXT + '\n\n证据：[结果]('+link()+')、[范围与余量表](deliverables/learning_chain/b2_stratified_scope_preparation_20261011/qualification_matrix.csv)、[核验](deliverables/learning_chain/b2_stratified_scope_preparation_20261011/verification.json)、[滚动月报]('+M+')。\n'
        elif name == '研究推进计划_当前版.md':
            pos = text.index('## 研究目标和保留架构\n') + len('## 研究目标和保留架构\n')
            text = text[:pos] + '\n2026-10-11当前离线准备：'+SUMMARY+' '+KEYS+'\n\n'+NEXT+' '+LIMITS+'\n\n以下四点评价及旧准备保留各自时点：\n' + text[pos:]
            pos = text.index('### B.2 小规模学习与评价包\n') + len('### B.2 小规模学习与评价包\n')
            text = text[:pos] + '\n当前第3项进展：'+SUMMARY+' '+COST+'\n\n'+NEXT+'\n\n第4项冻结后独立评价和第5项姿态/联合范围验收仍待；21点零残差评价不准入非零SAC或新训练。'+REMINDER+'\n\n以下四点实际交付及原要求保留：\n' + text[pos:]
        elif name == '项目交付总览.md':
            pos = text.index('## 基线与接口交付\n') + len('## 基线与接口交付\n')
            insert = '\n### B.2第3项21新组合离线适用性与有限提案｜2026-10-11\n\n'+SUMMARY+'\n\n'+KEYS+'\n\n成果与使用：[结果]('+link()+')、[逐点表](deliverables/learning_chain/b2_stratified_scope_preparation_20261011/qualification_matrix.csv)、[仅标准库复现器](deliverables/learning_chain/b2_stratified_scope_preparation_20261011/analyse_scope.py)、[未来提案](deliverables/learning_chain/b2_stratified_scope_preparation_20261011/execution_candidate.json)、[入口实现计划](docs/superpowers/plans/2026-10-11-b2-stratified-zero-baseline-entry.md)、[核验](deliverables/learning_chain/b2_stratified_scope_preparation_20261011/verification.json)。\n\n'+LIMITS+'\n\n'+COST+' '+REMINDER+'\n\n'+NEXT+'\n'
            text = text[:pos] + insert + text[pos:]
        elif name == M:
            additions = {
                '## 一、本月综合摘要': '**本次离线准备（2026-10-11）：** '+SUMMARY+' '+KEYS+' '+COST+'\n\n'+NEXT+'\n\n以下四点实际结果及历史材料保留：',
                '## 二、关键数字与证据': '| 本次离线准备项 | 结果 |\n|---|---|\n| 矩阵与新增数 | 25点：1对中/4位置/4姿态/16联合；旧4映射、新21 |\n| 针体入口筛查 | 25/25；新21均通过，真实复位/全碰撞/动态仍待 |\n| 初始入口径向余量下界 | 最小44.1855μm，与终末MAIN余量分列 |\n| 初始最高Z上界 / 距MAIN间隔下界 | 33.3777 / 216.6223μm |\n| 未来纯B2提案 | 新21次/304500周期/3045000子步/6小时；DRAFT |\n| 本项物理/策略/训练/经验 | 全0；累计258、PAUSED、独立测试0 |\n\n[离线原始计算](../../learning_chain/b2_stratified_scope_preparation_20261011/geometry_screen.json)。以下实际四点数据及旧准备数字保留：',
                '## 三、负结果与限制': '**本次范围限制：** 静态针体筛查不证明导向壳体无碰撞、复位有效、动态可行或非零SAC资格。21新组合实测0，旧3逐profile缺口保留；旧四点全成功不能证明传统B2存在功能失败。6小时硬截止可能留下未执行点，不把不完整矩阵填满。\n\n原四点F2000提速2.72%且精度下降的负结果保持，未按新指标追改10%条件。主方法必须用RL。以下此前限制保留：',
                '## 四、图表与讲稿': '本次使用[25点资格/入口余量表](../../learning_chain/b2_stratified_scope_preparation_20261011/qualification_matrix.csv)；它是静态分析，不画成新增成功率或耗时曲线。\n\n讲稿：“当前是B.2第3项，21新组合的离线准备完成。针体入口保守筛查通过，但实际复位和轨迹仍待。先准备21点纯B2一次性入口，再取得共同基线和冻结SAC开发结果，用数据定位不足；主方法保留RL，B.2进入C前先汇总。”\n\n以下实际四点图表及此前讲稿保留：'
            }
            for heading, content in additions.items():
                assert text.count(heading+'\n') == 1
                text = text.replace(heading+'\n', heading+'\n\n'+content+'\n', 1)
            text = section(text, '## 五、下一项', NEXT+'\n\n'+LIMITS+'\n\n'+COST+'\n\n'+REMINDER+'\n\n[本项结果]('+link(True)+')。')
            text += '\n\n2026-10-11｜B.2第3项21新组合离线准备：[结果]('+link(True)+')、[几何](../../learning_chain/b2_stratified_scope_preparation_20261011/geometry_screen.json)、[未来提案](../../learning_chain/b2_stratified_scope_preparation_20261011/execution_candidate.json)、[核验](../../learning_chain/b2_stratified_scope_preparation_20261011/verification.json)。'+SUMMARY+' '+COST+'\n'
        path.write_text(text, encoding='utf-8')
    for name in ['AGENTS.md'] + docs:
        dst = OUT/'after_documents'/name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, dst)
    plan = ROOT/'docs/superpowers/plans/2026-10-11-b2-stratified-zero-baseline-entry.md'
    shutil.copyfile(plan, OUT/'入口实现计划快照.md')
    (OUT/'document_update.json').write_text(json.dumps(dict(status='INTEGRATED',files=docs,
        AGENTS_modified=False,monthly_sections=5,plan_snapshot='入口实现计划快照.md'),
        ensure_ascii=False,indent=2)+'\n', encoding='utf-8')
    print('Five rolling documents integrated; six before/after snapshots and plan snapshot saved.')


if __name__ == '__main__':
    main()
