"""Record the implementation stage in the three existing rolling documents."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STAGE = 'deliverables/learning_chain/b2_actor_lr_implementation_20260930'
MARK = '独立actor学习率实现与协议准备（2026-09-30）'


def change(path, transform):
    p = ROOT / path
    raw = p.read_bytes()
    text = raw.decode('utf-8').replace('\r\n', '\n')
    if MARK in text:
        raise ValueError('Stage already recorded; do not duplicate: ' + path)
    result = transform(text)
    p.write_bytes(result.replace('\n', '\r\n').encode('utf-8'))


def replace_line(text, prefix, line):
    lines = text.splitlines(keepends=True)
    matches = [i for i, value in enumerate(lines) if value.startswith(prefix)]
    assert len(matches) == 1, prefix
    lines[matches[0]] = line + '\n'
    return ''.join(lines)


def insert(text, anchor, new):
    assert text.count(anchor) == 1, anchor
    return text.replace(anchor, anchor + new, 1)


def progress(text):
    text = insert(text, '## 当前状态\n\n', f'**{MARK}：** 用户明确要求开始修复后，已接通actor独立学习率A=3e-4/B=3e-5，critic/温度保持3e-4；恢复前校验全部优化器参数组，准备配置封锁所有计算入口。随机分布解析诊断与四预热256状态已准备。[本阶段交付]({STAGE}/README.md)及[101项最终协议通过]({STAGE}/final_protocol_results.json)，实际模型前向/优化/物理调用0，独立审查通过；4149旧封存文件与929旧源码原字节复核，当前283项另行绑定。实现与协议准备已验收，策略效果未验证；同起点完整重建、A支复现及新执行资格尚缺，B.2未完成。拟议1000批/8动态与额外真实测试/诊断未批准，旧余19/2000不执行，自动跟踪PAUSED。\n\n')
    text = replace_line(text, '| B.2 小规模学习与评价包 |', f'| B.2 小规模学习与评价包 | 待验收；独立actor学习率实现/协议准备已验收，效果未验证 | [已停执行包](deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/README.md)、[修复准备]({STAGE}/README.md)；101协议通过、实际前向/优化/物理0 | 同起点重建、A支复现、新资格和最终/恢复/独立评价尚缺；旧余19/2000不执行，拟议1000批/8动态及额外真实验证另批 |')
    text = text.replace('本次接续证据复核与对照草案属于准备交付；技术导读入口保留，不新增A/B/C/D研究能力验收。', '本次独立actor学习率实现与纯协议准备完成；技术导读入口保留，不新增策略收益或A/B/C/D研究阶段验收。')
    text = replace_line(text, '| 6 普通残差SAC |', '| 6 普通残差SAC | 原轮13动态/2500批后三次力保护停止，余19/2000不执行；已见失败未漏用、危险边界高估与持续偏置差异有证据。actor独立学习率和恢复前拒绝已实现，101项纯协议通过；真实网络/物理/优化0，候选效果未验证，B.2未完成 |')
    text = text.replace('本次方案支持原任务6的后续决策，不增加实验计数或研究验收。', '本次实现与协议准备支持原任务6，不增加实验计数或研究阶段验收。')
    text = replace_line(text, '| 单变量与有限对照可比性 |', '| 单变量与有限对照可比性 | 已分离actor率并校验恢复全部参数组；A/B准备身份已绑定，但四预热/零更新完整起点尚未重建，A支未复现 | 新执行适配和资格、真实状态验证及计算另批；先从归档重建并复现A支500批，不符停止；旧资格不可用，不补跑预热 |')
    text = replace_line(text, '| 原项目全量测试 |', '| 原项目全量测试 | 原历史回归证据保持；本阶段101项指定纯协议通过，监控前向/Adam.step/物理0 | 未运行真实网络更新/物理全量矩阵；纯协议通过不等于真实学习恢复或效果通过，不与历史测试数相加 |')
    old = '下一项是确认方向后实现单独actor学习率与纯协议准备，再提交新资格/计算清单供明确启动批准。当前候选未实现、未签发资格；不启动训练、不追加模型计算、不使用旧余19次/2000批、不恢复自动跟踪。若不能准确重建并复现A支，停止并沟通，不临时扩预算或改为仅续训B支。'
    assert old in text
    text = text.replace(old, f'单独actor学习率与纯协议准备已完成，见[验收]({STAGE}/assessment.json)。下一项为新执行适配、完整同起点重建与状态验证，提交新资格和[实际计算清单]({STAGE}/proposed_compute.json)供单独启动批准；拟额外合成事务最多16次、测试状态前向最多128次、诊断actor状态前向768次，正式1000批/8动态。当前均未执行，旧余19/2000不结转，跟踪PAUSED。若不能准确重建并复现A支，停止并沟通，不临时扩预算或只续训B支。')
    text = insert(text, '## 追加式阶段记录\n\n', f'### 2026-09-30 B.2｜独立actor学习率实现与协议准备\n\n- 用户授权开始修复，沿用当前工作树和分支，全部原修改保留；仅继承的SAC接线修改，保存其原字节，新添3生产模块/4测试文件。4149旧封存文件、929旧源码和276前置资料原字节通过，283当前资料另绑定。\n- actor A=3e-4/B=3e-5，critic/温度保持；恢复前核对全部优化器参数组，准备类含内部目标均阻断；随机分布贴边概率和KL解析、四预热256状态准备完成。\n- [最终101项]({STAGE}/final_protocol_results.json)全部通过、0失败/错误；模型前向/优化/物理0。[只读审查]({STAGE}/review.md)发现内部目标入口已修正，相关红/绿证据保留；未运行真实计算全量测试。\n- [交付]({STAGE}/README.md)、[验收]({STAGE}/assessment.json)、[9月滚动月报](deliverables/monthly_progress/2026-09/月报素材_2026-09.md)同步。实现/准备通过不等于策略有效；完整起点重建、A复现、新资格及新计算未执行，B.2未完成。按阶段约定暂停汇报；旧余19/2000和跟踪PAUSED保持。\n\n')
    return text


def overview(text):
    text = insert(text, '|---|---|---|\n', f'| {MARK} | [修复交付]({STAGE}/README.md)、[101项协议]({STAGE}/final_protocol_results.json)、[验收]({STAGE}/assessment.json) | actor率单独可配，恢复前参数组拒绝，A/B准备与分布解析已实现；真实计算0，效果未验证，无执行资格 |\n')
    text = replace_line(text, '| 上轮为何不达标、优先修什么、怎样避免误判修复 |', f'| 上轮为何不达标、优先修什么、怎样避免误判修复 | [原因复核与修复建议](deliverables/learning_chain/b2_repair_review_20260930/原因复核与修复建议.md)、[当前实现]({STAGE}/README.md) | 覆盖差异非唯一根因证明；actor率候选现已实现，随机分布/初始4/4保持待真实检验，不能宣称效果修复 |')
    text = replace_line(text, '| 下一候选改哪里、有限对照如何限制成本 |', f'| 下一候选改哪里、有限对照如何限制成本 | [actor率实现]({STAGE}/README.md)、[后续拟议计算]({STAGE}/proposed_compute.json)；[原草案](deliverables/learning_chain/b2_actor_lr_design_20260929/README.md)保留 | actor独立3e-5已接通；同起点完整重建/A支复现未通过，正式1000批/8动态与额外真实验证未授权，当前不可运行 |')
    text = replace_line(text, '| 学习原因是否缩小、修复下一步 |', f'| 学习原因是否缩小、修复下一步 | [限定价值核对与图](deliverables/learning_chain/b2_force_mechanism_review_20260929/critic_probe/结果说明.md)、[实现准备]({STAGE}/README.md) | 4检查点/20,968组为历史计算；新危险边界+9.364对−8.359，唯一原因未隔离；actor率候选已实现未验证收益 |')
    text = insert(text, '## 维护记录\n\n', f'### 2026-09-30｜独立actor学习率实现与协议准备\n\n- [本阶段]({STAGE}/README.md)交付actor率、恢复前全部参数组检查、版本化准备与分布解析；使用上述配置/状态材料作审阅输入，准备类型主动拒绝执行，旧资格不可沿用。\n- [101项最终协议]({STAGE}/final_protocol_results.json)通过，模型前向/优化/物理0，独立审查无剩余重要问题；红/绿与原字节保存，4149旧封存文件保持。\n- 原三份滚动资料同步。未重建真实训练状态、未复现A、未签发资格或启动计算；策略效果未验证，B.2未完成。旧余19/2000不执行，自动跟踪PAUSED，下一阶段另批。\n\n')
    return text


def monthly(text):
    stage = '../../learning_chain/b2_actor_lr_implementation_20260930'
    text = insert(text, '## 一、可直接用于汇报的本月总结\n\n', f'**{MARK}：** 用户要求开始修复后，已将actor学习率独立配置为3e-5（A支3e-4），critic/温度保持3e-4；恢复前拒绝错误优化器参数组，A/B准备入口均阻断计算。随机分布解析和256个固定诊断状态已备好；101项最终纯协议通过、独立审查通过，实际网络前向/优化/物理0。4149旧封存文件与929旧源码原字节保持，283当前资料另行绑定。获得代码/准备验收，尚无策略改善证据；完整起点重建、A复现和新资格未完成，拟议真实测试与1000批/8动态未批准。B.2未完成，旧余19/2000与跟踪暂停保持。[交付]({stage}/README.md)、[证据]({stage}/final_protocol_results.json)。\n\n')
    text = insert(text, '|---|---|---|---|\n', f'| 独立actor率实现与协议准备（9月30日） | actor独立3e-5、恢复前全组拒绝、A/B准备与随机分布解析；101项通过，实际计算0 | [交付]({stage}/README.md)、[验收]({stage}/assessment.json) | 实现/协议范围；起点完整重建与A复现未完成，无新资格/训练/策略收益 |\n')
    text = insert(text, '### 数字使用规则\n\n', '本阶段101是最终指定纯协议子集的总数，已包含新增反例与相关原回归；不与16/47/79等中间运行或历史检查相加。256是从四预热选出的固定诊断状态，本阶段并未推理；22766是待重建经验池的归档行数，非新增经验。\n\n')
    text = insert(text, '## 三、必须保留的问题与负结果\n\n', f'本阶段代码/协议准备通过，不能据此声称actor更慢已抑制力保护。真实网络恢复/更新与物理效果未测试，完整起点及A复现未通过；现有[配置与预算]({stage}/proposed_compute.json)均不可执行、未授权。原初始4/4能力、保护和奖励仍为后续判据。\n\n')
    text = insert(text, '## 五、两分钟讲稿（截至本次整理）\n\n', '截至9月30日，我们针对危险边界价值过于乐观、训练动作持续偏置的证据，先实现单独减慢actor更新的候选，critic与温度保持原率。恢复前参数组检查和随机分布诊断已接通，101项纯协议通过；本阶段没有新网络前向、学习更新或物理回合。它完成了修复准备，尚未证明策略效果。下一步先重建共同起点、复现原学习率对照，再在单独批准的有限预算内比较；旧剩余预算与自动跟踪保持暂停。以下保留本月各阶段历史汇报口径。\n\n')
    text = insert(text, '## 六、下一步素材需求\n\n', f'最新下一项：依据[实现准备]({stage}/README.md)完成版本化执行适配、完整同起点重建与真实状态验证，先过A支复现；后续计算清单另批。未来取得分布与固定任务结果后再新增图表，本项没有新性能曲线，继续引用原价值/停止图且注明历史日期。\n\n')
    text = insert(text, '## 七、阶段增量与来源追溯\n\n', f'2026-09-30实现增量：用户明确要求修复，独立actor率、恢复前检查与准备阻断实现；[最终101项]({stage}/final_protocol_results.json)通过、真实调用0，[独立审查]({stage}/review.md)复核无重要问题。4149旧封存文件和929旧源码经原字节复核，283当前文件另绑定；四预热256诊断状态准备，不加载检查点、不重建起点、不复现A、不启动训练。[阶段验收]({stage}/assessment.json)、[准备收据]({stage}/preparation_receipt.json)。原三份滚动文件维护，未改历史包/合同/阈值，旧余19/2000与跟踪PAUSED保持，B.2未完成。\n\n')
    return text


change('项目进度跟踪.md', progress)
change('项目交付总览.md', overview)
change('deliverables/monthly_progress/2026-09/月报素材_2026-09.md', monthly)
print('Updated the three existing rolling documents; historical sections retained.')
