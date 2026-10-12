"""Update live document sections and append closeout records; never run experiments."""
import datetime, re
import paired_contract as C

START='<!-- stage-resume-current -->';END='<!-- /stage-resume-current -->'
STAGE='deliverables/learning_chain/b2_stage_permission_resume_20261003'
PLAN='docs/superpowers/plans/2026-10-03-stage-permission-resume.md'
FILES=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']

def section(text,heading,change):
    pattern=r'(^'+re.escape(heading)+r'\n)(.*?)(?=^## |\Z)'
    result,n=re.subn(pattern,lambda m:m[1]+'\n'+change(m[2].strip())+'\n\n',text,count=1,flags=re.M|re.S)
    if n!=1:raise ValueError('Missing rolling section: '+heading)
    return result

def managed(body,key,content,history=None):
    start='<!-- '+key+' -->';end='<!-- /'+key+' -->';block=start+'\n'+content+'\n'+end
    if start in body:return re.sub(re.escape(start)+'.*?'+re.escape(end),lambda m:block,body,count=1,flags=re.S)
    return block+('\n\n'+history if history and body and not body.startswith(history) else '')+('\n\n'+body if body else '')

def append_once(body,key,content):
    if '<!-- '+key+' -->' in body:return body
    return body+'\n\n<!-- '+key+' -->\n'+content+'\n<!-- /'+key+' -->'

def row(text,key,value):
    result,n=re.subn(r'^\| '+re.escape(key)+r' \|[^\n]*$',lambda m:value,text,count=1,flags=re.M)
    if n!=1:raise ValueError('Missing current capability/risk row: '+key)
    return result

def points(rows):
    return f'成功{sum(r["success"] for r in rows)}/{len(rows)}个已完成点（计划4）' if rows else '未执行冻结开发点评价（计划4）'

def main():
    if (C.HERE/'result_analysis/delivery_verification.json').exists():raise RuntimeError('Delivery already sealed; retain rolling-document boundary')
    run=C.HERE/'run';state=C.read(run/'ledger.json')
    a=C.read(C.HERE/'result_analysis/assessment.json') if (C.HERE/'result_analysis/assessment.json').exists() else None
    n=len(state['attempts'])-12;b=sum(x['completed'] for x in state['updates'].values());attempted=sum(x['attempted'] for x in state['updates'].values())
    done=state['status']!='healthy';status='已收口' if done else '执行中'
    if done and a is None:raise ValueError('Finished run requires its actual assessment')
    if a and (a['status']!=state['status'] or a['accounting']['new_dynamic_starts']!=n or a['accounting']['formal_batches_completed']!=b or a['accounting']['formal_batches_attempted']!=attempted or a['accounting']['updates']!=state['updates']):raise ValueError('Assessment and ledger differ')
    judgement=a['judgement'] if a else 'incomplete'
    if done and judgement=='incomplete':raise ValueError('Finished ledger lacks a final judgement')
    verdict={
        'controlled_guard_stop':'保护触发后受控停止，完整配对效果尚不能判断',
        'operational_failure':'运行故障阻止完成配对效果判断',
        'insufficient_active_warmup':'活动经验未达预登记门槛，未进行学习',
        'promising_success_signal':'出现预登记成功数积极信号，仍需扩大证据',
        'promising_load_signal':'出现预登记载荷积极信号，仍需扩大证据',
        'successful_without_stage_advantage':'任务成功，但阶段约束额外收益未达门槛',
        'effect_target_not_met':'本轮方法效果未达到预登记目标',
        'incomplete':'实际效果尚未判定'}[judgement]
    next_step={
        'promising_success_signal':'先制定多训练种子、未参与调参的评价工况和必要消融计划及新预算；本轮只是继续研究信号，不直接宣称论文收益或扩大计算。',
        'promising_load_signal':'先制定多训练种子、未参与调参的载荷/效率评价与消融计划及新预算；10%实用门槛不是统计显著性，不直接扩大计算。',
        'successful_without_stage_advantage':'保留小幅度训练与任务完成证据，停止本轮；阶段约束额外价值未成立，先审视论文主张，不盲目加训。',
        'effect_target_not_met':'保留全部负结果，停止本轮；审视F/S与B2差异，最多提出一次有明确证据的机制调整，另行登记后才能执行。',
        'controlled_guard_stop':'保持整轮停止；先分析保护触发轨迹和权限，不推断未运行分支效果，不自动补回合或继续学习。',
        'operational_failure':'先定位实际运行、保存或恢复阻碍；已消耗预算保留，故障解除和新范围登记前不重跑，不判断未完成的方法效果。',
        'insufficient_active_warmup':'先审视当前任务是否提供足量SEARCH活动经验及机制假设；本轮不补采、不混旧回放，不把没有训练机会写成策略学习失败。',
        'incomplete':'复核继承预热、通过两组零状态读取门后，按冻结顺序执行配对学习、末次评价与独立代表复现；保护或运行故障停止整轮。'}[judgement]
    diagnosed=bool(a and a.get('offline_checkpoint_diagnosis',{}).get('complete_equal'))
    if diagnosed and judgement=='operational_failure':
        next_step='已定位固定60秒读取超时；先把新读取监督器接入下一执行版本，明确继承8份已审核F/S预热数据并完成两组零状态读取门，再在新登记范围中完成训练、评价与代表复现，避免重采12个已完成回合。本轮失败账本和关闭余量保留，自动训练不恢复。'
    c_state='实现中' if not done else ('受阻' if judgement in ('controlled_guard_stop','operational_failure','insufficient_active_warmup') else '待验收')
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    rows=a['rows'] if a else [x['result'] for x in state['attempts'] if x['status']=='finished']
    groups=a['final_groups'] if a else {k:[r for r in rows if (r['stage']=='b2' if k=='B2' else r['stage']=='final' and r['arm']==k)] for k in ('B2','F','S')}
    comparison='；'.join(('纯B2' if k=='B2' else k+'冻结末次策略')+'：'+points(groups[k]) for k in ('B2','F','S'))
    restores=[r for r in rows if r['stage']=='restore']
    recovery='代表恢复未执行，不声称恢复通过' if not restores else f'代表恢复完成{len(restores)}/2，完整轨迹一致{sum(r.get("restoration_equal") is True for r in restores)}/2'
    valid='尚无完整回合可核验' if not rows else f'{sum(r["simulation_valid"] and r["physical_stopped"] for r in rows)}/{len(rows)}个已完成回合有效且停稳'
    budget=f'未执行{18-n}动态、未尝试{5000-attempted}批余量关闭，不结转。' if done else '本轮上限18动态/5000批，历史余量不使用。'
    cost='逐进程成本尚未收口，未知调用不记为0。' if not a else f'已记录物理子步{a["recorded_physical_substeps"]}；'+('成本记录完整。' if a['costs_complete'] else '成本记录未完整，已记录量不是完整总量，未知调用不记为0。')
    counts=f'新启动{n}/18动态、审核完成{len(rows)-12}个新回合，另引用12个历史回合，累计{102+n}/120；正式更新尝试{attempted}、完成{b}/5000批（F{state["updates"]["F"]["completed"]}/S{state["updates"]["S"]["completed"]}）'
    limit='限定单训练种子和四个开发点；正式独立测试0、多种子证据未完成，B.2及完整C能力未验收。代表复现不增加性能样本。'
    active='活动经验门与两个零状态读取门都通过才授予学习准入。'
    if (run/'warmup_gate.json').exists():
        gate=C.read(run/'warmup_gate.json')
        active='；'.join(f'{arm}预热活动经验{gate["arms"][arm]["active_rows"]}条、{gate["arms"][arm]["active_cases"]}个方向' for arm in ('F','S'))+'；活动数据门'+('通过' if gate['passed'] else '未通过')+f'，完整读取门{len(state.get("zero_readers",{}))}/2；不是统计充分性证明。'
    output={}
    for name in FILES:
        p=C.ROOT/name;text=p.read_text(encoding='utf-8');text=text.replace('<!-- stage-permission-current -->','<!-- stage-permission-history -->\n前轮归档状态（历史）：').replace('<!-- /stage-permission-current -->','<!-- /stage-permission-history -->');prefix='../../../' if name.startswith('deliverables/monthly') else ''
        link=lambda label,path:f'[{label}]({prefix}{path})'
        target=link('结果与图',STAGE+'/result_analysis/结果说明.md') if a else link('执行记录',STAGE+'/progress.md')
        audit=link('机器审核',STAGE+'/result_analysis/assessment.json') if a else link('运行账本',STAGE+'/run/ledger.json')
        plan=link('计划书',PLAN)
        current=f'''**阶段权限配对恢复验证{status}（{now}，北京时间）：{verdict}。** {plan}；{target}、{audit}。

比较纯B2、固定XY50残差F与仅SEARCH开放的同幅度S。{comparison}。

{counts}。{valid}；{recovery}。{budget} {cost}

继承4个B2和8个匹配预热，重新准入后从相同零更新网络起点出发，不沿用旧150映射回放或C2000权重。成功/保护/奖励不变；本轮相关离线协议与执行审查通过不等于实际效果通过。{limit} 自动跟踪PAUSED。

下一项：{next_step}'''
        if diagnosed:
            current+='\n\n读取诊断与修复：F零更新检查点完整状态离线比对通过（总65.863秒，恢复审核61.559秒），报告入口已修复；新的读取监督器5项针对性检查通过，尚未接入正式训练。原读取回执缺失与诊断末尾日志错误均保留，不补写历史成功。'+link('诊断与最小修复',STAGE+'/failure_diagnosis.md')+'。'
        text=re.sub(re.escape(START)+'.*?'+re.escape(END)+r'\s*','',text,flags=re.S)
        if name=='项目进度跟踪.md':
            text=re.sub(r'最后更新：\d{4}-\d{2}-\d{2}','最后更新：'+now[:10],text,count=1)
            text=section(text,'## 当前状态',lambda body:managed(body,'stage-resume-current',current,'### 前轮状态记录（历史口径，以下保留各自归档时点）'))
            text=row(text,'B.2 小规模学习与评价包',f'| B.2 小规模学习与评价包 | 待验收；阶段权限配对{status} | {target}、{audit} | {verdict}；正式独立评价未完成 |')
            text=row(text,'C 候选约束与消融',f'| C 候选约束与消融 | {c_state}；SEARCH-only实现与协议通过 | {plan}、{target} | {verdict}；连续进展约束尚未实现，不等于完整C验收 |')
            mapping={
                '1 开发适用性':'四点100μm零倾角开发范围保持；本轮不使用正式独立测试，不能推广至连续域或实物',
                '2 统一闭环/SAC接口':'新阶段权限会话、50幅度审核、完整学习状态与监督入口已接通并绑定；旧共享实现与封存版本保留',
                '3 动态闭环/成本':counts+'；'+cost,
                '4 B1':'已有开发基线与正常失败保留，本轮没有新B1回合',
                '5 B2与批量评价':'继承同版本纯B2：'+points(groups['B2'])+'；历史不同工况结果另行保留',
                '6 普通残差SAC':f'F匹配新50映射数据，完成{state["updates"]["F"]["completed"]}批；'+points(groups['F'])+'；B.2正式独立评价未完成',
                '7 阶段与进展约束':f'SEARCH-only已实现，S完成{state["updates"]["S"]["completed"]}批；{verdict}；尚未加入连续进展约束',
                '8 正式证据与展示':f'{target}、{audit}；{recovery}；正式独立测试0、多种子未完成'}
            for key,value in mapping.items():text=row(text,key,f'| {key} | {value} |')
            text=re.sub(r'^本次(?:冻结部署筛查|阶段权限验证)支持原任务[^\n]*$',f'本次阶段权限验证支持原任务6、7、8的开发工作；{verdict}，不新增完整B.2或论文效果验收。',text,flags=re.M)
            risks={
                '修复归因与验收范围':(verdict,'工程协议、任务成功、方法收益和正式独立评价分别判断；'+next_step),
                '单变量与有限对照可比性':('新F/S共用50幅度、零更新网络和登记预算；各自匹配预热与在线数据，仅阶段权限不同','记录有效活动经验与实际成本差异，不声称随机数据逐样本相同'),
                '训练覆盖与目标':(active,'未完成两支匹配学习与固定评价时，不推断未执行分支；不补采或混旧回放'),
                '工程范围可观测性与动作作用':('同周期观测/命令/经验与next权限一致性已实现；'+comparison,'使用控制阶段，不引入孔中心真值；开发点不等于泛化'),
                '学习时间尺度':('2ms控制/策略与100ms保持预热，dt折扣不变；'+cost,'本轮采集/更新/保存/审核按实测，历史吞吐不作本轮保证'),
                '越界与数值分类':('本轮配置和源码按独立binding冻结；共享守卫和历史封存保留','普通任务失败、保护、无效仿真和运行故障分别统计，新资格不追认旧摘要'),
                '周期峰值/停止尾段事件':('保留原周期峰值奖励与完整停止审核；'+valid,'周期峰值、周期末采样和子步事实区分；有限尝试不证明任意策略安全'),
                '条件恢复':('保留原B2回撤/恢复逻辑；残差仍受停止、回撤和阶段权限控制','策略检查点代表恢复与物理回撤是不同概念；历史应力样本不作本轮恢复成功率'),
                '原项目全量测试':('本轮相关离线协议通过；审查性质与限制见阶段review.md','不是全项目测试；真实效果与完整恢复按本轮实际结果判断'),
                '熵项与奖励尺度':(f'本轮F{state["updates"]["F"]["completed"]}/S{state["updates"]["S"]["completed"]}批；原奖励/熵和critic边界配额保持','额外critic诊断0，不能称历史价值高估已消除或唯一根因已证实'),
                '训练状态恢复':(recovery,'文件完整恢复、独立物理复现、任务成功分别判断，未执行不记通过'),
                '创新与外推':(verdict+'；模型未标定',limit)}
            for key,(fact,bound) in risks.items():text=row(text,key,f'| {key} | {fact} | {bound} |')
            text=section(text,'## 下一项交付',lambda body:f'{next_step}\n\n{counts}。{budget} {limit} 自动跟踪PAUSED。{plan}；{target}。')
            if done:
                log=f'### {now}｜阶段权限配对恢复验证收口\n\n产出与证据：{plan}；{target}、{audit}。\n\n实际：{counts}。{comparison}。{valid}；{recovery}。\n\n验收与限制：{verdict}。{limit} {budget}\n\n下一项：{next_step} 汇报素材同步至{link("10月滚动月报",FILES[3])}。'
                text=section(text,'## 追加式阶段记录',lambda body:append_once(body,'stage-resume-closeout-log',log))
        elif name=='项目交付总览.md':
            first,_,rest=text.partition('\n');history='## 前轮交付摘要（历史口径）'
            if not rest.lstrip().startswith(history):rest='\n'+history+'\n\n'+rest.lstrip()
            text=first+'\n\n'+managed('','stage-resume-current',current)+'\n'+rest
            text=re.sub(r'最后整理：\d{4}-\d{2}-\d{2}','最后整理：'+now[:10],text,count=1)
            text=text.replace('| 最新冻结C2000部署与阶段交接 |','| 前轮冻结C2000部署与阶段交接（历史） |',1).replace('| 最新保存修复后的100ms效果结果 |','| 前轮保存修复后的100ms效果结果（历史） |',1)
            entry=f'| 阶段权限F/S配对与本轮纯B2 | [B.2/C阶段交付](#c-stage-resume-20261002)、{target} | {verdict}；{recovery}；B.2正式独立评价未完成 |'
            text=row(text,'阶段权限F/S配对与本轮纯B2',entry) if '| 阶段权限F/S配对与本轮纯B2 |' in text else text.replace('|---|---|---|','|---|---|---|\n'+entry,1)
            delivery=f'<a id="c-stage-resume-20261002"></a>\n### B.2/C｜固定50与SEARCH-only配对可行性验证（{now[:10]}）\n\n成果：权限会话、匹配档案审核、独立F/S完整学习状态与监督入口已版本化；本轮{status}，{verdict}。{counts}。\n\n实际证据：{comparison}。{valid}；{recovery}。{target}、{audit}、{link("完整账本",STAGE+"/run/ledger.json")}。\n\n使用：先读{plan}及{target}，通过{audit}定位原始档案与已保存检查点。已消耗的一次性入口不可重跑，旧预算不复用。\n\n限制：{limit} {budget} 下一项以[项目进度跟踪](项目进度跟踪.md)为准。'
            text=section(text,'## 基线与接口交付',lambda body:managed(body,'stage-resume-delivery',delivery))
            if done:text=section(text,'## 维护记录',lambda body:append_once(body,'stage-resume-delivery-source',f'### {now}｜阶段权限配对交付\n\n{target}、{audit}；{counts}。{verdict}；保留稳定编号与历史版本，未新增B.2/C完整验收。'))
        elif name.startswith('deliverables/monthly'):
            text=re.sub(r'统计截至：[^。\n]+','统计截至：'+now+'（北京时间）',text,count=1)
            text=section(text,'## 一、本月综合摘要',lambda body:managed(body,'stage-resume-current',current,'### 本月前轮进展（历史口径，保留各自时点）'))
            numbers=f'最新统计：{counts}。{budget} {valid}。{cost}\n\n| 本轮项目 | 实际结果 | 解释 |\n|---|---|---|\n'+'\n'.join(f'| {k}冻结开发点评价 | {points(groups[k])} | 预热/在线回合不混入此分母 |' for k in ('B2','F','S'))+f'\n| 活动经验门 | {active} | 不是统计充分性证明 |\n| 完整代表复现 | {recovery} | 不作为新增性能样本 |\n| 正式独立测试/多种子 | 0/未完成 | 本轮不支持正式泛化结论 |'
            text=section(text,'## 二、关键数字与证据',lambda body:managed(body.replace('最新冻结筛查新增10动态/训练0，累计90；','前轮冻结筛查（历史）新增10动态/训练0，累计90；',1),'stage-resume-numbers',numbers,'### 前轮关键数字（历史口径）'))
            negative=f'本轮判定：{verdict}。{comparison}。{active}\n\n{limit} 保护、无效、运行故障与普通任务失败分别记录；未执行分支不补齐，较低载荷或较早失败不自动算收益。{cost}\n\n{next_step}'
            text=section(text,'## 三、负结果与限制',lambda body:managed(body,'stage-resume-limits',negative,'### 前轮负结果与限制（以下“本次/下一步”为归档当时口径）'))
            figures='本轮结果图尚未生成；不得引用前轮图作为新实验结果。\n\n'
            if a and (C.HERE/'result_analysis/results.png').exists():
                figures=f'![本轮阶段权限结果]({prefix}{STAGE}/result_analysis/results.png)\n\n'+link('PNG',STAGE+'/result_analysis/results.png')
                if (C.HERE/'result_analysis/results.pdf').exists():figures+=' / '+link('PDF',STAGE+'/result_analysis/results.pdf')
                figures+='：仅展示继承B2和新增冻结评价；预热、在线与代表复现单列于原始表；未执行项不补数据。\n\n'
            figures+=f'最新讲稿：“我们保持成功与保护标准，比较同幅度固定残差F和仅SEARCH开放的S，并引用同版本纯B2。{counts}。{comparison}。{verdict}。{recovery}。工程通过、方法信号与正式泛化证据分别判断，B.2仍未完成。”'
            text=section(text,'## 四、图表与讲稿',lambda body:managed(body.replace('最新讲稿：冻结最新C2000','前轮冻结筛查讲稿（历史）：冻结当时最新C2000',1).replace('![最新冻结部署筛查]','![前轮冻结部署筛查（历史）]',1),'stage-resume-figures',figures,'### 前轮图表与讲稿（历史口径）'))
            text=section(text,'## 五、下一项',lambda body:f'{next_step}\n\n{budget} {limit} 自动跟踪PAUSED。{plan}；{target}。')
            if done:text=section(text,'## 六、来源记录',lambda body:append_once(body,'stage-resume-monthly-source',f'{now}｜阶段权限配对收口：{plan}、{target}、{audit}、{link("运行账本",STAGE+"/run/ledger.json")}。{counts}。{comparison}。{verdict}。{recovery}；正式独立测试0，{budget}'))
        else:
            first,_,rest=text.partition('\n');history='## 前轮状态摘要（历史口径）'
            if not rest.lstrip().startswith(history):rest='\n'+history+'\n\n'+rest.lstrip()
            text=first+'\n\n'+managed('','stage-resume-current',current)+'\n'+rest
            text=text.replace('几何、动力学、B1/B2、旧回合记录与原校验清单不因本次入口整理而改变。本次未修改控制代码或增加实验，不新增算法或训练验收结论。','几何、动力学、B1/B2和旧回合记录及校验清单保留原版本；本轮新增阶段权限实现与验证按顶部结果记录，文档整理本身不新增算法或训练验收结论。')
            nav='| 当前阶段权限配对计划、范围与停止规则 | '+plan+' |'
            if nav not in text:text=re.sub(r'^\| 研究目标、能力划分与执行边界 \|[^\n]*$',lambda m:m[0]+'\n'+nav,text,count=1,flags=re.M)
        output[p]=text
    # Missing expected rows/sections fail before any document is written.
    for p,text in output.items():p.write_text(text,encoding='utf-8')
    if done:
        p=C.HERE/'progress.md';key='<!-- stage-resume-docs-closed -->'
        if key not in p.read_text(encoding='utf-8'):
            with p.open('a',encoding='utf-8') as f:f.write(f'\n{key}\n{now}：实际结果已同步四份滚动文档；{counts}。{verdict}。\n')
    print(f'Rolling documents updated: {status}, {n} starts, {b} completed batches, {judgement}.')

if __name__=='__main__':main()

