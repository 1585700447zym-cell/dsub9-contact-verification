"""Write the result and integrate the completed bounded stage in rolling docs."""
from pathlib import Path
import json,re,shutil
from datetime import datetime,timezone,timedelta
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent;REL=OUT.relative_to(ROOT).as_posix()
def section(s,h,body):
    a=s.index(h)+len(h);b=s.find('\n## ',a)
    return s[:a]+'\n\n'+body+'\n'+(s[b:] if b>=0 else '')
def save(p,s):p.write_text(s,encoding='utf8',newline='\n')

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    a=json.loads((OUT/'assessment.json').read_text(encoding='utf8'));stamp=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    tests=int(re.search(r'(\d+) passed',(OUT/'tests_final.txt').read_text()).group(1))
    rows=a['rows'];finished=[r for r in rows if r['status']=='finished']
    zero=[r for r in finished if r['method']=='F50' and r['profile']=='zero']
    pulse=[r for r in finished if r['profile']=='pulse'];b1=[r for r in finished if r['method']=='B1']
    passed=a['bounded_preflight_passed'];conclusion='v4残差接入的有限预检通过' if passed else 'v4残差接入有限预检未通过，已停止并关闭余量'
    numbers=f"{tests}项相关检查通过；新增{a['attempts']}/9动态、完成{a['completed']}回合，{a['control_cycles']}控制周期/{a['physical_substeps']}子步；累计{a['cumulative']}，未执行{a['unused_closed']}关闭。网络调用/训练/独立测试0，自动跟踪PAUSED，B.2未完成。"
    mechanism=f"零残差完整轨迹一致{sum(r['trace_equal'] is True for r in zero)}/2；非零F/S脚本完成{len(pulse)}/2，脚本功能成功{sum(r['full_success'] for r in pulse)}（不代表SAC学习收益）；B1功能成功{sum(r['full_success'] for r in b1)}/{len(b1)}个已执行点。独立审核{sum(r['actual_reference_checks'] for r in finished)}个实际搜索参考端点，越界{sum(r['actual_reference_failures'] for r in finished)}。"
    limits='本轮只验证接口、已登记开发工况和脚本作用，不是网络学习、独立评价或完整新训练准入；共同几何/控制/保护保持，旧失败不改写。'
    next_text=('补齐边界滤波实际触发检查、137维新观测的学习掩码/回放与奖励绑定、保存加载和优化器恢复准入，不重复已通过的零动作回合；通过后按新一次性账本执行已提议的F/S小规模pilot，最多28回合/4000批。该训练预算当前仍未消费、尚未签发训练准入。' if passed else
        '先读取本轮首个未通过项和归档差异，制定针对性修复；不重跑已关闭余量、不启动训练，也不把未执行工况记作通过。')
    summary=f'''<!-- v4-adapter-current -->
**{conclusion}（{stamp[:16]}）。** {numbers}

{mechanism}

{limits} 下一项：{next_text} [结果]({REL}/结果说明.md)、[独立核对]({REL}/assessment.json)、[审查修复]({REL}/review.md)。
<!-- /v4-adapter-current -->'''
    def numeric(r,key):return '—' if r.get(key) is None else f'{r[key]:.3f}'
    table='\n'.join(f"| {r['id']} | {r.get('outcome',r['status'])} | {str(r.get('verification_passed','未完成'))} | {numeric(r,'task_end_time_s')} | {numeric(r,'peak_force_mN')} |" for r in rows)
    physical_filter_cycles=sum(r['filter_cycles'] for r in finished)
    permission_checks=sum(r['permission_checks'] for r in finished)
    masked_requests=sum(r['masked_nonzero_requests'] for r in finished)
    report=f'''# v4残差接入有限预检结果

{stamp}：**{conclusion}**。{numbers}

## 实现与验证

新增残差合成后的一步参考约束：在已限幅基线和候选速度间缩减，保留驱动速度/加速度界；被过滤时使用R−1pm内侧目标，零残差/原本可行请求保持。原请求、权限后请求和实际命令层作用分别记录，经验动作保持权限后的归一化请求。新会话保留分层成功、DriveObservation、参考释放与XY导纳重置链，使用live参考/命令的137维版本化观测；F50允许INSERT/SEARCH，S50只允许SEARCH。

B1只运行原固定导纳，共用v4模型/25秒/裁判和保护；无搜索/恢复。F/S非零脚本在每个INSERT/SEARCH阶段开始20–120ms请求[0.1,−0.1,0.1,−0.1]，S按阶段清零，不是策略推理或学习结果。

{mechanism}

另按归档逐条重算{permission_checks}条动作权限与经验动作映射；其中{masked_requests}条非零请求被阶段权限正确屏蔽，实际残差和经验动作均为零。

| 回合 | 结果 | 接口验证门 | 任务结束 s | 峰值力 mN |
|---|---|---|---:|---:|
{table}

完整逐项证据见[assessment.json](assessment.json)、[一次性账本](run/ledger.json)、[冻结配置](configuration.json)。误差、首次不一致、实际停稳、实际参考端点及非零物理命令通道分别核验，未运行点不补推。B1的合格保护是基线失败，保留分母；所有方法仍须共同真实停稳。

## 离线与审查

[离线重放](offline_replay.json)：16,563个SEARCH零命令逐值相同，132,504个XY有界反事实全部满足预测盘；6个旧反例被过滤。反事实不是新物理样本。{tests}相关检查通过，非全项目测试。[独立审查](review.md)发现4项Important，已单次修复并用RED→GREEN核验：整轮异常封闭、STOP启动前门、实际参考端点复核、完整冻结依赖/runtime复核。无延期Minor。

实际参考门只审核控制周期端点，不保证所有物理子步都在盘内，也不证明多步安全。无效/未停稳/接口失败使整轮停止；源文件与准备文件执行前后核对，所有已尝试回合保留。

本轮真实回合边界滤波触发{physical_filter_cycles}个周期。若为0，说明脚本未走到过滤分支，不能把离线6个反例通过写成滤波已在物理中触发；需在训练准入前另登记最小触发检查。动态脚本仅为0.1归一化脉冲，不能扩展为整个[-1,1]策略空间已经实测合格。

## 当前边界与下一步

{limits} {next_text}

沿用原工作树及全部未提交修改；未提交、清理或重写历史。关键选择：新增适配器而不改冻结基类；在已限幅速度段上缩减以保持凸可行性；增量作用与原请求分记；实际端点检查作为准入门而不将预测当物理保证。这些选择的限制已在本节和[计划](../../../docs/superpowers/plans/2026-10-04-v4-residual-adapter.md)写明。
'''
    save(OUT/'结果说明.md',report)
    docs=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    for name in docs:
        before=OUT/'before_documents'/name;before.parent.mkdir(parents=True,exist_ok=True)
        if not before.exists():shutil.copy2(ROOT/name,before)
    for name in [docs[0],docs[1],docs[2],docs[4]]:
        text=(ROOT/name).read_text(encoding='utf8');block=summary
        if name.startswith('deliverables/'):block=block.replace(']('+REL,'](../../../'+REL)
        text,n=re.subn(r'<!-- paper-protocol-current -->.*?<!-- /paper-protocol-current -->',lambda _:block,text,count=1,flags=re.S)
        assert n==1,name;save(ROOT/name,text)
    p=ROOT/docs[1];text=p.read_text(encoding='utf8')
    text=re.sub(r'^最后更新：[^。]+。','最后更新：'+stamp[:10]+'。',text,count=1,flags=re.M)
    text=re.sub(r'^\| B\.1 接口与训练准入包 .*$',f'| B.1 接口与训练准入包 | 旧版本已验收；v4有限预检状态见结果 | [本轮]({REL}/结果说明.md) | {limits} |',text,flags=re.M)
    text=re.sub(r'^\| B\.2 小规模学习与评价包 .*$',f'| B.2 小规模学习与评价包 | 待验收；{conclusion} | [本轮]({REL}/结果说明.md) | 新训练0、未证明SAC增益 |',text,flags=re.M)
    updates={'1 开发适用性':'保持共同v4有限开发范围；不扩展连续域/硬件/独立评价','2 统一闭环/SAC接口':conclusion+'；合成后约束、137维相对观测和F/S阶段权限已实现',
        '3 动态闭环/成本':numbers,'4 B1':f'新任务已完成{len(b1)}/5点，功能成功{sum(r["full_success"] for r in b1)}；全部有效失败保留',
        '5 B2与批量评价':mechanism,'6 普通残差SAC':'v4接口/脚本状态见本轮；网络更新0，学习收益待验证',
        '7 阶段与进展约束':'F50/S50阶段掩码实现，未新增进展候选或证明增益','8 正式证据与展示':'本轮轨迹、动作、观测、停稳及输入快照归档；正式独立测试0、多种子未完成'}
    for label,value in updates.items():text=re.sub(r'^\| '+re.escape(label)+r' \|.*$',f'| {label} | {value} |',text,flags=re.M)
    start=text.index('## 当前风险和准入门')+len('## 当前风险和准入门');end=text.index('| 项目 | 当前事实 | 解除条件 |',start)
    text=text[:start]+'\n\n当前优先风险：'+limits+' '+mechanism+'\n\n下表保留历史学习限制，最新边界以上文为准。\n\n'+text[end:]
    text=section(text,'## 下一项交付',next_text+f' [本轮证据]({REL}/结果说明.md)。')
    text=text.replace('## 追加式阶段记录\n\n',f'## 追加式阶段记录\n\n### {stamp[:16]}｜v4残差接入预检收口\n\n{conclusion}。{numbers} {mechanism} {limits} 下一项：{next_text} [结果]({REL}/结果说明.md)、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n\n',1);save(p,text)
    p=ROOT/docs[2];text=p.read_text(encoding='utf8').replace('| v4共同对照准备 |','| 已封存v4共同对照准备 |',1)
    text=text.replace('|---|---|---|\n',f'|---|---|---|\n| v4残差接入有限预检 | [结果]({REL}/结果说明.md)、[核对]({REL}/assessment.json) | {conclusion} |\n',1)
    text=text.replace('## 基线与接口交付\n\n',f'## 基线与接口交付\n\n### PC-02｜v4残差接入有限预检（{stamp[:10]}）\n\n[结果/边界]({REL}/结果说明.md)、[配置]({REL}/configuration.json)、[计划](docs/superpowers/plans/2026-10-04-v4-residual-adapter.md)。{numbers} {mechanism} {limits} runner已消费或关闭本轮额度，禁止重启原目录。\n\n',1);save(p,text)
    p=ROOT/docs[3];text=p.read_text(encoding='utf8');where=text.index('\n## ')
    text=text[:where]+f'\n## {stamp[:16]}：v4接入预检后的执行修订\n\n{conclusion}。{numbers}\n\n{mechanism}\n\n{limits} {next_text} [结果]({REL}/结果说明.md)。以下保留历史依据，下一项以上文为准。\n'+text[where:];save(p,text)
    p=ROOT/docs[4];text=p.read_text(encoding='utf8')
    text=re.sub(r'^统计截至：.*?。',f'统计截至：{stamp[:16]}（北京时间）。',text,count=1,flags=re.M)
    text=re.sub(r'^最新对照准备：.*$',f'最新接入预检：{numbers} {mechanism} [核对](../../../{REL}/assessment.json)。',text,count=1,flags=re.M)
    text=re.sub(r'^最新：.*$',f'最新：{limits}',text,count=1,flags=re.M)
    text=text.replace('本轮新增：旧残差合成有6个命令级参考越界反例，尚未修复，不能直接训练；没有新增动力学失败。','历史PC-01发现：旧合成的6个命令级越界反例已在本轮离线修复；实际接入预检见顶部，不等于训练准入。',1)
    text=text.replace('## 四、图表与讲稿\n',f'## 四、图表与讲稿\n\n最新结果表：[零等价、脚本和B1逐回合结果](../../../{REL}/结果说明.md)。讲稿：“{conclusion}；{mechanism}下一步仍需补齐新训练准入，不能将脚本效果当作SAC收益。”\n',1)
    text=section(text,'## 五、下一项',next_text+f' [本轮报告](../../../{REL}/结果说明.md)。')
    text=text.replace('## 六、来源记录\n\n',f'## 六、来源记录\n\n{stamp[:16]}｜[PC-02结果](../../../{REL}/结果说明.md)、[账本](../../../{REL}/run/ledger.json)、[独立核对](../../../{REL}/assessment.json)、[审查](../../../{REL}/review.md)。{numbers}\n\n',1);save(p,text)
    plan=ROOT/'docs/superpowers/plans/2026-10-04-v4-residual-adapter.md'
    save(plan,plan.read_text(encoding='utf8').replace('- [ ]','- [x]')+f'\n## 实际收口\n\n{stamp}：{conclusion}。{numbers} 任务勾选代表实现、有限验证执行或受控停止、归档完成，不代表全部工况通过或训练准入。\n')
    with (OUT/'progress.md').open('a',encoding='utf8') as f:f.write(f'\nTask 3: complete — {conclusion}。{numbers}\nTask 4: complete pending seal — 结果独立核对、五份滚动资料更新；详见assessment.json。\n')
    save(OUT/'closeout_context.json',json.dumps(dict(stamp=stamp,conclusion=conclusion,numbers=numbers,mechanism=mechanism,limits=limits,next_text=next_text),ensure_ascii=False,indent=2)+'\n')
    print(conclusion,numbers)

if __name__=='__main__':main()
