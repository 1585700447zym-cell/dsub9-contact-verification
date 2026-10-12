"""Integrate SCOPE-08 into rolling records; preserve historical stages."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

ROOT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT=ROOT/'deliverables/learning_chain/b2_joint_admission_design_20261009'
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
SUMMARY='B2-SCOPE-08准入方案设计完成：8份J档案确认SEARCH保留旧INSERT受阻历史，返回INSERT前全部清空，活动INSERT时长最大0.402s；本项饱和现象不要求改137维观测。已核对同版本零倾角自然恢复254.143μm及297个屏蔽周期，继承流程依据，不冒称联合姿态恢复通过。'
COST='本轮新增物理、学习器/张量读取、网络前向、更新及经验发布全0。实际累计动态225，自动跟踪PAUSED，旧预算关闭。拟最多12次新动态（8动作＋4工程恢复）、训练0，若以后另获授权并全部执行累计上限237；当前未实施、未授权，不把237记为实际累计。'
LIMITS='联合点完整动作域及真实恢复仍待实测；12次为代表性补验方案，不证明任意策略安全。2468次SEARCH饱和事实保持，其分支语义疑点已核对；不据此宣称完整Markov状态。31条相关测试只是读取历史结果（22条当前PC-06来源、9条旧B1），不是本轮新增测试通过。完整B.2/C未验收，±0.25°离散点不等于原±1.5°目标，独立测试0。'
NEXT='下一项实现B.2联合点预检候选并完成离线验收：固定A/B动作序列、单次恢复夹具、覆盖审核与一次性预算门，复用既有监督/归档；不创建环境、不推理或训练。程序和来源绑定完成后，再提交具体的新物理执行申请。P点不补采，137维、共同物理/保护/奖励保持，C暂缓。'

def section(t,heading,body):
    t,n=re.subn('('+re.escape(heading)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+body.rstrip()+'\n',t,count=1,flags=re.S)
    assert n==1;return t

def main():
    assert not (OUT/'delivery_manifest.json').exists() and not (OUT/'document_update.json').exists()
    reg=json.loads((OUT/'registration.json').read_text(encoding='utf-8'));updated={}
    for name in DOCS:
        path=ROOT/name;assert hashlib.sha256(path.read_bytes()).hexdigest()==reg['before_documents'][name]
        t=path.read_text(encoding='utf-8');rel=os.path.relpath(OUT,path.parent).replace('\\','/')
        links=f'[具体准入方案]({rel}/准入方案.md)、[未实施机器提案]({rel}/admission_proposal.json)、[状态与恢复证据]({rel}/evidence_review.json)、[继承矩阵]({rel}/inheritance_matrix.json)。'
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2；任务：联合点动作域与恢复准入方案设计，已完成。** '+SUMMARY+'\n\n'+COST+'\n\n'+LIMITS+'\n\n'+NEXT+'\n\n'+links+' 以下历史阶段的旧下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        t,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,t,count=1,flags=re.S);assert n==1
        if name=='项目进度跟踪.md':
            t,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；联合点准入方案已设计 | [B2-SCOPE-08]({rel}/准入方案.md) | 先实现/离线验收，拟12动态尚未授权；姿态匹配学习、冻结评价与完整范围仍待 |',t,flags=re.M);assert n==1
            rows=[
               '1 开发适用性 | 保留J01～J04离散范围，继承初始化和零残差依据；拟动作/恢复补验，原大范围未验收',
               '2 统一闭环/SAC接口 | 137维保持；8/8返回INSERT前旧历史清空，本项时长饱和不要求修改观测',
               '3 动态闭环/成本 | 本轮动态0、实际累计225；拟12次/174万子步/整体6h均未授权，237仅为未来提案上限',
               '4 B1 | 当前和历史资格按来源/范围继承，不重跑整套旧物理测试；旧9条恢复测试不冒称当前联合通过',
               '5 B2与批量评价 | 拟8动作＋4工程恢复，固定分母；当前runner未实现，功能/有效停稳/作用/恢复分别判定',
               '6 普通残差SAC | 先补联合点准入，再另行登记姿态匹配短训和共同参照；本轮无训练准入',
               '7 阶段与进展约束 | C继续暂缓，PC-11～14及其数值成果保留',
               '8 正式证据与展示 | 新交付状态语义、恢复继承、明确动作/恢复协议和成本；无新独立评价或学习效果']
            t=section(t,'## 原八项任务对应','| 原任务 | 本次核对状态 |\n|---|---|\n'+'\n'.join('| '+row+' |' for row in rows)+'\n\n'+COST)
            start=t.index('## 当前风险和准入门');end=t.index('下表保留历史限制',start)
            t=t[:start]+'## 当前风险和准入门\n\n'+LIMITS+'\n\n'+NEXT+'\n\n保护/运行/审核失败关闭后续分配；普通任务失败和覆盖不足分列，不补采到通过，不放宽25mN保护。原S/F负结果与旧失败封存保持。\n\n'+t[end:]
            t=section(t,'## 下一项交付',NEXT+'\n\n'+COST+'\n\n'+links)
            t+='\n### 2026-10-09｜B2-SCOPE-08联合点准入方案设计\n\n'+SUMMARY+'\n\n'+COST+'\n\n'+LIMITS+'\n\n'+NEXT+'\n\n'+links+' 本项只验收离线审查与方案；最终校验见verification.json。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)，阶段结束暂停汇报。\n'
        elif name=='项目交付总览.md':
            heading='## 快速查找\n\n';assert heading in t
            t=t.replace(heading,heading+'当前方案见[B2-SCOPE-08准入设计]('+rel+'/准入方案.md)；机器提案明确runner_implemented=false、dynamic_authorized=false。'+NEXT+'\n\n',1)
            t=t.replace('当前先看[B2-SCOPE-07联合点复核]','前轮依据见[B2-SCOPE-07联合点复核]',1)
            entry='### B2-SCOPE-08｜联合点动作域与恢复准入设计（2026-10-09）\n\n'+SUMMARY+'\n\n'+COST+'\n\n使用：先读方案的固定12项、动作日程、工程恢复触发、失败出口和成本；按继承矩阵区分可复用依据与待实测项。该提案不能作为执行grant。\n\n'+LIMITS+'\n\n'+links+'\n\n'
            t=t.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n'+entry,1)
        elif name=='研究推进计划_当前版.md':
            start=t.index('### B.2 小规模学习与评价包');end=t.index('\n1. 先在',start)
            t=t[:start]+'### B.2 小规模学习与评价包\n\n2026-10-09执行优先级更新：'+SUMMARY+' '+COST+' '+NEXT+' 以下原要求保留，完整B.2/C未验收。\n'+t[end:]
        elif name.startswith('deliverables/'):
            parts={
              '## 一、本月综合摘要':'截至本轮B2-SCOPE-08：'+SUMMARY+' '+COST+'\n\n下一步先实现准入候选，不直接训练。以下保留此前阶段证据：',
              '## 二、关键数字与证据':'| 本轮B2-SCOPE-08项目 | 实际审查或未执行提案 |\n|---|---|\n| 既有联合档案/周期 | 8／42656，离线读取 |\n| 返回INSERT清空历史 | 8/8；活动INSERT时长最大0.402s |\n| 已核对SEARCH饱和 | 2468；SEARCH时钟未饱和 |\n| 旧零倾角恢复 | 回撤254.143μm；屏蔽297周期 |\n| 历史相关测试记录 | 31（当前来源22／旧B1 9），非新执行 |\n| 拟新动态上限 | 12：8动作＋4工程恢复，尚未授权 |\n| 拟子步/整体硬限 | 1740000／6h，尚未执行 |\n| 新物理/推理/训练 | 全0；实际累计225 |\n| 237 | 仅未来全部执行时的提案累计上限 |\n\n'+links+'\n\n以下为前轮数字：',
              '## 三、负结果与限制':LIMITS+'\n\n旧G50自然回撤时请求全零，不能替代非零F50恢复屏蔽压力检查；工程触发的R也不能解释为自然恢复成功率。以下保留前轮时点：',
              '## 四、图表与讲稿':f'本轮采用[继承证据表、固定12项矩阵和成本表]({rel}/准入方案.md)。讲稿：“仍在B.2。这次查清受阻时长在SEARCH只是保留的旧历史，回到INSERT会清空，暂不改137维。旧零倾角恢复可以作为流程依据，但联合姿态还要定向补验。拟8次动作和4次恢复，先实现与离线检查；本轮物理0、累计225，不是已开启新预算。”\n\n以下讲稿保留此前时点：'}
            for h,b in parts.items():assert t.count(h)==1;t=t.replace(h+'\n',h+'\n\n'+b+'\n',1)
            t=section(t,'## 五、下一项',NEXT+'\n\n'+COST+'\n\n'+LIMITS)
            t+='\n### 2026-10-09｜B2-SCOPE-08准入设计来源\n\n'+SUMMARY+'\n\n'+COST+'\n\n'+LIMITS+'\n\n'+links+' 设计未实施，未新增物理样本、学习结果或独立测试。\n'
        else:assert name=='项目当前入口.md'
        updated[name]=t
    for name,text in updated.items():(ROOT/name).write_text(text,encoding='utf-8')
    after={}
    for name in DOCS+['AGENTS.md']:
        p=OUT/'document_snapshots'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
        after[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    (OUT/'document_update.json').write_text(json.dumps(dict(stage_id='B2-SCOPE-08',after_documents=after,rolling_documents_may_advance=True),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Five rolling documents and six immutable after snapshots updated.')

if __name__=='__main__':main()
