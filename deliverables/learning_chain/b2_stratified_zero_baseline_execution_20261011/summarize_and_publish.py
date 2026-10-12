"""Publish the closed baseline package using saved, standard-library evidence only."""
import json
import math
from pathlib import Path
import re
import shutil
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
ENTRY=ROOT/'deliverables/learning_chain/b2_stratified_zero_baseline_entry_20261011'
sys.path.insert(0,str(ENTRY))
import scope_contract as c
from assess_results import require_closed

GROUPS=[('aligned','对中'),('position_only','仅位置'),('orientation_only','仅姿态'),('joint','联合')]
MONTH='deliverables/monthly_progress/2026-10/月报素材_2026-10.md'
DOCS=['项目当前入口.md','项目进度跟踪.md','研究推进计划_当前版.md','项目交付总览.md',MONTH]

def number(value,digits=4):
    return '待完整证据' if value is None else f'{value:.{digits}f}'

def replace_section(text,heading,body):
    start=text.index(heading+'\n')+len(heading)+1
    end=text.find('\n## ',start)
    if end<0:end=len(text)
    return text[:start]+'\n'+body+'\n'+text[end:]

def main():
    execution=ENTRY/'execution'
    ledger=c.read(execution/'ledger.json');closure=c.read(execution/'authorization_closure.json')
    require_closed(ledger,closure)
    result=c.read(execution/'assessment.json')
    if (OUT/'run').exists():
        original={str(p.relative_to(execution)):c.sha(p) for p in execution.rglob('*') if p.is_file()}
        archived={str(p.relative_to(OUT/'run')):c.sha(p) for p in (OUT/'run').rglob('*') if p.is_file()}
        if original!=archived:raise ValueError('Preserve original runtime copy; publication refresh requires identical evidence')
    else:shutil.copytree(execution,OUT/'run')
    for name in ['assessment.json','comparison.csv']:
        target=OUT/name
        if target.exists():
            if c.sha(target)!=c.sha(execution/name):raise ValueError('First actual assessment/csv differs')
        else:shutil.copyfile(execution/name,target)
    shutil.copyfile(execution/'authorization_closure.json',OUT/'authorization_closure.json')
    rows=result['records'];summary=result['summary'];cost=result['costs'];complete=summary['complete_valid_stopped_matrix']
    package=ledger.get('package_supervisor',{})
    whole=package.get('wall_seconds',package.get('wall_s'))
    # Different frozen supervisors use different wall-field labels; retain proof rather than inventing a duration.
    c.write(OUT/'registration.json',dict(stage='B.2第3项',purpose='21_new_pure_B2_development_cases',
        source_binding_sha256=c.sha(ENTRY/'source_binding.json'),grant_sha256=c.sha(OUT/'authorization_grant.json'),
        new_case_ids=[p['id'] for p in c.new_cases()],old_cases_reused=['J11','J22','J33','J44'],
        limits=c.LIMITS,run_id=ledger['run_id'],data_use='development',no_retries=True))
    c.write(OUT/'case_qualification.json',dict(status='ZERO_BASELINE_DISCRETE_COMPLETE' if complete else 'ZERO_BASELINE_PARTIAL',
        recorded_initialization_passes=sum(r.get('initial_audit',{}).get('passed') is True for r in ledger['episodes']),
        audited_available=len(rows),expected=25,complete_valid_stopped_matrix=complete,
        functional_successes=summary['functional_successes'],ordinary_failures=summary['ordinary_failures'],
        nonzero_SAC_qualified=False,training_admitted=False,continuous_scope_qualified=False,
        full_B2_accepted=False,C_accepted=False))
    status='已完成并关闭' if ledger['status']=='CLOSED_COMPLETE' else '已停止并关闭，矩阵未完整'
    synopsis=(f"本次新尝试{result['new_attempts']}/21，复用旧4点；25点已审核{summary['available']}/25，"
        f"功能成功{summary['functional_successes']}，普通任务失败{summary['ordinary_failures']}；"
        f"保护{summary['guards']}、无效{summary['invalid']}、未停稳{summary['unstopped']}，另有档案/监督不完整尝试{len(result['incomplete_attempts'])}；"
        f"完整有效停稳矩阵={'是' if complete else '否'}。")
    costs=(f"本次环境构造尝试{cost['environment_creation_attempts']}、复位尝试{cost['reset_attempts']}，"
        f"已记录控制周期{cost['control_cycles_recorded']}、物理子步{cost['native_steps_recorded']}；"
        f"成本完整性={cost['control_counts_complete']}，累计动态{result['cumulative_dynamic'] if result['cumulative_dynamic'] is not None else result['cumulative_dynamic_range']}。"
        "新策略调用/学习器/张量/更新/经验发布/独立测试均0；余额关闭，无重试或结转，自动跟踪PAUSED，完整B.2/C未验收。")
    next_task=("下一项（待开始）：依据本次真实初始化与零残差证据，离线准备冻结F0/F2000在21新增开发点的同口径评价入口与有限42单元方案；"
        "先核对非零动作适用性和执行准入，不直接运行新策略评价或训练。") if complete else (
        "下一项（待开始）：只读核对本次停止/故障原因与已保留证据，先决定需要的修复或适用性补充；不自动重试剩余点，不启动SAC评价或训练。")
    reminder='强化学习保持课题主方法，纯B2是共同传统对照。B.2完成、准备进入C之前，主动提醒阶段性成果总结与汇总。'
    table=['| 场景 | 已审核/登记 | 功能成功 | 普通失败 | 附加精度80μm/0.5° | 含失败均值（秒） | 成功P50/P90（秒） | 平均SEARCH（秒） |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for key,title in GROUPS:
        s=result['strata'][key];subset=[r for r in rows if r['group']==key]
        search=math.fsum(r['phase_times_s'].get('SEARCH',0.) for r in subset)/len(subset) if subset else None
        table.append(f"| {title} | {s['available']}/{s['expected']} | {s['functional_successes']} | {s['ordinary_failures']} | {s['additional_precision']} | {number(s['mean_penalized_time_s'])} | {number(s['success_p50_s'])}/{number(s['success_p90_s'])} | {number(search)} |")
    table='\n'.join(table)
    details=['| 点 | 资料 | 功能结果 | 任务耗时（秒） | SEARCH（秒） | 净力峰值（mN） | 终末XY（μm） | 终末倾角（°） | 最小余量（μm） |',
        '|---|---|---|---:|---:|---:|---:|---:|---:|']
    by_id={r['case_id']:r for r in rows}
    matrix=['| 位置 / 姿态 | 无倾角 | A1 (+,+) | A2 (−,+) | A3 (−,−) | A4 (+,−) |',
        '|---|---:|---:|---:|---:|---:|']
    for i in range(5):
        cells=[]
        for j in range(5):
            case_id='D00' if i==j==0 else 'A'+str(j) if i==0 else 'P'+str(i) if j==0 else 'J'+str(i)+str(j)
            row=by_id.get(case_id)
            if row is None:cells.append(case_id+' 缺证据');continue
            suffix='*' if row['reused'] else ''
            valid=row['simulation_valid'] is True and row['physical_stopped'] is True and row['guard'] is False
            value=number(row['task_time_s'],3) if valid and row['task_outcome']=='FULL_SUCCESS' else '普通失败（罚26秒）' if valid and row['task_outcome']=='TASK_FAILURE' else row['task_outcome']+'（保护/无效/未停稳，未计分）'
            cells.append(case_id+suffix+' '+value)
        title=['XY=(0,0)','P1 (+,+)','P2 (−,+)','P3 (−,−)','P4 (+,−)'][i]
        matrix.append('| '+title+' | '+' | '.join(cells)+' |')
    matrix='\n'.join(matrix)+'\n\n单元为点编号与任务耗时（秒）；*为旧4点只读复用。行符号对应X/Y各±75μm，列符号对应roll/pitch各±0.25°；原四点只在J11/J22/J33/J44，新增点补齐其余组合。'
    for point in c.registered_cases():
        row=by_id.get(point['id'])
        if row is None:
            details.append(f"| {point['id']} | 缺完整可计分档案 | 待证据 | — | — | — | — | — | — |")
            continue
        margin='无MAIN重叠' if row['audit_end_clearance_um'] is None else number(row['audit_end_clearance_um'],5)
        details.append(f"| {row['case_id']} | {'旧点复用' if row['reused'] else '本次新增'} | {row['task_outcome']} | {number(row['task_time_s'],3)} | {number(row['phase_times_s'].get('SEARCH',0.),3)} | {number(row['force_mN'],3)} | {number(row['final_xy_um'],3)} | {number(row['final_angle_deg'],4)} | {margin} |")
    discussion=[]
    if complete:
        if summary['ordinary_failures']==0:
            discussion.append('这25个离散开发点没有出现纯B2功能失败，不能据此声称传统方法在当前范围失败率高。')
        else:
            discussion.append('已保存普通任务失败，失败按登记26秒罚时；具体机制须对照轨迹，不能只凭结果标签认定接触歧义或控制器缺陷。')
        base=result['strata']['aligned']['mean_penalized_time_s']
        joint=result['strata']['joint']['mean_penalized_time_s']
        position=result['strata']['position_only']['mean_penalized_time_s']
        orientation=result['strata']['orientation_only']['mean_penalized_time_s']
        discussion.append(f"对中/仅位置/仅姿态/联合的登记均值分别为{number(base)}/{number(position)}/{number(orientation)}/{number(joint)}秒。这是本限定离散矩阵的描述比较，不是重复试验的统计显著性、连续域或实物结论。")
        positional=[r for r in rows if r['group']=='position_only']
        misses=[r for r in rows if r.get('functional_plus_precision') is not True]
        angle_misses=[r for r in misses if r['final_angle_deg']>.5]
        discussion.append(f"登记附加质量标准达标{summary['additional_precision']}/25。仅位置组为0/4，終末XY为{min(r['final_xy_um'] for r in positional):.3f}～{max(r['final_xy_um'] for r in positional):.3f}μm，最小几何余量为{min(r['audit_end_clearance_um'] for r in positional):.5f}～{max(r['audit_end_clearance_um'] for r in positional):.5f}μm。联合组为{result['strata']['joint']['additional_precision']}/16；其中终末倾角超过0.5°的点为"+'、'.join(f"{r['case_id']}（{r['final_angle_deg']:.4f}°）" for r in angle_misses)+"。其余附加质量未达标点主要是终末XY超过80μm。")
        discussion.append('附加质量未达标点：'+', '.join(r['case_id'] for r in misses)+'。80μm/0.5°是在本次执行前登记的诊断标准，未标定为产品失效界限；较小几何余量或较大倾角也没有经过额外扰动/实机验证，不能直接称鲁棒性失败。当前可核对的不足是特定组合的搜索耗时及功能成功后的终末质量差异，尚需同信息、同口径的SAC与合理传统对照来判断改善空间。')
    else:discussion.append('矩阵不完整，保留已完成结果、故障和未执行点；不发布完整25点平均值，不把剩余点当作失败或成功。')
    discussion.append('本次只有传统B2新数据；尚未形成21新点的SAC配对结果，不能认定强化学习提升或候选C方法成立。旧四点F2000的平均2.72%提速、附加精度0/4及单种子限制保持，不外推到新矩阵。')
    report='\n\n'.join(['# B.2第3项：21点纯B2实际评价与25点分层基线',
        f'2026-10-11。当前阶段B.2第3项“普通SAC训练与真实任务评价”；本项{status}。普通SAC后续工作、第4项独立评价、第5项联合范围验收仍待。',
        synopsis,'位置取对中与4个XY角点（X/Y各±75μm），姿态取无倾角与4个roll/pitch角点（各±0.25°）。这两组5状态独立组合，得到对中1、仅位置4、仅姿态4、联合16点；yaw=0、初始原点Z=−4mm、目标深度4mm。未覆盖全部单轴或连续幅值，它们是刚性多针模型的离散开发资料，不是连续域或实机认证。',table,'## 位置×姿态矩阵',matrix,'## 逐点结果','\n'.join(details),'## 证据判断','\n\n'.join(discussion),
        '功能采用原裁判；附加80μm/0.5°只作质量诊断。最终质量在真实停稳审核末端计算，任务结束位姿与两处几何余量另存于原始档案。SEARCH、载荷、位置、姿态和几何余量分别报告，不以保护阈值替代实际载荷表现。',
        '## 初始化、监督与费用',costs,
        f"新点实际初始化通过{sum(r.get('initial_audit',{}).get('passed') is True for r in ledger['episodes'])}/{result['new_attempts']}。各原始收据包含完整模型复位、真实位姿、初始接触与穿透、六维载荷、守卫、退出监督及归属证明。整包监督原始墙钟字段={whole}；完整字段见[整包监督](run/coordinator_gate.supervisor.json)。",
        '共同模型/控制/保护/成功阈值、旧4点与新25点范围摘要保持。旧4点别名仅用于矩阵展示，原case_id/档案/范围摘要未改写。21新点的零残差证据不授予非零SAC、训练或连续域资格。',
        '旧入口46/46离线测试与一次独立审查沿用；旧四点准备测试26/27的历史目录存在断言限制保留。本轮不重写旧测试或档案、不提交、不另建工作区。最终实际结果与发布由作者核验，没有新增独立复现实验或第二次代码审查。',
        '## 下一项与路线',next_task,reminder,
        '证据：[授权](authorization_grant.json)、[登记](registration.json)、[关闭账本](run/ledger.json)、[授权关闭](authorization_closure.json)、[完整审核](assessment.json)、[逐点CSV](comparison.csv)、[限定资格](case_qualification.json)、[最终核验](verification.json)。原始新档案保留在本目录run/case_0～case_20（仅实际尝试的子目录存在）；旧4点来源路径和哈希保持在assessment.json。'])+'\n'
    (OUT/'结果说明.md').write_text(report,encoding='utf-8')
    for name in DOCS:
        prefix='../../learning_chain/' if name==MONTH else 'deliverables/learning_chain/'
        link=prefix+OUT.name+'/结果说明.md'
        marker='\n'.join(['<!-- b2-scope-current -->',f'**2026-10-11｜当前阶段B.2第3项；任务：21点纯B2实际评价与分层基线，{status}。**','',synopsis,'',costs,'',next_task,'',reminder,'','[本次真实结果与证据]('+link+')。以下历史资料保留各自时点，当前下一项以本段为准。','<!-- /b2-scope-current -->'])
        path=ROOT/name
        prior_snapshot=OUT/'after_documents'/name
        if prior_snapshot.exists() and c.sha(path)!=c.sha(prior_snapshot):raise ValueError('Preserve intervening document edits before publication refresh')
        text=(OUT/'before_documents'/name).read_text(encoding='utf-8')
        text,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:marker,text,count=1,flags=re.S)
        if n!=1:raise ValueError('Missing current marker')
        if name=='项目进度跟踪.md':
            text=text.replace('当前入口限制：','此前入口交付限制（当时）：',1)
            row=next(l for l in text.splitlines() if l.startswith('| B.2 小规模学习与评价包 |'))
            text=text.replace(row,f'| B.2 小规模学习与评价包 | 待验收；新21点纯B2{status} | [实际证据]({link}) | 普通SAC分层、第4/5项及连续范围仍待 |',1)
            start=text.index('## 原八项任务对应\n');end=text.index('## 当前风险和准入门\n',start)
            mapping='\n'.join(['## 原八项任务对应','', '| 原任务 | 当前对应 |','|---|---|',
                f"| 1 开发适用性 | 本次真实初始化通过{sum(r.get('initial_audit',{}).get('passed') is True for r in ledger['episodes'])}/{result['new_attempts']}；仅零残差离散基线，非零SAC/连续范围及旧3缺口保持 |",
                '| 2 统一闭环/SAC接口 | 2379绑定来源/200共同工具保持；共同配置与四点/25点范围指纹分开登记 |',
                f"| 3 动态闭环/成本 | 新复位尝试{cost['reset_attempts']}，累计{result['cumulative_dynamic'] if result['cumulative_dynamic'] is not None else result['cumulative_dynamic_range']}；所有尝试和费用归档，余额关闭 |",
                '| 4 B1 | 既有成果保持；零残差结果不升级非零动作或训练资格 |',
                f"| 5 B2与批量评价 | 25点已审核{summary['available']}/25；功能成功{summary['functional_successes']}，普通失败{summary['ordinary_failures']}，旧4点只读复用 |",
                '| 6 普通残差SAC | 原四点2000批保持；冻结演员新21点开发评价与必要普通SAC工作仍待，主方法必须用RL |',
                '| 7 阶段与进展约束 | C暂缓，依据B.2数据与阶段总结确定含RL候选 |',
                '| 8 正式证据与展示 | 新实际档案、分层/逐点表和成本归档；第4/5项、C前汇总及D正式多种子仍待 |','', ''])
            text=text[:start]+mapping+text[end:]
            text=replace_section(text,'## 下一项交付',next_task+'\n\n'+costs+'\n\n'+reminder+'\n\n[本轮结果]('+link+')、[当月月报]('+MONTH+')。')
            pos=text.index('## 当前风险和准入门\n')+len('## 当前风险和准入门\n')
            text=text[:pos]+'\n当前实际评价限制：'+synopsis+' 非零SAC适用性仍待；不能把零残差通过等同训练准入。\n'+text[pos:]
            text+='\n\n### 2026-10-11｜B.2第3项新21点纯B2实际评价\n\n'+synopsis+'\n\n'+costs+'\n\n'+next_task+'\n\n[结果]('+link+')、[滚动月报]('+MONTH+')。\n'
        elif name=='研究推进计划_当前版.md':
            for heading in ['## 研究目标和保留架构','### B.2 小规模学习与评价包']:
                pos=text.index(heading+'\n')+len(heading)+1
                text=text[:pos]+'\n2026-10-11当前实际交付：'+synopsis+' '+costs+'\n\n'+next_task+'\n\n'+reminder+'\n\n以下此前入口/范围准备保留当时口径：\n'+text[pos:]
        elif name=='项目交付总览.md':
            pos=text.index('## 基线与接口交付\n')+len('## 基线与接口交付\n')
            text=text[:pos]+'\n### B.2第3项新21点实际纯B2与25点分层基线｜2026-10-11\n\n'+synopsis+'\n\n成果与使用：[实际结果]('+link+')、[机器审核]('+prefix+OUT.name+'/assessment.json)、[CSV]('+prefix+OUT.name+'/comparison.csv)、[核验]('+prefix+OUT.name+'/verification.json)。只读归档，不重新调用已消费execution。\n\n'+costs+'\n\n'+next_task+'\n'+text[pos:]
        elif name==MONTH:
            inserts={'## 一、本月综合摘要':synopsis+' '+costs+' '+next_task,
                '## 二、关键数字与证据':table+'\n\n'+costs,
                '## 三、负结果与限制':' '.join(discussion)+' 非零SAC、连续域和完整B.2/C尚未验收。',
                '## 四、图表与讲稿':'本轮展示[25点逐点与分层结果表]('+link+')；讲稿：“当前B.2第3项只取得纯B2分层基线，随后准备冻结SAC同场景对照；不能用文档或零残差通过宣称B.2全部完成。”'}
            for heading,body in inserts.items():text=text.replace(heading+'\n',heading+'\n\n**本次真实评价更新：** '+body+'\n\n以下此前记录保留：\n',1)
            text=replace_section(text,'## 五、下一项',next_task+'\n\n'+costs+'\n\n'+reminder+'\n\n[本轮结果]('+link+')。')
            text+='\n\n2026-10-11｜B.2第3项新21点真实纯B2：[结果]('+link+')。'+synopsis+' '+costs+'\n'
        path.write_text(text,encoding='utf-8')
    for name in ['AGENTS.md']+DOCS:
        dest=OUT/'after_documents'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
    c.write(OUT/'document_update.json',dict(files=DOCS,status='INTEGRATED',monthly_sections=5,AGENTS_modified=False))
    with (OUT/'progress.md').open('a',encoding='utf-8') as stream:stream.write('\nPublication verification: saved evidence retained; terminal quality diagnosis and rolling snapshots updated. Task4 final seal pending.\n')
    print(c.canonical(dict(package_status=ledger['status'],summary=summary,costs=cost)))

if __name__=='__main__':main()
