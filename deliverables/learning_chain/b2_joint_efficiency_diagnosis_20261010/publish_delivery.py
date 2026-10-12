"""Prepare five reviewed project-document updates and preserve six snapshots."""
import argparse,os,re,shutil,sys
from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
from analyze import read,write,sha
from build_report import tables
def section(text,heading,body):
    text,n=re.subn('('+re.escape(heading)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+body.rstrip()+'\n',text,count=1,flags=re.S)
    if n!=1:raise ValueError('Missing section '+heading)
    return text
def prepare():
    if (OUT/'document_proposal.json').exists():raise FileExistsError('Preserve first proposal')
    reg=read(OUT/'registration.json');d=read(OUT/'diagnosis.json');time_table,precision_table=tables(d)
    summary='B2-SCOPE-21四点耗时与精度离线归因已完成：读取8份既有F0/F2000档案、42171周期，未新增模型／张量／推理／物理／更新／经验。'
    finding='J01增加3.096秒，其中SEARCH增加3.084秒；J02省下4.068秒，主要免去UNLOAD和SEARCH；四点平均改善2.77%未达10%。原80μm/0.5°附加精度为F0 4/4、F2000 0/4，未通过项均为XY，功能成功仍各4/4。'
    cause='J01实际搜索XY路径71.95→200.06μm、退出更晚；J01/J03/J04搜索后INSERT再漂离中心。全部启用命令预测／执行一致，权限及42171条冻结奖励复算通过；未见丢动作或搜索审核误截断。既有功能判据和奖励未纳入附加终末XY精度，这是已确认目标缺项，不是唯一学习成因。'
    limits='仍在B.2第3项“普通SAC训练与真实任务评价”。初始137维观测8档案相同，不能期待复位时首步按绝对象限区分；接触后仍有信息，不据此立即扩观测。入口状态不同，路径对照不等于演员物理反事实；critic、熵或数据顺序的唯一成因未确认。四点已用开发资料／单种子，原3处覆盖缺口及事后修订保持，完整B.2/C未验收，独立测试0。'
    scope='SCOPE20的2000更新、最终功能4/4及独立恢复一致仍有效；旧失败和3685个历史封存成员保持。累计动态254、自动跟踪PAUSED、当前无新科学执行准入；本轮不修改运行时奖励、物理、观测或成功标签，不重开旧预算。'
    next_task='下一项（待开始）：离线准备普通SAC共同精度目标与奖励一致性候选。保留137维／4维、物理和共同保护、既有功能判据；明确80μm/0.5°开发精度用途、单一终末精度奖励候选及其与10%耗时条件的并列关系，登记同版本公平对照与一次有限预算。实质目标改变先提交可审阅方案；候选未实现，不直接加训或扩展C机制。'
    body='\n\n'.join((summary,finding,cause,limits,scope,next_task));pending={}
    for name,pin in reg['before_documents'].items():
        if sha(ROOT/name)!=pin:raise ValueError('Concurrent edit '+name)
        if name=='AGENTS.md':continue
        path=ROOT/name;rel=os.path.relpath(OUT,path.parent).replace('\\','/')
        links=f'[本次离线归因]({rel}/结果说明.md)、[路线决定]({rel}/路线决定.md)、[原始诊断]({rel}/diagnosis.json)。'
        block='<!-- b2-scope-current -->\n**2026-10-10｜当前阶段B.2第3项；任务：B2-SCOPE-21四点耗时与精度离线归因，已完成。** '+body+'\n\n'+links+' 以下历史下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        text,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,path.read_text(encoding='utf8'),count=1,flags=re.S)
        if n!=1:raise ValueError('Current marker missing')
        if name=='项目进度跟踪.md':
            text=text.replace('## 当前状态\n','## 当前状态\n\n2026-10-10当前：'+summary+' '+finding+' '+scope+'\n\n以下保留此前时点：\n',1)
            text,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；SCOPE-21耗时／精度归因完成 | [结果]({rel}/结果说明.md) | SCOPE20运行链通过；效率未达10%，附加精度4/4→0/4，下一项共同目标候选 |',text,flags=re.M)
            if n!=1:raise ValueError('Capability row missing')
            tasks=[('1 开发适用性','固定四点已用开发资料；连续姿态／联合范围仍待'),('2 统一闭环/SAC接口','SCOPE20实际训练／保存／恢复通过；本轮仅分析标准库档案'),
                   ('3 动态闭环/成本','新增物理／更新0，复核既有42171周期；累计254'),('4 B1','既有成果保持，不扩大验收'),
                   ('5 B2与批量评价','F0/F2000功能各4/4；附加80μm/0.5°为4/4→0/4；无新纯B2对照'),
                   ('6 普通残差SAC','已完成2000批，但效率／精度未达预期；先准备共同精度与奖励目标候选'),
                   ('7 阶段与进展约束','C物理推进暂缓，现有成果保持；本轮未扩机制'),('8 正式证据与展示','8档案来源、阶段耗时、路径／命令／奖励／末态表已归档；单种子／独立测试0')]
            text=section(text,'## 原八项任务对应','| 原任务 | 当前对应 |\n|---|---|\n'+'\n'.join(f'| {a} | {b} |' for a,b in tasks))
            start=text.index('## 当前风险和准入门');end=text.index('下表保留历史限制',start)
            text=text[:start]+'## 当前风险和准入门\n\n'+finding+'\n\n'+limits+'\n\n'+next_task+'\n\n'+text[end:]
            text=section(text,'## 下一项交付',next_task+'\n\n'+scope+'\n\n'+links)
            text+='\n### 2026-10-10｜B2-SCOPE-21耗时与终末精度离线归因\n\n'+body+'\n\n'+links+' 同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。本交付阶段结束后暂停汇报。\n'
        elif name=='项目交付总览.md':
            text=text.replace('## 快速查找\n\n','## 快速查找\n\n最新离线归因：[B2-SCOPE-21]('+rel+'/结果说明.md)；运行链成果仍见SCOPE20。\n\n',1)
            text=text.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n### B2-SCOPE-21｜四点耗时与精度离线归因（2026-10-10）\n\n'+body+'\n\n'+links+'\n\n使用：diagnosis.json和CSV核对阶段、命令、奖励与真实位移；verify_delivery.py只读核验。analyze.py拒绝覆盖首次结果；当前不执行新候选。\n\n',1)
            text=text.replace('| 最新真实学习与冻结评价 |','| 最近实际训练与冻结评价（SCOPE20） |',1)
        elif name=='研究推进计划_当前版.md':
            start=text.index('### B.2 小规模学习与评价包');end=text.index('\n1. 先在',start)
            text=text[:start]+'### B.2 小规模学习与评价包\n\n2026-10-10当前：'+body+' 以下原阶段要求保留。\n'+text[end:]
        elif name.startswith('deliverables/'):
            text=re.sub(r'^统计截至：.*$', '统计截至：2026-10-10（北京时间，B2-SCOPE-21离线归因）。实时状态见[项目进度跟踪](../../../项目进度跟踪.md)，此前月报保留历史口径。',text,count=1,flags=re.M)
            numbers='| 本轮核对项 | 实际值 |\n|---|---|\n| 既有档案／周期 | 8／42171 |\n| 新物理／模型／张量／前向／优化／经验 | 全0 |\n| 累计动态／跟踪 | 254／PAUSED |\n| 功能成功F0/F2000 | 各4/4 |\n| 附加80μm/0.5°F0/F2000 | 4/4／0/4（XY未通过） |\n| 训练后耗时改善 | 2.77%，未达10% |\n'
            additions={'## 一、本月综合摘要':body,'## 二、关键数字与证据':numbers+'\n'+time_table+'\n'+precision_table+'\n'+links,
                '## 三、负结果与限制':finding+'\n\n'+limits+'\n\n'+cause,
                '## 四、图表与讲稿':time_table+'\n'+precision_table+'\n讲稿：“仍在B.2第3项，普通SAC运行链已经完成，但四点用时收益被一快一慢抵消，附加精度从4/4降到0/4。已有功能成功口径不追改；下一项先准备共同精度目标和奖励一致性方案，不直接追加训练。”'}
            for heading,addition in additions.items():
                if text.count(heading)!=1:raise ValueError('Monthly section missing')
                text=text.replace(heading+'\n',heading+'\n\n'+addition+'\n\n以下保留前轮时点：\n',1)
            text=section(text,'## 五、下一项',next_task+'\n\n'+scope+'\n\n'+limits)
            text+='\n### 2026-10-10｜B2-SCOPE-21离线归因来源\n\n'+body+'\n\n'+links+'\n'
        pending[name]=text
    proposed={}
    for name,text in pending.items():
        dst=OUT/'document_proposals'/name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_text(text,encoding='utf8');proposed[name]=sha(dst)
    write(OUT/'document_proposal.json',dict(stage_id='B2-SCOPE-21',before_documents=reg['before_documents'],proposed_documents=proposed,
          report_sha256=sha(OUT/'结果说明.md'),route_sha256=sha(OUT/'路线决定.md'),publisher_sha256=sha(__file__)))
    print('Prepared five project-document proposals; current documents unchanged.')
def publish():
    if (OUT/'document_update.json').exists():raise FileExistsError('Preserve published snapshots')
    proposal=read(OUT/'document_proposal.json');review=read(OUT/'review_resolution.json')
    if review['status']!='RESOLVED' or review['open_critical'] or review['open_important']:raise PermissionError('Unresolved review')
    if sha(OUT/'document_proposal.json')!=review['document_proposal_sha256']:raise PermissionError('Reviewed proposal identity changed')
    for key,path in (('report_sha256',OUT/'结果说明.md'),('route_sha256',OUT/'路线决定.md'),('publisher_sha256',Path(__file__))):
        if sha(path)!=proposal[key]:raise ValueError('Reviewed publication changed')
    for name,pin in proposal['before_documents'].items():
        if sha(ROOT/name)!=pin:raise ValueError('Concurrent edit '+name)
    for name,pin in proposal['proposed_documents'].items():
        if sha(OUT/'document_proposals'/name)!=pin:raise ValueError('Reviewed proposal changed')
    for name in proposal['proposed_documents']:shutil.copyfile(OUT/'document_proposals'/name,ROOT/name)
    after={}
    for name in proposal['before_documents']:
        dst=OUT/'document_snapshots'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);after[name]=sha(dst)
    write(OUT/'document_update.json',dict(stage_id='B2-SCOPE-21',after_documents=after,rolling_documents_may_advance=True,next_task_started=False))
    print('Published five current documents; six snapshots preserved.')
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','publish'));a=p.parse_args();prepare() if a.mode=='prepare' else publish()
