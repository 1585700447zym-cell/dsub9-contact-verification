"""Integrate the actual failed numeric attempt into the five rolling project documents."""
from pathlib import Path
import os,re,shutil,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
KIT=HERE.parent/'b2_warm_reconstruction_preparation_20261009';sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha

def section(text,heading,body):
    text,n=re.subn('('+re.escape(heading)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+body.rstrip()+'\n',text,count=1,flags=re.S)
    assert n==1;return text

def main():
    if (HERE/'document_update.json').exists():raise FileExistsError('Do not overwrite published evidence')
    reg=read(HERE/'launch_registration/registration.json');d=read(HERE/'failure_diagnosis.json');s=read(HERE/'supervisor.supervisor.json')
    assert read(HERE/'review_resolution.json')['status']=='RESOLVED'
    assert d['status']=='CONFIRMED_IMPORT_GUARD_FALSE_POSITIVE' and d['process_exit_confirmed']
    summary=f'B2-SCOPE-16按明确批准执行一次恢复数值门，实际监督用时{s["wall_seconds"]:.2f}秒，在导入阶段失败并关闭。数值恢复未通过，原4份预热经验尚未完成本轮张量重建。'
    cause='根因已由原始异常栈、源码依赖链与标准库复现确认：NoPhysics按tools.dynamics整个目录拦截，误拒绝action.py依赖的纯NumPy工具tools.dynamics.safety。此前61项离线测试通过，但漏查真实学习依赖链与拦截规则的兼容性；不能再把该测试结果当成可运行证明。这是本次首先观察到的直接阻塞，修正它仍不能推定后续恢复链可用。'
    scope='科学运行时导入已开始；学习器构造、检查点读取、预测、保存、旧档案回放重建、新物理及优化更新实际均0。parent入口已进入，reader未启动；无新检查点。拥有的进程树与启动器退出已确认，账本CLOSED、授权CLOSED_ERROR收口，未用次数全部关闭、不结转、不重试。累计动态245，自动跟踪PAUSED。'
    limits='当前仍在B.2第3项“普通SAC训练与真实任务评价”；SCOPE13原F0评价4＋预热4成功、正式更新0及失败记录保留。仅四个固定±75μm／±0.25°开发点，原3处逐profile覆盖缺口与事后开发覆盖修订仍在；完整B.2/C未验收，独立测试0。当前没有数值或训练执行准入。'
    next_task='下一项优先离线修正导入边界：逐个核对并允许确实只做数值处理的必要依赖，继续拒绝MuJoCo、物理环境和仿真执行模块；补上真实传递依赖链的兼容性反例。修复应另存新候选、保留旧封存，完成相关检查后再提出新的数值执行申请；本次关闭的授权不重开。'
    body='\n\n'.join((summary,cause,scope,limits,next_task))
    table='| 本轮项目 | 实际结果 |\n|---|---|\n'
    table+=f'| 正式数值入口 | 1次，导入失败；监督{s["wall_seconds"]:.2f}秒 |\n'
    table+='| 模型构造／张量读取／确定性预测 | 0／0／0 |\n| 保存／旧档案重建 | 0／0 |\n| 新物理／优化更新／新经验 | 0／0／0 |\n| 独立reader／新检查点 | 未启动／未生成 |\n| 进程退出／授权关闭 | 已确认／已关闭全部未用次数 |\n| 累计动态／完整B.2、C验收 | 245／均未验收 |\n'
    report='# B2-SCOPE-16｜恢复数值验证导入失败收口\n\n当前阶段：B.2第3项；任务：一次批准的恢复数值验证已停止并完成失败收口，完整数值恢复未通过。\n\n'+body+'\n\n## 实际执行与证据\n\n'+table
    report+='\n本轮使用原封存SCOPE15入口，未改其代码或校验值。新的单次grant依据用户对具体申请的“批准”登记；新claim与本次输出目录绑定。失败发生在numeric_state导入时，NumericState对象尚未创建。计数是在每项实际数值操作之前递增，因此本次零计数与异常位置、reader未启动和检查点不存在相互吻合。\n\n'
    report+='依赖链：`numeric_state → v4_sac → audited_replay → action → tools.dynamics.safety`。safety.py只导入`__future__`、`numpy`、`numpy.typing`，包含数值限幅和力矩参考点换算，未导入MuJoCo。失败规则却拒绝所有`tools.dynamics.*`。诊断仅运行标准库AST检查和原NoPhysics判定函数，不重新导入科学运行时或重试原门。\n\n'
    report+='启动辅助脚本最初把ROOT层级向上多取一级，在grant、claim及运行输出生成前报ModuleNotFoundError；已保留原脚本和记录，修正后正式数值入口只进入一次。运行日志另有Matplotlib用户缓存写入警告，最终致命异常为上述NoPhysics PermissionError；两者不混为同一原因。\n\n'
    report+='原61项离线测试的历史通过记录保留。本次真实运行补充了其未覆盖的负结果，应优先补完整依赖链验证，不能仅删除整个物理拦截器来取得通过。\n\n'
    report+='证据：[异常栈](supervisor.log)、[监督退出](supervisor.supervisor.json)、[实际账本](counter.json)、[授权关闭](authorization_closure.json)、[根因复现](failure_diagnosis.json)、[审查](review.md)、[交付核验](verification.json)。\n'
    (HERE/'结果说明.md').write_text(report,encoding='utf8')
    pending={}
    for name,pin in reg['before_documents'].items():
        if name=='AGENTS.md':continue
        p=ROOT/name;assert sha(p)==pin,'Concurrent edit '+name
        rel=os.path.relpath(HERE,p.parent).replace('\\','/')
        links=f'[失败收口]({rel}/结果说明.md)、[根因证据]({rel}/failure_diagnosis.json)、[关闭记录]({rel}/authorization_closure.json)。'
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2第3项；任务：B2-SCOPE-16恢复数值验证已失败关闭并收口。** '+body+'\n\n'+links+' 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        text,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,p.read_text(encoding='utf8'),count=1,flags=re.S);assert n==1
        if name=='项目进度跟踪.md':
            text=text.replace('## 当前状态\n','## 当前状态\n\n2026-10-09当前：'+summary+' '+cause+' '+scope+'\n\n以下保留此前时点：\n',1)
            text,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；SCOPE-16数值入口导入失败关闭 | [结果]({rel}/结果说明.md) | 模型构造／恢复均未开始；原8物理回合成功，正式更新0；先修导入边界 |',text,flags=re.M);assert n==1
            tasks=[('1 开发适用性','四点联合开发范围保持，不扩展完整范围'),('2 统一闭环/SAC接口','恢复入口导入边界误拦截，真实依赖兼容性待修'),('3 动态闭环/成本','本轮新增物理0，累计245；数值运行失败关闭'),('4 B1','已有成果保留，不扩大验收'),('5 B2与批量评价','SCOPE13初始评价4/4、预热4/4成功；训练后评价未执行'),('6 普通残差SAC','SCOPE16在构造前导入失败；新检查点、完整恢复均无；正式更新0'),('7 阶段与进展约束','仍在B.2第3项；C物理接入暂缓'),('8 正式证据与展示','完整失败栈与关闭证明保留；独立测试0；覆盖缺口保留')]
            text=section(text,'## 原八项任务对应','| 原任务 | 当前对应 |\n|---|---|\n'+'\n'.join(f'| {a} | {b} |' for a,b in tasks))
            a=text.index('## 当前风险和准入门');b=text.index('下表保留历史限制',a)
            text=text[:a]+'## 当前风险和准入门\n\n'+limits+'\n\n'+cause+'\n\n'+next_task+'\n\n'+text[b:]
            text=section(text,'## 下一项交付',next_task+'\n\n'+scope+'\n\n'+links)
            text+='\n### 2026-10-09｜B2-SCOPE-16恢复数值门导入失败收口\n\n'+body+'\n\n'+links+' 本交付阶段结束后暂停汇报。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            text=text.replace('## 快速查找\n\n','## 快速查找\n\n当前恢复门执行结果：[B2-SCOPE-16失败收口]('+rel+'/结果说明.md)。\n\n',1)
            text=text.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n### B2-SCOPE-16｜恢复门导入失败收口（2026-10-09）\n\n'+body+'\n\n'+links+'\n\n使用：只读核验诊断、账本和关闭记录；旧入口不得再次执行。\n\n',1)
        elif name=='研究推进计划_当前版.md':
            a=text.index('### B.2 小规模学习与评价包');b=text.index('\n1. 先在',a)
            text=text[:a]+'### B.2 小规模学习与评价包\n\n2026-10-09当前：'+summary+' '+cause+' '+next_task+' '+scope+' 以下原阶段要求保留。\n'+text[b:]
        elif name.startswith('deliverables/'):
            additions={'## 一、本月综合摘要':body,'## 二、关键数字与证据':table+'\n'+links,'## 三、负结果与限制':cause+' '+limits,
                '## 四、图表与讲稿':'依赖链：恢复入口 → SAC → 回放 → 动作工具 → safety数值工具（被目录级拦截误拒绝）。\n\n讲稿：“仍在B.2第3项。本次实际恢复验证在依赖导入阶段失败，未构造模型或读取检查点。已有预热档案保留；先修复导入兼容性，数值恢复和正式训练仍未完成。”'}
            for h,b in additions.items():assert text.count(h)==1;text=text.replace(h+'\n',h+'\n\n'+b+'\n\n以下保留前轮时点：\n',1)
            text=section(text,'## 五、下一项',next_task+'\n\n'+scope+'\n\n'+limits)
            text+='\n### 2026-10-09｜B2-SCOPE-16来源记录\n\n'+body+'\n\n'+links+'\n'
        pending[name]=text
    for name,text in pending.items():(ROOT/name).write_text(text,encoding='utf8')
    after={}
    for name in reg['before_documents']:
        dst=HERE/'document_snapshots'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);after[name]=sha(dst)
    write(HERE/'document_update.json',dict(after_documents=after,rolling_documents_may_advance=True))
    print('Failure integrated into five current documents; six snapshots saved.')

if __name__=='__main__':main()
