"""Update five rolling documents; preserve prior stage records and snapshots."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,re,shutil,json
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];REL=OUT.relative_to(ROOT).as_posix()
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
def read(p):return json.loads(p.read_text(encoding='utf8'))
def main(final):
    stamp=datetime.now(timezone(timedelta(hours=8))).isoformat(timespec='seconds')
    if final:
        a=read(OUT/'assessment.json');num=f"新增{a['attempts']}/28动态，完成{a['completed']}，累计{a['cumulative']}/168；正式更新尝试{a['formal_update_attempts']}，完成{a['formal_updates']}/4000（F{a['per_branch_updates']['F50']}/S{a['per_branch_updates']['S50']}）；余{a['unused_closed']}动态与未尝试批量关闭，不结转。发布{a['published_transitions']}条经验。"
        conclusion='137维学习链准入通过，有限pilot按实际结果收口'
        if a['status']=='complete':nexttext='冻结本轮方法与检查点；先核对开发继续信号，再登记未用评价范围和独立重复，达到工程学习/评价验收后才审查B.2。'
        else:nexttext='本轮停止点已定位：零残差搜索基线已不可继续，过滤归零仍发出该基线。先补共同SEARCH边界可行性回退，再用此反例离线验证并登记新的少量动态；不重启本轮、不补26动态/4000批。'
        signal='无法判断，矩阵不完整' if a['pilot_signal'] is None else str(a['pilot_signal'])
        facts=f"420项相关离线检查与独立数值完整恢复通过。状态{a['status']}，整轮已停止；{a['control_cycles']}控制周期/{a['physical_substeps']}物理子步，实际策略调用{a['policy_calls']}。开发继续信号：{signal}。实际问题：{a['error'] or a['audit_errors'] or '见各分支保护与任务结果'}。"
        if a['formal_updates']==0:facts+=' F负Y预热成功，S负Y预热SEARCH_REFERENCE_LIMIT；两者有效/停稳/无硬保护，S拒绝入池。尚未正式学习，不是已训练策略失效。'
    else:
        pin=read(OUT/'qualification_pin.json')['sha256'];conclusion='137维学习链准入通过，有限F/S pilot已启动'
        num='实际动态/正式更新以一次性账本为准；本轮登记上限28动态/4000批，累计起点140、上限168。'
        facts=f'新零更新网络同seed、共同几何/B2/连续性层，F与S按偏置点交替。已通过修复后受检源码绑定、CPU学习/原生运行时绑定及独立进程完整恢复；资格摘要{pin}。'
        nexttext='先独立读取两组完整零状态，随后4预热+4在线/2000批+5冻结开发评价+1代表复现/分支；合格硬保护停该分支，共同错误停整轮。授权覆盖此有限pilot，自动跟踪仍PAUSED。'
    limits='学习链实现/数值恢复通过不等于随机动作安全、学习收益或论文方法优于基线。五点是已使用开发点；独立测试0、多种子/硬件未做，B.2尚未验收。代表复现不增加性能样本。'
    text=f'**{conclusion}（{stamp[:16]}）。** {num}\n\n{facts}\n\n{limits}\n\n下一项：{nexttext} [证据与使用]({REL}/结果说明.md)、[审查/修复]({REL}/review.md)、[账本]({REL}/run/ledger.json)。'
    for name in DOCS:
        p=ROOT/name;backup=OUT/'before_documents'/name;backup.parent.mkdir(parents=True,exist_ok=True)
        if not backup.exists():shutil.copy2(p,backup)
        original=p.read_text(encoding='utf8');body=text.replace(']('+REL,'](../../../'+REL) if name.startswith('deliverables/') else text
        block='<!-- v4-learning-pilot-current -->\n'+body+'\n<!-- /v4-learning-pilot-current -->'
        if '<!-- v4-learning-pilot-current -->' in original:
            original=re.sub(r'<!-- v4-learning-pilot-current -->.*?<!-- /v4-learning-pilot-current -->',lambda _:block,original,count=1,flags=re.S)
        else:
            marker='## 当前状态' if name==DOCS[1] else '## 一、本月综合摘要' if name==DOCS[4] else None
            pos=original.index(marker)+len(marker) if marker else original.index('\n')
            original=original[:pos]+'\n\n'+block+'\n\n以下保留前序时点记录，其下一项以上述最新状态为准。\n'+original[pos:]
        if name==DOCS[1]:
            original=re.sub(r'^\| B\.1 接口与训练准入包 .*$',f'| B.1 接口与训练准入包 | 137维新学习链准入通过；实际执行见PC-04 | [证据]({REL}/结果说明.md) | 权限/回放/优化/完整恢复通过不等于策略收益 |',original,flags=re.M)
            original=re.sub(r'^\| B\.2 小规模学习与评价包 .*$',f'| B.2 小规模学习与评价包 | 未验收；有限pilot'+('已收口' if final else '执行中')+f' | [PC-04]({REL}/结果说明.md) | 尚缺完整固定评价/未用范围独立评价与重复证据 |',original,flags=re.M)
            updates={'2 统一闭环/SAC接口':'137维学习链/权限/回放/优化器及完整检查点准入通过，实际结果见PC-04',
                '3 动态闭环/成本':num,'6 普通残差SAC':('新任务正式更新0；预热因共同参考错误停止，不能判断学习收益' if final and a['formal_updates']==0 else '新零起点有限pilot'+('收口；收益按实测判定' if final else '执行中，不声称有效')),
                '7 阶段与进展约束':'F与仅SEARCH的S公平同起点对照，未证明新方法收益','8 正式证据与展示':'本轮学习证据见PC-04；未用独立测试、多种子和论文收益未完成'}
            for label,value in updates.items():original=re.sub(r'^\| '+re.escape(label)+r' \|.*$',f'| {label} | {value} |',original,flags=re.M)
            start=original.index('## 下一项交付');end=original.find('\n## ',start+1)
            original=original[:start]+'## 下一项交付\n\n'+nexttext+f' [PC-04]({REL}/结果说明.md)。\n'+(original[end:] if end>=0 else '')
            risk=original.index('## 当前风险和准入门')+len('## 当前风险和准入门');table=original.index('| 项目 | 当前事实 | 解除条件 |',risk)
            original=original[:risk]+'\n\n当前风险：137维学习链已准入；SEARCH边界可行性回退不足导致本轮停止，未开始正式学习。固定开发评价/独立评价未完成；最大规模读取成本、刚性模型外推及论文收益仍未证明。\n\n下表保留历史限制；最新下一项见上文。\n\n'+original[table:]
            if final and '｜137维学习链与有限pilot收口' not in original:original=original.replace('## 追加式阶段记录\n\n',f'## 追加式阶段记录\n\n### {stamp[:16]}｜137维学习链与有限pilot收口\n\n{text} [10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n\n',1)
        if name==DOCS[2] and final and '### PC-04｜' not in original:original=original.replace('## 基线与接口交付\n\n',f'## 基线与接口交付\n\n### PC-04｜137维学习链准入与有限pilot（{stamp[:10]}）\n\n{text} 使用runner的一次性资格/账本；已领取目录禁止再次执行。\n\n',1)
        if name==DOCS[4]:
            original=re.sub(r'^统计截至：.*?。',f'统计截至：{stamp[:16]}（北京时间）。',original,count=1,flags=re.M)
            if final and '｜[PC-04结果]' not in original:original=original.replace('## 六、来源记录\n\n',f'## 六、来源记录\n\n{stamp[:16]}｜[PC-04结果](../../../{REL}/结果说明.md)、[核对](../../../{REL}/assessment.json)、[审查](../../../{REL}/review.md)。{num}\n\n',1)
        p.write_text(original,encoding='utf8',newline='\n')
    report=f'''# 137维学习链准入与有限F/S pilot

{text.replace(REL+'/','')}

实现：新137维网络、整回合审核/发布、critic边界16行/精确终末返回、actor均匀采样和完整状态原子检查点。F允许INSERT/SEARCH，S仅SEARCH；两组同零网络/seed2026092716，学习率3e-4、CPU线程1、每批256、100ms均匀预热。旧权重/经验/120维回放未复用。

准入证据：verification.txt/json/xml绑定实际受检源码；review.json保存唯一独立审查版本、5项Important的一轮修复差异与验证版本；probe_v2保存实际预热流、随机下一动作、采样、下一更新的独立进程完整恢复。probe旧版本保留，未混作最终证据。

一次性执行：先领取run目录，逐回合登记；完整停稳、独立审核后发布，500批只在回合边界。逐批尝试和结果fsync保存，未决/失败不重试。保护后该分支停止，另一分支只在共同检查仍通过时按既定额度继续；无效/参考/源/保存/读取错误停整轮。评价样本不入池，冻结末次2000检查点；独立代表复现比较完整轨迹，并计入28额度。

暂缓Minor：400行数值完整恢复没有测量116000行最大规模的读取成本；独立读取预登记300秒，超限是新问题并停止，不补跑。资格与实测结果不同，所有缺失与失败保留。

运行入口：tools.validation.run_v4_learning_pilot，--qualify生成资格，--execute必须给已绑定SHA。当前目录只能领取一次，不能重启或补用关闭余量。自动跟踪PAUSED。源码与原始档案封存后可只读复核；不能把开发继续信号直接当论文发表条件。

[计划](../../../docs/superpowers/plans/2026-10-06-v4-learning-pilot.md)、[配置](configuration.json)、[资格](qualification.json)、[独立数值恢复](probe_v2/result.json)、[审查](review.md)、[实际账本](run/ledger.json)。
'''
    if final:report+='\n[停止点诊断与下一方案](诊断与下一步.md)、[参考独立重算](reference_diagnosis.json)。后者证明本例预测准确，但当前归零回退不足；没有修改已冻结执行源或继续训练。\n'
    (OUT/'结果说明.md').write_text(report,encoding='utf8')
    (OUT/'closeout_context.json').write_text(json.dumps(dict(stamp=stamp,final=final,conclusion=conclusion,numbers=num,facts=facts,limits=limits,next_text=nexttext),ensure_ascii=False,indent=2),encoding='utf8')
    print(conclusion)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--final',action='store_true');main(p.parse_args().final)
