"""Integrate current findings into five rolling documents and snapshot them."""
from pathlib import Path
import os
import re
import shutil
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
from joint_contract import read,write,sha

def section(text,heading,body):
    text,n=re.subn('('+re.escape(heading)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+body.rstrip()+'\n',text,count=1,flags=re.S)
    assert n==1;return text

def main():
    if (OUT/'document_update.json').exists():raise FileExistsError('Already published')
    reg=read(OUT/'registration.json');r=read(OUT/'recovery_assessment.json')
    suite_name='suite_final.json' if (OUT/'suite_final.json').exists() else 'suite_first.json'
    tests=read(OUT/suite_name);assert tests['successful']
    summary=f"B2-SCOPE-14文件读写修复候选与恢复来源核对已完成：Windows瞬态访问拒绝在读、替换两端作最多0.5秒的有限重试，并受整体／最近有效阶段绝对截止约束。完整相关离线测试{tests['tests']}项通过，含真实Windows文件锁、并发读写、受控子进程退出与原联合合同回归。"
    recovery=f"只读核对原4份预热档案：{r['replay_rows']}行，其中{r['active_rows']}行允许残差动作，388次四维抽样（1552个标量），顺序、动作保持、资格／配置／策略hash及原物理内容一致。重建所需来源齐全；尚未构造回放张量、加载检查点或验证NumPy／Torch随机状态，因此完整数值恢复与无损续跑均未通过。"
    scope='本轮新增物理／学习器／张量读取／网络前向／优化／经验发布均0，累计动态245；自动跟踪PAUSED，新执行准入无，旧17回合申请未用部分仍关闭。SCOPE13实际F0评价4＋预热4成功、正式更新0的结果不变。'
    limits='当前仍在B.2第3项“普通SAC训练与真实任务评价”；原3处逐profile覆盖缺口和事后开发覆盖修订保留。范围仅四个固定±75μm／±0.25°开发点；完整B.2/C未验收，独立测试0。文件修复通过不代表SAC有效或任意未来文件操作不会失败。'
    next_task='下一项：离线接入“零起点＋4份既有预热档案”的状态重建与独立保存／恢复数值门，明确新来源绑定、所需数值操作及验收条件，形成可审阅候选后再提出具体执行申请。优先复用已完成物理档案；不直接加载旧零检查点跳进在线回合，不重开旧运行或自动重复前8回合。'
    table='| 状态组成 | 已有证据 | 当前结论 |\n|---|---|---|\n'
    table+='| 网络、优化器、温度 | 原零检查点独立恢复通过；更新0；档案演员hash一致 | 零状态可作为来源；重建张量未加载 |\n'
    table+='| 回放、终末边界 | 原19300行完整、有序、hash对应 | 可按原算法重建；实际数组尚未验证 |\n'
    table+='| 预热随机流 | 固定种子与388次四维抽样、逐周期held均记录 | PCG64完整状态与逐值抽样待数值核对 |\n'
    table+='| 回放／边界随机流 | 尚未执行第一次抽样或更新 | 源码支持仍为初始态；真实状态待核对 |\n'
    table+='| 策略Torch随机流 | F0为确定性预测，未执行在线采样 | 未变是源码支持的预期，尚无本轮张量证据 |\n'
    table+='| 中断事务 | online J01仅登记；原进程已终止 | 目标为前一完整预热边界，不能称恢复中断事务 |\n'
    report='# B2-SCOPE-14｜文件读写修复与恢复来源核对\n\n当前阶段：B.2第3项“普通SAC训练与真实任务评价”；本次离线修复候选与来源核对已完成，实际数值重建待开始。\n\n'+summary+'\n\n'+recovery+'\n\n## 修复及验证\n\n'
    report+='原程序在真实Windows独占锁测试中读、替换均失败；新候选在短锁释放后恢复。持续拒绝在0.5秒或更早外部绝对截止到达时停止，损坏JSON及非权限错误直接失败，替换失败保留原目标和新暂存文件。只重试文件操作，不重放物理或优化动作。\n\n'
    report+='监督器将已读取的阶段截止时间记为monotonic时刻；同一记录重复读取或墙钟回拨不会延长该期限。文件重试受当前最早截止限制，已过期阶段不能由新记录救回；正常、错误、阶段过期、整体过期和持续锁均验证拥有的进程树退出。单个OS文件调用本身不能由Python重试循环抢占，本项验证的是本地文件访问竞争及重试策略；不外推为磁盘故障容错。\n\n'
    report+='候选文件：bounded_io.py、phase_deadline.py、joint_contract.py、supervised.py。相对于SCOPE12，仅文件交换和监督路径发生改变，joint_contract的研究配置、四点、计数限制与评价函数保持。windows_job.py为未改动副本。旧封存文件保持原样；本目录不提供训练运行入口或新的训练资格。\n\n'
    report+='验证日志：[完整离线集]('+suite_name.replace('.json','.log')+')、[机器结果]('+suite_name+')、[原始读写失败](red_io.log)、[监督器反例](red_supervisor.log)、[独立审查](review.md)。\n\n## 恢复状态的证据边界\n\n'+table+'\n'+scope+'\n\n'+limits+'\n\n## 下一项\n\n'+next_task+'\n\n机器证据：[恢复核对](recovery_assessment.json)、[交付核验](verification.json)。\n'
    (OUT/'结果说明.md').write_text(report,encoding='utf8')
    route='# 预热后状态重建路线\n\n当前阶段：B.2第3项；来源核对已完成，完整数值重建及独立恢复未执行。\n\n'+table+'\n'
    route+='选择保留并复用SCOPE13的零检查点和四份原预热档案，准备一个新的、明确记录继承来源的数值门。它重建“第四次预热完整发布之后、首个在线事务之前”的状态，不把原grant重新打开，不抹去原失败。\n\n'
    route+='拟接入顺序：先核验所有来源hash与原关闭记录；在后续另登记的CPU数值运行中读取零检查点，按原顺序验证388次随机向量和动作保持，以原回放／边界算法重建19300行；核对零更新网络、优化器、温度、全部计数、两个未消费抽样流、预热流和策略RNG；随后保存新完整检查点，由独立进程读取并逐值比较。任何来源、随机流或状态不一致都停止该路线，不能以只检查演员hash替代完整恢复。\n\n'
    route+='新数值候选尚须处理旧binding与新审计来源的区别、禁止物理环境和优化调用的入口、父／reader共享操作计数以及失败关闭。实际构造／读取／保存次数须从完成后的代码路径登记，当前不凭空签发数量，也未执行它们。只有该门通过后，才考虑另行登记剩余训练及匹配评价；本轮不增加物理、网络前向或训练。\n\n'+next_task+'\n'
    (OUT/'状态重建路线.md').write_text(route,encoding='utf8')
    pending={}
    for name,pin in reg['before_documents'].items():
        if name=='AGENTS.md':continue
        path=ROOT/name;assert sha(path)==pin,'Concurrent rolling edit '+name
        rel=os.path.relpath(OUT,path.parent).replace('\\','/')
        links=f'[修复结果]({rel}/结果说明.md)、[恢复来源]({rel}/recovery_assessment.json)、[状态重建路线]({rel}/状态重建路线.md)。'
        body=summary+'\n\n'+recovery+'\n\n'+scope+'\n\n'+limits+'\n\n'+next_task+'\n\n'+links
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2第3项；任务：B2-SCOPE-14文件读写修复与恢复来源核对，已完成离线交付。** '+body+' 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        text,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,path.read_text(encoding='utf8'),count=1,flags=re.S);assert n==1
        if name=='项目进度跟踪.md':
            text=text.replace('## 当前状态\n','## 当前状态\n\n2026-10-09当前：'+summary+' '+recovery+' '+scope+'\n\n以下保留此前时点：\n',1)
            text,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；SCOPE-14离线修复完成 | [结果]({rel}/结果说明.md) | 文件监督修复通过；原8回合成功/更新0；完整数值重建未执行 |',text,flags=re.M);assert n==1
            tasks=[('1 开发适用性','四点联合开发范围保持，未扩展原完整范围'),('2 统一闭环/SAC接口','文件读写与监督修复候选通过；SAC数值内核不变'),('3 动态闭环/成本',scope),('4 B1','已有成果保留，不扩大验收'),('5 B2与批量评价','SCOPE13初始评价4/4成功，预热4/4成功；训练后评价未执行'),('6 普通残差SAC',recovery),('7 阶段与进展约束','仍在B.2第3项，C物理接入暂缓'),('8 正式证据与展示','独立测试0；旧失败和原覆盖缺口保留')]
            text=section(text,'## 原八项任务对应','| 原任务 | 当前对应 |\n|---|---|\n'+'\n'.join(f'| {k} | {v} |' for k,v in tasks))
            a=text.index('## 当前风险和准入门');b=text.index('下表保留历史限制',a)
            text=text[:a]+'## 当前风险和准入门\n\n'+limits+'\n\n'+recovery+'\n\n'+next_task+'\n\n'+text[b:]
            text=section(text,'## 下一项交付',next_task+'\n\n'+scope+'\n\n'+links)
            text+='\n### 2026-10-09｜B2-SCOPE-14文件并发修复与恢复来源核对\n\n'+body+' 本交付阶段结束后暂停汇报。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            text=text.replace('当前四点普通SAC试跑结果：','前轮四点普通SAC试跑结果：',1)
            text=text.replace('## 快速查找\n\n','## 快速查找\n\n当前文件并发修复与恢复来源：[B2-SCOPE-14]('+rel+'/结果说明.md)。\n\n',1)
            text=text.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n### B2-SCOPE-14｜文件并发修复与恢复来源（2026-10-09）\n\n'+body+'\n\n使用：只作为新版本候选与恢复来源核对；运行离线测试见run_suite.py，目录没有训练入口。\n\n',1)
        elif name=='研究推进计划_当前版.md':
            a=text.index('### B.2 小规模学习与评价包');b=text.index('\n1. 先在',a)
            text=text[:a]+'### B.2 小规模学习与评价包\n\n2026-10-09当前：'+summary+' '+recovery+' '+next_task+' '+scope+' 以下原阶段要求保留。\n'+text[b:]
        elif name.startswith('deliverables/'):
            numbers=f'| 本轮项目 | 实际结果 |\n|---|---|\n| 相关离线检查 | {tests["tests"]}项通过 |\n| 核对既有预热行 | 19300（非新增经验） |\n| 允许残差动作行 | 14127 |\n| 原四维随机抽样 | 388次 |\n| 本轮新增物理/模型读取/训练 | 0/0/0 |\n| 累计动态 | 245 |\n| 完整数值恢复 | 未执行 |'
            adds={'## 一、本月综合摘要':body,'## 二、关键数字与证据':numbers+'\n\n'+links,
                '## 三、负结果与限制':recovery+' '+limits,
                '## 四、图表与讲稿':table+'\n讲稿：“仍在B.2第3项。本轮修复文件访问冲突并验证截止与进程退出。已有预热资料可作为状态重建来源，但尚未完成完整数值恢复，正式训练更新仍为0。”'}
            for h,b in adds.items():assert text.count(h)==1;text=text.replace(h+'\n',h+'\n\n'+b+'\n\n以下保留前轮时点：\n',1)
            text=section(text,'## 五、下一项',next_task+'\n\n'+scope+'\n\n'+limits)
            text+='\n### 2026-10-09｜B2-SCOPE-14来源记录\n\n'+body+'\n'
        pending[name]=text
    for name,text in pending.items():(ROOT/name).write_text(text,encoding='utf8')
    after={}
    for name in reg['before_documents']:
        dst=OUT/'document_snapshots'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);after[name]=sha(dst)
    write(OUT/'document_update.json',dict(after_documents=after,rolling_documents_may_advance=True,test_report=suite_name))
    print('Five rolling documents integrated; six snapshots written.')

if __name__=='__main__':main()
