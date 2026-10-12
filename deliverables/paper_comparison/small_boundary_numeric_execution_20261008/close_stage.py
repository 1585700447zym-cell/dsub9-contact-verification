"""Close the consumed numerical-only grant and maintain five rolling documents."""
from pathlib import Path
import datetime,re,shutil,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];KIT=OUT.parent/'small_boundary_numeric_gate_20261007'
sys.path.insert(0,str(KIT))
from numeric_contract import read,write,sha
sys.path.insert(0,str(OUT))
from audit_numeric_result import audited_result
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
NEXT='下一项只做F12.5物理backend接入与准入材料的离线准备：连接固定物理profile、零更新部署/独立恢复和原保护审核，先形成可审阅候选。2次物理预检、拟21动态/2000正式批仍需独立的新授权与逐项准入；本次4/32合成数值额度已耗尽关闭，无结转或自动重试。自动跟踪PAUSED。'
STATE='本轮合成更新4/4（父3/reader1）、显式测试状态前向32/32（各16），新合成回放400行，辅助模型构造4/4、CPU张量读取3/3。新物理/子步/正式更新/性能评价均0，累计动态208；完整B.2/C未验收。798旧封存成员、1057共享输入及36runtime文件保持。'


def section(s,title,text):
    pattern=re.escape(title)+r'\n.*?(?=\n## |\Z)'
    if len(re.findall(pattern,s,re.S))!=1:raise ValueError('Section differs: '+title)
    return re.sub(pattern,lambda _:title+'\n\n'+text+'\n',s,count=1,flags=re.S)


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Already sealed; no rewriting')
    a=audited_result();assert a['passed'] and a['status']=='PASSED_NUMERIC_ONLY'
    write(OUT/'numeric_assessment.json',a)
    write(OUT/'numeric_qualification.json',dict(version='pc14_numeric_validation_only_v1',status='PASSED_NUMERIC_ONLY',
        scope='F12p5 synthetic numerical integration and independent complete restoration',numeric_verified=True,
        training_admitted=False,physical_training_admitted=False,dynamic_authorized=False,physical_backend_implemented=False,
        authorization_consumed=True,authorization_closed=True,grant_sha256=a['grant_sha256'],candidate_sha256=a['candidate_sha256'],
        assessment_sha256=sha(OUT/'numeric_assessment.json'),actual_synthetic_updates=4,actual_explicit_state_forwards=32,
        actual_new_synthetic_rows=400,actual_physical_episodes=0,actual_formal_updates=0,cumulative_dynamic=208))
    m=a['measured']
    summary=f"PC-14合成数值门已验收：使用冻结CPU运行时，真实同种子零起点/空优化器与回放/三个RNG、完整检查点独立进程恢复和下一步参数/Adam/回放/终末边界/RNG/采样索引逐值一致通过；仅测量wall_s排除。{a['checks']}项只读收口检查通过，沿用PC-13的78项纯检查证据。实际总监督用时{m['whole_supervised_wall_s']:.2f}s。"
    (OUT/'结果说明.md').write_text(f'''# PC-14：小边界合成数值门通过

2026-10-08（Asia/Shanghai），用户明确批准上一条4事务/32显式状态/400合成行提案。沿用原worktree、分支和未提交修改。**本次只验收合成数值集成，未签发物理训练资格。**

{summary}

| 验证或成本 | 实际结果 | 证据 |
|---|---|---|
| 零起点 | actor/critic/target/alpha四指纹与预登记一致；计数0、空Adam/回放/历史、warm/replay/boundary三个RNG起点一致 | [原始记录](run/zero_origin.json) |
| SAC数值更新 | 父3＋reader1，共4尝试/4完成；末端actor/critic/target/temperature计数均3；reader前两批为继承记录 | [全局账本](run/ledger.json)、[父journal](run/parent_chain/update_journal.jsonl)、[reader journal](run/reader_chain/update_journal.jsonl) |
| 显式状态前向 | 父16＋reader16，共32尝试/32完成；实际a未缩放进入回放/critic，物理组合才0.25a；inactive target实际钩子检查通过 | [独立动作](run/reader_actions.json)、[固定且未改代码](../small_boundary_numeric_gate_20261007/numeric_worker.py) |
| 新合成档案 | warm4＋online1，80行/份，共400新行、390活动行、8次warm抽样；恢复拷贝400行逐字节相同 | [原始复核](numeric_assessment.json) |
| 完整落盘与恢复 | 外层profile与原完整核心保存；真实独立Windows reader恢复后，参数/Adam/replay/终末边界/RNG/下次采样及更新逐值一致 | [运行结果](run/numeric_result.json)、[完整检查点](run/checkpoint/manifest.json) |
| 额外原模型构造 | 4尝试/4完成，合计{m['model_construction_wall_s']:.4f}s | [父成本](run/parent_costs.json)、[reader成本](run/reader_costs.json) |
| CPU张量读取 | 3尝试/3完成，合计{m['tensor_read_wall_s']:.4f}s | 同上；复核脚本只读JSON/原始字节，没有新增张量读取 |
| 数值整体监督 | {m['whole_supervised_wall_s']:.2f}s；4个更新事务自身合计{m['actual_update_wall_s']:.4f}s | [正常退出](run.supervision/exit.json)、[reader退出](run/reader_exit.json) |

批内SAC前后向属于4个更新事务，32只统计显式测试状态，不是全部网络计算调用数。构造4次包含原核心保存/读取时的审核实例；读取3次包含reader两次核心读取与父一次读取reader状态，全部成本单列。

全局授权已消费并关闭：4/4、32/32，未用0，无结转/重试。新物理回合、物理子步、正式训练更新、性能评价均0，累计动态208，自动跟踪PAUSED。400行是全新synthetic_qualification数据，raw明确synthetic=true/dynamics_executed=false/physical_stop_measurement=null；用于边界检查的TASK_FAILURE/eligibility布尔值不计为物理任务成败或停稳实测。独立恢复的400行复制不再计为新经验。

[只读复核](numeric_assessment.json)确认5份恢复档案与原始字节相同，父/reader三批历史中采样索引、loss、actor指纹和计数一致；第3批各自计算，前两批reader继承。固定脚本已对完整张量状态逐值比对，只排除被测wall_s。原actor/critic/target/alpha、SAC超参数、奖励、几何、保护、137维/4维与1057共享来源保持。

PC-13的33封存成员及此前765成员保持（共798）。其候选/请求/报告仍保留2026-10-07未授权准备状态。本次唯一新授权和结果在本目录；固定脚本追加的排他claim位于PC-13 numeric_claims，并已在[本次快照](claim_snapshot/identity.json)留证。没有改写原封存摘要或旧原始实验。

实际Windows venv launcher→真实Python父/reader链均核验且正常退出，五个登记PID已结束。超时强制树停止仍只有PC-13纯反例证据，本轮没有做额外故障计算。数值门通过不证明F12.5学习收益、物理闭环有效或S优势；旧S/F0.39%未过10%门保持，PC-12两个停止上下文缺口保持，完整B.2/C仍未验收。

{NEXT}

本次无新执行源码，沿用PC-13一次代码审查及作者修复；本轮完成真实数值和只读原始证据复核，没有第二次代码审查或新资格扩权。工作取舍见[阶段账本](progress.md)。五份滚动资料和快照已维护，本可交付阶段完成后暂停汇报。
''',encoding='utf8')
    for name in DOCS:
        p=ROOT/name;s=p.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else '';base=prefix+'deliverables/paper_comparison/small_boundary_numeric_execution_20261008/'
        block=f'''<!-- pc14-current -->
**PC-14（2026-10-08）：小边界合成数值门通过；物理backend与训练准入仍待。** {summary}

{STATE}

{NEXT}

本次数字只计合成数值集成；资格[numeric_verified=true/training_admitted=false]({base}numeric_qualification.json)。旧S/F0.39%继续门失败和PC-12两个停止上下文缺口保持。正常退出通过，额外故障/策略性能评价未进行。[结果说明]({base}结果说明.md)、[原始复核]({base}numeric_assessment.json)、[关闭账本]({base}authorization_closure.json)。本阶段完成后暂停汇报，下方保留历史时点。
<!-- /pc14-current -->'''
        if '<!-- pc14-current -->' in s:raise RuntimeError('PC14 rolling stage already written')
        s=s.replace('\n','\n\n'+block+'\n',1)
        if name=='项目进度跟踪.md':
            s=s.replace('## 当前状态\n','## 当前状态\n\n**截至2026-10-08，最新为PC-14合成数值门通过。** '+STATE+' '+NEXT+'\n\n下方保留此前阶段的日期和原结论；当前下一项见本文件顶部及“下一项交付”。\n',1)
            s,n=re.subn(r'\| C 候选约束与消融 \| [^\n]*',
                '| C 候选约束与消融 | 待验收；PC-14合成数值门已验收 | [真实数值证据]('+base+'结果说明.md) | 物理backend/新训练准入仍待，没有新物理匹配训练或策略效果结论 |',s,count=1);assert n==1
            labels=['1 开发适用性','2 统一闭环/SAC接口','3 动态闭环/成本','4 B1','5 B2与批量评价','6 普通残差SAC','7 阶段与进展约束','8 正式证据与展示']
            values=['原五开发点范围保持；本轮只有合成数据，无新物理适用性或最终测试',
                '137维/4维保持；F12.5实际SAC数值、完整独立保存/恢复/下一步逐值对照已验收',
                '新增物理0、累计208；合成4更新/32显式状态/400行，辅助构造4/读取3，整体89.34s',
                '历史B1结果保持，本轮未补采',
                '历史25评价/PC-12命令缺口保持；本轮新性能评价0，完整B.2未验收',
                'F12.5归一化a与物理尺度实际数值门通过；新物理匹配训练未开始',
                'C公平对照前置数值门通过；物理backend/准入待，完整C验收仍待',
                'PC-14真实数值/原始审计/费用和额度关闭证据交付；论文性能/多种子/最终测试待']
            for label,value in zip(labels,values):
                s,n=re.subn(r'\| '+re.escape(label)+r' \| [^\n]* \|',lambda _:f'| {label} | {value} |',s,count=1);assert n==1
            s=section(s,'## 下一项交付',NEXT+'\n\n'+STATE+'\n\n[数值门已关闭]('+base+'authorization_closure.json)。')
            a0=s.index('## 当前风险和准入门');b0=s.index('下表保留历史限制',a0)
            s=s[:a0]+'## 当前风险和准入门\n\n'+summary+'\n\n'+STATE+'\n\n风险：本轮仅合成数值集成。真实物理backend未连接、物理/训练新资格无；数值通过不证明策略收益。正常进程恢复通过，超时强停没有追加实测；旧两个停止上下文缺口及S/F0.39%负结果保持。额度已耗尽且关闭，旧余额不重开。\n\n'+s[b0:]
            s+='\n\n### 2026-10-08｜PC-14合成数值门真实执行与收口\n\n'+summary+' '+STATE+' '+NEXT+' 来源：[结果]('+base+'结果说明.md)、[复核]('+base+'numeric_assessment.json)、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            marker='### PC-14｜小边界合成数值门（2026-10-08）'
            s=s.replace('### PC-13｜',marker+'\n\n- **获得：** '+summary+'\n- **使用：** [结果]('+base+'结果说明.md)、[数值资格（不准入物理训练）]('+base+'numeric_qualification.json)、[只读复核]('+base+'audit_numeric_result.py)。执行已关闭，不再运行原worker。\n- **证据与成本：** '+STATE+'\n- **限制与下一项：** '+NEXT+'\n\n### PC-13｜',1)
        elif name.startswith('deliverables/'):
            s=re.sub(r'统计截至：[^\n]*','统计截至：2026-10-08（北京时间，PC-14合成数值门真实执行）。实时状态见[项目进度跟踪](../../../项目进度跟踪.md)，10月继续维护本文件，9月保留历史口径。',s,count=1)
            values={'## 一、本月综合摘要':summary+' '+STATE,
                '## 二、关键数字与证据':f'PC-14：4/4合成更新、32/32显式状态、400新合成行；构造4/4、CPU读取3/3；整体{m["whole_supervised_wall_s"]:.2f}s、构造{m["model_construction_wall_s"]:.4f}s、读取{m["tensor_read_wall_s"]:.4f}s。物理/正式训练/性能评价0、累计208。798旧封存/1057共享输入/36runtime文件保持；新数值授权已耗尽关闭。',
                '## 三、负结果与限制':'PC-14数值集成真实通过，不代表策略有效或物理训练准入；物理backend仍待。额外超时故障实测0。旧S/F0.39%负结果及PC-12两个停止上下文缺口保持，完整B.2/C未验收。',
                '## 四、图表与讲稿':'PC-14采用[实际验证与成本表]('+base+'结果说明.md)。讲稿：“小边界适配的实际SAC更新和完整独立恢复已经通过，4批和32测试状态额度用完；物理回合仍然0，没有新增策略优势证据。下一项先接物理backend，物理训练需另行准入。”'}
            for title,value in values.items():
                pattern='('+re.escape(title)+r'\n\n)PC-13[^\n]*'
                s,n=re.subn(pattern,lambda match:match[1]+value,s,count=1);assert n==1,title
            s=section(s,'## 五、下一项',NEXT+'\n\n'+STATE)
            s+='\n\n2026-10-08｜PC-14合成数值门执行｜'+summary+' '+STATE+' 来源：[结果]('+base+'结果说明.md)、[复核]('+base+'numeric_assessment.json)、[关闭]('+base+'authorization_closure.json)。\n'
        p.write_text(s,encoding='utf8');snapshot=OUT/'document_snapshots'/name;snapshot.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,snapshot)
    p=ROOT/'docs/superpowers/plans/2026-10-07-small-boundary-numeric-gate.md';s=p.read_text(encoding='utf8')
    s=s.replace('# 小边界数值集成门实施计划\n','# 小边界数值集成门实施计划\n\n> 2026-10-08接续：用户明确批准4/32/400合成门，PC-14实际执行通过并耗尽关闭；以下PC-13离线准备约束保留当时口径，原封存快照不改。物理/正式训练仍0。\n',1)
    s=s.replace('- [ ] 实际CPU零起点','- [x] 实际CPU零起点').replace('这一步本轮不执行。失败关闭余额，无重试。','PC-13阶段未执行；现PC-14在明确授权后通过，4/4、32/32，400合成行，余额已关闭。物理/正式训练0，无重试。')
    p.write_text(s,encoding='utf8');shutil.copyfile(p,OUT/'implementation_plan_updated_snapshot.md')
    p=OUT/'执行登记.md';s=p.read_text(encoding='utf8').replace('- [ ]','- [x]');p.write_text(s,encoding='utf8')
    with (OUT/'progress.md').open('a',encoding='utf8') as f:
        f.write('\nTask actual execution: complete — 一次监督执行exit0，4/4合成更新、32/32显式状态、400新合成行，真实完整独立下一步状态一致。辅助构造4/4、CPU读取3/3，整体89.34s，物理/正式0。\n')
        f.write('\nTask raw audit: complete — 初次只读脚本engine_binding字段假设导致KeyError，按原始qualification_sha256/config_sha256字段修正；warmup_draws是累计值按max复核。没有重新启动执行、张量读取或推理。91初检通过，追加75份claim快照后166检查通过。五登记PID均已结束、额度耗尽关闭、无新代码复审。\n')
        f.write('\nTask rolling documents: complete — 五份更新及before/current快照保存，当前能力/八任务/风险/下一项与10月综合摘要数字、限制、讲稿及来源同步。原PC13封存33成员保持。\n')
    files={}
    for p in sorted(OUT.rglob('*')):
        if p.is_file() and not any(part=='__pycache__' for part in p.relative_to(OUT).parts):
            rel=p.relative_to(OUT).as_posix()
            if rel!='delivery_manifest.json':files[rel]=dict(sha256=sha(p),bytes=p.stat().st_size)
    write(OUT/'delivery_manifest.json',dict(version='pc14_numeric_execution_v1',status='SEALED_PASSED_NUMERIC_ONLY',
        user_date='2026-10-08',timezone='Asia/Shanghai',numeric_verified=True,training_admitted=False,physical_training_admitted=False,
        actual_synthetic_updates=4,actual_test_state_forwards=32,actual_synthetic_rows=400,physical_episodes=0,formal_updates=0,
        cumulative_dynamic=208,automatic_tracking='PAUSED',authorization_closed=True,
        rolling_documents='immutable snapshots; current roots may advance',files=files))
    print('PC14 NUMERIC EXECUTION SEALED',len(files),'files; five documents updated; numeric pass, training false')


if __name__=='__main__':main()
