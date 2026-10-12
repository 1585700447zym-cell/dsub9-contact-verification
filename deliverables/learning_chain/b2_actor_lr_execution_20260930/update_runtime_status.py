"""Read the existing ledger only; no model, optimizer or physical work."""
import datetime
import hashlib
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent;RUN=HERE/'run'
STAGE='deliverables/learning_chain/b2_actor_lr_execution_20260930'
read=lambda path:json.loads(path.read_text(encoding='utf-8'))
s=read(RUN/'ledger.json');proof=read(RUN/'a_reproduction.json');frozen=read(RUN/'frozen.json')
if proof.get('learning_exact') is not True:raise ValueError('Exact A proof missing')
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
count=lambda kind,role:sum(r['units'] for r in s['attempts'] if r['kind']==kind and r['branch']==role)
formal={r:count('formal',r) for r in ('A','B')};physical={r:count('physical',r) for r in ('A','B')}
summary=f'**actor率有限对照执行中（2026-10-01）：** 截至{now}，[A500精确复现]({STAGE}/run/a_reproduction.json)已通过，正式A/B已尝试{formal["A"]}/{formal["B"]}批，固定检查点见[冻结记录]({STAGE}/run/frozen.json)。真实验证4事务/8测试状态已通过；当前账本阶段{s["phase"]}，新物理A/B已启动{physical["A"]}/{physical["B"]}，诊断状态initial/A/B已收费{count("diagnostic","initial")}/{count("diagnostic","A")}/{count("diagnostic","B")}。[实时账本]({STAGE}/run/ledger.json)保留所有尝试；尚无最终策略收益结论，B.2未完成，旧余19/2000不执行，自动跟踪PAUSED。'
progress=ROOT/'项目进度跟踪.md';text=progress.read_text(encoding='utf-8')
text=re.sub(r'^\*\*actor率有限对照已获批并启动（2026-10-01）.*$',summary,text,count=1,flags=re.M)
text=text.replace('A500精确复现→B500→分布与固定评价，尚无新效果','A500已精确复现、B500已冻结；分布与固定物理评价执行中，尚无新效果',1)
text=text.replace('A复现进行中。未取得新策略效果','A500已精确复现，B500已冻结；固定评价执行中。未取得新策略效果',1)
text=text.replace('真实数值验证已通过，A500精确学习复现→B500→768固定状态分布诊断→最多8次冻结开发评价',
    '真实数值验证及A500精确复现通过，B500已冻结；继续768固定状态分布诊断→最多8次冻结开发评价',1)
progress.write_text(text,encoding='utf-8')
overview=ROOT/'项目交付总览.md';text=overview.read_text(encoding='utf-8')
text=text.replace('A精确复现仍在执行，尚无物理评价或策略收益','A500已精确复现、B500冻结；固定评价执行中，策略收益未知',1)
overview.write_text(text,encoding='utf-8')
monthly=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';text=monthly.read_text(encoding='utf-8')
text=re.sub(r'^\*\*actor率有限对照已获批并启动（2026-10-01）.*$',summary.replace(STAGE,'../../learning_chain/b2_actor_lr_execution_20260930'),text,count=1,flags=re.M)
text=text.replace('| 正式固定数据学习 | A执行中，B未开始 | A/B各500；A不精确复现即停 |','| 正式固定数据学习 | A500精确复现通过、B500固定冻结，共1000批 | 不加训、不挑选中间策略 |')
text=text.replace('| 分布诊断及物理 | 尚未启动 |',f'| 分布诊断及物理 | 按账本阶段{s["phase"]}执行，启动A/B={physical["A"]}/{physical["B"]} |',1)
text=text.replace('先检查原学习率能否精确复现；修复效果尚未获得新证据。','原学习率500批已精确复现、候选500批已冻结，正在检查固定策略的物理效果。',1)
monthly.write_text(text,encoding='utf-8')
print(json.dumps(dict(as_of=now,phase=s['phase'],status=s['status'],formal=formal,physical=physical)))
