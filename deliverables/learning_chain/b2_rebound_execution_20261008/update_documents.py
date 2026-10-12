"""One-time evidence-based closeout of the five established rolling documents."""
import json
from pathlib import Path
import re

ROOT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT=ROOT/'deliverables/learning_chain/b2_rebound_execution_20261008'
REL='deliverables/learning_chain/b2_rebound_execution_20261008/'
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']

def section(text,heading,end_marker,body):
    start=text.index(heading)+len(heading); end=text.index(end_marker,start)
    return text[:start]+'\n\n'+body+'\n\n'+text[end:]

def lead(text,heading,body):
    start=text.index(heading)+len(heading); rest=text[start:].lstrip('\n')
    return text[:start]+'\n\n'+body+rest[rest.index('\n\n'):]

def main():
    assert not (OUT/'document_snapshots').exists()
    s=json.loads((OUT/'report_summary.json').read_text(encoding='utf-8'))
    c=json.loads((OUT/'authorization_closure.json').read_text(encoding='utf-8')); t=c['actual']
    summary,evidence,limit,next_text=[s[k] for k in ('summary','evidence','limit','next')]
    assert c['status'].startswith('CLOSED_')
    edited={}
    for name in DOCS:
        raw=(ROOT/name).read_bytes(); assert raw==(OUT/'before_documents'/name).read_bytes(),name
        text=raw.decode('utf-8').replace('\r\n','\n'); prefix='../../../' if name.startswith('deliverables/') else ''
        links=(f'[本轮实际结果]({prefix}{REL}结果说明.md)、[实耗与授权关闭]({prefix}{REL}authorization_closure.json)、'
               f'[固定矩阵审核]({prefix}{REL}run/assessment.json)、[路线决定]({prefix}{REL}路线决定.md)')
        body=summary+'\n\n'+evidence+'\n\n'+limit+'\n\n'+next_text
        block=(f'<!-- b2-scope-current -->\n**2026-10-08｜当前阶段B.2；任务：姿态预检实际执行与结果收口，已完成。** '
               +body+'\n\n'+links+'。以下旧阶段保留当时状态，其旧下一项不代表当前授权。\n<!-- /b2-scope-current -->')
        text,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda _:block,text,count=1,flags=re.S); assert n==1
        if name=='项目进度跟踪.md':
            text=section(text,'## 当前状态','下方保留此前阶段的日期和原结论',body)
            replacements={
             '| B.2 小规模学习与评价包 |':f'| B.2 小规模学习与评价包 | 位置里程碑完成；本轮姿态预检已执行，完整范围待验收 | [B2-SCOPE-06实际结果]({REL}结果说明.md) | 审核{c["registered_dynamic_audit_passes"]}/16，路线{s["route"]}；匹配训练、恢复与完整范围仍缺 |',
             '| 1 开发适用性 |':f'| 1 开发适用性 | 原63份PC-06/07/09零倾角档案保持；本轮静态{c["registered_static_audit_passes"]}/9、动态审核{c["registered_dynamic_audit_passes"]}/16，限登记±0.25°开发点，不能外推连续域 |',
             '| 2 统一闭环/SAC接口 |':'| 2 统一闭环/SAC接口 | 修订审核器已用于本轮真实worker；记录137维观测、命令、奖励、保护与停止，脚本运行不等于SAC学习准入 |',
             '| 3 动态闭环/成本 |':f'| 3 动态闭环/成本 | 本轮{t["static_initializations"]}静态/{t["dynamic_attempts"]}动态，{t["control_cycles"]}周期/{t["physical_substeps"]}子步，累计{c["cumulative_dynamic_after"]}，学习0、未用{c["unused_dynamic_closed"]}动态关闭 |',
             '| 5 B2与批量评价 |':f'| 5 B2与批量评价 | 固定9静态/16动态分母保留，功能{c["functional_successes"]}/16、附加精度{c["strict_precision_successes"]}/16；接触、动作作用与信息差异分别审核，完整B.2/C未验收 |',
             '| 8 正式证据与展示 |':'| 8 正式证据与展示 | 本轮新grant/原始记录/审核/实耗/进程退出/路线已归档；新训练、独立测试、多种子与SAC收益0 |'}
            lines=text.splitlines()
            for marker,value in replacements.items():
                hits=[i for i,line in enumerate(lines) if line.startswith(marker)]; assert len(hits)==1,marker
                lines[hits[0]]=value
            text='\n'.join(lines)+'\n'
            text=text.replace('本轮B2-SCOPE-04完成审核器修复及旧档案回归，新增仿真/学习0；历史G失败/S旧成功与原失败账本保持。',
                              '本轮B2-SCOPE-06已执行登记姿态预检，新增学习0；历史G失败/S旧成功与原失败账本保持。',1)
            text=section(text,'## 当前风险和准入门','下表保留历史限制',limit+'\n\n'+next_text+'\n\n'
                         '原S/F 0.39%未过10%继续门、首次位置附加精度0/4与旧STOP上下文缺口保持。新的脚本预检不翻转旧学习结论；已消费grant及未用回合不恢复。')
            text=section(text,'## 下一项交付','## 追加式阶段记录',next_text+'\n\n'+limit+'\n\n'+links)
            text+=f'\n### 2026-10-08｜B2-SCOPE-06姿态预检实际执行与收口\n\n{body}\n\n{links}、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            text=lead(text,'## 快速查找',f'当前先看[B2-SCOPE-06实际预检结果]({REL}结果说明.md)和[路线]({REL}路线决定.md)。本轮新grant已消费并关闭；B2-SCOPE-05保留准备时点，旧请求不是可重复执行授权。')
            heading='## 基线与接口交付'; assert text.count(heading)==1
            text=text.replace(heading,heading+f'\n\n### B2-SCOPE-06｜姿态预检实际执行（2026-10-08）\n\n{body}\n\n{links}。'
                              '使用原始档案及审核结果只读分析；不再次调用本轮--execute，不修改旧封存。',1)
        elif name=='研究推进计划_当前版.md':
            text,n=re.subn(r'2026-10-08执行优先级更新：.*?以下原要求保留。',lambda _:'2026-10-08执行优先级更新：'+summary+' '+limit+' '+next_text+' 以下原要求保留。',text,count=1); assert n==1
        elif name.startswith('deliverables/'):
            text,n=re.subn(r'统计截至：2026-10-08（北京时间，[^\n]*?）',lambda _:'统计截至：2026-10-08（北京时间，B2-SCOPE-06姿态预检实际执行与收口）',text,count=1); assert n==1
            text=lead(text,'## 一、本月综合摘要',body.replace('\n\n',' ')+' 以下保留此前阶段摘要：')
            numbers=('| 本轮B2-SCOPE-06项目 | 实际值 |\n|---|---:|\n'
                     f'| 静态审核 | {c["registered_static_audit_passes"]}/9 |\n| 动态尝试／审核 | {t["dynamic_attempts"]}/16／{c["registered_dynamic_audit_passes"]}/16 |\n'
                     f'| 功能／附加精度 | {c["functional_successes"]}/16／{c["strict_precision_successes"]}/16 |\n| 环境创建／复位完成 | {t["case_environment_instances_completed"]}／{t["resets_completed"]} |\n'
                     f'| 周期／子步 | {t["control_cycles"]}／{t["physical_substeps"]} |\n| 整轮监督s | {c["whole_supervised_wall_seconds"]:.3f} |\n'
                     f'| 累计动态 | {c["cumulative_dynamic_after"]} |\n| 未用动态 | {c["unused_dynamic_closed"]}，关闭 |\n| 新训练／推理／发布 | 全0 |\n'
                     f'| 接触／script接触作用 | {s["metrics"]["contact_episodes"]}/16／{s["metrics"]["script_contact_effect_covered"]}/8 |')
            text=lead(text,'## 二、关键数字与证据',numbers)
            text=lead(text,'## 三、负结果与限制',limit+' 原B2-SCOPE-03审核故障、关闭15回合和后续修复回归保持各自时点。')
            text=text.replace('当前版本尚无非零初始倾角训练/评价证据；旧入口角度写死0，且初始守卫为±0.5°，原±1.5°不能直接继承。',
                              'B2-SCOPE-01审计时尚无非零初始倾角训练/评价证据；原旧入口角度写死0。本轮新增登记脚本预检，仍无非零倾角匹配SAC训练；初始守卫±0.5°与原±1.5°目标的差异仍未解除。',1)
            text=lead(text,'## 四、图表与讲稿',f'本轮使用[固定16项结果与8组对称信息表](../../../{REL}结果说明.md)。讲稿：“目前仍在B.2。'
                      f'9项静态检查后，动态审核通过{c["registered_dynamic_audit_passes"]}/16；累计{c["cumulative_dynamic_after"]}。功能成功、接触作用和可辨识性分别计证据，'
                      '完整B.2与C尚未验收，当前没有新训练准入。下一步按本轮路线先做离线分析。”')
            text=section(text,'## 五、下一项','## 六、来源记录',next_text+'\n\n'+limit)
            text+=f'\n### 2026-10-08｜B2-SCOPE-06姿态预检执行来源\n\n{body}\n\n{links}。\n'
        edited[name]=text
    for name,text in edited.items():
        (ROOT/name).write_text(text,encoding='utf-8',newline='\n')
        target=OUT/'document_snapshots'/name; target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write((ROOT/name).read_bytes())
    with (OUT/'document_snapshots/AGENTS.md').open('xb') as f:f.write((ROOT/'AGENTS.md').read_bytes())
    with (OUT/'progress.md').open('a',encoding='utf-8') as f:
        f.write('\n五份滚动文档已整合本轮实测、限制与下一项，六份执行后快照保存。\n')
    print('Updated five rolling documents and six immutable after snapshots.')

if __name__=='__main__': main()
