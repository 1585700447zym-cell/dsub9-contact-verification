"""Integrate the completed preparation stage into the five rolling documents."""
from pathlib import Path
import hashlib,json,re,shutil
from datetime import datetime,timezone,timedelta

ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
REL=OUT.relative_to(ROOT).as_posix()

def read(name):return (OUT/name).read_text(encoding='utf-8')
def write(path,text):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8',newline='\n')
def section(text,heading,body):
    start=text.index(heading)+len(heading);end=text.find('\n## ',start)
    return text[:start]+'\n\n'+body.strip()+'\n'+(text[end:] if end>=0 else '')

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
    stamp=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    audit=json.loads(read('residual_integration_audit.json'));metrics=json.loads(read('baseline_metrics.json'))
    tests=int(re.search(r'(\d+) passed',read('tests_final.txt')).group(1))
    review=json.loads(read('review_result.json'));assert review['unresolved_critical']==review['unresolved_important']==0
    numbers=f'{tests}项相关检查通过；本轮新增动态/物理子步/网络调用/训练更新均0，累计动态130，自动跟踪PAUSED，B.2未完成。'
    mechanism='五个封存B2开发点功能5/5、附加精度1/5；平均完成时间12.706s、平均全回合峰值力19.600mN（包含对准零接触点）。16,563个SEARCH命令零残差预测完全一致；132,504次有界XY命令反事实出现6个参考越界，最大16.609nm，均在负Y末段。后者是接口兼容性反例，不是新物理失败或旧训练失败的因果证明。'
    limits='共同协议/评价实现完成；B1新任务适配、残差v4会话和训练准入尚未完成，没有F/S新任务效果、多种子或独立测试证据。'
    next_text='先实现保留新会话继承链的残差适配、合成后参考边界约束及新观测版本，F/S共用安全层；再做B1五点、±Y零残差等价及F/S非零脚本的最多9回合预检（训练0）。离线门和执行账本通过才启动；后续28回合/4000批只是待准入pilot提案，旧余量不结转。'
    summary=f'''<!-- paper-protocol-current -->
**v4论文对照准备完成（{stamp[:16]}）：共同任务/基线/评价口径已冻结，确认残差接入还有参考边界缺口。** {numbers}

{mechanism}

{limits} 下一项：{next_text} [结果]({REL}/结果说明.md)、[协议](docs/stage_b/论文对照协议_v4.md)、[机器审计]({REL}/residual_integration_audit.json)。
<!-- /paper-protocol-current -->'''
    rows=json.loads(read('baseline_records.json'))
    table='\n'.join(f"| {r['case_id']} | {r['task_end_time_s']:.3f} | {r['peak_force_N']*1000:.3f} | {r['sampled_force_integral_N_s']:.6f} |" for r in rows)
    report=f'''# v4公平对照准备结果

收口时间：{stamp}。

共同实验协议与离线评价工具已完成；发现并具体复现了旧残差合成与新搜索参考边界的不兼容，修复尚未实施。{numbers}

## 已交付

- [共同协议](../../../docs/stage_b/论文对照协议_v4.md)、[机器配置](protocol.json)：共同几何/成功/保护/控制参数与源文件绑定；B1、B2、F50、S50定义；五点开发矩阵和有界后续预算。
- [评价工具](../../../tools/evaluation/paper_comparison.py)：全部尝试进分母；失败罚26s，缺失/无效/未停稳使矩阵不可比；拒绝混版本或重复工况。相同成功数只是前提，预定效率门为罚时均值减少10%、保护不增、峰值力均值增幅不超过5%。S须对B2和F分别过门，仅是开发继续信号。
- [基线逐回合数据](baseline_records.json)、[汇总](baseline_metrics.json)：来源为TV-09的已封存归档，本轮没有重复采样。成功/停稳承接上一阶段已独立审核且哈希绑定的事实，本轮复算时间、载荷汇总与采样积分。
- [残差接入审计](residual_integration_audit.json)：零命令逐点复算和有界残差反例；[执行脚本](prepare_and_audit.py)可在未封存输出上执行，现已封存，读取结果即可。

## 基线数字

{mechanism}

| 工况 | 功能成功判定时间 s | 全回合峰值力 mN | 2ms采样力时间积分 N·s |
|---|---:|---:|---:|
{table}

载荷含真实停止尾段，采样积分不是子步载荷积分。五点是开发工况，5/5不能作为连续分布的成功率或论文泛化结论。

## 新发现与最小修复方案

旧compose_command在B2检查纯基线之后叠加残差。−Y约9.146s，零动作下一参考半径119.979948μm，合法动作[1,−1,0,0]经实际速度/加速度限幅后为120.000763μm；最多超出16.609nm。当前控制器的参考判定容差1pm，故这种命令会越过它的边界。几何裁判1nm是另一项判据，不能借它忽略参考越界。只证明接口可出现此问题，没有执行反事实物理轨迹，不是出现六个真实失败回合，也不证明旧学习失败只由它引起。

建议合成后再预测参考；必要时在基线到候选的命令段上缩减残差，并以最终实际限幅结果复核。零基线本身不可行时按共同受控停止/恢复处理，不能扩大半径或绕过加速度。保留LayeredReferenceSession的DriveObservation/参考释放/导纳重置/分层成功链；观测另起版本，F/S共用安全层。该适配未实现，不能直接把旧ResidualSession换模型后启动训练。

## 验证、局限与下一项

{tests}项相关检查通过（不是整个项目全量测试），新增模块先RED后GREEN；审查及修复见[记录](review.md)。9个历史阶段共2112个文件哈希保持，见[历史封存核对](prior_seals_verified.json)。第一次审计摘要误要求包含归档自己的哈希，脚本已纠正且原失败日志保留，源档案未改。

{limits} {next_text}

本次决定：失败罚26s防止提前失败获得速度优势；旧日志只报采样积分；按既有授权完成准备，不自动开启训练；遵从用户保留脏工作树和不提交/清理。若口径需要更改必须立新协议，不能改写已封存的结果。
'''
    write(OUT/'结果说明.md',report)
    docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    for name in docs:
        p=OUT/'before_documents'/name;p.parent.mkdir(parents=True,exist_ok=True)
        if not p.exists():shutil.copy2(ROOT/name,p)
    for name in [docs[0],docs[1],docs[2],docs[4]]:
        text=(ROOT/name).read_text(encoding='utf-8')
        block=summary
        if name.startswith('deliverables/'):
            block=block.replace(']('+REL,'](../../../'+REL).replace('](docs/','](../../../docs/')
        if '<!-- paper-protocol-current -->' in text:
            text,n=re.subn(r'<!-- paper-protocol-current -->.*?<!-- /paper-protocol-current -->',lambda _:block,text,count=1,flags=re.S)
        else:
            text,n=re.subn(r'<!-- layered-referee-current -->.*?<!-- /layered-referee-current -->',lambda _:block,text,count=1,flags=re.S)
        assert n==1,name;write(ROOT/name,text)
    p=ROOT/docs[1];text=p.read_text(encoding='utf-8')
    text=re.sub(r'^\| B\.1 接口与训练准入包 .*$', '| B.1 接口与训练准入包 | 旧版本限定工程链路已验收；v4须重新准入 | [旧B1-09](deliverables/residual_interface/b1_closeout_20260926/README.md)、[v4缺口]('+REL+'/结果说明.md) | 新会话继承、合成参考边界和观测版本尚未完成 |',text,flags=re.M)
    text=re.sub(r'^\| B\.2 小规模学习与评价包 .*$', '| B.2 小规模学习与评价包 | 待验收；v4共同协议与评价工具已完成 | [本轮结果]('+REL+'/结果说明.md) | 新训练0，不能由B2传统基线5/5推断SAC有效 |',text,flags=re.M)
    updates={'1 开发适用性':'v4五开发点已有有效停稳证据；未扩展到连续域、硬件或独立评价',
      '2 统一闭环/SAC接口':'v4残差接入缺口已用归档命令定位；合成后参考约束、新观测版本尚未实现',
      '3 动态闭环/成本':numbers,
      '4 B1':'旧结果保留；v4共同回合适配与五点复验待执行',
      '5 B2与批量评价':'冻结reference_search_v7及五点5/5；统一离线评价工具完成，平均完成12.706s',
      '6 普通残差SAC':'F50新任务尚未训练；旧数据/权重不直接迁用',
      '7 阶段与进展约束':'F50/S50阶段最小消融已登记协议；未实现进展候选或证实收益',
      '8 正式证据与展示':'共同指标、哈希绑定、残差接口反例已归档；独立测试0、多种子未完成'}
    for label,value in updates.items():text=re.sub(r'^\| '+re.escape(label)+r' \|.*$',f'| {label} | {value} |',text,flags=re.M)
    a=text.index('## 当前风险和准入门')+len('## 当前风险和准入门');b=text.index('| 项目 | 当前事实 | 解除条件 |',a)
    text=text[:a]+'\n\n当前优先风险：'+limits+' '+mechanism+'\n\n下表保留历史学习限制，v4最新缺口以上文为准。\n\n'+text[b:]
    text=section(text,'## 下一项交付',next_text+' [协议](docs/stage_b/论文对照协议_v4.md)。')
    marker='### '+stamp[:16]+'｜v4共同对照协议准备完成'
    text=text.replace('## 追加式阶段记录\n\n','## 追加式阶段记录\n\n'+marker+'\n\n'+numbers+' '+mechanism+' '+limits+' 下一项：'+next_text+f' [结果]({REL}/结果说明.md)、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n\n',1)
    write(p,text)
    p=ROOT/docs[2];text=p.read_text(encoding='utf-8')
    text=text.replace('| 分层几何裁判最新验证 |','| 已封存分层裁判验证 |',1)
    text=text.replace('|---|---|---|\n',f'|---|---|---|\n| v4共同对照准备 | [协议](docs/stage_b/论文对照协议_v4.md)、[结果]({REL}/结果说明.md) | 评价工具已完成，残差适配未准入 |\n',1)
    entry=f'### PC-01｜v4论文对照准备（2026-10-04）\n\n[结果/使用边界]({REL}/结果说明.md)、[机器协议]({REL}/protocol.json)、[接口审计]({REL}/residual_integration_audit.json)。{numbers} {mechanism} {limits} 评价入口tools/evaluation/paper_comparison.py为纯离线模块；封存审计脚本禁止重写当前交付。\n\n'
    text=text.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n'+entry,1);write(p,text)
    p=ROOT/docs[3];text=p.read_text(encoding='utf-8');index=text.index('\n## ')
    text=text[:index]+f'\n## {stamp[:16]}：v4论文对照准备后的执行修订\n\n'+numbers+' '+mechanism+'\n\n'+limits+'\n\n'+next_text+f' [协议](docs/stage_b/论文对照协议_v4.md)、[本轮结果]({REL}/结果说明.md)。以下保留此前依据，下一项以上文为准。\n'+text[index:];write(p,text)
    p=ROOT/docs[4];text=p.read_text(encoding='utf-8')
    text=re.sub(r'^统计截至：.*?。',f'统计截至：{stamp[:16]}（北京时间）。',text,count=1,flags=re.M)
    text=re.sub(r'^最新分层裁判：.*$',f'最新对照准备：{numbers} {mechanism} [指标](../../../{REL}/baseline_metrics.json)。',text,count=1,flags=re.M)
    text=re.sub(r'^最新：.*$',f'最新：{limits}',text,count=1,flags=re.M)
    text=text.replace('## 三、负结果与限制\n','## 三、负结果与限制\n\n本轮新增：旧残差合成有6个命令级参考越界反例，尚未修复，不能直接训练；没有新增动力学失败。{0}\n'.format(limits),1)
    text=text.replace('## 四、图表与讲稿\n',f'## 四、图表与讲稿\n\n最新数字表：[五点共同基线和接口反例](../../../{REL}/结果说明.md)。本轮无需新增轨迹图，沿用下方TV-09图。讲稿：“传统B2五点可以完成任务；公平对照协议已固定，但学习适配还有一处合成后参考边界缺口，下一步先修接口再有限验证。”\n',1)
    text=section(text,'## 五、下一项',next_text+f' [协议](../../../docs/stage_b/论文对照协议_v4.md)。')
    text=text.replace('## 六、来源记录\n\n',f'## 六、来源记录\n\n{stamp[:16]}｜[PC-01结果](../../../{REL}/结果说明.md)、[协议](../../../{REL}/protocol.json)、[审计](../../../{REL}/residual_integration_audit.json)、[审查](../../../{REL}/review.md)。{numbers}\n\n',1);write(p,text)
    plan=ROOT/'docs/superpowers/plans/2026-10-04-paper-protocol-v4.md'
    write(plan,plan.read_text(encoding='utf-8').replace('- [ ]','- [x]')+'\n## 实际收口\n\n'+stamp+'：准备阶段完成。'+numbers+' 勾选不表示残差适配、B.1新准入或B.2训练完成。\n')
    with (OUT/'progress.md').open('a',encoding='utf-8') as f:
        f.write('\nTask 2: complete — 2112个历史封存文件通过，5个基线指标重算；16563零命令等价、132504反事实发现6越界。物理/训练0。\nTask 3: complete pending seal — 独立审查及相关检查完成，五份滚动资料更新。\n')
    write(OUT/'closeout_context.json',json.dumps(dict(timestamp=stamp,tests=tests,numbers=numbers,mechanism=mechanism,limits=limits,next_text=next_text),ensure_ascii=False,indent=2)+'\n')
    print('Five rolling documents integrated; report written. Seal pending.')

if __name__=='__main__':main()
