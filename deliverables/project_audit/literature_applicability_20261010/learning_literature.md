# 定向学习文献核查：残差、柔顺性、阶段权限与约束

阶段B.2第3项｜计划第1、2项的文献分工，已完成原文核查；访问日期均为2026-10-10。仅阅读及写本文，无仿真、模型推理、训练或运行配置修改。本文是供主报告整合的来源证据，不是研究效果验收。

先纠正前提：残差RL、动态柔顺控制、接触阶段改变控制权限、力限制条件化都已有先例。“传统方法一定弱”“阶段残差边界本身新颖”“必须采用SAC”均不能由这些文献推出。以下结果跨任务、成功口径、动作权限不同，不能与本项目成功率直接排名。

## 检索、追溯与入选

查询实际包括：`"Learning Hybrid-Control Policies" Brown Hollinger Lee`；`"Integrating admittance control and residual reinforcement learning"`；`robot insertion phase dependent residual reinforcement learning action constraints variable impedance uncertainty`；`"Variable Compliance Control for Robotic Peg-in-Hole Assembly" DOI`；`"Residual Reinforcement Learning for Robot Control" DOI 2019`；`"FORGE" "force" "robot" assembly reinforcement learning arxiv`。

追溯：Beltran-Hernandez2020 §2.4.1 → Johannink2019；MATCH2026 §II与§IV-A → Beltran-Hernandez的连续位置/力选择；CG-RL2026 ref22/§II-C → FORGE；FORGE ref10 → Beltran-Hernandez。数值及机制只取原作者arXiv全文或正式出版社页面，二手搜索摘要只用于定位。

入选6篇：2篇基础残差/柔顺，MATCH与CG-RL作为最近阶段/约束机制对照，FORGE作为强力反馈基线，Li等Robotica作为摘要级相近组合。排除本轮深入比较：Su等2026柔性peg示教约束区域（DOI10.1016/j.rcim.2026.103259，涉及柔性部件与示教，公开页只有预览）；通用安全RL/导航、视觉语言策略、综述不作为本刚性9针问题的直接效果证据。未穷尽全部文献，不据此宣称唯一性或首次。

## 书目信息与访问级别

| ID | 一手书目与链接 | 本轮可用证据 |
|---|---|---|
| L1 | Tobias Johannink, Shikhar Bahl, Ashvin Nair, Jianlan Luo, Avinash Kumar, Matthias Loskyll, Juan Aparicio Ojea, Eugen Solowjow, Sergey Levine. *Residual Reinforcement Learning for Robot Control*. ICRA2019. [DOI10.1109/ICRA.2019.8794127](https://doi.org/10.1109/ICRA.2019.8794127)；[作者全文1812.03201v2](https://arxiv.org/html/1812.03201v2) | 全文；preprint2018，正式会议2019；IEEE元数据核对 |
| L2 | Cristian C. Beltran-Hernandez, Damien Petit, Ixchel G. Ramirez-Alpizar, Kensuke Harada. *Variable Compliance Control for Robotic Peg-in-Hole Assembly: A Deep-Reinforcement-Learning Approach*. Applied Sciences2020,10(19):6923. [DOI10.3390/app10196923](https://doi.org/10.3390/app10196923)；[2008.10224v2全文](https://arxiv.org/html/2008.10224v2) | 全文v2；arXiv元数据核对期刊；出版社读取失败。v3存在，本轮具体表值按v2定位 |
| L3 | Hunter L. Brown, Geoffrey Hollinger, Stefan Lee. *Learning Hybrid-Control Policies for High-Precision In-Contact Manipulation Under Uncertainty*. 2026-04-21 preprint. [2604.19677v1全文](https://arxiv.org/html/2604.19677v1)；[arXiv DOI](https://doi.org/10.48550/arXiv.2604.19677) | 全文；未核实正式录用，按预印本 |
| L4 | Lin He, Min Deng. *Constraint-Grounded Reinforcement Learning for Variable Impedance Control in Contact-Rich Robotic Insertion*. 2026-09-11 preprint. [2609.13516v1全文](https://arxiv.org/html/2609.13516v1)；[arXiv DOI](https://doi.org/10.48550/arXiv.2609.13516) | 全文；仅模拟实验；按预印本 |
| L5 | Shi Li, Bin Li, Jianbo Yu. *Integrating admittance control and residual reinforcement learning for robotic assembly with visual and force feedback*. Robotica44(1):37–51,2026；online2025-12-29. [Cambridge/DOI10.1017/S0263574725102853](https://doi.org/10.1017/S0263574725102853) | 正式出版社摘要/参考文献，正文不可得；不是全文核验 |
| L6 | Michael Noseworthy, Bingjie Tang, Bowen Wen, Ankur Handa, Chad Kessens, Nicholas Roy, Dieter Fox, Fabio Ramos, Yashraj Narang, Iretiayo Akinola. *FORGE: Force-Guided Exploration for Robust Contact-Rich Manipulation under Uncertainty*. preprint2024，v2于2025-01-02. [2408.04587v2全文](https://arxiv.org/html/2408.04587v2)；[arXiv DOI](https://doi.org/10.48550/arXiv.2408.04587) | 全文；本轮未核实正式发表信息 |

## 机制、证据与迁移限制（简洁记录）

### L1：残差的来源，不能泛化为传统基线失效

Block inserted between movable/toppleable blocks; numerical clearance absent. Sim observes block poses/wrench; real uses camera tracking and axial force. Additive learned correction to an engineered controller, TD3; success judged manually by upright/correct block placement, no verified hard force threshold. Misaligned real trials: residual15/20 vs engineered2/20; aligned both20/20 (Fig3a/§VI-B). About8000 real samples; simulation10 seeds (§III-B,§VI-B). Same learner without base controller is the RL comparator; optimized engineered search/compliance baseline not demonstrated. No explicit stage/progress-varying bound verified. Supports a possible contact/dynamics correction problem, while aligned counterexample prevents “traditional always weak.” Movable objects, camera, and correction authority differ from fixed rigid9-pin mating and four velocity residuals; rates do not transfer. [原文§III–VI](https://arxiv.org/html/1812.03201v2).

### L2：已有残差、可变增益与阶段行为

UR3e cuboid clearance1mm; random goal error±2mm/±5° in training (Fig5/Table1). Pose error, velocity, previous action, desired force and12×6 wrench history;24 actions include6 pose corrections and18 gain/selection parameters (§2.2). Fixed parameter bounds around baseline; terminate/penalize force-limit exceedance, success within1mm; numeric maximal force/gain bounds not verified.500k simulation steps+15k real refinement;20 tests/condition. True-goal results100%/3.28s; transfer-only95%/3.77s (Table2). No tuned classical baseline. Search/contact/insertion change force-position weights (Fig7), but not explicit progress-dependent residual velocity envelope. Discussion explicitly recognizes wide/narrow bound tradeoff. Novel LAN transfer only55–60%, true goal (Table5). Supports testing permission/interference tradeoffs; variable gain/mode authority exceeds current4 residual axes. Estimated target input can come from planning rather than live vision, but 1mm cuboid tolerance does not establish9-pin strict alignment. [原文§2–4](https://arxiv.org/html/2008.10224v2).

### L3：阶段不同权限已有强近邻，低平均力不等于安全

Circular peg≈0.5mm clearance;10N break simulation. Actor: noisy relative pose/velocity/force/previous action; critic/contact supervision privileged. Hybrid xyz force/pose selection; orientation pose/yaw only. PPO5 seeds×3M steps, shared architectures/conditions; compliant Pose and VICES comparators (§V).100 tests/seed: MATCH97.0±1.5% success,0 breaks,2.7±0.2N; Pose95.4±1.6%,1.6±1.5% breaks,1.9±0.3N (TableI; errors are SE). Thus safer did not mean lower mean force. No-SSL deteriorates (TableI). Learned selection changes across phases (Fig3/§VI-D), not a prescribed four-axis residual envelope. VICES not significantly inferior under noise (§VI-E); supports strong adaptive comparator, not universal hybrid superiority. Real20N stop; gains tuned, best seed selected; Fig5 caption50 vs §VII100 trials/noise conflicts, exact denominator unresolved. Different pose/yaw/force authority, privileged training and selection protocol prevent direct translation to no-vision137-input XY/roll/pitch residual model. [原文§V–VII](https://arxiv.org/html/2604.19677v1).

### L4：最接近阶段门控与执行约束；优势必须拆开归因

Sim17° bore/compliant sleeve;30mm target; clearance, numeric terminal tolerance/reset magnitude absent.35 observations include ground-truth fixture registration and pair-contact reaction, not wrist wrench.8 actions:6 absolute pose residuals+gain+advance. Effective bounds±0.5mm/±0.75°; five-phase primitive zeros residual during contact ramp/hold (§IV-C). Gain projection/rate limiting separate from learned force compliance. PPO5 seeds,600 iterations,512 environments×128 rollout. TableV CCS85.78±7.73% vs midpoint50.10±0.96%; K-conditioned89.34±2.45%, learned contrasts inconclusive. Constant gain request1550+projection recovers most benefit, differences nonsignificant (§V-B2); no optimized fixed-search baseline. Combined shifts all0; high friction14.86±4.91% (TableVI). Supports testing authority versus policy, not RL necessity. Existing stage-zeroing overlaps gate concept; gain-set constraint differs from progress-varying4-axis velocity amplitude. Ground-truth geometry, scalar gain/axial-rate authority and sleeve invalidate direct9-pin transfer. No physical force guarantee or real validation. [原文§IV–VI](https://arxiv.org/html/2609.13516v1).

### L5：仅确认相近组合，不借摘要宣传效果

Publisher abstract combines admittance with visual/force feedback and residual TD3. Geometry/clearance, noise distribution, exact observations/actions/bounds, protection threshold, baseline tuning, independent seeds and interaction count unknown. Abstract claims400→100 epochs; epochs are not interchangeable with samples or wall time, and no table/denominator accessible. Do not use this number as verified comparative-effect evidence. Phase/progress action-envelope overlap cannot be judged without full text. This is evidence against claiming the mere “admittance+residualRL” combination new; it does not show whether a four-axis residual without vision outperforms a tuned baseline. Need fulltext before method-level exclusion or reproduction. [Cambridge Abstract/Information](https://doi.org/10.1017/S0263574725102853).

### L6：力条件化已存在，而且论文明确指出阶段力限制问题

8mm peg/0.5mm diametrical clearance; fixed-pose error0–5mm. Noisy pose/velocity/force/previous action+force threshold; relative xyz/yaw targets and termination prediction, no roll/pitch; recurrent PPO/asymmetric critic. Three seeds; training total steps unknown. IndustReal comparison adapts frequency, noise and matched networks; gain/action-scale randomized; soft force penalty, no hard-force guarantee.45 real trials/row: peg FORGE0.84(SE0.05) vs IndustReal0.82(0.06), peak12.84 vs21.15N (TableI); success advantage is small, reduced loading clearer. Snap-fit broad-reset success6/10; §V-D explicitly says one threshold may fail because low force needed before alignment, high force afterwards. Thus phase-dependent protection is an existing identified problem; no explicit progress-dependent residual envelope verified. Limited role transfer: no live vision needed in most calibrated/noised trials, but upright orientation, deformable snap-fit/slip and xyz/yaw authority differ from fixed rigid9-pin XY/roll/pitch velocities. [原文§II–V/AppC](https://arxiv.org/html/2408.04587v2).

## 本项目的判断与验证提纲（研究者推论，尚未执行）

1. **可成立的问题候选**：当前控制在对中/接触转换处可能存在残差权限与精度目标冲突。必须先展示同信息、同保护、同时间预算且合理调参的确定性控制仍有可重复缺陷；文献只提供机制方向，不能代替本项目证据。
2. **最低公平对照**：合理调参的零残差控制；开发集选择的固定小/中残差边界；手工阶段门控/连续进度缩放；学习残差使用与之相同观测、四轴权限和保护。将“有无策略”与“大小边界/启停规则”拆开，否则控制执行层改善会被误算为学习收益。
3. **强方法候选有条件加入**：MATCH/VICES/CG-RL的gain或force模式，以及FORGE的轴向/偏航权限均超出当前动作合同。可借鉴机制设计同权限确定性自适应对照，但不能把裁掉关键动作后的实现称完整原论文复现。若增益/轴向动作必须开放，属于研究范围变更，应先明确方案。
4. **新颖性应窄化并保留待查**：仅把阶段启停、柔顺+残差、约束条件化作贡献不够。可能需要区分“在有限传感与固定四轴速度权限下，利用可观测接触/进度设置连续、可校核的权限包络”及其代价；本次搜索未证实已有完全相同组合，也未证实其新颖或有效。
5. **记录与裁判**：分别记录raw normalized action、物理四轴残差、阶段权限、裁剪/门控后实际命令、接触响应与失败原因。平均力、峰值、保护触发、成功率、失败计入耗时分别统计；加入正常成功工况的反证，避免只展示困难条件。成功与保护口径必须保持项目合同，不能换用文献1mm或30mm等阈值。
6. **观测适用性缺口**：137维数量本身不保证信息充分；需只读核实哪些来自传感/历史、哪些是模拟真值，是否包含可辨别接触阶段与深度的量、四轴速度是否真正可纠正该失败。现有刚性无视觉模型不能证实pin弯曲、材料损伤、grasp slip或实机部署收益。

## 原文定位与未解决项

定位均按上述固定版本章节/表号；不使用浏览器行号作为稳定论文页码。L1 Fig3a/§VI-B；L2 Eq2/5、Fig7、Tables1/2/5、§4；L3 TableI、Fig3、§V/VI-E/VII；L4 Eq17后残差说明、TablesII–VI、§V-B2/VI；L5 Abstract；L6 TableI、§V-D、AppC。原文缺失参数一律保留未知，不反推成功率或从图上猜数字。

本轮必要补证：L5全文；L3实机试次数矛盾；若要复现L4需CAD间隙、数值终端容差、reset范围与sim contact-to-wrist映射；L6训练步数。后续只在问题确有证据时扩大文献追溯。本文未授权、未执行任何新训练/推理/物理验证。
