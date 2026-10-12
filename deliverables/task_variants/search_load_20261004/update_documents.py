from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
rel='deliverables/task_variants/search_load_20261004'
summary=f'''<!-- search-load-current -->
**SEARCH载荷修复有限验证已结束（2026-10-04 00:48）：未越力，但仍未插入成功。** 81项相关检查通过；实际1/5动态，负Y150在第二次搜索再次高侧向载荷时因SEARCH_BUDGET_EXHAUSTED正常失败，仿真有效并实际停稳。功能/严格精度均0/1，6718控制周期/67180物理子步，累计120；余4关闭，训练/网络/独立测试0，PAUSED，B.2未完成。

8.486 s新卸载触发并释放XY参考，8.570 s进入第二次搜索；原25 mN越力未重现（全回合峰值24.474139 mN），但仅推进0.239755 mm。进一步定位到Y导纳内部累计纠偏达到500 μm上限，949个SEARCH采样在Fy为正时Y导纳输出0，其中693个总Y命令仍反向；外部参考释放没有同步处理这个内部状态。这是具体机制证据，不是“清零即可成功”的证明。正Y及±X/对准四点本轮未执行。

下一项收窄为导纳积分限幅、搜索命令合成与参考释放的一致性/抗饱和，保持实际运动边界；先形成一个明确方案后有限验证，不直接增大额度、次数或开训。[结果与图]({rel}/结果说明.md)、[机器核对]({rel}/assessment.json)、[失败诊断]({rel}/failure_diagnosis.json)。
<!-- /search-load-current -->'''

def load(n):return (ROOT/n).read_text(encoding='utf-8')
def save(n,s):(ROOT/n).write_text(s,encoding='utf-8',newline='\n')
def section(s,h,body):
    a=s.index(h)+len(h);b=s.find('\n## ',a)
    return s[:a]+'\n\n'+body.strip()+'\n'+(s[b:] if b>=0 else '')

docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
for n in docs:
    s=load(n);block=summary.replace(']('+rel,'](../../../'+rel) if n.startswith('deliverables/') else summary
    s,count=re.subn(r'<!-- (?:functional-b2|search-load)-current -->.*?<!-- /(?:functional-b2|search-load)-current -->',lambda _:block,s,count=1,flags=re.S)
    assert count==1,n;save(n,s)

next_text=f'先处理SEARCH中导纳累计纠偏额度、合成命令与参考重置的一致性。已确认Y内部+500 μm限幅抑制正向卸载，而螺旋仍可能反向顶压；需明确重新定参考时内部积分如何重设/抗饱和，同时保留实际运动和参考领先保护。不得仅扩大额度/搜索次数，不重用关闭余4；新方案形成后先有限负Y验证再做共同回归，通过后才重新绑定残差学习接口。见[本轮诊断]({rel}/结果说明.md)。'
n='项目进度跟踪.md';s=load(n)
s=re.sub(r'^\| B\.2 小规模学习与评价包 .*$',f'| B.2 小规模学习与评价包 | 待验收；SEARCH修复未通过功能验证 | [本轮结果]({rel}/结果说明.md) | 负Y无保护但两次搜索耗尽，内部导纳额度问题待处理；新训练0 |',s,flags=re.M)
updates={'1 开发适用性':'当前1.20 mm功能任务负Y新1回合有效停稳、无保护但未插入；新连续域/训练未准入',
 '2 统一闭环/SAC接口':'新LOAD卸载与一次XY控制参考释放会话已实现，真实位姿/速度/保护不重置；导纳内部额度与参考一致性仍待修',
 '3 动态闭环/成本':'本轮1/5动态、6718周期/67180子步，累计120；训练/网络0，余4关闭',
 '5 B2与批量评价':'负Y在新规则下不越力，但第二次高载荷因搜索预算耗尽失败；其余四点未执行，81项相关检查通过',
 '7 阶段与进展约束':'SEARCH载荷触发与参考释放已实现，尚未完成基线功能验证；没有新增残差/约束候选比较',
 '8 正式证据与展示':'本轮1份完整轨迹、对照图、4244采样因果边界、停稳审核和导纳饱和诊断保存；独立测试0、多种子未完成'}
for label,value in updates.items():s=re.sub(r'^\| '+re.escape(label)+r' \|.*$',f'| {label} | {value} |',s,flags=re.M)
a=s.index('## 当前风险和准入门')+len('## 当前风险和准入门');b=s.index('| 项目 | 当前事实 | 解除条件 |',a)
s=s[:a]+'''\n\n**本轮优先风险：** 载荷卸载/参考释放虽使当前负Y不触发保护，但仍未到深度，不能计作成功；其余四个回归点未执行。内部Y导纳累计命令额度500 μm与真实位移不同，饱和后卸载输出为0，参考重置未同步处理内部状态。下一步应审查状态一致性与抗饱和，不能用增大额度或搜索次数掩盖。独立评价/训练资格仍缺失。\n\n下表保留此前学习实验的限制，旧“本轮”参数对应其原实验版本，最新共同任务边界以上文为准。\n\n'''+s[b:]
s=section(s,'## 下一项交付',next_text)
log=f'### 2026-10-04 00:48｜SEARCH载荷卸载/参考释放验证失败收口\n\n81项相关检查通过，一次审查修复原SEARCH边界优先级。实际1/5负Y动态：无保护、有效停稳，但SEARCH_BUDGET_EXHAUSTED，功能0/1；67180物理子步，累计120，余4关闭。定位949个正Fy但Y导纳饱和为0的采样，693个总Y命令仍反向，下一项改为内部额度/参考一致性。实施与有限验证交付完成，效果未通过，B.2未验收、0训练。证据：[结果]({rel}/结果说明.md)、[10月月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n\n'
s=s.replace('## 追加式阶段记录\n\n','## 追加式阶段记录\n\n'+log,1);save(n,s)

n='研究推进计划_当前版.md';s=load(n)
current=f'''## 2026-10-04 00:48：SEARCH卸载实测后的下一修复

本轮SEARCH载荷触发与XY参考释放已实现，81检查通过；实际1/5动态后，负Y在第二次高载荷时搜索预算耗尽，虽无保护仍未插入，余4关闭、累计120。原正Y成功结果保留，本版本正Y/±X/对准未复验。B.2未完成，训练0。[结果及机制证据]({rel}/结果说明.md)。

{next_text}

本轮不再追加物理或SAC训练。下一方案须保持共同任务、保护和各方法公平权限；不能将参考重置或积分清零默认为物理成功。以下为此前修订的历史依据，最新下一项以本节为准。

'''
s=s.replace('## 2026-10-04：风险卸载复验后的执行修订',current+'## 2026-10-04：风险卸载复验后的执行修订',1);save(n,s)

n='项目交付总览.md';s=load(n)
s=s.replace('|---|---|---|\n',f'|---|---|---|\n| SEARCH载荷/参考释放最新验证 | [结果与图]({rel}/结果说明.md)、[导纳饱和诊断]({rel}/failure_diagnosis.json) | 无保护但功能失败，1/5后关闭余4，B.2未完成 |\n',1)
s=s.replace('| 功能插入/共同B2风险卸载最新验证 |','| 前轮功能插入/共同B2风险卸载 |',1)
entry=f'''### TV-03｜SEARCH载荷卸载与参考释放（2026-10-04）

[结果/使用边界]({rel}/结果说明.md)、[配置]({rel}/configuration.json)、[实施计划](docs/superpowers/plans/2026-10-04-search-load.md)。新增显式载荷触发控制器与一次XY参考释放会话；原物理状态/保护保持。81相关检查、边界优先级审查修复完成。实际1/5负Y动态，无保护但两次搜索耗尽，0成功，余4关闭；不是B.2或训练资格。

入口tools/validation/run_search_load_preflight.py已消费本轮预算，再运行拒绝已有目录；同目录完整轨迹、停稳审核、旧/新前4244采样核对、对照图与949/693采样导纳饱和诊断可只读使用。后续需新明确方案/预算，不覆写本归档。

'''
s=s.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n'+entry,1)
s+='\n2026-10-04 00:48维护：新增TV-03和SEARCH载荷修复失败证据；历史编号、原轨迹和封存保留。\n';save(n,s)

n='deliverables/monthly_progress/2026-10/月报素材_2026-10.md';s=load(n)
s=re.sub(r'^统计截至：.*?。', '统计截至：2026-10-04 00:48（北京时间）。',s,count=1,flags=re.M)
s=re.sub(r'^最新功能任务修复：.*$',f'最新SEARCH载荷修复：1/5新动态、0功能/严格精度成功、0接触/运动保护、1/1有效停稳；6718周期/67180子步，累计120，余4关闭；81相关检查，训练/网络/独立测试0。峰值总力24.474139 mN；949个SEARCH采样在正Fy下Y导纳限幅为0，其中693个总Y命令仍负。[机器核对](../../../{rel}/assessment.json)。旧轮次数值各自保留。',s,flags=re.M)
s=re.sub(r'^最新：功能判据.*$','最新：本轮消除了已测负Y的原越力路径，但第二次搜索仍顶压并耗尽预算，不能当任务成功。只重置驱动参考而保留已饱和的导纳内部额度不足以完成插入；内部500 μm不是实际位移500 μm。其余四点未执行，暂无新SAC收益或泛化证据。',s,flags=re.M)
s=re.sub(r'^最新图：.*$',f'最新图：[SEARCH卸载、参考领先与实际推进](../../../{rel}/results.png)，同目录PDF。讲稿：“这次把负Y从越力保护转为无保护的正常停止，但仍未插入。进一步发现导纳内部纠偏额度饱和，外部参考虽释放，正向卸载输出仍被压为0；下一步处理状态一致性，不把没有越力误称成功。”',s,flags=re.M)
s=section(s,'## 五、下一项',next_text.replace(']('+rel,'](../../../'+rel))
s=s.replace('## 六、来源记录\n\n',f'## 六、来源记录\n\n2026-10-04 00:48｜[SEARCH载荷修复结果](../../../{rel}/结果说明.md)、[配置](../../../{rel}/configuration.json)、[账本](../../../{rel}/run/ledger.json)、[失败诊断](../../../{rel}/failure_diagnosis.json)、[审查](../../../{rel}/review.md)。1新动态，正常失败/有效停稳，余4关闭；0训练。\n\n',1);save(n,s)

plan=ROOT/'docs/superpowers/plans/2026-10-04-search-load.md'
s=plan.read_text(encoding='utf-8').replace('- [ ]','- [x]')+'\n## 实际收口\n\n2026-10-04 00:48：81项相关检查通过；实际1/5，首例负Y无保护但SEARCH_BUDGET_EXHAUSTED，功能未通过，余4关闭、累计120。其余四点未执行。勾选表示实施与依预定规则有限验证/归档完成，不表示修复性能或B.2验收。执行时计划原文在source_snapshot，后续研究下一项转为导纳积分/参考状态一致性。\n'
plan.write_text(s,encoding='utf-8',newline='\n')
with (OUT/'progress.md').open('a',encoding='utf-8') as f:f.write('\nTask 2: complete within first-case stop rule；负Y正常失败无保护/有效停稳，1/5，余4关闭、累计120，0训练。\nTask 3: complete；原始档案/功能与严格判据/停稳/4244采样核对、导纳饱和949/693采样诊断、图表已检查；四份滚动资料和研究计划同步更新。整体修复未通过，下一方案仅建议，待最终封存。\n')
print('Rolling documents and stage closeout updated; no historical archive modified.')
