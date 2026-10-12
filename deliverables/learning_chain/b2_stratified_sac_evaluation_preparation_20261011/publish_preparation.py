"""Update rolling documents and snapshots after tests and review; no computation grant."""
from pathlib import Path
import re,shutil,sys,subprocess
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sac_scope import OUT,ROOT,read,write,sha,now

def publish():
    q=read(OUT/'qualification_candidate.json')
    if not (q['offline_checks_passed'] and q['fresh_review_completed']):raise PermissionError('Final checks/review must finish first')
    tests=read(OUT/'offline_tests.json')['passed_tests'];bound=len(read(OUT/'source_binding.json')['files'])
    rel=OUT.relative_to(ROOT).as_posix();report=rel+'/结果说明.md'
    status=f'**2026-10-11｜当前阶段B.2第3项；任务：冻结F0/F2000分层评价入口实现与离线核验，已完成。**'
    body=f'''{status}

已实现独立数值门、冻结演员部署、42单元固定顺序与12+30动态准入门；{tests}项关联标准库测试通过，一次新上下文审查及修复完成，绑定{bound}来源，旧529封存成员和200工具源保持。这里只验收入口实现与离线交付；真实张量读取、策略调用和新物理回合均0。

既有纯B2 25/25功能成功、附加精度15/25保持；F0/F2000旧四点评价各4份只读复用。开发比较共75单元=33复用+42待执行；32帧旧观测已登记，数值动作一致性尚未实测。前12个新评价全部保留并兼作非零动态预检，余30仅在审核通过后继续，普通任务失败按26s计分。

累计动态279，自动跟踪PAUSED，独立测试0；旧预算关闭，无新数值/物理/训练准入，完整B.2/C未验收。固定演员离散点审核不升级连续域或训练资格，旧3处接触覆盖缺口保留。

下一项（待开始）：单独取得32帧/64次调用、2张量读取、2演员及2原SACPolicy参照构造、600s数值门授权，验证旧动作/原路径/新部署完全一致；通过后再核对独立42回合物理授权。本次用户仅批准实现和离线检查，不执行这些计算。

强化学习保持论文主方法；B.2达到验收条件、准备进入C之前，主动提醒阶段性成果总结与汇总。

[本次入口与限制]({report})；[最近真实基线](deliverables/learning_chain/b2_stratified_zero_baseline_execution_20261011/结果说明.md)。以下历史资料保持各自时点。
'''
    names=['项目当前入口.md','项目进度跟踪.md','研究推进计划_当前版.md','项目交付总览.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
    for name in names:
        p=ROOT/name;t=p.read_text(encoding='utf-8-sig');current=body
        if 'monthly_progress' in name:current=current.replace(']('+rel+']',']('+rel+']').replace(']('+rel+'/','](../../learning_chain/'+OUT.name+'/').replace('](deliverables/learning_chain/','](../../learning_chain/')
        t,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->','<!-- b2-scope-current -->\n'+current+'<!-- /b2-scope-current -->',t,count=1,flags=re.S)
        if n!=1:raise ValueError('Missing rolling current block '+name)
        if name=='项目进度跟踪.md':
            t=t.replace('## 当前状态\n','## 当前状态\n\n'+status+'\n\n冻结普通SAC新21点入口离线完成；数值和动态证据待新授权。当前累计279，PAUSED。\n',1)
            t=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；冻结F0/F2000分层入口离线完成 | [入口证据]({report})；25点纯B2实绩保持 | 32帧数值门、42评价、第4/5项与范围验收仍待 |',t,count=1,flags=re.M)
            mapping='''## 原八项任务对应

| 原任务 | 当前对应 |
|---|---|
| 1 开发适用性 | 纯B2新增21真实初始化保持；固定演员非零动态待12点门，连续域及旧3缺口保持 |
| 2 统一闭环/SAC接口 | 冻结actor部署与原137维/4维/F50语义已接入；旧动作数值一致性待实测 |
| 3 动态闭环/成本 | 累计279；本次新增物理/策略/张量0；42单元预约/实际成本分列且不重试 |
| 4 B1 | 既有成果保持；本次不授予新训练资格 |
| 5 B2与批量评价 | 纯B2 25/25完成；同矩阵33复用+42冻结评价待单独准入 |
| 6 普通残差SAC | 原四点2000批保持；F0/F2000分层入口完成，数值/新点评价及B.2第4/5项待；主方法须RL |
| 7 阶段与进展约束 | C暂缓；B.2完成、进入C前主动提醒汇总，再按开发数据确定RL候选 |
| 8 正式证据与材料 | 本轮入口报告、检查、来源和月报完成；独立测试0、多种子/最终测试仍待 |

'''
            t=re.sub(r'## 原八项任务对应\n.*?(?=## 当前风险和准入门)',mapping,t,count=1,flags=re.S)
            t=t.replace('## 当前风险和准入门\n','## 当前风险和准入门\n\n当前准入：入口离线实现通过不等于真实数值或非零动态通过；用户设计批准仅覆盖实现。32帧数值门与42物理包分别DRAFT；前12失败关闭剩余30，所有尝试保留。完整B.2/C未验收，无新训练准入。\n',1)
            next_text=f'## 下一项交付\n\n先核对一次新的32帧/64调用数值门授权，2张量读取、2演员和2原SACPolicy参照构造、600s，物理/更新0。通过后另行核对42回合物理包；当前不运行。\n\n[入口与预算]({report})、[当月月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。B.2达到验收、进入C前提醒成果汇总。\n\n'
            t=re.sub(r'## 下一项交付\n.*?(?=## 追加式阶段记录)',next_text,t,count=1,flags=re.S)
            t+=f'\n\n### 2026-10-11｜B.2第3项冻结SAC分层入口离线交付\n\n'+body+f'\n[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。保存六份前后文档快照。\n'
        elif name=='项目交付总览.md':
            t=t.replace('## 快速查找\n',f'## 快速查找\n\n当前B.2第3项入口：[报告]({report})、[使用与预算]({rel}/authorization_requests.json)、[只读核对]({rel}/verification_final.json)。入口实现及离线检查通过，真实演员数值/动态仍待准入。原能力稳定编号不变。\n',1)
            t+=f'\n\n### 2026-10-11｜冻结SAC分层入口维护记录\n\n{status} [使用入口与证据]({report})。{tests}项纯测试，旧529封存成员保持；本次计算0，累计279。数值门与42回合方案未授权，不构成完整B.2/C验收。\n'
        elif name=='研究推进计划_当前版.md':
            t+=f'\n\n### 2026-10-11｜B.2第3项接续安排\n\n冻结入口离线完成。顺序固定为32帧数值一致性、12点兼作预检的新评价、余30评价、75单元分层汇总，再核对B.2第4/5项。每一实际计算须独立新准入；不重开旧预算、不以功能成功筛选12点。主方法保持RL，当前不进入C；准备进入C前提醒成果总结。[本轮]({report})。\n'
        elif 'monthly_progress' in name:
            blocks={
                '## 一、本月综合摘要':f'最新截至2026-10-11：B.2第3项冻结F0/F2000分层入口离线完成，{tests}项关联测试通过、一次新上下文审查完成。实际计算均0，累计279、PAUSED；入口资格与真实数值/动态资格分开。纯B2既有25/25功能与15/25附加精度保持；下一项是另准入32帧数值门。',
                '## 二、关键数字与证据':f'| 最新离线入口 | 数量与状态 |\n|---|---|\n| 关联纯测试/来源 | {tests}通过 / {bound}绑定 |\n| 历史封存 / 共同工具 | 529成员 / 200工具保持 |\n| 参照观测 | 32帧已登记，真实一致性未测 |\n| 开发比较 | 75单元=33复用+42待执行；前12兼作预检 |\n| 本次实绩 | 新物理/张量/策略/更新0；累计279 |',
                '## 三、负结果与限制':'最新限制：元数据与字节哈希不能证明新部署动作一致；离线假会话检查不能证明实际非零动态适用性或Windows监督路径已运行。旧3处接触覆盖缺口、完整B.2/C未验收保持。纯B2功能25/25成功，不能宣称传统方法功能失败率高；附加精度/余量问题与真实失败分列。旧SCOPE20清单误读的假报警已更正，139/139哈希和大小一致。',
                '## 四、图表与讲稿':'本轮流程：来源锁定 → 32帧数值门（待准入） → 前12固定评价兼作动态预检（待准入） → 余30（条件继续） → 75单元分层对照。讲稿：“我们仍在B.2第3项，已接通冻结普通SAC的共同评价入口，但没有新增训练或评价结果。先验证部署动作与旧策略一致，再检查非零动态；所有失败和尝试都保留。”现有25点基线图表保持。',
                '## 五、下一项':'下一项先取得32帧/64次调用数值门新授权：2张量读取、2演员、2原SACPolicy参照构造，600秒，物理/更新0。通过后才核对42回合独立物理授权，前12结果全部纳入、失败关闭余30。完整B.2到进入C前主动提醒阶段汇总。'}
            for header,value in blocks.items():
                if header not in t:raise ValueError('Missing monthly section '+header)
                t=t.replace(header+'\n',header+'\n\n'+value+'\n',1)
            t+=f'\n\n### 2026-10-11｜冻结F0/F2000分层入口离线实现来源\n\n[入口报告](../../learning_chain/{OUT.name}/结果说明.md)、[最终核对](../../learning_chain/{OUT.name}/verification_final.json)、[未授权请求](../../learning_chain/{OUT.name}/authorization_requests.json)。本次只完成入口实现，真实计算0，累计279，B.2/C未验收。\n'
        p.write_text(t,encoding='utf-8',newline='')
    before=read(OUT/'before_state.json');docpins={}
    for name in before['documents']:
        p=OUT/'after_documents'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p);docpins[name]=sha(p)
    def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,stderr=subprocess.DEVNULL)
    write(OUT/'after_state.json',dict(at=now(),documents=docpins,branch=git('branch','--show-current').decode().strip(),
        head=git('rev-parse','HEAD').decode().strip(),uncommitted_entries=len([r for r in git('status','--porcelain=v1','-z').split(b'\0') if r]),
        before_uncommitted_entries=before['uncommitted_entries'],prior_tools_unchanged=200,new_physics=0,tensor_loads=0,policy_calls=0))
    print({'updated_documents':5,'snapshot_pairs':6,'new_computation':0})

if __name__=='__main__':publish()
