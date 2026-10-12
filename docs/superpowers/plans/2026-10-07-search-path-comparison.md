# PC-10离线搜索路径对照计划

> For agentic workers: use superpowers:executing-plans inline. 用户已明确要求继续现有F/G/匹配训练S档案的离线对照；保留指定工作区及全部未提交修改，不提交、不清理、不重开预算。

**Goal:** 给出G两次搜索耗尽的可核查路径证据和一页路线决定，区分已定位的执行事实与尚未隔离的训练/权限假设。

**Architecture:** 新交付目录中的纯档案分析器只读PC-09的F50/F12.5/G50负Y及PC-06的匹配训练S50负Y。动作前观测定义SEARCH段，按段内时间和共同螺旋相位对齐，分别保存实际运动、参考方向、四维请求和总命令。统计与原始逐周期CSV并列，滚动文档保存当时快照。

**Tech Stack:** 当前Python、NumPy、Matplotlib；不导入物理环境、策略、优化器或生产控制器，不运行网络推理。

**Spec:** 本次用户指令、AGENTS.md及项目进度跟踪PC-09下一项。

## Global Constraints

- 工作目录`.worktrees/dsub9-v1-contact-validation`，分支`feature/dsub9-dynamic-actuator-v1`，HEAD `d2e7e4fa4ed0631d9dd1b7b98a121c1e46ea6406`；未提交修改全部保留。
- 新动态、物理子步、策略推理、梯度、经验发布均0；累计208，旧预算关闭，自动跟踪PAUSED，新训练准入无。
- 不扫描门槛、不改生产代码、137维/4维、奖励、几何、保护或冻结摘要；只用已用负Y开发点，无新的独立样本。
- 原封存PC-09清单SHA `c123f8f1f445c856e04222156f519e7b39e5cb8097e00bd646720f95858d3038`；PC-06 `fd98d247484e919c3c4e099d03575b1d4d40e977a5da939efc088759c84b9ed5`；PC-08 `1500e169da44e364c33dc01e84b30538b3de2abedb37c9486055d6fe4687a76f`。
- 四份数据共用comparison_key；G/F为同演员，S为不同匹配训练演员。相近入口不等于同轨迹受控干预，描述差异不升级唯一因果。
- 阶段用动作前policy_phase；真实运动不能替换为积分命令或effective_command_delta。

## Review Focus

- 切换周期的trace阶段滞后一周期；按观测解码，不误并停止尾段。
- SEARCH第二段重新定原点，但净深度门保持历史峰值；分列段内深度与净门限。
- 参考圆与实际XY精度不同；用已存动作重算120μm圆终止和完整100μm推进门，不能改阈值。
- dt、数组缺失/错位、非有限数及来源变化拒绝；以可手算数据验证时间、路径及向量单位。
- S旧成功不是新增样本，也不证明G重训必成功；当前无G匹配训练证据，不签发新资格。

## Tasks

### Task 1: 逐段路径与失败证据

Files: `deliverables/paper_comparison/search_path_comparison_20261007/{analyze.py,test_analysis.py,configuration.json,diagnosis.json,search_cycles.csv,alignment.csv,progress.md}`。

Interfaces: `search_segments(raw)`返回动作前SEARCH连续索引；`segment_metrics(raw,start,end)`输出状态、真实/参考路径、请求/命令积分与角分量；`boundary_recheck(event,last_row)`仅数值复核已存边界事件。

- [x] 写手算反例并观察RED：动作前切换、可变dt、命令与运动分离、两段搜索、终止边界判据、错误输入。
- [x] 实现纯数据分析，逐份核验原摘要、数组长度、许可与命令执行、参考积分；输出四档案五段及完整逐周期数据。
- [x] 按共同螺旋相位和段内秒数对齐；记录G边界末段、S提前满足净深度门及不同演员/入口的混杂因素。

### Task 2: 路线决定与交付

Files: 同目录的结果说明、路线决定、路径图/数据/检查/快照/封存；更新根入口、进度、总览、当前计划、10月滚动月报。

- [x] 绘制科研静态图并目视复核；失败原因分为确认事实/支持假设/证据不支持，给出一页路线决定。
- [x] 根据证据选停止G或另登记同权限公平短训准备；本轮不执行任何训练。
- [x] 运行专项数值检查和既有纯档案相关检查，作者独立复算关键原始周期；核对1057生产输入和旧封存文件未变。
- [x] 更新能力表、八项对应、风险、下一项、追加日志与月报摘要/数字/负结果/讲稿；保存快照，封存后重读核验，阶段结束暂停汇报。

## Decisions

Ruling: 本轮属于已明确授权的离线证据交付，直接在当前会话执行，不再次请求流程批准。
Ruling: 不运行可能生成新物理/策略计算的全历史测试；只运行纯档案专项及相关检查，不宣称全仓库通过。
Ruling: 用户要求保留全部未提交修改，所有新增脚本和记录留在新交付目录；不自动提交、移动或删除工作区。
