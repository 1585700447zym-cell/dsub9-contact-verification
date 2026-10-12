"""PC-09 report, figures, rolling documents and one-time delivery seal."""
import argparse,datetime,json,re,shutil,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
from run_probe import read,sha,write,verify_sources
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
BASE='deliverables/paper_comparison/contact_gate_probe_20261007/'

def build():
    import os
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_pc09_figures'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    a=read(OUT/'assessment.json');assert a['audit_errors']==[]
    rows=[r for p in ('B2','F50','F12.5','G50') for r in a['records'][p] if r['status']=='finished']
    fig,axs=plt.subplots(1,2,figsize=(11,4.2))
    methods=('B2','F50','F12.5','G50');colors=('#777777','#d47b37','#4b94c6','#4a9e69')
    figure_rows=[]
    for ax,case in zip(axs,('aligned','y_neg_150')):
        rs=[next((r for r in rows if r['profile']==p and r['case_id']==case),None) for p in methods]
        values=[r['task_end_time_s'] if r and r['outcome']=='FULL_SUCCESS' else 26. for r in rs]
        ax.bar(methods,values,color=colors);ax.set_ylim(0,29);ax.set_ylabel('All-attempt penalized task time (s)');ax.set_title(case)
        for i,(v,r) in enumerate(zip(values,rs)):
            label=f'{v:.3f}s\n'+(r['outcome'].replace('FULL_SUCCESS','success').replace('TASK_FAILURE','failure') if r else 'missing')
            ax.text(i,v+.5,label,ha='center',fontsize=8)
            figure_rows.append(dict(profile=methods[i],case=case,penalized_time_s=v,outcome=r['outcome'] if r else None))
        ax.grid(axis='y',alpha=.2)
    fig.suptitle('Frozen actor deployment probe: two used development positions\nNo new training; ordinary failures retained with 26 s penalty',fontsize=11)
    fig.tight_layout();fig.savefig(OUT/'time_comparison.png',dpi=180);plt.close(fig)
    fig,axs=plt.subplots(1,2,figsize=(11,4.2))
    for ax,case in zip(axs,('aligned','y_neg_150')):
        rs=[next((r for r in rows if r['profile']==p and r['case_id']==case),None) for p in methods]
        values=[1000*r['peak_force_N'] if r else float('nan') for r in rs]
        ax.bar(methods,values,color=colors);ax.axhline(25,color='#b32626',ls='--',label='Common 25 mN guard')
        ax.set_ylim(0,28);ax.set_ylabel('Whole-episode peak force (mN)');ax.set_title(case)
        for i,(v,r) in enumerate(zip(values,rs)):
            if r:ax.text(i,v-1.4 if v>2 else v+.4,f'{v:.3f}',ha='center',fontsize=9,color='white' if v>2 else 'black')
        ax.grid(axis='y',alpha=.2);ax.legend(fontsize=8)
    fig.suptitle('Whole-episode loads, including stages before actor permission\nSame model and protection; frozen deployment sensitivity only',fontsize=11)
    fig.tight_layout();fig.savefig(OUT/'force_comparison.png',dpi=180);plt.close(fig)
    write(OUT/'figure_data.json',dict(time=figure_rows,load=[dict(profile=r['profile'],case=r['case_id'],peak_force_mN=1000*r['peak_force_N']) for r in rows],assessment_sha256=sha(OUT/'assessment.json')))
    lines=['| 方法 | 工况 | 功能结果 | 判定用时s | 峰值力mN | 80μm/0.5° | NN调用 | INSERT力门控阈值切换 |','|---|---|---|---:|---:|---|---:|---|']
    for r in rows:lines.append(f"| {r['profile']} | {r['case_id']} | {r['outcome']} | {r['task_end_time_s']:.3f} | {1000*r['peak_force_N']:.6f} | {'达标' if r['strict_precision_success'] else '未达标'} | {r['network_calls']} | {r['insert_force_gate_switches'] if r['profile']=='G50' else '不适用'} |")
    next_text=(OUT/'next_step.md').read_text(encoding='utf8')
    text=f'''# PC-09接触门控与小固定边界部署预检

**固定部署预检已按实际结果收口；完整B.2/C与论文优势另行验收。** 新启动{a['new_attempts']}/8、完成{a['finished']}，累计动态{a['cumulative_dynamic']}，未用{a['unused_closed']}关闭；新增优化和经验发布0。

{chr(10).join(lines)}

两点都是已用开发工况、同一训练种子。B2零残差且没有网络；F50/F12.5/G50只读原F2000演员。F12.5的四个演员输出乘0.25，不是小尺度下重训；G50在SEARCH开放，INSERT以动作前测得5mN轴向反力开放，原共同保护同时生效。没有改模型、奖励、137维/4维或生产代码。

![固定8回合时间](time_comparison.png)

![完整回合峰值载荷](force_comparison.png)

{next_text}

## 复核证据与实际成本

{len(a['baseline_continuity'])}份B2/F50新档案与旧同版本完整trace、控制器事件、结果、外部事件、停稳样本、峰值及动作（除新增角色/原演员元数据）逐值一致。G50对中与B2完整轨迹一致：{a['aligned_G50_B2_trace_exact']}。逐条动作前wrench与上一实际trace的归一化观测一致；演员输出与实际请求映射、门控/mask、终末和物理时间折扣均复核。

独立复算{a['independent_reward_rows']:,}条奖励、推进与时间，功能几何/附加精度、循环峰值/末点、实际停稳全部按原判据。成本{a['control_cycles']:,}控制周期/{a['physical_substeps']:,}物理子步、真实网络成功/尝试{a['network_policy_calls']:,}/{a['network_attempts']:,}次；回合墙时合计{a['wall_seconds']:.1f}s，读取/审核开销另在执行日志，不混成仿真时间。所有普通失败保留，26s罚时计入均值；保护不被算成成功。

88相关离线检查（38新+50旧）；一次fresh限定只读审查C0/I1/M0，初始化异常留档问题经作者两种无物理反例RED/GREEN及回归关闭，未二次独立复审。审查在物理资格前，未来结果由作者完整重读原档案核验；不冒称第二次独立效果审查。两次原F2000完整读取（准备与实际执行）均保持原完整状态，每回合前后模型/优化器/RNG保持；不宣称新G权限下训练状态恢复。

原1057生产输入、PC-06/07/08全部580封存文件重新核验保持；旧预算关闭、自动跟踪PAUSED。没有新增最终未见测试，四旧首次位置不用于本项选参。机械臂/夹爪、姿态联合范围、多种子、合理固定边界重训和论文统计仍缺。

[原始复核](assessment.json)、[配置](configuration.json)、[资格](qualification.json)、[实际账本](run/ledger.json)、[审查与修正](review.md)、[最终检查](closure_verification.json)、[阶段记录](progress.md)、[封存](delivery_manifest.json)。执行目录一次领取，不复跑；分析生成文件，封存后只在完整副本核对。
'''
    (OUT/'结果说明.md').write_text(text,encoding='utf8',newline='\n');print('Report and two figures built')

def close():
    a=read(OUT/'assessment.json');l=read(OUT/'run/ledger.json');c=read(OUT/'configuration.json')
    assert a['audit_errors']==[] and read(OUT/'figure_qa.json')['passed']
    assert l['status'] in ('complete','error','controlled_stop') and l['unused_closed']==8-len(l['episodes'])
    assert l['formal_updates']==l['published_transitions']==0 and a['new_attempts']==len(l['episodes'])
    verify_sources(c,full=True)
    q=read(OUT/'qualification.json');assert sha(OUT/'qualification.json')==l['qualification_sha256']
    for n,p in q['evidence_sha256'].items():assert sha(OUT/n)==p,n
    for e in l['episodes']:
        if e['status']=='finished':assert sha(OUT/'run'/(e['id']+'.json.gz'))==e['archive_sha256']
    assert read(OUT/'review.json')['critical']==read(OUT/'review.json')['important']==0
    summary=(OUT/'closure_summary.md').read_text(encoding='utf8').strip()
    next_text=(OUT/'next_step.md').read_text(encoding='utf8').strip()
    for name in DOCS:
        p=ROOT/name;s=p.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else ''
        doc_next=next_text.replace('](failure_summary.json)',f']({prefix}{BASE}failure_summary.json)')
        block=f'<!-- pc09-current -->\n**PC-09收口（2026-10-07）：固定接触门控/较小边界部署预检完成；完整B.2/C仍待验收。** {summary}\n\n{doc_next}\n\n[结果与图]({prefix}{BASE}结果说明.md)、[原始复核]({prefix}{BASE}assessment.json)、[账本]({prefix}{BASE}run/ledger.json)。阶段完成暂停汇报；下方保留历史时点。\n<!-- /pc09-current -->'
        if '<!-- pc09-current -->' in s:s=re.sub(r'<!-- pc09-current -->.*?<!-- /pc09-current -->',lambda _:block,s,count=1,flags=re.S)
        else:s=s.replace('\n','\n\n'+block+'\n',1)
        if name=='项目进度跟踪.md':
            table={
                '1 开发适用性':'已有五开发点及四个已消费首次位置；PC-09仅重复对中/负Y两已用点，单种子，未扩展姿态/硬件',
                '2 统一闭环/SAC接口':'137维/4维及1057生产输入保持；新G权限/缩放显式评价合同通过，不等于新权限训练准入',
                '5 B2与批量评价':'PC-09两个B2零网络回合成功，与旧同版本完整轨迹一致；四方法同两点，失败不替换',
                '6 普通残差SAC':'PC-09冻结F50/F12.5各2/2功能成功；小尺度只是部署敏感性、未重训；原critic技巧保持，不称原样标准SAC',
                '8 正式证据与展示':'PC-09全部8档案/原始复核/两图封存；G1/2失败如实保留；新的最终测试和三个训练种子的论文证据仍未完成'}
            for key,value in table.items():s=re.sub(r'^\| '+re.escape(key)+r' \|.*$',f'| {key} | {value} |',s,count=1,flags=re.M)
            s=re.sub(r'^\| C 候选约束与消融 \|.*$',f'| C 候选约束与消融 | 待验收；PC-09固定部署预检收口 | [结果及下一项]({BASE}结果说明.md) | 本项为冻结部署，不是G重训/正式消融；连续进展未实现 |',s,count=1,flags=re.M)
            s=re.sub(r'^\| 3 动态闭环/成本 \|.*$',f'| 3 动态闭环/成本 | PC-09新{a["new_attempts"]}/8、完成{a["finished"]}，累计{a["cumulative_dynamic"]}；{a["control_cycles"]:,}周期/{a["physical_substeps"]:,}子步，NN{a["network_policy_calls"]:,}，新优化/发布0，未用{a["unused_closed"]}关闭 |',s,count=1,flags=re.M)
            s=re.sub(r'^\| 7 阶段与进展约束 \|.*$',f'| 7 阶段与进展约束 | PC-09接触门控与小固定边界冻结部署已评价；完整训练/进展约束与论文优越性待验收 |',s,count=1,flags=re.M)
            s=re.sub(r'(## 下一项交付\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+doc_next+'\n',s,count=1,flags=re.S)
            s=re.sub(r'当前风险：.*?(?=\n\n)',lambda _:'当前风险：'+summary+' '+doc_next,s,count=1,flags=re.S)
            s+=f'\n### 2026-10-07｜PC-09接触门控固定部署收口\n\n{summary}\n\n{doc_next} [证据]({BASE}结果说明.md)、[当月素材](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
            s=s.replace('本轮只收口限定固定对照/首次位置评价，不以方法打平或运行通过标论文方法有效。','本轮仅收口两个已用位置的固定部署预检；G失败不改写为通过，运行有效与论文方法有效分别判断。')
        if name=='项目交付总览.md' and '### PC-09｜' not in s:
            s=s.replace('### PC-08｜',f'### PC-09｜接触门控与小固定边界部署预检（2026-10-07）\n\n{summary}\n\n[结果与使用]({BASE}结果说明.md)、[资格]({BASE}qualification.json)、[封存]({BASE}delivery_manifest.json)。固定8回合一次领取；分析仅完整副本复核，不把冻结部署算G训练。\n\n### PC-08｜',1)
        if name.startswith('deliverables/'):
            mb='../../paper_comparison/contact_gate_probe_20261007/'
            bodies={'一、本月综合摘要':summary,'二、关键数字与证据':summary+' 88关联离线检查、旧580文件与1057生产输入保持；PC-06两组各2000批未追加。',
                '三、负结果与限制':doc_next+' 两个已用位置和一个训练种子不足以证明泛化；小固定边界未重训，新门控未学习。',
                '四、图表与讲稿':f'[全尝试时间]({mb}time_comparison.png)、[完整回合力峰]({mb}force_comparison.png)。讲稿：“这轮只验证冻结演员的权限和尺度。看对中干扰是否消除，再看偏置纠正是否保留；成功、工程运行和论文优势分别判断。”'}
            for title,body in bodies.items():s=s.replace('## '+title+'\n','## '+title+'\n\nPC-09：'+body+'\n',1)
            s=re.sub(r'(## 五、下一项\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+doc_next+'\n',s,count=1,flags=re.S)
            s+=f'\n### 2026-10-07｜PC-09部署预检来源\n\n{summary} {doc_next} [来源]({mb}结果说明.md)。\n'
        p.write_text(s,encoding='utf8',newline='\n');dest=OUT/'documents_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    write(OUT/'closure_verification.json',dict(passed=True,new_attempts=a['new_attempts'],finished=a['finished'],new_dynamics=a['new_attempts'],
        reward_rows=a['independent_reward_rows'],baseline_continuity=len(a['baseline_continuity']),aligned_G50_B2_trace_exact=a['aligned_G50_B2_trace_exact'],
        production_inputs_unchanged=1057,prior_archive_files_unchanged=580,source_checks_full=True,optimizer_updates=0,published_transitions=0,
        network_calls=a['network_policy_calls'],cumulative_dynamic=a['cumulative_dynamic'],unused_closed=a['unused_closed'],physical_retries=0,
        tests=88,figure_qa=True,independent_review='one pre-execution read-only C0/I1/M0, I1 author-closed; no second review',
        scope='fixed deployment stage closed; method benefit and full B.2/C/paper evidence remain separate'))
    with (OUT/'progress.md').open('a',encoding='utf8') as f:f.write('\nTask3 complete: actual archive/geometry/reward/mask/mapping/stop/cost/source audit, figures visually checked, five rolling documents and snapshots maintained. Stage closed; pause/report.\n')
    print('Five rolling documents/snapshots and closure proof updated')

def seal():
    assert read(OUT/'closure_verification.json')['passed'];c=read(OUT/'configuration.json');verify_sources(c,full=True)
    links=0;manifest=OUT/'delivery_manifest.json'
    for name in DOCS:
        p=ROOT/name;assert sha(p)==sha(OUT/'documents_snapshot'/name)
        block=re.search(r'<!-- pc09-current -->.*?<!-- /pc09-current -->',p.read_text(encoding='utf8'),re.S).group()
        for target in re.findall(r'\]\(([^)]+)\)',block):assert (p.parent/target).resolve().exists();links+=1
    for target in re.findall(r'\]\(([^)]+)\)',(OUT/'结果说明.md').read_text(encoding='utf8')):
        p=(OUT/target).resolve();assert p.exists() or p==manifest,target;links+=1
    files={p.relative_to(OUT).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size) for p in sorted(OUT.rglob('*')) if p.is_file() and p!=manifest and '__pycache__' not in p.parts}
    write(manifest,dict(status='SEALED',created_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        scope='PC-09 fixed eight development deployment attempts, no new training or paper superiority claim',files=files,local_links_checked=links))
    assert all(sha(OUT/n)==v['sha256'] and (OUT/n).stat().st_size==v['bytes'] for n,v in files.items())
    print(json.dumps(dict(files=len(files),sha256=sha(manifest),links=links)))

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('step',choices=('build','close','seal'));args=a.parse_args()
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed; no mutable re-run')
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    {'build':build,'close':close,'seal':seal}[args.step]()
