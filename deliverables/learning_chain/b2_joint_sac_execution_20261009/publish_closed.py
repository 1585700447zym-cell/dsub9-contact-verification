"""Prepare the closed result narrative from measured evidence, then update rolling docs."""
from pathlib import Path
import os
import re
import shutil
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];KIT=OUT.parent/'b2_joint_sac_preparation_20261009'
sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha


def section(text,heading,body):
    text,n=re.subn('('+re.escape(heading)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+body.rstrip()+'\n',text,count=1,flags=re.S)
    assert n==1;return text


def main():
    if (OUT/'document_update.json').exists():raise PermissionError('Already published closed outcome')
    s=read(OUT/'execution_summary.json');reg=read(OUT/'registration.json');a=s['assessment']
    supervisor=read(OUT/'execution/supervisor.supervisor.json')
    probe=read(OUT/'phase_io_probe.json')
    assert s['status']=='CLOSED_ERROR' and s['attempts']==8 and s['updates_completed']==0
    assert len(s['episodes'])==9 and s['episodes'][-1]['execution_class']=='REGISTERED_NOT_STARTED_CLOSED'
    assert probe['original_launcher_log_sha256']==sha(OUT/'launcher.log')
    assert probe['original_supervisor_sha256']==sha(OUT/'execution/supervisor.supervisor.json')
    stage='B2-SCOPE-13'
    summary=f"{stage}四点普通F50 SAC有限试跑因监督器文件访问异常中断，已完成本次尝试的证据收口：状态{s['status']}，实际物理回合{s['attempts']}/17（F0评价4＋预热4，全部功能成功、有效停稳、无硬保护触发），完整原始档案{s['complete_raw_archives']}份，正式更新完成{s['updates_completed']}/2000批，新回放发布{s['replay_publications_completed']}次。首个在线回合仅登记、未启动，不能计入物理尝试。"
    numeric='；'.join(c['label']+'完整独立恢复'+('通过' if c['independent_restore_verified'] else '未通过/未完成') for c in s['checkpoints']) or '完整检查点未形成'
    if a:
        benefit=f"匹配F0/F2000四点平均罚时分别{a['scores']['zero']['metric']['mean_penalized_time_s']:.6f}／{a['scores']['final']['metric']['mean_penalized_time_s']:.6f}秒，改善{100*a['relative_improvement']:.4f}%；开发继续信号{'通过' if a['development_continue'] else '未通过'}。"
        next_task=('下一项：先基于本次全档案核对学习收益和失败/负载分布，再登记必要的重复训练与冻结评价；尚不启动C或扩大范围。' if a['development_continue'] else
            '下一项：仅离线分析本次F0/F2000、预热与在线档案，定位未通过开发继续门的原因，形成下一路线；不自动加训、不补抽成功样本。')
    else:
        benefit='监督器读取phase_deadline.json时发生PermissionError；同一读写函数的文件并发试验已复现访问冲突。这是运行实现缺陷，训练前后比较未形成，不能给学习改善或策略失效结论，也不能归因于原3处覆盖缺口。'
        next_task='下一项：仅离线准备新版本文件并发读写修复及硬时限回归，核对零起点＋4份预热档案能否精确重建继续所需的回放和随机状态，再形成具体的新执行方案。当前只有零更新检查点，没有预热后的完整检查点；不得直接宣称可无损续跑。本轮剩余9回合及2000批已关闭，不重试、不结转、不转借旧授权。'
    limits='当前阶段B.2第3项；完整B.2/C未验收，独立测试0，范围仍仅四个固定±75μm／±0.25°开发点。原3处逐profile覆盖缺口及SCOPE11事后修订保持，不把开发结果当独立验证。'
    cost=f"累计动态{s['cumulative_dynamic']}，本轮监督用时{supervisor['wall_seconds']:.3f}秒（{supervisor['wall_seconds']/60:.2f}分钟），全部余额关闭，当前无继续训练准入，自动跟踪PAUSED；拥有的运行进程树退出已确认。预留上界与实际档案成本分别报告，不将未用上界当已执行计算。"
    table='| 回合 | 状态 | 任务结果 | 任务用时(s) | 控制周期 |\n|---|---|---|---:|---:|\n'
    for r in s['episodes']:
        pending=r.get('execution_class')=='REGISTERED_NOT_STARTED_CLOSED'
        out=r.get('outcome',{}).get('task_outcome','未执行');time=r.get('task_time_s')
        state='登记后未启动，已关闭' if pending else '完成'
        table+=f"| {r['id']} | {state} | {out} | {format(time,'.3f') if time is not None else '—'} | {r.get('control_cycles',r.get('partial_cycles_lower_bound','—'))} |\n"
    actual=s['actual_complete_raw_costs'];reserved=s['counts_reserved_upper_bounds']
    report='# B2-SCOPE-13｜四点普通SAC有限试跑结果\n\n当前阶段：B.2第3项“小规模学习与评价”；本次异常尝试的证据收口已完成，原定17回合试跑未完成。\n\n'+summary+'\n\n'+numeric+'。 '+benefit+'\n\n'+table+'\n原始ledger保留第9行status=running，表示中断时已登记；counter中dynamic_episodes与environment_creations均为8，第9行没有环境或原始轨迹。收口派生表将其归为REGISTERED_NOT_STARTED_CLOSED，保留原记录，不算第9个物理失败样本。在线4／最终评价4／恢复复现1均未执行。\n\n## 实际成本与关闭\n\n'+cost+'\n\n'
    report+=f"完整原始档案合计：控制周期{actual['control_cycles']}、原生物理子步{actual['physical_substeps']}、观测向量{actual['observations']}、策略调用{actual['policy_calls']}。正式更新尝试{s['update_attempts']}批、完成{s['updates_completed']}批，update journal未产生；发布新回放{s['replay_rows']}行。第9行物理成本为0。\n\n"
    report+=f"辅助操作登记尝试：学习器构造{reserved['learner_constructions']}/7、CPU张量读取{reserved['tensor_loads']}/2、检查点保存{reserved['checkpoint_saves']}/2。保存完成与恢复通过由manifest和reader回复分别验证；这些次数不直接等同于成功次数。更新内部网络运算计入更新批，不混入物理策略调用。\n\n"
    report+='## 证据与局限\n\n运行入口及来源沿用封存SCOPE12；零起点恢复先于物理回合，预热档案通过运行内门；正式更新原定于在线回合后进行，本次尚未开始。回放来源与新物理档案按完整解码内容核对；两个写入器的JSON空白不同，各自原始字节分别绑定，不要求压缩文件哈希相同。真实张量不在收口阶段再次加载。\n\n'+limits+'\n\n'+next_task+'\n\n[失败原因与修复路线](失败原因与修复路线.md)、[机器证据](failure_diagnosis.json)。具体原始证据：execution/run/ledger.json、execution/counter.json、execution/authorization_closure.json、execution/supervisor.log、execution_summary.json；source及封存复核见verification.json。所有成功、失败、不完整与阶段日志均保留。\n'
    (OUT/'结果说明.md').write_text(report,encoding='utf-8')
    evidence_names=['launcher.log','execution/supervisor.supervisor.json','execution/phase_deadline.json',
        'execution/counter.json','execution/run/ledger.json','execution/authorization_closure.json',
        'execution_summary.json','phase_io_probe.json','diagnose_phase_io.py']
    diagnosis=dict(stage_id=stage,failure_class='SUPERVISOR_PHASE_FILE_PERMISSION_ERROR',
        observed_failure=dict(reader='supervised.py:64 -> joint_contract.py:28',errno=13,phase='online_F50_J01',
            registered_rows=9,physical_episodes=8,environment_creations=8,formal_updates=0,deadline_hit=False),
        supported_mechanism='Concurrent atomic replacement and plain read on Windows; reproduced with the exact sealed I/O functions. The original lock owner was not traced.',
        file_only_probe={k:probe[k] for k in ('wall_s','read_success','write_success','read_permission_errors','write_permission_errors','new_physics','new_learning')},
        source_pins={name:sha(OUT/name) for name in evidence_names},
        candidate_source_pins={name:sha(KIT/name) for name in ('joint_contract.py','supervised.py','pilot_worker.py')},
        checkpoint_boundary='zero_only_no_post_warmup_checkpoint',restart_authorized=False,
        implementation_fixed=False,original_runner_unchanged=True,
        decision='Prepare a separate offline I/O repair and state-reconstruction candidate; no restart or quota carryover.')
    write(OUT/'failure_diagnosis.json',diagnosis)
    route='''# B2-SCOPE-13｜失败原因与修复路线

当前阶段：B.2第3项“小规模学习与评价”；本次异常诊断与路线决定已完成。修复实现及再次运行待开始。

## 已确认的中断原因

launcher.log明确指向监督器supervised.py第64行：读取phase_deadline.json时，joint_contract.read的普通文件打开抛出PermissionError（errno 13）。监督器随即停止它拥有的进程树，运行以CLOSED_ERROR关闭；不是达到6小时或单阶段时限。

worker在physical()中依次登记ledger、用临时文件加os.replace替换阶段截止文件、再调用open_episode预留物理资源。最终截止文件为online_F50_J01，ledger有9行，而环境创建和动态计数均为8。故前8回合已完成，首个在线回合还没有创建环境；2000批正式更新一批也未开始。

## 机制证据与判断边界

新建scratch文件，调用原封存joint_contract.read/write，用两个标准库线程并发读取与原子替换，限定最多1000次写及15秒。实际{wall:.3f}秒，读取成功{reads}次、写成功{writes}次，读取访问拒绝{rerrors}次、写入访问拒绝{werrors}次。试验只涉及新JSON文件，新增物理和学习均0；全部错误与残留暂存文件保留。

该试验支持Windows上同一路径并发替换/读取竞争是本次异常的原因。原运行未记录操作系统层的锁持有者，不能进一步断定具体占用线程或外部进程。本次缺陷在监督和文件交换实现层；现有证据不支持归因于SAC更新、接触保护或原3处覆盖缺口。8次有限成功也不足以证明覆盖缺口对未来训练完全无影响。

原封存write未对替换访问冲突重试，监督循环每20ms普通读取一次且未处理此类短暂错误。仅给写入端加重试不足以解决读取端的本次故障。旧工具已有有限Windows替换重试，可作为新版本设计参考；旧封存程序与失败记录不改写。

## 路线决定与下一项验收

1. 先准备独立的新版本文件交换修复。只对可识别的瞬态Windows共享/访问冲突做有界处理；读写两端都覆盖。持续错误、损坏JSON和字段不合法仍停止，不能静默忽略。
2. 文件重试期间继续检查原整体硬时限和最近有效阶段的绝对截止时间，不能重新起计时、延长期限或恢复已关闭执行。通过文件级并发、暂时锁、永久拒绝、损坏输入、临近超时及进程退出回归后，才认为修复候选可审阅。
3. 原尝试只有zero完整检查点；4份预热档案已发布19300行回放，但没有保存预热后的完整回放/随机状态检查点。下一项先离线核对是否能从零状态和档案精确重建继续边界，列明能够及不能够恢复的状态。未经证实，不把零检查点当作预热后的恢复点，也不声称恢复了原中断进程。
4. 上述候选和状态来源确认后，再提出具体新的运行安排及成本；本次余9物理回合和2000批更新全部关闭。不能把新尝试冒充本轮无缝续跑，不能自动重复前8回合或沿用旧授权。

此阶段交付是失败证据、真实成本和路线决定；不标修复已实现、不标训练收益通过。完整B.2/C未验收，独立测试0，自动跟踪PAUSED。

证据：[运行汇总](execution_summary.json)、[日志](launcher.log)、[监督器结果](execution/supervisor.supervisor.json)、[文件试验](phase_io_probe.json)、[哈希绑定及结论](failure_diagnosis.json)。
'''.format(wall=probe['wall_s'],reads=probe['read_success'],writes=probe['write_success'],rerrors=probe['read_permission_errors'],werrors=probe['write_permission_errors'])
    (OUT/'失败原因与修复路线.md').write_text(route,encoding='utf-8')
    expected=read(OUT/'active_document_update.json')['after_documents'] if (OUT/'active_document_update.json').exists() else reg['before_documents']
    pending={}
    for name in reg['before_documents']:
        if name=='AGENTS.md':continue
        path=ROOT/name;assert sha(path)==expected[name],'Concurrent document edit: '+name
        rel=os.path.relpath(OUT,path.parent).replace('\\','/')
        links=f'[试跑结果]({rel}/结果说明.md)、[失败原因与修复路线]({rel}/失败原因与修复路线.md)、[逐回合与成本]({rel}/execution_summary.json)、[授权关闭]({rel}/execution/authorization_closure.json)。'
        body=summary+'\n\n'+numeric+'。 '+benefit+'\n\n'+cost+'\n\n'+limits+'\n\n'+next_task+'\n\n'+links
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2第3项；任务：B2-SCOPE-13四点普通SAC有限试跑与收口，已完成本次尝试收口。** '+body+' 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        text,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,path.read_text(encoding='utf-8'),count=1,flags=re.S);assert n==1
        if name=='项目进度跟踪.md':
            text=text.replace('## 当前状态\n','## 当前状态\n\n2026-10-09当前：'+summary+' '+benefit+' '+cost+'\n\n以下保留此前时点：\n',1)
            text,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；SCOPE-13本次试跑收口 | [结果]({rel}/结果说明.md) | 实际{s["attempts"]}/17动态、{s["updates_completed"]}/2000批；{benefit} |',text,flags=re.M);assert n==1
            tasks=[('1 开发适用性','仅四点联合开发范围；未扩展原完整范围'),('2 统一闭环/SAC接口',numeric),('3 动态闭环/成本',cost),('4 B1','原成果保留，不跨范围升级'),('5 B2与批量评价',benefit),('6 普通残差SAC',summary),('7 阶段与进展约束','仍在B.2第3项，C物理工作暂缓'),('8 正式证据与展示','独立测试0；负结果、账本和原覆盖缺口保留')]
            text=section(text,'## 原八项任务对应','| 原任务 | 当前对应 |\n|---|---|\n'+'\n'.join(f'| {k} | {v} |' for k,v in tasks))
            start=text.index('## 当前风险和准入门');end=text.index('下表保留历史限制',start)
            text=text[:start]+'## 当前风险和准入门\n\n'+limits+'\n\n'+benefit+'\n\n'+next_task+'\n\n'+text[end:]
            text=section(text,'## 下一项交付',next_task+'\n\n'+cost+'\n\n'+links)
            text+='\n### 2026-10-09｜B2-SCOPE-13试跑及收口\n\n'+body+' 本交付阶段结束后暂停汇报。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            text=text.replace('当前四点普通SAC接入与具体新运行申请：','前轮四点普通SAC接入与当时运行申请：',1)
            text=text.replace('## 快速查找\n\n','## 快速查找\n\n当前四点普通SAC试跑结果：[B2-SCOPE-13]('+rel+'/结果说明.md)。\n\n',1)
            text=text.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n### B2-SCOPE-13｜四点普通SAC有限试跑（2026-10-09）\n\n'+body+'\n\n使用：先核对状态与实际完成项，再读原始档案；关闭授权不可再次使用。\n\n',1)
        elif name=='研究推进计划_当前版.md':
            start=text.index('### B.2 小规模学习与评价包');end=text.index('\n1. 先在',start)
            text=text[:start]+'### B.2 小规模学习与评价包\n\n2026-10-09当前：'+summary+' '+benefit+' '+next_task+' '+cost+' 以下原阶段要求保留。\n'+text[end:]
        elif name.startswith('deliverables/'):
            additions={'## 一、本月综合摘要':body,'## 二、关键数字与证据':table+'\n'+cost+'\n\n'+links,
                '## 三、负结果与限制':benefit+' '+limits,
                '## 四、图表与讲稿':'图表使用本次逐回合表和实际成本表。讲稿：“当前仍在B.2第3项。'+summary+benefit+'本次结果仅用于开发，完整阶段和独立评价尚未验收。”'}
            for h,b in additions.items():assert text.count(h)==1;text=text.replace(h+'\n',h+'\n\n'+b+'\n\n以下保留前轮时点：\n',1)
            text=section(text,'## 五、下一项',next_task+'\n\n'+cost+'\n\n'+limits)
            text+='\n### 2026-10-09｜B2-SCOPE-13来源记录\n\n'+body+'\n'
        pending[name]=text
    for name,text in pending.items():(ROOT/name).write_text(text,encoding='utf-8')
    after={}
    for name in reg['before_documents']:
        dst=OUT/'document_snapshots'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);after[name]=sha(dst)
    write(OUT/'document_update.json',dict(after_documents=after,rolling_documents_may_advance=True))
    print('Closed result and five integrated documents written; six snapshots preserved.')


if __name__=='__main__':main()
