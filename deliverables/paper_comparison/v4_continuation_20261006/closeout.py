"""Integrate this delivered stage and a factual B.2 remaining-work estimate."""
import json,re,shutil
from pathlib import Path
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;REL=OUT.relative_to(ROOT).as_posix()

def save(p,s):p.write_text(s,encoding='utf8',newline='\n')
def section(s,h,body):
    start=s.index(h)+len(h);end=s.find('\n## ',start)
    return s[:start]+'\n\n'+body+'\n'+(s[end:] if end>=0 else '')

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    a=json.loads((OUT/'assessment.json').read_text(encoding='utf8'));stamp=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    tests=int(re.search(r'(\d+) passed',(OUT/'tests_final.txt').read_text()).group(1))
    passed=a['bounded_preflight_passed'];conclusion='残差边界连续性修复及单回合实测通过' if passed else '残差边界连续性实测未通过，整轮已停止'
    numbers=f"{tests}项相关检查通过；新增{a['attempts']}/1动态、完成{a['completed']}回合，{a['control_cycles']}控制周期/{a['physical_substeps']}物理子步；累计{a['cumulative']}，余{a['unused_closed']}关闭。正式训练/策略推理/回放发布/独立测试0，自动跟踪PAUSED，B.2未完成。"
    if passed:
        mechanism=f"脉冲前{a['prefix_equal_samples']}个轨迹点逐值一致；第一层滤波比例{a['first_step_fraction']:.9f}、连续性比例{a['continuation_fraction']:.6f}、合成比例{a['combined_fraction']:.9f}。实际触发滤波{a['filter_cycles']}周期，下一零动作B2没有参考失败；审核{a['actual_reference_checks']}个实际SEARCH参考端点，越界0。本例{a['outcome']['task_outcome']}，任务判定{a['task_end_time_s']:.3f}s，峰值力{a['peak_force_mN']:.3f}mN。"
    else:
        mechanism=f"实际结果/首个未通过项见独立核对；不补写未执行或未通过的证据。状态{a['status']}，原因{a.get('reason',a.get('errors'))}。"
    limits='只证明已登记负Y单脉冲的有限连续性修复；不保证任意未来动作、lead裁剪、所有物理子步或整个策略空间安全。137维学习掩码/回放/SAC/完整检查点仍需新版本准入，未沿用旧120维权重或旧训练数据；本轮不是学习收益。'
    proposed_limit=a['cumulative']+28
    next_text=(f'补齐137维学习链准入：阶段与经验掩码、整回合发布及无效隔离、共同奖励、完整模型/优化器/回放/RNG保存恢复，绑定新会话及源/模型/runtime。通过后另签发F/S相同新零网络起点的最多28回合/4000批pilot，累计提案上限{proposed_limit}；当前尚无训练准入。随后冻结方法和检查点，登记未用范围的独立评价及重复复现，才审查B.2验收。' if passed else '先定位本轮首个未通过项并制定针对性方案，不复用关闭余量、不进入训练。')
    summary=f'''<!-- v4-continuation-current -->
**{conclusion}（{stamp[:16]}）。** {numbers}

{mechanism}

{limits} 下一项：{next_text} [结果]({REL}/结果说明.md)、[独立核对]({REL}/assessment.json)、[审查]({REL}/review.md)。
<!-- /v4-continuation-current -->'''
    old=json.loads((ROOT/'deliverables/paper_comparison/v4_adapter_20261004/assessment.json').read_text(encoding='utf8'))
    fs=[r['wall_seconds'] for r in old['rows'] if r['method'] in ('F50','S50')]
    mean_s=sum(fs)/len(fs);hours=mean_s*28/3600
    archive_link='run/ledger.json'
    for name in ['run/F50_boundary_y_neg_150.json.gz','run/F50_boundary_y_neg_150.error.json.gz']:
        if (OUT/name).exists():archive_link=name;break
    transition_evidence=(f"另逐条核对{a['transition_reward_permission_checks']}条137维观测连续性、权限/经验动作、物理时间折扣及奖励重算。" if passed else
        '未通过项及未完成审核按assessment记录，不补写通过。')
    report=f'''# 残差参考连续性修复与B.2剩余工作

截至{stamp}，**{conclusion}**。{numbers}

## 问题与最小修改

旧单步滤波把第一个命令预测到半径119.999999μm，下一真实B2在9.148s却预测约120.016546μm并触发SEARCH_REFERENCE_LIMIT。16,563个旧SEARCH零命令逐值一致；六个旧反例中3个有这种下一步失败，其余3个为正常螺旋耗尽。

新增层先保留旧单步过滤，再核对下一零动作B2的参考；仅在需要时沿已限幅基线→候选速度段减半，并重新核验实际限幅。不假设第二步分量限幅可行性单调，不追求最大残差保留。基线本身无法继续则保留并明确未证明状态；正常耗尽不误判。F/S共用，继承链、几何、保护、裁判、137维观测、请求和经验语义保持。

## 实测及独立审核

{mechanism}

登记方案为从正常reset开始，仅在9.146s请求一次[1,−1,0,0]，其他控制周期全为零。实际已执行内容以[回合归档或故障账本]({archive_link})为准；轨迹、动作、137维连续观测、周期奖励与载荷、实际参考、事件和停止样本留存，失败也保留。

[独立核对](assessment.json)核验脉冲前逐轨迹、两层比例的独立重算、下一控制器、实际限幅和搜索参考端点、真实停稳。{transition_evidence}观测/奖励档案只用于只读审核，没有入池或优化，不能替代学习链准入。

{limits}

## 检查、审查与选择

{tests}相关检查通过，非全项目测试。独立审查0 Critical/0 Important/2 Minor；两项暂缓：生产日志未单列第一层原始比例（本轮档案独立重算证明，不把合成比例当证据）；没有专门非单调mock回归（每个接受候选已显式检查）。原始发现与边界见[review.md](review.md)。

选择及代价：沿用脏工作树、新模块和旧冻结基类以保持历史可追溯，代价是少量逻辑重复；保守减半可能压缩可用残差；本轮先修已确认控制阻塞而未并行改学习器，代价是训练准入另有缺口。记录持续保留，不提交/清理。不存在无限时域安全或非冻结驱动配置保证，仍需运行时守卫。

## 离B.2还有多远

不能按已完成任务数给百分比。还剩三个实际交付：

| 关口 | 当前缺口 | 通过所需证据 |
|---|---|---|
| 新任务学习准入 | 旧回放/SAC/检查点仍按120维；v4为137维 | 新版本掩码、奖励/隔离、完整保存加载、优化器/RNG恢复及绑定通过 |
| 小规模学习与固定开发评价 | 新任务正式更新0 | 相同起点/预算F/S训练、末次冻结五点评价、所有成功失败和成本留档 |
| 冻结后的独立评价与可重复运行 | 新v4尚无这类证据 | 预登记未用评价范围、冻结检查点、独立进程恢复与实际重复证据 |

上述B.2工程验收要求完整、可重复的学习与真实评价；论文“新方法更好”还需额外收益证据。五点开发通过不能冒充泛化或发表资格，正式论文的多种子/独立配对测试属于后续研究证据。预定pilot继续信号仍为S对B2和F分别保持成功数、罚时至少减少10%、保护不增加、平均峰值力不增加超过5%。无信号就报告负结果，不通过事后阈值修改制造增益。

按PC-02四个F/S回合平均{mean_s:.1f}s粗估，28回合纯采样墙时约{hours:.2f}小时；另加实际学习、审核、保存恢复和未登记独立评价成本。此估算不代表完成日期或保证本轮方法有效；遇新问题可能提前停止并留下未完成项。

## 下一项

{next_text}

[计划](../../../docs/superpowers/plans/2026-10-06-v4-continuation-preflight.md)、[配置](configuration.json)、[一次性账本](run/ledger.json)、[离线真实控制器对照](offline_check.json)。旧实验、冻结合同及校验清单不改写。
'''
    save(OUT/'结果说明.md',report)
    docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    for name in docs:
        dest=OUT/'before_documents'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists():shutil.copy2(ROOT/name,dest)
    for name in (docs[0],docs[1],docs[2],docs[4]):
        p=ROOT/name;s=p.read_text(encoding='utf8');block=summary
        if name.startswith('deliverables/'):block=block.replace(']('+REL,'](../../../'+REL)
        s,n=re.subn(r'<!-- v4-adapter-current -->.*?<!-- /v4-adapter-current -->',lambda _:block,s,count=1,flags=re.S)
        assert n==1,name;save(p,s)
    p=ROOT/docs[1];s=p.read_text(encoding='utf8')
    s=re.sub(r'^最后更新：[^。]+。','最后更新：'+stamp[:10]+'。',s,count=1,flags=re.M)
    s=re.sub(r'^\| B\.1 接口与训练准入包 .*$',f'| B.1 接口与训练准入包 | v4接入及有限连续性状态见本轮；学习准入未齐 | [本轮]({REL}/结果说明.md) | {limits} |',s,flags=re.M)
    s=re.sub(r'^\| B\.2 小规模学习与评价包 .*$',f'| B.2 小规模学习与评价包 | 未验收；剩学习准入、短训固定评价、独立评价/复现 | [缺口与估算]({REL}/结果说明.md) | 正式新训练0，学习效果未证明 |',s,flags=re.M)
    updates={'2 统一闭环/SAC接口':conclusion+'；137维学习链待新准入','3 动态闭环/成本':numbers,
        '5 B2与批量评价':mechanism+' 原TV-09五点B2 5/5、PC-02 B1 1/5仍是开发结果',
        '6 普通残差SAC':'新任务正式更新0，尚缺137维学习链准入、训练及冻结独立评价',
        '7 阶段与进展约束':'F/S公共连续性层实测状态见本轮；未证明阶段/进展学习收益',
        '8 正式证据与展示':'本轮原始轨迹/观测/奖励、独立核验/封存完成；独立测试0，论文多种子待做'}
    for label,value in updates.items():s=re.sub(r'^\| '+re.escape(label)+r' \|.*$',f'| {label} | {value} |',s,flags=re.M)
    start=s.index('## 当前风险和准入门')+len('## 当前风险和准入门');end=s.index('| 项目 | 当前事实 | 解除条件 |',start)
    s=s[:start]+'\n\n当前：'+limits+'\n\n下表保留历史限制，下一项以上文为准。\n\n'+s[end:]
    s=section(s,'## 下一项交付',next_text+f' [三关缺口和耗时估计]({REL}/结果说明.md)。')
    s=s.replace('## 追加式阶段记录\n\n',f'## 追加式阶段记录\n\n### {stamp[:16]}｜边界连续性实测收口\n\n{conclusion}。{numbers} {mechanism} {limits} 下一项：{next_text} [结果]({REL}/结果说明.md)、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n\n',1);save(p,s)
    p=ROOT/docs[2];s=p.read_text(encoding='utf8')
    s=s.replace('|---|---|---|\n',f'|---|---|---|\n| 残差边界连续性实测 | [结果/剩余工作]({REL}/结果说明.md)、[核对]({REL}/assessment.json) | {conclusion} |\n',1)
    s=s.replace('## 基线与接口交付\n\n',f'## 基线与接口交付\n\n### PC-03｜残差参考连续性有限修复（{stamp[:10]}）\n\n[结果/使用/边界]({REL}/结果说明.md)、[计划](docs/superpowers/plans/2026-10-06-v4-continuation-preflight.md)。{numbers} {mechanism} {limits} 原runner已消费或关闭，禁止重启该目录。\n\n',1);save(p,s)
    p=ROOT/docs[3];s=p.read_text(encoding='utf8');where=s.index('\n## ')
    s=s[:where]+f'\n## {stamp[:16]}：参考连续性修复后的执行修订\n\n{conclusion}。{numbers}\n\n{mechanism}\n\n{limits} {next_text} [结果及三道剩余验收]({REL}/结果说明.md)。以下保留历史依据，下一项以上文为准。\n'+s[where:];save(p,s)
    p=ROOT/docs[4];s=p.read_text(encoding='utf8')
    s=re.sub(r'^统计截至：.*?。',f'统计截至：{stamp[:16]}（北京时间）。',s,count=1,flags=re.M)
    s=re.sub(r'^最新接入预检：.*$',f'最新连续性实测：{numbers} {mechanism} [独立核对](../../../{REL}/assessment.json)。',s,count=1,flags=re.M)
    s=re.sub(r'^最新：.*$',f'最新：{limits}',s,count=1,flags=re.M)
    s=s.replace('## 三、负结果与限制\n',f'## 三、负结果与限制\n\n最新诊断：旧单步滤波的3个下一真实控制器参考失败已离线修复并做单回合触发验证，另3个正常耗尽保留；这是接口连续性问题，不是新物理失败或旧训练失败的唯一因果证明。{limits}\n',1)
    s=s.replace('## 四、图表与讲稿\n',f'## 四、图表与讲稿\n\n最新[实测和B.2三关表](../../../{REL}/结果说明.md)。讲稿：“{conclusion}，尚缺学习准入、训练开发评价和冻结独立评价/复现。计算量约数小时，不等于方法成功日期。”\n',1)
    s=section(s,'## 五、下一项',next_text+f' [本轮](../../../{REL}/结果说明.md)。')
    s=s.replace('## 六、来源记录\n\n',f'## 六、来源记录\n\n{stamp[:16]}｜[PC-03结果](../../../{REL}/结果说明.md)、[核对](../../../{REL}/assessment.json)、[离线反例](../../../{REL}/offline_check.json)、[审查](../../../{REL}/review.md)。{numbers}\n\n',1);save(p,s)
    plan=ROOT/'docs/superpowers/plans/2026-10-06-v4-continuation-preflight.md'
    save(plan,plan.read_text(encoding='utf8').replace('[ ]','[x]')+f'\n## 实际收口\n\n{stamp}：{conclusion}。{numbers} 勾选代表本轮实现/登记执行或受控停止/归档完成，不代表训练准入、B.2或算法收益。\n')
    save(OUT/'closeout_context.json',json.dumps(dict(stamp=stamp,conclusion=conclusion,numbers=numbers,mechanism=mechanism,
        limits=limits,next_text=next_text,estimated_28_sampling_hours=hours,proposed_cumulative_limit=proposed_limit),ensure_ascii=False,indent=2)+'\n')
    with (OUT/'progress.md').open('a',encoding='utf8') as f:f.write(f'\nTask 3: complete — {conclusion}。{numbers}\nTask 4: complete pending seal — 独立档案/奖励/权限核验，五份文档同步，三道B.2缺口及成本估计按事实列出。\n')
    print(conclusion,numbers)

if __name__=='__main__':main()
