"""Record actual authorized startup and maintain the three rolling documents."""
import datetime,json,re
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
s=read(HERE/'run/ledger.json');pins=read(HERE/'execution_pins.json')
now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds')
record=dict(as_of=now,status=s['status'],physical_starts=len(s['attempts']),active=s['active'],
    protocol_tests=149,complete_B_restoration_verified=True,new_training_batches=0,
    **pins,automatic_tracking='PAUSED',b2_complete=False)
with (HERE/'startup_assessment.json').open('x',encoding='utf-8') as stream:
    json.dump(record,stream,ensure_ascii=False,indent=2);stream.write('\n')
S='deliverables/learning_chain/b2_actor_lr_b_eval_20261001'
paragraph=f'**冻结B单独评价已获批并启动（2026-10-01）：** 用户确认上一条完整范围后回复“继续”，本轮独立适配、协议验证与最多4新动态/0训练已授权。[149项相关协议]({S}/related_green_results.json)全过，前向/优化/物理0；[完整B恢复预检]({S}/restoration_preflight.json)一致。独立审查及最终53项封存输入核对通过，[执行资格与授权摘要]({S}/execution_pins.json)已锁定。截至{now}，新动态已预约{len(s["attempts"])}/4，状态{s["status"]}，正在按正X/负X/正Y/负Y顺序评价冻结B500；实际结果见[账本]({S}/run/ledger.json)。任何保护停稳归档后停止余点，故障不重试，训练0；旧7及19/2000不结转，自动跟踪PAUSED，B.2未完成。'
p=ROOT/'项目进度跟踪.md';t=p.read_text(encoding='utf-8')
t=t.replace('## 当前状态\n\n','## 当前状态\n\n'+paragraph+'\n\n',1)
t=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；冻结B单独有限评价已获批并运行 | [149协议]({S}/related_green_results.json)、[B恢复]({S}/restoration_preflight.json)、[运行账本]({S}/run/ledger.json) | 最多4新动态/0训练，保护即停；尚无B物理结论；旧7及19/2000不执行，最终/恢复/独立研究证据未全 |',t,count=1,flags=re.M)
t=t.replace('冻结B单独评价证据已核对，独立范围待确认、入口未适配。','冻结B单独评价已获批，独立入口/149协议/完整恢复通过并运行。',1)
t=re.sub(r'## 下一项交付\n.*?(?=## 追加式阶段记录)',f'## 下一项交付\n\n继续同一已批准的[冻结B有限评价]({S}/README.md)：最多4原开发点，训练0，累计动态至多62，每点含停止尾段最多13000控制周期。任何保护完成停稳审核后停止余点，运行故障不重试；不重复A、不重训、不追加诊断、不使用旧7或19/2000。执行结束独立复核档案并同步三份滚动文档后暂停汇报。\n\nB须4/4才算保持历史初始四点成功数，仍不证明2500批在线修复、独立泛化或B.2完成；未执行点不得计成成功或已测失败。\n\n',t,count=1,flags=re.S)
t=t.replace('## 追加式阶段记录\n\n','## 追加式阶段记录\n\n### 2026-10-01 B.2｜独立B评价授权、适配与启动\n\n'+paragraph+'\n\n- 新实现只在阶段目录，原1011源/4149历史封存保持；独立53输入封存。首25缺行为反例→25绿，相关149绿；封存预检无实际前向/优化/物理。用户授权覆盖适配、验证、实际有限评价，不另拆计算审批。\n\n',1)
p.write_text(t,encoding='utf-8')
p=ROOT/'项目交付总览.md';t=p.read_text(encoding='utf-8')
t=t.replace('|---|---|---|\n',f'|---|---|---|\n| 已冻结B单独评价实际执行（2026-10-01） | [入口与范围]({S}/README.md)、[149协议]({S}/related_green_results.json)、[启动]({S}/startup_assessment.json)、[账本]({S}/run/ledger.json) | 用户批准最多4新动态/0训练；完整恢复/审查/封存通过并启动，结果待收口；旧7及19/2000保持未用 |\n',1)
p.write_text(t,encoding='utf-8')
p=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';t=p.read_text(encoding='utf-8');M='../../learning_chain/b2_actor_lr_b_eval_20261001'
t=t.replace('## 一、本月综合摘要\n\n','## 一、本月综合摘要\n\n'+paragraph.replace(S,M)+'\n\n',1)
t=t.replace('|---|---|---|\n',f'|---|---|---|\n| 独立B评价启动 | 149协议通过、完整B恢复一致，新预约{len(s["attempts"])}/4 | 本轮已授权0训练/最多4动态，累计最多62；尚无最终物理结论 |\n',1)
t=t.replace('单独B评价当前仅完成只读证据复核，未获得新执行资格或物理结果；不能把范围讨论计为修复成果或预算授权。','单独B评价现已获批、适配/协议/完整恢复通过并运行；尚无最终物理结果，不能把实现通过计为修复收益。',1)
t=re.sub(r'## 五、下一项\n.*?(?=## 六、来源记录)',f'## 五、下一项\n\n继续同一已批准B500四点有限评价，保护停稳归档后停止余点，故障不重试，训练0。结束审核全部尝试并更新本月结果；旧7及19/2000不结转。4/4只证明初始成功数保持，不代表2500批在线修复或独立泛化。\n\n补充讲稿：“冻结B的独立评价已获批并启动；149项协议及完整恢复通过，我们将以实际物理结果判断候选，所有保护失败和未执行点保留。”\n\n',t,count=1,flags=re.S)
t+='\n2026-10-01独立B评价启动：'+paragraph.replace(S,M)+'\n'
p.write_text(t,encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
