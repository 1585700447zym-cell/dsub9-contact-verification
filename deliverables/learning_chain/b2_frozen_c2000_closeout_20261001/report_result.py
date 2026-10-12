"""Original-result plots, reconciled rolling docs, snapshots and final seal."""
import datetime,gzip,json,os,re,shutil
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np
import night_contract as N

def load_assessments(here):
    variants=N.started_variants(here)
    missing=[v for v in variants if not (Path(here)/v/'assessment.json').exists()]
    if missing:raise ValueError('Started candidate lacks terminal audit: '+','.join(missing))
    results=[N.read(Path(here)/v/'assessment.json') for v in variants]
    for a in results:
        exits=N.confirm_stopped(Path(here)/a['variant'])
        if a.get('worker_stop_confirmed') is not True or a.get('supervised_exit_sha256')!=exits:raise ValueError('Unconfirmed candidate exit')
    return results

def main():
    results=load_assessments(N.HERE)
    if not results:raise ValueError('No terminal audit')
    for a in results:
        N.P.verify_files(a['result_inputs_sha256'])
        if any(a['offline_calls'].values()):raise ValueError('Audit computation')
    N.verify_parent();pins=N.read(N.HERE/'execution_pins.json');N.verify(pins['binding_sha256'],pins['authorization_sha256'],'base')
    out=N.HERE/'result_analysis';out.mkdir(exist_ok=False)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams['font.family']=['Microsoft YaHei','DejaVu Sans'];plt.rcParams['axes.unicode_minus']=False
    fig,ax=plt.subplots(1,2,figsize=(11,4.7),layout='constrained')
    for j,a in enumerate(results):
        rows=[r for r in a['rows'] if r['index']<4];by={r['index']:r for r in rows}
        for i in range(4):
            r=by.get(i);x=i+(j-.5)*.28
            if r:
                color='#348d63' if r['success'] else '#d4524b' if r['guard_hit'] else '#d39f3d'
                ax[0].bar(x,r['final_xy_error_m']*1e6,width=.25,color=color,label=a['variant'] if i==0 else None)
                ax[0].text(x,r['final_xy_error_m']*1e6+2,('成功' if r['success'] else '保护' if r['guard_hit'] else '失败'),ha='center',fontsize=8)
                ax[1].bar(x,r['force_peak_N']*1000,width=.25,color=color)
            else:ax[0].text(x,6,'未执行',rotation=90,ha='center',fontsize=8)
    for x in ax:x.set_xticks(range(4),['+X','−X','+Y','−Y']);x.grid(axis='y',alpha=.2)
    ax[0].axhline(50,color='k',linestyle='--');ax[0].set_ylabel('终末XY误差 μm');ax[0].set_title('冻结C2000：原幅度/缩幅部署')
    ax[1].axhline(25,color='k',linestyle='--');ax[1].set_ylabel('周期峰值力 mN');ax[1].set_title('25 mN保护保持；灰缺项未执行')
    fig.suptitle('每点最多一次；独立重放不计新增性能样本')
    for ext in ('png','pdf'):fig.savefig(out/('development_results.'+ext),dpi=160)
    plt.close(fig)
    last_a=results[-1];last=next((r for r in reversed(last_a['rows']) if r['index']<4),None)
    if last:
        raw=json.loads(gzip.decompress((N.ROOT/last['archive_path']).read_bytes()));ts=np.asarray([r['trace_row']['time_s'] for r in raw['transitions']]);xy=np.asarray([r['trace_row']['position_m'][:2] for r in raw['transitions']])*1e6
        req=np.asarray([r['action_log']['raw_action'] for r in raw['transitions']]);active=np.asarray([r['action_active'] for r in raw['transitions']])
        forces=[.025*np.sqrt(max(0.,-r['reward_terms']['force']/(.2*r['dt'])))*1000 for r in raw['transitions']]
        fig,axes=plt.subplots(3,1,figsize=(11,8),sharex=True,layout='constrained')
        axes[0].plot(ts,xy[:,0],label='X');axes[0].plot(ts,xy[:,1],label='Y');axes[0].plot(ts,np.linalg.norm(xy,axis=1),label='XY');axes[0].axhline(50,color='k',linestyle='--');axes[0].set_ylabel('位置 μm');axes[0].legend()
        axes[1].plot(ts,np.where(active,req[:,0],np.nan),label='X请求');axes[1].plot(ts,np.where(active,req[:,1],np.nan),label='Y请求');axes[1].set_ylabel('归一化请求');axes[1].legend()
        axes[2].plot(ts,forces);axes[2].axhline(25,color='k',linestyle='--');axes[2].set_ylabel('周期峰值力 mN');axes[2].set_xlabel('原轨迹时间 s')
        fig.suptitle(f"{last_a['variant']} 最后开发回合：{N.identities()[last['index']]['name']}；原始轨迹含停稳尾段")
        for ext in ('png','pdf'):fig.savefig(out/('last_trace.'+ext),dpi=160)
        plt.close(fig)
    operational=any(a['operational_fault'] for a in results);usable=any(a['status']=='complete' and a['restore_ok'] for a in results)
    small=next((a for a in results if a['variant']=='small'),None);base=results[0]
    judged='执行问题阻止本阶段验收' if operational else '冻结部署筛查完成；存在可复现评价，允许下一阶段实现准备' if usable else '冻结部署筛查受保护停止；下一阶段设计可推进，实际对照尚缺完整冻结评价'
    if small and small['development_completed']==4 and small['development_success']==4 and small['restore_ok']:judged='XY缩幅部署四点成功且独立复现；普通SAC训练修复和公平训练对照仍待验证'
    actual=sum(a['accounting']['new_dynamic_starts'] for a in results);totals={k:sum(a['actual_costs'][k] for a in results) for k in ('actor_states','module_calls','physical_substeps')}
    cost_complete=all(a['actual_costs_complete'] for a in results)
    stamp=datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')
    lines=[f'# 冻结C2000最小评价与阶段交接\n\n截至{stamp}（北京时间）。**{judged}。**\n',
        '使用预先固定的最新C2000，不筛选最佳检查点。新训练、额外critic评分、独立测试均0。小幅度若执行，是同一冻结网络的部署筛查，未使用旧数据训练新动作映射，也不能冒称已得到合理调优的小固定边界SAC。\n',
        '| 部署 | 开发完成/预定 | 成功/已测 | 独立代表点复现 | 停止状态 |\n|---|---:|---:|---|---|']
    for a in results:lines.append(f"| {'XY150 μm/s' if a['variant']=='base' else 'XY50 μm/s'} | {a['development_completed']}/4 | {a['development_success']}/{a['development_completed']} | {'完整轨迹一致' if a['restore_ok'] else '未执行/未通过，见审核'} | {a['status']} |")
    lines.extend(['\n| 回合 | 部署 | 结果 | XY μm | 峰值力 N | 原因 |\n|---|---|---|---:|---:|---|'])
    for a in results:
        for r in a['rows']:
            if r['index']==4:continue
            lines.append(f"| {N.identities()[r['index']]['name']} | {a['variant']} | {'成功' if r['success'] else '保护失败' if r['guard_hit'] else '普通失败'} | {r['final_xy_error_m']*1e6:.3f} | {r['force_peak_N']:.9f} | {r['stop_reason']} |")
    lines.extend(['\n![逐点结果](development_results.png)\n','![最后原始轨迹](last_trace.png)\n',
        f"新增{actual}/10动态，累计{80+actual}/90；剩余{10-actual}关闭不结转。已记录actor状态{totals['actor_states']}、模块调用{totals['module_calls']}、物理子步{totals['physical_substeps']}；计算记录完整={cost_complete}。若不完整，以上仅为已记录下限，已预约物理子步上限{actual*130000}，未知成本不记为0。原始失败和所有已启动故障保留，复现不是新增独立样本。\n",
        '保护停止对应候选全部余量，原执行账本与旧修复4/4目标保持。物理、成功/保护/奖励、2ms策略、转动0.0005rad/s不变。任何无效/停稳/监督/读写/复现故障阻止下一阶段实际实验。\n',
        '## 下一阶段最低计划\n\n1. 可立即设计阶段与进展约束；首先仅阶段约束，再加入接近完成时的连续收窄。只用已有推进量/控制阶段，不用孔中心真值。\n2. 实际对照先具备同版本、可复现的冻结普通SAC评价，以及真正使用较小固定边界训练的合理基线；本轮部署筛查不能代替后者。\n3. 固定边界/较小固定边界/阶段约束共用学习、预算、守卫、观测和动作权限；一次小范围筛查后决定是否追加进展约束。不以普通SAC必须优于B2为先决条件，不降低成功或保护标准。\n4. B.2正式独立评价、多种子和论文效果结论仍未完成；独立测试保留，不用于选择本轮部署幅度。\n',
        '## 过程决定\n\n用户授权自主制定并实施本阶段计划，无重复确认；保留全部未提交与封存文件，无提交/删除/自动跟踪；缩幅先作部署筛查，避免改变动作映射后继续沿用旧回放训练。成本是本轮不能证明新的训练方法最优。\n'])
    (out/'结果说明.md').write_text('\n'.join(lines),encoding='utf-8')
    rel=N.HERE.relative_to(N.ROOT).as_posix();summary=f'**冻结C2000夜间筛查收口（{stamp}）：** {judged}。新增{actual}/10动态，累计{80+actual}/90，训练0；余量关闭，自动跟踪PAUSED，B.2未完成。[结果与图]({rel}/result_analysis/结果说明.md)。'
    status=f'本次仅固定C2000确定性部署；原幅度{base["development_success"]}/{base["development_completed"]}已测点成功。'+(f'缩幅{small["development_success"]}/{small["development_completed"]}已测点成功。' if small else '缩幅未执行。')+'代表复现以实际完整轨迹核验为准；当前独立评价、真正小边界训练对照未完成。'
    docs=['项目进度跟踪.md','项目交付总览.md','项目当前入口.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    for name in docs:
        p=N.ROOT/name;t=p.read_text(encoding='utf-8');local=summary if 'monthly_progress' not in name else summary.replace(rel,'../../'+rel.removeprefix('deliverables/'))
        if name=='项目进度跟踪.md':
            t=t.replace('## 当前状态\n\n','## 当前状态\n\n'+local+'\n\n'+status+'\n\n',1)
            t=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；本次冻结部署筛查已收口 | [最新结果]({rel}/result_analysis/结果说明.md) | {status} B.2未完成 |',t,count=1,flags=re.M)
            t=t.replace('本次真实数值验证、A500复现、B500冻结与停止证据收口完成；','历史actor率轮真实数值验证、A500复现、B500冻结与停止证据收口完成；')
            t=t.replace('本次达到20k目标时','历史20k目标轮达到目标时').replace('新增B逐点结果与正X实际轨迹两图','历史B评价新增逐点结果与正X实际轨迹两图')
            t=t.replace('技术导读支持原任务2与8；本次实际执行支持原任务6与8，新增1000正式批/1动态，收益及B.2仍未验收。',f'本次冻结部署筛查支持原任务6与8，新增{actual}动态/训练0；完整结果及图见当前入口，B.2仍未验收。')
            t=t.replace('| 本轮受控停止与运行稳定性 | 13动态/2500批','| 历史原子写入轮运行稳定性 | 13动态/2500批')
            t=re.sub(r'^\| 熵项与奖励尺度 \|.*$',f'| 熵项与奖励尺度 | 最新学习为C2000；本次冻结评价训练0，保持原奖励/熵；历史价值核对保留 | 保存故障已修复；尚无最新critic高估消除或唯一根因证据 |',t,count=1,flags=re.M)
            t=t.replace('## 下一项交付\n\n','## 下一项交付\n\n'+status+' 下一步按最新交接计划决定小固定边界训练对照和阶段约束；不解锁旧预算。\n\n',1)
            t=t.replace('## 追加式阶段记录\n\n','## 追加式阶段记录\n\n### '+stamp+'｜冻结C2000夜间收口\n\n'+local+'\n\n'+status+'\n\n',1)
        elif 'monthly_progress' in name:
            t=t.replace('## 一、本月综合摘要\n\n','## 一、本月综合摘要\n\n'+local+'\n\n'+status+'\n\n',1)
            t=t.replace('## 二、关键数字与证据\n\n',f'## 二、关键数字与证据\n\n最新冻结筛查新增{actual}动态/训练0，累计{80+actual}；基准与缩幅逐点分开，代表重放不增加性能样本。\n\n',1)
            t=t.replace('## 三、负结果与限制\n\n','## 三、负结果与限制\n\n'+status+' 缩幅部署不能当作新训练方法或公平消融收益。\n\n',1)
            t=t.replace('## 四、图表与讲稿\n\n','## 四、图表与讲稿\n\n![最新冻结部署筛查](../../learning_chain/b2_frozen_c2000_closeout_20261001/result_analysis/development_results.png)\n\n最新讲稿：冻结最新C2000，先确定性评价，再按预登记条件进行单个XY缩幅部署筛查。'+status+'\n\n',1)
            t=t.replace('## 五、下一项\n\n','## 五、下一项\n\n按最新冻结筛查结果准备公平的小固定边界与阶段约束对照。B.2独立评价保持待完成。\n\n',1)
            t+='\n'+stamp+'｜夜间冻结筛查：'+local+' '+status+'\n'
        else:
            first=t.find('\n');t=t[:first+1]+'\n'+local+'\n\n'+status+'\n'+t[first+1:]
            if name=='项目当前入口.md':t=t.replace('**100ms预热学习验证已收口（2026-10-01）：**','**上一保存故障轮（历史，2026-10-01）：**',1)
            if name=='项目交付总览.md':t=t.replace('| 我要找什么 | 优先打开 | 使用提醒 |\n|---|---|---|','| 我要找什么 | 优先打开 | 使用提醒 |\n|---|---|---|\n'+f'| 最新冻结C2000部署与阶段交接 | [结果]({rel}/result_analysis/结果说明.md) | {status} |',1)
        p.write_text(t,encoding='utf-8')
    snap=out/'document_snapshot';snap.mkdir()
    for name in docs:shutil.copyfile(N.ROOT/name,snap/Path(name).name)
    final=dict(status='blocked_by_execution' if operational else 'phase_terminal',judgement=judged,previous_dynamic=80,new_dynamic=actual,cumulative_dynamic=80+actual,
        unused_dynamic_closed=10-actual,new_training=0,actual_costs=totals,actual_costs_complete=cost_complete,reserved_physical_substep_upper_bound=actual*130000,results=results,next_stage_design_ready=not operational,
        next_stage_actual_comparison_requires_fair_trained_baseline=True,representative_replay_available=usable,b2_complete=False,independent_test=0,automatic_tracking='PAUSED')
    N.write(out/'assessment.json',final)
    with (N.HERE/'progress.md').open('a',encoding='utf-8') as f:f.write('\nTask 3 complete: original archives audited, plots exported, rolling docs reconciled/snapshotted; bounded phase terminal, no B.2 completion.\n')
    files={p.relative_to(N.ROOT).as_posix():N.digest(p) for p in N.HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='delivery_verification.json'}
    N.write(out/'delivery_verification.json',dict(parent_sha256=N.PARENT_SEAL,binding_sha256=pins['binding_sha256'],authorization_sha256=pins['authorization_sha256'],sha256=files,summary=final,rolling_originals_not_frozen=True))
    N.P.verify_files(files);print(json.dumps(dict(judgement=judged,new_dynamic=actual,cumulative_dynamic=80+actual,delivery_sha256=N.digest(out/'delivery_verification.json')),ensure_ascii=False))

if __name__=='__main__':main()
