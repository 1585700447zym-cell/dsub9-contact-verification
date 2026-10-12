"""Publish SCOPE15 preparation results and update current project documentation."""
from pathlib import Path
import os,re,shutil,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
from joint_contract import read,write,sha

def section(text,heading,body):
    text,n=re.subn('('+re.escape(heading)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+body.rstrip()+'\n',text,count=1,flags=re.S)
    assert n==1;return text

def main():
    if (OUT/'document_update.json').exists():raise FileExistsError('Preserve published snapshot')
    reg=read(OUT/'registration.json');review=read(OUT/'review_resolution.json');assert review['status']=='RESOLVED'
    suite='suite_final.json' if (OUT/'suite_final.json').exists() else 'suite_first.json';tests=read(OUT/suite);assert tests['successful']
    summary=f'B2-SCOPE-15预热状态重建与独立恢复数值门已完成离线接入。相关标准库测试{tests["tests"]}项通过，独立审查已收口；实际数值恢复尚未执行。'
    capability='候选将核对原零检查点的全部网络、优化器、温度、计数和策略随机状态，按原顺序重建4份预热档案的19300行回放与终末边界，逐周期重放388次四维预热抽样。新检查点独立读取、重新构建、完整状态比较及运行对象恢复读回均已接入，尚无真实张量验证结果。'
    scope='本轮新增物理／学习器／张量读取／网络前向／优化／经验发布均0，累计动态245；自动跟踪PAUSED。SCOPE13已完成F0评价4＋预热4成功、正式更新0的结果及原文件访问失败保持；旧17回合授权的未用部分关闭，不重开、不自动重跑前8回合。'
    limits='当前仍在B.2第3项“普通SAC训练与真实任务评价”。范围为四个固定±75μm／±0.25°开发点，原3处逐profile覆盖缺口及事后开发覆盖修订保留；完整B.2/C未验收，独立测试0。接口和离线检查通过不等于数值恢复通过，也不等于SAC有效。'
    next_task='下一项：申请一次独立的CPU状态重建验证，限学习器构造2、张量读取2、完整保存1、确定性预测2、旧档案回放重建8（父进程4＋独立进程4）；新增物理／优化更新／采集经验均0。整体最多30分钟，独立读取进程最多15分钟，失败关闭且不重试。通过后再准备从预热边界继续的训练及匹配评价方案；当前没有新的训练准入。'
    table='| 状态组成 | 候选实现 | 当前证据边界 |\n|---|---|---|\n'
    table+='| 零状态来源 | 完整有类型状态比较：网络／Adam／温度／策略RNG／全部计数 | 张量未加载 |\n'
    table+='| 旧经验与预热随机流 | 原4档案重建19300行；按原种子核对388次四维抽样 | 实际数组及PCG64状态待数值门 |\n'
    table+='| 独立恢复 | reader独立重建、完整摘要比较、运行对象恢复读回；再检查确定性预测 | 真实reader未运行 |\n'
    table+='| 执行约束 | 一次性运行、父／reader共享计数、角色上限、拥有的进程树硬截止、失败关闭 | 标准库反例与受控子进程测试通过 |\n'
    table+='| 研究结论 | 保留失败和开发范围限制 | 不能据此主张策略有效或完整B.2/C验收 |\n'
    body='\n\n'.join((summary,capability,scope,limits,next_task))
    report='# B2-SCOPE-15｜预热状态重建与独立恢复数值门接入\n\n当前阶段：B.2第3项；本次离线接入与审查已完成，实际数值恢复待开始。\n\n'+body+'\n\n## 验证与局限\n\n'+table
    report+='\n来源从SCOPE13的零检查点、已关闭执行记录、4份预热原档案及收据继承；来源封套保留旧binding以标明出处，外层training_admitted=false，不能凭此启动旧在线事务。恢复目标为第四份预热完整发布之后的边界。原online J01仅登记、未创建环境，不能把本项写成恢复该中断事务。\n\n'
    report+='新申请中的“重建8次”是父／reader各复算同4份旧经验，并非8个新物理回合，也不增加数据量。两次确定性预测只检查预测前后完整模型与策略随机状态是否一致，不评价策略性能。运行时间30分钟是本次监督上限，不是预估必需耗时。\n\n'
    report+='测试用标准库运行，未导入NumPy、Torch、MuJoCo或SB3。离线测试覆盖拒绝未授权入口、重复角色／超额／非法计数、关闭余额、恢复元数据，以及此前Windows文件锁、截止和进程退出回归；实际张量、随机数发生器与神经网络数值语义仍待运行验证。\n\n'
    report+='独立审查发现并修复两项问题：完整摘要补上字典长度以区分嵌套结构；进程持锁超时后，凭整棵进程树退出证据处理遗留锁，账本关闭失败也独立写授权关闭记录。反例均先失败再通过，详情见review.md。本门不创建可训练V4Chain；后续在线接入及审计随机流等运行字段仍须单独验证。\n\n'
    report+='使用：[候选](candidate.json)、[未批准的执行申请](authorization_request.json)、[完整离线测试]('+suite+')、[独立审查](review.md)、[交付核验](verification.json)。run_gate.py只接受独立签发并绑定本候选的新grant；authorization_request.json本身不能启动。候选失败时不恢复旧额度。\n'
    (OUT/'结果说明.md').write_text(report,encoding='utf8')
    pending={}
    for name,pin in reg['before_documents'].items():
        if name=='AGENTS.md':continue
        path=ROOT/name;assert sha(path)==pin,'Concurrent edit '+name
        rel=os.path.relpath(OUT,path.parent).replace('\\','/')
        links=f'[本次结果]({rel}/结果说明.md)、[数值候选]({rel}/candidate.json)、[具体申请（未批准）]({rel}/authorization_request.json)。'
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2第3项；任务：B2-SCOPE-15状态重建数值门离线接入，已完成。** '+body+'\n\n'+links+' 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        text,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,path.read_text(encoding='utf8'),count=1,flags=re.S);assert n==1
        if name=='项目进度跟踪.md':
            text=text.replace('## 当前状态\n','## 当前状态\n\n2026-10-09当前：'+summary+' '+capability+' '+scope+'\n\n以下保留此前时点：\n',1)
            text,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；SCOPE-15恢复数值门已接入 | [结果]({rel}/结果说明.md) | 实际恢复未运行；原8回合成功／更新0；训练和独立评价待 |',text,flags=re.M);assert n==1
            tasks=[('1 开发适用性','四点联合开发范围保持，未扩展完整范围'),('2 统一闭环/SAC接口','恢复验证入口已接入；SAC算法及奖励不变'),('3 动态闭环/成本',scope),('4 B1','已有成果保留，不扩大验收'),('5 B2与批量评价','原初始评价4/4及预热4/4成功；训练后评价未执行'),('6 普通残差SAC',capability),('7 阶段与进展约束','仍在B.2第3项，C物理接入暂缓'),('8 正式证据与展示','独立测试0；旧失败、3处覆盖缺口保留')]
            text=section(text,'## 原八项任务对应','| 原任务 | 当前对应 |\n|---|---|\n'+'\n'.join(f'| {a} | {b} |' for a,b in tasks))
            a=text.index('## 当前风险和准入门');b=text.index('下表保留历史限制',a)
            text=text[:a]+'## 当前风险和准入门\n\n'+limits+'\n\n'+capability+'\n\n'+next_task+'\n\n'+text[b:]
            text=section(text,'## 下一项交付',next_task+'\n\n'+scope+'\n\n'+links)
            text+='\n### 2026-10-09｜B2-SCOPE-15预热状态重建数值门接入\n\n'+body+'\n\n'+links+' 本交付阶段结束后暂停汇报。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            text=text.replace('## 快速查找\n\n','## 快速查找\n\n当前恢复验证候选：[B2-SCOPE-15]('+rel+'/结果说明.md)。\n\n',1)
            text=text.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n### B2-SCOPE-15｜预热状态重建数值门（2026-10-09）\n\n'+body+'\n\n'+links+'\n\n使用：run_suite.py可进行离线回归；run_gate.py须另有绑定本候选的明确数值授权。\n\n',1)
        elif name=='研究推进计划_当前版.md':
            a=text.index('### B.2 小规模学习与评价包');b=text.index('\n1. 先在',a)
            text=text[:a]+'### B.2 小规模学习与评价包\n\n2026-10-09当前：'+summary+' '+capability+' '+next_task+' '+scope+' 以下原阶段要求保留。\n'+text[b:]
        elif name.startswith('deliverables/'):
            numbers=f'| 本轮项目 | 实际结果 |\n|---|---|\n| 标准库离线测试 | {tests["tests"]}项通过 |\n| 本轮新增物理／张量读取／训练 | 0／0／0 |\n| 累计动态 | 245 |\n| 重建来源 | 4份旧预热，19300行 |\n| 数值恢复／完整B.2验收 | 均未通过，实际数值门未执行 |'
            adds={'## 一、本月综合摘要':body,'## 二、关键数字与证据':numbers+'\n\n'+links,'## 三、负结果与限制':limits+' '+capability,
                '## 四、图表与讲稿':table+'\n讲稿：“仍在B.2第3项。本轮准备复用已有预热经验，已完成完整状态重建及独立恢复验证入口和离线测试。实际恢复待执行，正式更新仍为0，不能把工程准备写成策略效果。”'}
            for h,b in adds.items():assert text.count(h)==1;text=text.replace(h+'\n',h+'\n\n'+b+'\n\n以下保留前轮时点：\n',1)
            text=section(text,'## 五、下一项',next_task+'\n\n'+scope+'\n\n'+limits)
            text+='\n### 2026-10-09｜B2-SCOPE-15来源记录\n\n'+body+'\n\n'+links+'\n'
        pending[name]=text
    for name,text in pending.items():(ROOT/name).write_text(text,encoding='utf8')
    after={}
    for name in reg['before_documents']:
        dst=OUT/'document_snapshots'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);after[name]=sha(dst)
    write(OUT/'document_update.json',dict(after_documents=after,rolling_documents_may_advance=True,test_report=suite))
    print('Five current documents integrated; six snapshots saved.')

if __name__=='__main__':main()
