"""Build offline diagnosis figures/report, then maintain and seal this stage."""
import argparse,datetime,json,re,shutil,os,math
from pathlib import Path
from diagnose import OUT,ROOT,PC07,read,write,sha,verify_sources

DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
BASE='deliverables/paper_comparison/residual_effect_diagnosis_20261007/'

def build():
    r=read(OUT/'diagnosis.json');assert r['source_proof']==verify_sources()
    assert r['archive_count']==37 and len(r['prefixes'])==14 and all(p['trace_prefix_exact'] for p in r['prefixes'])
    trained=[e for e in r['records'] if e['provider']=='S2000' and e['case_id']!='aligned']
    assert len(trained)==8 and all(e['peak_before_first_enabled'] for e in trained)
    assert all(e['active_predicted_end_command_mismatch_cycles']==0 for e in r['records'])
    recovery=[dict(id=e['id'],cycles=e['predicted_end_command_mismatch_cycles'],phases=e['command_mismatch_physical_phases']) for e in r['records'] if e['predicted_end_command_mismatch_cycles']]
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_pc08'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(10,6));timeline=[]
    for i,e in enumerate(trained):
        interval=e['peak_cycle_interval_s'];label=('dev ' if e['group']=='development' else 'first-use ')+e['case_id']
        ax.plot(interval,[i,i],color='#bd3f32',lw=5);ax.plot(sum(interval)/2,i,'o',color='#bd3f32')
        ax.plot(e['first_enabled_time_s'],i,'s',color='#2175aa');timeline.append(dict(id=e['id'],label=label,peak_cycle_interval_s=interval,first_enabled_time_s=e['first_enabled_time_s']))
    ax.set_yticks(range(8),[e['label'] for e in timeline]);ax.invert_yaxis();ax.set_xlabel('Recorded simulation time (s)')
    ax.set_title('S2000: peak-force cycle precedes first residual permission\nAll eight contact cases; physical prefixes match B2 exactly')
    ax.plot([],[],'o',color='#bd3f32',label='Peak cycle (2 ms interval)');ax.plot([],[],'s',color='#2175aa',label='First enabled cycle')
    ax.legend();ax.grid(axis='x',alpha=.2);fig.tight_layout();fig.savefig(OUT/'peak_before_action.png',dpi=180);plt.close(fig)
    clipping=[]
    for e in r['records']:
        if e['group']!='development' or e['provider'] not in ('F2000','S2000'):continue
        phase='INSERT' if e['provider']=='F2000' else 'SEARCH';s=e['stages'].get(phase)
        if not s or not s['enabled_cycles']:continue
        clipping.append(dict(id=e['id'],label=e['provider']+' '+phase+' '+e['case_id'],enabled=s['enabled_cycles'],
            legacy_pct=100*s['clipped_cycles']/s['enabled_cycles'],target_limited_pct=100*s['total_target_limited_cycles']/s['enabled_cycles']))
    fig,ax=plt.subplots(figsize=(11,6.5));ys=list(range(len(clipping)))
    ax.barh([y-.18 for y in ys],[x['legacy_pct'] for x in clipping],height=.32,label='Request differs from instantaneous zero-alternative delta',color='#9a9a9a')
    ax.barh([y+.18 for y in ys],[x['target_limited_pct'] for x in clipping],height=.32,label='Post-stage total target differs from final drive command',color='#2474b5')
    ax.set_yticks(ys,[x['label'] for x in clipping]);ax.invert_yaxis();ax.set_xlim(0,105);ax.set_xlabel('Fraction of residual-enabled cycles (%)')
    ax.set_title('Limiter diagnostics differ: persistent residuals remain in command history\nDevelopment archives only; neither measure is caused physical displacement')
    handles,labels=ax.get_legend_handles_labels();fig.legend(handles,labels,loc='lower center',fontsize=8)
    ax.grid(axis='x',alpha=.2);fig.tight_layout(rect=(0,.07,1,1));fig.savefig(OUT/'limiter_definitions.png',dpi=180);plt.close(fig)
    write(OUT/'figure_data.json',dict(timeline=timeline,clipping=clipping,recovery_command_differences=recovery,diagnosis_sha256=sha(OUT/'diagnosis.json')))
    aligned=next(e for e in r['records'] if e['provider']=='F2000' and e['case_id']=='aligned')
    s=aligned['stages']['INSERT'];net=math.hypot(*s['actual_xy_net_um'])
    rows=['| 开发档案阶段 | 启用周期 | 旧请求/即时差不等 | 总命令确实受限 | 零测得wrench仍启用 |','|---|---:|---:|---:|---:|']
    for e in r['records']:
        if e['group']!='development' or e['provider'] not in ('F2000','S2000'):continue
        for phase,a in e['stages'].items():
            if not a['enabled_cycles']:continue
            rows.append(f"| {e['provider']} {e['case_id']} {phase} | {a['enabled_cycles']} | {a['clipped_cycles']} | {a['total_target_limited_cycles']} | {a['zero_measured_wrench_enabled_cycles']} |")
    report=f'''# PC-08残差实际作用归因

**归因完成；候选尚未实现或验证。** 只读37档案、{r['cycle_rows']:,}周期；新增动态/优化/网络策略调用/经验发布0，累计动态仍200。PC-07的96文件、PC-06的457文件和1057生产输入保持。

当前有限证据支持三项判断：S对这些工况启用得晚，无法改变已发生的力峰；F在无接触反馈阶段仍能引入不必要的扰动；旧“裁剪”字段不足以证明残差未被执行。没有证据据此宣布SAC整体无效或已解决全部历史问题。

## 实际归因

1. 已训练S四个有接触开发点和四首次位置共8个工况，全回合力峰值周期严格先于首个残差许可周期；14/14 S初始或已训练评价与B2在许可前完整轨迹前缀一致。对中S全程未启用、力0，另行记录，不伪造许可时刻。峰值仅定位到2ms周期区间，不推断子步时刻。
2. 开发S相对B2的省时10.916s中，负Y贡献10.020s（91.79%）；四首次位置S仍慢于B2约1.38%。这是收益集中和未见稳定优势，不足以单凭四点断言过拟合。
3. 对中F的INSERT启用2050周期，其中1859周期动作前测得wrench完全为0。该工况实际净侧移约{net:.3f}μm、全回合峰值力{aligned['peak_force_N']*1000:.6f}mN；B2/S没有侧移或接触。当前F在INSERT中普遍仍输出残差，不是只在有效接触时纠偏。
4. 对中F旧口径2050/2050“裁剪”，总命令确实受限仅378/2050；37份档案残差启用周期的最终预测命令与执行器记录一致。持续40μm/s残差已执行时，因上一命令含历史残差，零替代命令只来得及降到30μm/s，即时差10μm/s；不能据0.25比值称75%未执行。
5. 当前奖励为推进、时间、力/力矩及功能终末奖励，没有直接XY精度项（[源码](../../../tools/learning/reward.py)）。四新位置附加80μm/0.5°均0/4，功能成功另为4/4；不能把附加精度未达标当成软件判错，或声称功能成功已满足该精度。

{chr(10).join(rows)}

![峰值与许可](peak_before_action.png)

![两种限幅统计](limiter_definitions.png)

## 下一项最小方案

先检验一条接触权限规则G50：SEARCH保持启用，INSERT只有已有5mN轴向反力门槛满足时启用；其余共同保护不变。同时保留F50并加入0.25尺度的F12.5，避免把权限收益混成单纯缩小动作的收益。采用现有137维/4维接口，不叠加新网络、critic技巧、奖励或进展模块。该候选只由开发点和既有5mN配置提出，四首次位置不用于挑参数。

[具体候选、8回合无训练预检和准入条件](next_candidate.md)。这8回合是下一项拟登记预算，当前执行0；不能跳过新权限在会话、观测、采集和审核中的一致性检查。只读原F检查点进行部署探测，不声称新门控下已训练或跨方法完整恢复。若出现明显退化，收口并复审研究假设，不再盲目加训。

## 复核与限制

17项手算反例先RED后GREEN；另2项持续残差/驱动限幅反例和2项启用/回撤命令差反例各RED后GREEN，最终57关联离线检查通过。代码只在本交付目录；生产0修改。原始来源和数组对齐、dt、动作前阶段、许可、有限数、峰值及完整前缀核对见[配置](configuration.json)和[全部归因](diagnosis.json)。旧clipped统计仍按其原定义保留，未改写历史档案或已训练的观测字段。

三份负Y档案（B2成功、F0/S0普通失败）各275个残差禁用的回撤周期，策略侧预测零命令、执行器接管Z回撤，共825个差异周期全部保留；不属于启用残差的预测失败。此前“所有周期都应一致”的收口断言被实际记录否定，已用两个反例纠正统计。命令差异的真实阶段明细见diagnosis.json和figure_data.json，不删失败或重跑物理。

effective_command_delta只是同一历史状态下的命令层对照。真实XY路径和旋转路径另计，分阶段整段包含停稳尾段，task_duration单列；不能把请求积分、命令差积分或物理路径互相替换。总命令限幅统计比较的是**已经过阶段上限**的目标与最终驱动预测，不包含无法由此恢复的更早阶段裁剪。

单训练种子、有限开发点与已消费的四首次位置；不新增独立效果样本，不覆盖姿态/联合扰动或机械臂/夹爪。B.2位置里程碑保持，完整B.2/C/论文优势仍待验收。阶段完成后暂停汇报，自动跟踪保持PAUSED。

[阶段记录](progress.md)、[审查](review.md)、[封存](delivery_manifest.json)。分析会写输出，封存后只在完整副本复核，不修改原封存依赖。
'''
    (OUT/'结果说明.md').write_text(report,encoding='utf8',newline='\n')
    print('PC-08 two figures and report built; review/closure pending')

def close():
    review=read(OUT/'review.json')
    assert review['unresolved_critical']==review['unresolved_important']==0 and read(OUT/'figure_qa.json')['passed']
    r=read(OUT/'diagnosis.json');assert verify_sources()==r['source_proof']
    summary='离线37档案/245,221周期归因通过；已训练S八接触工况的峰值全部先于残差许可，14/14前缀与B2相同；对中F引入约100μm侧移和5.383mN接触。旧请求/即时差统计不是执行损失，总命令限幅已分列。新增动态/训练/策略调用/发布0，累计200；137维/4维及1057生产输入保持。'
    next_text='下一项实现并登记G50接触门控及F12.5较小固定边界的有界部署预检（拟8回合、训练0）；先通过权限/来源/保存与只读检查，才启动新预算。当前候选未实现、未准入、未执行。完整B.2/C及论文优势仍待；四首次位置已消费，旧预算关闭，自动跟踪PAUSED。'
    for name in DOCS:
        p=ROOT/name;s=p.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else ''
        block=f'<!-- pc08-current -->\n**PC-08收口（2026-10-07）：残差实际作用归因已验收，候选仅为下一方案。** {summary}\n\n{next_text} [结果与图]({prefix}{BASE}结果说明.md)、[最小候选]({prefix}{BASE}next_candidate.md)、[原始归因]({prefix}{BASE}diagnosis.json)。阶段完成暂停汇报；下方记录保留历史时点。\n<!-- /pc08-current -->'
        if '<!-- pc08-current -->' in s:s=re.sub(r'<!-- pc08-current -->.*?<!-- /pc08-current -->',lambda _:block,s,count=1,flags=re.S)
        else:s=s.replace('\n','\n\n'+block+'\n',1)
        if name=='项目进度跟踪.md':
            s=re.sub(r'^\| C 候选约束与消融 \|.*$',f'| C 候选约束与消融 | 待验收；PC-08完成离线归因 | [归因及下一候选]({BASE}结果说明.md) | G50/F12.5仅拟预检；连续进展未实现，不能把命令差比值当物理损失 |',s,count=1,flags=re.M)
            s=re.sub(r'^\| 7 阶段与进展约束 \|.*$',f'| 7 阶段与进展约束 | PC-08归因完成；S峰值时序受权限限制、F对中额外干扰；新接触候选与小固定对照待实现，完整进展约束未实现 |',s,count=1,flags=re.M)
            s=re.sub(r'(## 下一项交付\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+next_text+f' [方案]({BASE}next_candidate.md)。\n',s,count=1,flags=re.S)
            s=re.sub(r'当前风险：.*?(?=\n\n)',lambda _:'当前风险：'+summary+' '+next_text,s,count=1,flags=re.S)
            s+=f'\n### 2026-10-07｜PC-08残差作用离线归因收口\n\n{summary}\n\n{next_text} [证据]({BASE}结果说明.md)、[10月月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        if name=='项目交付总览.md' and '### PC-08｜' not in s:
            s=s.replace('### PC-07｜',f'### PC-08｜残差实际作用归因（2026-10-07）\n\n{summary}\n\n[使用与结果]({BASE}结果说明.md)、[候选]({BASE}next_candidate.md)、[封存]({BASE}delivery_manifest.json)。只读旧档案；不新增论文性能样本或生产算法。\n\n### PC-07｜',1)
        if name.startswith('deliverables/'):
            mb='../../paper_comparison/residual_effect_diagnosis_20261007/'
            bodies={'一、本月综合摘要':summary,'二、关键数字与证据':summary+' 57关联检查通过；旧96+457封存文件保持；825个禁用回撤命令差单列保留。',
                '三、负结果与限制':'S无法改变许可前已发生的峰值；开发收益集中负Y91.79%。旧裁剪字段高占比不等于动作未执行；F对中产生额外干扰。没有新增独立样本，也不能单凭四点断言过拟合或SAC整体无效。',
                '四、图表与讲稿':f'[峰值先于许可]({mb}peak_before_action.png)、[限幅口径区别]({mb}limiter_definitions.png)。讲稿：“学习链能工作，当前主要问题是权限与评价目标是否对得上。先查无接触残差干扰，并加入小固定边界对照，暂不盲目加训。”'}
            for title,body in bodies.items():s=s.replace('## '+title+'\n','## '+title+'\n\nPC-08：'+body+'\n',1)
            s=re.sub(r'(## 五、下一项\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+next_text+'\n',s,count=1,flags=re.S)
            s+=f'\n### 2026-10-07｜PC-08归因来源\n\n{summary} {next_text} [来源]({mb}结果说明.md)。\n'
        p.write_text(s,encoding='utf8',newline='\n')
        dest=OUT/'documents_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    write(OUT/'closure_verification.json',dict(passed=True,archive_count=37,cycle_rows=r['cycle_rows'],sources_unchanged=verify_sources(),
        tests=57,new_physics=0,new_optimizer_batches=0,new_network_calls=0,published_transitions=0,cumulative_dynamic=200,
        figure_qa=True,independent_review=read(OUT/'review.json'),scope='offline diagnosis complete; candidate implementation/admission/effect unverified'))
    with (OUT/'progress.md').open('a',encoding='utf8') as f:f.write('\nTask2: complete — report, figure data/visual QA, one review, five rolling documents/snapshots maintained. Candidate not implemented/admitted; new physics/training0. Stage completed, pause and report.\n')
    print('Five documents and closure proof updated')

def seal():
    assert read(OUT/'closure_verification.json')['passed'];verify_sources()
    cfg=read(OUT/'configuration.json')
    for n,pin in cfg['diagnostic_input_sha256'].items():assert sha(ROOT/n)==pin,n
    links=0
    for name in DOCS:
        p=ROOT/name;assert sha(p)==sha(OUT/'documents_snapshot'/name)
        block=re.search(r'<!-- pc08-current -->.*?<!-- /pc08-current -->',p.read_text(encoding='utf8'),re.S).group()
        for target in re.findall(r'\]\(([^)]+)\)',block):assert (p.parent/target).resolve().exists();links+=1
    for target in re.findall(r'\]\(([^)]+)\)',(OUT/'结果说明.md').read_text(encoding='utf8')):
        p=(OUT/target).resolve();assert p.exists() or p==OUT/'delivery_manifest.json';links+=1
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='delivery_manifest.json' and '__pycache__' not in p.parts}
    write(OUT/'delivery_manifest.json',dict(status='SEALED',created_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        scope='offline descriptive attribution; no new physics, policy inference, optimization or candidate effectiveness',files=files,local_links_checked=links))
    assert all(sha(OUT/n)==v['sha256'] for n,v in files.items())
    print(json.dumps(dict(files=len(files),sha256=sha(OUT/'delivery_manifest.json'),links=links)))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('step',choices=('build','close','seal'));args=a.parse_args()
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Already sealed')
    {'build':build,'close':close,'seal':seal}[args.step]()
