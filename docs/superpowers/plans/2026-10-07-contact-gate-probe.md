# PC-09接触权限与小固定边界部署预检

> For agentic workers: use superpowers:executing-plans inline. 用户在具体PC-08候选之后明确“继续”，沿用自主执行授权；原工作区/分支/213条脏记录保留，不提交、不清理。

**Goal:** 实现G50与F12.5的最小部署变体，完成固定8回合预检，判断是否保留候选。

**Architecture:** 新交付目录`deliverables/paper_comparison/contact_gate_probe_20261007`包含deployment_profile.py（权限/比例/会话适配）、run_probe.py（只读检查点与固定采集）、专项测试及结果收口。生产1057输入保持，不改变旧合同或归档。复用ContinuationResidualSession和原动作合成、控制器、物理、奖励、停稳审核。

**Tech Stack:** 原CPU Python/NumPy/torch/SB3/MuJoCo及137维/4维接口；不安装依赖。

**Spec:** `deliverables/paper_comparison/residual_effect_diagnosis_20261007/next_candidate.md`，已在继续前呈现并获得执行授权。

## Global Constraints

- B2零残差；F50原边界；F12.5同一F2000演员的四个归一化请求乘0.25，另存未缩放actor_action，不冒充该尺度下重训；G50保持最大尺度，SEARCH启用，INSERT仅`Fz_M <= -0.005N`启用。
- G50由同一动作前可见wrench数据判定；使用与137维观测相同的float32归一化量比较，避免5mN边界双精度/单精度不一致。其他原pending/物理阶段/无效/保护权限必须同时满足。
- 保留原F50检查点/优化器/RNG完整读取校验，只作冻结推理；不宣称新G权限下完整训练恢复。
- 固定8回合：aligned×B2/F50/F12.5/G50，然后y_neg_150×四方法；开发范围，不用四个已消费首次位置选参，不重试。
- 新动态上限8，累计200→208；优化/经验发布0。每回合14500周期/1200s/STOP；普通失败和合格保护保留，来源/运行/参考/无效/未停稳错误整轮停，余量关闭不结转。
- 137维/4维、模型、力25mN/力矩/几何/奖励/控制时间和共同B2不变。PC-06/07/08原封存及全部生产来源保持。
- 新profile合同明确命名，不把G50标成原F50。F12.5记录actor_action及scaled_request，原session内F50尺度仅作为公共动作合成器，不进入新训练。

## Tasks

### Task1 最小权限与只读部署合同

Create deployment_profile.py/test_profile.py。

Interfaces: `enabled(profile, phase, base, wrench_z)`统一门控；`permissions(observations,profile)`验证137维字段、当前action_active和新规则；`deployment_action(actor_action,profile)`返回实际请求；`ProfileSession`仅覆写stage_permission；`audit_rows(raw)`验证连续观测/新权限/动作映射/物理时间折扣/边界，不发布经验。

- [ ] 手算RED：5mN正反号/阈值/float32邻域、SEARCH低载启用、INSERT低载禁用、共同保护与pending、旧F50不接受G假标签、比例与原actor分列、无效动作、跨周期mask、终末和折扣。
- [ ] 最小GREEN；生产代码0修改；原schema引用完整来源，不能转改action_active去迎合旧合同。

### Task2 固定采集登记与执行

Create run_probe.py/test_execution.py/configuration/verification/review/qualification/progress。

- [ ] 复用原rollout循环的环境/审判/奖励/参考实测/STOP，明确变化仅session/profile和权限审核；保存移植来源SHA。
- [ ] 离线完整读取F2000、状态保持/原策略确定性；准备模型与8矩阵、角色合同、来源/脚本/配置哈希。故障调用计数统一从已记entry派生，不漏计、不自动重试。
- [ ] 一次限定独立审查在新物理准入前完成；冻结资格，然后一次领取执行8回合。每回合前后完整演员/优化器/RNG不变。

### Task3 原始复核和收口

- [ ] 全部实际档案独立复算停稳/功能及附加精度/dt奖励/折扣/权限/动作/来源/计数；原B2/F50与旧同版本对应档案完整轨迹、事件和结果逐值比较；G对中全零动作及B2轨迹比较，不删失败。
- [ ] 报告成功/罚时/载荷/精度/NN调用/门控切换和墙时；F12.5为部署敏感性，G为冻结演员权限探测，不当正式论文效果或新权限下训练结果。
- [ ] 图表目视核对，更新五份原滚动资料与快照，总览PC-09、能力表/原八项/风险/下一项、同月素材；封存后阶段暂停汇报。

## Review Focus

- float32阈值邻域和动作前反馈来源；不偷用真实孔位/接触计数。
- G权限在会话、观测、采集、终末与审核必须一致，旧合同不改写。
- F12.5原演员输出与部署请求必须分列，不能把缩放后动作伪称原输出。
- 故障路径调用/部分周期成本与尝试必须保留，不因审核失败漏记或重试。
- 基线与G对中轨迹若不一致必须调查；不能以新mask冒充新训练/恢复/独立测试。

## Decisions

Ruling: 保留原工作区及生产来源，把新增适配/合同放交付目录；不新增学习模块。代价是新方法资格单独登记。
Ruling: 本项是已授权8回合部署预检，不扩大训练，关联测试只跑不产生物理/梯度的检查；不声称全仓库通过。
Ruling: 一次fresh审查放在物理资格前；执行后由作者按原始档案和完整来源独立复核，明确审查当时尚无物理结果，不重复购买审查上下文。
