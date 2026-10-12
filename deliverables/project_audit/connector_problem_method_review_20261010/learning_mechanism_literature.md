# 联合 XY/倾角误差下的学习机制：原文证据与可检验假设

阶段 B.2 第 3 项｜任务：连接器问题与学习机制文献复核，2026-10-10 完成只读检索及本文。本文只建议评价设计；未运行仿真、科学库导入、模型/检查点加载、推理、训练或运行代码修改。保留当前 dirty worktree。仅写本文件，不在本分工中更新其他导航或合同。

**结论先行：力历史、循环网络、主动探测、原语选择、失败预测及回退均已有直接先例。当前更值得评价的假设是“依据已执行动作—实际运动—F/T 的接触响应，选择小幅协调 XY/roll/pitch 修正”。这不是已经证实的新颖机制，更不是已经证明需要学习的问题。** 初期可保留规则 Z、保护和固定恢复；学习撤退不必成为前提。

当前四点开发资格、F0/F2000 各 4/4、耗时改善 2.77%、额外精度 4/4→0/4，不能证明合理强传统基线的结构性缺陷；F0 也不是纯 B2。旧负 Y150μm 零倾角耗时线索不能替代联合误差的缺陷验证。现有刚性九针+D 壳、理想净六维 wrench 的结论只适用于该建模范围，不延伸到弹性针、损伤、电气接通或实机。

## 1. 证据范围与访问等级

本轮深入 5 篇主研究：基础导纳残差、主动 F/T 探测、循环插入、触觉倾角推断、失败预测恢复；另外核查 4 个紧邻工作的边界。已读旧包 [learning_literature.md](../literature_applicability_20261010/learning_literature.md)，其 Johannink2019、Beltran-Hernandez2020、MATCH、CG-RL、FORGE 等不重复算本轮新发现。这里只补旧计划基础种子遗漏与接触响应/恢复机制证据。

| ID | 一手原文、年代与访问 | 用途 |
|---|---|---|
| M1 | Xiang Zhang 等，*Efficient Sim-to-real Transfer of Contact-Rich Manipulation Skills with Online Admittance Residual Learning*，CoRL2023，PMLR229:1621–1639。[出版社](https://proceedings.mlr.press/v229/zhang23e.html)，[19页全文](https://proceedings.mlr.press/v229/zhang23e/zhang23e.pdf) | 原计划基础种子；全文、附录已核 |
| M2 | Junfeng Ding、Chen Wang、Cewu Lu，*Transferable Force-Torque Dynamics Model for Peg-in-hole Task*，2019。[1912.00260v1 全文](https://arxiv.org/html/1912.00260v1)，[元数据](https://arxiv.org/abs/1912.00260) | 多姿态主动探测的直接近邻；按预印本记录，不补未核正式书目 |
| M3 | Tadanobu Inoue 等，*Deep Reinforcement Learning for High Precision Assembly Tasks*，2017。[1708.04033v1 全文](https://arxiv.org/html/1708.04033v1) | 循环网络+力历史+倾角/位置误差；IROS2017书目亦见M1参考文献1 |
| M4 | Tatsuya Kamijo、Ixchel G. Ramirez-Alpizar、Enrique Coronado、Gentiane Venture，*Tactile-based Active Inference for Force-Controlled Peg-in-Hole Insertions*。[2309.15681v1 全文](https://arxiv.org/html/2309.15681v1) | 2023-09-27预印本仅v1；[作者书目](https://ixchel-ramirez-alpizar.com/publications/)列2026 SII:161–166。以下机制/数字仅依据v1，不宣称已比对正式版 |
| M5 | Yuhan Liu、Xinyu Zhang、Haonan Chang、Abdeslam Boularias，*Failure Forecasting Boosts Robustness of Sim2Real Rhythmic Insertion Policies*，2025。[2507.06519v1 全文](https://arxiv.org/html/2507.06519v1)，[作者项目/IROS2025](https://jaysparrow.github.io/rit/) | 历史条件失败预测与确定性撤退重试的归因对照 |
| B1 | *InsertionNet 2.0: Minimal Contact Multi-Step Insertion Using Multimodal Multiview Sensory Input*，2022。[2203.01153v1 全文](https://arxiv.org/html/2203.01153v1) | 多针VGA、XY+角度残差、独立Z/阶段切换的范围反证 |
| B2 | Xiang Zhang 等，*Learning Insertion Primitives with Discrete-Continuous Hybrid Action Space for Robotic Assembly Tasks*，ICRA2022:9881–9887；预印本2021。[2110.12618v1 全文](https://arxiv.org/html/2110.12618v1) | tilt-and-translate、原语/力阈值退出、连接器已有先例 |
| B3 | Guanghui Shen 等，*Recovery-Aware HIL-SERL for Contact-Rich USB Insertion with Global State Encoding*。[作者项目](https://sgh21.github.io/USBInsertionRL/)，[9页作者PDF](https://sgh21.github.io/USBInsertionRL/static/pdfs/Recovery-Aware%20HIL-SERL%20for%20Contact-Rich%20USB%20Insertion%20with%20Global%20State%20Encoding.pdf) | 网站标CoDL2025；PDF带投稿行号、未核正式录用，不升级为正式期刊证据 |
| B4 | Wen Chung Chang、Chi Fu Ho，*Coordinated dual-arm robotic assembly based on reinforcement learning with multimodal perception*。[作者机构记录](https://ntut.elsevierpure.com/en/publications/coordinated-dual-arm-robotic-assembly-based-on-reinforcement-lear/)，[DOI10.1007/s00170-026-18922-9](https://doi.org/10.1007/s00170-026-18922-9) | 仅机构摘要，标Accepted/In press–2026；无精确上线日期，不能断定截止日前正式公开的全文或优先权 |

## 2. 五篇主研究的紧凑证据卡

### M1：基础种子是在线导纳参数优化，不能直接等同四轴运动残差

- **任务/信息/动作**：方peg边长4cm、间隙2mm；初始XYZ为±30mm/30±5mm，未核到随机roll/pitch。状态含相对孔位姿、速度、wrench；离线SAC输出6D速度+6D刚度。在线录制/重放F/T窗口，用SQP优化M/K/D残差，正值约束保证参数正定。（§3、AppA/B）
- **对照/数据/结果**：直接迁移与手调同一学习轨迹；总训练交互未报告可核数。装配各10次：提出方法10/10、19.0±11.2s、最大力23.6±6.3N；手调10/10、28.1±8.6s、10.3±2.2N；直迁3/10。手调参数见Table4，权重w=0.4且有消融。（Table1、AppC/D）
- **保护/缺口**：正定约束不是硬接触力保证；作者承认初始次优接触、低更新率不适合脆弱对象，几何相似与force replay是限制。采集力的±10N截断不是实机最大力限制；间隙定义也不与本项目100μm径向间隙直接等价。[全文§3–5、AppA–E](https://proceedings.mlr.press/v229/zhang23e/zhang23e.pdf)

**迁移判断（本研究者推论）**：它支持“接触动态需要适应”，并不支持“固定导纳必失败”。当前未开放增益学习且无实机sim-to-real证据，直接换成该路线会改变问题和动作权限。当前若只比较速度，必须同时约束保护失败与力/力矩负载；手调成功且更低峰值是必须保留的反例。

### M2：多姿态 F/T 信息增益已做过，但探测幅度与动作范围差异很大

- **任务/信息/动作**：单peg多种形状，间隙约1±0.5mm；RGB-D先粗对齐至XY误差2±0.5mm。每XY点以0°及X/Y的±30°五姿态下压到Fz阈值，拼30D wrench。两层LSTM预测动作后状态；MPC或离线A3C只选择XY运动。（§III–IV）
- **数据/对照/结果**：7形状训练、9×9采样网格；薄板可变形训练、刚板测试；离线合成10步序列。新孔16点微调与从零动力学/实机在线A3C比较；MPC计划200序列、6步，最多6次控制，100次插入；TableI为MPC80–93%、model-based RL89–100%。（§V、TableI）
- **保护/缺口**：有Fz停止阈值，数值未核到；无优化过的经典搜索对照、单次6D状态消融未核到；主动倾角用于感知，而不是学习修正初始roll/pitch。30°是该文经验选择，不是本项目适用安全幅度。[全文§IV-A–E、V](https://arxiv.org/html/1912.00260v1)

**迁移判断（推论）**：它直接否定“净六维力歧义+多姿态探测”是空白。对于九针+D壳，固定XY旋转可能让其他针/壳接触切换，已不能假定形成相同形状的力状态图；更不能直接复制30°动作。候选差异只能落在小幅、联合四轴、动作条件的多接触响应与成本约束上，仍需证实。

### M3：循环力感知与倾角补偿已有2017先例，经典对照却较弱

- **任务/信息/动作**：钢圆peg直径34.990/34.980mm、孔35.000mm，文中间隙10/20μm为直径差。五个力/矩量+粗化XY位置信息，双层LSTM Q-learning；搜索用XY目标力，插入用下压力+±roll/pitch。控制周期40ms，力传感2ms平均；历史用于接触状态不明和两周期延迟。（§II–IV）
- **数据/对照/结果**：各技能最大230episode；搜索/插入分别学。1mm偏差→3mm课程，搜索采用20N下压力，10mm安全区；最大100/300步。TableII的1mm偏差+1.6°单轴倾角、20μm间隙100次均成功，4.36s；传统约5s来源是产品目录，不是同场景复现。（§IV、TableI/II）
- **缺口**：各配置在线学习；未核到无LSTM等容量消融或连续联合四维误差评价。传感器额定载荷不等于保护阈值。[全文§III、IV-A–C](https://arxiv.org/html/1708.04033v1)

**迁移判断（推论）**：该文确有位置偏差和倾斜的同次评价，不能写“此前都只研究位置误差”。但单圆peg的先XY后倾角控制不能证明九针+D壳所需的共同修正方向。GRU/LSTM本身已有重叠；必须识别可归因的接触响应预测/动作选择收益。

### M4：active inference处理的是夹内一维滑转，额外触觉信息不能省略

- **任务/信息/动作**：已知目标TCP；UR5e腕F/T+GelSight指尖触觉。用正抓触觉面积图旋转增强，快速训练decoder；隐变量为夹内一维tilt，推断后旋转TCP对齐。插入RL排除旋转，动作含位置/力控制增益与选择矩阵。（§III–IV）
- **数据/对照/结果**：插入仿真100k步；decoder评估500增强图/5epoch，双策略1000图；4个初始位置块共40插入。方peg间隙0.08mm：36/40 vs无触觉1/20；pulley间隙0.3mm：37/40 vs14/20。其触觉推断对比相同数据CNN。（§V、TableI/II）
- **保护/缺口**：采用力控避免过大力，硬阈值未核；初始XY含约1cm偏置，角度分布未定量报告。排除轴向滑移研究，gel损伤令baseline仅20次；并非无传感代价的纯wrench方法。[全文§IV-C、V](https://arxiv.org/html/2309.15681v1)

**迁移判断（推论）**：它不是在未知孔几何下用小探测寻找信息，而是利用夹内触觉估计一维滑转。当前刚性绑定与净wrench不含同类触觉/滑移，因此不能声称照搬即可辨别roll/pitch。它是“推断隐状态再分配对齐动作”已有先例，也是信息不同造成提升的反证。

### M5：学习何时重试与学习怎么撤退应分开，简单超时是强对照

- **任务/信息/动作**：3D打印扳手套螺母，容差1–2mm；RGB-D/FoundationPose追踪双方6D位姿，PPO输出6D位姿增量。XY±1cm/yaw±10°随机化；并无联合roll/pitch随机化核验。历史+时间训练失败预测；恢复固定插值回预插入姿态，持续固定步数。（§III–IV）
- **数据/对照/结果**：预测器用仿真10kepisode；与相同actor无恢复、time-only恢复比较。实机每尺寸/方法50次：Size5无恢复94%/31步，time-only100%/40步，历史分类100%/34步；后两者reset率14%/8%。Size3为92%/29步→100%/36步。预测阈值有调参。（TableIII、§V）
- **保护/缺口**：实机控制器用力反馈避免强接触，阈值未核；moving-window因控制频率不同未直接迁移实机。平均步数仅成功试次，训练actor总样本未核。[全文§IV-B–D、V-A–D](https://arxiv.org/html/2507.06519v1)

**迁移判断（推论）**：收益包括更高成功率和较少无效重试，未必比无恢复更快。该文不能证明要学习撤退轨迹；固定恢复+学习触发已足够构成已有机制。当前没有视觉对象位姿，替换成F/T历史需要新的可观测性证据与time-only/停滞规则对照。

## 3. 连接器、原语与阶段感知的紧邻反证

- **B1 InsertionNet2.0**：原文§III-A/E、Alg2、§IV-A/B/G使用双腕相机+F/T，输出XY/三角度修正、Z独立推进；150点/plug生成训练样本，每任务200试次；VGA报告100%，三步锁具用终态图关系判别切换，50/50。未报告可比100μm针径向间隙。多步状态感知、Z与残差拆分、多针电连接器已有先例；但视觉与终态图使它不是当前净wrench平台的公平直接效果对照。跨版本VGA提升还混合相机/机器人改变，不能全归因学习。[B1全文](https://arxiv.org/html/2203.01153v1)
- **B2 Zhang2022原语**：原文§III-A、§IV明确“tilt-and-translate”建立边缘接触，学习平移/转动/插入及力阈值退出；随机不确定性为XY/yaw，未核roll/pitch分布；刚圆peg间隙0.05mm，30次实机成功86.7%；防水/网口也测试。手工原语+学习参数/类别不是新组合，也不能说低层SAC天然最佳；连接器间隙留空，不补数。[B2全文§III、IV、TableII/III](https://arxiv.org/html/2110.12618v1)
- **B3 Recovery-Aware HIL-SERL**：作者PDF§3.4/4.3用人工挑选恢复轨迹，Demo/RL/Recovery按4:4:2采样；真实USB硬接触需撤退再靠近，20次/方法，恢复55%→90%、10.16s→8.63s。三相机及人工介入；无定量间隙/联合roll-pitch误差。阶段编码和恢复经验偏采样已有先例，人工gate不是自动学得的恢复触发；不要把所有提升归给F/T历史。[作者PDF](https://sgh21.github.io/USBInsertionRL/static/pdfs/Recovery-Aware%20HIL-SERL%20for%20Contact-Rich%20USB%20Insertion%20with%20Global%20State%20Encoding.pdf)
- **B4双臂2026**：机构摘要明确视觉+F/T+pose history预测6D残差、受约束传统baseline+bounded RL补偿jam/接触切换，报告100实机试次；全文、几何、精确误差与公开日期未可核。因此只是“这个组合已有人提出”的检索警报，不作为当前平台可复现对照或严格截止优先权证据。[机构记录摘要/状态](https://ntut.elsevierpure.com/en/publications/coordinated-dual-arm-robotic-assembly-based-on-reinforcement-lear/)

以上已有工作不能相互叠加成“同一论文解决了全部九针联合误差”，也不能因没有完全一致任务就断定本候选新颖。需要进一步找最相近机制并验证技术增量。

## 4. 与现平台对齐：事实、推论和假设分开

**静态已核事实**：当前 [observation.py](../../../tools/learning/observation.py) 已有4次控制采样wrench、relative pose、velocity、base_command、previous_limited_command、previous_residual、stall progress/span；[v4_observation.py](../../../tools/learning/v4_observation.py)追加drive/reference及控制器摘要。源码明写不保证完整Markov状态。4个控制时刻、总跨度6ms的力历史是很短的窗，不是完整搜索/卡滞过程。以上只读文本，未导入模块。

所以，“再加上一步动作”“给网络137维”“加GRU”“按阶段门控”均不能单独作为技术贡献。当前已有命令和运动信息，候选增量须是其使用方式与作用机制。理想净wrench也不自动等于能够看见各针/外壳接触；多个不同接触分配可以具有相同合力/合矩，但在当前小范围是否实际出现、是否影响决策尚未建立。

**优先假设 H1：动作条件的接触响应指导协调四轴修正。** 给定对齐时间戳的窗口 `已限幅执行命令/实际ΔXY与Δroll-pitch/wrench/ΔZ进展`，估计若实施一个允许范围内的小四轴修正，将产生的 `Δwrench及ΔZ进展` 与可信度。决策利用这一响应预测同时选择平移与转动方向；当预测无法区分或响应不稳定时保持已有规则/保护。它不必声称准确反演四维绝对孔误差，也不能假装能看见每针接触。

这比“当前矩大就转、当前横向力大就平移”多了动作—响应因果线索，但**尚未证实**动作窗足以区分横向偏置与倾角导致的阻塞。普通GRU预测器只是实现选项；需要具体的候选动作后果预测、歧义处理和协调规则。保留规则Z、既有保护与固定恢复，使第一次问题验证不依赖Z权限/增益/恢复事件同时变化。

**响应估计可以先不学习**：以相同信息与预算，用局部有限差分/正则最小二乘估计4轴动作到wrench/进展的响应，再选小幅协调修正。这是H1必须打败的传统强对照。局部响应不保证光滑或满秩；低秩/接触切换时不能强行求逆。理论上的6输入/4动作维数也不是可观测性证明。

## 5. 排序、平台变化与最强否证

| 顺位 | 候选方法与用途 | 必要平台变化（未实施） | 最强反驳/停止理由 |
|---|---|---|---|
| 1 | H1：动作条件响应预测+小幅协调XY/roll-pitch修正。优先验证机制而非算法牌子 | 可保持4轴接口、Z/保护/固定恢复；保证命令—实际运动—F/T窗对齐；定义候选动作评分/不确定性；如改观察窗需新版本和重新准入 | 同信息局部线性响应或简单矩/力分配就能同样解决；当前基线并无稳定联合误差缺陷；所谓收益来自更大动作权限/更高力 |
| 2 | 被动历史条件actor/encoder：用作最低改动学习基线与H1消融 | 对齐较长事件窗，保存动作和运动序列；时序回放/隐藏状态重置，不能沿用旧checkpoint资格 | Inoue2017、Ding2019与旧包Beltran2020已有重叠；仅循环网络无特定机制，或延长历史未增加决策信息 |
| 3 | H1+有成本的局部主动探测：只在响应歧义高且允许时做小四轴探测 | 探测动作/幅度/时长预算、结果历史和接触保护；如果必须卸载Z才能探测则已有权限不够，需单独方案 | Ding2019已有直接先例；固定对称探测/同样额外搜索时间即够；探测收益被力、耗时或失败成本抵消 |
| 4 | 学习恢复触发/选择固定恢复：仅若固定恢复时机成为主要瓶颈再考虑 | 新监督事件接口；固定恢复几何/保护不变，新增超时/停滞与误触发统计。当前4轴残差不能等同Z撤退权限 | M5时间规则已强；B3恢复采样已有；误触发损害本来能完成的试次。初期非必要，不能为显得复杂而增加 |
| 5 | 在线导纳残差/M1路线 | 开放M/K/D或有限增益参数，实时优化与独立稳定性/负载检查；未来实机传感与sim-to-real验证 | 当前没有相应模型缺陷/部署任务；M1手调已成功且峰值更低；扩大权限后不能归因当前4轴策略 |

纯固定阶段门控、纯SAC替换、未说明响应机制的“GRU+残差”不建议作为核心方法。H1在科学意义上仍可能只是局部响应控制的学习实现；若不能超过恰当解析/非参数基线，应该保留工程结果并否定学习必要性，而不是继续包装创新。

## 6. 建立价值所必需的评价设计（建议，未执行）

1. **先定位缺陷**：在共同、合法的联合XY/roll-pitch范围内，以纯B2与至少一种同信息协调力/矩或局部响应控制比较；四点只能做开发示例。先核旧J_zero可比性，不能拿随机F0代替纯B2。成功率饱和时才以受保护的总耗时/搜索耗时为主要问题；不得人为缩时间或加错误让传统必败。
2. **证明历史有用**：找出即时wrench相近但下一合适修正不同的实际案例；比较单次wrench、现4样本、较长被动窗、动作条件窗。打乱动作—响应对齐、去掉实际运动增量、仅增加同等参数量的MLP，区分记忆/容量/因果线索。隐接触真值只能供离线解释或监督标签，不进部署actor。
3. **证明协调有用**：相同动作边界比较仅XY、仅roll-pitch、独立规则分配、联合响应决策；保留共同Z、保护、恢复。几何上若某阻塞需要退出Z后重置，四轴学习不应被强求解决。
4. **证明需要学习**：共同信息、相同调参/执行预算下比较局部线性响应、非参数查表/回归、固定小探测、历史actor及H1。预先登记开发/留出工况，跨初始误差方向、摩擦、可用传感噪声/延迟，避免只记住四个点。
5. **归因探测和恢复**：被动H1 vs固定探测+H1 vs按可信度探测；共同探测次数/接触时间预算。恢复若另行开放，则无恢复、停滞/超时触发、学习触发共享同一固定撤退动作；单列触发正确率、漏检、误触发及原本可成功试次损害。
6. **报告完整结果**：所有尝试保留，任务失败/保护失败/无效仿真分开；包括总预算内成功、总耗时与失败代价、wrench峰值/持续负载、搜索/恢复次数，避免仅成功试次平均时长。策略种子与重复试次另列，不混成“独立样本”。保持电气/损伤/弹性证据缺口。

上述建议不构成计算授权。所有先前预算关闭；第一次新科学运行仍须按主项目登记、方案和准入处理。

## 7. 检索轨迹与未解决访问限制

检索日期2026-10-10。查询包含：`Transferable Force-Torque Dynamics Model for Peg-in-hole Task`；`Tactile-based Active Inference for Force-Controlled Peg-in-Hole Insertions`；`robotic insertion learned failure recovery strategic retraction reinforcement learning contact wrench`；`insertion recurrent force multi-peg`；`insertion awareness multi-contact reinforcement learning`；`Deep Reinforcement Learning for High Precision Assembly Tasks Inoue PDF`；`InsertionNet multi contact`；`Learning Insertion Primitives with Discrete-Continuous Hybrid Action Space pdf`。检索页及综述只作定位；技术事实仅取上表一手源，不引用聚合平台的自动摘要。

追溯：M1 ref1→M3、ref2→B2；M2介绍/§IV-A→多姿态力歧义；M5§IV-C→历史预测/Time-only对照；作者项目→B3原PDF；作者机构→B4 DOI。未继续扩大论文数量，因为已有先例足以排除“历史/探测/门控本身新”的前提。

限制：M1 PDF可读19页文本，但截图服务返回不可用，Table2提取缺行，故不填写该表四类对象的全部精确数值；其总训练步数、窗口T数值未核，不自行反算。M4错误v3地址不可读，改为元数据实际存在的v1；未将不存在版本当新版。作者书目访问曾报内部错误，搜索返回原作者内容能核到2026 SII书目，但正式稿未比对。B4 DOI读取失败，仅机构摘要，不推断精确发表日期/样本规则。M2及M3的间隙定义与本项目径向公差有区别；各任务成功率、步数、传感条件不可直接横比。本轮不是完整系统综述，不能保证未遗漏更近先例，也不能保证论文录用或最终新颖性。

交付检查：链接使用一手源；事实与本研究者推论/待验假设分开；未补缺失量；当前平台信息/动作权限不外推；源文档、代码与历史结果未改。
