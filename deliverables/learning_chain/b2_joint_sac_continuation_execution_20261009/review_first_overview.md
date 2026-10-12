# D-sub9 项目交付总览

<!-- b2-scope-current -->
**2026-10-10｜当前阶段B.2第3项；任务：B2-SCOPE-20续训、匹配评价与独立恢复复现，已完成关闭。** B2-SCOPE-20四点普通SAC续训、匹配评价与独立恢复物理复现已完成并关闭。新增9/9回合全部成功、仿真有效且真实停稳，无硬保护或参考故障；正式更新尝试／完成2000／2000批。

F0与F2000同四点均4/4成功；平均惩罚任务耗时8.9060→8.6595秒，改善2.77%，未达到预登记的10%开发继续条件。J02改善48.39%，J01变慢39.29%，J03改善0.30%，J04变慢0.14%。结果支持运行链完成和有限开发点功能保持，尚不支持预期整体效率收益。

实际可训练预热链保存与独立恢复门通过后才开始在线采集；四个在线回合分别发布后完成500批更新，actor／critic／temperature／target各2000。最终完整运行状态独立恢复摘要一致，J01轨迹、动作、转移、事件、结果、停稳记录和峰值逐值一致。未额外执行恢复后的下一次梯度更新等价试验。

复用原F0评价4与预热4（19300行），不重跑旧8回合；新在线发布21671行。实际48878控制周期／488780物理子步／36751策略调用，整体监督2478.02秒（41.30分钟）；构造8／张量读取3／保存2／档案重建28（旧预热20＋新在线8）。累计动态254，一次授权已消费关闭，不重试、不结转；自动跟踪PAUSED，当前无新训练准入。

当前仍在B.2第3项“普通SAC训练与真实任务评价”。仅四个固定±75μm／±0.25°已使用开发点、一个训练种子；完整B.2/C未验收，独立测试0。原3处逐profile接触覆盖缺口及事后开发覆盖修订保持，不能由本轮成功推断连续姿态／联合范围或任意策略安全，也不能直接归因本轮效率未达标于这些缺口。

下一项（待开始）：只读取现有F0/F2000同点档案，按阶段分解任务时间、搜索路径、接触载荷、四维请求与实际命令、动作权限及奖励，优先解释J01退化与J02改善为何方向相反。提交可定位的原因证据和是否值得修改的路线决定；不加载模型或评分critic，新增物理／推理／更新0，不改10%判据、不补跑旧预算。完成离线证据后再决定是否形成新的有限候选。

[本次结果](deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009/结果说明.md)、[原始指标](deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009/assessment.json)、[独立审查](deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009/review.md)。 下方历史下一项不代表当前授权。
<!-- /b2-scope-current -->

<!-- pc14-current -->
**PC-14（2026-10-08）：小边界合成数值门通过；物理backend与训练准入仍待。** PC-14合成数值门已验收：使用冻结CPU运行时，真实同种子零起点/空优化器与回放/三个RNG、完整检查点独立进程恢复和下一步参数/Adam/回放/终末边界/RNG/采样索引逐值一致通过；仅测量wall_s排除。166项只读收口检查通过，沿用PC-13的78项纯检查证据。实际总监督用时89.34s。

本轮合成更新4/4（父3/reader1）、显式测试状态前向32/32（各16），新合成回放400行，辅助模型构造4/4、CPU张量读取3/3。新物理/子步/正式更新/性能评价均0，累计动态208；完整B.2/C未验收。798旧封存成员、1057共享输入及36runtime文件保持。

下一项只做F12.5物理backend接入与准入材料的离线准备：连接固定物理profile、零更新部署/独立恢复和原保护审核，先形成可审阅候选。2次物理预检、拟21动态/2000正式批仍需独立的新授权与逐项准入；本次4/32合成数值额度已耗尽关闭，无结转或自动重试。自动跟踪PAUSED。

本次数字只计合成数值集成；资格[numeric_verified=true/training_admitted=false](deliverables/paper_comparison/small_boundary_numeric_execution_20261008/numeric_qualification.json)。旧S/F0.39%继续门失败和PC-12两个停止上下文缺口保持。正常退出通过，额外故障/策略性能评价未进行。[结果说明](deliverables/paper_comparison/small_boundary_numeric_execution_20261008/结果说明.md)、[原始复核](deliverables/paper_comparison/small_boundary_numeric_execution_20261008/numeric_assessment.json)、[关闭账本](deliverables/paper_comparison/small_boundary_numeric_execution_20261008/authorization_closure.json)。本阶段完成后暂停汇报，下方保留历史时点。
<!-- /pc14-current -->

<!-- pc13-current -->
**PC-13（2026-10-07）：C公平对照的数值门脚本已准备，真实数值门未授权/未执行。** PC-13数值集成门脚本准备完成：授权先查、父/reader共享排他账本、全新合成数据、CPU runtime绑定、零起点与完整检查点/独立进程恢复/下一更新逐值对照脚本已实现；78项关联纯检查通过，36个runtime文件哈希核验。一轮审查修复覆盖计算收据、关闭余额、进程超时、隔离库来源和辅助开销统计；真正4批/32状态门未执行，不能记数值通过或新资格。

本轮真实学习器构造/张量读取/网络前向/优化/经验发布/物理/子步均0，累计动态208、自动跟踪PAUSED，新数值/物理/训练授权无、旧预算关闭。765旧封存文件、1057共享输入保持。完整B.2/C仍未验收。

下一项申请并核验一次新的合成数值门授权：最多4更新事务（父3/reader1）、32显式测试状态（各16），新合成400行；物理/正式训练0。获明确授权后才用已绑定CPU解释器验证零起点、完整落盘和独立进程恢复。通过也不自动开启21动态/2000正式批；实际物理backend与新的物理/训练准入仍待。

旧S/F0.39%继续门失败保持；PC-12的9750/9752命令反算与2停止边界缺口不改。本轮没有新性能结论。[准备说明](deliverables/paper_comparison/small_boundary_numeric_gate_20261007/结果说明.md)、[未授权数值候选](deliverables/paper_comparison/small_boundary_numeric_gate_20261007/numeric_candidate.json)、[授权请求（未批准）](deliverables/paper_comparison/small_boundary_numeric_gate_20261007/authorization_request.json)、[纯检查](deliverables/paper_comparison/small_boundary_numeric_gate_20261007/offline_tests.json)。本阶段完成后暂停汇报，历史下一项保留当时口径。
<!-- /pc13-current -->

<!-- pc12-current -->
**PC-12（2026-10-07）：离线适配/协议候选完成；数值恢复、物理backend、训练准入未完成。** PC-12小边界离线适配与协议候选完成：四轴F12.5物理尺度、未缩放归一化a、完整检查点外层和固定21次一次性调度已实现；53项纯检查通过。9752个既有状态中9750个命令级反算通过（7362启用），另2个停止边界无法由旧记录重建完整命令上下文，保留缺口；不是完整轨迹等价或数值恢复验收。

新增物理/子步/学习器构造/真实检查点加载/网络前向/优化更新/经验发布均0，累计208，自动跟踪PAUSED、新训练准入无、旧预算关闭；730旧封存文件与1057共享输入保持。完整B.2/C仍未验收。

下一项先实现并审阅独立数值集成脚本与runtime连接，形成最多4合成事务/32测试状态的可审阅数值门，再另行取得明确计算授权后验证零起点、完整落盘与新进程恢复。当前不启动该计算。物理backend尚未连接；21动态/2000正式批及累计229仍只是未启用提案，不能由协议通过或旧余额自动开启。

旧S/F0.39%未过10%继续门保持；本轮不产生新策略性能结论。[候选说明](deliverables/paper_comparison/small_boundary_execution_20261007/结果说明.md)、[未准入候选](deliverables/paper_comparison/small_boundary_execution_20261007/qualification_candidate.json)、[纯检查](deliverables/paper_comparison/small_boundary_execution_20261007/offline_tests.json)、[命令复算及缺口](deliverables/paper_comparison/small_boundary_execution_20261007/command_equivalence.json)、[下一数值门](deliverables/paper_comparison/small_boundary_execution_20261007/数值门清单.md)。本可交付阶段结束后暂停汇报，历史下一项保留当时口径。
<!-- /pc12-current -->

<!-- pc11-current -->
**PC-11收口（2026-10-07）：公平对照草案完成，实现/准入/执行未开始。** PC-11公平小边界登记草案完成：有条件只读继承25份B2/F0/S0/F2000/S2000评价，拟仅新增F12.5匹配训练，四轴物理尺度12.5μm/s与0.125mrad/s。拟21新动态/2000正式批（2预检＋19训练评价），数值门拟4合成更新/32测试状态单列；若以后获批，累计上限229。历史成本外推约2.10h、规划2–4h、拟整体硬限6h；不是新实测。

旧S/F用时改善0.39%未过10%门保持，补小边界对照不把旧S升级为通过。本项主要问题是小边界匹配训练的学习收益与减少对中干扰；S作参照，四轴幅度/权限差异不冒称单变量或完整因子消融。

本轮新物理/子步/检查点加载/网络推理/更新/经验发布0，实际累计208，自动跟踪PAUSED、新训练准入无、旧预算关闭。704旧封存文件及1057共享输入保持；草案完成不算新增训练能力，完整B.2/C仍待验收。

下一项只实现新F12.5薄适配与离线门，完成归一化动作/物理尺度一致、外层完整检查点、来源绑定和21次一次性驱动的可审阅候选。保持共享来源和共同key；继承门失败就停止本方案，不自动三组重训。数值/物理/训练计算须另有明确预算及准入，当前不启动。

[草案说明](deliverables/paper_comparison/small_boundary_registration_20261007/结果说明.md)、[完整设计与路线](docs/superpowers/specs/2026-10-07-small-boundary-fair-comparison-design.md)、[机器登记（非执行资格）](deliverables/paper_comparison/small_boundary_registration_20261007/draft_contract.json)、[预算依据](deliverables/paper_comparison/small_boundary_registration_20261007/budget_basis.json)。可交付阶段完成后暂停汇报；历史时点的旧下一项不作为当前授权。
<!-- /pc11-current -->

<!-- pc10-current -->
**PC-10收口（2026-10-07）：离线搜索路径证据交付已验收，完整B.2/C仍待。** PC-10离线搜索路径对照已完成：4份既有负Y档案/28,465周期，5段SEARCH/15,626周期。G两段最大净深度−6.140/−6.355μm，未超过旧峰值；参考到120μm圆后下一共同命令超界5.279/0.046nm，按原规则两次耗尽。S首段净深度100.021μm后退出并保持旧10.760s成功。启用命令、参考积分及边界公式核对无执行错误证据；不同演员/权限与前段历史未隔离，不能称唯一训练成因。停止F演员直接套G门控路线，保留匹配训练S及合理小固定边界公平对照方向。

本轮新增物理/子步/网络推理/梯度/经验发布均0，累计动态208；旧预算关闭、自动跟踪PAUSED、新训练准入无。生产1057输入及旧658封存文件保持。完整B.2/C、合理小边界重训、多种子和新的冻结最终测试仍待验收。

下一项仅准备S50与合理小固定边界的公平对照登记草案：共同零更新起点、匹配权限/尺度数据、相同登记预算和开发分布、实际成本分列；先审查新来源与保存恢复准入，再另行批准预算。F12.5现有结果只是部署缩放，不当作小边界匹配训练证据；不申请G加训、不扫描门槛或扩网络，四已消费位置不再称未见最终测试。当前不执行新训练。

[失败原因与路径图](deliverables/paper_comparison/search_path_comparison_20261007/结果说明.md)、[一页路线决定](deliverables/paper_comparison/search_path_comparison_20261007/路线决定.md)、[原始复算](deliverables/paper_comparison/search_path_comparison_20261007/diagnosis.json)、[逐周期数据](deliverables/paper_comparison/search_path_comparison_20261007/search_cycles.csv)。阶段完成后暂停汇报；下方保留各历史时点，旧“下一项”不作为当前执行授权。
<!-- /pc10-current -->

<!-- pc09-current -->
**PC-09收口（2026-10-07）：固定接触门控/较小边界部署预检完成；完整B.2/C仍待验收。** 新增8/8动态完成，累计208，7成功/1普通任务失败；8/8有效停稳，无硬保护或参考运行故障，未用0关闭，新优化/经验发布0。G50对中与B2完整轨迹相同、残差/网络调用0；负Y两次搜索耗尽，G功能1/2，B2/F50/F12.5各2/2。失败按26s罚时，平均用时分别12.555/7.288/7.992/15.165s；G较B2慢20.79%，本修复方案未达到整体任务预期。F12.5对中无接触、误差42.10μm，负Y误差100.80μm；附加80μm/0.5°为B2/F12.5/G各1/2、F50为0/2，功能与精度分列。45,660周期/456,600子步及45,660条奖励复算通过，真实网络调用/尝试21,658/21,658；4份B2/F50与旧同版本轨迹/动作/事件/结果一致。88相关检查、一次限定审查I1经作者反例关闭；生产1057输入和旧580封存文件保持，137维/4维不变。完整B.2/C及论文优势不据此验收。

**本方案结论：停止直接把现有F2000演员套上G50门控的部署路线。** G50对中完全保持B2、没有侧移/接触/网络调用，但负Y150μm两次搜索耗尽；G为1/2成功，B2/F50/F12.5各2/2。按26s失败罚时，G平均15.165s，比B2的12.555s慢20.79%；不能认定已解决任务，更不能进入正式论文优越性验收。这不是“全部残差SAC插入失败”。

F12.5可保留为合理小固定边界的候选参照：对中误差42.10μm、接触力0，负Y成功但误差100.80μm；该点比F50慢13.85%。它只是同一演员输出缩放的部署敏感性，不等于该尺度下公平重训。G的负YINSERT仅一次力阈值切换、198启用周期，SEARCH 7440启用周期；启用命令预测与执行一致，仅15周期参考缩减。数据不支持优先加迟滞或把失败归为“残差未执行”。两次搜索边界结束是既有正常恢复/预算判定，运行/保护没有故障。[具体事件与既有匹配训练S参考](deliverables/paper_comparison/contact_gate_probe_20261007/failure_summary.json)只作归因，S旧同点成功10.760s，不算本轮新增样本。

**效率优先的下一项：只用现有F/G/匹配训练S负Y档案做一次离线搜索路径对照。** 按每段SEARCH对齐入口状态、真实XY运动、参考方向、四维请求和最终总命令，核对G为何沿参考边界耗尽、S的匹配训练为何能成功；区分可定位的实现错误与仅有支持的训练/权限不匹配假设。该读取任务新增物理、训练、网络推理0，不扫描门槛、不扩观测/网络/critic。随后出一页路线决定：有具体依据才为同权限起点的一次公平短训另行登记；无依据就停止G，收缩到已有匹配训练的阶段约束及合理小固定边界对照。当前不自动签发任何新训练。

本轮固定预算8/8收口、不重试，自动跟踪PAUSED。完整B.2姿态/联合范围、C完整机制、合理对照重训、多种子和新的冻结最终测试仍待；四个旧首次位置已消费，不能重新当未见测试。阶段完成后暂停汇报。

[结果与图](deliverables/paper_comparison/contact_gate_probe_20261007/结果说明.md)、[原始复核](deliverables/paper_comparison/contact_gate_probe_20261007/assessment.json)、[账本](deliverables/paper_comparison/contact_gate_probe_20261007/run/ledger.json)。阶段完成暂停汇报；下方保留历史时点。
<!-- /pc09-current -->

<!-- pc08-current -->
**PC-08收口（2026-10-07）：残差实际作用归因已验收，候选仅为下一方案。** 离线37档案/245,221周期归因通过；已训练S八接触工况的峰值全部先于残差许可，14/14前缀与B2相同；对中F引入约100μm侧移和5.383mN接触。旧请求/即时差统计不是执行损失，总命令限幅已分列。新增动态/训练/策略调用/发布0，累计200；137维/4维及1057生产输入保持。

下一项实现并登记G50接触门控及F12.5较小固定边界的有界部署预检（拟8回合、训练0）；先通过权限/来源/保存与只读检查，才启动新预算。当前候选未实现、未准入、未执行。完整B.2/C及论文优势仍待；四首次位置已消费，旧预算关闭，自动跟踪PAUSED。 [结果与图](deliverables/paper_comparison/residual_effect_diagnosis_20261007/结果说明.md)、[最小候选](deliverables/paper_comparison/residual_effect_diagnosis_20261007/next_candidate.md)、[原始归因](deliverables/paper_comparison/residual_effect_diagnosis_20261007/diagnosis.json)。阶段完成暂停汇报；下方记录保留历史时点。
<!-- /pc08-current -->

<!-- pc07-current -->
**PC-07收口（2026-10-07）：同版本公平对照与冻结后首次位置评价完成；完整B.2/C及论文优势不据此标已验收。** 新启动27/27，采样结束27，累计200/200；183,705控制周期/1,837,050物理子步，真实网络控制76,257次；新梯度/经验发布0，未用0关闭。

开发F相对B2：用时改善16.86%，综合继续信号未满足（峰值力均值增加5.57%超过5%）；开发S相对B2：用时改善17.18%，综合继续信号满足；开发S相对F：用时改善0.39%，综合继续信号未满足（用时改善不足10%）；F学习贡献对照：用时改善23.01%，综合继续信号未满足（峰值力均值增加5.57%超过5%）；S学习贡献对照：用时改善26.75%，综合继续信号满足；新位置F相对B2：用时增加1.61%，综合继续信号未满足（用时改善不足10%）；新位置S相对B2：用时增加1.38%，综合继续信号未满足（用时改善不足10%）；新位置S相对F：用时改善0.23%，综合继续信号未满足（用时改善不足10%）。

F0/S0是同种子随机初始化、0更新的确定性策略，动作并非全零；B2才是全零残差。10份训练后开发档案只读继承PC-06；新位置四象限各一点，仿真前固定，单训练种子小样本。63关联检查通过；独立审查1 Important经两种故障RED/GREEN关闭，未二次独立复审；生产1057输入保持。原始奖励/停稳/几何、计数、状态保持及来源按实际收口复核。

本轮未支持简单SEARCH-only约束相对合理对照的稳定优势。下一项先用现有档案做离线归因：核对分阶段动作、裁剪、残差实际运动和各工况时间贡献，再确定最多一次有依据的机制调整及较小固定边界对照；暂不追加训练、扩维或降低判据。 本轮四点已消费，后续调参不能复用它们作为未见最终测试；旧预算及自动跟踪保持关闭/PAUSED。 [结果与图](deliverables/paper_comparison/frozen_comparison_20261007/结果说明.md)、[完整比较](deliverables/paper_comparison/frozen_comparison_20261007/assessment.json)、[收口检查](deliverables/paper_comparison/frozen_comparison_20261007/closure_verification.json)、[首次使用登记](deliverables/paper_comparison/frozen_comparison_20261007/first_use_registration.json)。本阶段完成暂停汇报，旧PC-06及前序记录保留当时状态。
<!-- /pc07-current -->

<!-- v4-requalification-current -->
**PC-06收口（2026-10-07）：本轮修复及有限学习pilot已验收；完整B.2未验收。F/S各2000批，冻结开发点各5/5功能成功；独立进程代表复现2/2逐值一致，28/28有效停稳，参考故障/硬保护0。S相对F平均用时改善0.39%，未达到预登记的10%开发继续信号。**

新动态28/28，累计173；190,882控制周期/1,908,820物理子步；正式更新尝试/完成4000/4000；策略控制调用78,520，发布117,108条经验（F54,776/S62,332），未用预算0。两次普通搜索耗尽失败均发布，评价/恢复不入池。原关闭余量不重开，自动跟踪PAUSED。

441项关联离线检查通过；一次限定独立审查0 Critical/Important/Minor；28份原始档案的停稳、几何、奖励逐条复算通过；18次完整检查点读取门通过。1057项输入及源码ZIP逐项核验未变，PC-03/04/05与复杂度审查原封存保持。只重绑两个登记文件，137维/4维动作、网络、奖励、几何、保护和超参数保持；没有新增学习模块。

五点均为已用开发点、单训练种子，正式独立测试0；两次恢复复现不增加性能样本。旧B2控制指纹不同，未重新贴标签比较；本轮没有证明学习贡献、S优于B2、历史critic高估消除或完整C能力。下一项优先冻结当前控制器、137维学习器和超参数，预登记同一共同版本的B2配对评价、未用范围评价及必要的重复训练种子；据成功、用时和接触载荷判断是否值得扩展阶段约束。先补公平比较和学习贡献证据，不因本轮无运行故障就新增观测或算法层。本轮预算已全部消费并收口，下一物理/训练执行需新的登记，不能复用关闭余量。

[结果与图](deliverables/paper_comparison/v4_learning_requalification_20261006/结果说明.md)、[原始复核](deliverables/paper_comparison/v4_learning_requalification_20261006/assessment.json)、[收口检查](deliverables/paper_comparison/v4_learning_requalification_20261006/closure_verification.json)、[冻结计划](docs/superpowers/plans/2026-10-06-v4-learning-requalification.md)。本可交付阶段完成，按协作约定暂停汇报。
<!-- /v4-requalification-current -->

以下保留此前时点记录，其下一项以上述当前状态为准。

<!-- search-boundary-fix-current -->
**共同搜索边界局部修复有限验收通过（2026-10-06 20:47），B.2仍未完成。** 新增3/3动态、完成3，累计145；26,395控制周期/263,950物理子步。B2零残差成功、F固定随机请求成功、S固定随机请求两次搜索耗尽后普通任务失败；3/3有效停稳、无参考故障/硬保护。正式更新、网络策略调用、回放发布和独立测试0；新未用0，旧26动态/4000批保持关闭，自动跟踪PAUSED。

共同控制器在参考圆内但下一搜索命令不可行时，任意相位沿用已有停止/回撤；当前已越界先报故障，第二次搜索正常耗尽，恢复次数未增加。S在8.754s结束第一段、9.382s真实恢复；原8.756s中断未重现，最终仍未插入，终末奖励−2。没有放宽120μm参考圆、80μm附加精度、几何或力保护；137维/4维动作与学习设置保持。

311项关联离线检查通过；一次独立审查1 Important经作者RED/修复/回归关闭，未二次独立复审。五点旧B2 16,563个SEARCH命令重算未变；新B2完整11,271点、F完整5,886点与各自旧轨迹逐值一致。两个生产文件总行数178→175，已移除第二层残差缩减，未新增学习模块。

下一项：按新共同控制指纹重新登记现有137维学习链准入及有限预算，复用现有审核/保存/恢复，完成真实训练和冻结评价。原PC-04源绑定不能沿用，本项开发数据未获学习授权；不重开已关闭执行、不加新维数或算法技巧。 [实际结果](deliverables/paper_comparison/search_boundary_fix_20261006/结果说明.md)、[原始复核](deliverables/paper_comparison/search_boundary_fix_20261006/assessment.json)、[账本](deliverables/paper_comparison/search_boundary_fix_20261006/run/ledger.json)。
<!-- /search-boundary-fix-current -->

以下为此前时点记录，其下一项以本次修复状态为准。

<!-- project-complexity-audit-current -->
**客观代码/机制审查完成（2026-10-06，未实施新修复）。** 观测120→137是追加17个控制器/参考状态，动作仍4维；三份档案22,508条观测中，新增参考组6维可由旧字段重构，尚无新增字段收益证明。新旧SAC文件有200行完全相同，活动实现需要收缩。

最新v4仅完成2个随机预热，正式更新/策略调用0；累计动态仍142，B.2未完成、自动跟踪PAUSED。本轮新增动力学/优化/网络调用0，未修改生产代码。历史120维真实训练后的失败保留，不能用本次故障解释全部历史。

停止反例中，即使允许整个速度/加速度可达矩形，下一参考最小半径仍超120μm约4.21nm。优先修共同搜索边界的提前结束/既有恢复，并区分合格任务失败与运行故障；不再先扩展观测或学习器。虚拟120μm参考圆与80μm附加定位精度、200μm实际位移保护不同。有限零残差参考重算只支持筛查软边界缓冲，不证明动态修复。

当前残差SAC还包含边界重采样和尾段目标修正，不能称未经修改的标准SAC；零残差则只执行B2。暂时冻结137维与学习设置，控制稳定后再统一精简输入/复用实现。原26动态/4000批余量保持关闭，后续动态须新登记。 [完整审查](deliverables/project_audit/complexity_20261006/客观审查与修复优先级.md)、[字段/代码核对](deliverables/project_audit/complexity_20261006/audit_metrics.json)、[参考可达性](deliverables/project_audit/complexity_20261006/reference_counterfactual.json)。
<!-- /project-complexity-audit-current -->

以下为前序时点记录，其下一项以本次审查及进度文件为准。

<!-- v4-learning-pilot-current -->
**137维学习链准入通过，有限pilot按实际结果收口（2026-10-06T17:41）。** 新增2/28动态，完成2，累计142/168；正式更新尝试0，完成0/4000（F0/S0）；余26动态与未尝试批量关闭，不结转。发布5885条经验。

420项相关离线检查与独立数值完整恢复通过。状态error，整轮已停止；11263控制周期/112630物理子步，实际策略调用0。开发继续信号：无法判断，矩阵不完整。实际问题：ValueError('Common reference failure')。 F负Y预热成功，S负Y预热SEARCH_REFERENCE_LIMIT；两者有效/停稳/无硬保护，S拒绝入池。尚未正式学习，不是已训练策略失效。

学习链实现/数值恢复通过不等于随机动作安全、学习收益或论文方法优于基线。五点是已使用开发点；独立测试0、多种子/硬件未做，B.2尚未验收。代表复现不增加性能样本。

下一项：本轮停止点已定位：零残差搜索基线已不可继续，过滤归零仍发出该基线。先补共同SEARCH边界可行性回退，再用此反例离线验证并登记新的少量动态；不重启本轮、不补26动态/4000批。 [证据与使用](deliverables/paper_comparison/v4_learning_pilot_20261006/结果说明.md)、[审查/修复](deliverables/paper_comparison/v4_learning_pilot_20261006/review.md)、[账本](deliverables/paper_comparison/v4_learning_pilot_20261006/run/ledger.json)。


本轮最终封存以[V2清单](deliverables/paper_comparison/v4_learning_pilot_20261006/delivery_manifest_v2.json)为准，[修订原因](deliverables/paper_comparison/v4_learning_pilot_20261006/封存修订说明.md)；原候选保留。
<!-- /v4-learning-pilot-current -->

以下保留前序时点记录，其下一项以上述最新状态为准。


<!-- v4-continuation-current -->
**残差边界连续性修复及单回合实测通过（2026-10-06T16:08）。** 310项相关检查通过；新增1/1动态、完成1回合，11245控制周期/112450物理子步；累计140，余0关闭。正式训练/策略推理/回放发布/独立测试0，自动跟踪PAUSED，B.2未完成。

脉冲前4574个轨迹点逐值一致；第一层滤波比例0.963296598、连续性比例0.125000、合成比例0.120412075。实际触发滤波1周期，下一零动作B2没有参考失败；审核7359个实际SEARCH参考端点，越界0。本例FULL_SUCCESS，任务判定20.730s，峰值力24.474mN。

只证明已登记负Y单脉冲的有限连续性修复；不保证任意未来动作、lead裁剪、所有物理子步或整个策略空间安全。137维学习掩码/回放/SAC/完整检查点仍需新版本准入，未沿用旧120维权重或旧训练数据；本轮不是学习收益。 下一项：补齐137维学习链准入：阶段与经验掩码、整回合发布及无效隔离、共同奖励、完整模型/优化器/回放/RNG保存恢复，绑定新会话及源/模型/runtime。通过后另签发F/S相同新零网络起点的最多28回合/4000批pilot，累计提案上限168；当前尚无训练准入。随后冻结方法和检查点，登记未用范围的独立评价及重复复现，才审查B.2验收。 [结果](deliverables/paper_comparison/v4_continuation_20261006/结果说明.md)、[独立核对](deliverables/paper_comparison/v4_continuation_20261006/assessment.json)、[审查](deliverables/paper_comparison/v4_continuation_20261006/review.md)。
<!-- /v4-continuation-current -->

### 以下为此前时点摘要；其“下一项”以本页最新状态为准

**规划增量（2026-10-03）：** 已将用户明确的论文优先、任务可调整原则写入[当前计划](研究推进计划_当前版.md)，附现有1.15 mm主孔/1.00 mm针径的源码证据与1.20 mm/80 μm候选比较。用途是决定下一共同任务版本，不是新模型或学习成果；物理、推理、优化均0，原B.2/C状态不变。候选实施后须共同重评受影响基线，旧结果保留。

<!-- stage-resume-current -->
**阶段权限配对恢复验证已收口（2026-10-03 12:43，北京时间）：保护触发后受控停止，完整配对效果尚不能判断。** [计划书](docs/superpowers/plans/2026-10-03-stage-permission-resume.md)；[结果与图](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/结果说明.md)、[机器审核](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/assessment.json)。

比较纯B2、固定XY50残差F与仅SEARCH开放的同幅度S。纯B2：成功3/4个已完成点（计划4）；F冻结末次策略：未执行冻结开发点评价（计划4）；S冻结末次策略：未执行冻结开发点评价（计划4）。

新启动7/18动态、审核完成7个新回合，另引用12个历史回合，累计109/120；正式更新尝试3500、完成3500/5000批（F2000/S1500）。19/19个已完成回合有效且停稳；代表恢复未执行，不声称恢复通过。未执行11动态、未尝试1500批余量关闭，不结转。 已记录物理子步394980；成本记录完整。

继承4个B2和8个匹配预热，重新准入后从相同零更新网络起点出发，不沿用旧150映射回放或C2000权重。成功/保护/奖励不变；本轮相关离线协议与执行审查通过不等于实际效果通过。限定单训练种子和四个开发点；正式独立测试0、多种子证据未完成，B.2及完整C能力未验收。代表复现不增加性能样本。 自动跟踪PAUSED。

下一项：归档诊断已完成，保持整轮停止。下一方案优先解决搜索末段精度退化及F停止截断S评价的问题；先明确同批次比较、分支停止口径和新有限预算，再审核是否继续，不直接补跑关闭余量。

**实际停止点与诊断：** F2000负Y恢复推进后触发力保护（0.025000337 N），终末XY155.70 μm；F/S正Y均约74 μm未成功。两组独立零状态读取均通过（67.357/65.772秒）。[归档诊断与结论](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/诊断与结论.md)记录时序、动作统计、未完成项和下一步边界；没有新增critic评分、物理复跑或训练。
<!-- /stage-resume-current -->

## 前轮交付摘要（历史口径）

<!-- stage-permission-history -->
前轮归档状态（历史）：
**阶段权限配对可行性验证已收口（2026-10-03 10:46，北京时间）：运行故障阻止完成配对效果判断。** [计划书](docs/superpowers/plans/2026-10-02-stage-residual-feasibility.md)；[结果与图](deliverables/learning_chain/b2_stage_permission_20261002/result_analysis/结果说明.md)、[机器审核](deliverables/learning_chain/b2_stage_permission_20261002/result_analysis/assessment.json)。

比较纯B2、固定XY50残差F与仅SEARCH开放的同幅度S。纯B2：成功3/4个已完成点（计划4）；F冻结末次策略：未执行冻结开发点评价（计划4）；S冻结末次策略：未执行冻结开发点评价（计划4）。

新启动12/30动态、审核完成12回合，累计102/120；正式更新尝试0、完成0/5000批（F0/S0）。12/12个已完成回合有效且停稳；代表恢复未执行，不声称恢复通过。未执行18动态、未尝试5000批余量关闭，不结转。 已记录物理子步733800；成本记录未完整，已记录量不是完整总量，未知调用不记为0。

新数据分别匹配权限，从相同零更新网络起点出发，不沿用旧150映射回放或C2000权重。成功/保护/奖励不变；92项相关离线协议和核心审查通过不等于实际效果通过。限定单训练种子和四个开发点；正式独立测试0、多种子证据未完成，B.2及完整C能力未验收。代表复现不增加性能样本。 自动跟踪PAUSED。

下一项：已定位固定60秒读取超时；先把新读取监督器接入下一执行版本，明确继承8份已审核F/S预热数据并完成两组零状态读取门，再在新登记范围中完成训练、评价与代表复现，避免重采12个已完成回合。本轮失败账本和关闭余量保留，自动训练不恢复。

读取诊断与修复：F零更新检查点完整状态离线比对通过（总65.863秒，恢复审核61.559秒），报告入口已修复；新的读取监督器5项针对性检查通过，尚未接入正式训练。原读取回执缺失与诊断末尾日志错误均保留，不补写历史成功。[诊断与最小修复](deliverables/learning_chain/b2_stage_permission_20261002/failure_diagnosis.md)。
<!-- /stage-permission-history -->

## 前轮交付摘要（历史口径）

**冻结C2000夜间筛查收口（2026-10-02 21:29）：** 冻结部署筛查完成；存在可复现评价，允许下一阶段实现准备。新增10/10动态，累计90/90，训练0；余量关闭，自动跟踪PAUSED，B.2未完成。[结果与图](deliverables/learning_chain/b2_frozen_c2000_closeout_20261001/result_analysis/结果说明.md)。

本次仅固定C2000确定性部署；原幅度0/4已测点成功。缩幅0/4已测点成功。代表复现以实际完整轨迹核验为准；当前独立评价、真正小边界训练对照未完成。

**效果判断：** 本轮没有解决策略失效：原幅度和已测缩幅均未达到四点成功目标。执行/复现通过不等于方法有效。

**下一阶段机制草案（2026-10-02）：** [仅SEARCH阶段开放残差的最小方案](deliverables/learning_chain/b2_frozen_c2000_closeout_20261001/下一阶段最小方案.md)，包含公平固定幅度基线、权限一致性检查和进入实际对照的条件。设计建议已形成，代码/训练/效果均未实施。

**100ms预热重启验证已收口（2026-10-01）：** 本方法尚未解决已观察到的学习后失效问题。C_online_y_neg_100在2000批策略下触发['FORCE_LIMIT']，周期峰值0.025161399 N；原轨迹有效性/真实停稳分别审核。 新增8/24动态、2000/5000正式批（C2000/A0），累计动态80/96、本方法累计2500批含旧故障500批。未执行余16动态/3000批关闭不结转；保存接口实际门与完整检查点按实测审计，独立测试未用，PAUSED，B.2未完成。[结果与图](deliverables/learning_chain/b2_temporal_learning_restart_20261001/result_analysis/结果说明.md)、[机器审核](deliverables/learning_chain/b2_temporal_learning_restart_20261001/result_analysis/assessment.json)。

滚动维护；最后整理：2026-10-06。用途是查找“已交付什么、怎么使用、证据在哪里”，不是第二份进度表。当前阶段、阻塞与下一项以[项目进度跟踪](项目进度跟踪.md)为准；汇报素材见[2026年10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)，[9月素材](deliverables/monthly_progress/2026-09/月报素材_2026-09.md)保留历史口径，总入口见[项目当前入口](项目当前入口.md)。

## 快速查找

最新普通SAC实际结果：[B2-SCOPE-20](deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009/结果说明.md)。

当前续训候选：[B2-SCOPE-19](deliverables/learning_chain/b2_joint_sac_continuation_preparation_20261009/结果说明.md)。

当前恢复验证结果：[B2-SCOPE-18](deliverables/learning_chain/b2_warm_restore_execution_20261009/结果说明.md)。

当前恢复验证候选：[B2-SCOPE-17](deliverables/learning_chain/b2_warm_import_repair_20261009/结果说明.md)。

当前恢复门执行结果：[B2-SCOPE-16失败收口](deliverables/learning_chain/b2_warm_reconstruction_execution_20261009/结果说明.md)。

当前恢复验证候选：[B2-SCOPE-15](deliverables/learning_chain/b2_warm_reconstruction_preparation_20261009/结果说明.md)。

当前文件并发修复与恢复来源：[B2-SCOPE-14](deliverables/learning_chain/b2_joint_io_repair_20261009/结果说明.md)。

前轮四点普通SAC试跑结果：[B2-SCOPE-13](deliverables/learning_chain/b2_joint_sac_execution_20261009/结果说明.md)。

前轮四点普通SAC接入与当时运行申请：[B2-SCOPE-12](deliverables/learning_chain/b2_joint_sac_preparation_20261009/结果说明.md)。旧覆盖复核与失败档案保持。

当前路线见[B2-SCOPE-11](deliverables/learning_chain/b2_joint_coverage_review_20261009/结果说明.md)：按初始工况合并代表性证据，建议覆盖补验0，转准备普通SAC短训。原SCOPE10结果及更正保留。

当前实际结果见[B2-SCOPE-10](deliverables/learning_chain/b2_joint_preflight_execution_20261009/结果说明.md)；B2-SCOPE-10固定12项联合点预检已执行并关闭：本轮尝试12/12，审核通过12，功能成功12、真实停稳12，未执行0项数量关闭。工程恢复覆盖4/4；A/B时序覆盖缺口3处（J03_A_AXIS、J04_A_AXIS、J02_B_CORNERS），缺口的逐周期接触／权限／有效作用分类已归档。3处快速块按原登记判据均缺少“周期末有接触且动作有效”的记录；其中J03_A_AXIS有3个、J04_A_AXIS有2个快速周期记录到周期内接触峰值，J02_B_CORNERS未记录到此类峰值。因此不能把这3处统称为“完全没有接触”，也不能据此推断改时序后的结果。本轮未达到全部登记覆盖要求，不能把有限成功升级为完整准入。

前轮实现见[B2-SCOPE-09](deliverables/learning_chain/b2_joint_admission_preflight_20261009/接入与验收说明.md)；执行申请未授权。下一项是审阅已绑定的12项新物理执行申请：8次A/B动作＋4次R工程恢复，单独静态0、训练0；每回合14500周期／145000子步、1200秒，合计174000周期／1740000子步、整体6小时，含停稳和审核。获明确新授权后才可执行，不重开旧额度或补采到通过。全部相关检查通过，也仅准备另行登记的普通SAC姿态匹配短训；C继续暂缓。

前轮方案见[B2-SCOPE-08准入设计](deliverables/learning_chain/b2_joint_admission_design_20261009/准入方案.md)；机器提案明确runner_implemented=false、dynamic_authorized=false。下一项实现B.2联合点预检候选并完成离线验收：固定A/B动作序列、单次恢复夹具、覆盖审核与一次性预算门，复用既有监督/归档；不创建环境、不推理或训练。程序和来源绑定完成后，再提交具体的新物理执行申请。P点不补采，137维、共同物理/保护/奖励保持，C暂缓。

前轮依据见[B2-SCOPE-07联合点复核](deliverables/learning_chain/b2_joint_learning_review_20261009/结果说明.md)和[下一准入路线](deliverables/learning_chain/b2_joint_learning_review_20261009/路线决定.md)。前轮[B2-SCOPE-06实际预检结果](deliverables/learning_chain/b2_rebound_execution_20261008/结果说明.md)和[路线](deliverables/learning_chain/b2_rebound_execution_20261008/路线决定.md)。本轮新grant已消费并关闭；B2-SCOPE-05保留准备时点，旧请求不是可重复执行授权。

历史范围依据见[B2-SCOPE-01范围缺项与预检](deliverables/learning_chain/b2_scope_audit_20261008/范围审计与最小预检方案.md)；后续实现按[计划](docs/superpowers/plans/2026-10-08-b2-pose-scope-preflight.md)。

| 我要找什么 | 优先打开 | 使用提醒 |
|---|---|---|
| 最新真实学习与冻结评价 | [SCOPE-20结果](deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009/结果说明.md) | 2000批、最终4/4成功、独立复现一致；改善2.77%未达10% |
| 残差边界连续性实测 | [结果/剩余工作](deliverables/paper_comparison/v4_continuation_20261006/结果说明.md)、[核对](deliverables/paper_comparison/v4_continuation_20261006/assessment.json) | 残差边界连续性修复及单回合实测通过 |
| v4残差接入有限预检 | [结果](deliverables/paper_comparison/v4_adapter_20261004/结果说明.md)、[核对](deliverables/paper_comparison/v4_adapter_20261004/assessment.json) | v4残差接入的有限预检通过 |
| 已封存v4共同对照准备 | [协议](docs/stage_b/论文对照协议_v4.md)、[结果](deliverables/paper_comparison/protocol_v4_20261004/结果说明.md) | 评价工具已完成，残差适配未准入 |
| 已封存分层裁判验证 | [结果与图](deliverables/task_variants/layered_referee_20261004/结果说明.md)、[诊断](deliverables/task_variants/layered_referee_20261004/diagnosis.json) | 分层几何裁判修复已通过，五个开发工况全部功能成功。 |
| 前轮25秒共同任务验证 | [结果与图](deliverables/task_variants/deadline25_20261004/结果说明.md)、[诊断](deliverables/task_variants/deadline25_20261004/diagnosis.json) | 已完成插入并真实停稳，但现行成功判据仍判失败；新增定位到整针保守几何裁判与分层孔不一致的问题。 |
| 前轮驱动参考一致性验证 | [结果与图](deliverables/task_variants/reference_search_20261004/结果说明.md)、[诊断](deliverables/task_variants/reference_search_20261004/diagnosis.json) | 本工况参考漂移已修复，插入推进明显改善；完整成功仍未通过。 |
| 前轮分轴搜索与净推进验证 | [结果与图](deliverables/task_variants/axis_search_20261004/结果说明.md)、[诊断](deliverables/task_variants/axis_search_20261004/diagnosis.json) | 分轴控制与净推进修复已验证，仍未解决插入失败。 |
| 前轮搜索/导纳统一参考验证 | [结果与图](deliverables/task_variants/compliant_search_20261004/结果说明.md)、[诊断](deliverables/task_variants/compliant_search_20261004/diagnosis.json) | 合成冲突修复生效，功能插入仍失败。 |
| 前轮XY导纳同步重设验证 | [结果与图](deliverables/task_variants/admittance_rebase_20261004/结果说明.md)、[诊断](deliverables/task_variants/admittance_rebase_20261004/diagnosis.json) | 同步重设生效，但负Y仍未插入成功。 |
| 前轮SEARCH载荷/参考释放验证 | [结果与图](deliverables/task_variants/search_load_20261004/结果说明.md)、[导纳饱和诊断](deliverables/task_variants/search_load_20261004/failure_diagnosis.json) | 无保护但功能失败，1/5后关闭余4，B.2未完成 |
| 前轮功能插入/共同B2风险卸载 | [结果与两图](deliverables/task_variants/functional_b2_20261003/结果说明.md)、[机器核对](deliverables/task_variants/functional_b2_20261003/assessment.json) | 正Y成功、负Y力保护；2/9后停止，功能/严格精度分别统计，训练0 |
| 阶段权限F/S配对与本轮纯B2 | [B.2/C阶段交付](#c-stage-resume-20261002)、[结果与图](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/结果说明.md) | 保护触发后受控停止，完整配对效果尚不能判断；代表恢复未执行，不声称恢复通过；B.2正式独立评价未完成 |
| 前轮冻结C2000部署与阶段交接（历史） | [结果](deliverables/learning_chain/b2_frozen_c2000_closeout_20261001/result_analysis/结果说明.md) | 本次仅固定C2000确定性部署；原幅度0/4已测点成功。缩幅0/4已测点成功。代表复现以实际完整轨迹核验为准；当前独立评价、真正小边界训练对照未完成。 |
| 前轮保存修复后的100ms效果结果（历史） | [结果与图](deliverables/learning_chain/b2_temporal_learning_restart_20261001/result_analysis/结果说明.md)、[机器审核](deliverables/learning_chain/b2_temporal_learning_restart_20261001/result_analysis/assessment.json) | C2000在线0/4，3普通失败/1力保护，程序存取已核验；新8动态/2000批，余16/3000关闭，B.2未完成 |
| 上一预检（历史）：100ms预热机制 | [结果与图](deliverables/learning_chain/b2_temporal_warmup_execution_20261001/result_analysis/结果说明.md)、[机器审核](deliverables/learning_chain/b2_temporal_warmup_execution_20261001/result_analysis/assessment.json) | 8完成回合、0未执行、训练0；采集机制预检通过，但不授予训练或证明策略修复；旧余不结转 |
| 上一准备阶段（历史）：时间相关预热（2026-10-01） | [方案、证据与图](deliverables/learning_chain/b2_temporal_warmup_design_20261001/修复方案.md)、[18协议](deliverables/learning_chain/b2_temporal_warmup_design_20261001/final_green_protocol.json) | 当时100ms预热内核已准备；2ms控制/策略/学习转移不变，入口未接、无新物理/训练；拟8动态预检未执行，不等于修复成功 |
| 冻结B独立评价结果（2026-10-01） | [结果与两图](deliverables/learning_chain/b2_actor_lr_b_eval_20261001/result_analysis/结果说明.md)、[独立审核](deliverables/learning_chain/b2_actor_lr_b_eval_20261001/result_analysis/assessment.json) | 0/2已执行点成功、2未执行，2新动态/0训练；未保持初始4/4，正X横向过冲，降率未通过修复目标；有效停稳和历史字节保持 |
| 已冻结B能否单独评价（2026-10-01前置历史核对） | [只读核对记录](deliverables/learning_chain/b2_actor_lr_b_eval_scope_20261001/evidence_recheck.json)、[当前下一项](项目进度跟踪.md#下一项交付) | B500/1011源/22运行/12交付/4149历史摘要一致；记录中的待确认/未适配是当时状态，随后已获批执行并收口，见上一行 |
| actor率有限对照停止结果（2026-10-01） | [结果与图](deliverables/learning_chain/b2_actor_lr_execution_20260930/run_analysis/停止结果说明.md)、[独立审核](deliverables/learning_chain/b2_actor_lr_execution_20260930/run_analysis/execution_audit.json)、[真实验证](deliverables/learning_chain/b2_actor_lr_execution_20260930/run/real_validation.json) | A500精确复现/B500冻结；A首点力保护停稳、B未动态评价。X偏置增大，不能宣称修复；1新动态/1000批，余新7/旧19与2000不执行 |
| actor率对照执行适配与协议准备（2026-09-30） | [执行入口与用法](deliverables/learning_chain/b2_actor_lr_execution_20260930/README.md)、[216项](deliverables/learning_chain/b2_actor_lr_execution_20260930/final_protocol_results.json)、[验收](deliverables/learning_chain/b2_actor_lr_execution_20260930/assessment.json) | 完整离线A/B、预算/监督/恢复/诊断/评价适配已接通；真实验证/A复现/效果未运行，预算另批 |
| 四预热共同起点重建（2026-09-30） | [严格版起点](deliverables/learning_chain/b2_actor_lr_origin_20260930/README.md)、[133项](deliverables/learning_chain/b2_actor_lr_origin_20260930/final_strict_results.json)、[验收](deliverables/learning_chain/b2_actor_lr_origin_20260930/assessment.json) | 22766行完整零更新状态、原请求和500抽样/随机流核对；前向/优化/物理0，A学习未复现，无新资格 |
| 独立actor学习率实现与协议准备（2026-09-30） | [修复交付](deliverables/learning_chain/b2_actor_lr_implementation_20260930/README.md)、[101项协议](deliverables/learning_chain/b2_actor_lr_implementation_20260930/final_protocol_results.json)、[验收](deliverables/learning_chain/b2_actor_lr_implementation_20260930/assessment.json) | actor率单独可配，恢复前参数组拒绝，A/B准备与分布解析已实现；真实计算0，效果未验证，无执行资格 |
| 上轮为何不达标、优先修什么、怎样避免误判修复 | [原因复核与修复建议（历史）](deliverables/learning_chain/b2_repair_review_20260930/原因复核与修复建议.md)、[当前结果](deliverables/learning_chain/b2_actor_lr_b_eval_20261001/result_analysis/结果说明.md) | 覆盖差异非唯一根因证明；actor率候选已实现和实际评价，0/2已测点成功，未保持初始4/4，不能宣称效果修复 |
| 第一次接手：技术栈、文件结构、实现与学习顺序 | [项目技术导读与学习路线](项目技术导读与学习路线.md) | 依据2026-09-29本地源码核对；含结构图与交接文字；架构导读不替代实时进度与实验资格 |
| 学习原因是否缩小、修复下一步 | [限定价值核对与图](deliverables/learning_chain/b2_force_mechanism_review_20260929/critic_probe/结果说明.md)、[实现准备](deliverables/learning_chain/b2_actor_lr_implementation_20260930/README.md) | 4检查点/20,968组为历史计算；新危险边界+9.364对−8.359，唯一原因未隔离；actor率候选已实现未验证收益 |
| 本次为何重复力保护、是否已修复 | [机制复核与对照图](deliverables/learning_chain/b2_force_mechanism_review_20260929/README.md)、[数据](deliverables/learning_chain/b2_force_mechanism_review_20260929/assessment.json) | 13档案只读；前两次失败边界已抽样5116/2134次，真实越限；无新增物理/推理/优化，未证实唯一学习成因，不冒称代码修复 |
| 本轮力保护受控停止及图表 | [停止说明与三图](deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/停止结果说明.md)、[机器审核](deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/stop_assessment.json) | 第9训练回合累计三次力保护后停止；13动态/2500批，13/13有效停稳；余19/2000不执行，跟踪PAUSED，最终评价缺失 |
| 修复后重开与简要训练界面 | [当前执行包](deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/README.md)、[启动核验](deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/startup_assessment.json)、[本机进度页](http://127.0.0.1:8766/) | 69项新检查/929输入；初始评价4/4完成且学习状态不变；本轮现已受控停止，13动态/2500批；保留32新动态/4500批原上限、累计76，旧剩额关闭。页面每5秒只读刷新；不等于策略有效或B.2验收 |
| Windows账本替换失败是否修复 | [修复与限定验证](deliverables/learning_chain/b2_atomic_write_fix_20260929/README.md)、[验收](deliverables/learning_chain/b2_atomic_write_fix_20260929/assessment.json) | 短暂读占用真实复现；有界文件重试，112项协议通过；历史占用者未知；该修复交付物理/优化0，后续重开见上行 |
| 修复后有限训练为何又停止 | [停止结果及更新图](deliverables/learning_chain/b2_force_failure_resumed_20260929/停止结果说明.md)、[核验](deliverables/learning_chain/b2_force_failure_resumed_20260929/stop_assessment.json) | 文件替换WinError 5，非原生崩溃；8回合有效停稳、144批完成，剩24次/4356批不执行，跟踪PAUSED；无学后检查点与性能评价 |
| Windows虚拟环境入口拒绝是否修复 | [修复与验证](deliverables/learning_chain/b2_windows_parent_fix_20260929/README.md)、[真实进程结果](deliverables/learning_chain/b2_windows_parent_fix_20260929/real_process_results.json)、[验收](deliverables/learning_chain/b2_windows_parent_fix_20260929/assessment.json) | 已修复，57相关检查/真实工作与恢复进程链通过；该修复交付物理/优化0；后续新资格与实际运行见上一行 |
| 合格力保护版本正式启动结果 | [入口拒绝与原因](deliverables/learning_chain/b2_force_failure_cycle_20260929/启动失败说明.md)、[机器核验](deliverables/learning_chain/b2_force_failure_cycle_20260929/launch_failure_assessment.json) | 32次/4500批已批准；唯一入口尝试因Windows启动层身份判断拒绝，物理/优化0，不自动重试，跟踪暂停 |
| 合格力保护失败如何进入学习、如何受控停止 | [限定实现与149项协议验证](deliverables/learning_chain/b2_force_failure_implementation_20260928/README.md)、[机器证据](deliverables/learning_chain/b2_force_failure_implementation_20260928/assessment.json) | 仍为失败且保留−10；采集/目标/检查点/评价统一，3项独立审查问题已修复；该前项只有规则实现，后续执行准备见上一行 |
| 保护失败为何中断训练、是否可以参与学习 | [限定规则审查](deliverables/learning_chain/b2_guard_failure_review_20260928/README.md)、[机器证据](deliverables/learning_chain/b2_guard_failure_review_20260928/assessment.json) | 四份归档/17诊断反例，确认−10终奖存在但被过滤；仅支持单独力保护规则的实现验证，不是新准入或性能改善 |
| 固定转动残差候选的正式执行与结果 | [停止结果与三图](deliverables/learning_chain/b2_fixed_rotation_cycle_20260928/停止结果说明.md)、[机器复核](deliverables/learning_chain/b2_fixed_rotation_cycle_20260928/assessment.json) | 500批后首个采集触发力保护，有效停稳、非原生崩溃；9/32启动，剩余23次/4000批不执行；初始4/4非学习收益，B.2未完成 |
| 已验证的B1/B2对照结果 | [A-02 新版共同环境基线](#a-02) | 七个固定开发工况，不是独立泛化成功率 |
| 残差观测、动作与Gym如何调用 | [B1-03 残差交互接口](#b1-03) | 接口可调试不等于SAC已接通；候选经验仍不可学习 |
| 学习库、张量权限与未训练策略验证 | [B1-04 隔离学习环境](#b1-04) | 必须用新环境解释器；未训练模型不是学习成果 |
| 策略如何续采、截断、审核及发布经验 | [B1-05 候选采集与经验池](#b1-05) | 真实候选仍拒绝入池；正向发布仅有合成数据证据 |
| 工程范围、非零动作接触与完整停止证据 | [B1-06 工程动态预检](#b1-06) | 9次初始化+17动态；有效且停稳不等于装配成功或姿态冻结 |
| 2.5°依据及模型有效性边界 | [B1-07 历史审查](#b1-07)、[B1-09 限定收口](#b1-09) | 历史未冻结结论保留；现仅固定操作触发值，不是可信角上界 |
| 时变动作、角度触发后接触停止证据 | [B1-08 动态补验](#b1-08) | 8有效停稳、0成功；该交付本身不是准入，后续限定资格见B1-09 |
| 保护、实际停止与恢复规则 | [B1-02 共同守卫候选](#b1-02) | 原规则不变；当前限定参数记录见B1-09 |
| B.1是否通过、首训参数和耗时、如何检查资格 | [B1-09 B.1收口包](#b1-09) | 7门通过、294测试通过；B.1原版本工程资格；后续有界SAC更新见B2-02 |
| 如何正式采集、审核后入池及复核原始数据 | [B2-01 正式采集](#b2-01) | 历史采集证据；实际更新见B2-02，完整恢复见B2-03 |
| SAC是否真正更新、权限及更新计数是否正确 | [B2-02 有界更新探针](#b2-02) | 16批更新可重放；完整恢复见B2-03，首次短训与开发评价见B2-04 |
| 完整训练状态能否保存、跨进程恢复和继续学习 | [B2-03 完整状态恢复](#b2-03) | 审核发布边界恢复已验收；同环境CPU；后续首训见B2-04 |
| 首次短训结果、最终检查点和固定开发集评价 | [B2-04 首训与配对](#b2-04) | 固定8点零残差B2完整成功8/8，确定性SAC为7/8；单种子开发观察，独立测试未用 |
| 为什么首训未改善 | [B2-05 离线诊断](#b2-05) | 23旧档案复算，无新增训练；后续诊断见B2-06/07 |
| 接触反馈是否有信息、残差是否实际纠偏 | [B2-06 有限接触预检](#b2-06) | 9初始化/17动态；位移门未全过，未取得新训练准入 |
| SEARCH阶段四轴动作能否改变运动 | [B2-07 SEARCH四轴诊断](#b2-07) | 8回合，8有效停稳，训练更新0 |
| 动作已接入却只产生微小运动的原因 | [B2-08 动作链诊断](#b2-08) | 11旧档案离线，新物理/更新0 |
| 后段已有运动时的残差局部作用 | [B2-09 运动状态±X对照](#b2-09) | 固定两回合预算、更新0 |
| 真实随机预热下的接触与停止 | [B2-10候选预检](#b2-10) | 最多8回合，训练更新0 |
| 四点接触短训配置和实际结果 | [B2-12执行适配](#b2-12)、[B2-13实际短训](#b2-13) | 已执行限定预算；结果与限制见B2-13 |
| 理论上是否应优于B2、当前学习卡在哪里 | [B2-14效果审查](#b2-14) | 已确认终末价值拟合不足；尚未修复，不等于证明SAC无效 |
| 固定策略价值对照做到哪里 | [B2-15对照记录](#b2-15) | 修正版有效对照完成：终末拟合改善，可动作边界仍未达标；首轮作废保留 |
| Python访问违规崩溃的原因与修复 | [原生容量修复](#b2-native-repair) | EPA临时数组越界已定位；修复通过故障现场和6311周期完整回合，正式运行库资格待建立 |
| 为什么改用隔离新版接触路径 | [H-04 可靠性诊断](#h-04)、[A-01 新版复验](#a-01) | 旧问题与失败保留，不跨版本拼接性能结论 |
| 早期模型、动力学和传统控制资料 | [历史能力与诊断](#history) | 历史文档中的“当前/下一步”指归档时点 |
| 暂定论文主张、指标和本轮停止结果图 | [暂定指标口径](deliverables/learning_chain/b2_repaired_cycle_v2_20260928/指标与图表口径_暂定.md)、[固定转动候选三图](deliverables/learning_chain/b2_fixed_rotation_cycle_20260928/停止结果说明.md) | 两轮停止结果各有三图；当前图分列初始、随机采集及未执行阶段，最终/独立评价与创新方法图仍缺失 |
| 图、动画和可直接讲的内容 | [本月图表清单](deliverables/monthly_progress/2026-10/月报素材_2026-10.md#figures) | 每份素材标明版本、结论和不能支持的说法；9月资料保留历史口径 |
| 复现、交互显示与旧报告目录 | [可视化指南](VSCode与MuJoCo可视化仿真指南.md)、[历史报告总索引](报告总索引.md) | 旧SDF/MPR模型与新版native验证入口不能混用 |

## 通用使用边界

- 实际工作目录：`D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation`。继续使用该现有工作树，不从主分支建干净副本替代。
- 新学习接口依据[训练合同v3](docs/stage_b/训练合同_v3.md)；v2与旧报告保留其历史意义。
- 本表按已取得的证据索引能力。不能因同一工况在多个版本重复回归，就累计成更多独立评价样本。
- 每个交付编号保持不变。后续增加条目或注明替代关系，不删除失败版本，不覆盖原始记录和校验清单。

## 基线与接口交付

### B2-SCOPE-20｜四点普通SAC实际续训与匹配评价（2026-10-10）

B2-SCOPE-20四点普通SAC续训、匹配评价与独立恢复物理复现已完成并关闭。新增9/9回合全部成功、仿真有效且真实停稳，无硬保护或参考故障；正式更新尝试／完成2000／2000批。

F0与F2000同四点均4/4成功；平均惩罚任务耗时8.9060→8.6595秒，改善2.77%，未达到预登记的10%开发继续条件。J02改善48.39%，J01变慢39.29%，J03改善0.30%，J04变慢0.14%。结果支持运行链完成和有限开发点功能保持，尚不支持预期整体效率收益。

实际可训练预热链保存与独立恢复门通过后才开始在线采集；四个在线回合分别发布后完成500批更新，actor／critic／temperature／target各2000。最终完整运行状态独立恢复摘要一致，J01轨迹、动作、转移、事件、结果、停稳记录和峰值逐值一致。未额外执行恢复后的下一次梯度更新等价试验。

复用原F0评价4与预热4（19300行），不重跑旧8回合；新在线发布21671行。实际48878控制周期／488780物理子步／36751策略调用，整体监督2478.02秒（41.30分钟）；构造8／张量读取3／保存2／档案重建28（旧预热20＋新在线8）。累计动态254，一次授权已消费关闭，不重试、不结转；自动跟踪PAUSED，当前无新训练准入。

当前仍在B.2第3项“普通SAC训练与真实任务评价”。仅四个固定±75μm／±0.25°已使用开发点、一个训练种子；完整B.2/C未验收，独立测试0。原3处逐profile接触覆盖缺口及事后开发覆盖修订保持，不能由本轮成功推断连续姿态／联合范围或任意策略安全，也不能直接归因本轮效率未达标于这些缺口。

下一项（待开始）：只读取现有F0/F2000同点档案，按阶段分解任务时间、搜索路径、接触载荷、四维请求与实际命令、动作权限及奖励，优先解释J01退化与J02改善为何方向相反。提交可定位的原因证据和是否值得修改的路线决定；不加载模型或评分critic，新增物理／推理／更新0，不改10%判据、不补跑旧预算。完成离线证据后再决定是否形成新的有限候选。

[本次结果](deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009/结果说明.md)、[原始指标](deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009/assessment.json)、[独立审查](deliverables/learning_chain/b2_joint_sac_continuation_execution_20261009/review.md)。

使用：verify_closed.py只读核验；完整检查点位于该交付run/checkpoints/final。当前授权已关闭。

### B2-SCOPE-19｜预热状态接入续训链（2026-10-09）

B2-SCOPE-19预热状态接入续训链及四点匹配评价候选已完成离线实现和独立审查，19项标准库检查通过；实际训练链恢复与续训尚未执行。

新增适配入口从SCOPE18已验证封套恢复普通SAC训练链；只把外层状态的binding换成独立的新授权，4份旧预热档案和收据字节保持。旧预热须逐份hash匹配，新的online来源须使用新授权。安装模型／优化器／温度、回放、终末边界和三个随机流，同时补齐预热审核随机流、累计抽样数与held动作；先核对完整安装状态，再保存并交给独立进程核对包含运行字段的完整状态，通过后才创建首个物理环境。

本轮科学库导入／模型构造／张量读取／预测／优化／物理／新经验均0，累计动态245、自动跟踪PAUSED。SCOPE18旧预热组件恢复数值通过仍有效；SCOPE13原F0评价4与预热4成功、文件访问失败，以及SCOPE16导入失败均保持。新候选未签发grant、未消耗claim，不重开任何旧授权或未用次数。

仍在B.2第3项“普通SAC训练与真实任务评价”。当前四点路线正式更新0、训练后评价未执行；原3处逐profile接触覆盖缺口和事后开发覆盖修订保留。范围仅四个固定±75μm／±0.25°开发点，完整B.2/C未验收，独立测试0。标准库检查与代码接入不等于真实训练链恢复通过、下一批更新等价或策略有效。

下一项：申请一次绑定本候选的新运行，新增9个动态回合（在线4＋F2000匹配评价4＋独立恢复物理复现1），每个在线回合完整审核发布后最多500批、共2000正式更新批。模型构造8、张量读取3、保存2、检查点档案重建28（旧预热20＋新在线8）；整体6小时、单物理20分钟、单reader30分钟。先过可训练预热链完整保存与独立恢复门，失败立即关闭、不重试、不结转。复用已绑定F0四点评价及4份预热，不重跑旧8回合；本次申请尚未批准，累计动态254仅为拟上限。

[本次候选结果](deliverables/learning_chain/b2_joint_sac_continuation_preparation_20261009/结果说明.md)、[具体新申请（未批准）](deliverables/learning_chain/b2_joint_sac_continuation_preparation_20261009/authorization_request.json)、[独立审查](deliverables/learning_chain/b2_joint_sac_continuation_preparation_20261009/review.md)。

使用：run_pilot.py默认只读；新执行须另有绑定候选的grant。

### B2-SCOPE-18｜旧预热恢复数值验证（2026-10-09）

B2-SCOPE-18按批准完成一次旧预热状态恢复数值验证并成功关闭，整体监督用时97.37秒，其中独立读取进程46.67秒。旧零检查点核对、预热重建、新检查点保存与独立组件恢复均通过。

父进程与独立读取进程分别从同一零起点和4份旧档案重建，完整状态摘要一致：19300行经验、14127行动作启用、388次四维均匀动作抽样（1552个标量）。独立进程已将模型、优化器、温度与随机状态写回运行对象，并核对独立重建的回放和终末边界；两次确定性预测均未改变模型或策略随机状态。本结果验证的是已登记封套内的组件状态；尚未创建可训练V4Chain或执行恢复后的下一次优化。

本次模型构造2、张量读取2、保存1、确定性预测2、旧档案重建8（父4＋独立进程4）；新增物理／正式更新／新经验均0，累计动态245，自动跟踪PAUSED。本次授权已耗尽关闭；SCOPE13原8回合、文件访问失败及SCOPE16导入失败证据保持，旧未用次数不结转。

当前仍在B.2第3项“普通SAC训练与真实任务评价”。四个固定±75μm／±0.25°开发点与原3处逐profile覆盖缺口保持，事后开发覆盖修订不撤销。当前四点路线的正式训练更新仍为0，训练后评价未做；完整B.2/C未验收，独立测试0。恢复数值通过不能证明物理续训、训练收益或论文优势。

下一项：离线接入并审查从第四份预热完整发布边界继续的训练入口，明确新封套到可训练V4Chain的转换、回放／终末边界／模型／优化器／温度／随机流及_audited_warm_rng等运行字段的恢复，形成一次有限续训及同四点训练后匹配评价的具体候选。复用已验证旧预热数据和初始评价，不重跑前8回合。先完成可审阅代码、恢复前后及下一步一致性的验证方案，再依据新候选确定计算次数、时限与准入；当前没有新训练授权。

[本次恢复结果](deliverables/learning_chain/b2_warm_restore_execution_20261009/结果说明.md)、[独立读取回执](deliverables/learning_chain/b2_warm_restore_execution_20261009/reader_reply.json)、[资格与边界](deliverables/learning_chain/b2_warm_restore_execution_20261009/numeric_qualification.json)。

使用：verify_closed.py只读复核，不加载张量；新检查点须经过后续训练入口接入与新准入才能用于续训。

### B2-SCOPE-17｜恢复入口导入规则修复（2026-10-09）

B2-SCOPE-17恢复入口导入规则已完成离线修复。相关标准库测试70项通过，独立审查已收口；本候选实际运行时导入和数值恢复尚未执行。

运行入口只为已绑定的纯NumPy工具tools.dynamics.safety增加精确名称例外；相邻模块、MuJoCo与物理环境仍被拒绝。由真实入口追踪24个仓库模块、182条立即导入记录及7条延迟导入记录，旧规则在该图中仅误拒绝safety，新规则通过源码级兼容性检查。数值重建内核、计数和失败关闭逻辑逐字保持。第三方包未执行或递归分析，延迟导入不视为已运行；该检查不等于实际恢复通过。

本轮科学库导入／物理／学习器／张量读取／网络前向／优化／经验发布均0，累计动态245；自动跟踪PAUSED。SCOPE16导入失败及关闭记录完整保留，本轮未重试。SCOPE13原F0评价4＋预热4成功、正式更新0及原文件访问失败保持；两次旧授权的未用次数均关闭，不重开、不重跑前8回合。

当前仍在B.2第3项“普通SAC训练与真实任务评价”。范围为四个固定±75μm／±0.25°开发点，原3处逐profile覆盖缺口及事后开发覆盖修订保留；完整B.2/C未验收，独立测试0。接口和离线检查通过不等于数值恢复通过，也不等于SAC有效。

下一项：申请一次独立的CPU状态重建验证，限学习器构造2、张量读取2、完整保存1、确定性预测2、旧档案回放重建8（父进程4＋独立进程4）；新增物理／优化更新／采集经验均0。整体最多30分钟，独立读取进程最多15分钟，失败关闭且不重试。通过后再准备从预热边界继续的训练及匹配评价方案；当前没有新的训练准入。

[本次结果](deliverables/learning_chain/b2_warm_import_repair_20261009/结果说明.md)、[数值候选](deliverables/learning_chain/b2_warm_import_repair_20261009/candidate.json)、[具体申请（未批准）](deliverables/learning_chain/b2_warm_import_repair_20261009/authorization_request.json)。

使用：run_suite.py可进行离线回归；run_gate.py须另有绑定本候选的明确数值授权。

### B2-SCOPE-16｜恢复门导入失败收口（2026-10-09）

B2-SCOPE-16按明确批准执行一次恢复数值门，实际监督用时10.03秒，在导入阶段失败并关闭。数值恢复未通过，原4份预热经验尚未完成本轮张量重建。

根因已由原始异常栈、源码依赖链与标准库复现确认：NoPhysics按tools.dynamics整个目录拦截，误拒绝action.py依赖的纯NumPy工具tools.dynamics.safety。此前61项离线测试通过，但漏查真实学习依赖链与拦截规则的兼容性；不能再把该测试结果当成可运行证明。这是本次首先观察到的直接阻塞，修正它仍不能推定后续恢复链可用。

科学运行时导入已开始；学习器构造、检查点读取、预测、保存、旧档案回放重建、新物理及优化更新实际均0。parent入口已进入，reader未启动；无新检查点。拥有的进程树与启动器退出已确认，账本CLOSED、授权CLOSED_ERROR收口，未用次数全部关闭、不结转、不重试。累计动态245，自动跟踪PAUSED。

当前仍在B.2第3项“普通SAC训练与真实任务评价”；SCOPE13原F0评价4＋预热4成功、正式更新0及失败记录保留。仅四个固定±75μm／±0.25°开发点，原3处逐profile覆盖缺口与事后开发覆盖修订仍在；完整B.2/C未验收，独立测试0。当前没有数值或训练执行准入。

下一项优先离线修正导入边界：逐个核对并允许确实只做数值处理的必要依赖，继续拒绝MuJoCo、物理环境和仿真执行模块；补上真实传递依赖链的兼容性反例。修复应另存新候选、保留旧封存，完成相关检查后再提出新的数值执行申请；本次关闭的授权不重开。

[失败收口](deliverables/learning_chain/b2_warm_reconstruction_execution_20261009/结果说明.md)、[根因证据](deliverables/learning_chain/b2_warm_reconstruction_execution_20261009/failure_diagnosis.json)、[关闭记录](deliverables/learning_chain/b2_warm_reconstruction_execution_20261009/authorization_closure.json)。

使用：只读核验诊断、账本和关闭记录；旧入口不得再次执行。

### B2-SCOPE-15｜预热状态重建数值门（2026-10-09）

B2-SCOPE-15预热状态重建与独立恢复数值门已完成离线接入。相关标准库测试61项通过，独立审查已收口；实际数值恢复尚未执行。

候选将核对原零检查点的全部网络、优化器、温度、计数和策略随机状态，按原顺序重建4份预热档案的19300行回放与终末边界，逐周期重放388次四维预热抽样。新检查点独立读取、重新构建、完整状态比较及运行对象恢复读回均已接入，尚无真实张量验证结果。

本轮新增物理／学习器／张量读取／网络前向／优化／经验发布均0，累计动态245；自动跟踪PAUSED。SCOPE13已完成F0评价4＋预热4成功、正式更新0的结果及原文件访问失败保持；旧17回合授权的未用部分关闭，不重开、不自动重跑前8回合。

当前仍在B.2第3项“普通SAC训练与真实任务评价”。范围为四个固定±75μm／±0.25°开发点，原3处逐profile覆盖缺口及事后开发覆盖修订保留；完整B.2/C未验收，独立测试0。接口和离线检查通过不等于数值恢复通过，也不等于SAC有效。

下一项：申请一次独立的CPU状态重建验证，限学习器构造2、张量读取2、完整保存1、确定性预测2、旧档案回放重建8（父进程4＋独立进程4）；新增物理／优化更新／采集经验均0。整体最多30分钟，独立读取进程最多15分钟，失败关闭且不重试。通过后再准备从预热边界继续的训练及匹配评价方案；当前没有新的训练准入。

[本次结果](deliverables/learning_chain/b2_warm_reconstruction_preparation_20261009/结果说明.md)、[数值候选](deliverables/learning_chain/b2_warm_reconstruction_preparation_20261009/candidate.json)、[具体申请（未批准）](deliverables/learning_chain/b2_warm_reconstruction_preparation_20261009/authorization_request.json)。

使用：run_suite.py可进行离线回归；run_gate.py须另有绑定本候选的明确数值授权。

### B2-SCOPE-14｜文件并发修复与恢复来源（2026-10-09）

B2-SCOPE-14文件读写修复候选与恢复来源核对已完成：Windows瞬态访问拒绝在读、替换两端作最多0.5秒的有限重试，并受整体／最近有效阶段绝对截止约束。完整相关离线测试39项通过，含真实Windows文件锁、并发读写、受控子进程退出与原联合合同回归。

只读核对原4份预热档案：19300行，其中14127行允许残差动作，388次四维抽样（1552个标量），顺序、动作保持、资格／配置／策略hash及原物理内容一致。重建所需来源齐全；尚未构造回放张量、加载检查点或验证NumPy／Torch随机状态，因此完整数值恢复与无损续跑均未通过。

本轮新增物理／学习器／张量读取／网络前向／优化／经验发布均0，累计动态245；自动跟踪PAUSED，新执行准入无，旧17回合申请未用部分仍关闭。SCOPE13实际F0评价4＋预热4成功、正式更新0的结果不变。

当前仍在B.2第3项“普通SAC训练与真实任务评价”；原3处逐profile覆盖缺口和事后开发覆盖修订保留。范围仅四个固定±75μm／±0.25°开发点；完整B.2/C未验收，独立测试0。文件修复通过不代表SAC有效或任意未来文件操作不会失败。

下一项：离线接入“零起点＋4份既有预热档案”的状态重建与独立保存／恢复数值门，明确新来源绑定、所需数值操作及验收条件，形成可审阅候选后再提出具体执行申请。优先复用已完成物理档案；不直接加载旧零检查点跳进在线回合，不重开旧运行或自动重复前8回合。

[修复结果](deliverables/learning_chain/b2_joint_io_repair_20261009/结果说明.md)、[恢复来源](deliverables/learning_chain/b2_joint_io_repair_20261009/recovery_assessment.json)、[状态重建路线](deliverables/learning_chain/b2_joint_io_repair_20261009/状态重建路线.md)。

使用：只作为新版本候选与恢复来源核对；运行离线测试见run_suite.py，目录没有训练入口。

### B2-SCOPE-13｜四点普通SAC有限试跑（2026-10-09）

B2-SCOPE-13四点普通F50 SAC有限试跑因监督器文件访问异常中断，已完成本次尝试的证据收口：状态CLOSED_ERROR，实际物理回合8/17（F0评价4＋预热4，全部功能成功、有效停稳、无硬保护触发），完整原始档案8份，正式更新完成0/2000批，新回放发布4次。首个在线回合仅登记、未启动，不能计入物理尝试。

zero完整独立恢复通过。 监督器读取phase_deadline.json时发生PermissionError；同一读写函数的文件并发试验已复现访问冲突。这是运行实现缺陷，训练前后比较未形成，不能给学习改善或策略失效结论，也不能归因于原3处覆盖缺口。

累计动态245，本轮监督用时1736.053秒（28.93分钟），全部余额关闭，当前无继续训练准入，自动跟踪PAUSED；拥有的运行进程树退出已确认。预留上界与实际档案成本分别报告，不将未用上界当已执行计算。

当前阶段B.2第3项；完整B.2/C未验收，独立测试0，范围仍仅四个固定±75μm／±0.25°开发点。原3处逐profile覆盖缺口及SCOPE11事后修订保持，不把开发结果当独立验证。

下一项：仅离线准备新版本文件并发读写修复及硬时限回归，核对零起点＋4份预热档案能否精确重建继续所需的回放和随机状态，再形成具体的新执行方案。当前只有零更新检查点，没有预热后的完整检查点；不得直接宣称可无损续跑。本轮剩余9回合及2000批已关闭，不重试、不结转、不转借旧授权。

[试跑结果](deliverables/learning_chain/b2_joint_sac_execution_20261009/结果说明.md)、[失败原因与修复路线](deliverables/learning_chain/b2_joint_sac_execution_20261009/失败原因与修复路线.md)、[逐回合与成本](deliverables/learning_chain/b2_joint_sac_execution_20261009/execution_summary.json)、[授权关闭](deliverables/learning_chain/b2_joint_sac_execution_20261009/execution/authorization_closure.json)。

使用：先核对状态与实际完成项，再读原始档案；关闭授权不可再次使用。

### B2-SCOPE-12｜四点普通SAC离线接入（2026-10-09）

B2-SCOPE-12四点普通F50 SAC离线接入与具体登记完成：联合位姿贯通采集、审核和检查点，原SAC数值内核保持；15项纯检查通过，4份旧零残差档案共同条件核对通过，独立审查3项问题已修复。

3处原逐profile缺口保持；按同一J点合并A/B支持有限开发准备，但不能保证训练效果。覆盖专项补验0。范围仅四个固定±75μm／±0.25°点；原完整范围、实际短训、真实恢复和独立评价仍待，完整B.2/C未验收。

本轮新物理／学习器／张量读取／推理／更新／经验发布均0，累计动态237；训练未准入，自动跟踪PAUSED，旧授权全部关闭。

下一项：申请一次新的17动态回合、最多2000正式更新批及7次构造／2次张量读取／2次保存的新运行，整体硬限6小时；先过零起点完整检查点真实独立恢复门，再固定完成F0评价4、预热4、在线4、F2000评价4、独立物理复现1。失败停止、不重试、不结转，累计动态最多254；不进入C。

主指标保持共同26秒正常失败罚时；F2000相对匹配F0均值改善≥10%且最终四点成功、无硬保护、有效停稳及恢复一致，才给开发继续信号。无效仿真、保护失败与全部峰值单列；不是独立效果验收。

[接入与登记说明](deliverables/learning_chain/b2_joint_sac_preparation_20261009/结果说明.md)、[具体新申请（未批准）](deliverables/learning_chain/b2_joint_sac_preparation_20261009/authorization_request.json)、[候选](deliverables/learning_chain/b2_joint_sac_preparation_20261009/candidate.json)、[原始档案核对](deliverables/learning_chain/b2_joint_sac_preparation_20261009/baseline_equivalence.json)。

使用：默认入口仅做文件校验；新执行须另有绑定该候选的新grant，历史预算不可复用。

### B2-SCOPE-11｜覆盖条件复核（2026-10-09）

B2-SCOPE-11离线覆盖条件复核完成：8份动作档案重算与原审核一致。按同一J点合并A/B后，快速接触有效命令周期分别25／28／32／30，长保持1428／1767／2341／2510；下一次观测均有非零六维力／力矩信号。四点均有四轴正负方向，原4项工程恢复和24项峰值重叠证据保留。

建议把两种时序的覆盖要求按每个J点合并A/B检查，保留周期末接触定义与所有保护条件。覆盖专项新增回合建议0，下一项转普通SAC小规模训练的接入与具体登记。该建议来自开发档案复核，不是独立验证；SCOPE10按原逐profile判据的3处缺口及失败路线保持。

本轮新增物理／子步／学习器／推理／更新／经验发布均0，累计动态237；训练未准入，自动跟踪PAUSED，旧授权全部关闭。

当前阶段B.2第2项已交付本次复核；训练接入与执行尚未完成，完整B.2/C未验收。范围仅四个离散±75μm／±0.25°开发点，不扩展原±1.5°或连续域。观察到信号和命令作用不等于策略收益或任意动作安全。

下一项：准备四个离散J点上的普通F50残差SAC小规模训练与共同参照：接入既有学习／检查点代码，冻结数据用途、训练与评价顺序、具体次数／更新／墙钟上限和停止规则，完成离线接线检查后交付一次具体执行申请。覆盖专项补验建议0；运行来源或接口改变时重新判断受影响检查。

[复核与路线](deliverables/learning_chain/b2_joint_coverage_review_20261009/结果说明.md)、[建议条件v2](deliverables/learning_chain/b2_joint_coverage_review_20261009/recommended_gate_v2.json)、[逐周期统计](deliverables/learning_chain/b2_joint_coverage_review_20261009/coverage_comparison.json)、[训练准备边界](deliverables/learning_chain/b2_joint_coverage_review_20261009/pilot_preparation_scope.json)。

使用：先读新旧条件差异与限制，再查看逐项统计；建议文件本身不启动训练或重新打开旧授权。

### B2-SCOPE-10｜联合点固定物理预检（2026-10-09）

B2-SCOPE-10固定12项联合点预检已执行并关闭：本轮尝试12/12，审核通过12，功能成功12、真实停稳12，未执行0项数量关闭。工程恢复覆盖4/4；A/B时序覆盖缺口3处（J03_A_AXIS、J04_A_AXIS、J02_B_CORNERS），缺口的逐周期接触／权限／有效作用分类已归档。3处快速块按原登记判据均缺少“周期末有接触且动作有效”的记录；其中J03_A_AXIS有3个、J04_A_AXIS有2个快速周期记录到周期内接触峰值，J02_B_CORNERS未记录到此类峰值。因此不能把这3处统称为“完全没有接触”，也不能据此推断改时序后的结果。本轮未达到全部登记覆盖要求，不能把有限成功升级为完整准入。

本轮实际累计动态237（原225＋本轮12）；归档54260控制周期／542600物理子步。学习器、张量读取、前向、优化和经验发布全0；训练未准入，自动跟踪PAUSED，全部本轮及旧预算关闭，无重试。

完整B.2/C未验收；四个±75μm／±0.25°联合开发点不等于原±1.5°范围，固定代表动作不是连续动作域安全证明。R为工程触发恢复，不计自然成功率；A/B不计策略学习收益。独立评价0，共同模型／保护／观测／奖励保持。

下一项：仅用现有档案离线设计覆盖缺口的最小处理方案：比较按动作获准时刻安排固定序列与明确收窄时序声明，给出是否需要新补验及其最小范围。已通过项保留，本轮数量已关闭；不重跑整套矩阵、不自动补采或训练。

[结果说明](deliverables/learning_chain/b2_joint_preflight_execution_20261009/结果说明.md)、[路线决定](deliverables/learning_chain/b2_joint_preflight_execution_20261009/路线决定.md)、[原始账本](deliverables/learning_chain/b2_joint_preflight_execution_20261009/run/ledger.json)、[授权关闭](deliverables/learning_chain/b2_joint_preflight_execution_20261009/authorization_closure.json)。

使用：按原始账本和逐项收据区分功能、有效性、停稳、覆盖；授权关闭后不能续跑旧入口。

### B2-SCOPE-09｜联合点预检候选实现与离线验收（2026-10-09）

B2-SCOPE-09联合点预检候选实现及离线验收完成：固定A/B日程、一次工程恢复夹具、覆盖审核、新授权与一次性预算门已接入；21项离线测试通过。既有J01_script的4834周期／4835观测只读回归与封存结果一致。

本轮新增环境创建、reset、物理积分、学习器、张量读取、网络前向、优化和经验发布全0；实际累计动态225。自动跟踪PAUSED，旧预算关闭。固定12项新物理预检仍未授权、未执行，237只是以后全部执行的累计上限。

使用：先读接入说明；离线check-only可核对绑定。执行申请本身不是grant；旧授权不能复用，同候选不可重复消费。

当前只验收程序实现和离线证据，真实联合点动作／恢复覆盖仍待实测；纯状态替身和旧档案回归不算新物理成功。完整B.2/C未验收，±0.25°离散点不等于原±1.5°范围，独立评价0、无训练准入；137维及全部共同模型／保护／奖励保持。

[接入与验收说明](deliverables/learning_chain/b2_joint_admission_preflight_20261009/接入与验收说明.md)、[未授权执行申请](deliverables/learning_chain/b2_joint_admission_preflight_20261009/authorization_request.json)、[来源绑定](deliverables/learning_chain/b2_joint_admission_preflight_20261009/candidate_binding.json)、[离线测试](deliverables/learning_chain/b2_joint_admission_preflight_20261009/offline_tests.txt)。

### B2-SCOPE-08｜联合点动作域与恢复准入设计（2026-10-09）

B2-SCOPE-08准入方案设计完成：8份J档案确认SEARCH保留旧INSERT受阻历史，返回INSERT前全部清空，活动INSERT时长最大0.402s；本项饱和现象不要求改137维观测。已核对同版本零倾角自然恢复254.143μm及297个屏蔽周期，继承流程依据，不冒称联合姿态恢复通过。

本轮新增物理、学习器/张量读取、网络前向、更新及经验发布全0。实际累计动态225，自动跟踪PAUSED，旧预算关闭。拟最多12次新动态（8动作＋4工程恢复）、训练0，若以后另获授权并全部执行累计上限237；当前未实施、未授权，不把237记为实际累计。

使用：先读方案的固定12项、动作日程、工程恢复触发、失败出口和成本；按继承矩阵区分可复用依据与待实测项。该提案不能作为执行grant。

联合点完整动作域及真实恢复仍待实测；12次为代表性补验方案，不证明任意策略安全。2468次SEARCH饱和事实保持，其分支语义疑点已核对；不据此宣称完整Markov状态。31条相关测试只是读取历史结果（22条当前PC-06来源、9条旧B1），不是本轮新增测试通过。完整B.2/C未验收，±0.25°离散点不等于原±1.5°目标，独立测试0。

[具体准入方案](deliverables/learning_chain/b2_joint_admission_design_20261009/准入方案.md)、[未实施机器提案](deliverables/learning_chain/b2_joint_admission_design_20261009/admission_proposal.json)、[状态与恢复证据](deliverables/learning_chain/b2_joint_admission_design_20261009/evidence_review.json)、[继承矩阵](deliverables/learning_chain/b2_joint_admission_design_20261009/inheritance_matrix.json)。

### B2-SCOPE-07｜联合姿态点离线复核（2026-10-09）

B2-SCOPE-07离线复核8份J01～J04档案、42656周期及42664个137维观测，已完成。零残差接触信息有差异，8/8首次接触和力峰时均有残差权限；script只在每点50个SEARCH接触周期产生非零作用，未覆盖峰值当周期的非零动作。保留四个联合点作为待准入的匹配学习候选。

本轮新增物理、网络推理、训练更新和经验发布全0。实际累计动态225，自动跟踪PAUSED，旧预算关闭，无新物理或训练授权。SCOPE-06的9静态/16动态及原覆盖不足路线保持。

使用：先读结果表和路线决定，按档案ID查analysis.json及joint_cycles.csv；裁剪字段与同一时刻对照见information_refinement.json。脚本只读取封存JSON，封存后拒绝覆盖新结果，不运行仿真或学习器。

力峰距25mN保护阈值最少0.419mN（1.676%）；小幅相关脚本不代表完整动作域，联合点恢复事件0。2468个有权限SEARCH观测的受阻时长饱和（其中2214个有接触），另3440次仅在无权限停止尾段；首次接触无裁剪不能外推全程无裁剪。脚本按工况定方向，不能证明可部署辨识或学习收益。±0.25°离散点不能验收原±1.5°目标。完整B.2/C未验收，独立测试0。

下一项准备B.2联合点动作域与恢复准入登记：先审查时长饱和的状态语义和既有恢复证据可继承范围，再固定最少新增缺口预检、成本与失败出口。具体方案获新授权后才执行；通过后另行登记普通SAC姿态匹配短训、共同参照及冻结评价。P01～P04保留无接触功能对照，不追加填覆盖，不扩137维或物理范围，不进入C。

[本轮证据](deliverables/learning_chain/b2_joint_learning_review_20261009/结果说明.md)、[路线决定](deliverables/learning_chain/b2_joint_learning_review_20261009/路线决定.md)、[逐周期复核](deliverables/learning_chain/b2_joint_learning_review_20261009/analysis.json)、[观测裁剪复核](deliverables/learning_chain/b2_joint_learning_review_20261009/information_refinement.json)。

### B2-SCOPE-06｜姿态预检实际执行（2026-10-08）

B2-SCOPE-06一次执行已收口：静态审核9/9；动态尝试16/16、审核通过16/16、功能成功16/16、80μm/0.5°附加精度成功16/16。运行状态CLOSED_COMPLETE；本轮未用动态0，新授权已关闭。

本轮环境创建/复位完成各25次，67016控制周期/670160物理子步，整轮监督4516.837s；进程退出确认，学习器/张量读取/网络前向/优化/经验发布全0。实际累计动态225，自动跟踪PAUSED，原旧15回合未重开。

本轮接触覆盖8/16、script四轴命令作用覆盖8/8、接触时作用覆盖4/8、对称接触信息差异覆盖4/8，恢复事件覆盖0/16。±0.25°离散开发点不覆盖±0.5°边界、原±1.5°目标或连续域；固定0.1幅度且四轴相关的脚本不覆盖完整F50动作域，脚本不是SAC，非零差异不等于可辨识性或学习收益。完整B.2/C未验收，无新训练准入，独立测试0。

下一项只离线复核J01～J04的现有接触信息、动作许可与作用时序，判断4个有接触联合点是否支持限定姿态匹配学习候选，并列出恢复及动作域缺口。P01～P04保留为无接触功能对照；不追加它们填接触覆盖，不扩137维观测或物理范围，不进入C或训练。原±1.5°目标与当前±0.25°开发验证的验收边界须另行明确。

[本轮实际结果](deliverables/learning_chain/b2_rebound_execution_20261008/结果说明.md)、[实耗与授权关闭](deliverables/learning_chain/b2_rebound_execution_20261008/authorization_closure.json)、[固定矩阵审核](deliverables/learning_chain/b2_rebound_execution_20261008/run/assessment.json)、[路线决定](deliverables/learning_chain/b2_rebound_execution_20261008/路线决定.md)。使用原始档案及审核结果只读分析；不再次调用本轮--execute，不修改旧封存。

### B2-SCOPE-05｜新预检执行候选（2026-10-08）

B2-SCOPE-05已将修订审核器接入新的固定预检执行程序；新候选、来源绑定和领取目录独立，沿用原8点、zero/script顺序、控制器、模型、奖励和停止规则。

最终41项关联离线检查通过，2173项输入核验；实际worker审核步骤用旧P01完整记录及NumPy类型回放通过。一次只读审查的源码校验表绑定缺口已补齐，缺少/错误SHA会在执行前拒绝；真实未批准请求拒绝且未建claims。

本轮新增仿真/初始化/动态/子步/网络前向/优化/经验发布全0，实际累计动态209，自动跟踪PAUSED。旧15个动态和旧授权保持关闭；完整B.2/C未验收，无新训练准入。离线接入不能替代新动态、接触/脚本作用或范围验证。

[新程序与上限](deliverables/learning_chain/b2_preflight_rebound_20261008/接入说明.md)、[离线检查](deliverables/learning_chain/b2_preflight_rebound_20261008/offline_tests_final.txt)、[审查处置](deliverables/learning_chain/b2_preflight_rebound_20261008/review.md)、[本次运行申请（未批准）](deliverables/learning_chain/b2_preflight_rebound_20261008/authorization_request.json)。现在可用run_preflight.py --check-only核对来源；实际--execute需本次新grant。

下一项申请并核验本候选的一次新仿真运行授权：9次无积分初始化全部通过后，按固定顺序最多16个动态，环境/复位各最多25次、训练/推理0、无重试、整轮监督硬限6h；若全跑累计上限225。静态失败、保护、无效仿真、运行错误或停止不明则关闭剩余。获明确批准后才生成新grant并执行，C的F12.5接入继续暂缓。

### B2-SCOPE-04｜审核器离线修复（2026-10-08）

B2-SCOPE-04审核器离线修复与真实档案回归完成：同值Python/NumPy标量可正确比较，布尔与数值仍区分，非有限值和真实差异继续拒绝；混合大整数/浮点采用确切差，原容差不变。

最终14项新检查、6项原有审核回归通过；正式修订入口只读复核9份静态＋1份动态档案通过。P01的3045周期和3046个137维观测得到复核；一次只读审查的1项Important经作者反例及修复关闭。

本轮新增仿真/初始化/子步/网络前向/优化/经验发布全0，累计动态209，自动跟踪PAUSED。原B2-SCOPE-03失败账本、NO_SCOPE_QUALIFICATION及15个未运行且已关闭的动态保持；完整B.2/C未验收，无新训练准入。现有P01无接触，脚本、联合动态及更大姿态范围仍缺。

[修复与使用](deliverables/learning_chain/b2_scope_auditor_fix_20261008/结果说明.md)、[正式档案复核](deliverables/learning_chain/b2_scope_auditor_fix_20261008/archive_reassessment_final.json)、[最终回归](deliverables/learning_chain/b2_scope_auditor_fix_20261008/final_tests.txt)、[审查与处置](deliverables/learning_chain/b2_scope_auditor_fix_20261008/review.md)。使用audit_existing.py --check-only核对来源，省略该选项只读复核既有档案。

下一项仅把修订审核器接入新的预检执行候选，核对来源绑定和停止规则，形成明确的仿真运行上限。旧物理入口仍保留旧审核器，不能直接再次调用；本项没有新增执行授权，旧15回合不恢复。C的F12.5接入继续暂缓。

### B2-SCOPE-03｜姿态预检执行与审核故障（2026-10-08）

B2-SCOPE-03获批一次性预检后，9/9静态初始化通过；P01_zero运行完成后，审核器标量类型比较报错，按规则关闭余下15个动态。动态尝试1/16、原运行审核通过0/16，动态范围未验收。

本轮10次环境创建/复位、3045控制周期、30450物理子步，全程监督260.759s，进程退出确认；学习器/张量/网络前向/优化/经验发布全0。累计动态209，自动跟踪PAUSED，旧预算关闭。

生产奖励独立复算3045/3045一致。原审核器误拒同值的float/NumPy标量；3个同值反例复现，仅在诊断进程统一标量类型后，命令/奖励/3046个137维观测/守卫/几何/停止复核通过，4个异常反例仍拒绝。封存代码与原失败状态不改。

P01零残差原始记录及只读诊断支持功能成功、4.330s任务时间和物理停稳，但接触0、脚本未执行；联合动态、对称配对、恢复及匹配训练仍缺。完整B.2/C未验收，无新训练准入；±0.25°静态通过不覆盖±0.5°边界或原±1.5°目标。

[执行与故障说明](deliverables/learning_chain/b2_pose_scope_execution_20261008/结果说明.md)、[授权收口](deliverables/learning_chain/b2_pose_scope_execution_20261008/authorization_closure.json)、[根因证据](deliverables/learning_chain/b2_pose_scope_execution_20261008/audit_diagnosis.json)、[路线决定](deliverables/learning_chain/b2_pose_scope_execution_20261008/路线决定.md)。使用原档案和诊断证据只读核查；原grant已消费，执行入口不得再次调用。

下一项仅离线修复审核器标量比较，补真实内存NumPy奖励与JSON往返命令的回归，并保留对真实数值差异、非有限值和布尔混用的拒绝。新候选及绑定可审阅后，再登记明确的新物理预算；本轮关闭的15动态不恢复，不重试，C的F12.5物理接入继续暂缓。

### B2-SCOPE-02｜姿态预检离线实现（2026-10-08）

B2-SCOPE-02小倾角预检离线实现与审查收口：实际初始角贯通、固定9静态/16动态顺序、一次性新授权及进程监督、完整上下文归档和只读命令/奖励/几何/停止审核已准备。这属于B.2姿态/联合范围预检准备，真实初始化和动态尚未执行。

33项新离线/无仿真进程检查、12项关联父进程检查通过；一次独立审查及修复记录留档。950历史封存成员、19个B2-SCOPE-01成员、1057共享输入和63原始档案复核保持。

本轮物理引擎加载、真实初始化、动态/子步及全部神经网络/张量/优化/经验开销均0；实际累计动态208，自动跟踪PAUSED，旧预算关闭，当前无新训练准入。完整B.2/C未验收。±0.25°开发预检不覆盖±0.5°边界或原±1.5°目标，脚本作用不等于SAC收益。

[实现说明](deliverables/learning_chain/b2_pose_scope_preflight_20261008/结果说明.md)、[离线检查](deliverables/learning_chain/b2_pose_scope_preflight_20261008/offline_tests.json)、[审查](deliverables/learning_chain/b2_pose_scope_preflight_20261008/review.md)、[新预算请求（未批准）](deliverables/learning_chain/b2_pose_scope_preflight_20261008/authorization_request.json)。使用 `run_preflight.py --check-only` 做无引擎检查；实际执行须新grant。

### B2-SCOPE-01｜姿态/联合范围审计与最小预检方案（2026-10-08）

B2-SCOPE-01范围审计与最小预检方案完成，属于离线证据整理与规划，未新增物理或学习能力。PC-06/07/09的63份当前版本原始新回合均为初始零倾角；当前每轴初始输入限为±0.5°，旧pilot入口还把roll/pitch写死为0。原±1.5°目标不能直接套用，完整B.2仍待验收。

使用方式：先读[范围证据表与固定8点矩阵](deliverables/learning_chain/b2_scope_audit_20261008/范围审计与最小预检方案.md)，再按[实现计划](docs/superpowers/plans/2026-10-08-b2-pose-scope-preflight.md)准备运行器；[candidate.json](deliverables/learning_chain/b2_scope_audit_20261008/candidate.json)是未授权候选，不能交给旧学习入口执行。

只读核验950个PC-06～14封存成员及1057共享输入；63原始档案按旧账本SHA复核。S/F0.39%未过原继续门、四首次位置附加精度均0/4、PC-12两个停止上下文缺口均保持。 本轮物理引擎加载、初始化、动态/子步、神经网络推理、张量读取、优化和经验发布均0；实际累计动态208，自动跟踪PAUSED，旧预算关闭。拟16动态若以后全部获准执行，累计上限224，现在不计入实绩。完整B.2/C未验收；±0.25°预检不能覆盖±0.5°边界或原±1.5°目标。

下一项优先实现B.2小倾角范围预检的离线运行器与准入检查，显式贯通实际初始角，保留当前v4模型/控制/保护。候选为每轴±0.25°的8个开发点，拟9次无积分初始化、最多16个零残差/脚本配对动态；先完成纯检查和审查，再申请具体新物理预算。运行器未实现，候选未授权，当前不执行。C的F12.5物理接入暂缓，既有PC-11～14成果保留。

### PC-14｜小边界合成数值门（2026-10-08）

- **获得：** PC-14合成数值门已验收：使用冻结CPU运行时，真实同种子零起点/空优化器与回放/三个RNG、完整检查点独立进程恢复和下一步参数/Adam/回放/终末边界/RNG/采样索引逐值一致通过；仅测量wall_s排除。166项只读收口检查通过，沿用PC-13的78项纯检查证据。实际总监督用时89.34s。
- **使用：** [结果](deliverables/paper_comparison/small_boundary_numeric_execution_20261008/结果说明.md)、[数值资格（不准入物理训练）](deliverables/paper_comparison/small_boundary_numeric_execution_20261008/numeric_qualification.json)、[只读复核](deliverables/paper_comparison/small_boundary_numeric_execution_20261008/audit_numeric_result.py)。执行已关闭，不再运行原worker。
- **证据与成本：** 本轮合成更新4/4（父3/reader1）、显式测试状态前向32/32（各16），新合成回放400行，辅助模型构造4/4、CPU张量读取3/3。新物理/子步/正式更新/性能评价均0，累计动态208；完整B.2/C未验收。798旧封存成员、1057共享输入及36runtime文件保持。
- **限制与下一项：** 下一项只做F12.5物理backend接入与准入材料的离线准备：连接固定物理profile、零更新部署/独立恢复和原保护审核，先形成可审阅候选。2次物理预检、拟21动态/2000正式批仍需独立的新授权与逐项准入；本次4/32合成数值额度已耗尽关闭，无结转或自动重试。自动跟踪PAUSED。

### PC-13｜小边界数值集成门脚本（2026-10-07）

- **获得：** PC-13数值集成门脚本准备完成：授权先查、父/reader共享排他账本、全新合成数据、CPU runtime绑定、零起点与完整检查点/独立进程恢复/下一更新逐值对照脚本已实现；78项关联纯检查通过，36个runtime文件哈希核验。一轮审查修复覆盖计算收据、关闭余额、进程超时、隔离库来源和辅助开销统计；真正4批/32状态门未执行，不能记数值通过或新资格。
- **使用：** [说明](deliverables/paper_comparison/small_boundary_numeric_gate_20261007/结果说明.md)、[请求](deliverables/paper_comparison/small_boundary_numeric_gate_20261007/authorization_request.json)、[候选](deliverables/paper_comparison/small_boundary_numeric_gate_20261007/numeric_candidate.json)、[只读复核](deliverables/paper_comparison/small_boundary_numeric_gate_20261007/verify.py)。`numeric_worker.py --inspect`只查看；所有执行模式缺新授权先拒绝。
- **限制：** 本轮真实学习器构造/张量读取/网络前向/优化/经验发布/物理/子步均0，累计动态208、自动跟踪PAUSED，新数值/物理/训练授权无、旧预算关闭。765旧封存文件、1057共享输入保持。完整B.2/C仍未验收。 下一项申请并核验一次新的合成数值门授权：最多4更新事务（父3/reader1）、32显式测试状态（各16），新合成400行；物理/正式训练0。获明确授权后才用已绑定CPU解释器验证零起点、完整落盘和独立进程恢复。通过也不自动开启21动态/2000正式批；实际物理backend与新的物理/训练准入仍待。

### PC-12｜小边界离线适配与协议候选（2026-10-07）

- **获得：** PC-12小边界离线适配与协议候选完成：四轴F12.5物理尺度、未缩放归一化a、完整检查点外层和固定21次一次性调度已实现；53项纯检查通过。9752个既有状态中9750个命令级反算通过（7362启用），另2个停止边界无法由旧记录重建完整命令上下文，保留缺口；不是完整轨迹等价或数值恢复验收。
- **使用：** [说明](deliverables/paper_comparison/small_boundary_execution_20261007/结果说明.md)、[未准入候选](deliverables/paper_comparison/small_boundary_execution_20261007/qualification_candidate.json)、[复核](deliverables/paper_comparison/small_boundary_execution_20261007/verify.py)、[数值门](deliverables/paper_comparison/small_boundary_execution_20261007/数值门清单.md)。仅--inspect；--execute缺准入先拒绝，实际backend待。
- **证据与限制：** 新增物理/子步/学习器构造/真实检查点加载/网络前向/优化更新/经验发布均0，累计208，自动跟踪PAUSED、新训练准入无、旧预算关闭；730旧封存文件与1057共享输入保持。完整B.2/C仍未验收。 下一项先实现并审阅独立数值集成脚本与runtime连接，形成最多4合成事务/32测试状态的可审阅数值门，再另行取得明确计算授权后验证零起点、完整落盘与新进程恢复。当前不启动该计算。物理backend尚未连接；21动态/2000正式批及累计229仍只是未启用提案，不能由协议通过或旧余额自动开启。

### PC-11｜公平小边界登记草案（2026-10-07）

- **获得：** PC-11公平小边界登记草案完成：有条件只读继承25份B2/F0/S0/F2000/S2000评价，拟仅新增F12.5匹配训练，四轴物理尺度12.5μm/s与0.125mrad/s。拟21新动态/2000正式批（2预检＋19训练评价），数值门拟4合成更新/32测试状态单列；若以后获批，累计上限229。历史成本外推约2.10h、规划2–4h、拟整体硬限6h；不是新实测。
- **使用：** [设计](docs/superpowers/specs/2026-10-07-small-boundary-fair-comparison-design.md)、[机器草案](deliverables/paper_comparison/small_boundary_registration_20261007/draft_contract.json)、[成本依据](deliverables/paper_comparison/small_boundary_registration_20261007/budget_basis.json)、[后续计划（未执行）](docs/superpowers/plans/2026-10-07-small-boundary-fair-comparison.md)。
- **限制：** 本轮新物理/子步/检查点加载/网络推理/更新/经验发布0，实际累计208，自动跟踪PAUSED、新训练准入无、旧预算关闭。704旧封存文件及1057共享输入保持；草案完成不算新增训练能力，完整B.2/C仍待验收。

### PC-10｜离线搜索路径与路线决定（2026-10-07）

- **获得：** PC-10离线搜索路径对照已完成：4份既有负Y档案/28,465周期，5段SEARCH/15,626周期。G两段最大净深度−6.140/−6.355μm，未超过旧峰值；参考到120μm圆后下一共同命令超界5.279/0.046nm，按原规则两次耗尽。S首段净深度100.021μm后退出并保持旧10.760s成功。启用命令、参考积分及边界公式核对无执行错误证据；不同演员/权限与前段历史未隔离，不能称唯一训练成因。停止F演员直接套G门控路线，保留匹配训练S及合理小固定边界公平对照方向。
- **使用：** [结果与两图](deliverables/paper_comparison/search_path_comparison_20261007/结果说明.md)、[路线决定](deliverables/paper_comparison/search_path_comparison_20261007/路线决定.md)、[逐周期CSV](deliverables/paper_comparison/search_path_comparison_20261007/search_cycles.csv)、[原始统计](deliverables/paper_comparison/search_path_comparison_20261007/diagnosis.json)。分析器仅纯读取；封存后生成操作须在完整副本中复核。
- **验收与限制：** 6专项+21相关检查及来源复核；本轮新增物理/子步/网络推理/梯度/经验发布均0，累计动态208；旧预算关闭、自动跟踪PAUSED、新训练准入无。生产1057输入及旧658封存文件保持。完整B.2/C、合理小边界重训、多种子和新的冻结最终测试仍待验收。

### PC-09｜接触门控与小固定边界部署预检（2026-10-07）

新增8/8动态完成，累计208，7成功/1普通任务失败；8/8有效停稳，无硬保护或参考运行故障，未用0关闭，新优化/经验发布0。G50对中与B2完整轨迹相同、残差/网络调用0；负Y两次搜索耗尽，G功能1/2，B2/F50/F12.5各2/2。失败按26s罚时，平均用时分别12.555/7.288/7.992/15.165s；G较B2慢20.79%，本修复方案未达到整体任务预期。F12.5对中无接触、误差42.10μm，负Y误差100.80μm；附加80μm/0.5°为B2/F12.5/G各1/2、F50为0/2，功能与精度分列。45,660周期/456,600子步及45,660条奖励复算通过，真实网络调用/尝试21,658/21,658；4份B2/F50与旧同版本轨迹/动作/事件/结果一致。88相关检查、一次限定审查I1经作者反例关闭；生产1057输入和旧580封存文件保持，137维/4维不变。完整B.2/C及论文优势不据此验收。

[结果与使用](deliverables/paper_comparison/contact_gate_probe_20261007/结果说明.md)、[资格](deliverables/paper_comparison/contact_gate_probe_20261007/qualification.json)、[封存](deliverables/paper_comparison/contact_gate_probe_20261007/delivery_manifest.json)。固定8回合一次领取；分析仅完整副本复核，不把冻结部署算G训练。

### PC-08｜残差实际作用归因（2026-10-07）

离线37档案/245,221周期归因通过；已训练S八接触工况的峰值全部先于残差许可，14/14前缀与B2相同；对中F引入约100μm侧移和5.383mN接触。旧请求/即时差统计不是执行损失，总命令限幅已分列。新增动态/训练/策略调用/发布0，累计200；137维/4维及1057生产输入保持。

[使用与结果](deliverables/paper_comparison/residual_effect_diagnosis_20261007/结果说明.md)、[候选](deliverables/paper_comparison/residual_effect_diagnosis_20261007/next_candidate.md)、[封存](deliverables/paper_comparison/residual_effect_diagnosis_20261007/delivery_manifest.json)。只读旧档案；不新增论文性能样本或生产算法。

### PC-07｜同版本公平对照、初始策略及首次位置评价（2026-10-07）

- **获得：** 同版本公平对照与冻结后首次位置评价完成。新启动27/27，采样结束27，累计200/200；183,705控制周期/1,837,050物理子步，真实网络控制76,257次；新梯度/经验发布0，未用0关闭。
- **比较：** 开发F相对B2：用时改善16.86%，综合继续信号未满足（峰值力均值增加5.57%超过5%）；开发S相对B2：用时改善17.18%，综合继续信号满足；开发S相对F：用时改善0.39%，综合继续信号未满足（用时改善不足10%）；F学习贡献对照：用时改善23.01%，综合继续信号未满足（峰值力均值增加5.57%超过5%）；S学习贡献对照：用时改善26.75%，综合继续信号满足；新位置F相对B2：用时增加1.61%，综合继续信号未满足（用时改善不足10%）；新位置S相对B2：用时增加1.38%，综合继续信号未满足（用时改善不足10%）；新位置S相对F：用时改善0.23%，综合继续信号未满足（用时改善不足10%）。
- **使用：** [结果、两图和下一项](deliverables/paper_comparison/frozen_comparison_20261007/结果说明.md)、[固定矩阵](deliverables/paper_comparison/frozen_comparison_20261007/configuration.json)、[首次使用](deliverables/paper_comparison/frozen_comparison_20261007/first_use_registration.json)、[原始复核](deliverables/paper_comparison/frozen_comparison_20261007/assessment.json)、[封存](deliverables/paper_comparison/frozen_comparison_20261007/delivery_manifest.json)。执行一次性领取，不重跑；分析只在完整副本中复核。
- **边界：** 生产来源/算法/奖励0变化；新训练/发布0；单种子四新位置，使用后不再是后续未见测试；没有完整C、硬件或论文优势验收。

### PC-06｜新控制来源准入、真实学习与冻结评价（2026-10-07）

- **获得能力：** 本轮修复及有限学习pilot已验收；完整B.2未验收。F/S各2000批，冻结开发点各5/5功能成功；独立进程代表复现2/2逐值一致，28/28有效停稳，参考故障/硬保护0。S相对F平均用时改善0.39%，未达到预登记的10%开发继续信号。
- **成本和数据：** 新动态28/28，累计173；190,882控制周期/1,908,820物理子步；正式更新尝试/完成4000/4000；策略控制调用78,520，发布117,108条经验（F54,776/S62,332），未用预算0。两次普通搜索耗尽失败均发布，评价/恢复不入池。原关闭余量不重开，自动跟踪PAUSED。
- **证据：** 441关联离线检查，一次限定审查0重要问题；1057输入不变；28档案逐条独立复核；18完整读取门及两次物理复现通过。
- **使用：** [结果、统计与图](deliverables/paper_comparison/v4_learning_requalification_20261006/结果说明.md)、[复核](deliverables/paper_comparison/v4_learning_requalification_20261006/assessment.json)、[收口检查](deliverables/paper_comparison/v4_learning_requalification_20261006/closure_verification.json)、[执行清单](deliverables/paper_comparison/v4_learning_requalification_20261006/执行清单.md)、[最终封存](deliverables/paper_comparison/v4_learning_requalification_20261006/delivery_manifest.json)。保存F/S各2000批完整检查点；本轮执行一次性预算已消费，不重新运行执行入口。
- **限制：** 五点已用、单训练种子；旧B2不重绑；学习贡献、独立泛化、完整B.2/C及论文优势未证明。下一项先补同版本B2与未用范围/重复证据。

### PC-05｜共同搜索边界局部修复与有限开发回归（2026-10-06）

- **获得能力：** 任意搜索相位的参考边界耗尽沿用真实停止/回撤；当前越界仍故障，第二次正常失败，恢复预算不扩展。删除第二层残差缩减，观测/动作/学习设置不变。
- **证据：** 311关联离线检查；一次独立审查1 Important由作者反例修复关闭，未二次独立复审。3/3新动态有效停稳，无参考/保护：B2成功、F随机成功、S随机任务失败。B2完整11,271点、F完整5,886点与旧轨迹逐值一致。
- **使用：** [结果与范围](deliverables/paper_comparison/search_boundary_fix_20261006/结果说明.md)、[机器复核](deliverables/paper_comparison/search_boundary_fix_20261006/assessment.json)、[账本](deliverables/paper_comparison/search_boundary_fix_20261006/run/ledger.json)、[审查及修复](deliverables/paper_comparison/search_boundary_fix_20261006/review.md)。执行预算已消费，不重跑；离线脚本可按说明复核。
- **限制：** 累计145，正式训练/策略调用/回放发布/独立测试0，S未插入；只验收有限修复，不证明SAC收益或B.2完成。新共同源资格须重新登记；旧26动态/4000批不使用，PAUSED。

### PC-04｜137维学习链准入与有限pilot（2026-10-06）

**137维学习链准入通过，有限pilot按实际结果收口（2026-10-06T17:39）。** 新增2/28动态，完成2，累计142/168；正式更新尝试0，完成0/4000（F0/S0）；余26动态与未尝试批量关闭，不结转。发布5885条经验。

状态error，整轮已停止；11263控制周期/112630物理子步，网络调用0。开发继续信号None（null表示矩阵不完整而无法判断）。实际问题：ValueError('Common reference failure')。 F負Y预热成功，S負Y预热SEARCH_REFERENCE_LIMIT；两者有效/停稳/无硬保护，S拒绝入池。尚未正式学习，不是已训练策略失效。

学习链实现/数值恢复通过不等于随机动作安全、学习收益或论文方法优于基线。五点是已使用开发点；独立测试0、多种子/硬件未做，B.2尚未验收。代表复现不增加性能样本。

下一项：本轮停止点已定位：零残差搜索基线已不可继续，过滤归零仍发出该基线。先补共同SEARCH边界可行性回退，再用此反例离线验证并登记新的少量动态；不重启本轮、不补26动态/4000批。 [证据与使用](deliverables/paper_comparison/v4_learning_pilot_20261006/结果说明.md)、[审查/修复](deliverables/paper_comparison/v4_learning_pilot_20261006/review.md)、[账本](deliverables/paper_comparison/v4_learning_pilot_20261006/run/ledger.json)。 使用runner的一次性资格/账本；已领取目录禁止再次执行。

### PC-03｜残差参考连续性有限修复（2026-10-06）

[结果/使用/边界](deliverables/paper_comparison/v4_continuation_20261006/结果说明.md)、[计划](docs/superpowers/plans/2026-10-06-v4-continuation-preflight.md)。310项相关检查通过；新增1/1动态、完成1回合，11245控制周期/112450物理子步；累计140，余0关闭。正式训练/策略推理/回放发布/独立测试0，自动跟踪PAUSED，B.2未完成。 脉冲前4574个轨迹点逐值一致；第一层滤波比例0.963296598、连续性比例0.125000、合成比例0.120412075。实际触发滤波1周期，下一零动作B2没有参考失败；审核7359个实际SEARCH参考端点，越界0。本例FULL_SUCCESS，任务判定20.730s，峰值力24.474mN。 只证明已登记负Y单脉冲的有限连续性修复；不保证任意未来动作、lead裁剪、所有物理子步或整个策略空间安全。137维学习掩码/回放/SAC/完整检查点仍需新版本准入，未沿用旧120维权重或旧训练数据；本轮不是学习收益。 原runner已消费或关闭，禁止重启该目录。

### PC-02｜v4残差接入有限预检（2026-10-05）

[结果/边界](deliverables/paper_comparison/v4_adapter_20261004/结果说明.md)、[配置](deliverables/paper_comparison/v4_adapter_20261004/configuration.json)、[计划](docs/superpowers/plans/2026-10-04-v4-residual-adapter.md)。297项相关检查通过；新增9/9动态、完成9回合，81772控制周期/817720子步；累计139，未执行0关闭。网络调用/训练/独立测试0，自动跟踪PAUSED，B.2未完成。 零残差完整轨迹一致2/2；非零F/S脚本完成2/2，脚本功能成功2（不代表SAC学习收益）；B1功能成功1/5个已执行点。独立审核16445个实际搜索参考端点，越界0。 本轮只验证接口、已登记开发工况和脚本作用，不是网络学习、独立评价或完整新训练准入；共同几何/控制/保护保持，旧失败不改写。 runner已消费或关闭本轮额度，禁止重启原目录。

### PC-01｜v4论文对照准备（2026-10-04）

[结果/使用边界](deliverables/paper_comparison/protocol_v4_20261004/结果说明.md)、[机器协议](deliverables/paper_comparison/protocol_v4_20261004/protocol.json)、[接口审计](deliverables/paper_comparison/protocol_v4_20261004/residual_integration_audit.json)。272项相关检查通过；本轮新增动态/物理子步/网络调用/训练更新均0，累计动态130，自动跟踪PAUSED，B.2未完成。 五个封存B2开发点功能5/5、附加精度1/5；平均完成时间12.706s、平均全回合峰值力19.600mN（包含对准零接触点）。16,563个SEARCH命令零残差预测完全一致；132,504次有界XY命令反事实出现6个参考越界，最大16.609nm，均在负Y末段。后者是接口兼容性反例，不是新物理失败或旧训练失败的因果证明。 共同协议/评价实现完成；B1新任务适配、残差v4会话和训练准入尚未完成，没有F/S新任务效果、多种子或独立测试证据。 评价入口tools/evaluation/paper_comparison.py为纯离线模块；封存审计脚本禁止重写当前交付。

### TV-09｜分层几何裁判（2026-10-04）

[结果/使用边界](deliverables/task_variants/layered_referee_20261004/结果说明.md)、[配置](deliverables/task_variants/layered_referee_20261004/configuration.json)、[计划](docs/superpowers/plans/2026-10-04-layered-referee.md)。实际5/5动态，功能成功5、附加严格精度1；36165控制周期/361650物理子步，累计130，余0关闭。236相关检查通过，训练/网络/独立测试0，自动跟踪PAUSED，B.2未完成。 分层几何裁判修复已通过，五个开发工况全部功能成功。 将九针裁判改为圆柱与实际宽入口/窄主孔分层相交后的切平面检查；仍使用1nm容差，控制器、几何、深度/稳定/保护与25秒不变。历史裁判和旧失败保留；未来基线须共用新版裁判。

入口tools/validation/run_layered_referee_preflight.py已消费本轮预算；已有run目录拒绝重启。完整轨迹、控制事件、对照图、停稳核验和输入快照可只读使用。后续新实验须重新登记，不覆写本轮或旧归档。结果限当前开发点和仿真模型；负Y末态贴壁余量约7.45nm，向外10nm扰动即被拒绝。没有独立测试、多种子、硬件证据或方法优于基线的结论；B.2学习评价未完成，训练准入未授予。

### TV-08｜25秒共同任务（2026-10-04）

[结果/使用边界](deliverables/task_variants/deadline25_20261004/结果说明.md)、[配置](deliverables/task_variants/deadline25_20261004/configuration.json)、[计划](docs/superpowers/plans/2026-10-04-deadline25-preflight.md)。实际1/5动态，功能成功0、附加严格精度0；11270控制周期/112700物理子步，累计125，余4关闭。199相关检查通过，训练/网络/独立测试0，自动跟踪PAUSED，B.2未完成。 已完成插入并真实停稳，但现行成功判据仍判失败；新增定位到整针保守几何裁判与分层孔不一致的问题。 仅将共同任务总动作时限改为25秒；当前控制器、几何、功能判据和保护不变。20秒历史失败保留；未来基线须在相同25秒任务版本公平重评。

入口tools/validation/run_deadline25_preflight.py已消费本轮预算；已有run目录拒绝重启。完整轨迹、控制事件、对照图、停稳核验和输入快照可只读使用。后续新实验须重新登记，不覆写本轮或旧归档。正式功能成功0/1、附加严格精度0/1；XY97.607 μm仍超过附加80 μm。分层几何仅离线诊断，未替换运行裁判或授予训练准入；末态余量约7 nm，其他方向、重复性和独立评价均未证明，B.2未完成。

### TV-07｜驱动参考一致性（2026-10-04）

[结果/使用边界](deliverables/task_variants/reference_search_20261004/结果说明.md)、[配置](deliverables/task_variants/reference_search_20261004/configuration.json)、[计划](docs/superpowers/plans/2026-10-04-reference-search.md)。实际1/5动态，功能成功0、附加严格精度0；11000控制周期/110000物理子步，累计124，余4关闭。184相关检查通过，训练/网络/独立测试0，自动跟踪PAUSED，B.2未完成。 本工况参考漂移已修复，插入推进明显改善；完整成功仍未通过。 SEARCH反馈采用目标与当前驱动参考的误差，前馈采用连续目标点差分；按实际驱动限速/加速度预测下一参考，越界受控停止。保留分轴/净推进，恢复后首命令使用重置后的参考与命令。离散末端不可行段最多提前一个控制周期结束，不扩大圆盘；两项恢复观测反例已修复。

入口tools/validation/run_reference_search_preflight.py已消费本轮预算；已有run目录拒绝重启。完整轨迹、控制事件、对照图、停稳核验和输入快照可只读使用。后续新实验须重新登记，不覆写本轮或旧归档。仅负Y150完成1个开发回合：功能/附加严格精度0/1，仿真有效且真实停稳，无接触/运动硬保护；正Y/±X/对准未执行。真实回撤和净推进已在此回合发生，但完整成功、其他方向、多种子及独立评价仍未验证。B.2未完成，不能把传统控制改善当作残差SAC论文收益。

### TV-06｜分轴搜索与净推进（2026-10-04）

[结果/使用边界](deliverables/task_variants/axis_search_20261004/结果说明.md)、[配置](deliverables/task_variants/axis_search_20261004/configuration.json)、[计划](docs/superpowers/plans/2026-10-04-axis-search.md)。实际1/5动态，功能成功0、附加严格精度0；4483控制周期/44830物理子步，累计123，余4关闭。154相关检查通过，训练/网络/独立测试0，自动跟踪PAUSED，B.2未完成。 分轴控制与净推进修复已验证，仍未解决插入失败。 SEARCH禁用XY导纳并冻结内部XY状态，保留原有限螺旋轨迹、Z调载及角向导纳；搜索退出必须超过本段开始前已达到的最深Z 100 μm。旧控制器保持原推进判据，恢复入口非法观测校验经5个反例修复。

入口tools/validation/run_axis_search_preflight.py已消费本轮预算；已有run目录拒绝重启。完整轨迹、控制事件、对照图、停稳核验和输入快照可只读使用。后续新实验须重新登记，不覆写本轮或旧归档。仅负Y150完成1个开发回合：功能/严格精度0/1，仿真有效、真实停稳，无硬保护触发；正Y/±X/对准未运行。旧回撤回程误判已有离线反例验证，本轮为载荷卸载后再搜索，未进入完整回撤恢复，因此不声称新恢复流程已动态验收。B.2、学习收益、独立评价、多种子仍未完成。

### TV-05｜搜索/导纳统一参考（2026-10-04）

[结果/使用边界](deliverables/task_variants/compliant_search_20261004/结果说明.md)、[配置](deliverables/task_variants/compliant_search_20261004/configuration.json)、[计划](docs/superpowers/plans/2026-10-04-compliant-search.md)。实际1/5动态，功能成功0、附加严格精度0；6321控制周期/63210物理子步，累计122，余4关闭。127相关检查通过，训练/网络/独立测试0，自动跟踪PAUSED，B.2未完成。 合成冲突修复生效，功能插入仍失败。 新控制器保留累计导纳纠偏，合成目标投影到120 μm圆盘并同步投影前馈，实际200 μm门及原保护保持。运行后输入异常收口经3反例修复，停止尾段陈旧组成记录已更正。

入口tools/validation/run_compliant_search_preflight.py已消费本轮预算；已有run目录拒绝重启。完整轨迹、控制事件、对照图、停稳核验和输入快照可只读使用。后续新实验必须重新登记，不覆写当前或旧归档。仅负Y150完成1个开发回合，有效停稳且无保护，功能/严格精度0/1；实际推进约0.250 mm，未到约4 mm目标，正Y/±X/对准未执行。当前只能确认搜索位移被控制补偿抵消，不能把接触摩擦认定为已隔离的唯一原因。B.2、学习收益、独立评价和多种子均未完成。

### TV-04｜XY参考与导纳状态同步重设（2026-10-04）

[结果/使用边界](deliverables/task_variants/admittance_rebase_20261004/结果说明.md)、[配置](deliverables/task_variants/admittance_rebase_20261004/configuration.json)、[计划](docs/superpowers/plans/2026-10-04-admittance-rebase.md)。实际1/5动态，功能成功0、附加严格精度0；8553控制周期/85530物理子步，累计121，余4关闭。94相关检查通过，训练/网络/独立测试0，自动跟踪PAUSED，B.2未完成。 同步重设生效，但负Y仍未插入成功。 新会话只在一次有搜索资格的参考释放时重设XY导纳offset/velocity；每段±500 μm额度重新开放已明示。准备配置/模型绑定审查缺口经3反例修复。

入口tools/validation/run_admittance_rebase_preflight.py已消费本轮预算；已有run目录拒绝重启。完整轨迹、控制事件、对照图、停稳核验和输入快照可只读使用。后续新实验必须重新登记，不覆写当前或旧归档。仅负Y150一个开发点完成，新版本正Y/±X/对准未执行；无保护不等于成功，延后失败不算效率改善。末态XY179.907 μm，推进仅0.240551 mm，未到约4 mm深度；B.2、学习收益、独立评价和多种子证据仍未完成。

### TV-03｜SEARCH载荷卸载与参考释放（2026-10-04）

[结果/使用边界](deliverables/task_variants/search_load_20261004/结果说明.md)、[配置](deliverables/task_variants/search_load_20261004/configuration.json)、[实施计划](docs/superpowers/plans/2026-10-04-search-load.md)。新增显式载荷触发控制器与一次XY参考释放会话；原物理状态/保护保持。81相关检查、边界优先级审查修复完成。实际1/5负Y动态，无保护但两次搜索耗尽，0成功，余4关闭；不是B.2或训练资格。

入口tools/validation/run_search_load_preflight.py已消费本轮预算，再运行拒绝已有目录；同目录完整轨迹、停稳审核、旧/新前4244采样核对、对照图与949/693采样导纳饱和诊断可只读使用。后续需新明确方案/预算，不覆写本归档。

### TV-02｜功能任务与共同B2风险卸载（2026-10-04归档）

用途：检查插入功能与额外精度分离后的真实任务表现，并验证一次共同基线风险修复。[使用、范围与结果](deliverables/task_variants/functional_b2_20261003/结果说明.md)、[配置](deliverables/task_variants/functional_b2_20261003/configuration.json)、[计划](docs/superpowers/plans/2026-10-03-functional-b2.md)。已实现显式功能会话、INSERT持续载荷/转角风险卸载；共享默认旧行为保持，旧封存不变。65项相关检查、一次独立审查及错误事件归档修复完成。

实际2/9回合、1功能成功/1力保护、0严格精度成功、2/2有效停稳，累计119。入口`tools/validation/run_functional_preflight.py`已消费本轮预算并关闭余7；再次直接运行会拒绝已有输出，后续须明确新版本/预算。离线分析脚本在封存后拒绝覆盖输出。完整动态和因果边界核对均在交付目录；不是B.2或训练准入。

<!-- stage-resume-delivery -->
<a id="c-stage-resume-20261002"></a>
### B.2/C｜固定50与SEARCH-only配对可行性验证（2026-10-03）

成果：权限会话、匹配档案审核、独立F/S完整学习状态与监督入口已版本化；本轮已收口，保护触发后受控停止，完整配对效果尚不能判断。新启动7/18动态、审核完成7个新回合，另引用12个历史回合，累计109/120；正式更新尝试3500、完成3500/5000批（F2000/S1500）。

实际证据：纯B2：成功3/4个已完成点（计划4）；F冻结末次策略：未执行冻结开发点评价（计划4）；S冻结末次策略：未执行冻结开发点评价（计划4）。19/19个已完成回合有效且停稳；代表恢复未执行，不声称恢复通过。[结果与图](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/结果说明.md)、[机器审核](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/assessment.json)、[完整账本](deliverables/learning_chain/b2_stage_permission_resume_20261003/run/ledger.json)。

使用：先读[计划书](docs/superpowers/plans/2026-10-03-stage-permission-resume.md)及[结果与图](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/结果说明.md)，通过[机器审核](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/assessment.json)定位原始档案与已保存检查点。已消耗的一次性入口不可重跑，旧预算不复用。

限制：限定单训练种子和四个开发点；正式独立测试0、多种子证据未完成，B.2及完整C能力未验收。代表复现不增加性能样本。 未执行11动态、未尝试1500批余量关闭，不结转。 下一项以[项目进度跟踪](项目进度跟踪.md)为准。
<!-- /stage-resume-delivery -->

<!-- stage-permission-delivery -->
<a id="c-stage-permission-20261002"></a>
### B.2/C｜固定50与SEARCH-only配对可行性验证（2026-10-03）

成果：权限会话、匹配档案审核、独立F/S完整学习状态与监督入口已版本化；本轮已收口，运行故障阻止完成配对效果判断。新启动12/30动态、审核完成12回合，累计102/120；正式更新尝试0、完成0/5000批（F0/S0）。

实际证据：纯B2：成功3/4个已完成点（计划4）；F冻结末次策略：未执行冻结开发点评价（计划4）；S冻结末次策略：未执行冻结开发点评价（计划4）。12/12个已完成回合有效且停稳；代表恢复未执行，不声称恢复通过。[结果与图](deliverables/learning_chain/b2_stage_permission_20261002/result_analysis/结果说明.md)、[机器审核](deliverables/learning_chain/b2_stage_permission_20261002/result_analysis/assessment.json)、[完整账本](deliverables/learning_chain/b2_stage_permission_20261002/run/ledger.json)。

使用：先读[计划书](docs/superpowers/plans/2026-10-02-stage-residual-feasibility.md)及[结果与图](deliverables/learning_chain/b2_stage_permission_20261002/result_analysis/结果说明.md)，通过[机器审核](deliverables/learning_chain/b2_stage_permission_20261002/result_analysis/assessment.json)定位原始档案与已保存检查点。已消耗的一次性入口不可重跑，旧预算不复用。

限制：限定单训练种子和四个开发点；正式独立测试0、多种子证据未完成，B.2及完整C能力未验收。代表复现不增加性能样本。 未执行18动态、未尝试5000批余量关闭，不结转。 下一项以[项目进度跟踪](项目进度跟踪.md)为准。
<!-- /stage-permission-delivery -->

### B.2｜100ms预热学习有限验证收口（2026-10-01）

**100ms预热学习验证已收口（2026-10-01）：** 运行故障阻止完成修复判定。共同零更新起点4/4成功；C完成500批、A0批，但我新增的保存代码接口使用错误，C500未落盘且无法恢复，学后评价0。保存修复已完成7项离线检查（模型/优化/物理0），不等于策略修复。新增4/24动态，累计72/92；余20动态/4500批关闭，旧余不使用，自动跟踪PAUSED，B.2未完成。[结果与图](deliverables/learning_chain/b2_temporal_learning_validation_20261001/result_analysis/结果说明.md)、[保存修复](deliverables/learning_chain/b2_temporal_checkpoint_write_fix_20261001/README.md)。

使用：只读结果与原始账本/档案；本轮有效检查点0；独占执行目录不可再次运行。[完整状态索引](deliverables/learning_chain/b2_temporal_learning_validation_20261001/result_analysis/assessment.json)。保存修复及离线验证已完成；本轮故障账本关闭，余20动态/4500批不执行、不结转。后续效果验证必须另行绑定修复版本、明确新起点及累计成本，不能从丢失的C500续跑或重用本轮入口。自动跟踪PAUSED，B.2未完成。

使用范围：本阶段入口/协议可复核，已经尝试的独占执行目录不可重跑；[原始成本](deliverables/learning_chain/b2_temporal_warmup_execution_20261001/run/accounting.json)和[完整轨迹索引](deliverables/learning_chain/b2_temporal_warmup_execution_20261001/run/attempts.json)。本次预检通过，但后续共同起点学习对照未签发预算，不自动训练。

### B.2｜100ms预热真实预检收口（2026-10-01）

**100ms预热配对预检已收口（2026-10-01）：** 完成8回合，实际8/8新动态、完成8回合、成功7（A对照4/4、C候选3/4），训练/网络前向/经验入池均0。采集机制预检通过，但不授予训练或证明策略修复。[实际结果与图](deliverables/learning_chain/b2_temporal_warmup_execution_20261001/result_analysis/结果说明.md)、[独立离线核验](deliverables/learning_chain/b2_temporal_warmup_execution_20261001/result_analysis/assessment.json)。8/8完成回合有效且停稳；累计动态68/68，本轮未执行0次和旧余2/7/19、2000批不结转。103协议通过、入口3处审查问题已修复，历史字节保持，自动跟踪PAUSED，B.2未完成。

### B.2上一准备阶段（历史）｜100ms时间相关预热（2026-10-01）

- **交付与使用：** [完整方案](deliverables/learning_chain/b2_temporal_warmup_design_20261001/修复方案.md)、[8份归档统计](deliverables/learning_chain/b2_temporal_warmup_design_20261001/archive_analysis.json)、[请求持续性图](deliverables/learning_chain/b2_temporal_warmup_design_20261001/request_persistence.png)、[最终18协议](deliverables/learning_chain/b2_temporal_warmup_design_20261001/final_green_protocol.json)；只读准备，不是训练/采集入口。
- **新增能力：** 纯保持内核支持权限清零、阶段切换重抽、周期预算及保存恢复一致性；外部PCG状态需由后续完整检查点共同绑定。
- **限制：** 无新模型/物理/优化；100ms不是已证实最优，初始观察同一限制保留，拟8动态新配对预检未执行；策略修复和B.2仍未完成。

### B.2前项实际结果（历史）｜冻结B500独立评价（2026-10-01）

- **产出与使用：** [逐点结果与两图PNG/PDF](deliverables/learning_chain/b2_actor_lr_b_eval_20261001/result_analysis/结果说明.md)、[完整审核](deliverables/learning_chain/b2_actor_lr_b_eval_20261001/result_analysis/assessment.json)、[成本](deliverables/learning_chain/b2_actor_lr_b_eval_20261001/run/accounting.json)；只读已封存记录，不重跑独占入口。
- **结果：** 保护后受控停止，0/2已执行点成功、2未执行、2/2有效停稳。正X力较低但末端75.1μm超50μm，持续负X修正产生过冲。
- **限制：** 未保持初始4/4，不等于学习修复或B.2完成；A只有一个实测点，缺完整配对。新训练0，累计动态60，余本轮2和旧剩额不结转，PAUSED。

### B.2前轮执行记录｜actor率有限对照受控停止（2026-10-01）

- **产出：** 独立actor率真实实现验证、A500历史学习精确复现、固定A/B500检查点及768状态分布；A正X评价保护失败6287周期有效停稳，完整轨迹/收据/预算保存。
- **使用与证据：** [结果说明及分布PNG/PDF](deliverables/learning_chain/b2_actor_lr_execution_20260930/run_analysis/停止结果说明.md)、[独立机器审核](deliverables/learning_chain/b2_actor_lr_execution_20260930/run_analysis/execution_audit.json)、[效果范围](deliverables/learning_chain/b2_actor_lr_execution_20260930/run_analysis/assessment.json)、[独立审查](deliverables/learning_chain/b2_actor_lr_execution_20260930/run_analysis/独立结果审查.md)。只读结果与冻结检查点，不重跑独占入口。
- **该轮当时的限制：** A保护按预登记规则终止整轮，当时B物理未评价；后续独立B两点失败见上节，初始4/4保持目标未通过，完整配对A/B效果仍缺。B旋转贴边改善不能抵消X偏置和KL增大来宣称修复。父轮实际新1动态/1000批、4合成/8测试/768诊断，余新7及旧19/2000未用；PAUSED，无重试，B.2未完成。

### B.2最新限定交付｜Windows JSON账本替换修复（2026-09-29）

- **能力：** 同一已刷盘临时文件的Windows替换支持有限等待，持续拒绝仍失败；不重复优化或物理操作，不直接覆盖原目标。
- **证据：** [修复说明](deliverables/learning_chain/b2_atomic_write_fix_20260929/README.md)、[机器验收](deliverables/learning_chain/b2_atomic_write_fix_20260929/assessment.json)、真实文件锁复现及112项纯协议回归（含12新增）、一次独立审查。
- **限制：** 2项真实推理旧测试未复验；历史具体占用者未知；单写者约定保持，未验证掉电恢复。修复没有运行物理/优化、没有签发新资格，跟踪PAUSED。
- **原始结果：** 旧轮8动态/144批、未用24次/4356批保持；无更新后完整检查点或最终评价，不能称B.2完成。


### B.2前项限定交付｜Windows入口身份检查修复（2026-09-29）

- **修复能力：** 接受直接登记父进程或本虚拟环境单层启动器，检查镜像路径、父子关系、存活、创建/登记时间；错误身份、过期/PID复用和重复启动保持拒绝。
- **证据与使用：** [57项相关检查及真实进程链](deliverables/learning_chain/b2_windows_parent_fix_20260929/README.md)、[机器验收](deliverables/learning_chain/b2_windows_parent_fix_20260929/assessment.json)、[一次审查](deliverables/learning_chain/b2_windows_parent_fix_20260929/独立审查.md)。实际require_parent/claim在原监督器启动的独立Windows工作与恢复进程中通过，未调用训练入口。
- **限制：** 只验收项目当前Windows入口修复；物理/推理/优化0，不等于实际训练/恢复成功。原失败61文件和原911源输入通过快照保留；当前修改后的源码不能用旧候选直接运行，需新的执行包/资格，跟踪仍暂停。

### B.2前项交付｜有限周期执行准备（2026-09-29）

**获批实际启动的后续结果：** 11:02在学习链创建前发生入口拒绝，已用零物理标准库进程核对确认直接父进程假设错误。准备187检查不等于真实启动通过；新增物理/优化0。原授权/候选/失败保持，未自动重试。[具体证据](deliverables/learning_chain/b2_force_failure_cycle_20260929/启动失败说明.md)。

- **已实现：** 技术资格与独立用户预算授权双门、一次性顺序执行、新进程恢复、完整原始证据门，以及受控停止/原生崩溃/入口拒绝/执行失败/监督异常分类。连续2或累计3训练力保护先保留完成失败回合，再停止余流程。
- **证据与使用：** [执行方案](deliverables/learning_chain/b2_force_failure_cycle_20260929/README.md)、[187项测试](deliverables/learning_chain/b2_force_failure_cycle_20260929/test_binding.json)、[独立审查及修复](deliverables/learning_chain/b2_force_failure_cycle_20260929/独立审查.md)。同初始状态/空池一致，B2档案3/4复用核验；候选绑定911输入，新进程只读技术核验通过，缺授权入口拒绝。使用新入口的verify-only核验，不用旧资格脚本验证改版共享源码。
- **预算与限制：** 32新动态/最多4500批、旧36保留累计68已获用户批准，但唯一入口尝试被拒绝。旧23次/4000批不结转；本轮新增物理/推理/优化0，尚未开始该轮训练。冻结准备证据保持其当时状态，跟踪暂停，不自动重试，B.2及收益未验收。

### B.2前项限定交付｜合格力保护失败学习规则实现

- **已实现：** 新版本规则允许完整审核合格的单独FORCE_LIMIT成为失败经验，保留负终奖；穿透、力矩、运动及数值异常继续拒绝。频率上限先完成阈值失败回合记账，再独立记录受控停止。
- **证据：** [149项相关检查与一次独立审查](deliverables/learning_chain/b2_force_failure_implementation_20260928/README.md)。物理/优化/策略预测0；保存读回仅为零更新合成协议状态。5份原源码快照及两个封存包100/126项文件保持。
- **限制：** 该实现包准备资格明确拒绝运行，旧23次/4000批不结转；新入口、监督器和技术候选见9月29日交付，实际新增预算仍待批准。没有新成功率样本，也不代表B.2或策略收益验收完成。

<a id="a-01"></a>
### A-01｜隔离MuJoCo 3.13 native完整复验

- **获得能力：** 将最小接触异常检查推进到固定Y偏差的完整动力学与实际停止审核。
- **证据范围：** 732项静态检查、两种步长完整Y回合；几何完成与停止审核通过，见[交付说明](deliverables/native313_validation/README.md)。
- **使用入口：** 从上述说明选择对应隔离包与复现命令；不覆盖正式3.9安装。[图与讲解](deliverables/native313_validation/月报讲解.md)。
- **限制：** 该次只验证规定集合和固定Y工况，不代表全部连续域或SAC准入。后续同环境七工况证据见A-02。

<a id="a-02"></a>
### A-02｜新版共同环境B1/B2七工况基线

- **获得能力：** 在同一环境、预算和完整完成标准下比较B1固定导纳与B2搜索恢复，作为后续接口的冻结参照。
- **证据范围：** 14个固定开发回合，B1完整成功1/7、B2为3/7；14/14通过本轮实际停止与安全审核。[完整报告](deliverables/native313_baseline_matrix/README.md)、[机器结果](deliverables/native313_baseline_matrix/report_v1/assessment.json)。
- **使用入口：** [冻结依据](deliverables/native313_baseline_matrix/冻结依据.json)、[阶段交接](deliverables/native313_baseline_matrix/阶段交接_进入残差接口.md)及报告中的复现命令。交接文件的待办是当时快照，最新待办查进度文件。
- **限制：** 允许进入残差接口实现，不等于允许训练；本矩阵回撤计数均为0。不是独立测试集，也不能与旧环境计数直接比较并归因于控制算法提升。

<a id="b1-01"></a>
### B1-01｜兼容会话、周期统计与零残差封装

- **获得能力：** 从整回合B2运行器提炼可逐控制周期推进的会话、只读缓存、周期载荷统计及经验暂存基础。
- **证据范围：** 该交付71/71专项测试、七工况零残差精确回归通过；工程化实际回撤/恢复分支验证。[交付说明](deliverables/residual_interface/implementation_20260923/README.md)、[回归结果](deliverables/residual_interface/zero_compatibility_v2_review_fixes/assessment.json)。
- **使用入口：** 历史封装与测试依据在上述归档；需要当前交互调用方式时优先看B1-03，不用早期只接受零动作的兼容会话替代残差会话。
- **限制：** 这是兼容封装证据，不是学习性能。71项是该版本数量，不与后续94/143项相加。

<a id="b1-02"></a>
### B1-02｜共同守卫候选与动态边界

- **获得能力：** 逐物理子步收集接触、运动和数值事实；锁存停止尾段故障，区分任务判定时间与真实停止时间。
- **证据范围：** 该交付94/94专项；七工况精确回归；六动态探针6/6有效且停稳、5/6达到预登记守卫触发目标。[交付说明](deliverables/residual_interface/guard_candidate_20260923/README.md)、[探针结果](deliverables/residual_interface/guard_boundary_dynamics_v2_review_fixes/assessment.json)。
- **使用入口：** [姿态候选参数记录](deliverables/residual_interface/guard_candidate_20260923/姿态候选参数记录.md)，以及说明中的验证入口。所有候选配置必须显式给出。
- **限制：** 最大实际角约2.513404°，2.5°不是硬上限；负pitch接触试验未过载，不算过载覆盖。该交付时参数未冻结，后续限定记录见B1-09；候选经验仍不可学习。

<a id="b1-03"></a>
### B1-03｜白名单观测、非零残差与Gym交互

- **获得能力：** 120维策略观测、世界XY/roll/pitch四维残差、周期奖励、整回合隔离、非法初始化留档，以及保留正确下一状态的外部截断。
- **证据范围：** 2026-09-24交付143/143学习接口测试；7/7与原始及同守卫版本归档逐字段精确一致，覆盖36708任务周期、4640尾段周期和413480物理子步。原3/7成功不变。[交付说明](deliverables/residual_interface/observation_integration_20260924/README.md)、[动态结果](deliverables/residual_interface/residual_observation_regression_20260924/assessment.json)、[限定验收结论](deliverables/residual_interface/observation_integration_20260924/限定验收结论.json)。
- **使用入口：** [字段表与调用示例](deliverables/residual_interface/observation_integration_20260924/观测与调用约定.md)。只读查看说明即可；复现实验用新tag，不能覆盖归档。
- **限制：** 不是通用SB3训练入口；不允许自动复位/TimeLimit绕过审核。该交付时权限损失只有NumPy参照，PyTorch导入失败，见[历史阻塞记录](deliverables/residual_interface/observation_integration_20260924/学习库阻塞记录.md)。后续独立环境与张量验证见B1-04，原归档不改写。全部候选经验仍隔离，无训练权重或独立学习评价。

<a id="b1-04"></a>
### B1-04｜隔离CPU学习环境与真实张量权限

- **获得能力：** 新建项目内虚拟环境，固定torch2.12.1+cpu/SB3 2.8.0及依赖；实际导入、自动微分、active/inactive权限、单优化器跳步和未训练策略保存加载可验证。
- **证据范围：** 最终完整接口165/165通过，含22项新增专项；原18项RED→GREEN，独立审查新增2项动作/Q梯度反例能识别故意断链；SB3短轨迹各8周期、两次精确一致，经验均隔离。[交付与运行说明](deliverables/residual_interface/learning_tensor_20260924/README.md)、[环境指纹](deliverables/residual_interface/learning_tensor_20260924/environment.json)、[限定验收](deliverables/residual_interface/learning_tensor_20260924/assessment.json)。
- **使用入口：** 上述说明给出新解释器、测试命令及固定依赖复建方式；旧解释器的用户级torch故障仍在。后续测试不要照抄B1-03旧命令运行新增张量模块。
- **限制：** B1-04交付时未实现SAC采集/经验发布；后续限定适配见B1-05，原证据不改写。没有训练权重、性能提升或独立评价。CPU并非正式训练设备结论，短trace不是完整装配评价。

<a id="b1-05"></a>
### B1-05｜候选策略采集与整回合经验池

- **获得能力：** 未训练SAC策略调用现有环境，采集批次间续用同一回合；显式截断委托原停止审核。独立经验池完整校验后一次发布，按完整回合淘汰，支持权限/变时长折扣张量抽样；异常记录与待发布重试不重跑物理。
- **证据范围：** 最终完整接口205/205通过，包含40项本轮专项。真实候选8周期分批采集及停止审核，经验全部隔离、策略参数不变；合成数据验证正向发布、无效整段拒绝、容量和重复ID、真实截止点bootstrap。见[限定验收](deliverables/residual_interface/collection_replay_20260924/assessment.json)。
- **使用入口：** [说明与复验命令](deliverables/residual_interface/collection_replay_20260924/README.md)、[验收记录](deliverables/residual_interface/collection_replay_20260924/验收记录.md)。继续使用B1-04隔离解释器，不能用通用SB3逐步入池或自动reset替代。
- **限制：** 候选采集器固定拒绝训练准入，不能将已隔离回合改标后用于学习。正向入池只有合成协议证据；还不是绑定正式准入的训练采集器或完整学习循环。仅单所有者内存原子发布，不含持久化、并发写或完整训练器恢复；没有SAC学习更新、独立评价或新训练权重。

<a id="b1-06"></a>
### B1-06｜工程范围与非零残差动态预检

- **获得能力：** 新的预登记/逐次留档入口，在原B2与候选守卫下执行工程XY域复位、完整零残差参照和有界非零动作；检查观测、命令作用、权限、数值有效性及最终实际停止。异常保留，停止收尾不能洗掉先前失败，执行工况/动作必须与登记逐项对应。
- **证据范围：** 9/9初始化有效；17/17动态有效且停稳。5个零残差为1成功/4普通失败；8个单轴非零均普通失败；4个四角组合均力保护退出。12个非零均有接触和命令层作用，2例自行回撤恢复、最终仍保护失败。最终完整接口236/236通过，含31项新增专项；813生产输入与快照、26份测试源码和全部26次原始记录留存。
- **使用入口：** [说明与复验](deliverables/residual_interface/engineering_preflight_20260924/README.md)、[机器判定](deliverables/residual_interface/engineering_preflight_20260924/assessment.json)、[验收及负结果](deliverables/residual_interface/engineering_preflight_20260924/验收记录.md)、[原始归档核验](deliverables/residual_interface/engineering_preflight_20260924/归档核验.json)。沿用B1-04隔离解释器，重跑必须新tag，禁止覆盖本次尝试。
- **限制：** 初始倾角均为0，固定动作不是SAC策略。最大实际角2.160632°，没有覆盖2.5°边界或初始±1.5°范围，不冻结模型/姿态域。经验仍不可学习，无训练权重、策略收益或独立评价。完整矩阵字面常量单测的次要维护项延期，未来改矩阵必须重审完整预登记。

<a id="b1-07"></a>
### B1-07｜姿态参数与模型范围冻结审查

- **获得结论：** 2.5°保留为候选检测/停止触发角，不冻结。旧自由接近2.513404°超调与工程接触动态最大2.160632°不能拼成接触态边界保证；初始工程角0与后续±1.5°分布分开。
- **新增证据：** 预登记243个规定静态点，241点有1969个对应针孔正见证，检出/有限性检查全部通过；但240边界点穿透>30μm，其中156点>80μm。单一角度范围不是模型有效性的充分条件，原守卫全部保留。相关既有几何测试14通过，2旧SDF特定用例未选；未改生产代码。
- **使用入口：** [审查结论](deliverables/residual_interface/pose_scope_review_20260924/README.md)、[完整预登记](deliverables/residual_interface/pose_scope_review_20260924/protocol.json)、[实际静态结果](deliverables/residual_interface/pose_scope_review_20260924/static_assessment.json)、[核验说明](deliverables/residual_interface/pose_scope_review_20260924/核验说明.md)。全体原始记录保留，不用旧目录重跑覆盖；下一项动态补验预算在说明中列明。
- **限制：** 强制静态姿态不是正常闭环到达的状态；没有新增动力学回合，不证明数值失稳，也不是新初始化许可、连续域/D形外壳认证或实物载荷标定。2.52°仅诊断取样；模型/参数/训练许可均false。

<a id="b1-08"></a>
### B1-08｜有界时变残差与边界停止补验

- **获得能力与证据：** 固定整数周期切换动作、保留每段请求/权限/作用及首次新增保护的物理子步状态。预登记8完整回合全部有效且实际停稳，有接触和残差命令作用；0成功/5普通失败/2力保护/1姿态越界，全部尝试保留。
- **新增联合证据：** 四角0经历接触后触发2.5°，最大2.503932491°；触发瞬间无接触，停止尾段2个接触端点最大2.502420275°，最终停稳。整体最大穿透7.340108μm；不把本例超调当普遍上界或原始触发数当合格域证明。
- **使用入口：** [交付及剩余路径](deliverables/residual_interface/scheduled_boundary_20260926/README.md)、[机器协议](deliverables/residual_interface/scheduled_boundary_20260926/protocol.json)、[实际判定](deliverables/residual_interface/scheduled_boundary_20260926/assessment.json)、[原始复算](deliverables/residual_interface/scheduled_boundary_20260926/归档核验.json)、[审查及测试](deliverables/residual_interface/scheduled_boundary_20260926/核验说明.md)。复跑须用隔离解释器和全新tag。
- **验证与限制：** 22新专项、最终完整258通过；旧非编译429+隔离1通过，23编译不运行。修复新验证入口异常留档，原生产学习/物理/模型不变。次要计数语义与观察器触发分支对照缺口保留。没有SAC、准入或正式参数冻结；8回合后不追加同类试验。
- **阶段纠正：** 下一项B.1收口包集中处理限定范围/参数记录、准入、配置及独立成本；原设计中的完整训练/恢复属于B.2，不再混列为B.1前置。扩大初始倾角与实机任务仍后置。

<a id="b1-09"></a>
### B1-09｜限定工程范围的B.1收口与正式准入

- **获得能力：** 范围/参数独立记录、真实环境参数检查、源码/依赖/证据/配置绑定、全回归准入入口、缺项或变更拒绝，以及独立成本和首训预算。正式7门全部通过，B.1按限定工程范围已验收。
- **证据范围：** 当前完整294测试通过535.79s，含36新增；旧非编译429+隔离1通过。849项输入及源码快照、241项绑定证据；历史26/8次预检和14基线归档复算，不重新计作实验样本。
- **使用入口：** [交付与复核命令](deliverables/residual_interface/b1_closeout_20260926/README.md)、[实际准入](deliverables/residual_interface/b1_closeout_20260926/admission.json)、[参数记录](docs/stage_b/工程范围与姿态参数冻结记录_v1.md)、[首训配置](docs/stage_b/工程短训配置_v1.json)、[独立成本](deliverables/residual_interface/b1_cost_20260926/README.md)、[审查与失败记录](deliverables/residual_interface/b1_closeout_20260926/checks/核验说明.md)。使用B1-04隔离解释器，重新验收必须新输出目录。
- **成本与配置：** CPU单进程、20,000周期目标、完整回合后结束；仅重复已有中心/+X轨迹计时，3065周期/1863接触周期、有效停稳但普通任务失败。按33,000周期估算基础约21.2分钟+逐回合开销，预留60分钟而非硬上界。网络计算无参数更新。
- **限制：** 只限XY各±50μm、初始零倾角工程链路；2.5°是停止触发值，不是模型可信上界。候选数据仍不可直接学习，完整合格采集/SAC更新/保存恢复/评价属B.2；没有策略收益或独立评价。异常诊断尾段、继承模型局限及非常规故障不被本次资格消除。后续代码变化需新绑定，不能改旧摘要掩盖差异。

<a id="b2-01"></a>
### B2-01｜正式准入采集与整回合审核发布

- **获得能力：** 工程XY均匀采样、开始与发布前当前资格核验、原始回合先归档、整回合审核后原子入池及失败重试；沿用原物理会话，不追认旧候选数据。
- **证据范围：** 新增44项、完整338项学习接口测试通过；3个预登记新尝试有效停稳并发布6118条转移，含2个完整任务回合及1个8周期真实截断。中心/+X完整物理轨迹与B.1成本归档精确一致；抽取256条张量只证明抽样接口可用，不是256个独立样本。
- **使用入口：** [说明与复核命令](deliverables/learning_chain/b2_collection_20260926/README.md)、[实际判定](deliverables/learning_chain/b2_collection_20260926/assessment.json)、[新采集资格](deliverables/learning_chain/b2_collection_20260926/admission.json)、[审查及负结果](deliverables/learning_chain/b2_collection_20260926/核验说明.md)。使用原隔离CPU解释器；重跑使用全新输出目录。
- **版本与成本：** 849项原输入不变，新增5项后绑定854；单独采集验收235.90s含初始化、停止与归档，不是实际学习成本。交付保存新增源码及三份滚动文档快照，原始资产继续依赖现有工作目录。
- **限制：** `collection_admitted=true`仅授权当前正式采集，`runnable_trainer=false`；优化器更新0、策略权重未变。没有完整训练状态恢复、策略收益或独立评价；进程内重试不是崩溃后续训。范围仍为XY各±50μm、初始角0，2.5°仍仅是操作停止触发值。

<a id="b2-02"></a>
### B2-02｜SAC实际更新与有界接线验收

- **获得能力：** 整回合合格发布后进行SAC双critic、actor、温度及目标软更新；累计更新信用、独立随机流和批次异常回滚。更新后的采集原始档案记录真实更新计数和策略摘要。
- **证据范围：** 完整375项学习接口通过，含37新增；3个新尝试发布6098条转移，16批真实更新后4类参数块变化。从原始经验重建后更新数值和更新后8次动作精确重放；不是控制性能改善。
- **使用入口：** [说明与只读复核](deliverables/learning_chain/b2_sac_update_20260926/README.md)、[实际判定](deliverables/learning_chain/b2_sac_update_20260926/assessment.json)、[逐批指标](deliverables/learning_chain/b2_sac_update_20260926/updates.json)、[核验及限制](deliverables/learning_chain/b2_sac_update_20260926/核验说明.md)。沿用隔离CPU解释器；复核重新执行数值更新，不重新积分物理。
- **版本与成本：** 原854项输入不改、新增7项绑定861；全流程252.33s，16批更新均值26.178ms，含经验抽样及事务快照，不是长训吞吐保证。
- **限制：** 本历史交付只覆盖最多16批更新探针，当时未验收完整恢复、首次短训或固定开发评价；后续证据见B2-03/04。独立测试仍未进行，模型、保护、奖励及工程范围均未改变。

<a id="b2-03"></a>
### B2-03｜完整学习状态保存与跨进程续跑

- **获得能力：** 回合审核发布边界的完整学习状态保存与恢复；经验池含已淘汰ID、原始回合和发布凭据，网络/目标/三类Adam/温度、随机流、初始化/信用/历史计数及来源资格均保留。异常或未完成状态拒绝，临时写入不构成有效检查点。
- **证据范围：** 完整421测试通过，含46新增；真实2个完整预热回合后更新8批保存，连续和新进程分支各继续8批及同一8周期物理截断，下一抽样/更新/初始化/动作/完整最终状态精确一致，并从原始档案独立数值复算。
- **使用入口：** [说明及复核命令](deliverables/learning_chain/b2_checkpoint_20260926/README.md)、[实际判定](deliverables/learning_chain/b2_checkpoint_20260926/assessment.json)、[核验记录](deliverables/learning_chain/b2_checkpoint_20260926/核验说明.md)、[检查点凭据](deliverables/learning_chain/b2_checkpoint_20260926/checkpoint_receipt.json)。只读复核不重新积分；恢复须使用固定摘要与新输出目录。
- **版本与成本：** 原861输入不变，新增5项后绑定866；执行段384.88s，初始保存15.15s、新进程加载16.75s，含必要资格/档案验证开销。
- **限制：** 本历史交付是16批有界恢复验收；单分支6098转移，实际4次物理尝试6106转移含配对重复。首次短训后续见B2-04，策略收益与独立评价仍未验收；不支持回合中途物理恢复，不承诺跨机/GPU或任意文件系统断电恢复。

<a id="b2-04"></a>
### B2-04｜首次工程短训与固定开发集配对评价

- **获得能力：** 全新SAC训练、目标后完成整回合、消耗已发布信用并逐回合保存；最终检查点在新进程恢复后完成8点×2方法评价，评价不改变训练状态。
- **证据范围：** 443测试通过（含22新增）；7个完整训练回合、21,315条审核转移（超出1,315）、4,078批critic更新。原始动作/更新/状态与评价指标均可数值复核，全部尝试保留。
- **开发结果：** 固定8点零残差B2完整成功8/8，确定性SAC为7/8；16次仿真有效且停稳，接触/有效残差/裁剪/平滑性逐例报告；不把训练回合回报当固定策略性能。
- **使用入口：** [说明和复核](deliverables/learning_chain/b2_engineering_short_train_20260926/README.md)、[判定](deliverables/learning_chain/b2_engineering_short_train_20260926/assessment.json)、[最终选择及摘要](deliverables/learning_chain/b2_engineering_short_train_20260926/selection.json)、[训练诊断图](deliverables/learning_chain/b2_engineering_short_train_20260926/figures/01_训练链路与数值诊断.png)、[固定开发配对图](deliverables/learning_chain/b2_engineering_short_train_20260926/figures/02_固定开发集配对.png)。
- **成本与版本：** 首训执行1054.29s，16次评价1914.28s另列；864继承输入不变，2学习文件修改、6新增，资格绑定872。历史源码由原快照解释，旧摘要不改。
- **限制：** 单种子、既有小XY开发集结果，不是独立测试或泛化收益证据；工程范围、模型、保护和奖励均未扩大。同环境CPU边界恢复，不是中途物理恢复或独立通用安装包；B.2和原任务6仍未整体验收。

<a id="history"></a>
<a id="b2-05"></a>
### B2-05｜无接触可辨识性与残差漂移诊断

- **获得结论：** 三次既有失败定位到XY精度；策略有效期反馈不可区分、动作相同，固定平移与实际命令积分吻合；奖励/熵同口径复算完成。
- **使用：** [诊断报告及复算命令](deliverables/learning_chain/b2_observability_diagnosis_20260927/README.md)、[机器结果](deliverables/learning_chain/b2_observability_diagnosis_20260927/diagnosis.json)、[诊断图](deliverables/learning_chain/b2_observability_diagnosis_20260927/figures/01_可辨识性与尺度诊断.png)。
- **证据：** 23旧档案、最终冻结检查点；114文件/872源配置完整性核验；14315同权限行离线数值复算；二次复算一致。
- **限制：** 零新增物理回合/更新，不新增成功率样本；3.57倍仅即时尺度比，未证明漂移唯一成因；443测试为历史结果。
- **后续提案：** [9初始化/17动态的接触开发预检](deliverables/learning_chain/b2_observability_diagnosis_20260927/下一项建议.md)，后续已完成B2-06诊断，不是训练准入。

<a id="b2-06"></a>
### B2-06｜有限接触开发预检与作用诊断

- **结果：** 9初始化有效、17动态均有效停稳；零残差4/9成功，脉冲6/8成功（组别点位不同，不直接比成功率）；信息门通过，局部位移作用门7/8，未全过。四个75μm沿轴点均无接触且精度失败；四个100μm沿轴点有接触，零残差3/4成功。8个INSERT早期脉冲局部位置差仅0.871—6.129nm，载荷与后续基线响应可改变，不能等同于工程幅度纠偏。
- **使用入口：** [报告与复验命令](deliverables/learning_chain/b2_contact_preflight_20260927/README.md)、[机器结果](deliverables/learning_chain/b2_contact_preflight_20260927/assessment.json)、[作用分解](deliverables/learning_chain/b2_contact_preflight_20260927/command_effects.json)、[图表](deliverables/learning_chain/b2_contact_preflight_20260927/figures/01_零残差与脉冲物理作用.png)。
- **验证与成本：** 45相关测试通过，3项Important修复，872输入不变，原始档案二次复算；单进程执行3523.48s，详见[实施记录](deliverables/learning_chain/b2_contact_preflight_20260927/实施记录.md)。
- **限制：** 这是一组固定开发诊断，不是SAC效果比较；1nm是可检测参考，不能等同于工程幅度纠偏；无非零初始姿态/SEARCH/转动作用资格。
- **后续：** [8回合SEARCH四维诊断建议](deliverables/learning_chain/b2_contact_preflight_20260927/下一项建议.md)，已按B2-07执行；不自动授权新训练。

<a id="b2-07"></a>
### B2-07｜SEARCH阶段四轴局部作用诊断

- **获得内容：** B2-07完成8个SEARCH四轴正负脉冲诊断，8个有效停稳，0个完整成功；局部工程幅度参考达标：平移0/8、转动0/8。固定脉冲不是学习策略，本轮SAC更新0，训练资格未扩展。
- **使用入口：** [结果与复算用法](deliverables/learning_chain/b2_search_action_probe_20260927/README.md)、[原始机器指标](deliverables/learning_chain/b2_search_action_probe_20260927/assessment.json)、[结论与边界](deliverables/learning_chain/b2_search_action_probe_20260927/结论与边界.md)、[后续方案](deliverables/learning_chain/b2_search_action_probe_20260927/下一项建议.md)。
- **证据：** 54相关测试；872输入、旧190档案未变；完整原始动作/状态及停止记录复算。B2-07仅检验首次SEARCH起始0.2秒：八例均有效停稳但任务失败；实际位置差0.723—5.998nm、转角差0.071—1.214μrad，均未达到预登记工程幅度。参考与载荷可改变，后段基线自身也能明显运动，不能把早期微小响应外推为整个SEARCH或SAC无效。
- **限制：** 单开发点、固定脉冲、更新0；不能称训练收益。基线拒绝分支的候选请求计数Minor延期，不能作实际施加证据；有效轨迹以原始动作日志核验。

- **后续：** 已按B2-08完成11档案离线诊断，结果见下一条；原B2-07协议和阈值不变。

<a id="b2-08"></a>
### B2-08｜动作到实际运动的数据链离线诊断

- **获得内容：** B2-08完成11档案动作链离线诊断，49,270正常周期命令精确重放；参考减量主要来自B2反馈反向修正，早期接触反力承受大部分新增驱动力。新增物理0、更新0，尚不能认定SAC算法失败，也未扩展训练资格。
- **使用入口：** [证据链/全窗口表及复算](deliverables/learning_chain/b2_action_chain_diagnosis_20260927/README.md)、[机器分解](deliverables/learning_chain/b2_action_chain_diagnosis_20260927/decomposition.json)、[核验说明](deliverables/learning_chain/b2_action_chain_diagnosis_20260927/核验说明.md)。
- **验证：** 7项离线测试、11档案及分解精确复算；872输入与233旧封存文件保持。
- **限制与后续：** 不能从端点合力唯一归因摩擦、几何或求解器。[有限对照方案](deliverables/learning_chain/b2_action_chain_diagnosis_20260927/下一项建议.md)已按B2-09执行，原方案和档案保持，不授予新训练资格。

<a id="b2-09"></a>
### B2-09｜运动状态触发的±X对照

- **获得内容：** B2-09完成运动状态触发的±X对照：启动2回合，2个有效停稳且无守卫，0个完整成功；完整脉冲窗口2/2。局部位置最大差为1.98399/1.66572μm（负/正）；双侧候选判据通过。新增SAC更新0，训练资格未扩展。
- **使用入口：** [报告/图与复算](deliverables/learning_chain/b2_motion_state_probe_20260927/README.md)、[原始指标](deliverables/learning_chain/b2_motion_state_probe_20260927/assessment.json)、[核验](deliverables/learning_chain/b2_motion_state_probe_20260927/核验说明.md)。
- **证据：** 93相关测试、872输入及264旧封存文件核验；原始动作/前缀/停止门和B2积分分解二次复算一致。
- **限制与后续：** 建议B2-10在四个已有100μm沿轴零倾角接触点，各用两条真实预热规则的四维随机动作序列，最多8回合、更新0；具体触发/失败停止/预算方案已给出，尚未执行，先沟通再冻结。两侧局部作用通过不直接授予SAC探索训练资格。 [具体决策](deliverables/learning_chain/b2_motion_state_probe_20260927/下一步决策.md)。

<a id="b2-10"></a>
### B2-10｜代表性预热探索候选预检

- **获得内容：** B2-10启动8/8回合，归档8回合；8个有效停稳且未触发保护，完整成功6个，未执行0个。8回合均满足预检条件，仅支持下一项小规模接触学习方案和准入版本审查，尚未授予训练资格。
- **使用入口：** [报告与复算](deliverables/learning_chain/b2_warmup_preflight_20260927/README.md)、[原始结果](deliverables/learning_chain/b2_warmup_preflight_20260927/assessment.json)、[全部尝试](deliverables/learning_chain/b2_warmup_preflight_20260927/attempts.json)。
- **验证：** 80相关测试，输入与旧封存档案保持；新进程复算一致，零训练更新。
- **限制与后续：** 建议B2-11进入四点接触短训方案与准入版本审查：保留负X困难点，独立登记新训练范围和预算，验证采样/资格绑定；本准备项新增物理与优化更新0，完成后再作具体开训决策。当前预检通过不自动扩大旧±50μm工程训练资格。 [具体决策](deliverables/learning_chain/b2_warmup_preflight_20260927/下一步决策.md)。

<a id="b2-11"></a>
### B2-11｜四点接触短训准备与准入审查

- **获得内容：** B2-11完成四点接触配置、确定性采样/恢复、预算状态机与证据绑定；98项相关测试通过，准备记录复核通过。正式接触采集、更新及检查点执行适配尚未接通，training_admitted=false；新增物理回合和优化更新均0。
- **使用入口：** [报告](deliverables/learning_chain/b2_contact_preparation_20260927/README.md)、[独立配置](docs/stage_b/四点接触短训配置_v1.json)、[准备记录](deliverables/learning_chain/b2_contact_preparation_20260927/preparation.json)。
- **证据：** 98相关测试，精确测试身份与测试前后源码绑定，872原输入/345旧封存文件保持，准备记录独立进程复核。
- **限制：** 纯采样/预算模型不是正式学习许可；六次等概率选点不覆盖正Y；无新增物理或优化更新。
- **下一项：** 下一项B2-12应接通接触范围的正式采集、SAC配置/种子、检查点恢复、六回合驱动及四点开发评价适配，验证保护前发布门和失败保存后生成独立正式准入。先完成代码/离线验收，不直接启动物理短训；具体预算和受影响历史输入按新增执行版本审查。 [具体范围](deliverables/learning_chain/b2_contact_preparation_20260927/下一步决策.md)。

<a id="b2-12"></a>
### B2-12｜接触执行适配与正式准入

- **获得内容：** B2-12已接通四点接触采集、SAC、完整检查点、累计六次启动驱动及四点确定性评价，正式执行资格通过；136项相关检查通过，3次合成更新的新进程恢复状态一致。新增物理回合0，尚未启动接触短训。
- **使用入口：** [报告及命令](deliverables/learning_chain/b2_contact_execution_20260927/README.md)、[准入](deliverables/learning_chain/b2_contact_execution_20260927/admission.json)、[判定](deliverables/learning_chain/b2_contact_execution_20260927/assessment.json)。
- **证据：** 136项相关检查，3次合成更新独立恢复一致，879输入重新绑定；四个旧文件准确快照保留。
- **限制：** 只支持四固定100μm轴向点、零初始倾角；前六次采样不覆盖正Y；没有新增物理或独立评价。
- **下一项：** B2-13建议按冻结种子和四点范围启动首次接触短训：20k审核周期目标、最多6次启动、整回合结束、总审核周期严格小于33k；首次保护/无效/未停稳/归档或输入故障即停止。最终边界检查点另进程进行四点各一次确定性开发评价，复用未变共同版本的B2-06零残差对照。实际开训预算须先明确批准。 [具体预算](deliverables/learning_chain/b2_contact_execution_20260927/下一步决策.md)。

<a id="b2-13"></a>
### B2-13｜首次接触短训与固定开发评价

- **获得结果：** B2-13首次接触短训完成：4个训练回合、22,722条审核转移、4,430次critic更新；固定四点确定性SAC成功3/4，复用同共同版本零残差B2为3/4。
- **使用入口：** [报告](deliverables/learning_chain/b2_contact_short_train_20260927/README.md)、[原始复算](deliverables/learning_chain/b2_contact_short_train_20260927/assessment.json)、[预登记](deliverables/learning_chain/b2_contact_short_train_20260927/protocol.json)。
- **限制：** 执行链和开发评价完成；本次成功率未提升，终末误差有好有坏，峰值力未降低，尚未取得一致收益证据。独立测试未使用，全部尝试保留；不得直接重复一次性运行入口消除失败。
- **下一项：** 建议B2-14只做本轮档案的有限离线复盘：核对实际训练只覆盖正X一次、负X三次的影响，比较成功/失败回报与接触后的策略响应，给出下一次训练的最小预算方案。保持已查明的动作链和执行接口，不重做脉冲诊断；增加步数、改变采样或采用多种子均先明确方案后沟通，本项不自动追加物理或更新。

<a id="b2-14"></a>
### B2-14｜学习效果与关键瓶颈审查

- **获得结论：** 残差SAC没有有限训练必然超过B2的保证；已见成功终末奖励9.9998而Q仅0.8611～0.8739；无动作尾段起点真实折扣回报8.0178而Q接近0，确认当前价值拟合不足。
- **使用入口：** [报告](deliverables/learning_chain/b2_learning_effect_review_20260927/README.md)、[机器结果](deliverables/learning_chain/b2_learning_effect_review_20260927/assessment.json)；报告含只读复算命令和理论来源。
- **验证：** 4训练/4开发评价/4旧基线；重建4,430批原索引，187次终末行抽样分布于181批，日志与最终随机状态一致；61个B2-13封存文件保持，独立进程精确复算。新增物理/优化更新0。
- **限制与后续：** 终末稀少、长尾段和覆盖不足已确认，其因果贡献尚未隔离；先沟通固定策略价值对照，再讨论保证四点覆盖的训练。检查通过与策略收益仍分列。

<a id="b2-15"></a>
### B2-15｜固定策略价值对照与部分改善

- **实际状态：** 首轮2,000次因Adam张量共享作废；经用户批准，修正版额外2,000次完成并独立复核。完整尾段目标训练终末MAE0.1739，原一步目标5.3061；最后可动作误差仍4.7380，完整改善未通过。
- **使用入口：** [结果与失败说明](deliverables/learning_chain/b2_value_target_probe_20260927/README.md)、[机器判定](deliverables/learning_chain/b2_value_target_probe_20260927/assessment.json)、[原失败档案](deliverables/learning_chain/b2_value_target_probe_20260927/run/failure.json)、[批准记录](deliverables/learning_chain/b2_value_target_probe_20260927/authorization_v2.json)。
- **修正与验证：** 独立复制状态，修正版9项检查通过；运行前后独立性与计数通过，新进程指标精确复算；旧61文件和879输入保持。
- **边界：** 累计4,000次含作废2,000次；物理、actor和温度更新0。不并入正式SAC训练；终末标志在停止后才出现，不能以终末准确推断纠偏策略有效。2026-09-27高级别审查后，原单独边界诊断建议由下方有限推进方案替代；原MAE诊断门不提升为策略收益验收门。

<a id="b2-native-repair"></a>
### B.2｜原生碰撞崩溃与容量修复（2026-09-28）

- **获得能力：** 保存精确故障状态，单次forward复现并定位到第7针/孔壁接触；证实EPA临时数组第25项超出24项容量。只扩大两处分配及一处偏移，形成独立运行库修复。
- **验证证据：** 原版哨兵越界4字节→修复0；同编译环境未修复版仍崩溃，修复完整forward状态有限且警告0；同种子/动作流完整6311周期成功停稳、无守卫违规。[报告](deliverables/learning_chain/b2_native_crash_20260928/README.md)、[机器复核](deliverables/learning_chain/b2_native_crash_20260928/assessment.json)、[独立审查](deliverables/learning_chain/b2_native_crash_20260928/review.md)。
- **使用入口：** [构建与DLL](deliverables/learning_chain/b2_native_crash_20260928/build.json)、[修复脚本](deliverables/learning_chain/b2_native_crash_20260928/patch_horizon.py)、[离线核验](deliverables/learning_chain/b2_native_crash_20260928/verify_repair.py)。整个候选包固定摘要，原DLL和890输入/84历史/25重试绑定保持。
- **限制：** 新增2诊断动态，优化/经验发布0；随机预热成功不是策略收益，不证明全引擎或全部轨迹等价。旧运行与一次重试保留失败；新运行库严格资格尚待建立，不能使用诊断依赖替换直接训练。B.2整体未完成。

### B.2接续入口状态补充（2026-09-28）

截至2026-09-28 16:47，本轮已停止：第10个训练回合（负X100微米）在恢复后于10.7646秒触发30微米穿透保护，触发周期末穿透约30.104微米；仿真有效并完成停稳，无原生崩溃。前9回合发布49313条经验并完成3000批更新；第10回合6383条全部拒绝入池。本轮18次启动、连历史累计27/45，剩余18次及1500批不自动执行。最终开发、恢复和独立评价均未完成，B.2未完成，尚无学习收益证据；自动跟踪已暂停。 [停止证据](deliverables/learning_chain/b2_repaired_cycle_v2_20260928/assessment.json)。

停止后效果分析：停止后离线核对18份轨迹发现：四个预热成功2/4，更新后六次随机采集0/6（五任务失败、一接触保护），不同中间策略不能当最终成功率。三次到达目标深度却以0.96～1.29度停住，超过0.5度成功门；首个更新后回合roll请求96.8%的有权限周期贴近动作边界。保护后后续周期动作均归零，恢复后约0.9366秒触发穿透。已有明确不利行为证据，但最终效果与唯一学习成因仍未验证。分析新增物理/更新0。 [证据](deliverables/learning_chain/b2_repaired_cycle_v2_20260928/停止后效果分析.md)。

## 历史能力与诊断索引

以下用于追溯模型来源、实验决策与负结果，不替代上方新版共同环境证据。原报告中的待办不自动恢复为今天的任务。

<a id="h-01"></a>
### H-01｜几何、接触验证与显示资料

[原CAD](DSub9_Deliverables_V4/)、[碰撞几何报告](reports/collision_geometry_report.md)、[V1接触验证](reports/v1_contact_validation_report.md)、[V1适用性诊断](deliverables/v1_applicability/V1开发适用性诊断报告.md)、[凸分块覆盖修复](deliverables/contact_coverage_repair/接触覆盖修复报告.md)。用途是说明几何与碰撞模型来源、覆盖检查和替代路径；规定姿态扫描不等于动态闭环装配，旧SDF/128段/256段结果须按版本解释。

<a id="h-02"></a>
### H-02｜动态执行器与早期B1

[动态执行器验证](deliverables/dynamic_actuator_v1/动态执行器验证报告.md)、[B1开发报告](deliverables/b1_fixed_admittance/B1固定导纳_开发报告.md)、[9月16日讲稿](deliverables/monthly_progress/2026-09/一页汇报讲稿.md)。已建立接触影响实际运动、固定导纳及轨迹回放；采用简化笛卡尔动态执行器，不是完整CR5/真实夹爪。早期零反馈/B1对照不与新版B1/B2矩阵混用。

<a id="h-03"></a>
### H-03｜B2搜索恢复开发与有预算的候选比较

| 资料 | 用途及结论边界 |
|---|---|
| [B2七工况对照](deliverables/b2_search_recovery/matrix_v1_7cases/B2-4七工况对照报告.md) | 从单工况扩展到开发对照；旧环境深度到位仍可能精度不合格 |
| [退出条件复测](deliverables/b2_exit_gate_v2/README.md) | 严格退出条件未改善表现，保留原基线和退步证据 |
| [切换诊断](deliverables/b2_switch_diagnosis/README.md) | 离线定位同时改变的控制分量，不是新增动力学实验 |
| [X单变量试验](deliverables/b2_xy_probe/README.md)、[Y同参数检验](deliverables/b2_y_probe/README.md) | X恢复深度但精度未达标，Y未恢复；不能以单例宣称普遍有效 |
| [X/Y接触差异诊断](deliverables/b2_xy_contact_diagnosis/README.md) | 区分几何投影、实际接触与反馈；不宣称唯一根因 |
| [基线收尾与训练前审查](deliverables/baseline_training_readiness/README.md) | 一次有预算候选比较无完整成功增益，保留原B2；当时停止阻塞转入H-04排查 |

<a id="h-04"></a>
### H-04｜停止与接触可靠性诊断、被拒绝候选及最小复现

[停止问题定位](deliverables/stop_reliability/README.md) → [接触一致性候选](deliverables/contact_consistency_repair/README.md) → [最小复现包说明](deliverables/contact_minimal_reproducer/README.md) → [A-01新版完整复验](#a-01)。

该链保留了“短回合检查通过但长回合不能持续停稳”“静态候选通过但减半步长出现异常”的负结果。最小复现中的两个严重异常在新版native未重现，不自动证明所有接触正确；后续仍经过完整回归。关闭接触只作定位，不能计装配成功。

## 规划与管理资料

### 管理审查｜观测与活动代码复杂度（2026-10-06）

获得只读代码/归档审查和参考可达性计算，未增加研究能力或修改生产实现。 [报告与修复顺序](deliverables/project_audit/complexity_20261006/客观审查与修复优先级.md)、[机器指标](deliverables/project_audit/complexity_20261006/audit_metrics.json)、[参考反事实](deliverables/project_audit/complexity_20261006/reference_counterfactual.json)、[只读复算脚本](deliverables/project_audit/complexity_20261006/audit.py)。复算使用现有隔离CPU解释器，不调用物理或SAC；历史归档不可覆盖。17项追加观测尚未证明必要性，4维动作不变；200行SAC重复可见。边界修复/精简尚未实施，B.2未完成。


**2026-09-27 B.2高级别审查与规划：** [有限修正、训练与评价方案](docs/superpowers/plans/2026-09-27-b2-bounded-learning-cycle.md)。GPT-6 Astra / xhigh独立审查后，明确覆盖不足已知、唯一失败根因未证实；提出保留2ms的一次尾段目标/critic采样修正、12回合均衡训练及冻结评价。预算提案32动态、4静态、4503更新（4500正式+3合成恢复）；待确认，新增执行0。规划文件不是算法能力或训练资格；单种子、小型未见四点评价均有范围限制，20ms不在本轮执行范围。

**后续执行增量：** 2026-09-28 一次重试结果：再次在首个预热回合发生原生访问违规，异常栈指向 `tools/dynamics/cartesian.py:234` 的 `mujoco.mj_forward`。已完成1500周期，异常位于随后500周期内，精确周期与底层根因未知。新动态启动1次，两轮累计6次；旧初始评价4/4复用，完整训练0、正式更新0，静态4和合成3未重做。训练进程已确认全部退出，跟踪已暂停，不自动第三次尝试。B.2受阻且未完成，未形成策略收益结论。 [重试结果](deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/assessment.json)、[异常栈](deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/fault.log)。

[当前研究计划](研究推进计划_当前版.md)、[训练合同v3](docs/stage_b/训练合同_v3.md)、[共用回合管理设计](docs/superpowers/specs/2026-09-23-residual-session-design.md)、[B.1实施计划](docs/superpowers/plans/2026-09-23-residual-interface.md)、[2026-09-23方案审查修订](deliverables/planning_review_20260923/审查与修订说明.md)。设计文件存在不代表其中所有功能已实现，完成状态查进度文件。

## 本文更新规则

1. 每次可交付增量完成，在本文件补充或更新对应能力：获得什么、证据与日期、怎么使用、限制。新增能力使用不重复编号；同能力新版标明证据日期和旧版链接。
2. 这里只维护交付和使用索引；任务优先级、当前阻塞只在进度文件维护。月报按当月整合，不复制所有详细技术说明。
3. 阶段目录保留必要的简短验收说明、源码/配置/数据与复现资料；不再为每个阶段另写一套月报素材。既有分散月报不删除、不搬移。
4. 滚动文件可以更新；已归档文件及其校验摘要不能随之改写。归档若需要绑定滚动文档，复制当时快照并记录日期，不把持续更新的原文件当不可变输入。
5. 更正结论时注明原因和受影响版本，保留原证据。检查新增链接有效后再汇报。

## 维护记录

### 2026-09-30｜四预热共同起点重建

- [阶段交付](deliverables/learning_chain/b2_actor_lr_origin_20260930/README.md)保存严格origin_v2状态、固定500批抽样、新源/分支身份及重建证据；旧origin和中间结果保留，不将数据产物冒作可执行检查点。
- 133最终纯协议通过，独立审查精度问题修正；原请求逐值一致，前向/优化/物理0。原283源和39前项产物/4149旧封存字节保持。
- 原三份滚动资料同步；A学习尚未复现，执行适配/新预算账本/资格及真实计算未完成，B.2未完成，旧余19/2000与跟踪PAUSED保持。

### 2026-09-30｜独立actor学习率实现与协议准备

- [本阶段](deliverables/learning_chain/b2_actor_lr_implementation_20260930/README.md)交付actor率、恢复前全部参数组检查、版本化准备与分布解析；使用上述配置/状态材料作审阅输入，准备类型主动拒绝执行，旧资格不可沿用。
- [101项最终协议](deliverables/learning_chain/b2_actor_lr_implementation_20260930/final_protocol_results.json)通过，模型前向/优化/物理0，独立审查无剩余重要问题；红/绿与原字节保存，4149旧封存文件保持。
- 原三份滚动资料同步。未重建真实训练状态、未复现A、未签发资格或启动计算；策略效果未验证，B.2未完成。旧余19/2000不执行，自动跟踪PAUSED，下一阶段另批。

### 2026-09-30｜原因复核与有界修复建议

- 交付[报告](deliverables/learning_chain/b2_repair_review_20260930/原因复核与修复建议.md)、[证据](deliverables/learning_chain/b2_repair_review_20260930/archive_review.json)及标准库复算脚本；只读核对13轨迹、2500更新记录、25项输入/产物摘要与4检查点文件，276源码/测试/冻结资料保持。
- 优先独立降低actor学习率，避免公共字段同时降低critic；补充随机策略分布及初始能力保持判据。早期筛选与后续交互修复验收分开解释，不证明候选已有效。
- 本次没有生产源码变更、训练测试、模型前向、物理或优化。旧余19/2000不执行，跟踪未恢复；历史草案和实验原位保留。

### 2026-09-29｜接续复核与单变量对照准备

- [方案及预算草案](deliverables/learning_chain/b2_actor_lr_design_20260929/README.md)说明actor单独3e-5、状态重建、A支复现、固定四点评价与结果判读；学习率共用与恢复参数覆盖风险已定位，尚未改代码。
- [复核证据](deliverables/learning_chain/b2_actor_lr_design_20260929/evidence_recheck.json)：4149旧包文件、10价值核对产物、13归档、4检查点一致；使用本项标准库脚本只做字节/JSON复核，不触发旧运行器。
- 该交付用于审阅后续方向与预算，不是执行资格或B.2验收；新增物理/推理/更新0，历史证据原位保留。当前状态及下一步仍只维护在进度文件。

- 2026-09-29入口修复：整合57项相关检查、真实监督/工作/恢复进程链、1项审查Minor修复和历史快照；不覆盖旧入口失败，不重启训练，新增物理/优化0。

- 2026-09-29 11:02入口负结果：新预算获批后唯一启动被Windows虚拟环境父进程检查拒绝，零物理复现原因；保留准备187检查及实际失败，训练未开始，跟踪暂停，不重试。

- 2026-09-29有限执行准备：加入187项检查、一次审查3项修复、911输入技术候选与缺授权拒绝证据；同步32次/4500批及累计68待批预算和原三份文档。新增实际执行0，历史包与旧预算关闭保持。

- 2026-09-28原生修复：新增EPA容量根因、同编译器故障对照、6311周期完整修复回合及复现入口；原证据不改写，新运行库正式资格待建立。

- 2026-09-27高级别规划：整合有限修正—训练—评价方案入口，校正边界拟合与唯一根因的关系；替代最新的单独边界诊断建议。仅文档管理更新，所有原实验与历史清单保留。

- 2026-09-24：按用户确认建立统一交付总览，归纳几何/动态/B2诊断、新版基线、三个接口交付及规划资料。仅整理入口，没有新增算法成果、训练或实验。
- 2026-09-24后续：新增B1-04独立学习环境、张量权限及未训练策略资格入口；B1-03导入阻塞明确为历史时点。没有SAC学习或整体训练准入。
- 2026-09-24采集增量：新增B1-05候选采集与整回合经验池入口，区分真实候选拒绝发布与合成数据正向测试。沿用同一滚动月报，无新分散月报或演示稿。

- 2026-09-27：新增B2-05离线诊断索引和有限接触开发预检提案；旧交付不改，新增物理回合/训练为0。

- 2026-09-27：新增B2-06有限接触诊断索引；位移作用门未全过，失败与局限保留，不计新增训练。

- 2026-09-27：新增B2-07 SEARCH四轴作用诊断，结果/限制/图表与复算入口整合，训练资格未扩展。

- 2026-09-27：新增B2-08动作链诊断，补齐B2反馈与限制器的积分分解及完整SEARCH窗口图；提出一个两回合后续方案，未执行。

- 2026-09-27：新增B2-09运动状态±X对照，整合局部作用、结局、失败账与后续停止规则；训练资格未扩展。

- 2026-09-27：整合B2-10固定预热探索候选预检，保留全部启动、未执行及保护/停止事实；训练资格未扩大。

- 2026-09-27：整合B2-11准备资格与正式执行资格的边界，新增四点配置、采样/预算测试及后续适配范围。

- 2026-09-28：保留有限周期原生崩溃证据，登记用户批准的一次重试；已完成评价复用，失败不抹除。

- 2026-09-28：授权重试再次访问违规，封存原生异常栈和真实累计成本；没有新增学习效果交付。

2026-09-28停止后分析增量：停止后离线核对18份轨迹发现：四个预热成功2/4，更新后六次随机采集0/6（五任务失败、一接触保护），不同中间策略不能当最终成功率。三次到达目标深度却以0.96～1.29度停住，超过0.5度成功门；首个更新后回合roll请求96.8%的有权限周期贴近动作边界。保护后后续周期动作均归零，恢复后约0.9366秒触发穿透。已有明确不利行为证据，但最终效果与唯一学习成因仍未验证。分析新增物理/更新0。 48000条critic边界抽样已执行，采样与尾段目标修正未自动转化为控制收益；方向性修改尚未实施。

2026-09-28：用户接受阶段/进展相关残差权限分配的论文主张为暂定目标，允许按真实结果修订。已整理指标优先级与阶段图表口径，并补齐当前中止训练的三张PNG/SVG图；输入/输出摘要绑定、图像查看通过。新增物理、策略推理和优化均0；不改变B.2未完成状态或授予新实验预算。

### 2026-09-29｜授权重开与只读监看交付

新包不改历史文件、合同或固定学习方案。使用入口为上表本机进度页；关闭页面不控制训练。重开从原初态开始，原144批只作历史记录。旧包8动态、旧剩24/4356关闭及新累计76明确分账；仍无最终策略收益结论。

### 2026-09-29 16:27｜本轮初始评价完成

[初始阶段证据](deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/initial_milestone.json)：四点4/4成功，全部有效并停稳，完整学习状态保持，用时1312.12秒。进入均衡预热采样，更新0；该结果不能作为学习收益或独立评价结论。

### 2026-09-29 16:47｜首组更新与检查点

[阶段证据](deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/first_update_milestone.json)：500批完成、完整检查点文件摘要核对通过。一次JSON替换已恢复，没有重复学习；恢复实际重放与固定最终评价仍未完成，不能称学习有效。

### 2026-09-29｜受控停止交付

**当前已停止（2026-09-29 17:12:32）：** 第9训练回合完整归档后，累计第3次合格力保护失败触发预登记受控停止，退出码20。13个物理回合全部离线重审有效停稳；训练9回合为1成功/5普通失败/3力保护，发布47,474条经验，完成2500批更新。最新完整检查点为第8训练回合/2500批，第9回合后未再优化。新启动13/32、累计57/76，余19次/2000批保留不执行，跟踪PAUSED，不自动重试。本轮没有原生崩溃、入口拒绝或写入失败；10次文件重试均已恢复。最终开发/恢复/独立评价未执行，无固定最终策略收益证据，B.2未完成。 [停止说明与三图](deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/停止结果说明.md)、[机器复核](deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/stop_assessment.json)。

### 2026-09-30｜actor率对照执行协议准备

**actor率对照执行适配与协议准备（2026-09-30）：** [执行适配](deliverables/learning_chain/b2_actor_lr_execution_20260930/README.md)已接通版本化A/B、独立持久账本、完整检查点、新进程冻结评价及真实验证前置代码；216项最终纯协议全过、实际前向/优化/物理0。审查发现的阶段/授权/恢复/监督/诊断门缺口已补反例并修正。原286源、前项产物、4149封存与929旧源码原字节保持。协议准备已验收，真实数值验证与A500学习复现尚未运行，效果未验证，B.2未完成；旧余19/2000不结转、跟踪PAUSED。新计算申请见[清单](deliverables/learning_chain/b2_actor_lr_execution_20260930/authorization_request.json)，需单独批准。

使用方式、门禁与新预算见上述README。该能力扩展原B2学习/恢复工程入口，不新增研究收益或B.2验收；自动跟踪继续暂停。

### 2026-10-01｜有限actor率对照实际执行

**actor率有限对照已获批并启动（2026-10-01）：** 用户明确批准[封存候选](deliverables/learning_chain/b2_actor_lr_execution_20260930/candidate_pin.json)及新上限16合成事务/128测试状态前向、768诊断状态、1000正式批/8动态；[授权](deliverables/learning_chain/b2_actor_lr_execution_20260930/authorization.json)单独保存。真实数值验证已通过，实际消耗4合成事务/8测试状态，首次actor差分范数比约0.09999992，critic/温度一致、无权限屏蔽/注入回滚/保存恢复与跨分支拒绝通过。[启动快照](deliverables/learning_chain/b2_actor_lr_execution_20260930/startup_assessment.json)截至2026-10-01T12:22:57+08:00，A复现进行中；实时进展见[运行账本](deliverables/learning_chain/b2_actor_lr_execution_20260930/run/ledger.json)。A必须精确复现才B，评价任何保护完整停稳归档后停止整轮，运行/写盘/输入故障不重试；尚无新策略收益或B.2验收，旧余19/2000不执行，自动跟踪PAUSED。


2026-10-01｜100ms预热有限学习验证收口：结果和同一10月月报已整合，旧资料与全部未提交成果保留。

### 保存修复后的零起点效果重启（2026-10-01）

**100ms预热重启验证已启动（2026-10-01）：** 用户要求继续，修复保存接口后另建执行版本从共同零更新重启；先做真实完整状态落盘与独立进程零计算重建，再执行initial/C学习/固定/恢复/A对照。新增上限24动态/5000批；此前72动态和失败500批保留，累计上限96动态/本方法5500批。原参数/保护/成功门不改；任一保护或故障停止、不重试，旧余量关闭，自动跟踪PAUSED，B.2未完成。[方案](deliverables/learning_chain/b2_temporal_learning_restart_20261001/验证方案.md)、[账本](deliverables/learning_chain/b2_temporal_learning_restart_20261001/run/ledger.json)。

使用入口仅执行一次，先存取门、后实际训练；原包不重跑，成本保留。

2026-10-01重启终点：本方法尚未解决已观察到的学习后失效问题；[实际结果](deliverables/learning_chain/b2_temporal_learning_restart_20261001/result_analysis/结果说明.md)。有效状态见机器检查点清单，余量关闭。

2026-10-01补充使用与限制：保存故障已经由真实存取门和四个学习后检查点落盘/离线完整恢复核验；本次停止是实际力保护，非程序保存故障。8/8完整回合均有效停稳，起点4/4成功；在线0/4（3普通失败、1力保护）。保护回合未发布新经验，未获额外更新信用；最新C2000包含前7份审核学习档案和37,270条经验，触发原轨迹单独保留。 本轮在2000批随机在线负Y回合的力保护处结束，不是2500批确定性四点评价失败。C2500、固定最终四点、独立恢复动态及A对照均未执行；不能据此断言任意100ms方案无效、A一定更好、唯一原因已确定或critic高估已消除。 [C2000完整状态索引](deliverables/learning_chain/b2_temporal_learning_restart_20261001/run/latest_checkpoint_C.json)。独占入口不再执行。

<!-- stage-permission-delivery-source -->
### 2026-10-03 10:46｜阶段权限配对交付

[结果与图](deliverables/learning_chain/b2_stage_permission_20261002/result_analysis/结果说明.md)、[机器审核](deliverables/learning_chain/b2_stage_permission_20261002/result_analysis/assessment.json)；新启动12/30动态、审核完成12回合，累计102/120；正式更新尝试0、完成0/5000批（F0/S0）。运行故障阻止完成配对效果判断；保留稳定编号与历史版本，未新增B.2/C完整验收。
<!-- /stage-permission-delivery-source -->

<!-- stage-resume-delivery-source -->
### 2026-10-03 12:43｜阶段权限配对交付

[结果与图](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/结果说明.md)、[机器审核](deliverables/learning_chain/b2_stage_permission_resume_20261003/result_analysis/assessment.json)；新启动7/18动态、审核完成7个新回合，另引用12个历史回合，累计109/120；正式更新尝试3500、完成3500/5000批（F2000/S1500）。保护触发后受控停止，完整配对效果尚不能判断；保留稳定编号与历史版本，未新增B.2/C完整验收。
<!-- /stage-resume-delivery-source -->


### 2026-10-03 19:37｜1.20 mm任务实现与基线预检

新增模型及实例成功参数、九针配合裁决、禁止覆盖的预检入口，旧默认XML/50 μm保持。使用与证据见[结果](deliverables/task_variants/clearance120_20261003/结果说明.md)、[诊断](deliverables/task_variants/clearance120_20261003/诊断与下一步.md)。44检查、8动态、训练0；新任务未获训练准入，B.2/C未验收。

2026-10-04维护：新增TV-02及最新结果导航，历史稳定编号和原路径保留；新增成果是共同基线局部修复及失败诊断，未新增SAC性能验收。

2026-10-04 00:48维护：新增TV-03和SEARCH载荷修复失败证据；历史编号、原轨迹和封存保留。

2026-10-04 17:39维护：新增TV-04，保留TV-01～03及历史档案。

2026-10-04 18:21维护：新增TV-05，保留TV-01～04及历史档案。

2026-10-04 18:44维护：新增TV-06，保留TV-01～05及历史档案。

2026-10-04 19:14维护：新增TV-07，保留TV-01～06及历史档案。

2026-10-04 19:36维护：新增TV-08，保留TV-01～07及历史档案。

2026-10-04 20:15维护：新增TV-09，保留TV-01～08及历史档案。
