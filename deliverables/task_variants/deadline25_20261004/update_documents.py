"""Update existing rolling documents after bounded verification closes."""
from pathlib import Path
import json,re,shutil
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
ctx=json.loads((OUT/'closeout_context.json').read_text(encoding='utf-8'))
a=json.loads((OUT/'assessment.json').read_text(encoding='utf-8'))
ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf-8'))
stamp=ledger['ended_at'][:16].replace('T',' ');rel='deliverables/task_variants/deadline25_20261004'
numbers=f"实际{a['episodes']}/5动态，功能成功{a['functional_success']}、附加严格精度{a['strict_precision_success']}；{a['control_cycles']}控制周期/{a['physical_substeps']}物理子步，累计{a['cumulative']}，余{a['unused_closed']}关闭。199相关检查通过，训练/网络/独立测试0，自动跟踪PAUSED，B.2未完成。"
summary=f'''<!-- deadline25-current -->
**25秒共同任务验证已结束（{stamp}）：{ctx['conclusion']}** {numbers}

{ctx['mechanism']}

下一项：{ctx['next_text']} [结果与图]({rel}/结果说明.md)、[机器核对]({rel}/assessment.json)、[诊断]({rel}/diagnosis.json)。
<!-- /deadline25-current -->'''


def load(n):return (ROOT/n).read_text(encoding='utf-8')
def save(n,s):(ROOT/n).write_text(s,encoding='utf-8',newline='\n')
def section(s,h,body):
    a=s.index(h)+len(h);b=s.find('\n## ',a)
    return s[:a]+'\n\n'+body.strip()+'\n'+(s[b:] if b>=0 else '')


docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
for n in docs:
    dest=OUT/'before_documents'/n;dest.parent.mkdir(parents=True,exist_ok=True)
    if not dest.exists():shutil.copy2(ROOT/n,dest)
for n in [docs[0],docs[1],docs[2],docs[4]]:
    block=summary.replace(']('+rel,'](../../../'+rel) if n.startswith('deliverables/') else summary
    s,count=re.subn(r'<!-- reference-search-current -->.*?<!-- /reference-search-current -->',lambda _:block,load(n),count=1,flags=re.S)
    assert count==1,n;save(n,s)

n=docs[1];s=load(n)
s=re.sub(r'^\| B\.2 小规模学习与评价包 .*$',f"| B.2 小规模学习与评价包 | 待验收；{ctx['conclusion']} | [本轮结果]({rel}/结果说明.md) | {ctx['limits']}；新训练0 |",s,flags=re.M)
updates={'1 开发适用性':ctx['limits'],
 '2 统一闭环/SAC接口':'新共同任务总时限20→25秒；驱动参考控制器、会话、功能判据和保护保持，未接入残差学习',
 '3 动态闭环/成本':numbers,
 '5 B2与批量评价':ctx['conclusion']+'；199项相关检查通过，实测范围见本轮报告',
 '7 阶段与进展约束':'本轮仅验证共同总时限，控制器不变，未新增残差/约束候选比较',
 '8 正式证据与展示':'完整新轨迹、XY冻结/命令重算及净推进核验、停稳审核、旧新对照图已保存；独立测试0、多种子未完成'}
for label,value in updates.items():s=re.sub(r'^\| '+re.escape(label)+r' \|.*$',f'| {label} | {value} |',s,flags=re.M)
start=s.index('## 当前风险和准入门')+len('## 当前风险和准入门');end=s.index('| 项目 | 当前事实 | 解除条件 |',start)
s=s[:start]+f"\n\n**本轮优先风险：** {ctx['limits']} {ctx['mechanism']}\n\n下表保留此前学习实验限制，旧参数对应其原实验，最新边界以上文为准。\n\n"+s[end:]
s=section(s,'## 下一项交付',ctx['next_text']+f' [本轮证据]({rel}/结果说明.md)。')
log=f"### {stamp}｜25秒共同任务有限验证收口\n\n{ctx['conclusion']} {numbers} {ctx['mechanism']} {ctx['next_text']} 证据：[结果]({rel}/结果说明.md)、[10月月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n\n"
s=s.replace('## 追加式阶段记录\n\n','## 追加式阶段记录\n\n'+log,1);save(n,s)

n=docs[3];s=load(n);where=s.index('\n## ')
s=s[:where]+f"\n## {stamp}：25秒共同任务实测后的执行修订\n\n{ctx['conclusion']} {numbers}\n\n{ctx['mechanism']}\n\n{ctx['next_text']}\n\n{ctx['limits']} [结果与证据]({rel}/结果说明.md)。以下保留此前计划依据，下一项以上述修订为准。\n"+s[where:];save(n,s)

n=docs[2];s=load(n)
s=s.replace('| 驱动参考一致性最新验证 |','| 前轮驱动参考一致性验证 |',1)
s=s.replace('|---|---|---|\n',f'|---|---|---|\n| 25秒共同任务最新验证 | [结果与图]({rel}/结果说明.md)、[诊断]({rel}/diagnosis.json) | {ctx["conclusion"]} |\n',1)
entry=f'''### TV-08｜25秒共同任务（2026-10-04）

[结果/使用边界]({rel}/结果说明.md)、[配置]({rel}/configuration.json)、[计划](docs/superpowers/plans/2026-10-04-deadline25-preflight.md)。{numbers} {ctx['conclusion']} 仅将共同任务总动作时限改为25秒；当前控制器、几何、功能判据和保护不变。20秒历史失败保留；未来基线须在相同25秒任务版本公平重评。

入口tools/validation/run_deadline25_preflight.py已消费本轮预算；已有run目录拒绝重启。完整轨迹、控制事件、对照图、停稳核验和输入快照可只读使用。后续新实验须重新登记，不覆写本轮或旧归档。{ctx['limits']}

'''
s=s.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n'+entry,1)
s+=f'\n{stamp}维护：新增TV-08，保留TV-01～07及历史档案。\n';save(n,s)

n=docs[4];s=load(n)
s=re.sub(r'^统计截至：.*?。',f'统计截至：{stamp}（北京时间）。',s,count=1,flags=re.M)
s=re.sub(r'^最新参考跟踪：.*$',f'最新25秒任务：{numbers} {ctx["conclusion"]} [核对](../../../{rel}/assessment.json)。',s,flags=re.M)
s=re.sub(r'^最新：.*$',f'最新：{ctx["limits"]} {ctx["mechanism"]}',s,count=1,flags=re.M)
s=re.sub(r'^最新图：.*\n','',s,flags=re.M)
s=s.replace('## 四、图表与讲稿\n',f'## 四、图表与讲稿\n\n最新图：[20秒与25秒同控制器对照](../../../{rel}/results.png)、[搜索运动与净推进](../../../{rel}/search_diagnosis.png)，[末段深度、配合与稳定](../../../{rel}/completion.png)，同目录PDF。讲稿：“{ctx["narration"]}”\n',1)
s=section(s,'## 五、下一项',ctx['next_text']+f' [本轮报告](../../../{rel}/结果说明.md)。')
s=s.replace('## 六、来源记录\n\n',f'## 六、来源记录\n\n{stamp}｜[25秒任务结果](../../../{rel}/结果说明.md)、[配置](../../../{rel}/configuration.json)、[账本](../../../{rel}/run/ledger.json)、[诊断](../../../{rel}/diagnosis.json)、[审查](../../../{rel}/review.md)。{numbers}\n\n',1);save(n,s)

plan=ROOT/'docs/superpowers/plans/2026-10-04-deadline25-preflight.md'
s=plan.read_text(encoding='utf-8').replace('- [ ]','- [x]')+f'\n## 实际收口\n\n{stamp}：{ctx["conclusion"]} {numbers} 勾选仅表示实施、有限验证与归档完成；不表示B.2通过。执行时计划原文在source_snapshot，当前文档为收口版。\n'
plan.write_text(s,encoding='utf-8',newline='\n')
with (OUT/'progress.md').open('a',encoding='utf-8') as f:f.write(f'\nTask 2: bounded execution complete — {numbers}\nTask 3: complete pending seal — {ctx["conclusion"]} 原始轨迹、判据与停稳独立核对、诊断/图表、滚动资料更新完成。\n')
print('Updated rolling project documents and closeout plan.')
