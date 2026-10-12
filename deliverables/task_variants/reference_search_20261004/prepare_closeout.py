"""Prepare the next rolling-document updater; do not run until results are final."""
from pathlib import Path
OUT=Path(__file__).resolve().parent;OLD=OUT.parent/'axis_search_20261004'
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
t=(OLD/'update_documents.py').read_text(encoding='utf-8')
for a,b in [('axis_search_20261004','reference_search_20261004'),('axis-search-current','reference-search-current'),('compliant-search-current','axis-search-current'),('2026-10-04-axis-search','2026-10-04-reference-search'),('154','184'),('TV-06','TV-07'),('TV-01～05','TV-01～06'),('分轴搜索与净推进','驱动参考一致性'),('分轴搜索实测后的执行修订','驱动参考一致性实测后的执行修订')]:t=t.replace(a,b)
t=t.replace("s=s.replace('| 搜索/导纳统一参考最新验证 |','| 前轮搜索/导纳统一参考验证 |',1)","s=s.replace('| 分轴搜索与净推进最新验证 |','| 前轮分轴搜索与净推进验证 |',1)")
t=t.replace("r'^最新统一参考：.*$'","r'^最新分轴搜索：.*$'").replace('最新分轴搜索：{numbers}','最新参考跟踪：{numbers}')
t=t.replace('新增SEARCH分轴控制及历史最深Z冻结基准；INSERT保留导纳，原物理/载荷保护保持；尚未接入残差学习','新增驱动参考反馈、离散螺旋前馈及参考包络前瞻核验，修正恢复后观测时序；分轴/净推进及原保护保持；尚未接入残差学习')
t=t.replace('本轮修共同传统控制的搜索与进展判据，未新增残差/约束候选比较','本轮修共同控制的速度到驱动参考映射，未新增残差/约束候选比较')
t=t.replace('SEARCH禁用XY导纳并冻结内部XY状态，保留原有限螺旋轨迹、Z调载及角向导纳；搜索退出必须超过本段开始前已达到的最深Z 100 μm。旧控制器保持原推进判据，恢复入口非法观测校验经5个反例修复。','SEARCH反馈采用目标与当前驱动参考的误差，前馈采用连续目标点差分；按实际驱动限速/加速度预测下一参考，越界受控停止。保留分轴/净推进，恢复后首命令使用重置后的参考与命令。离散末端不可行段最多提前一个控制周期结束，不扩大圆盘；两项恢复观测反例已修复。')
t=t.replace('搜索轨迹与净推进','搜索运动与净推进').replace('分轴搜索旧新对照','参考跟踪旧新对照')
t=t.replace('同目录PDF。讲稿：','[驱动参考对照](../../../{rel}/reference_diagnosis.png)，同目录PDF。讲稿：')
t=t.replace('run_axis_search_preflight','run_reference_search_preflight')
(OUT/'update_documents.py').write_text(t,encoding='utf-8')
print('Prepared rolling updater; no rolling documents changed yet.')
