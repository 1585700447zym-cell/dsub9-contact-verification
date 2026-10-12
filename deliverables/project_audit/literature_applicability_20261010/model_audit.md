# 模型、信息、动作与旧档案适用性核查

2026-10-10。当前阶段：B.2 第3项的步骤1+2前置核查；本报告完成静态适用性审查，不构成新增科学执行准入。实际工作目录及分支已核对为 `.worktrees/dsub9-v1-contact-validation` / `feature/dsub9-dynamic-actuator-v1`；既有未提交文件保留。仅使用源码/文档读取和标准库 JSON/gzip/XML/hash 解析，新增仿真、科学库导入、模型加载/推理/更新均0。

**结论：优先验证“有限搜索与恢复的效率瓶颈”具有本地线索；尚未证明当前联合四点的合理纯B2存在可重复缺陷。** 旧负Y纯B2成功但搜索两轮并恢复，用时20.780s，是一个具体开发点线索；它不能推导高失败率、联合扰动普遍缺陷或学习优势。当前四点F0/F2000各功能4/4、效率改善2.77%未过旧10%门，以及附加精度4/4→0/4，证明的是既有学习链和该开发比较的结果；F0不是纯B2。终末漂移宜先作为约束/次级诊断，80μm/0.5°尚无真实产品质量依据。

本次当前性依据为 `项目当前入口.md:3–17`、`项目进度跟踪.md:3–17`、`研究推进计划_当前版.md` 顶部当前标记，以及 `deliverables/project_audit/research_plan_20261010/研究问题与证据推进计划表.md:3–13,23–27`。SCOPE21历史“下一项改精度奖励”已被最新计划替代。

## 1. 有效模型与范围

有效版本以 SCOPE20 的 `deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009/configuration.json`（下称 **S20配置**）和同目录 `model.xml` 为准。静态核对其 `common.frozen_common_source_sha256` 中本报告使用的七个核心文件均与工作区字节一致：`layered_task.py`、`observation.py`、`v4_observation.py`、`v4_action.py`、`v4_session.py`、`cartesian.py`、`reference_search.py`。机器摘要见 `model_evidence.json`。这不是对全部2173绑定输入的重新验收。

| 项目 | 当前有效事实 | 可验证现象 / 限制与定位 |
|---|---|---|
| 几何 | 9个刚性圆柱针，直径1.00mm、长4mm；上排5针/下排4针，X间距2.77mm，两排Y=±1.42mm，针中心Z=2mm | S20 `model.xml` 的 `pin_01…pin_09`；`tools/model/clearance_task.py:15–24`。能够表达多针共同位姿导致的不同接触/几何余量，不能表达独立针弯曲 |
| 孔与配合 | 主孔径1.20mm，入口径1.35mm、入口深0.25mm，总孔深4.5mm；两层各256面凸分解，共4608孔碰撞geom | S20配置 `common.geometry_referee.layers/segments`；`tools/model/layered_task.py:15–27`。名义主孔径向间隙100μm、入口175μm，是几何推算，均不是制造商规格 |
| 外壳/有限接触面 | 模型实际有78个 `male_guide_collision` 和42个 `female_socket_collision` mesh；碰撞类别4/8互配。针孔类别1/2互配，视觉geom碰撞关闭 | S20 `model.xml:6,14–21,542` 及male尾段。不能误称只有针没有外壳；可讨论模型内刚性D形导向/有限表面接触。无相机、视觉特征、弹性外壳或电气插合质量；不能直接等同视觉DB-25实物论文 |
| 刚体/执行器 | 固定female＋单个6自由度male；male质量0.05kg、主惯量各2e−5kg·m²，重力0。虚拟有界笛卡尔PD驱动，非完整机械臂/夹爪 | S20 XML `body/inertial/freejoint`；`tools/dynamics/cartesian.py:63–81,211–237`。实际位姿由积分产生，只有reset指定；惯量/刚度未标定 |
| 接触/摩擦 | native碰撞、MuJoCo3.13绑定；XML friction=`1 0.005 0.0001`，solref=`0.02 1`，solimp=`0.9 0.95 0.001 0.5 2`，margin0，CCD容差1e−12 | S20 XML:3,9–21；S20配置 `common.dynamic_config.collision_backend/runtime_proof_sha256`。数值接触有柔顺求解参数，不等于针脚材料弹性；未作实物力标定/摩擦辨识 |
| 时间/运动范围 | 物理0.2ms、控制2ms；命令平移1mm/s、转动0.03rad/s，变化率5mm/s²/0.3rad/s²；动作25s，裁决最多1s，真实停稳尾段另计 | S20配置 `common.dynamic_config,b2_config,metric_version`；共同协议 `docs/stage_b/论文对照协议_v4.md:9–11,30–32`。实际运动守卫20mm/s、0.5rad/s、行程6mm；这些不是部署性能 |
| 初始化/资格 | J01=(+75,+75,+.25,+.25)、J02=(−75,+75,−.25,+.25)、J03=(−75,−75,−.25,−.25)、J04=(+75,−75,+.25,−.25)，单位μm/°；yaw0，Z−4mm、目标4mm | S20配置 `cases` / `methods.F50.joint_cases`；SCOPE12 `joint_contract.py:34–56`、`joint_rollout.py:22–30`。顶层逐点字段覆盖继承的 `common.initial_pose` 零倾角，不能读取后者误认为当前无倾角；普通reset拒绝初始接触 |

当前保护候选允许初始roll/pitch各≤0.5°、相对起点总转角≤2.5°（S20配置 `common.guard_config`，`tools/learning/guarded_environment.py:71–77,115–117`），但“代码允许”不等于整个范围有资格。当前有证据的首轮联合范围仅上述四个离散点。原合同XY各±100μm、roll/pitch各±1.5°是计划扩展域（`docs/stage_b/训练合同_v3.md:94`），当前不能宣称覆盖。

## 2. 策略与裁判的信息来源

| 信息 | 来源/维度 | 边界与证据 |
|---|---|---|
| 六维接触wrench | M点、世界轴的净接触力/力矩；4个控制时刻历史24维，历史跨度6ms | `tools/learning/observation.py:1–4,98–99`。仿真理想量，不是实测带噪F/T；未提供单针/外壳接触分解或周期内峰值历史 |
| 本体运动 | 相对reset位置/姿态、世界速度、最大Z推进；参考相对当前位置误差 | `observation.py:100–103,140–141`。复位后初始绝对XY/倾角被相对化，不直接给孔位/目标正姿误差；不能以奖励真值推断actor已获得该信息 |
| 控制器/保护状态 | 基础命令、前受限命令/残差、阶段与权限、计时、受阻进展、导纳状态、搜索原点/角度、守卫与剩余预算 | `observation.py:104–138`。显式控制器摘要改善有限记忆输入，不证明完整Markov性 |
| v4追加17维 | 相对驱动参考、搜索参考XY与有效位、峰值Z/净推进剩余、风险/负载计时、重锚计数与上次过滤比例 | `tools/learning/v4_observation.py:24–38`；S20配置 `methods.F50.width=137`、`schema[0…].source/start/width`。总120+17=137，已知偏置不直接可见 |
| 特权评价 | 初始工况、绝对全局位姿、九孔/针几何、穿透/接触数、完成/保护及奖励裁决 | `tools/learning/v4_session.py:46–47`、`tools/model/layered_task.py:3,84–108`；原始档案 `case,simulation_case,trace,source_session_outcome,outcome`。用于环境/裁判/日志，不是137维孔真值输入 |

S21 `diagnosis.json.initial_observation_identical_across_all_eight=true`，且同一actor首动作一致：只能否定“首步直接按未知象限纠偏”的期待。接触后的反馈会变化；不能由初始一致判整个回合不可学习。任何视觉定位、力传感噪声、单针接触信息或主动探测扩展都需另建信息协议和共同比较，当前没有这些证据。

## 3. 动作权限、搜索和恢复

| 方法/动作 | 有效权限 | 能应对什么 / 不能推出什么 |
|---|---|---|
| 纯B2 | 固定四轴导纳XY/roll/pitch，INSERT轴向1mm/s；受阻后UNLOAD，SEARCH采用螺旋目标有限差分＋参考跟踪，XY导纳冻结、角导纳保留、Z作8mN力调节 | `tools/control/fixed_admittance.py:14–18,44–50`；`reference_search.py:49–101`。能表达接触纠偏、有限搜索与回撤；无孔真值，不主动控制yaw；不保证任意几何都可恢复 |
| F50（当前普通残差） | a∈[−1,1]^4 → VX,VY,ωX,ωY，尺度50μm/s、50μm/s、0.0005rad/s、0.0005rad/s；仅获准INSERT/SEARCH可用 | `tools/learning/action.py:16–36`、`v4_action.py:6`、`v4_session.py:19–20`。不能学习直接Z/yaw控制、改变恢复次数、裁判或预算；非零请求不等于全部送达或物理收益 |
| S50/G50/小固定边界 | S仅SEARCH；PC09 G接触门控/SEARCH；F12.5为部署较小固定尺度，非匹配训练出的强基线 | 必须区分actor、许可和训练分布。PC09部署敏感性不等于G训练优劣；不能直接用它解释联合四点 |
| 共同限幅/参考边界 | INSERT XY±0.5mm/s、SEARCH±0.3mm/s，角±0.02rad/s，再速度/变化率限幅；SEARCH参考圆120μm，当前步过滤及下一零动作可行性记录 | `action.py:40–66`、`v4_action.py:15–47`、`v4_continuation.py:28–47`。日志 `requested_residual/applied_residual/effective_command_delta/actual_end_limited_command`分层；命令层反事实不是实际运动反事实 |
| 搜索/恢复预算 | 最多2次SEARCH、每次8s、螺距40μm、速度150μm/s、实际XY相对搜索原点上限200μm；净Z推进超入搜索时冻结旧峰值100μm才退出。最多1次物理回撤250μm、实退≥200μm、低负载真实停稳后恢复 | S20配置 `common.b2_config`；`axis_search.py:49–51,78`；`cartesian.py:155–170`。参考圆并非实际搜索覆盖面积或孔捕获域；有限权限可能造成耗尽，但该因果尚需受控证据 |

## 4. 裁判、载荷与资格覆盖

| 判据/资格 | 实际定义或已有证据 | 限制 |
|---|---|---|
| 功能完成 | 九针在实际entry/main层内检查最小面余量，全部九针须与main层重叠，轴Z≥.99，余量≥−1nm；Z绝对≤20μm、线速≤10μm/s、角速≤.001rad/s、力<25mN、G点力矩<.5mNm、穿透<30μm，保持100ms并通过全回合峰值/停稳/有效性审核 | `layered_task.py:26–27,84–108`；`tools/learning/session.py:179–195`。1nm是数值容差。`functional_finish`没有XY80μm/总角0.5°额外门；不能把配置字典里存在字段误认作已执行 |
| 附加严格精度 | 全局载体原点XY范数≤80μm、相对目标正姿总转角≤0.5°，另列 | S21 `diagnosis.json.additional_precision_successes/records`及 `结果说明.md`“功能与附加精度”。不是针孔最小裕度，也不是产品公差/电气插合认证；改变主判据必须新开发协议 |
| 力/力矩 | `qfrc_constraint`转换为世界净接触wrench；M为male原点/COM，G=M+R(0,0,−14.5mm)，扭矩转移包含力臂。驱动力另列且按分量限幅50mN/2mNm | `cartesian.py:74–81,110–122,129–135,228–236`。净合力小可能来自多接触抵消，不能推断每针载荷小/无损伤；驱动力不是接触力 |
| 保护/负载 | 子步检查净力25mN、G矩.5mNm、穿透30μm；80μm穿透为无效边界。旋转/实际运动另守卫；周期/全回合峰值包含尾段，奖励使用周期峰值 | `guarded_environment.py:99–117`；`tools/learning/environment.py:22–29`。离散触发并真实停止不保证绝不超阈值；未标定载荷仅支持相同模型内比较；2ms采样力积分不能叫子步积分 |
| 联合预检SCOPE10 | 12/12固定动作/工程恢复均有效停稳、功能成功；A/B四轴正负接触作用/峰值重叠，R4/4实退254.143μm | `b2_joint_preflight_execution_20261009/结果说明.md:15–26,40–42`。应力序列和工程触发恢复不是学习样本/自然恢复概率 |
| 原3处缺口 | J03_A_AXIS、J04_A_AXIS快速1周期块各56周期，J02_B_CORNERS48周期，与周期末接触无重叠，接触且许可/有效作用均0 | 同报告:30–38；`coverage_gap_evidence.json`对应profile/hold块。只是时序未重叠，不是已证明物理无效；原逐profile门保持未通过 |
| SCOPE11/12收窄资格 | 公开事后合并同J的A/B，快速接触有效周期25/28/32/30，长保持1428/1767/2341/2510，下一观测有非零六维wrench；维持四轴正负、保护与工程恢复 | `b2_joint_coverage_review_20261009/recommended_gate_v2.json.each_joint_case_require/scope/removed_requirement`；SCOPE12报告:5–9。支持有限四点开发准备，不填补逐profile缺口，不证明充分可观测、任意连续动作或±1.5°域 |

当前奖励为最大Z推进+5、时间−.1dt、归一化周期F/T平方代价、功能成功+10，无终末XY/角度项（`tools/learning/reward.py:19–35`）。这说明若另设精细对中目标需要评价目标一致性，但不能证明改奖励必然解决，更不能先用未经依据的80μm制造算法优势。

## 5. 旧档案复用表

共同模型哈希均为 `dbb662662dffc48d002e4bc26963d5192f13ff3be20764eac821f8fd10e861cf`；PC07/09/10共同键为 `199f0f49…627b5`，S20联合键为 `d06ace13…adfd`、`parent_common_key`指向前者。相同模型/控制/运行时并不自动产生相同工况、方法、会话封套或比较分母。

| 归档 | 可复用内容 / 真实数字 | 版本及用途边界 |
|---|---|---|
| PC07 `frozen_comparison_20261007` | 五个开发点同版纯B2/F/S＋四个冻结后首次位置；五点B2/F2000/S2000各5/5、罚时均值12.706/10.564/10.5228s；四新位置各4/4、10.950/11.1265/11.101s，附加精度各0/4 | `configuration.json.common_key/attempts/inherited_development`；`assessment.json.records/metrics`；报告:19–48。零倾角位置证据；首次四位置已消费，后续调参不得继续称未见测试。单种子，当前正式独立测试数仍0 |
| PC09 `contact_gate_probe_20261007` | 对中/负Y两点B2/F50/F12.5各2/2，G1/2；均罚时12.555/7.288/7.992/15.165s，G负Y普通失败按26s；4份B2/F50轨迹与旧档案一致 | `assessment.json.records/metrics/baseline_continuity`。同199f键、冻结actor部署敏感性；不是新训练强基线，不当作新增独立样本 |
| PC10 `search_path_comparison_20261007` | 上述负Y既有4档案、28465周期、5段SEARCH；G两段净推进−6.140/−6.355μm，S首段+100.021μm后退出；命令/参考核对无执行错误证据 | `configuration.json.archives/common_key`、`diagnosis.json.records/search_segments`。描述性开发分析，演员/权限/前史未隔离，不确证唯一机制；不增加回合样本 |
| SCOPE06/12联合零残差参照 | J_zero四点功能4/4，用时7.920/8.436/9.242/10.010s；来源/位姿/模型与共同参数静态核对 | `b2_joint_sac_preparation_20261009/baseline_equivalence.json.rows[].role/common_parameters_equal`。接受为开发背景参照；wrapper不同，不宣称字节轨迹完全一致，旧 `model_scope_qualified=false`保留。尚未建立同当前四点完整纯B2配对评价 |
| SCOPE10/11资格档案 | 四点A/B动作时序、信号、峰值与R工程恢复资格，可定位已有覆盖与3处缺口 | 原始固定动作不是actor性能/自然恢复概率；S11是事后开发修订，不能称独立测试 |
| SCOPE20续训 | 2000批更新；继承S13 F0四份和预热四份；新9/9回合包括4online+4final+1restore；F0/F2000各4/4、8.906→8.6595s、改善2.77%，未过10%；restore逐值一致 | `assessment.json.scores/relative_improvement/restore_exact/independent_tests`；S20 `configuration.json.cases/methods.F50`。仅d06ace联合四点、一个训练种子。F0随机零更新确定性actor非全零残差；restore为复现，不新增独立样本 |
| SCOPE21离线诊断 | 上述8评价档案42171周期；附加精度F0=4、F2000=0；J01慢3.096s中SEARCH+3.084s，J02省4.068s且免去卸载/搜索 | `diagnosis.json.archive_count/archive_cycles/additional_precision_successes/comparisons/records`。沿用S20，不新增物理证据；终末漂移是真实开发现象，不等于传统B2缺陷；历史下一项优先级以最新计划为准 |

### 负Y效率线索的原始定位

PC07 `assessment.json.records.development.B2[0]` 为 `(0,−150μm)`、零倾角纯B2：功能成功20.780s、峰值F24.4741mN、G矩0.257970mNm。同位置F2000=10.236s、S2000=10.760s均功能成功；两者附加精度也未通过。PC09 `records.B2[1]`补有终末XY97.607μm、`records.F50[1]`100.300μm、`records.F12.5[1]`100.796μm；后者用时11.654s。

原始 `frozen_comparison_20261007/run/dev_B2_y_neg_150.json.gz.controller_events`：0.746s轴向受阻；SEARCH1 1.526→9.150s（7.624s）后 `SEARCH_EXHAUSTED`；`events`中9.170s接受恢复、9.719s回撤完成、9.742s恢复；SEARCH2 9.742→16.886s（7.144s），净推进100.118μm后回INSERT。PC09同B2序列逐值相同，验证运行一致性；不能把重跑当第二个独立样本。搜索总时间14.768s约占任务71.07%，适合提出“为什么当前有限搜索有长尾”的竞争性解释。相同点学习策略更快仅提供候选线索；不排除传统参数/搜索起点方向合理改善，不能归因为学习必需。

## 6. 候选方向与最小补证

| 候选 | 现模型能检验的主张 | 最小缺失证据与反例 |
|---|---|---|
| **优先：位置—姿态残余误差下，有限搜索/恢复的效率与覆盖** | 当前几何、F/T、四轴纠偏及有限预算可表达；旧负Y有耗时/自然恢复线索，当前J点有接触与动作作用资格 | 先按当前联合封套把旧J_zero纳入相同评价表，核对计时/动作零/参考/裁判/载荷/恢复数；再登记纯B2与一个有合理调参机会的简单强对照（搜索起始方向/有限路径或现有参数优化）及分层开发点。若简单方法已充分解决、或瓶颈来自数值故障，停止学习扩展。扩大初始域先补对应资格 |
| 插入后段不必要残差与功能/几何余量保持 | S21显示最后INSERT漂移、无精度奖励；信息可用于阶段诊断、动作可抑制XY/角扰动 | 先明确具有功能意义的连续余量/偏差指标及来源，报告纯B2/强传统/残差共同终末分布；再受控区分演员输出、初始不确定性、阶段权限和奖励。若功能已满足且阈值无应用意义，则不提升为主问题，不预设改奖励/阶段约束有效 |
| 接触后的隐状态辨识与有限历史 | 137维有限历史的部分可观测问题可以在模型内提出 | 接触后是否存在有任务意义而难区分的状态、是否需要更长历史/主动探测尚无证据。先分析已有轨迹的竞争解释；无必要性证据不扩维。视觉高精度/弹性针损伤问题当前不能验证，应缩小主张而非移植论文能力 |

下一阶段验证提纲应固定：当前模型/共同观测/保护/裁判、零残差纯B2与简单强对照、方向×位置×小倾角层（首轮不超已有资格）、全部尝试和失败罚时26s、成功/有效停稳/保护为约束，任务耗时与恢复/搜索成本为候选主指标，连续几何余量/XY/角度及净载荷为次指标。先确认合理传统方法的不足及重复性，再选择方法；本报告不预设新回合数量、训练预算或执行授权。

本次交付只完成模型侧静态核查。文献侧应用依据、优先问题最终选定及第3项执行登记需与联合交付合并判断；无新科学执行准入，旧预算关闭，自动跟踪PAUSED。
