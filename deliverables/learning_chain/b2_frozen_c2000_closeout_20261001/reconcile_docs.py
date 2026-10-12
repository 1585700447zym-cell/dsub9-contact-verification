"""Refresh current rolling status before report_result snapshots it; no simulation."""
import datetime,re
from zoneinfo import ZoneInfo
import night_contract as N
from report_result import load_assessments

def main():
    results=load_assessments(N.HERE)
    if not results:raise ValueError('Audited results required')
    for a in results:N.P.verify_files(a['result_inputs_sha256'])
    date=datetime.datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
    total=sum(a['accounting']['new_dynamic_starts'] for a in results)
    evidence='deliverables/learning_chain/b2_frozen_c2000_closeout_20261001/result_analysis/结果说明.md'
    design='deliverables/learning_chain/b2_frozen_c2000_closeout_20261001/下一阶段最小方案.md'
    rowtext='；'.join(f"{a['variant']}成功{a['development_success']}/{a['development_completed']}已测点，状态{a['status']}，代表重放{'一致' if a['restore_ok'] else '未完成'}" for a in results)
    replay=any(a['restore_ok'] for a in results)
    operational=any(a['operational_fault'] for a in results)
    solved=any(a['development_completed']==4 and a['development_success']==4 and a['restore_ok'] for a in results)
    effect='执行问题阻止效果判定。' if operational else '缩幅部署保住四点成功，但新动作映射的训练效果仍待验证。' if solved else '本轮没有解决策略失效：原幅度和已测缩幅均未达到四点成功目标。执行/复现通过不等于方法有效。'
    next_step=('先解决最新执行故障，禁止自动新实验。' if operational else
        '进入阶段约束设计/实现准备；实际对照须先冻结公平的小固定边界训练基线和新预算。' if replay else
        '可推进阶段约束设计；实际对照仍缺完整冻结评价与独立进程代表复现，先解决这一执行门。')
    p=N.ROOT/'项目进度跟踪.md';t=p.read_text(encoding='utf-8')
    t=re.sub(r'最后更新：\d{4}-\d{2}-\d{2}',f'最后更新：{date}',t,count=1)
    t=t.replace('## 当前状态\n\n','## 当前状态\n\n**效果判断：** '+effect+'\n\n',1)
    t=re.sub(r'^\| C 候选约束与消融 \|.*$',f'| C 候选约束与消融 | 设计已修订；未实现/未验证 | [SEARCH阶段权限最小草案]({design}) | 匹配权限实现、合理小固定边界训练基线与同预算比较；无收益结论 |',t,count=1,flags=re.M)
    replacements={
        '3 动态闭环/成本':f'本次新增{total}/10冻结评价动态，训练0，累计{80+total}/90；完整成本见最新审核，旧轮吞吐不作为本轮实测',
        '5 B2与批量评价':'历史B2开发对照保持；最新冻结C2000部署结果见当前状态，代表重放不计新增性能样本',
        '6 普通残差SAC':rowtext+'；保存修复与策略效果分开，未取得B.2正式验收',
        '7 阶段与进展约束':'已提出仅SEARCH开放残差的最小阶段权限草案；未实现/未训练，无收益或创新结论',
        '8 正式证据与展示':'本次逐点图、原轨迹、完整归档与预算审核；独立评价尚未完成，95μm独立点与原64测试不取用',
    }
    for key,value in replacements.items():t=re.sub(r'^\| '+re.escape(key)+r' \|.*$',f'| {key} | {value} |',t,count=1,flags=re.M)
    risk={
        '修复归因与验收范围':('最新固定C2000开发筛查：'+rowtext,'不把冻结部署缩幅当重新训练收益；'+next_step),
        '单变量与有限对照可比性':('本次固定同一C2000，仅比较登记XY150/50部署；转动与保护保持','缩幅是部署筛查，公平的小固定边界方法需用匹配动作映射训练；不回流独立测试'),
        '本次力失败学习机制':('历史价值核对：已见失败未漏用，新危险边界Q约+9.364对精确尾段−8.359','本轮无额外critic推理，不能称价值高估已消除或唯一根因已证实'),
        '工程范围可观测性与动作作用':('冻结C2000本次真实接线与归档按候选审核；'+rowtext,'普通失败、保护、无效和运行故障分开；有限开发点不等于泛化'),
        '原项目全量测试':('本次24项相关协议通过；一次源码审查4项Important已由反例修复','非全项目测试；真实表现及复现以本次结果为准'),
        '训练状态恢复':('C2000完整updater恢复及来源数据审核绑定；本次代表物理重放'+('已取得一致证据' if replay else '未完成'),'历史C2500未执行；文件恢复、物理复现、任务成功是不同结论'),
    }
    for key,(fact,gate) in risk.items():t=re.sub(r'^\| '+re.escape(key)+r' \|.*$',f'| {key} | {fact} | {gate} |',t,count=1,flags=re.M)
    t=re.sub(r'(?<=## 下一项交付\n\n).*?(?=\n## 追加式阶段记录)',next_step+f' [最小机制草案]({design})。B.2独立评价仍未完成；本轮余量关闭、旧余不使用、自动跟踪PAUSED。\n',t,count=1,flags=re.S)
    p.write_text(t,encoding='utf-8')
    month=N.ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';m=month.read_text(encoding='utf-8')
    m=re.sub(r'统计截至：\d{4}-\d{2}-\d{2}',f'统计截至：{date}',m,count=1)
    m=m.replace('## 一、本月综合摘要\n\n','## 一、本月综合摘要\n\n**效果判断：** '+effect+'\n\n',1)
    m=re.sub(r'(?<=## 五、下一项\n\n).*?(?=\n## 六、来源记录)',next_step+' [SEARCH权限最小设计](../../learning_chain/b2_frozen_c2000_closeout_20261001/下一阶段最小方案.md)，仅草案，未实现/未训练。B.2独立评价尚未完成。\n',m,count=1,flags=re.S)
    month.write_text(m,encoding='utf-8')
    for name in ('项目交付总览.md','项目当前入口.md'):
        p=N.ROOT/name;text=p.read_text(encoding='utf-8');first=text.find('\n')
        note=f'\n**效果判断：** {effect}\n\n**下一阶段机制草案（{date}）：** [仅SEARCH阶段开放残差的最小方案]({design})，包含公平固定幅度基线、权限一致性检查和进入实际对照的条件。设计建议已形成，代码/训练/效果均未实施。\n'
        p.write_text(text[:first+1]+note+text[first+1:],encoding='utf-8')
    N.write(N.HERE/'rolling_reconciliation.json',dict(date=date,new_dynamic=total,results=rowtext,next_step=next_step,
        changes='Current status rows/date/next step only; historical append-only records and sealed snapshots preserved.'))

if __name__=='__main__':main()
