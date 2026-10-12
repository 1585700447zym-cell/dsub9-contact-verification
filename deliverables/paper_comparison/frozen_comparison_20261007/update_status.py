"""Update the current PC-07 block without rewriting historical delivery facts."""
from pathlib import Path
import datetime,json,re
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
l=json.loads((OUT/'run/ledger.json').read_text(encoding='utf8')) if (OUT/'run/ledger.json').exists() else dict(status='qualified',episodes=[])
done=sum(e['status']=='finished' for e in l['episodes']);starts=len(l['episodes'])
calls=sum(e.get('policy_calls',0) for e in l['episodes'] if e['spec']['provider']!='B2')
stamp=datetime.datetime.now().isoformat(timespec='minutes');base='deliverables/paper_comparison/frozen_comparison_20261007/'
for name in ['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']:
    path=ROOT/name;s=path.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else ''
    block=f'''<!-- pc07-current -->
**PC-07同版本公平对照/冻结后首次位置评价：{l['status']}（{stamp}）；完整B.2未验收。** 新增{starts}/27动态，完成{done}，累计{173+starts}/200；本轮训练/梯度更新/经验发布0，已记录真实网络控制调用至少{calls}，执行中周期记录为下界。原PC-06两组各2000批检查点只读，生产1057项来源保持，137维/4维与几何/保护/奖励不变。

固定矩阵：B2五开发点；初始确定性F/S各五点；4个预登记首次位置×B2/F2000/S2000。继承PC-06十份冻结开发档案，不重复采集；四个位置在执行前按种子2026100701分象限锁定，单训练种子/小样本，使用后不作为后续调参后的未见测试。63关联检查通过；独立审查1 Important计数问题经两种故障RED/GREEN关闭，未二次独立复审。B2零提供器接口调用不混入真实网络计数。

源/运行/参考/无效/未停稳错误整轮停，合格任务/保护失败作为固定评价结果保留。预算一次领取，不重试，不重开旧额度，自动跟踪PAUSED。阶段内部持续执行，结束后按实际比较收益或不足收口。

[本轮计划]({prefix}docs/superpowers/plans/2026-10-07-v4-frozen-comparison.md)、[资格]({prefix}{base}qualification.json)、[账本]({prefix}{base}run/ledger.json)、[审查与修正]({prefix}{base}review.md)。下方PC-06及此前记录保留当时状态，最新待办以上述为准。
<!-- /pc07-current -->'''
    pattern=r'<!-- pc07-current -->.*?<!-- /pc07-current -->'
    if re.search(pattern,s,re.S):s=re.sub(pattern,lambda _:block,s,count=1,flags=re.S)
    else:
        index=s.index('\n')+1;s=s[:index]+'\n'+block+'\n'+s[index:]
    path.write_text(s,encoding='utf8',newline='\n')
print(f'PC-07 {l["status"]}: {starts} starts/{done} finished; new gradients/publication0')
