"""Maintain one bounded stage status in the five rolling project documents."""
from pathlib import Path
import json,datetime,re,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed; do not replace the closing status')
paths=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
stamp=datetime.datetime.now().isoformat(timespec='minutes')
q=json.loads((OUT/'qualification.json').read_text(encoding='utf8'))
ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf8')) if (OUT/'run/ledger.json').exists() else dict(status='qualified_preparing',episodes=[],formal_updates=0,formal_update_attempts=0,policy_calls=0,per_branch_updates={'F50':0,'S50':0})
if ledger['status'] in ('complete','controlled_stop','error'):raise RuntimeError('Closed; use the closing document procedure')
done=sum(e['status']=='finished' for e in ledger['episodes']);attempts=len(ledger['episodes'])
recorded_calls=sum(e.get('policy_calls',0) for e in ledger['episodes'])
base='deliverables/paper_comparison/v4_learning_requalification_20261006/'
for name in paths:
    path=ROOT/name;s=path.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else ''
    block=f'''<!-- v4-requalification-current -->
**PC-06新控制来源学习pilot：{ledger['status']}（截至{stamp}），B.2未验收。** 新资格v2已签发，441关联离线检查、一次限定独立审查0 Critical/Important/Minor、独立进程完整数值恢复通过。全部输入1057项、新共同来源904项；仅两个登记源变更，不扩展137维/4维动作、网络、算法、几何或保护。

新启动{attempts}/28动态，完成{done}，累计{145+attempts}/173；正式更新尝试{ledger['formal_update_attempts']}，完成{ledger['formal_updates']}/4000（F{ledger['per_branch_updates']['F50']}/S{ledger['per_branch_updates']['S50']}），已记录物理策略控制调用至少{recorded_calls}。执行中回合仅周期性记录下界，最终以完整档案为准。只用新数据/同起点新网络；有效停稳普通TASK_FAILURE可学，源/仿真/参考/读取故障整轮停，硬保护停对应分支。旧26动态/4000批保持关闭，自动跟踪PAUSED。

本轮按每组4预热、4在线×500批、5冻结开发评价、1独立代表复现执行；五点均为开发点，独立测试0。旧B2来源指纹不同，保留原档案作为历史上下文，不改标签形成新配对优势。本pilot运行通过与策略更好分别判断；完成后还需当前共同版本B2配对及未用范围/重复证据。

[新计划]({prefix}docs/superpowers/plans/2026-10-06-v4-learning-requalification.md)、[资格]({prefix}{base}qualification.json)、[实时账本]({prefix}{base}run/ledger.json)、[本轮审查]({prefix}{base}review.md)。阶段内部持续推进，结束后据实际学习/评价结果收口。
<!-- /v4-requalification-current -->'''
    pattern=r'<!-- v4-requalification-current -->.*?<!-- /v4-requalification-current -->'
    if re.search(pattern,s,re.S):s=re.sub(pattern,lambda _:block,s,flags=re.S)
    else:
        index=s.index('\n')+1;s=s[:index]+'\n'+block+'\n\n以下保留此前时点记录，其下一项以上述当前状态为准。\n'+s[index:]
    path.write_text(s,encoding='utf8',newline='\n')
print(f'rolling status {ledger["status"]}: {attempts} starts/{done} completed, {ledger["formal_updates"]} batches')
