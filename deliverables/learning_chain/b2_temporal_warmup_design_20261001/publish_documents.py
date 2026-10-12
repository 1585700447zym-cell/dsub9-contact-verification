"""Integrate the bounded preparation into the project's existing rolling docs."""
import re
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
S='deliverables/learning_chain/b2_temporal_warmup_design_20261001'
summary=f'**下一修复方案与采样器准备完成（2026-10-01）：** [100ms时间相关预热方案]({S}/修复方案.md)已明确。8份归档显示：旧预热100ms窗口X平均请求均方根0.0792，B两失败约0.966/0.937；正负X初始120维观测相同，不能使用孔中心真值纠偏。[归档证据及图]({S}/archive_analysis.json)、[最终18项协议]({S}/final_green_protocol.json)通过；保持内核、权限清零、完整计数校验已准备，尚未接通物理入口。拟新2ms/100ms预热配对预检最多8动态/0训练，参数和停止规则明确，但未签发执行资格；本阶段物理/网络前向/优化0，累计动态仍60，旧余2/7/19与2000批不使用，PAUSED，B.2未完成。'

def replace_one(text,pattern,replacement):
    text,n=re.subn(pattern,lambda m:replacement,text,count=1,flags=re.M)
    if n!=1:raise ValueError('Expected one existing document section: '+pattern)
    return text

p=ROOT/'项目进度跟踪.md';t=p.read_text(encoding='utf-8')
if '下一修复方案与采样器准备完成' in t:raise FileExistsError('Already published')
t=t.replace('## 当前状态\n\n','## 当前状态\n\n'+summary+'\n\n',1)
t=replace_one(t,r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；下一修复方案及时间相关预热内核准备完成 | [方案与归档图]({S}/修复方案.md)、[18协议]({S}/final_green_protocol.json)；旧降率候选0/2已测成功，失败保留 | 新2ms/100ms配对预检入口未接、8动态/0训练仅为方案；效果未验证，最终/恢复/独立研究证据仍缺 |')
t=replace_one(t,r'^\| 6 普通残差SAC \|.*$',f'| 6 普通残差SAC | 降率候选未保持初始4/4；下一100ms时间相关预热方案及18协议内核准备完成，尚未接执行入口，实际物理/前向/优化0；B.2未完成 |')
t=replace_one(t,r'^\| 修复归因与验收范围 \|.*$',f'| 修复归因与验收范围 | 8归档显示预热100ms请求相互抵消而B持续贴边；初始正负X观测同一，唯一训练根因未隔离 | 先比较2ms/100ms预热覆盖，不使用孔中心真值，不以请求持续性冒称物理覆盖或策略修复；[具体方案]({S}/修复方案.md) |')
t=re.sub(r'## 下一项交付\n.*?(?=## 追加式阶段记录)',f'## 下一项交付\n\n[下一修复方案与采样器准备]({S}/修复方案.md)已完成，按用户要求在此节点汇报。下一实际工作为新入口接入、资格/预算/档案与恢复验证，再执行经登记的2ms/100ms配对预检；拟最多8动态、0训练，当前未启动。保持2ms学习转移和全部共同阈值，不自动进入学习阶段。\n\n累计动态仍60，旧余2、7、19/2000不结转，自动跟踪PAUSED；唯一根因和候选效果未证明，B.2未完成。\n\n',t,count=1,flags=re.S)
t=t.replace('## 追加式阶段记录\n\n',f'## 追加式阶段记录\n\n### 2026-10-01 B.2｜时间相关预热下一方案与采样器准备\n\n{summary}\n\n- 旧预热341个完整100ms活动窗口的四轴均无绝对均值≥0.8；B两个失败点的X窗口均达到该持续幅度。此为保存请求统计，不是危险概率或反事实轨迹。\n- 独立审查暴露准备内核的不可达恢复状态，先补3项失败反例，再修复块起点/活动计数一致性，最终18项通过；旧生产与封存未改。\n- 提供明确的对照公平性、PCG状态共同恢复、任一保护即停和不自动加训规则；三份滚动文档同步，研究效果未验收。\n\n',1)
p.write_text(t,encoding='utf-8')

p=ROOT/'项目交付总览.md';t=p.read_text(encoding='utf-8')
marker='|---|---|---|\n'
t=t.replace(marker,marker+f'| 下一修复方案：时间相关预热（2026-10-01） | [方案、证据与图]({S}/修复方案.md)、[18协议]({S}/final_green_protocol.json) | 100ms预热内核已准备；2ms控制/策略/学习转移不变，入口未接、无新物理/训练；拟8动态预检未执行，不等于修复成功 |\n',1)
t=replace_one(t,r'^\| 下一项机制与有限预算 \|.*$',f'| 下一项机制与有限预算 | [具体预热方案]({S}/修复方案.md)、[拟议参数]({S}/proposal.json) | 新2ms/100ms两臂配对预检最多8动态/0训练，任一保护即停；需独立接入资格和预算，旧余不结转 |')
t=t.replace('## 基线与接口交付\n\n',f'## 基线与接口交付\n\n### B.2最新准备｜100ms时间相关预热（2026-10-01）\n\n- **交付与使用：** [完整方案]({S}/修复方案.md)、[8份归档统计]({S}/archive_analysis.json)、[请求持续性图]({S}/request_persistence.png)、[最终18协议]({S}/final_green_protocol.json)；只读准备，不是训练/采集入口。\n- **新增能力：** 纯保持内核支持权限清零、阶段切换重抽、周期预算及保存恢复一致性；外部PCG状态需由后续完整检查点共同绑定。\n- **限制：** 无新模型/物理/优化；100ms不是已证实最优，初始观察同一限制保留，拟8动态新配对预检未执行；策略修复和B.2仍未完成。\n\n',1)
p.write_text(t,encoding='utf-8')

p=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';t=p.read_text(encoding='utf-8');M='../../learning_chain/b2_temporal_warmup_design_20261001'
t=t.replace('## 一、本月综合摘要\n\n','## 一、本月综合摘要\n\n'+summary.replace(S,M)+'\n\n',1)
t=t.replace('|---|---|---|\n',f'|---|---|---|\n| 下一修复方案与内核准备 | 8归档、18项纯协议、1张请求持续性图 | 新物理/网络前向/优化0；拟2ms/100ms两臂8动态预检未执行 |\n| 100ms窗口X均方根 | 旧预热0.0792，B正/负X约0.966/0.937 | 动作请求的时间统计，不是状态覆盖率或危险概率 |\n',1)
t=t.replace('## 三、负结果与限制\n\n','## 三、负结果与限制\n\n新100ms预热方案只针对时间相关的数据差异；初始正负X观测完全相同，不能用孔中心真值补策略信息。保持采样器协议通过不代表物理入口已接通或策略修复。准备阶段的恢复计数漏洞已由三项先失败后通过的反例修正。\n\n',1)
t=t.replace('<a id="figures"></a>\n\n',f'<a id="figures"></a>\n\n![请求持续性]({M}/request_persistence.png)\n\n[PNG]({M}/request_persistence.png)/[PDF]({M}/request_persistence.pdf)：20/100/400ms窗口请求持续性的归档对照，没有新增物理轨迹。\n\n当前方案讲稿：“降低actor学习率未恢复初始能力。我们进一步发现，旧预热动作在较长窗口内大多抵消，失败策略却持续同向。下一候选只改变预热的时间持续性，100ms保持采样器通过18项协议，下一步先做新的配对采集预检；尚无修复收益结论。”\n\n',1)
t=re.sub(r'## 五、下一项\n.*?(?=## 六、来源记录)',f'## 五、下一项\n\n[100ms时间相关预热方案]({M}/修复方案.md)和采样器准备完成。下一项接入新2ms/100ms配对预检入口、完整资格与恢复；拟最多8动态/0训练，当前未执行或签发资格。先看双向持续请求及命令作用，任一保护即停；通过也只证明采集机制可用，不自动加训。累计动态60不变，旧余2/7/19与2000批不结转，PAUSED，B.2未完成。\n\n',t,count=1,flags=re.S)
t+='\n2026-10-01时间相关预热方案与内核准备收口：'+summary.replace(S,M)+'\n'
p.write_text(t,encoding='utf-8')
print('Updated the same progress, delivery overview and October monthly documents.')
