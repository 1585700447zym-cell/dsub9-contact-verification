"""Publish the closed outcome to existing rolling documents and snapshots."""
from pathlib import Path
import os
import re
import shutil
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(OUT.parent/'b2_joint_admission_preflight_20261009'))
from scope_contract import read,sha
from execution_contract import write
def section(t,h,b):
    t,n=re.subn('('+re.escape(h)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+b.rstrip()+'\n',t,count=1,flags=re.S)
    assert n==1;return t
def main():
    if (OUT/'document_update.json').exists():raise PermissionError('Already updated')
    s=read(OUT/'execution_summary.json');r=read(OUT/'route_decision.json');running=read(OUT/'running_document_update.json')['after_documents']
    n=s['reserved_dynamic'];a=s['audited_attempts'];unused=s['unused_dynamic_closed'];total=s['cumulative_after_reserved'];counts=s['recorded_counts']
    recovery_count=len(r['recovery_covered']);gap_count=len(r['timing_gaps'])
    gaps='、'.join(g['id'] for g in r['timing_gaps']) or '无'
    evidence=f"工程恢复覆盖{recovery_count}/4；A/B时序覆盖缺口{gap_count}处（{gaps}），缺口的逐周期接触／权限／有效作用分类已归档。"
    if r['gap_classifications'] and all(g['classification']=='NO_CONTACT_IN_FIXED_BLOCK' for g in r['gap_classifications']):
        evidence+='全部时序缺口均为固定快速块与实际接触没有重叠，不能据此推断改时序后的结果。'
    summary=f"B2-SCOPE-10固定12项联合点预检已执行并关闭：本轮尝试{n}/12，审核通过{a}，功能成功{r['audited_functional_successes']}、真实停稳{r['audited_physical_stops']}，未执行{unused}项数量关闭。"+evidence+r['conclusion']
    cost=f"本轮实际累计动态{total}（原225＋本轮{n}）；归档{counts['control_cycles']}控制周期／{counts['native_steps']}物理子步。学习器、张量读取、前向、优化和经验发布全0；训练未准入，自动跟踪PAUSED，全部本轮及旧预算关闭，无重试。"
    limits='完整B.2/C未验收；四个±75μm／±0.25°联合开发点不等于原±1.5°范围，固定代表动作不是连续动作域安全证明。R为工程触发恢复，不计自然成功率；A/B不计策略学习收益。独立评价0，共同模型／保护／观测／奖励保持。'
    next_task=r['next_task'];updated={}
    for name,pin in running.items():
        p=ROOT/name;assert sha(p)==pin,'Concurrent document edit: '+name
        t=p.read_text(encoding='utf-8');rel=os.path.relpath(OUT,p.parent).replace('\\','/')
        links=f'[结果说明]({rel}/结果说明.md)、[路线决定]({rel}/路线决定.md)、[原始账本]({rel}/run/ledger.json)、[授权关闭]({rel}/authorization_closure.json)。'
        body=summary+'\n\n'+cost+'\n\n'+limits+'\n\n'+next_task+'\n\n'+links
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2；任务：B2-SCOPE-10联合点固定物理预检，执行与收口已完成。** '+body+' 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        t,num=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,t,count=1,flags=re.S);assert num==1
        if name=='项目进度跟踪.md':
            t,num=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；SCOPE-10物理预检已关闭 | [结果]({rel}/结果说明.md) | {r["conclusion"]} 匹配学习、冻结评价与完整范围仍待 |',t,flags=re.M);assert num==1
            tasks=[('1 开发适用性','仍限四个离散J点，原大范围未验收'),('2 统一闭环/SAC接口','继承137维、F50和共同保护；工程恢复结果按本轮证据判定'),('3 动态闭环/成本',cost),('4 B1','原来源和资格保留，不跨范围升级'),('5 B2与批量评价',summary),('6 普通残差SAC',next_task),('7 阶段与进展约束','C继续暂缓，旧数值成果保留'),('8 正式证据与展示','固定分母、全部档案、停稳／覆盖／成本分列；无新独立评价或策略收益')]
            t=section(t,'## 原八项任务对应','| 原任务 | 本次核对状态 |\n|---|---|\n'+'\n'.join(f'| {k} | {v} |' for k,v in tasks))
            start=t.index('## 当前风险和准入门');end=t.index('下表保留历史限制',start)
            t=t[:start]+'## 当前风险和准入门\n\n'+r['conclusion']+evidence+'\n\n'+limits+'\n\n'+next_task+'\n\n'+t[end:]
            t=section(t,'## 下一项交付',next_task+'\n\n'+cost+'\n\n'+links)
            t+='\n### 2026-10-09｜B2-SCOPE-10联合点物理预检执行与关闭\n\n'+body+' 最终验收为记录与关闭校验，不把失败改为资格。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)，阶段结束暂停汇报。\n'
        elif name=='项目交付总览.md':
            t=t.replace('## 快速查找\n\n','## 快速查找\n\n当前实际结果见[B2-SCOPE-10]('+rel+'/结果说明.md)；'+summary+'\n\n',1)
            t=t.replace('当前实现见[B2-SCOPE-09]','前轮实现见[B2-SCOPE-09]',1)
            t=t.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n### B2-SCOPE-10｜联合点固定物理预检（2026-10-09）\n\n'+body+'\n\n使用：按原始账本和逐项收据区分功能、有效性、停稳、覆盖；授权关闭后不能续跑旧入口。\n\n',1)
        elif name=='研究推进计划_当前版.md':
            start=t.index('### B.2 小规模学习与评价包');end=t.index('\n1. 先在',start)
            t=t[:start]+'### B.2 小规模学习与评价包\n\n2026-10-09执行优先级：'+summary+' '+cost+' '+next_task+' 以下原要求保留。\n'+t[end:]
        elif name.startswith('deliverables/'):
            additions={'## 一、本月综合摘要':body,
                '## 二、关键数字与证据':f'| 本轮SCOPE-10 | 实际结果 |\n|---|---|\n| 固定分母／尝试／审核通过 | 12／{n}／{a} |\n| 未执行数量关闭 | {unused} |\n| 当前累计动态 | {total} |\n| 归档周期／子步 | {counts["control_cycles"]}／{counts["native_steps"]} |\n| 整体墙钟秒 | {s["outer_supervisor"]["wall_seconds"]:.3f} |\n| 新学习／独立评价 | 0／0 |\n\n'+links,
                '## 三、负结果与限制':r['conclusion']+' '+evidence+' '+limits+' 失败、未执行和峰值缺口原样保留，不通过补采改变分母。',
                '## 四、图表与讲稿':'本轮用结果说明的固定12行矩阵和成本表。讲稿：“仍在B.2，完成一轮有限预检并关闭授权。'+summary+' '+cost+' 下一步按真实路线结果处理，不自动进入C或训练。”'}
            for h,b in additions.items():assert t.count(h)==1;t=t.replace(h+'\n',h+'\n\n'+b+'\n\n以下保留前轮时点：\n',1)
            t=section(t,'## 五、下一项',next_task+'\n\n'+cost+'\n\n'+limits)
            t+='\n### 2026-10-09｜B2-SCOPE-10物理预检来源\n\n'+body+'\n'
        updated[name]=t
    for name,t in updated.items():(ROOT/name).write_text(t,encoding='utf-8')
    after={}
    for name in [*running,'AGENTS.md']:
        dst=OUT/'document_snapshots'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);after[name]=sha(dst)
    write(OUT/'document_update.json',dict(stage_id='B2-SCOPE-10',after_documents=after,rolling_documents_may_advance=True))
    print('Five rolling documents integrated; six immutable after snapshots saved.')
if __name__=='__main__':main()
