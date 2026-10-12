# 联合横向位置与倾角误差：强基线及文献边界

2026-10-10。当前阶段：B.2 问题与方法复核；本子任务为原始文献只读研究，已完成。已读本工作区 AGENTS.md、当前入口、进度和研究计划顶部；保留现有脏工作区。本轮物理、学习模型/检查点加载、策略推理、训练及生产源代码修改均为 0；只新增本记录和来源索引。根进度等由主任务统一更新。

**结论：不能预设“传统方法在联合误差下普遍失败”，也不能把“多销六维误差尚无人处理”作为空白。** 现有强方法既有成功反例，也有明确但有限的退化机制：接触信息不足、同净力矩对应多个接触构型、有限估计搜索域、摩擦或夹持滑移。当前项目尚未证明调优后的同信息传统基线存在稳定缺陷。

访问分级：A=读到原始全文；B=原始正文/表格片段可核，未读完整全文；C=仅原始摘要或预览；D=仅书目/题名。下列引用仅用作者上传、作者机构或出版方原始内容；第三方索引只用于找入口。

## 4 篇可核主体记录

| 编号、书目、访问及定位 | 工件、误差、信息与动作 | 实验/对照、结果与边界 |
|---|---|---|
| P1 Cao, S.; Xiao, J. **On Efficient and Flexible Autonomous Robotic Insertion Assembly in the Presence of Uncertainty**. RA-L 9(7), 6360–6367, 2024. DOI [10.1109/LRA.2024.3404749](https://doi.org/10.1109/LRA.2024.3404749)。A：[作者上传全文](https://www.researchgate.net/publication/380835107_On_Efficient_and_Flexible_Autonomous_Robotic_Insertion_Assembly_in_the_Presence_of_Uncertainty)，上传者 Shichen Cao；§III-C/D、IV-A/B/D、Tables II–IV。 | 无倒角、3D 打印混合形状四销；文中位置/姿态间隙 <1.5 mm/<0.015 rad（不是单针径向间隙）。实机 Panda+ATI+真空夹具；名义相对位姿、几何球树、净 F/T，4096 组实机训练和标定；完整六维小步修正。联合位置与 roll/pitch/yaw，不是先消除倾角。 | Table II：10 个偏差各 5 次，有界穷举接触优化 44/50，NN 先验+优化 50/50；case 10 为 [17.6,-17.2,-3.5] mm、[-0.2353,0.1567,-0.1984] rad，对照 1/5→5/5。基线搜索界/调优未给全。Table III：60 s 内 155/160；另 5 次最终成功，最长 3.08 min。§IV-D：平面孔外接触缺乏横向位置辨识、接触歧义导致多次尝试。这是效率边界，不能推出任意充分调优传统控制均失败。 |
| P2 Chen, Y.; Kimble, K.; Qian, H. H.; Chanrungmaneekul, P.; Seney, R.; Hang, K. **Robust Peg-in-Hole Assembly under Uncertainties via Compliant and Interactive Contact-Rich Manipulation**. RSS 2025；arXiv:2506.22766。A：[作者全文](https://arxiv.org/html/2506.22766v1)，[会议 PDF](https://www.roboticsproceedings.org/rss21/p060.pdf)本轮超时；§III-A、IV-C、V-A/C/D、VI，Fig.8、Tables I/II。 | 无学习单销接触漏斗；金属圆/矩形约 0.6–0.8 mm 间隙，PLA 非对称约 0.4 mm，无倒角。Panda+GelSight 手内位姿；已知板平面、工件几何和孔所在区域；阻抗+主动倾斜/角点接触+MPC/RLS。主动倾斜不是随机初始 roll/pitch 联合覆盖；未给其扫描范围。 | Table I 已知孔位置：9 种各 10 次，位置控制 27/90，漏斗阻抗 87/90；对照非导纳+搜孔强基线。Table II 完整流程 85/90。约 30% 膨胀区域先验。失败含高力/摩擦导致滑移超触觉范围及阻抗模型不准；§VI 未显式建模摩擦。没有给摩擦或夹持力阈值边界；触觉、手内弹性及动作权限与当前平台不同。 |
| P3 Jin, S.; Zhu, X.; Wang, C.; Tomizuka, M. **Contact Pose Identification for Peg-in-Hole Assembly under Uncertainties**. 2021，arXiv:2101.12467。A：[作者全文](https://arxiv.org/html/2101.12467)，§II-A/C、III-A/D、IV-A2/B、V，Tables I/II。 | FANUC+ATI，3D 打印单个方形/五边形销。初始位置/姿态约 ±20 mm/±3°；先用平面接触消除 roll/pitch/z，后续只 x/y/yaw。仿真 tilt-then-rotate 探测倾角为 15°；CNN 判位置误差方向，yaw 靠摆动。 | 每工件实机 20 次、至多 3 尝试；50 mm 方孔/1 mm 间隙 20/20，32 mm 方孔/0.5 mm 17/20，五边形/1 mm 19/20。无强传统对照。错误分类和导纳补偿不足是文中失败原因；只给方向、不给幅值，需调好导纳；模型不能分类 yaw。不能把它当作持续联合 roll/pitch 估计或九针实验；主动四轴探测与时序接触信息已有先例。 |
| P4 Cho, H.-C.; Kim, Y.-L.; Kim, B.-S.; Song, J.-B. **A Strategy for Connector Assembly using Impedance Control for Industrial Robots**. ICCAS 2012, 1433–1436。A：[第一作者上传全文](https://www.researchgate.net/publication/259571868_A_Strategy_for_Connector_Assembly_using_Impedance_Control_for_Industrial_Robots)，§2、3.1/3.2、4/5，Figs.2/5/6/7。 | 实际 LCD 面板 Molex 连接器，Denso 6DOF+腕部 F/T；重力补偿、1 ms 位置式阻抗。先与倾斜面板贴合，再探测两边并用 CAD 更新任务坐标，最后插接。倾斜面板不是接触插入阶段随机 roll/pitch 残差扫描。 | 公开代表轨迹约 35 s；面板对准 13 N/4.5 s，插接最大约 30 N。未给间隙、误差分布、成功样本数或比较组。只支持接触+CAD 的传统连接器可行性，不能声称高成功率或联合误差鲁棒范围。需要可接触面板/边缘和工件布局先验，当前局部九针接触环境不具备这些信息。 |

数字为实验事实；“更复杂必然使传统控制失效”等引言概括不作为本项目已验证缺陷。P1 的 uninformed 是无需预测 NN 的有界几何接触优化，P1 informed 与 P3 含监督学习，不能标成纯传统；P2/P4 是无策略学习方法。

## 关键正文片段与未取得全文

- **Tang et al., Autonomous Alignment of Peg and Hole by Force/Torque Measurement for Robotic Assembly**, CASE 2016, 162–167，DOI [10.1109/COASE.2016.7743375](https://doi.org/10.1109/COASE.2016.7743375)。B：[作者原 PDF 入口](https://wjchen84.github.io/publications/C2016_CASE_PH.pdf)现 404；出版搜索缓存可核 p.165、§III-C/D、§IV 和 Table I。6061-T6 单圆销，孔/销名义直径 25.400/25.370 mm、1 mm 倒角；三点接触解析估倾角/位移，先退回、空中对准、再插入。摩擦校准使用已知真实姿态；四个校准倾角 10.36°/15.75°/20.38°/26.47°不等于随机试验覆盖。摘要的 96% 因最终实验页/样本未核，不用于定量结论。单销模型及摩擦先验不能直接套用九针+壳体净 wrench。
- **Wang et al., Geometry and Force Guided Robotic Assembly With Large Initial Deviations for Electrical Connectors**, TASE 22, 8095–8107 (2025)，DOI [10.1109/TASE.2024.3477918](https://doi.org/10.1109/TASE.2024.3477918)。D：[作者机构书目](https://mse.hust.edu.cn/info/1142/13581.htm)论文[10]；[IEEE 原页](https://ieeexplore.ieee.org/document/10722037)浏览器验证阻挡。未取得正文；工件、联合误差范围、样本、成功/力/耗时及调参均不填。第三方转载摘要不用于技术论证。
- **Liao et al., Friction-aware robotic peg-in-hole assembly via contact wrench measurement**, Measurement 257 C, 118781 (2026)，DOI [10.1016/j.measurement.2025.118781](https://doi.org/10.1016/j.measurement.2025.118781)。C：[出版方预览](https://www.sciencedirect.com/science/article/abs/pii/S0263224125021402)，Abstract、Methodology/Experiment/Discussion snippets。可核：对准面、摩擦补偿角度估计→位置搜索→微调/插入；实机谐波减速器场景。无全文，误差轴/范围、间隙、样本和比较数字未知；其引言的“传统方法忽略摩擦”等不是 controlled failure experiment。
- **Li et al., Robotic Multiple Peg-in-Hole Assembly with Deviation Estimation and Fast Insertion Control**, TIE 72(1), 670–680 (2025)，DOI [10.1109/TIE.2024.3406860](https://doi.org/10.1109/TIE.2024.3406860)，[IEEE](https://ieeexplore.ieee.org/document/10574869/)本轮只返回题名。**A Novel Robotic Multiple Peg-in-Hole Assembly Pipeline: Modeling, Strategy, and Control**, TMECH 29, 2602–2613，DOI [10.1109/TMECH.2023.3337102](https://doi.org/10.1109/TMECH.2023.3337102)，[IEEE](https://ieeexplore.ieee.org/document/10360330/)同样缺正文。均为必须补读的强多销候选；本轮不从未认证作者的转载摘要填实验参数。

## 对当前平台的适用性判断（本报告推断）

当前为刚性九圆针+刚性 D 壳接触、名义单针径向间隙 100 μm；观测为理想净六维 wrench、相对运动和控制状态（137D），无孔绝对真值或视觉；动作只 XY/roll/pitch 四维速度残差，叠加固定导纳、有限螺旋和一次回撤。实机弹性、电连接、损伤及力标定未验证。资格仅联合四个离散 ±75 μm/±0.25° 点；旧负 Y150 μm、零倾角 B2 成功 20.780 s、SEARCH 14.768 s，只是开发效率线索；F0 随机 actor 不能作零残差 B2。

P1 最接近“净 wrench+几何+联合倾角+多销”，已排除宽泛的空白论断；但其名义位姿来源、全六维修正、实机标定/训练和多次尝试与本平台不同。P2 的平面先验与手内触觉，P3 的先消除倾角，P4 的面板边缘 CAD 定位均不能直接当作同信息对照。单孔净 wrench 可辨识性结论还需对九针+壳体同时接触单独检验。

**建议最强可行的同信息传统候选：有界四轴主动探测+局部 wrench 响应估计+确定性约束修正，保留无信息时的有限搜索与既有回撤。** 这是待设计和验证的工程候选，不是现成论文复现或已证明最优方法。

1. 先建立零残差纯 B2 的同共同版本对照；开发集有限调参，记录预算，独立评价不调参。固定导纳/保护/时限/一次回撤不改。
2. 只从 137D 中的合法运动、六维 wrench 历史和阶段进展取信息，在 XY/roll/pitch 内做等预算小幅双向探测；由命令/响应增量估计局部灵敏度，用正则化确定性最小二乘或短视优化选择减横向载荷/力矩且促进插入的残差。不得读真实孔误差、单针接触点真值或模拟器内部接触分解。
3. 接触模式改变或响应秩不足时，停止把低载荷当成已经对准，退回原有 bounded search；不加额外 Z/yaw 动作或第二次回撤。所有探测耗时计入总任务预算。

若机械接触优化模型可在同信息和计算预算内实现，再把 P1 的无预测器有界几何优化作为更强升级对照；必须说明摩擦/接触刚度、wrench 标定及多解处理，不能把知道真实初误差的 oracle 当传统基线。当前证据不足以承诺该方法会优于 B2，也不足以认定 SAC 必要。

## 可推进的 3 个问题候选及边界

1. **固定保护和一次恢复预算内，联合局部 XY+roll/pitch 误差是否让合理强传统控制出现可重复的长尾耗时/预算耗尽？** 指标为时限内功能成功、总时长/搜索时长分位数、回撤和载荷；先分清控制预算限制与刚性物理卡滞。未证实高失败率，不扩大成普遍难题。
2. **九针与壳体多接触时，有限四轴探测是否能比瞬时净 wrench/固定搜索更可靠地辨别有用修正方向？** 先对传统探测估计器评价；不把“主动探测”“时序接触”“几何引导”单独宣称新颖。范围限于已验证几何与局部姿态资格；强基线解决后应缩小或放弃学习贡献叙事。
3. **同一净 wrench 反馈下，摩擦/接触模式变化是否导致局部几何估计退化，且一次回撤能否纠正？** 先做离线候选与准入，后获授权才测试；现有无实机标定或损伤模型，不能讨论电子连接质量或防弯针效益。任何摩擦扩展需单独准入，不能由文献动机直接开训。

以上是可检验问题，不是新颖性或论文贡献声明。

## 检索与访问日志

- 精确题名/DOI：`Geometry and Force Guided Robotic Assembly With Large Initial Deviations`、`3477918 pdf`、`Zhenyu Wang Electrical Connectors assembly pdf`；作者 HUST 书目可达，IEEE 10722037 阻挡，RG 仅 request full text。未用第三方摘要支持技术数值。
- 多销线索：`three-stage multiple peg-in-hole friction`、`multiple peg-in-hole friction-aware`、`multiple peg-in-hole contact mode`、`three-stage multiple peg assembly strategy`；定位 TIE3406860 和 TMECH3337102，原出版页仅题名，全文未取得。Measurement [25]/[26] 的具体身份未完整核对，不将其概述绑定到某论文。
- 摩擦方法：`Friction-aware robotic peg-in-hole assembly 118781 pdf`；出版方可读摘要/分节片段、实验数字未公开取得。
- 角误差连接器：`connector assembly inclined errors`、`connector assembly inclined robot force`、`A Strategy for Connector Assembly using Impedance Control pdf`；找到 P4 作者上传全文。倾斜场景与插入残差角误差已区分。
- 几何估计：`Autonomous alignment of peg and hole pdf` 及作者 PDF 限域 experiment/TableII/success/random 检索；得到 p.165 原始缓存片段。web PDF 多次抓取失败；捆绑 Python+pypdf 只读内存提取先受网络沙箱限制，获只读升级后原作者 URL 返回 404，未取得全篇。Te Tang 博士论文原库 PDF 因 >10 MB web 限制未读；不引用其未知实验页。
- 主任务提供 P2/P3/P1：arXiv2506.22766、arXiv2101.12467 HTML 全文可读；RSS PDF 超时；P1 作者上传全文可读，核 §IV 和 Tables II–IV。P1/P2 对照权限不等与 P3 倾角先消除均已记录。
- 探索过 `Robotic Assembly for Irregular Shaped Peg-in-Hole with Partial Constraints` 等入口，MDPI 直读失败，未纳入主体或补充定量证据；遵循主任务要求停止扩展。

未决访问优先级：TASE3477918 连接器全文；TIE3406860/TMECH3337102 多销正文和实验表；Measurement118781 的摩擦扫描/对照；Tang 最后实验页。未取得全文不等于论文没有该实验。
