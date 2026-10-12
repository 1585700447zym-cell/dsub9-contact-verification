"""Prepare reviewable closeout documents, then publish with concurrent-edit guards."""
import argparse, os, re, shutil, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
KIT = OUT.parent / 'b2_joint_sac_continuation_preparation_20261009'
sys.path.insert(0, str(KIT))
from joint_contract import read, write, sha


def section(text, heading, body):
    text, count = re.subn('(' + re.escape(heading) + r'\n).*?(?=\n## |\Z)',
                         lambda m: m.group(1) + '\n' + body.rstrip() + '\n',
                         text, count=1, flags=re.S)
    if count != 1:
        raise ValueError('Missing section ' + heading)
    return text


def content():
    s = read(OUT / 'execution_summary.json')
    if (s['execution_status'] != 'CLOSED_COMPLETE' or s['completed_physical'] != 9 or
            s['completed_updates'] != 2000 or s['development_continue'] is not False):
        raise ValueError('Unexpected actual closeout results')
    receipts = [read(OUT / 'run/chain' / ('online_F50_J0' + str(i)) / 'status.json') for i in range(1, 5)]
    online = s['episodes'][:4]
    if any(r['committed'] != e['control_cycles'] or r['discarded'] or r['evicted']
           for r, e in zip(receipts, online)):
        raise ValueError('Unexpected publication receipt')
    published = sum(r['committed'] for r in receipts)
    if published != 21671:
        raise ValueError('Publication total differs')
    date = s['closeout_date']
    summary = ('B2-SCOPE-20四点普通SAC续训、匹配评价与独立恢复物理复现已完成并关闭。'
               '新增9/9回合全部成功、仿真有效且真实停稳，无硬保护或参考故障；正式更新尝试／完成2000／2000批。')
    effect = ('F0与F2000同四点均4/4成功；平均惩罚任务耗时8.9060→8.6595秒，改善2.77%，'
              '未达到预登记的10%开发继续条件。J02改善48.39%，J01变慢39.29%，J03改善0.30%，J04变慢0.14%。'
              '结果支持运行链完成和有限开发点功能保持，尚不支持预期整体效率收益。')
    capability = ('实际可训练预热链保存与独立恢复门通过后才开始在线采集；四个在线回合分别发布后完成500批更新，'
                  'actor／critic／temperature／target各2000。最终完整运行状态独立恢复摘要一致，J01轨迹、动作、'
                  '转移、事件、结果、停稳记录和峰值逐值一致。未额外执行恢复后的下一次梯度更新等价试验。')
    scope = (f'复用原F0评价4与预热4（19300行），不重跑旧8回合；新在线发布{published}行。'
             '实际48878控制周期／488780物理子步／36751策略调用，整体监督2478.02秒（41.30分钟）；'
             '构造8／张量读取3／保存2／档案重建28（旧预热20＋新在线8）。累计动态254，'
             '一次授权已消费关闭，不重试、不结转；自动跟踪PAUSED，当前无新训练准入。')
    limits = ('当前仍在B.2第3项“普通SAC训练与真实任务评价”。仅四个固定±75μm／±0.25°已使用开发点、'
              '一个训练种子；完整B.2/C未验收，独立测试0。原3处逐profile接触覆盖缺口及事后开发覆盖修订保持，'
              '不能由本轮成功推断连续姿态／联合范围或任意策略安全，也不能直接归因本轮效率未达标于这些缺口。')
    next_task = ('下一项（待开始）：只读取现有F0/F2000同点档案，按阶段分解任务时间、搜索路径、接触载荷、'
                 '四维请求与实际命令、动作权限及奖励，优先解释J01退化与J02改善为何方向相反。'
                 '提交可定位的原因证据和是否值得修改的路线决定；不加载模型或评分critic，新增物理／推理／更新0，'
                 '不改10%判据、不补跑旧预算。完成离线证据后再决定是否形成新的有限候选。')
    body = '\n\n'.join((summary, effect, capability, scope, limits, next_task))
    comparison = '| 开发点 | F0任务耗时（秒） | F2000任务耗时（秒） | 耗时改善 |\n|---|---:|---:|---:|\n'
    for r in s['comparison']:
        comparison += f'| {r["case_id"]} | {r["F0_penalized_s"]:.3f} | {r["F2000_penalized_s"]:.3f} | {100*r["relative_improvement"]:+.2f}% |\n'
    comparison += '| 四点均值 | 8.9060 | 8.6595 | +2.77%（未达10%） |\n'
    numbers = ('| 项目 | 本轮实际结果 |\n|---|---|\n'
               '| 新物理回合 | 在线4＋最终匹配评价4＋独立恢复J01复现1；9/9成功有效停稳 |\n'
               '| 正式更新 | 2000尝试／2000完成；四个优化组件各2000，无更新错误 |\n'
               f'| 新发布经验 | {published}行；旧预热19300行另列，评价／复现不入池 |\n'
               '| 实际控制／子步／策略调用 | 48878／488780／36751 |\n'
               '| 构造／张量读取／保存／档案重建 | 8／3／2／28（旧预热20＋新在线8） |\n'
               '| 整体监督耗时 | 2478.02秒；最终reader373.86秒，含物理复现 |\n'
               '| 累计动态／自动跟踪 | 254／PAUSED；一次授权关闭，无新训练准入 |\n'
               '| 开发继续／完整B.2／C／独立测试 | 未满足／未验收／未验收／0 |\n')
    report = '# B2-SCOPE-20｜普通SAC四点续训、匹配评价与关闭结果\n\n'
    report += '当前阶段：B.2第3项；本次执行及结果整理已完成，完整B.2仍待验收。\n\n' + body
    report += '\n\n## 同点开发评价\n\n' + comparison
    report += ('\nF0为同配置、同种子、零更新随机初始化演员的确定性策略，动作并非全零；F0不是纯B2。'
               '本轮比较检验该固定边界普通SAC的学习前后变化，不证明F2000优于纯B2或C机制。'
               'F0四份评价从SCOPE13按hash继承，F2000四份评价使用同一冻结最终检查点。'
               '指标沿用普通任务失败26秒罚时；本轮四点均成功，故惩罚均值就是成功任务耗时均值。'
               '任务耗时不包含审核停稳尾段，不等于程序墙钟或档案终止时间。'
               '总体只减少0.2465秒，点间变化明显；单种子、四个已用点无法给出稳定泛化收益结论。\n')
    report += '\n## 实际运行与计数\n\n' + numbers
    report += ('\n保留四个在线中间策略的全部尝试；在线4/4成功不与最终评价4/4混成最终成功率。'
               '独立恢复物理回合只验证复现，不增加性能样本。更新完成数来自持久journal的2000组attempt／complete，'
               'update_attempt.json的1999是最后事务开始前快照，不能作为最终完成数。\n\n'
               'counter.json记录预约／尝试开销：130500控制周期、1305000子步、130509观察和130500策略调用为逐回合最大值预约，'
               '不是实测执行量；实际轨迹量另列。全部预约额度消费关闭、未用可执行余额0，并不意味着实测周期等于上限。'
               '实际9回合、2000更新和辅助8／3／2／28均在授权内完成；未启动重试。\n')
    report += '\n## 保存恢复证据与限制\n\n'
    for label, title in (('warm', '预热链'), ('final', '最终链')):
        request = read(OUT / 'run' / (label + '.request.json'))
        reply = read(OUT / 'run' / (label + '.reply.json'))
        if request['state_digest'] != reply['state_digest']:
            raise ValueError('Reader digest differs')
        report += f'{title}父进程与独立reader完整运行状态摘要：`{request["state_digest"]}`。\n\n'
    report += ('状态核对覆盖模型、优化器、温度、回放、终末边界、随机流和适配器运行字段。'
               '最终J01的8组物理字段逐值一致：trace、actions、transitions、outcome、controller_events、events、stop_samples、peaks。'
               '完整归档字节不同包含时间戳等管理信息，不把文件hash一致当作复现要求。'
               '最终检查点已保存在run/checkpoints/final；本次收口审核仅读取字节hash／JSON／压缩档案，不再加载张量或调用科学库。\n')
    report += '\n## 历史证据、审核与使用\n\n'
    report += ('SCOPE13文件访问失败、SCOPE16导入失败、SCOPE10原覆盖不足以及所有旧关闭记录保持原样。'
               'SCOPE19冻结准备检查器在批准执行后仍断言“candidate not executed”，已只读复现为历史检查器适用时点限制。'
               '不删合法claim、不改旧脚本或重封存：本次verify_closed.py先核对SCOPE18及更早3491个成员，'
               '再直接核对SCOPE19的55个冻结成员、2655输入和当前一次claim及关闭记录，共保留3546个旧封存成员。'
               '独立审查对该替代核验路径及实际关闭结果另行记录。\n\n'
               '启动日志中的解释器定位提示、Matplotlib字体缓存权限警告保留；实际运行exit0，未造成运行失败。'
               '不将本轮成功外推为任意文件故障容错。\n\n'
               '证据：[原始结果](assessment.json)、[汇总](execution_summary.json)、[更新journal](run/chain/update_journal.jsonl)、'
               '[关闭记录](authorization_closure.json)、[独立审查](review.md)、[收口核验](verification.json)。\n\n'
               '使用已绑定CPU解释器执行verify_closed.py即可只读核对收口；--current-docs额外核对当下滚动文档。'
               '滚动文档以后推进时省略该开关，历史交付始终绑定document_snapshots。'
               '不要再次调用run_pilot.py或旧数值／物理入口。本交付阶段结束后暂停汇报。\n')
    return date, summary, effect, capability, scope, limits, next_task, body, comparison, numbers, report


def prepare():
    if (OUT / 'document_proposal.json').exists() or (OUT / 'document_update.json').exists():
        raise FileExistsError('Preserve first proposal and published snapshots')
    date, summary, effect, capability, scope, limits, next_task, body, comparison, numbers, report = content()
    reg = read(OUT / 'launch_registration/registration.json')
    running = read(OUT / 'launch_registration/running_document_update.json')
    before = dict(running['after_documents'], **{'AGENTS.md': reg['before_documents']['AGENTS.md']})
    if set(before) != set(reg['before_documents']):
        raise ValueError('Wrong six document inputs')
    pending = {}
    for name, pin in before.items():
        if sha(ROOT / name) != pin:
            raise ValueError('Concurrent edit ' + name)
        if name == 'AGENTS.md':
            continue
        path = ROOT / name
        rel = os.path.relpath(OUT, path.parent).replace('\\', '/')
        links = f'[本次结果]({rel}/结果说明.md)、[原始指标]({rel}/assessment.json)、[独立审查]({rel}/review.md)。'
        block = f'<!-- b2-scope-current -->\n**{date}｜当前阶段B.2第3项；任务：B2-SCOPE-20续训、匹配评价与独立恢复复现，已完成关闭。** ' + body
        block += '\n\n' + links + ' 下方历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        text, count = re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->', lambda m: block,
                             path.read_text(encoding='utf8'), count=1, flags=re.S)
        if count != 1:
            raise ValueError('Missing current marker ' + name)
        if name == '项目进度跟踪.md':
            text = text.replace('## 当前状态\n', '## 当前状态\n\n' + date + '当前：' + summary + ' ' + effect + ' ' + scope + '\n\n以下保留此前时点：\n', 1)
            text, count = re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',
                f'| B.2 小规模学习与评价包 | 待验收；SCOPE-20四点短训／评价／恢复完成 | [结果]({rel}/结果说明.md) | 2000批、最终4/4成功；耗时改善2.77%未达10%，范围／独立评价仍待 |', text, flags=re.M)
            if count != 1:
                raise ValueError('Missing B.2 capability row')
            tasks = [('1 开发适用性', '四个固定联合开发点成功；连续姿态／联合范围仍待'),
                     ('2 统一闭环/SAC接口', '实际训练链保存及两次独立恢复通过；未额外验证下一梯度更新等价'),
                     ('3 动态闭环/成本', '本轮9回合／48878周期／488780子步；监督2478.02秒，累计254'),
                     ('4 B1', '既有成果保留，不扩大验收'),
                     ('5 B2与批量评价', 'F0与F2000各4/4成功；本轮无纯B2新评价，独立测试0'),
                     ('6 普通残差SAC', '实际完成2000批；平均任务耗时改善2.77%未达10%，下一项离线归因'),
                     ('7 阶段与进展约束', '当前仍在B.2第3项；C物理推进暂缓，既有成果保持'),
                     ('8 正式证据与展示', '训练／评价／复现档案与负结果已归档；单种子、开发4点，完整B.2/C未验收')]
            text = section(text, '## 原八项任务对应', '| 原任务 | 当前对应 |\n|---|---|\n' + '\n'.join(f'| {a} | {b} |' for a, b in tasks))
            start = text.index('## 当前风险和准入门')
            end = text.index('下表保留历史限制', start)
            text = text[:start] + '## 当前风险和准入门\n\n' + effect + '\n\n' + limits + '\n\n' + next_task + '\n\n' + text[end:]
            text = section(text, '## 下一项交付', next_task + '\n\n' + scope + '\n\n' + links)
            text += f'\n### {date}｜B2-SCOPE-20四点续训及实际结果收口\n\n' + body + '\n\n' + links + ' 同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。本交付阶段完成后暂停汇报。\n'
        elif name == '项目交付总览.md':
            text = text.replace('当前续训候选：', '本轮续训准备（历史冻结候选，执行已关闭）：', 1)
            text = text.replace('## 快速查找\n\n', f'## 快速查找\n\n最新普通SAC实际结果：[B2-SCOPE-20]({rel}/结果说明.md)。\n\n', 1)
            text = text.replace('## 基线与接口交付\n\n', f'## 基线与接口交付\n\n### B2-SCOPE-20｜四点普通SAC实际续训与匹配评价（{date}）\n\n' + body + '\n\n' + links + '\n\n使用：verify_closed.py只读核验；完整检查点位于该交付run/checkpoints/final。当前授权已关闭。\n\n', 1)
            text = re.sub(r'^\| 最新真实学习与冻结评价 \|.*$',
                          f'| 最新真实学习与冻结评价 | [SCOPE-20结果]({rel}/结果说明.md) | 2000批、最终4/4成功、独立复现一致；改善2.77%未达10% |', text, flags=re.M)
        elif name == '研究推进计划_当前版.md':
            start = text.index('### B.2 小规模学习与评价包')
            end = text.index('\n1. 先在', start)
            text = text[:start] + '### B.2 小规模学习与评价包\n\n' + date + '当前：' + body + ' 以下原阶段要求保留。\n' + text[end:]
        elif name.startswith('deliverables/'):
            text = re.sub(r'^统计截至：.*$', f'统计截至：{date}（北京时间，B2-SCOPE-20执行及结果收口）。实时状态见[项目进度跟踪](../../../项目进度跟踪.md)，9月材料保留历史口径。', text, count=1, flags=re.M)
            additions = {'## 一、本月综合摘要': body,
                         '## 二、关键数字与证据': numbers + '\n' + comparison + '\n' + links,
                         '## 三、负结果与限制': effect + '\n\n' + limits + '\n\n历史文件访问／导入失败保持；本轮运行成功与效率未达标分别记录。',
                         '## 四、图表与讲稿': comparison + '\n讲稿：“仍在B.2第3项，四点普通SAC已完成2000批训练和真实评价，最终4/4成功，独立恢复复现一致。平均用时改善2.77%，未达到10%继续条件；接下来先离线解释一快一慢的原因，尚未完成完整B.2或进入C的新实验。”'}
            for heading, addition in additions.items():
                if text.count(heading) != 1:
                    raise ValueError('Wrong monthly section')
                text = text.replace(heading + '\n', heading + '\n\n' + addition + '\n\n以下保留前轮时点：\n', 1)
            text = section(text, '## 五、下一项', next_task + '\n\n' + scope + '\n\n' + limits)
            text += f'\n### {date}｜B2-SCOPE-20来源记录\n\n' + body + '\n\n' + links + '\n'
        pending[name] = text
    (OUT / '结果说明.md').write_text(report, encoding='utf8')
    proposals = {}
    for name, text in pending.items():
        dst = OUT / 'document_proposals' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text, encoding='utf8')
        proposals[name] = sha(dst)
    write(OUT / 'document_proposal.json', dict(stage_id='B2-SCOPE-20', before_documents=before,
          proposed_documents=proposals, report_sha256=sha(OUT / '结果说明.md'), publisher_sha256=sha(__file__)))
    print('Prepared result report and five document proposals; current documents unchanged.')


def publish():
    if (OUT / 'document_update.json').exists():
        raise FileExistsError('Never overwrite published snapshots')
    proposal = read(OUT / 'document_proposal.json')
    review = read(OUT / 'review_resolution.json')
    if review['status'] != 'RESOLVED' or review['open_critical'] or review['open_important']:
        raise PermissionError('Unresolved execution closeout review')
    if sha(__file__) != proposal['publisher_sha256'] or sha(OUT / '结果说明.md') != proposal['report_sha256']:
        raise ValueError('Reviewed closeout changed')
    for name, pin in proposal['before_documents'].items():
        if sha(ROOT / name) != pin:
            raise ValueError('Concurrent edit ' + name)
    for name, pin in proposal['proposed_documents'].items():
        if sha(OUT / 'document_proposals' / name) != pin:
            raise ValueError('Reviewed proposal changed ' + name)
    for name in proposal['proposed_documents']:
        shutil.copyfile(OUT / 'document_proposals' / name, ROOT / name)
    after = {}
    for name in proposal['before_documents']:
        dst = OUT / 'document_snapshots' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dst)
        after[name] = sha(dst)
    write(OUT / 'document_update.json', dict(stage_id='B2-SCOPE-20', before_documents=proposal['before_documents'],
          after_documents=after, rolling_documents_may_advance=True, authorization_status='CLOSED', next_task_started=False))
    print('Published five documents and six snapshots; no additional scientific execution.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('prepare', 'publish'))
    args = parser.parse_args()
    prepare() if args.mode == 'prepare' else publish()
