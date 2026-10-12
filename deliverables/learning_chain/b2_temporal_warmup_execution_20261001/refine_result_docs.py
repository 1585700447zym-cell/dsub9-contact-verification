"""Integrate arm-specific negative result and current mechanism numbers."""
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
paths=[ROOT/'项目进度跟踪.md',ROOT/'项目交付总览.md',ROOT/'项目当前入口.md',ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md',HERE/'result_analysis/结果说明.md']
for path in paths:
    t=path.read_text(encoding='utf-8')
    t=t.replace('完成8回合、成功7，训练/网络前向/经验入池均0。','完成8回合、成功7（A对照4/4、C候选3/4），训练/网络前向/经验入池均0。')
    t=t.replace('### B.2最新准备｜100ms时间相关预热','### B.2上一准备阶段（历史）｜100ms时间相关预热')
    t=t.replace('### B.2最新实际结果｜冻结B500独立评价','### B.2前项实际结果（历史）｜冻结B500独立评价')
    if path.name=='月报素材_2026-10.md':
        t=t.replace('| 100ms窗口X均方根 | 旧预热','| 旧预热/B的100ms窗口X均方根（历史） | 旧预热')
        t=t.replace('## 二、关键数字与证据\n\n','## 二、关键数字与证据\n\n本次新A/C对照：A四点4/4、C四点3/4；C负X普通失败的末端XY为66.824 μm，高于50 μm成功门。C完整100ms窗口381个，X请求RMS 0.53540（A为0.08032）；四轴均取得正/负≥0.8请求。C接触有权限100ms窗口191个，X/Y双向命令有效改变量均满足≥1 μm/s门；这些证明采样机制有作用，不证明学习效果。\n\n',1)
        t=t.replace('当前方案讲稿：“降低actor学习率','上一准备阶段讲稿（历史）：“降低actor学习率',1)
        t=t.replace('本次预检已实际接通采样/物理入口，但不是学习效果验收；','C负X普通失败保留，且C四个点峰值力均略高于各自A；样本少，不能称成功率、载荷或效率改善。本次预检已实际接通采样/物理入口，但不是学习效果验收；',1)
    path.write_text(t,encoding='utf-8')
print('Integrated arm-specific result and current preflight numbers in the same documents.')
