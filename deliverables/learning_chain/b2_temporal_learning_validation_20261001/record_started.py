"""Record current authorized execution in the same rolling documents."""
from pathlib import Path
import re,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
S='deliverables/learning_chain/b2_temporal_learning_validation_20261001';M='../../learning_chain/b2_temporal_learning_validation_20261001'
summary=f'**100ms预热学习验证已启动（2026-10-01）：** 用户明确要求直接做到验证结束。174项相关协议通过，独立审查3项Important已逐项反例修复；新资格已封存，共同零更新四点评价正在进行。候选C先执行至2500批和固定/独立恢复四点，再A同预算对照；原学习率3e−4、2ms策略/控制与全部保护阈值保持。上限新增24动态/5000正式批，此前68、累计上限92；任何保护/故障停止余量，不重试。前项预热原始false权限与committed0不改写，本阶段明确新资格重审后单独入池；旧余2/7/19及2000批不使用。自动跟踪PAUSED，学后效果及B.2仍待验证。[具体判据]({S}/验证方案.md)、[实际账本]({S}/run/ledger.json)。'
def insert(p,anchor,text):
    t=p.read_text(encoding='utf-8');assert '**100ms预热学习验证已启动' not in t
    assert anchor in t;t=t.replace(anchor,anchor+'\n'+text+'\n',1);p.write_text(t,encoding='utf-8')
insert(ROOT/'项目进度跟踪.md','## 当前状态\n',summary)
insert(ROOT/'项目当前入口.md','# D-sub9 项目当前入口\n',summary)
insert(ROOT/'项目交付总览.md','## 基线与接口交付\n','### B.2｜100ms预热学习有限验证（2026-10-01）\n\n'+summary)
insert(ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md','## 一、本月综合摘要\n',summary.replace(S,M))
p=ROOT/'项目交付总览.md';t=p.read_text(encoding='utf-8');t=t.replace('| 100ms预热机制的真实有限预检 |','| 上一预检（历史）：100ms预热机制 |',1)
t=t.replace('| 我要找什么 | 优先打开 | 使用提醒 |\n|---|---|---|',f'| 我要找什么 | 优先打开 | 使用提醒 |\n|---|---|---|\n| 当前100ms预热学习验证 | [判据]({S}/验证方案.md)、[账本]({S}/run/ledger.json) | 已授权并启动，结果待定；24新增动态/5000批上限，不代表已验证收益 |',1);p.write_text(t,encoding='utf-8')
p=ROOT/'项目进度跟踪.md';t=p.read_text(encoding='utf-8');t=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；100ms预热学习验证已启动 | [判据]({S}/验证方案.md)、[实际账本]({S}/run/ledger.json)；24新增动态/5000正式批上限 | 初始能力/候选学后保持/独立恢复/对照尚待实际判定 |',t,count=1,flags=re.M)
t=re.sub(r'## 下一项交付\n.*?(?=\n## )','## 下一项交付\n\n直接完成已批准的100ms预热有限学习验证，达到预登记终点或保护/故障停止；形成实际结果和明确判定后汇报，不追加预算或调参。旧余不结转、PAUSED、独立测试不使用。\n',t,count=1,flags=re.S);p.write_text(t,encoding='utf-8')
p=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';t=p.read_text(encoding='utf-8');t=t.replace('本次新A/C对照：','上一真实预检A/C（历史）：',1);t=t.replace('| 内容 | 实际完成 | 上限与解释 |\n|---|---|---|',f'| 内容 | 实际完成 | 上限与解释 |\n|---|---|---|\n| 100ms预热学习验证 | 已授权并启动，初始四点评价进行中 | 24新动态/5000正式批；C先行，任何保护/故障停止，效果待定 |',1);t+='\n2026-10-01｜100ms预热有限学习验证启动：'+summary.replace(S,M)+'\n';p.write_text(t,encoding='utf-8')
print(json.dumps(dict(documents_updated=4,scope='24_new_dynamic_5000_batches',effect='pending')))
