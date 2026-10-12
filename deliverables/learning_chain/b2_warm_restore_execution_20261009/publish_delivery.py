"""Publish the bounded numerical restoration result into the five rolling documents."""
import os, re, shutil, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / 'b2_warm_import_repair_20261009'))
from joint_contract import read, write, sha


def section(text, heading, body):
    text, count = re.subn('(' + re.escape(heading) + r'\n).*?(?=\n## |\Z)',
                         lambda m: m.group(1) + '\n' + body.rstrip() + '\n', text, count=1, flags=re.S)
    assert count == 1
    return text


def main():
    if (HERE / 'document_update.json').exists():
        raise FileExistsError('Preserve published evidence')
    reg = read(HERE / 'launch_registration/registration.json')
    review = read(HERE / 'review_resolution.json')
    assert review['status'] == 'RESOLVED' and review['open_critical'] == review['open_important'] == 0
    audit = read(HERE / 'runtime_verification.json')
    assert audit['status'] == 'VERIFIED_NUMERIC_RESTORE' and audit['numeric_restore_verified']
    a = read(HERE / 'assessment.json')
    assert a['verified'] and a['numeric_restore_verified'] and not a['training_admitted']
    summary = (f'B2-SCOPE-18按批准完成一次旧预热状态恢复数值验证并成功关闭，整体监督用时{audit["supervisor_wall_s"]:.2f}秒，'
               f'其中独立读取进程{audit["reader_wall_s"]:.2f}秒。旧零检查点核对、预热重建、新检查点保存与独立组件恢复均通过。')
    capability = ('父进程与独立读取进程分别从同一零起点和4份旧档案重建，完整状态摘要一致：19300行经验、14127行动作启用、'
                  '388次四维均匀动作抽样（1552个标量）。独立进程已将模型、优化器、温度与随机状态写回运行对象，'
                  '并核对独立重建的回放和终末边界；两次确定性预测均未改变模型或策略随机状态。'
                  '本结果验证的是已登记封套内的组件状态；尚未创建可训练V4Chain或执行恢复后的下一次优化。')
    scope = ('本次模型构造2、张量读取2、保存1、确定性预测2、旧档案重建8（父4＋独立进程4）；'
             '新增物理／正式更新／新经验均0，累计动态245，自动跟踪PAUSED。'
             '本次授权已耗尽关闭；SCOPE13原8回合、文件访问失败及SCOPE16导入失败证据保持，旧未用次数不结转。')
    limits = ('当前仍在B.2第3项“普通SAC训练与真实任务评价”。四个固定±75μm／±0.25°开发点与原3处逐profile覆盖缺口保持，'
              '事后开发覆盖修订不撤销。当前四点路线的正式训练更新仍为0，训练后评价未做；完整B.2/C未验收，独立测试0。'
              '恢复数值通过不能证明物理续训、训练收益或论文优势。')
    next_task = ('下一项：离线接入并审查从第四份预热完整发布边界继续的训练入口，明确新封套到可训练V4Chain的转换、'
                 '回放／终末边界／模型／优化器／温度／随机流及_audited_warm_rng等运行字段的恢复，'
                 '形成一次有限续训及同四点训练后匹配评价的具体候选。复用已验证旧预热数据和初始评价，不重跑前8回合。'
                 '先完成可审阅代码、恢复前后及下一步一致性的验证方案，再依据新候选确定计算次数、时限与准入；当前没有新训练授权。')
    body = '\n\n'.join((summary, capability, scope, limits, next_task))
    table = ('| 本次检查 | 结果 | 解释 |\n|---|---|---|\n'
             '| 旧来源重建 | 4份，19300行／14127行动作启用 | 父与独立进程各复算一次，没有新增样本 |\n'
             '| 预热随机动作 | 388次四维抽样 | 每次抽4值；逐周期保持动作与旧档案一致 |\n'
             '| 保存与恢复 | 1个新检查点；独立完整状态摘要一致 | 模型等运行对象、重建回放及边界读回核对通过 |\n'
             '| 确定性预测 | 2次 | 检查预测不改变完整模型／策略随机状态，不是性能评价 |\n'
             f'| 监督时间 | 整体{audit["supervisor_wall_s"]:.2f}秒，内含读取进程{audit["reader_wall_s"]:.2f}秒 | 未触发30分钟／15分钟上限，两棵受控进程树均退出 |\n'
             '| 本次新增物理／正式更新／新经验 | 0／0／0 | 累计动态245；当前路线仍无训练后效果证据 |\n'
             '| 完整B.2／C／独立测试 | 未验收／未验收／0 | 不扩大本次验收范围 |\n')
    report = '# B2-SCOPE-18｜旧预热状态恢复数值验证\n\n当前阶段：B.2第3项；本次恢复数值验证与证据收口已完成。\n\n' + body
    report += '\n\n## 实际验证结果\n\n' + table
    report += ('\n## 恢复内容与证据边界\n\n'
               '来源为SCOPE13的已绑定零检查点、原4份完整预热档案及其发布收据。每份旧档案的字节摘要、政策来源、动作随机流、'
               '回放发布结果均重新核对。新封套保存这些旧来源、预热末尾状态与终末边界。独立进程读取新检查点，并从原零起点与旧档案重新构造期望状态，'
               '完整类型化摘要相同；随后恢复模型／优化器／温度和随机数发生器，核对运行对象及重建回放／边界的完整读回。\n\n'
               '恢复目标是第四份预热发布结束、online J01开始前的边界；旧online J01仅登记，未创建物理环境。'
               '新封套中的历史binding只记录旧来源，外层training_admitted=false。恢复用模型禁止update，未调用V4Chain训练恢复入口，'
               '未验证下一次采样／梯度更新等价，也未恢复任何在途物理仿真。两次预测仅检查无状态副作用，不用来主张策略有效。\n\n'
               '原3处逐profile接触覆盖缺口仍在；此次恢复验证不提供新接触证据。旧文件访问失败、导入规则误拦截失败均保留原样，'
               '不能用本次成功改写历史失败或重新开启旧授权。\n\n'
               '运行日志中的Python路径提示和Matplotlib字体缓存写入警告已保留；两者未使本次数值验证失败。'
               '启动脚本文本准备时另有一次PowerShell引号语法错误，发生在登记、grant、claim和数值执行之前；'
               '已单列在launch_registration/preparation_note.json，不计为第二次数值执行。\n\n')
    report += ('## 文件与复核\n\n'
               '- [数值结果](assessment.json)、[独立恢复回执](reader_reply.json)、[新检查点摘要](checkpoint/manifest.json)。\n'
               '- [操作账本](counter.json)、[授权关闭](authorization_closure.json)、[整体进程退出](supervisor.supervisor.json)、[读取进程退出](reader.supervisor.json)。\n'
               '- [只读收口核验](verification.json)、[独立审查](review.md)、[本次资格](numeric_qualification.json)。\n\n'
               '使用verify_closed.py --current-docs进行标准库只读复核；滚动文档后续推进后省略--current-docs，仍核对本次快照。'
               '该脚本只做JSON／文件摘要／关闭凭证检查，不再次加载张量或运行模型。已消耗的run_gate入口不得再次执行。'
               '本可交付阶段结束后暂停汇报。\n')
    (HERE / '结果说明.md').write_text(report, encoding='utf8')
    write(HERE / 'numeric_qualification.json', dict(stage_id='B2-SCOPE-18', numeric_restore_verified=True,
          live_component_restore_verified=True, state_digest=a['state_digest'],
          checkpoint_manifest_sha256=sha(HERE / 'checkpoint/manifest.json'),
          physical_resume_verified=False, next_update_equivalence_verified=False, training_admitted=False,
          formal_updates=0, new_experience=0, physical_episodes=0, cumulative_dynamic=245,
          full_B2_accepted=False, C_accepted=False, independent_tests=0, automatic_tracking='PAUSED'))
    pending = {}
    for name, pin in reg['before_documents'].items():
        if name == 'AGENTS.md':
            continue
        path = ROOT / name
        assert sha(path) == pin, 'Concurrent edit ' + name
        rel = os.path.relpath(HERE, path.parent).replace('\\', '/')
        links = f'[本次恢复结果]({rel}/结果说明.md)、[独立读取回执]({rel}/reader_reply.json)、[资格与边界]({rel}/numeric_qualification.json)。'
        block = '<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2第3项；任务：B2-SCOPE-18旧预热状态恢复数值验证，已完成。** ' + body + '\n\n' + links + ' 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        text, count = re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->', lambda m: block,
                             path.read_text(encoding='utf8'), count=1, flags=re.S)
        assert count == 1
        if name == '项目进度跟踪.md':
            text = text.replace('## 当前状态\n', '## 当前状态\n\n2026-10-09当前：' + summary + ' ' + capability + ' ' + scope + '\n\n以下保留此前时点：\n', 1)
            text, count = re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',
                f'| B.2 小规模学习与评价包 | 待验收；SCOPE-18旧预热组件恢复数值验证通过 | [结果]({rel}/结果说明.md) | 续训入口与下一更新待验证；原8回合成功／本路线正式更新0 |', text, flags=re.M)
            assert count == 1
            tasks = [('1 开发适用性', '四点联合开发范围保持，未扩展完整范围'),
                     ('2 统一闭环/SAC接口', '旧预热封套保存与独立组件恢复已验证；可训练V4Chain接入仍待'),
                     ('3 动态闭环/成本', scope), ('4 B1', '已有成果保留，不扩大验收'),
                     ('5 B2与批量评价', '原初始评价4/4及预热4/4成功；训练后评价未执行'),
                     ('6 普通残差SAC', 'SCOPE18零起点、19300行重建及独立组件恢复通过；下一步优化等价与正式训练未执行'),
                     ('7 阶段与进展约束', '仍在B.2第3项；完整B.2/C未验收，C物理接入暂缓'),
                     ('8 正式证据与展示', '新增恢复数值证据；独立测试0；旧失败、覆盖缺口保持')]
            text = section(text, '## 原八项任务对应', '| 原任务 | 当前对应 |\n|---|---|\n' + '\n'.join(f'| {x} | {y} |' for x, y in tasks))
            start = text.index('## 当前风险和准入门')
            end = text.index('下表保留历史限制', start)
            text = text[:start] + '## 当前风险和准入门\n\n' + limits + '\n\n' + capability + '\n\n' + next_task + '\n\n' + text[end:]
            text = section(text, '## 下一项交付', next_task + '\n\n' + scope + '\n\n' + links)
            text += '\n### 2026-10-09｜B2-SCOPE-18旧预热恢复数值验证\n\n' + body + '\n\n' + links + ' 本交付阶段结束后暂停汇报。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name == '项目交付总览.md':
            text = text.replace('## 快速查找\n\n', '## 快速查找\n\n当前恢复验证结果：[B2-SCOPE-18](' + rel + '/结果说明.md)。\n\n', 1)
            text = text.replace('## 基线与接口交付\n\n', '## 基线与接口交付\n\n### B2-SCOPE-18｜旧预热恢复数值验证（2026-10-09）\n\n' + body + '\n\n' + links + '\n\n使用：verify_closed.py只读复核，不加载张量；新检查点须经过后续训练入口接入与新准入才能用于续训。\n\n', 1)
        elif name == '研究推进计划_当前版.md':
            start = text.index('### B.2 小规模学习与评价包')
            end = text.index('\n1. 先在', start)
            text = text[:start] + '### B.2 小规模学习与评价包\n\n2026-10-09当前：' + summary + ' ' + capability + ' ' + next_task + ' ' + scope + ' 以下原阶段要求保留。\n' + text[end:]
        elif name.startswith('deliverables/'):
            additions = {'## 一、本月综合摘要': body, '## 二、关键数字与证据': table + '\n' + links,
                         '## 三、负结果与限制': limits + ' 既有文件访问及导入误拦截失败保留；本次仅解除组件恢复的数值不确定性。',
                         '## 四、图表与讲稿': '证据链：旧零检查点＋4份旧预热 → 父进程重建并保存 → 独立进程读入＋从原档案复算 → 完整摘要及组件读回一致。\n\n讲稿：“仍在B.2第3项。本次完成了旧预热状态的保存与独立恢复验证，19,300行数据可以保留使用，不需要重跑旧预热。接下来接入续训并准备训练后评价；本次没有新增训练更新，还不能判断SAC效果。”'}
            for heading, content in additions.items():
                assert text.count(heading) == 1
                text = text.replace(heading + '\n', heading + '\n\n' + content + '\n\n以下保留前轮时点：\n', 1)
            text = section(text, '## 五、下一项', next_task + '\n\n' + scope + '\n\n' + limits)
            text += '\n### 2026-10-09｜B2-SCOPE-18来源记录\n\n' + body + '\n\n' + links + '\n'
        pending[name] = text
    for name, text in pending.items():
        (ROOT / name).write_text(text, encoding='utf8')
    after = {}
    for name in reg['before_documents']:
        dst = HERE / 'document_snapshots' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dst)
        after[name] = sha(dst)
    write(HERE / 'document_update.json', dict(after_documents=after, rolling_documents_may_advance=True))
    print('Five rolling documents updated; six immutable snapshots saved.')


if __name__ == '__main__':
    main()
