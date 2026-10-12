"""Keep the same four rolling documents and produce a truthful terminal report."""
import json,re,sys
from pathlib import Path
import validation_contract as C
HERE=C.HERE;ROOT=C.ROOT;S=HERE.relative_to(ROOT).as_posix();OUT=HERE/'result_analysis'
mode=sys.argv[1]
prefix='**100ms预热重启验证'
judgements=dict(limited_target_passed='本次限定修复目标通过',method_not_resolved='本方法尚未解决已观察到的学习后失效问题',
    operational_verification_blocked='新运行故障阻止效果判定',baseline_verification_blocked='共同零更新起点未满足四点要求，效果判定受阻')
if mode=='start':
    summary=f'{prefix}已启动（2026-10-01）：** 用户要求继续，修复保存接口后另建执行版本从共同零更新重启；先做真实完整状态落盘与独立进程零计算重建，再执行initial/C学习/固定/恢复/A对照。新增上限24动态/5000批；此前72动态和失败500批保留，累计上限96动态/本方法5500批。原参数/保护/成功门不改；任一保护或故障停止、不重试，旧余量关闭，自动跟踪PAUSED，B.2未完成。[方案]({S}/验证方案.md)、[账本]({S}/run/ledger.json)。'
    next_text='持续完成当前已授权的有界效果验证，直到预登记完成或保护/故障终点；不做额外训练、诊断和独立测试。'
elif mode=='final':
    a=C.read(OUT/'assessment.json');c=a['accounting'];rows=a['rows'];outcome=judgements[a['judgement']]
    last=rows[-1] if rows else None;detail=''
    if last and last['guard_hit']:
        e=next(x for x in a['episodes'] if x['id']==last['id']);reasons=e['guard_facts']['contact_reasons']+e['guard_facts']['motion_reasons']+e['guard_facts']['invalid_reasons']
        detail=f'{last["id"]}在{last["training_batches"]}批策略下触发{reasons}，周期峰值{last["force_peak_N"]:.9f} N；原轨迹有效性/真实停稳分别审核。'
    elif a['status']=='failed':detail='程序故障单独归类，不能据此给方法有效/无效结论。'
    elif a['judgement']=='method_not_resolved':detail='候选固定四点或独立完整恢复未满足预先判据；普通失败与未执行项保留。'
    elif a['limited_candidate_target_passed']:detail='C2500固定四点与独立完整恢复四点均4/4，轨迹一致；不外推多种子或独立泛化。'
    else:detail='起点未满足4/4，未把基准失败冒称学后策略失败。'
    summary=f'{prefix}已收口（2026-10-01）：** {outcome}。{detail} 新增{c["new_dynamic_starts"]}/24动态、{c["formal_batches_completed"]}/5000正式批（C{c["updates"]["C"]["completed"]}/A{c["updates"]["A"]["completed"]}），累计动态{c["cumulative_dynamic"]}/96、本方法累计{c["cumulative_temporal_batches_completed"]}批含旧故障500批。未执行余{c["unused_dynamic"]}动态/{5000-c["formal_batches_attempted"]}批关闭不结转；保存接口实际门与完整检查点按实测审计，独立测试未用，PAUSED，B.2未完成。[结果与图]({S}/result_analysis/结果说明.md)、[机器审核]({S}/result_analysis/assessment.json)。'
    if a['limited_candidate_target_passed']:next_text='限定目标通过，后续另设计多种子/独立评价及对照消融，未经新授权不扩大；B.2仍待完整验收。'
    elif a['judgement']=='method_not_resolved':next_text='100ms预热单变量未达修复目标。保持停止，下一步依据已保存的触发策略、请求与真实轨迹定位持续偏置/收敛机制，形成新的单变量修复方案；不盲目加训或放宽保护。'
    else:next_text='运行/起点故障阻断效果判定，保持停止；先依据完整故障证据离线定位，不自动重试或追加训练。'
    report=f'# 保存修复后100ms学习效果验证结果\n\n2026-10-01。**{outcome}。**\n\n{detail}\n\n本次是独立零更新重启，上轮C500未保存且无法恢复。旧4动态/500批成本保留，新的验证并非从丢失C500续跑。原24/5000预算关闭，本次用户继续后单独登记新24/5000范围。\n\n'
    stages=('initial','C_online','C_final','C_restored','A_online','A_final')
    report+='## 实际阶段与判据\n\n| 阶段 | 完成/预定 | 成功/完成 |\n|---|---:|---:|\n'
    for stage in stages:
        sub=[r for r in rows if r['stage']==stage];report+=f'| {stage} | {len(sub)}/4 | {sum(r["success"] for r in sub)}/{len(sub)} |\n'
    report+='\nC必须完成2500批、固定4/4及独立完整恢复4/4/全轨迹一致才通过有限目标。任一保护停止整轮；普通在线失败保留，C固定普通失败在该四点收口后停止，不补回合挑结果。运行故障与策略失败区分。\n\n'
    if a['judgement']=='method_not_resolved':report+='**本次预登记效果目标未达标。** 本轮证据说明100ms预热不足以解决已观察到的问题，不证明预热毫无作用、唯一根因已找到或A一定更好。\n\n'
    elif a['limited_candidate_target_passed']:report+='**本次限定目标通过。** 仅限同环境、此种子和四个开发点、2500批以内；不证明任意状态Q准确、长期稳定、多种子、独立泛化或全部B.2。\n\n'
    report+='## 全部登记回合\n\n| 回合 | 结果 | 使用策略批数 | 控制周期 | 峰值力 N | 末端XY μm |\n|---|---|---:|---:|---:|---:|\n'
    byid={r['id']:r for r in rows}
    for identity in C.attempts():
        r=byid.get(identity['id'])
        if not r:
            fault=next((x for x in a['failed_attempts'] if x['id']==identity['id']),None)
            report+=f'| {identity["id"]} | '+('已启动，运行故障；非完整策略评价' if fault else '未执行')+' | — | — | — | — |\n';continue
        p=Path(r['archive_path']).relative_to(HERE.relative_to(ROOT));label='保护失败' if r['guard_hit'] else '成功' if r['success'] else '普通任务失败'
        report+=f'| [{r["id"]}](../{p.parent.as_posix()}/status.json) | {label} | {r["training_batches"]} | {r["cycles"]} | {r["force_peak_N"]:.9f} | {r["final_xy_error_m"]*1e6:.3f} |\n'
    report+='\n![全部阶段与学习历史](validation_results.png)\n\n[PDF](validation_results.pdf)。未执行项不计入成功分母。\n\n![最后完整回合](last_episode_trace.png)\n\n[PDF](last_episode_trace.pdf)。原归档真实位置、请求和载荷，停止尾段保留，没有反事实重跑。\n\n'
    report+='## 保存修复、来源和检查点\n\n'
    report+=f'训练前真实零检查点与独立进程完整重建门：{"已通过" if a["zero_checkpoint_gate"] else "未通过/未完成"}。子进程模型/优化/物理调用0。原误用接口已替换为二进制序列化、flush/fsync、字节清单及排他目录发布；原故障包、修复包和旧消耗字节保留。\n\n'
    report+='A2ms/C100ms配对预热仍是原始未发布档案，当前新授权单独完整重审并授予本实验信用，历史false权限/committed0不改。两支从同零网络/空Adam/Torch RNG出发；同抽样算法/种子，不宣称不同长度数据的逐样本相同。当前在线使用2ms随机SAC，不使用100ms保持器；actor/critic/温度均3e−4、成功/保护/奖励/动作尺度和物理不改。独立测试不参与调参。\n\n'
    report+='| 已保存完整状态 | 正式批数 | 审核学习回合 | 经验行 |\n|---|---:|---:|---:|\n'
    for q in a['checkpoints']:
        rel=Path(q['path']).relative_to(HERE.relative_to(ROOT));report+=f'| [{rel.name}](../{rel.as_posix()}/manifest.json) | {q["batches"]} | {q["episodes"]} | {q["replay_rows"]} |\n'
    report+='\n完整网络/目标/Adam/温度、回放与原归档、资格清单原字节、边界索引、历史信用及抽样/Torch随机状态离线复核；触发策略摘要与前置检查点对应。暂存目录不构成有效检查点。\n\n'
    if a['failed_attempts']:report+='已启动故障回合另列于机器审核 `failed_attempts`，保留可用原始档案、错误、已占预算、来源字节、策略指纹及检查点对应；不完整回合不进入完整任务成功分母，绘图区分启动故障与未执行。\n\n'
    report+='## 实际成本与局限\n\n'
    report+=f'本轮新增{c["new_dynamic_starts"]}动态，确认{c["control_cycles_confirmed"]}控制周期，保守预留{c["control_cycles_reserved"]}；正式批尝试/完成{c["formal_batches_attempted"]}/{c["formal_batches_completed"]}，Adam调用{a["actual_costs"]["optimizer_steps_attempted"]}、模型模块调用{a["actual_costs"]["model_module_calls_attempted"]}、物理子步{a["actual_costs"]["physical_substeps_attempted"]}。此前累计72动态和故障500批另记，本方法两轮累计{c["cumulative_temporal_batches_completed"]}批。新余{c["unused_dynamic"]}动态/{5000-c["formal_batches_attempted"]}批及全部旧余关闭，不重置、不结转。\n\n'
    report+=f'相关协议{a["protocol_tests"]}项全过；实际档案、状态和来源审核新增模型/优化/物理均0。[机器审核](assessment.json)、[入口审查](../review.md)。协议/存取门通过不等于学习收益；未执行A或C最终结果不冒称通过。\n\n## 下一步\n\n{next_text} 自动跟踪PAUSED，B.2未完成。\n'
    with (OUT/'结果说明.md').open('x',encoding='utf-8') as f:f.write(report)
else:raise ValueError('start/final required')
docs=[ROOT/'项目进度跟踪.md',ROOT/'项目交付总览.md',ROOT/'项目当前入口.md',ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
for p in docs:
    t=p.read_text(encoding='utf-8');s=summary
    monthly=p.name=='月报素材_2026-10.md';link='../../learning_chain/'+HERE.name if monthly else S
    if monthly:s=s.replace(S,link)
    if mode=='start':
        if prefix in t:raise ValueError('Restart already recorded')
        n=t.find('\n');t=t[:n+1]+'\n'+s+'\n'+t[n+1:]
    else:t=re.sub(r'^\*\*100ms预热重启验证已启动（2026-10-01）：\*\*.*$',s,t,count=1,flags=re.M)
    if p.name=='项目进度跟踪.md':
        state='执行中；效果尚未验证' if mode=='start' else outcome
        t=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；保存修复后零起点重启 | [当前证据]({S}/验证方案.md) | {state}；B.2未完成 |',t,count=1,flags=re.M)
        t=re.sub(r'^\| 6 普通残差SAC \|.*$',f'| 6 普通残差SAC | {state}；原失败500批保留，新起点/存取门独立登记，保持原参数与四点判据 |',t,count=1,flags=re.M)
        t=re.sub(r'^\| 修复归因与验收范围 \|.*$',f'| 修复归因与验收范围 | {state}；程序存取修复与策略收益分开 | {next_text} |',t,count=1,flags=re.M)
        t=re.sub(r'^\| 训练状态恢复 \|.*$',f'| 训练状态恢复 | 本次真实零状态落盘/独立重建门；原C500无法恢复，成本保留 | {state}；恢复动态只按实测，未执行不称通过 |',t,count=1,flags=re.M)
        t=re.sub(r'^\| 原项目全量测试 \|.*$',f'| 原项目全量测试 | 保存修复7项及新版本相关协议，当前真实状态/效果另审 | {state}；并非全项目测试，不把协议通过当收益 |',t,count=1,flags=re.M)
        t=re.sub(r'## 下一项交付\n.*?(?=\n## )','## 下一项交付\n\n'+next_text+' PAUSED；旧余关闭，独立测试不使用。\n',t,count=1,flags=re.S)
        t=t.replace('## 追加式阶段记录\n\n','## 追加式阶段记录\n\n### 2026-10-01｜保存修复后重启验证'+('启动' if mode=='start' else '终点')+'\n\n'+s+'\n\n',1)
    elif p.name=='项目交付总览.md':
        if mode=='start':t+=f'\n### 保存修复后的零起点效果重启（2026-10-01）\n\n{s}\n\n使用入口仅执行一次，先存取门、后实际训练；原包不重跑，成本保留。\n'
        else:t+=f'\n2026-10-01重启终点：{outcome}；[实际结果]({S}/result_analysis/结果说明.md)。有效状态见机器检查点清单，余量关闭。\n'
    elif monthly:
        state='执行中，尚无新学后结论' if mode=='start' else outcome
        numbers='新上限24动态/5000批；此前72动态与500批保留' if mode=='start' else f'新增{c["new_dynamic_starts"]}动态/{c["formal_batches_completed"]}批；累计{c["cumulative_dynamic"]}动态/本方法{c["cumulative_temporal_batches_completed"]}批'
        if mode=='start':t=t.replace('| 内容 | 实际完成 | 上限与解释 |\n|---|---|---|','| 内容 | 实际完成 | 上限与解释 |\n|---|---|---|\n'+f'| 保存修复后零起点重启 | {numbers} | {state}；旧余不结转 |',1)
        else:t=re.sub(r'^\| 保存修复后零起点重启 \|.*$',f'| 保存修复后零起点重启 | {numbers} | {state}；新余量关闭 |',t,count=1,flags=re.M)
        note='新重启从零开始，不能把旧C500当成功恢复；真实完整存取门与策略收益分开。' if mode=='start' else detail+' '+next_text
        t=t.replace('## 三、负结果与限制\n\n','## 三、负结果与限制\n\n'+note+'\n\n',1)
        t=re.sub(r'## 五、下一项\n.*?(?=## 六、来源记录)','## 五、下一项\n\n'+next_text+'\n\n',t,count=1,flags=re.S)
        if mode=='final':t=t.replace('<a id="figures"></a>\n\n',f'<a id="figures"></a>\n\n![重启验证结果]({link}/result_analysis/validation_results.png)\n\n[PNG]({link}/result_analysis/validation_results.png)/[PDF]({link}/result_analysis/validation_results.pdf)：全部登记回合，未执行不补齐。\n\n![重启末回合轨迹]({link}/result_analysis/last_episode_trace.png)\n\n[PNG]({link}/result_analysis/last_episode_trace.png)/[PDF]({link}/result_analysis/last_episode_trace.pdf)：原始完整轨迹含停稳尾段，无重跑。\n\n本轮讲稿：“修正保存接口后，从共同零更新重启；真实完整存取与独立读取门先通过。{numbers}。{outcome}。{detail} 未把程序通过当作学习效果，B.2仍未完成。”\n\n',1)
        t+='\n2026-10-01重启'+('启动' if mode=='start' else '终点')+'来源：'+s+'\n'
    p.write_text(t,encoding='utf-8')
print(json.dumps(dict(mode=mode,documents=4),ensure_ascii=False))
