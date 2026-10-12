"""Integrate the reviewed offline continuation candidate into existing project docs."""
import os,re,shutil,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
from joint_contract import read,write,sha

def section(text,heading,body):
    text,n=re.subn('('+re.escape(heading)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+body.rstrip()+'\n',text,count=1,flags=re.S)
    assert n==1;return text

def main():
    if (OUT/'document_update.json').exists():raise FileExistsError('Preserve published snapshots')
    reg=read(OUT/'registration.json');review=read(OUT/'review_resolution.json');test=read(OUT/'suite_final.json')
    assert review['status']=='RESOLVED' and review['open_critical']==review['open_important']==0 and test['successful']
    summary=f'B2-SCOPE-19预热状态接入续训链及四点匹配评价候选已完成离线实现和独立审查，{test["tests"]}项标准库检查通过；实际训练链恢复与续训尚未执行。'
    capability='新增适配入口从SCOPE18已验证封套恢复普通SAC训练链；只把外层状态的binding换成独立的新授权，4份旧预热档案和收据字节保持。旧预热须逐份hash匹配，新的online来源须使用新授权。安装模型／优化器／温度、回放、终末边界和三个随机流，同时补齐预热审核随机流、累计抽样数与held动作；先核对完整安装状态，再保存并交给独立进程核对包含运行字段的完整状态，通过后才创建首个物理环境。'
    scope='本轮科学库导入／模型构造／张量读取／预测／优化／物理／新经验均0，累计动态245、自动跟踪PAUSED。SCOPE18旧预热组件恢复数值通过仍有效；SCOPE13原F0评价4与预热4成功、文件访问失败，以及SCOPE16导入失败均保持。新候选未签发grant、未消耗claim，不重开任何旧授权或未用次数。'
    limits='仍在B.2第3项“普通SAC训练与真实任务评价”。当前四点路线正式更新0、训练后评价未执行；原3处逐profile接触覆盖缺口和事后开发覆盖修订保留。范围仅四个固定±75μm／±0.25°开发点，完整B.2/C未验收，独立测试0。标准库检查与代码接入不等于真实训练链恢复通过、下一批更新等价或策略有效。'
    next_task='下一项：申请一次绑定本候选的新运行，新增9个动态回合（在线4＋F2000匹配评价4＋独立恢复物理复现1），每个在线回合完整审核发布后最多500批、共2000正式更新批。模型构造8、张量读取3、保存2、检查点档案重建28（旧预热20＋新在线8）；整体6小时、单物理20分钟、单reader30分钟。先过可训练预热链完整保存与独立恢复门，失败立即关闭、不重试、不结转。复用已绑定F0四点评价及4份预热，不重跑旧8回合；本次申请尚未批准，累计动态254仅为拟上限。'
    body='\n\n'.join((summary,capability,scope,limits,next_task))
    table='| 项目 | 本次状态 |\n|---|---|\n'+f'| 离线检查 | {test["tests"]}项通过；独立审查无未解决Critical／Important |\n'
    table+='| 原始数据继承 | F0四点评价＋4份预热19300行／14127行动作启用／388次四维抽样 |\n| 本轮新增模型／张量／更新／物理 | 0／0／0／0 |\n| 累计动态 | 245 |\n| 下一运行申请 | 9动态／2000批，未批准；预计累计最多254 |\n| 完整B.2／C／独立测试 | 未验收／未验收／0 |\n'
    report='# B2-SCOPE-19｜预热状态接入续训链与四点评价候选\n\n当前阶段：B.2第3项；本次离线实现、审查与候选准备已完成。\n\n'+body+'\n\n## 结果与限制\n\n'+table
    report+='\n本候选复用原普通F50 SAC算法、137维观察、4维动作、四个联合位姿、奖励、保护／成功判据及物理回合循环。configuration仅替换待运行序列。共同配置／运行时／旧档案均继续绑定；初始F0仍是同配置、同种子、同零更新演员的四点开发评价，不将其称未见独立测试。\n\n'
    report+='旧封套的模型、优化器、温度、随机状态、经验、原始档案及终末边界来自SCOPE18。迁移仅改变state.binding，随后逐值摘要检查其余字段不变；旧档案原grant是来源标识，不能成为新执行许可。新的online档案与新检查点均使用新grant。父进程初始化、保存验证以及两个reader使用同一完整恢复代码路径；_audited_warm_rng和_audited_warm_draws与预热随机状态同步。回放和边界必须由原档案重新审核构建。\n\n'
    report+='恢复后的预热状态available=0、正式更新=0。新在线采集须完成有效仿真、停稳与原保护审核并发布，才取得500批更新额度；不凭19300行旧预热经验直接开2000批更新。拟运行的前置门验证实际可训练链保存与独立恢复；尚未单独验证恢复后下一次优化的数值等价。本次不宣称该等价已通过。\n\n'
    report+='成本拆分：父进程4构造／1读取／2保存／16档案重建，预热reader2／1／0／4，最终reader2／1／0／8，总计8／3／2／28。28次重建包含20次旧预热和8次新在线档案，均为保存／恢复审核的重复计算，不是28个新增物理回合。控制循环／原生子步／观察／政策调用按9回合逐次预留最大值，真实执行量由轨迹与日志另报；优化块先预留500次，完成批数由持久更新历史核对。\n\n'
    report+='SCOPE14有限文件读／替换重试与绝对阶段截止、受控Windows进程树退出原样继承，不能外推成任意磁盘故障容错。新关闭回执独立撤销授权，即使计数器关闭失败也不允许复用；只有已确认拥有的进程退出，才清理遗留计数锁。现有验证覆盖元数据、真实档案、源码顺序及旧不变内容，未执行新数值恢复或故障注入。\n\n'
    report+='开发评价沿用26秒普通任务失败罚时：F2000相对匹配F0均值改善至少10%、四点均成功、无硬保护、有效停稳且独立恢复一致，才给开发继续信号。无效仿真、保护失败、全部尝试及峰值单列；未达门槛照实报告，不改阈值、扩种子或补跑至成功。该信号不等于完整B.2/C或论文优势验收。\n\n'
    report+='仓库导入检查覆盖所列运行入口与数值／物理模块的源码，记录条件及延迟依赖；第三方包未执行或递归分析，任意Python动态导入不由静态检查保证。主代理修复了过早的模块级科学导入，独立审查修复档案数值审核前的扣账顺序，反例先失败后通过；另有一次隔离解释器缺少本目录搜索路径的构建脚本错误，发生在复制前，已保留TDD记录。所有这些都是离线准备事件，worker从未启动。\n\n'
    report+='文件：[候选](candidate.json)、[具体新申请](authorization_request.json)、[继承核对](inheritance_audit.json)、[标准库检查](suite_final.json)、[独立审查](review.md)、[交付核验](verification.json)。\n\n使用run_pilot.py默认只读检查，不导入科学库。实际运行需独立签发绑定candidate和source_binding的新grant；申请JSON本身不能启动。verify_delivery.py --current-docs核对当前文档及快照，滚动文档后续推进后省略该开关。本阶段完成后暂停汇报。\n'
    (OUT/'结果说明.md').write_text(report,encoding='utf8')
    pending={}
    for name,pin in reg['before_documents'].items():
        if name=='AGENTS.md':continue
        path=ROOT/name;assert sha(path)==pin,'Concurrent edit '+name
        rel=os.path.relpath(OUT,path.parent).replace('\\','/')
        links=f'[本次候选结果]({rel}/结果说明.md)、[具体新申请（未批准）]({rel}/authorization_request.json)、[独立审查]({rel}/review.md)。'
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2第3项；任务：B2-SCOPE-19预热状态接入续训链及匹配评价候选，离线准备已完成。** '+body+'\n\n'+links+' 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        text,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,path.read_text(encoding='utf8'),count=1,flags=re.S);assert n==1
        if name=='项目进度跟踪.md':
            text=text.replace('## 当前状态\n','## 当前状态\n\n2026-10-09当前：'+summary+' '+capability+' '+scope+'\n\n以下保留此前时点：\n',1)
            text,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；SCOPE-19续训入口离线候选完成 | [结果]({rel}/结果说明.md) | SCOPE18组件恢复通过；新训练链恢复与9回合／2000批运行待批准 |',text,flags=re.M);assert n==1
            tasks=[('1 开发适用性','四个固定联合开发点保持，完整连续范围仍待'),('2 统一闭环/SAC接口','封套到训练链适配已实现，真实链保存／恢复未运行'),('3 动态闭环/成本',scope),('4 B1','既有成果保留，不扩大验收'),('5 B2与批量评价','F0四点继承核对通过；F2000匹配评价与独立恢复复现待新运行'),('6 普通残差SAC','复用19300行预热，四个在线回合逐次500批候选实现；当前路线正式更新0'),('7 阶段与进展约束','仍在B.2第3项，完整B.2/C未验收'),('8 正式证据与展示','19项离线检查及来源／审查证据；独立测试0，覆盖缺口保留')]
            text=section(text,'## 原八项任务对应','| 原任务 | 当前对应 |\n|---|---|\n'+'\n'.join(f'| {a} | {b} |' for a,b in tasks))
            start=text.index('## 当前风险和准入门');end=text.index('下表保留历史限制',start)
            text=text[:start]+'## 当前风险和准入门\n\n'+limits+'\n\n'+next_task+'\n\n'+text[end:]
            text=section(text,'## 下一项交付',next_task+'\n\n'+scope+'\n\n'+links)
            text+='\n### 2026-10-09｜B2-SCOPE-19预热状态接入续训链\n\n'+body+'\n\n'+links+' 本交付阶段结束后暂停汇报。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            text=text.replace('## 快速查找\n\n','## 快速查找\n\n当前续训候选：[B2-SCOPE-19]('+rel+'/结果说明.md)。\n\n',1)
            text=text.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n### B2-SCOPE-19｜预热状态接入续训链（2026-10-09）\n\n'+body+'\n\n'+links+'\n\n使用：run_pilot.py默认只读；新执行须另有绑定候选的grant。\n\n',1)
        elif name=='研究推进计划_当前版.md':
            start=text.index('### B.2 小规模学习与评价包');end=text.index('\n1. 先在',start)
            text=text[:start]+'### B.2 小规模学习与评价包\n\n2026-10-09当前：'+summary+' '+capability+' '+next_task+' '+scope+' 以下原阶段要求保留。\n'+text[end:]
        elif name.startswith('deliverables/'):
            adds={'## 一、本月综合摘要':body,'## 二、关键数字与证据':table+'\n'+links,'## 三、负结果与限制':limits+' 旧文件访问／导入误拦截失败保持，候选准备不增加效果证据。',
                  '## 四、图表与讲稿':'拟执行顺序：旧19300行预热 → 实际训练链完整恢复／保存 → 独立reader核对 → 在线J01至J04（各500批）→ F2000四点评价 → 独立恢复同点物理复现。\n\n讲稿：“仍在B.2第3项，已把预热数据接入续训候选并完成离线审查。下一次可以复用原初始评价和预热，新增9个回合完成2000批短训及匹配评价。当前尚未开训，也没有新的策略收益结论。”'}
            for h,b in adds.items():assert text.count(h)==1;text=text.replace(h+'\n',h+'\n\n'+b+'\n\n以下保留前轮时点：\n',1)
            text=section(text,'## 五、下一项',next_task+'\n\n'+scope+'\n\n'+limits)
            text+='\n### 2026-10-09｜B2-SCOPE-19来源记录\n\n'+body+'\n\n'+links+'\n'
        pending[name]=text
    for name,text in pending.items():(ROOT/name).write_text(text,encoding='utf8')
    after={}
    for name in reg['before_documents']:
        dst=OUT/'document_snapshots'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);after[name]=sha(dst)
    write(OUT/'document_update.json',dict(after_documents=after,rolling_documents_may_advance=True))
    print('Five current project documents updated; six snapshots saved.')

if __name__=='__main__':main()
