"""Record approved execution and maintain October's same rolling documents."""
import datetime
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent;RUN=HERE/'run'
STAGE='deliverables/learning_chain/b2_actor_lr_execution_20260930'
read=lambda path:json.loads(path.read_text(encoding='utf-8'))
ledger=read(RUN/'ledger.json');proof=read(RUN/'real_validation.json')
if proof.get('passed') is not True:raise ValueError('Passed actual validation required for this startup record')
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
record=dict(date='2026-10-01',as_of=now,candidate_sha256=ledger['candidate_sha256'],authorization_sha256=ledger['authorization_sha256'],
    real_validation_passed=True,synthetic_transactions=proof['synthetic_transactions'],test_forward_states=proof['test_forward_states'],
    first_actor_delta_norm_ratio=proof['first_actor_delta_norm_ratio'],phase=ledger['phase'],status=ledger['status'],
    formal_attempts={role:sum(r['units'] for r in ledger['attempts'] if r['kind']=='formal' and r['branch']==role) for role in ('A','B')},
    physical_starts=sum(r['units'] for r in ledger['attempts'] if r['kind']=='physical'),old_unused_consumed=0,
    automatic_tracking='PAUSED',b2_complete=False)
with (HERE/'startup_assessment.json').open('x',encoding='utf-8') as stream:json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')
summary=f'**actor率有限对照已获批并启动（2026-10-01）：** 用户明确批准[封存候选]({STAGE}/candidate_pin.json)及新上限16合成事务/128测试状态前向、768诊断状态、1000正式批/8动态；[授权]({STAGE}/authorization.json)单独保存。真实数值验证已通过，实际消耗4合成事务/8测试状态，首次actor差分范数比约0.09999992，critic/温度一致、无权限屏蔽/注入回滚/保存恢复与跨分支拒绝通过。[启动快照]({STAGE}/startup_assessment.json)截至{now}，A复现进行中；实时进展见[运行账本]({STAGE}/run/ledger.json)。A必须精确复现才B，评价任何保护完整停稳归档后停止整轮，运行/写盘/输入故障不重试；尚无新策略收益或B.2验收，旧余19/2000不执行，自动跟踪PAUSED。'
progress=ROOT/'项目进度跟踪.md';text=progress.read_text(encoding='utf-8')
text=text.replace('最后更新：2026-09-30。','最后更新：2026-10-01。',1)
text=text.replace('本月统一汇报材料见[2026年9月滚动月报](deliverables/monthly_progress/2026-09/月报素材_2026-09.md)',
    '本月统一汇报材料见[2026年10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)；[9月月报](deliverables/monthly_progress/2026-09/月报素材_2026-09.md)作为截至9月底历史资料保持')
text=text.replace('## 当前状态\n\n','## 当前状态\n\n'+summary+'\n\n',1)
text=re.sub(r'^\| B.2 小规模.*$',f'| B.2 小规模学习与评价包 | 待验收；已批准有限actor率对照，实际执行中 | [数值验证]({STAGE}/run/real_validation.json)、[运行账本]({STAGE}/run/ledger.json)；准备216协议通过，实际验证4事务/8状态通过 | A500精确复现→B500→分布与固定评价，尚无新效果；最终/恢复/独立研究验收仍缺，旧余19/2000不执行 |',text,flags=re.M)
text=re.sub(r'^\| 6 普通残差SAC.*$',f'| 6 普通残差SAC | 独立actor率和严格共同起点/执行协议保持；新预算已明确批准并启动，4真实合成事务/8测试状态验证通过，A复现进行中。未取得新策略效果，B.2未完成；不续用旧19/2000 |',text,flags=re.M)
start=text.index('## 下一项交付');end=text.index('## 追加式阶段记录',start)
text=text[:start]+f'''## 下一项交付

新候选及预算已明确批准，当前继续[既定执行链]({STAGE}/README.md)：真实数值验证已通过，A500精确学习复现→B500→768固定状态分布诊断→最多8次冻结开发评价。任一门失败不重试，A不符不启动B，评价保护停稳归档后停止整轮，不补足、不扩额、不续旧19/2000。自动跟踪仍PAUSED。

仅actor3e-4→3e-5；B须保持原初始4/4能力，500固定数据筛选不证明2500批在线问题已修复或独立泛化。执行结束完整审核原始档案并更新[10月同一份月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)，后续研究阶段另立范围。

'''+text[end:]
text=text.replace('## 追加式阶段记录\n\n','## 追加式阶段记录\n\n### 2026-10-01 B.2｜批准有限actor率对照并启动\n\n'+summary+'\n\n跨月建立10月同一份滚动素材，9月记录不改；实际运行与效果分开记账。\n\n',1)
progress.write_text(text,encoding='utf-8')
overview=ROOT/'项目交付总览.md';text=overview.read_text(encoding='utf-8').replace('最后整理：2026-09-30。','最后整理：2026-10-01。',1)
text=text.replace('汇报素材见[2026年9月滚动月报](deliverables/monthly_progress/2026-09/月报素材_2026-09.md)',
    '汇报素材见[2026年10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)，[9月素材](deliverables/monthly_progress/2026-09/月报素材_2026-09.md)保留历史口径')
marker='| actor率对照执行适配';index=text.index(marker)
text=text[:index]+f'| actor率有限对照已获批并启动（2026-10-01） | [授权]({STAGE}/authorization.json)、[真实验证]({STAGE}/run/real_validation.json)、[启动核验]({STAGE}/startup_assessment.json) | 新预算独立、4事务/8状态数值验证通过；A精确复现仍在执行，尚无物理评价或策略收益 |\n'+text[index:]
text+='\n### 2026-10-01｜有限actor率对照实际执行\n\n'+summary+'\n\n';overview.write_text(text,encoding='utf-8')
monthly=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';monthly.parent.mkdir(parents=True,exist_ok=True)
ms=summary.replace(STAGE,'../../learning_chain/b2_actor_lr_execution_20260930')
with monthly.open('x',encoding='utf-8') as stream:stream.write(f'''# D-sub9｜2026年10月滚动月报素材

统计截至：2026-10-01。10月持续维护同一文件。实时状态见[项目进度跟踪](../../../项目进度跟踪.md)，交付入口见[项目交付总览](../../../项目交付总览.md)；[9月材料](../2026-09/月报素材_2026-09.md)作为此前证据和历史口径保持。

## 一、本月综合摘要

{ms}

## 二、关键数字与证据

| 内容 | 已实际完成 | 上限/限制 |
|---|---|---|
| 真实数值验证 | 4个私有事务、8个测试状态；全部通过 | 16事务/128状态上限，未用成本不自动追加 |
| actor首次更新差分 | B/A范数比0.09999992，critic/温度一致 | 只验证实现，不能视为策略收益 |
| 正式固定数据学习 | A执行中，B未开始 | A/B各500；A不精确复现即停 |
| 分布诊断及物理 | 尚未启动 | 768诊断状态/最多8动态，既有57累计最多65 |
| 历史未用预算 | 19动态/2000批保持未用 | 不结转，自动跟踪PAUSED |

## 三、负结果与限制

初始过程收到matplotlib用户目录字体缓存权限提示，进程继续并通过真实验证；保留fault.log，不清除或冒称运行故障。真实数据起点和早期500批筛选不能证明原2500批在线危险边界问题已修复；正常失败、保护失败、运行故障和无效仿真分别保留。

## 四、图表与讲稿

尚未新增性能图，9月危险价值/停止图仍标明历史计算日期。当前讲稿：“仅降低actor更新速率的对照已启动，真实实现验证通过，先检查原学习率能否精确复现；修复效果尚未获得新证据。”

## 五、下一项

继续同一已批准执行链；门失败或保护停止时完整收口，不追加重跑或独立测试。结束后更新本文件的摘要、数字、负结果和讲稿并追加来源。

## 六、来源记录

2026-10-01：用户明确回复“批准”，新授权单独保存；此前两次会话中断发生在实际启动前，只有授权记录，没有run/started/claim，核对后首次启动。{ms}
''')
entry=ROOT/'项目当前入口.md';text=entry.read_text(encoding='utf-8')
text=text.replace('[2026年9月滚动月报素材](deliverables/monthly_progress/2026-09/月报素材_2026-09.md)',
    '[2026年10月滚动月报素材](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)',1)
text=text.replace('原9月16日PPT是历史快照，本次未更新演示稿。','原9月16日PPT与[9月滚动素材](deliverables/monthly_progress/2026-09/月报素材_2026-09.md)是历史资料，10月另维护同一份当月素材，本次未更新演示稿。',1)
entry.write_text(text,encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
