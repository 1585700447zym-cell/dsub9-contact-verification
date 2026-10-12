"""Update the five rolling indexes once, with before/after immutable snapshots."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

ROOT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT=ROOT/'deliverables/learning_chain/b2_joint_learning_review_20261009'
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
SUMMARY='B2-SCOPE-07离线复核8份J01～J04档案、42656周期及42664个137维观测，已完成。零残差接触信息有差异，8/8首次接触和力峰时均有残差权限；script只在每点50个SEARCH接触周期产生非零作用，未覆盖峰值当周期的非零动作。保留四个联合点作为待准入的匹配学习候选。'
COST='本轮新增物理、网络推理、训练更新和经验发布全0。实际累计动态225，自动跟踪PAUSED，旧预算关闭，无新物理或训练授权。SCOPE-06的9静态/16动态及原覆盖不足路线保持。'
LIMITS='力峰距25mN保护阈值最少0.419mN（1.676%）；小幅相关脚本不代表完整动作域，联合点恢复事件0。2468个有权限SEARCH观测的受阻时长饱和（其中2214个有接触），另3440次仅在无权限停止尾段；首次接触无裁剪不能外推全程无裁剪。脚本按工况定方向，不能证明可部署辨识或学习收益。±0.25°离散点不能验收原±1.5°目标。完整B.2/C未验收，独立测试0。'
NEXT='下一项准备B.2联合点动作域与恢复准入登记：先审查时长饱和的状态语义和既有恢复证据可继承范围，再固定最少新增缺口预检、成本与失败出口。具体方案获新授权后才执行；通过后另行登记普通SAC姿态匹配短训、共同参照及冻结评价。P01～P04保留无接触功能对照，不追加填覆盖，不扩137维或物理范围，不进入C。'

def replace_section(text,heading,body):
    pattern=r'('+re.escape(heading)+r'\n)(.*?)(?=\n## |\Z)'
    updated,n=re.subn(pattern,lambda m:m.group(1)+'\n'+body.rstrip()+'\n',text,count=1,flags=re.S)
    assert n==1,heading
    return updated

def main():
    assert not (OUT/'delivery_manifest.json').exists() and not (OUT/'document_update.json').exists()
    reg=json.loads((OUT/'registration.json').read_text(encoding='utf-8'))
    updates={}
    for name in DOCS:
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==reg['before_documents'][name],name+' changed since registration'
        t=(ROOT/name).read_text(encoding='utf-8')
        rel=os.path.relpath(OUT,(ROOT/name).parent).replace('\\','/')
        links=f'[本轮证据]({rel}/结果说明.md)、[路线决定]({rel}/路线决定.md)、[逐周期复核]({rel}/analysis.json)、[观测裁剪复核]({rel}/information_refinement.json)。'
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2；任务：联合姿态点接触信息与作用窗口离线复核，已完成。** '+SUMMARY+'\n\n'+COST+'\n\n'+LIMITS+'\n\n'+NEXT+'\n\n'+links+' 以下旧阶段保留当时状态，其旧下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        t,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,t,count=1,flags=re.S);assert n==1
        if name=='项目进度跟踪.md':
            t,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；联合点离线复核已完成 | [B2-SCOPE-07]({rel}/结果说明.md) | 保留J01～J04候选；动作域、恢复、时长饱和语义及匹配学习/冻结评价仍待 |',t,flags=re.M);assert n==1
            task_rows=[
              '1 开发适用性 | ±0.25°联合开发点有接触信息依据；P点仍为无接触对照，原±1.5°范围未验收',
              '2 统一闭环/SAC接口 | 42664个137维观测归一化复核；2468个SEARCH受阻时长饱和向量需审查语义，本轮未改接口',
              '3 动态闭环/成本 | 本轮新增动态/子步/推理/训练0，累计225；原67016周期/670160子步账本保持关闭',
              '4 B1 | 历史B1结果保持，本轮未补采或升级范围',
              '5 B2与批量评价 | 8既有J档案/42656周期离线分析；原16/16功能与附加精度结果保持，不新增成功样本',
              '6 普通残差SAC | 四个J点仅保留为待准入匹配学习候选，先补动作域和恢复缺口；无新训练准入',
              '7 阶段与进展约束 | C物理接入继续暂缓，PC-11～14保留；不把当前权限覆盖推定为C已完成',
              '8 正式证据与展示 | 作用时序、峰值余量、裁剪分类及路线已归档；新独立评价、多种子和学习收益证据仍无']
            t=replace_section(t,'## 原八项任务对应','| 原任务 | 本次核对状态 |\n|---|---|\n'+'\n'.join('| '+s+' |' for s in task_rows)+'\n\n'+COST)
            risk_start=t.index('## 当前风险和准入门');table_start=t.index('下表保留历史限制',risk_start)
            t=t[:risk_start]+'## 当前风险和准入门\n\n'+LIMITS+'\n\n'+NEXT+'\n\n原S/F 0.39%未过10%继续门、首次位置附加精度0/4与旧STOP上下文缺口保持。新离线证据不翻转旧学习结论。\n\n'+t[table_start:]
            t=replace_section(t,'## 下一项交付',NEXT+'\n\n'+LIMITS+'\n\n'+links)
            t+='\n### 2026-10-09｜B2-SCOPE-07联合姿态点离线复核\n\n'+SUMMARY+'\n\n'+COST+'\n\n'+LIMITS+'\n\n'+NEXT+'\n\n本项仅验收离线证据提取和路线决定；原封存与来源核验见本阶段verification.json。'+links+' 汇报素材同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。按协作约定阶段结束暂停汇报。\n'
        elif name=='项目交付总览.md':
            quick='当前先看[B2-SCOPE-06实际预检结果](deliverables/learning_chain/b2_rebound_execution_20261008/结果说明.md)'
            assert quick in t
            t=t.replace(quick,'当前先看[B2-SCOPE-07联合点复核]('+rel+'/结果说明.md)和[下一准入路线]('+rel+'/路线决定.md)。前轮[B2-SCOPE-06实际预检结果](deliverables/learning_chain/b2_rebound_execution_20261008/结果说明.md)',1)
            t=t.replace('当前先看[B2-SCOPE-01范围缺项与预检]','历史范围依据见[B2-SCOPE-01范围缺项与预检]',1)
            entry='### B2-SCOPE-07｜联合姿态点离线复核（2026-10-09）\n\n'+SUMMARY+'\n\n'+COST+'\n\n使用：先读结果表和路线决定，按档案ID查analysis.json及joint_cycles.csv；裁剪字段与同一时刻对照见information_refinement.json。脚本只读取封存JSON，封存后拒绝覆盖新结果，不运行仿真或学习器。\n\n'+LIMITS+'\n\n'+NEXT+'\n\n'+links+'\n\n'
            t=t.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n'+entry,1)
        elif name=='研究推进计划_当前版.md':
            h=t.index('### B.2 小规模学习与评价包');end=t.index('\n1. 先在',h)
            t=t[:h]+'### B.2 小规模学习与评价包\n\n2026-10-09执行优先级更新：'+SUMMARY+' '+LIMITS+' '+NEXT+' 以下原要求保留。\n'+t[end:]
        elif name.startswith('deliverables/'):
            inserts={
              '## 一、本月综合摘要':'截至2026-10-09：'+SUMMARY+' '+COST+'\n\n当前先推进联合点的准入缺项；此前SCOPE-06实测成功保留，不能据此开始训练。以下为此前阶段事实，历史下一项以本页当前状态为准。',
              '## 二、关键数字与证据':'| 本轮B2-SCOPE-07项目 | 实际值 |\n|---|---:|\n| 既有联合档案／周期 | 8／42656 |\n| 137维观测复核 | 42664 |\n| 接触周期／同时有权限 | 18250／15122 |\n| script非零／接触有效作用周期 | 596／200 |\n| 联合点恢复事件 | 0 |\n| 最小力峰余量 | 0.419mN，阈值的1.676% |\n| 活动SEARCH时长饱和向量 | 2468，其中接触2214 |\n| 无权限停止尾段时长饱和向量 | 3440 |\n| 新物理／推理／训练／发布 | 全0 |\n| 累计动态 | 225 |\n\n'+links+'\n\n以下为前轮实际数字：',
              '## 三、负结果与限制':LIMITS+'\n\n零残差接触信息差异不等于有噪声可辨识；script在接触前按工况指定方向，不能替代可部署学习证据。原SCOPE-06覆盖不足路线保持。以下保留前轮限制：',
              '## 四、图表与讲稿':f'本轮采用[8档案峰值时序表、4组接触脉冲表、运动配对表及裁剪分类表]({rel}/结果说明.md)。讲稿：“现在仍在B.2，四个联合点有接触信息和可作用窗口，值得保留为候选。但力峰附近的小幅动作、恢复及部分状态时长饱和尚未补清，不能直接开训。此次全为离线分析，累计225不增加；下一步先定最少缺口预检和准入方案。”\n\n以下讲稿保留前轮时点：'}
            for heading,body in inserts.items():
                assert t.count(heading)==1;t=t.replace(heading+'\n',heading+'\n\n'+body+'\n',1)
            t=replace_section(t,'## 五、下一项',NEXT+'\n\n'+LIMITS)
            t+='\n### 2026-10-09｜B2-SCOPE-07联合点离线复核来源\n\n'+SUMMARY+'\n\n'+COST+'\n\n'+LIMITS+'\n\n'+links+' 新产出分析/观测明细、路线、文档快照与封存校验；无新训练或性能样本。\n'
        else:
            assert name=='项目当前入口.md'
        assert t.count('<!-- b2-scope-current -->')==1 and 'B2-SCOPE-07' in t
        updates[name]=t
    # All preconditions and transformations complete before any rolling file write.
    for name,text in updates.items():(ROOT/name).write_text(text,encoding='utf-8')
    after={}
    for name in DOCS+['AGENTS.md']:
        path=OUT/'document_snapshots'/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,path)
        after[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT/'document_update.json').write_text(json.dumps(dict(stage_id='B2-SCOPE-07',after_documents=after,rolling_documents_may_advance=True),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Updated five rolling documents; preserved six before/after snapshots.')

if __name__=='__main__':main()
