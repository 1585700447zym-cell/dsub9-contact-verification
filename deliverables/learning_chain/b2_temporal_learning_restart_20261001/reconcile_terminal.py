"""Place terminal facts inside existing rolling summaries, preserving dated history."""
import re
from pathlib import Path
import validation_contract as C
HERE=C.HERE;ROOT=C.ROOT;S=HERE.relative_to(ROOT).as_posix();OUT=HERE/'result_analysis'
a=C.read(OUT/'assessment.json')
if a['judgement']!='method_not_resolved' or a['accounting']['formal_batches_completed']!=2000:raise ValueError('This supplement describes the observed 2000-batch endpoint only')
limitation='本轮在2000批随机在线负Y回合的力保护处结束，不是2500批确定性四点评价失败。C2500、固定最终四点、独立恢复动态及A对照均未执行；不能据此断言任意100ms方案无效、A一定更好、唯一原因已确定或critic高估已消除。'
status='保存故障已经由真实存取门和四个学习后检查点落盘/离线完整恢复核验；本次停止是实际力保护，非程序保存故障。8/8完整回合均有效停稳，起点4/4成功；在线0/4（3普通失败、1力保护）。保护回合未发布新经验，未获额外更新信用；最新C2000包含前7份审核学习档案和37,270条经验，触发原轨迹单独保留。'
p=OUT/'结果说明.md';t=p.read_text(encoding='utf-8')
t=t.replace('## 实际阶段与判据\n\n','## 实际阶段与判据\n\n'+limitation+'\n\n',1)
t=t.replace('两支从同零网络/空Adam/Torch RNG出发；','设计规定两支共用零网络/空Adam/Torch RNG，本轮实际只运行C，A未构建学习分支；')
t=t.replace('## 保存修复、来源和检查点\n\n','## 保存修复、来源和检查点\n\n'+status+'\n\n',1)
t+='\n## 执行中作出的决定\n\n- C500丢失后另登记零起点重启，旧500批保留；复做4个起点实际增加4动态成本，未用旧成功替代当前执行。\n- 本实验显式重用配对预热数据并单独重审资格和信用；同开发数据重复实验，不把它称作独立泛化。\n- 原工作树与全部修改、封存资料保留，没有提交、删除或自动重试。\n'
p.write_text(t,encoding='utf-8')
for name,heading in [('项目进度跟踪.md','## 当前状态'),('deliverables/monthly_progress/2026-10/月报素材_2026-10.md','## 一、本月综合摘要')]:
    p=ROOT/name;t=p.read_text(encoding='utf-8');m=re.search(r'^\*\*100ms预热重启验证已收口（2026-10-01）：\*\*.*$',t,re.M)
    if not m:raise ValueError('Latest terminal summary missing')
    summary=m.group(0);t=t[:m.start()]+t[m.end():];t=t.replace(heading+'\n\n',heading+'\n\n'+summary+'\n\n'+status+' '+limitation+'\n\n',1)
    if name=='项目进度跟踪.md':
        t=re.sub(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；保存修复有效，100ms方法未达效果目标 | [实际结果]({S}/result_analysis/结果说明.md)、[机器审核]({S}/result_analysis/assessment.json) | C2000在线3普通失败/1力保护；C固定最终/恢复/A未执行，B.2未完成 |',t,count=1,flags=re.M)
        t=re.sub(r'^\| 训练状态恢复 \|.*$',f'| 训练状态恢复 | 真实零存取与独立重建通过；C500/1000/1500/2000四个完整学习状态离线恢复/来源/抽样/Adam核验 | 原丢失C500仍不可恢复；C2500独立物理恢复未执行，不能把文件恢复通过当策略有效 |',t,count=1,flags=re.M)
        t=re.sub(r'^\| 原项目全量测试 \|.*$',f'| 原项目全量测试 | 最终181相关协议全过，8实测回合与4检查点完整离线审核；审核计算0 | 非项目全量测试；保存修复已核验，方法效果未达标 |',t,count=1,flags=re.M)
    t=re.sub(r'\n{4,}','\n\n',t);p.write_text(t,encoding='utf-8')
p=ROOT/'项目交付总览.md';t=p.read_text(encoding='utf-8')
t=re.sub(r'^\| 最新100ms预热学习验证结果 \|.*$',f'| 最新保存修复后的100ms效果结果 | [结果与图]({S}/result_analysis/结果说明.md)、[机器审核]({S}/result_analysis/assessment.json) | C2000在线0/4，3普通失败/1力保护，程序存取已核验；新8动态/2000批，余16/3000关闭，B.2未完成 |',t,count=1,flags=re.M)
t+=f'\n2026-10-01补充使用与限制：{status} {limitation} [C2000完整状态索引]({S}/run/latest_checkpoint_C.json)。独占入口不再执行。\n';p.write_text(t,encoding='utf-8')
with (HERE/'progress.md').open('a',encoding='utf-8') as f:
    f.write('\nTask2 terminal: initial4/4; candidate online0/4, ordinary3 + FORCE_LIMIT1 at2000; controlled20, no producer fault. New8/2000, cumulative80 dynamics / temporal2500 including prior500; unused16/3000 closed. Task3 audit8 complete archives and4 full states passed, actual calls0; plots viewed, current summaries/evidence/risk/original8/monthly reconciled. Terminal interpretation review and final seal pending.\n')
print('Terminal limits and rolling summaries reconciled; no computation.')
