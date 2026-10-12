"""Rolling status only; never changes pinned execution inputs or prior archives."""
from pathlib import Path
import datetime,json,re
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
l=json.loads((OUT/'run/ledger.json').read_text(encoding='utf8')) if (OUT/'run/ledger.json').exists() else dict(status='qualified',episodes=[])
starts=len(l['episodes']);done=sum(e['status']=='finished' for e in l['episodes']);calls=sum(e.get('policy_calls',0) for e in l['episodes'])
for name in DOCS:
    p=ROOT/name;s=p.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else ''
    base=prefix+'deliverables/paper_comparison/contact_gate_probe_20261007/'
    block=f'''<!-- pc09-current -->
**PC-09接触门控与较小固定边界部署预检：{l['status']}（{datetime.datetime.now().isoformat(timespec='minutes')}）；完整B.2未验收。** 新启动{starts}/8动态、完成{done}，累计{200+starts}/208；实际网络调用至少{calls}，执行中成本为下界；新增训练/经验发布0。

固定aligned、负Y150μm各B2/F50/F12.5/G50；只读同一F2000检查点。G50在SEARCH启用，INSERT以动作前5mN轴向反力门控；F12.5只把原输出乘0.25，不是该尺度重训。137维/4维、共同物理/奖励/保护及1057生产输入保持；不使用四个已消费位置选参，不宣称新门控下训练恢复或论文优势。

88关联离线检查及原完整检查点读取通过；资格以[实际登记]({base}qualification.json)为准。普通失败留档，运行/来源/参考/无效/未停稳异常整轮停；不重试，余量关闭，自动跟踪PAUSED。阶段内部持续，按实际结果收口后暂停汇报。 [计划]({prefix}docs/superpowers/plans/2026-10-07-contact-gate-probe.md)、[账本]({base}run/ledger.json)、[审查]({base}review.md)。下方保留此前时点记录。
<!-- /pc09-current -->'''
    pattern=r'<!-- pc09-current -->.*?<!-- /pc09-current -->'
    if re.search(pattern,s,re.S):s=re.sub(pattern,lambda _:block,s,count=1,flags=re.S)
    else:s=s.replace('\n','\n\n'+block+'\n',1)
    p.write_text(s,encoding='utf8',newline='\n')
print(f'PC-09 {l["status"]}: {starts}/8 starts, {done} finished, {calls} recorded network calls')
