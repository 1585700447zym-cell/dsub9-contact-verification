"""Close the result review's quick-index freshness finding."""
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
p=ROOT/'项目交付总览.md';t=p.read_text(encoding='utf-8')
lines=t.splitlines();current=next(x for x in lines if x.startswith('| 100ms预热机制的真实有限预检 |'))
lines.remove(current);first=next(i for i,x in enumerate(lines) if x.startswith('| 下一修复方案：时间相关预热'))
lines[first]=lines[first].replace('下一修复方案：时间相关预热','上一准备阶段（历史）：时间相关预热').replace('100ms预热内核已准备；','当时100ms预热内核已准备；')
lines.insert(first,current);p.write_text('\n'.join(lines)+'\n',encoding='utf-8')
p=HERE/'result_analysis/结果说明.md';t=p.read_text(encoding='utf-8');t=t.replace('图包括全部未执行项；','图展示全部8个预定回合（本轮无未执行项）；').replace('已执行子集的统计只作描述；','窗口统计用于本次机制门与描述；');p.write_text(t,encoding='utf-8')
p=ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md';t=p.read_text(encoding='utf-8');t=t.replace('新A/C请求和真实轨迹，全部未执行项保留。','新A/C请求和真实轨迹；8个预定回合均执行，普通失败保留。');p.write_text(t,encoding='utf-8')
print('Current result now comes first in the quick index; historical preparation is labelled.')
