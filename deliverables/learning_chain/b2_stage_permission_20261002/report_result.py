"""Read-only evidence reduction and versioned report. Never launches a rollout."""
from copy import deepcopy
import datetime,gzip,json,math,os
import paired_contract as C
os.environ['MPLCONFIGDIR']=str(C.ROOT/'tmp/learning_mpl_cache')

def judgement(state,groups):
    if state['status']=='failed':return 'operational_failure'
    if state['status']=='stopped':return 'controlled_guard_stop'
    if state['status']=='method_failed':return 'insufficient_active_warmup'
    if state['status']!='complete':return 'incomplete'
    b,f,s=(groups[k] for k in ('B2','F','S'))
    successes=lambda rows:sum(r['success'] for r in rows)
    if any(len(rows)!=4 for rows in (b,f,s)):raise ValueError('Complete paired final rows required')
    if successes(s)==4 and successes(s)>successes(f) and successes(s)>=successes(b):return 'promising_success_signal'
    if all(successes(rows)==4 for rows in (b,f,s)):
        mean=lambda rows,key:sum(r[key] for r in rows)/4
        if all(mean(s,'force_peak_N')<=.9*mean(rows,'force_peak_N') and mean(s,'task_stop_time_s')<=1.1*mean(rows,'task_stop_time_s') for rows in (b,f)):
            return 'promising_load_signal'
        return 'successful_without_stage_advantage'
    return 'effect_target_not_met'

def main():
    from tools.learning.engineering_evaluation import episode_metrics
    from tools.learning.sac_checkpoint import _audit_physics
    from stage_rules import StageRules
    from paired_collection import audit_sampling
    from run_pair import equal_trace,confirm_exit
    pins=C.read(C.HERE/'execution_pins.json');C.verify(pins['binding_sha256'],pins['authorization_sha256'])
    run=C.HERE/'run';l=C.Ledger.load(run/'ledger.json',**dict(binding_pin=pins['binding_sha256'],auth_pin=pins['authorization_sha256']))
    exits={}
    for name in ('process','restore_process'):
        if (C.HERE/name/'started.json').exists():exits[name]=confirm_exit(C.HERE/name)
    out=C.HERE/'result_analysis';out.mkdir(exist_ok=True)
    audited=[];inputs={};archives={}
    for a in l.state['attempts']:
        if a['status']!='finished':continue
        r=a['result'];p=C.ROOT/r['archive_path']
        if C.digest(p)!=r['archive_sha256']:raise ValueError('Changed raw archive')
        raw=json.loads(gzip.decompress(p.read_bytes()));_audit_physics(raw)
        facts=raw['guard_facts'];guard=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons'])
        if raw['fault'] is not None or raw['current_identity']!=a['identity']:raise ValueError('Archive fault/identity differs')
        if not guard:StageRules(raw['stage_mode']).classify(raw)
        if r['stage']=='warmup' and not guard:audit_sampling(raw)
        metrics=episode_metrics(raw)
        for key,value in metrics.items():
            if r.get(key)!=value:raise ValueError('Metric differs: '+r['id']+':'+key)
        if r['guard_hit']!=guard or r['physical_substeps']!=10*len(raw['transitions']):raise ValueError('Cost/guard differs')
        raw_last=raw['transitions'][-1]['trace_row'];q=raw_last['quaternion_wxyz']
        row=dict(r,stop_reason=raw['final_session']['reason'],guard_reasons=facts['contact_reasons']+facts['motion_reasons']+facts['invalid_reasons'],
            final_z_error_um=abs(raw_last['position_m'][2])*1e6,final_angle_deg=math.degrees(2*math.acos(min(1.,abs(q[0])/math.sqrt(sum(x*x for x in q))))))
        audited.append(row);archives[r['id']]=raw;inputs[r['archive_path']]=C.digest(p)
    groups={key:[r for r in audited if (r['stage']=='b2' if key=='B2' else r['stage']=='final' and r['arm']==key)] for key in ('B2','F','S')}
    for r in audited:
        if r['stage']=='restore':
            original=next(x for x in groups[r['arm']] if x['case_index']==0)
            if original['worker_pid']==r['worker_pid'] or not equal_trace(archives[original['id']],archives[r['id']]):raise ValueError('Representative recovery differs')
    costfiles=[p for p in run.glob('*_costs.json')];costs={p.name:C.read(p) for p in costfiles}
    confirmed_steps=sum(v['physical_substeps_attempted'] for v in costs.values())
    expected_phases=['main_costs.json']+(['restore_costs.json'] if 'restore_process' in exits else [])
    cost_complete=all(k in costs for k in expected_phases) and all(a['status']=='finished' for a in l.state['attempts'])
    if cost_complete and confirmed_steps!=sum(r['physical_substeps'] for r in audited):raise ValueError('Complete physical cost mismatch')
    status=judgement(l.state,groups)
    assessment=dict(version='paired_stage_assessment_v1',status=l.state['status'],judgement=status,accounting=l.accounting(),rows=audited,
        final_groups=groups,process_exits=exits,costs=costs,costs_complete=cost_complete,recorded_physical_substeps=confirmed_steps,
        all_completed_valid_stopped=all(r['simulation_valid'] and r['physical_stopped'] for r in audited),
        b2_complete=False,independent_test=0,multiseed_evidence=False,result_input_sha256=inputs)
    C.write(out/'assessment.json',assessment)
    labels=dict(operational_failure='运行故障，尚不能判断方法效果',controlled_guard_stop='出现保护触发，整轮按计划受控停止',
        insufficient_active_warmup='活动经验不足，未授予学习更新',incomplete='执行未完成',promising_success_signal='出现值得扩大验证的成功数信号',
        promising_load_signal='出现值得扩大验证的载荷信号',successful_without_stage_advantage='任务成功，但阶段约束没有达到额外收益门槛',effect_target_not_met='本轮方法效果目标未达到')
    now=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')
    lines=['# 阶段权限配对可行性验证结果','',f'截至{now}（北京时间）。**{labels[status]}。**','',
        '本轮范围：纯B2、固定XY50残差F、仅SEARCH开放的同幅度残差S；训练数据各自新采，成功/保护/奖励不变。只检验开发点，不是正式独立测试或论文效果验收。','',
        '| 方法 | 冻结开发点完成 | 成功 |','|---|---:|---:|']
    for key,rows in groups.items():lines.append(f'| {key} | {len(rows)}/4 | {sum(r["success"] for r in rows)}/{len(rows)} |')
    lines+=['','| 回合 | 成功 | XY μm | 峰值力 N | 停止原因 |','|---|---|---:|---:|---|']
    for r in audited:lines.append(f'| {r["id"]} | {r["success"]} | {r["final_xy_error_m"]*1e6:.3f} | {r["force_peak_N"]:.9f} | {r["stop_reason"]} |')
    ac=l.accounting();lines+=['',f'新增动态{ac["new_dynamic_starts"]}/30，累计{ac["cumulative_dynamic"]}/120；正式完成{ac["formal_batches_completed"]}/5000批，实际尝试{ac["formal_batches_attempted"]}批。未使用余量关闭，不结转。',
        f'完整计数记录：{cost_complete}；已记录物理子步{confirmed_steps}，逐进程初始化/模型/优化调用见assessment。未知调用不记为0。','',
        '## 判断边界','',
        '运行和权限校验通过不等于学习有效；预热、在线探索、冻结评价、代表复现分别报告。只有完成两支匹配学习与冻结评价，才能比较阶段机制。停止于预热或保护时，不推断未运行分支的结果。B.2独立评价、多种子和论文收益证据仍待完成。','',
        '若出现预登记积极信号，再制定扩大证据预算；否则保留负结果，停止本轮，不盲目加训、不放宽判据。详见[计划书](../../../../docs/superpowers/plans/2026-10-02-stage-residual-feasibility.md)。']
    (out/'结果说明.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if audited:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.rcParams['font.sans-serif']=['Microsoft YaHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
        fig,axes=plt.subplots(2,1,figsize=(11,7),constrained_layout=True)
        names=[r['id'] for r in audited];colors=['#246d9b' if r['success'] else '#db8640' for r in audited]
        axes[0].bar(range(len(audited)),[r['final_xy_error_m']*1e6 for r in audited],color=colors)
        axes[0].axhline(50,color='#be3c35',linestyle='--',label='成功门槛50 μm');axes[0].set_ylabel('终末XY误差 / μm');axes[0].legend()
        axes[1].bar(range(len(audited)),[r['force_peak_N'] for r in audited],color=colors)
        axes[1].axhline(.025,color='#be3c35',linestyle='--',label='力保护阈值0.025 N');axes[1].set_ylabel('峰值力 / N');axes[1].legend()
        for ax in axes:ax.set_xticks(range(len(names)),names,rotation=70,ha='right',fontsize=7);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
        fig.suptitle('阶段权限配对验证：蓝色成功，橙色未成功（不同阶段分别按回合名标识）')
        fig.savefig(out/'results.png',dpi=150);fig.savefig(out/'results.pdf');plt.close(fig)
    print(json.dumps(dict(status=l.state['status'],judgement=status,accounting=ac,costs_complete=cost_complete),ensure_ascii=False))

if __name__=='__main__':main()
