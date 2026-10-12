"""Integrate this development decision into the five existing project documents."""
from pathlib import Path
import os
import re
import shutil
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(OUT))
from analyze import read,sha,write

def section(t,h,b):
    t,n=re.subn('('+re.escape(h)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+b.rstrip()+'\n',t,count=1,flags=re.S)
    assert n==1;return t

def main():
    if (OUT/'document_update.json').exists():raise PermissionError('Already updated')
    r=read(OUT/'route_decision.json');reg=read(OUT/'registration.json');before=reg['before_documents']
    summary='B2-SCOPE-11离线覆盖条件复核完成：8份动作档案重算与原审核一致。按同一J点合并A/B后，快速接触有效命令周期分别25／28／32／30，长保持1428／1767／2341／2510；下一次观测均有非零六维力／力矩信号。四点均有四轴正负方向，原4项工程恢复和24项峰值重叠证据保留。'
    decision='建议把两种时序的覆盖要求按每个J点合并A/B检查，保留周期末接触定义与所有保护条件。覆盖专项新增回合建议0，下一项转普通SAC小规模训练的接入与具体登记。该建议来自开发档案复核，不是独立验证；SCOPE10按原逐profile判据的3处缺口及失败路线保持。'
    limits='当前阶段B.2第2项已交付本次复核；训练接入与执行尚未完成，完整B.2/C未验收。范围仅四个离散±75μm／±0.25°开发点，不扩展原±1.5°或连续域。观察到信号和命令作用不等于策略收益或任意动作安全。'
    cost='本轮新增物理／子步／学习器／推理／更新／经验发布均0，累计动态237；训练未准入，自动跟踪PAUSED，旧授权全部关闭。'
    pending={}
    for name,pin in before.items():
        if name=='AGENTS.md':continue
        p=ROOT/name;assert sha(p)==pin,'Concurrent edit: '+name;t=p.read_text(encoding='utf-8')
        rel=os.path.relpath(OUT,p.parent).replace('\\','/')
        links=f'[复核与路线]({rel}/结果说明.md)、[建议条件v2]({rel}/recommended_gate_v2.json)、[逐周期统计]({rel}/coverage_comparison.json)、[训练准备边界]({rel}/pilot_preparation_scope.json)。'
        body=summary+'\n\n'+decision+'\n\n'+cost+'\n\n'+limits+'\n\n下一项：'+r['next_task']+'\n\n'+links
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2第2项；任务：B2-SCOPE-11覆盖条件复核与最小处理方案，已完成。** '+body+' 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        t,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,t,count=1,flags=re.S);assert n==1
        if name=='项目进度跟踪.md':
            t=t.replace('## 当前状态\n','## 当前状态\n\n2026-10-09当前：'+summary+' '+decision+' '+cost+'\n\n以下为此前记录时点：\n',1)
            t,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；SCOPE-11覆盖条件复核已完成 | [复核]({rel}/结果说明.md) | 建议覆盖专项补验0；下一项普通SAC四点接入与登记，匹配训练／独立评价／完整范围仍待 |',t,flags=re.M);assert n==1
            tasks=[('1 开发适用性','本次仅四个离散J点；原完整范围未验收'),('2 统一闭环/SAC接口','原137维、F50、2ms与公共保护保持；新短训接线待完成'),('3 动态闭环/成本',cost),('4 B1','保留原资格与来源，不跨范围升级'),('5 B2与批量评价',summary+' 原SCOPE10判据与结果不追改'),('6 普通残差SAC','下一项四点普通SAC小规模训练接入与登记；覆盖专项补验建议0，尚未开训'),('7 阶段与进展约束','C物理实验仍暂缓，原数值成果保留'),('8 正式证据与展示','新旧判据并列；本次开发事后修订，不当作独立评价或论文效果')]
            t=section(t,'## 原八项任务对应','| 原任务 | 当前对应 |\n|---|---|\n'+'\n'.join(f'| {k} | {v} |' for k,v in tasks))
            start=t.index('## 当前风险和准入门');end=t.index('下表保留历史限制',start)
            t=t[:start]+'## 当前风险和准入门\n\n'+decision+'\n\n'+limits+'\n\n'+r['next_task']+'\n\n'+t[end:]
            t=section(t,'## 下一项交付',r['next_task']+'\n\n'+cost+'\n\n'+links)
            t+='\n### 2026-10-09｜B2-SCOPE-11覆盖条件复核与路线\n\n'+body+' 本阶段完成后暂停汇报。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            t=t.replace('## 快速查找\n\n','## 快速查找\n\n当前路线见[B2-SCOPE-11]('+rel+'/结果说明.md)：按初始工况合并代表性证据，建议覆盖补验0，转准备普通SAC短训。原SCOPE10结果及更正保留。\n\n',1)
            t=t.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n### B2-SCOPE-11｜覆盖条件复核（2026-10-09）\n\n'+body+'\n\n使用：先读新旧条件差异与限制，再查看逐项统计；建议文件本身不启动训练或重新打开旧授权。\n\n',1)
        elif name=='研究推进计划_当前版.md':
            start=t.index('### B.2 小规模学习与评价包');end=t.index('\n1. 先在',start)
            t=t[:start]+'### B.2 小规模学习与评价包\n\n2026-10-09当前优先级：'+summary+' '+decision+' '+r['next_task']+' '+cost+' 以下原阶段要求保留。\n'+t[end:]
        elif name.startswith('deliverables/'):
            additions={'## 一、本月综合摘要':body,
                '## 二、关键数字与证据':'| 本轮SCOPE-11离线复核 | 结果 |\n|---|---|\n| 重读动作档案 | 8 |\n| 每个J点快速接触有效命令周期 | 25／28／32／30 |\n| 每个J点长保持接触有效命令周期 | 1428／1767／2341／2510 |\n| 快速段后续非零力／力矩观测 | 115／115 |\n| 建议新增覆盖专项回合 | 0 |\n| 本轮新增物理／训练 | 0／0 |\n| 累计动态 | 237 |\n\n'+links,
                '## 三、负结果与限制':decision+' '+limits+' 周期内峰值与周期末反馈继续分开；原3处逐profile缺口保持。本次不证明学习方法有效。',
                '## 四、图表与讲稿':'本轮图表采用结果说明中的四点覆盖表和三路线比较。讲稿：“当前仍在B.2。按同一工况合并单轴和组合测试，四点均已有快速与长保持接触证据；建议不再为交叉表补采，转普通SAC短训准备。此调整是开发阶段修改，原结果和失败保留，训练未启动。”'}
            for h,b in additions.items():assert t.count(h)==1;t=t.replace(h+'\n',h+'\n\n'+b+'\n\n以下保留前轮时点：\n',1)
            t=section(t,'## 五、下一项',r['next_task']+'\n\n'+cost+'\n\n'+limits)
            t+='\n### 2026-10-09｜B2-SCOPE-11来源记录\n\n'+body+'\n'
        pending[name]=t
    for name,t in pending.items():(ROOT/name).write_text(t,encoding='utf-8')
    after={}
    for name in before:
        dst=OUT/'document_snapshots'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);after[name]=sha(dst)
    write(OUT/'document_update.json',dict(after_documents=after,rolling_documents_may_advance=True))
    print('Five current documents integrated; six after snapshots recorded.')

if __name__=='__main__':main()
