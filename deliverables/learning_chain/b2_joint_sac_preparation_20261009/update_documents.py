"""Integrate the current candidate into existing rolling documents, preserving history."""
from pathlib import Path
import os
import re
import shutil
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from joint_contract import ROOT,read,write,sha


def section(text,heading,body):
    text,n=re.subn('('+re.escape(heading)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+body.rstrip()+'\n',text,count=1,flags=re.S)
    assert n==1;return text


def main():
    if (OUT/'document_update.json').exists():raise PermissionError('Already integrated')
    reg=read(OUT/'registration.json')
    summary='B2-SCOPE-12四点普通F50 SAC离线接入与具体登记完成：联合位姿贯通采集、审核和检查点，原SAC数值内核保持；15项纯检查通过，4份旧零残差档案共同条件核对通过，独立审查3项问题已修复。'
    bounds='3处原逐profile缺口保持；按同一J点合并A/B支持有限开发准备，但不能保证训练效果。覆盖专项补验0。范围仅四个固定±75μm／±0.25°点；原完整范围、实际短训、真实恢复和独立评价仍待，完整B.2/C未验收。'
    cost='本轮新物理／学习器／张量读取／推理／更新／经验发布均0，累计动态237；训练未准入，自动跟踪PAUSED，旧授权全部关闭。'
    next_task='下一项：申请一次新的17动态回合、最多2000正式更新批及7次构造／2次张量读取／2次保存的新运行，整体硬限6小时；先过零起点完整检查点真实独立恢复门，再固定完成F0评价4、预热4、在线4、F2000评价4、独立物理复现1。失败停止、不重试、不结转，累计动态最多254；不进入C。'
    metric='主指标保持共同26秒正常失败罚时；F2000相对匹配F0均值改善≥10%且最终四点成功、无硬保护、有效停稳及恢复一致，才给开发继续信号。无效仿真、保护失败与全部峰值单列；不是独立效果验收。'
    pending={}
    for name,pin in reg['before_documents'].items():
        if name=='AGENTS.md':continue
        path=ROOT/name;assert sha(path)==pin,'Concurrent document edit: '+name
        text=path.read_text(encoding='utf-8');rel=os.path.relpath(OUT,path.parent).replace('\\','/')
        links=f'[接入与登记说明]({rel}/结果说明.md)、[具体新申请（未批准）]({rel}/authorization_request.json)、[候选]({rel}/candidate.json)、[原始档案核对]({rel}/baseline_equivalence.json)。'
        body=summary+'\n\n'+bounds+'\n\n'+cost+'\n\n'+next_task+'\n\n'+metric+'\n\n'+links
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2第3项；任务：B2-SCOPE-12四点普通SAC离线接入与具体登记，已完成；实际执行待开始。** '+body+' 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        text,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,text,count=1,flags=re.S);assert n==1
        if name=='项目进度跟踪.md':
            text=text.replace('## 当前状态\n','## 当前状态\n\n2026-10-09当前：'+summary+' '+cost+'\n\n以下保留此前时点：\n',1)
            text,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；SCOPE-12四点SAC离线候选已完成 | [说明]({rel}/结果说明.md) | 17回合／2000批新申请待批准；真实恢复／短训／独立评价及完整范围仍待 |',text,flags=re.M);assert n==1
            tasks=[('1 开发适用性','仅四个离散J点，未扩展原完整范围'),('2 统一闭环/SAC接口','F50/137维原数值内核保持，联合位姿接入及离线检查完成，真实恢复待运行'),('3 动态闭环/成本',cost),('4 B1','原成果及证据保留，不跨范围升级'),('5 B2与批量评价','四点旧共同参照核对通过；新F0/F2000开发评价待执行'),('6 普通残差SAC','17回合/2000批有界候选已登记，未开训'),('7 阶段与进展约束','仍在B.2第3项准备，C物理工作暂缓'),('8 正式证据与展示','事后覆盖修订及原失败保留，独立测试0，不将候选当效果')]
            text=section(text,'## 原八项任务对应','| 原任务 | 当前对应 |\n|---|---|\n'+'\n'.join(f'| {k} | {v} |' for k,v in tasks))
            start=text.index('## 当前风险和准入门');end=text.index('下表保留历史限制',start)
            text=text[:start]+'## 当前风险和准入门\n\n'+bounds+'\n\n'+next_task+'\n\n'+metric+'\n\n'+text[end:]
            text=section(text,'## 下一项交付',next_task+'\n\n'+cost+'\n\n'+links)
            text+='\n### 2026-10-09｜B2-SCOPE-12四点普通SAC接入与登记\n\n'+body+' 本可交付阶段完成后暂停汇报。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            text=text.replace('## 快速查找\n\n','## 快速查找\n\n当前四点普通SAC接入与具体新运行申请：[B2-SCOPE-12]('+rel+'/结果说明.md)。旧覆盖复核与失败档案保持。\n\n',1)
            text=text.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n### B2-SCOPE-12｜四点普通SAC离线接入（2026-10-09）\n\n'+body+'\n\n使用：默认入口仅做文件校验；新执行须另有绑定该候选的新grant，历史预算不可复用。\n\n',1)
        elif name=='研究推进计划_当前版.md':
            start=text.index('### B.2 小规模学习与评价包');end=text.index('\n1. 先在',start)
            text=text[:start]+'### B.2 小规模学习与评价包\n\n2026-10-09当前：'+summary+' '+next_task+' '+bounds+' '+cost+' 以下原阶段要求保持。\n'+text[end:]
        elif name.startswith('deliverables/'):
            additions={'## 一、本月综合摘要':body,
                '## 二、关键数字与证据':'| SCOPE-12本轮离线准备 | 结果 |\n|---|---|\n| 纯检查 | 15通过 |\n| 真实旧零残差档案核对 | 4 |\n| 共同绑定来源保持 | 2173文件 |\n| 本轮新物理／训练 | 0／0 |\n| 实际累计动态 | 237 |\n| 下一次提案 | 17回合／2000批，未批准 |\n| 独立测试 | 0 |\n\n'+links,
                '## 三、负结果与限制':bounds+' '+metric+' 本次未运行新的真实检查点／Windows硬终止故障注入。',
                '## 四、图表与讲稿':'图表采用SCOPE-12固定17回合顺序与实际/拟申请成本表。讲稿：“当前仍在B.2第3项，四点普通SAC接入已完成离线核对，真实训练尚未开始。原覆盖缺口保留，不能事先保证效果。下一轮先验证零起点恢复，再在相同四点比较训练前后，失败完整记录。”'}
            for heading,b in additions.items():assert text.count(heading)==1;text=text.replace(heading+'\n',heading+'\n\n'+b+'\n\n以下保留前轮时点：\n',1)
            text=section(text,'## 五、下一项',next_task+'\n\n'+cost+'\n\n'+bounds)
            text+='\n### 2026-10-09｜B2-SCOPE-12来源记录\n\n'+body+'\n'
        pending[name]=text
    for name,text in pending.items():(ROOT/name).write_text(text,encoding='utf-8')
    after={}
    for name in reg['before_documents']:
        target=OUT/'document_snapshots'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target);after[name]=sha(target)
    write(OUT/'document_update.json',dict(after_documents=after,rolling_documents_may_advance=True))
    print('Integrated five rolling documents and saved six immutable snapshots.')


if __name__=='__main__':main()
