# GRU Residual SAC Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans when implementation is requested. Track tasks with checkboxes. This delivery is a plan; every implementation task below is pending.

**Goal:** 在现有五维残差SAC中加入因果历史记忆，检验能否改善yaw与XY配合对准、完整插入成功率及完成时间。

**Architecture:** 保留共同环境、导纳、观测和动作权限，新增独立recurrent模块。actor、Q1、Q2各自使用单层GRU，两个target critic分别维护自己的参数及历史编码；新增连续序列回放、全周期记忆更新和来源审核。普通MLP-SAC通过相同新协议适配，作为训练对照。

**Tech Stack:** 当前项目Python、PyTorch原生`nn.GRU`、NumPy、MuJoCo及pytest；沿用现有依赖版本，首版CPU单线程，不迁移RL框架。

**Spec:** [给用户的实施计划](../../../deliverables/planning/gru_sac_20261104/给用户的实施计划.md)。用户2026-11-04本次授权制定两版计划和文献研究，不是实施或训练指令。

## Global Constraints

- 工作树为`D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation`。先读AGENTS及五份滚动记录，保留未提交成果、旧合同、旧批次、历史标签与冻结权重。
- 共同新协议绑定`dsub9_clearance120_layered_nano100_v6`、几何容差`1e-7 m`、`native_force_recovery_v1`、`five_axis_N2_30s_force_recovery_permission_v1`。100 nm是逐针几何容差，不是将整个插接体XY误差限制到100 nm。
- 绝对任务预算30 s，含搜索/卸载/回撤/重试；最终停止审核最多另2 s。被动yaw ON，次数不硬终止，加载转角为预警。恢复资格不清除累计事件和峰值。
- 保留5 N原生停止推进阈值；仅符合现协议的孤立5～6 N、连续超5 N不超过20 ms可恢复。等待卸载、实际回撤至少250 μm、低载稳定尾和其他硬保护保持；6 N仅为未实物标定的仿真恢复上限。普通恢复仍为实际200 μm。
- 保持140维观测、五维联合残差`[vx, vy, ωx, ωy, ωz]`，不增加独立Z动作。实际G1动作尺度为`[5e-4,5e-4,5e-4,5e-4,5e-3]`，前两维单位m/s、后三维rad/s；不可误用旧`five_axis_contract.SCALE`。此处G1为已有动作尺度名称，与下文动态准入阶段G1分别登记。
- 控制/网络周期2 ms，物理子步0.2 ms。行为epsilon保持25周期即50 ms；均值、方差、hidden每控制周期更新。目标SAC采样仍独立，不把行为保持噪声搬到target。
- 第一主实验速度建议900 μm/s；450只作后续稳健性检查。两模型均保持同速、同奖励/裁判/权限/探索/初始化分布。不新增固定导纳零残差实验组，遵守用户此前删除该组的要求。
- 不向actor加入真实孔位、目标yaw、逐针余量或特权reward历史。输入已有上一残差和上一受限执行命令，先核对来源，不重复拼接成145维。
- 最新恢复入口仍是零更新、禁止回放发布的诊断协议。只有新共同学习合同及动态、来源、停止审核准入通过后才可学习；禁止直接翻转旧入口的`training_admitted`标记。
- 当前仅计划交付：新增初始化/物理步/推理/更新均0，累计455；完整B.2与C未验收。后续预算须随执行阶段登记，不能因有本计划就自动启动。

## Review Focus

- 同一cycle多次读取导致hidden重复推进；真实回合重置未清hidden；恢复阶段误清hidden或漏观测。
- 随机单步回放、跨回合拼接、padding/burn-in参与loss、target错用t而不是t+1。
- 在线与target共用hidden、当前候选动作污染过去行为历史、更新权重后继续使用旧语义hidden。
- inactive动作或熵项未归零；actor/alpha被inactive或padding样本更新；NaN回滚遗漏GRU或优化器状态。
- 旧F4000或旧回放被当成新协议训练基线；无效仿真、恢复未完成或30 s失败被误作可bootstrap截断。

## 1 当前事实与设计依据

当前`five_axis_sac.py`实例化前馈SB3 `SACPolicy`，网络为两层256；`five_axis_replay.py`虽按完整回合保存，仍继承`audited_replay.py`的单步随机采样。现观测包含四帧力/力矩，跨度6 ms，还有上一残差、受限命令及控制器状态，不能称为无历史策略。

`five_axis_training.py`和`five_axis_collection.py`在inactive阶段不调用策略。最新诊断路径实际使用`noise50_trial.FrozenHeldPolicy`和`HeldSourceReplay`；其inactive输入为None，也不能直接包装一个GRU后继续沿用。当前176项纯检查不等于新恢复动力学或训练已经准入。

最新零更新结果只能提示联合配合问题，不能证明MLP能力到顶。旧F4000源自不同几何/探索/预算语义；首要比较是同一新协议下新初始化的MLP和GRU，旧F4000仅作额外冻结参考，不继承其Adam、回放或4000计数。

文献依据及固定源码链接见[论文与开源实现借鉴](../../../deliverables/planning/gru_sac_20261104/论文与开源实现借鉴.md)。以下数值是工程起点，不是论文已证明的最优值。

## 2 首版网络与序列语义

### 2.1 网络和预算起点

| 项目 | 首版选择 | 理由与后续边界 |
|---|---|---|
| 输入 | 保留当前归一化140维，每周期一帧 | 已含前残差、实际受限命令；不用reward作输入 |
| 网络 | 每支`Linear(140,64)+ReLU → GRU(64,64,1) → head` | 单向，dropout=0；actor和两Q独立，共3个online GRU，另2个target GRU |
| head | actor接`Linear(64,256)+ReLU`后5维mu/log_std；Q接`[hidden,action]`经256层到标量 | 联合输出五维；保留原tanh Gaussian与数值稳定修正 |
| 记忆更新 | 每2 ms；同回合跨搜索/卸载/回撤延续 | 新episode才清零；回合内冻结行为网络权重 |
| burn-in | 256周期，即512 ms，不计算loss | 当前参数重算hidden后detach，不是准确全历史的保证 |
| 学习段 | 128周期，即256 ms | 截断反向传播；上线记忆仍延续整回合 |
| batch | 2段，最多256个学习转移；额外1帧next observation | 与原MLP的256转移量级一致，实际有效loss行另计 |
| 优化初值 | lr均3e-4、alpha初值0.01、目标熵−5、tau=0.005、gamma(dt)=exp(−dt/10) | 从现`learning_config()`取值并在新版本冻结；若采用另一个当前批准率，两支共同更新登记 |
| 梯度 | 记录范数；有限检查；各optimizer clip global norm=10 | 两训练对照同样应用并登记；不能静默只给GRU额外稳定化 |
| 回放容量 | 首版沿用116000个转移，整回合淘汰 | 单份obs/动作元数据存储，不预分配capacity×15000 |

不共享actor/critic参数可避免两种loss竞争同一记忆表示。独立Q1/Q2方便检查Q相关性；若训练开销过高，再把“共享critic GRU＋双head”作为有版本的替代实验。部署只运行actor，不运行三套网络。

序列总输入上限为385帧（256+128+1），不是把30 s的15000步全程反传。burn-in起点若不在回合首，零初始化只是近似。准入时固定包含搜索、恢复的片段，对比当前参数从回合首无梯度重建的hidden及输出；报告误差和成本。若差异影响动作/结论，应延长burn-in或改完整prefix重建，并共同登记训练成本，不能隐瞒偏差。

### 2.2 数据约定与更新

`SequenceReplayBatch`保存`observations[B,T+1,140]`、`observation_valid_mask[B,T+1,1]`、`actions[B,T,5]`、`rewards/dt/terminated/truncated/active/next_active[B,T,1]`以及`valid_mask[B,T,1]`、`learn_mask[B,T,1]`、`episode_id`、起始cycle和真实prefix长度。T包含burn-in与学习转移；observation mask用于递推且包含真实额外next帧，transition mask用于loss，两者不能共用。真实终局next帧有效，其后padding无效；任何有效转移的前后两帧都必须有效。动作必须沿用审核后的experience_action定义；raw policy action、映射后残差和实体受限命令另存证据，不能混为一物。

每个网络分别执行`h_t = GRU(o_t,h_{t-1})`。`Q_i(h_t,a_t)`的当前候选动作只进Q head；下一帧`o_(t+1)`中的前动作/命令来自实际记录，不能替换为当前新采样动作。target critic用target参数独立编码；不能从online Q或actor拷贝hidden。

目标计算沿用SAC：`y_t = r_t + gamma(dt)*(1-terminated_t)*(min Q_target(h_(t+1), a') - alpha*I(next_active)*logπ(a'|h_(t+1)))`。next inactive时`a'=zeros(5)`且熵项0。Q历史来自记录的行为轨迹；当前t和下一t+1的索引必须用哨兵序列测试。

先对所有真实连续帧传播历史，再应用loss mask：critic使用`valid & learn`，actor/alpha使用`valid & learn & active`。不能先筛掉inactive帧再跑GRU；actor loss时冻结critic参数，仍保留Q对候选动作的梯度。先完成critic.step，再用更新后的critic参数重新编码用于actor loss的历史，不能复用旧critic计算图或旧hidden；actor也为自己的反传单独构图。全inactive批次不调用actor/alpha optimizer.step，避免Adam动量改变参数。target soft update计数与成功的critic update绑定。

padding不改变hidden，不能伪造零帧历史；短prefix用长度/mask明确跳过padding。仅真实回合起点清零。burn-in各支在当前参数下无梯度前推，学习段前detach；不保存旧hidden作为训练真值。首版不加优先回放，不按成功结果偷偷超采样；明确起点抽样分布与terminal覆盖。

保留当前完成停止审核后才`done`的时钟语义：30 s截止产生任务失败决定并关闭动作，不标成可bootstrap的`truncated`；停止尾继续记录真实inactive转移。最终最多2 s审核尾纳入共同训练序列，critic可学习这些真实转移，actor/alpha无loss；只在最终审核完成的最后一行`terminated=True`并由现reward.finalize给唯一终局奖励，随后没有训练转移。不能在30 s先给一次terminal、审核后再给一次。整回合审核合格后才发布；无效仿真/外部中断隔离，不将未验证结果拼入训练。奖励先沿用新协议共同奖励语义，不同时新增yaw或逐针特权塑形。

### 2.3 在线状态与复现

provider接口为`begin_episode(episode_id, checkpoint_id)`、`observe_or_select_cycle(episode_id, cycle_id, observation, active, context) -> decision`、`commit_action(cycle_id, experience_action, execution_evidence)`、`end_episode(outcome)`。相同cycle调用返回缓存，不再次前推或抽噪声；跳号/倒序报错。放在provider中，不放在可能refresh多次的observation.capture里。

在UNLOAD/RETRACT等inactive阶段继续编码真实140维观测，输出五零且不消费无权限动作噪声。phase变化按现规则刷新epsilon缓存，但不清GRU。最终STOPPING尾同样编码、计数并纳入上节训练序列，动作始终无权限。actor每回合使用固定权重，仅回合边界同步learner，防止hidden语义漂移。

source audit从回合初始零hidden按完整cycle顺序独立重放，包括inactive；核对动作、权限、保持噪声、执行映射、native恢复证据及停止审核。分别计数任务编码、动作head、来源编码、优化和burn-in前向，不能把observe-only伪装成零网络计算。

checkpoint仅承诺完整episode及完整update边界恢复：保存全部online/target网络、optimizer、alpha、随机数、回放采样器、合同hash和序列配置。旧版本明确拒绝；不承诺从任意物理中间态恢复。trainer的更新事务在sample_sequences之前保存replay RNG及逻辑计数；异常回滚这些状态并锁存failed，只能从健康完整checkpoint重启。失败尝试、墙钟及已消耗计算另记不可抹除；不能只回滚updater内部随机数后声称下一次抽样可复现。

## 3 文件与任务划分

新模块放在`tools/learning/`，审核放在`tools/validation/`；尽量组合原实现，避免改旧诊断入口语义。下列文件名为待创建目标，不表示已经存在。每任务先写有意义的失败测试、确认预期失败，再实现及运行相关回归；每任务通过后独立复核。不要自动提交已有用户修改。

### Task 1 冻结共同学习协议与数据资格

**Files:** 新建`tools/learning/recovery_learning_contract.py`、`tools/learning/recovery_learning.py`、`tools/validation/recovery_learning_audit.py`、`docs/stage_b/训练合同_v4_GRU共同协议.md`、`tests/test_recovery_learning_contract.py`、`tests/test_recovery_learning_audit.py`。复用`force_recovery_trial.py`、`consistent_sac.py`、当前reward与审核实现；保留旧v3及零更新入口。必要时仅抽取`consistent_sac_audit.py`的共享物理审核内核，保持其旧顶层路由和严格校验。

**Interfaces:** `learning_contract(search_speed_um_s, seed) -> dict`；`validate_learning_contract(config) -> dict`；共同session/collector工厂由MLP和GRU共用。MLP配置与更新器的版本校验通过显式新adapter适配，禁止猴子补丁绕过原validator。

新`RecoveryLearningArchiveV1`将`physical_protocol`与`learning_run`分开：前者是当前物理/观测/保护/裁判字段的冻结投影，后者记录算法、实际更新、行为来源、回放资格、checkpoint和seed。新`audit_recovery_learning_archive(...)`同时校验两部分，并复用原生恢复、参考、奖励和停止的物理审核；MLP/GRU各接自己的来源审核。现`force_recovery_trial`及`consistent_sac_audit`的零更新路由严格匹配旧合同且恢复分支固定`learning_version=None`，应继续拒绝学习档案。不能把实际训练档案伪装成`optimizer_updates=0`以通过旧入口。

物理投影须逐字段枚举、固定版本/hash并拒绝缺失/未知字段。当前`consistent_sac_audit.audit_archive`约180–353、364–369行可抽取物理内核；其中`time_budget_protocol`和动作日志`contract_version`比较改为接收明确的冻结物理协议及允许日志版本，不能放松为任意值。`verify_action_source`留在各自外层；参考/初态/恢复/reward/success hold/stop interval函数复用。旧外层回归与新外层集成分别验证。

- [ ] 对错误几何版本、旧SCALE、旧观测语义、恢复未验收、终局重复奖励、invalid/truncated混淆写失败测试。
- [ ] 合成档案验证envelope及物理层，错版本/假零更新/物理合同错配被拒绝，旧诊断入口仍拒绝学习档案；完整MLP/GRU来源集成验收留到Task 4，缺少来源审核时总结果必须未准入。
- [ ] 对照`config_450.json`/`config_900.json`与实际代码列出完整保护、奖励、终止、50 ms行为噪声、回放发布和失败类型；明确旧20 s/4维/75 μm合同常量不是本协议值。
- [ ] 实现共同版本及adapter；完整终局和来源审核通过后才发布整个episode，正常有效失败可以学习，invalid及未完成审核不可学习。
- [ ] 运行该测试文件及受影响既有合同/恢复/奖励审核测试，生成纯检查报告。此时仍不能凭纯检查宣称动态准入。

### Task 2 连续回放与序列边界

**Files:** 新建`tools/learning/recurrent_contract.py`、`tools/learning/recurrent_replay.py`、`tests/test_recurrent_replay.py`；参考`five_axis_replay.py`、`audited_replay.py`。

**Interfaces:** `SequenceReplayBatch`采用第2.2节字段；`sample_sequences(batch_size, burn_in, learn_steps, rng) -> SequenceReplayBatch`；完整回合发布/淘汰继续由共同审计门控制。

- [ ] 测试不能跨episode，obs/action/next_obs连续对齐，T+1观察mask与T转移mask各自正确，短prefix和终局padding不参与loss，terminal转移可采样，未准入episode被拒绝。
- [ ] 实现连续起点抽样，保存真实prefix和额外next帧；暂不保存网络hidden；登记实际有效学习行、padding和burn-in计算量。
- [ ] 用人工哨兵episode精确核验每一索引及mask；同seed抽样可复现，整回合淘汰不留下孤立片段。

### Task 3 循环SAC数值核心

**Files:** 新建`tools/learning/recurrent_sac.py`、`tests/test_recurrent_sac.py`；参考`five_axis_sac.py`、`tensor_masks.py`、`learning_rates.py`。不要把原4维canonical helper直接用于5维序列。

**Interfaces:** `RecurrentActor.forward_sequence(obs, h0, valid_mask)`、`step(obs,h)`；`RecurrentCritic.encode_sequence(...)`、`q(encoded,actions)`；`RecurrentUpdater.update(batch) -> audit_metrics`。显式区分online/target hidden，不创建actor target。

- [ ] 用固定权重/输入验证逐步前向等于批量序列前向，未来帧变化不能影响过去输出，Q候选动作不改变历史编码，t/t+1目标与手算一致。
- [ ] 实现第2节架构、tanh log_prob修正、双Q、alpha、时间折扣、Polyak及梯度隔离；保持原原子更新失败回滚语义。
- [ ] 测试burn-in无梯度、padding不影响loss、inactive熵/动作归零、全inactive actor/alpha及其Adam状态不变；critic仍训练有效inactive转移；actor阶段使用critic更新后的独立重算图。
- [ ] 注入NaN/Inf检查全部网络、target、optimizer、alpha、RNG和计数回滚；保存实际loss/梯度/alpha/动作饱和率，避免以有限loss代替控制有效。

### Task 4 全周期provider与独立来源审核

**Files:** 新建`tools/learning/recurrent_training.py`、`tools/learning/recurrent_collection.py`、`tools/validation/recurrent_sac_audit.py`、`tests/test_recurrent_lifecycle.py`、`tests/test_recurrent_source_audit.py`；参考`five_axis_session.py`、`five_axis_collection.py`、`noise50_trial.py`、`persistent_exploration.py`及`consistent_sac_audit.py`。

**Interfaces:** 第2.3节四个provider方法；`audit_recurrent_source(archive, checkpoint, contract) -> audit_result`；相同callback入口可接MLP，以共享物理环境及事件生命周期。

- [ ] 模拟SEARCH→UNLOAD→RETRACT→SEARCH与episode reset，测试hidden延续/清零、同cycle刷新幂等、跳号拒绝、无权限零动作。
- [ ] 在正常采集和恢复阶段每cycle送真实obs；固定行为权重到episode结束。明确episode、cycle、obs编码与epsilon draw各自计数。
- [ ] 独立重放全周期，篡改inactive观测/某次reset/phase噪声缓存/执行映射时审核必须失败；继续执行已有原生超力、参考一致性、几何与停止审核。
- [ ] 新MLP和GRU各一个合成整档案通过新学习外层完整审核；旧诊断外层配合同一物理内核仍能复核旧合成档案，两类envelope互相拒绝；补齐Task 1延后的来源集成测试。
- [ ] 运行纯生命周期与合成档案审核，不创建真实物理环境。测试输出标明synthetic，不能算真实恢复成功。

### Task 5 保存恢复与纯检查收口

**Files:** 新建`tools/learning/recurrent_checkpoint.py`、`tests/test_recurrent_checkpoint.py`；集成前述trainer。使用当前Python环境`tmp/learning_cpu_20260924/Scripts/python.exe`。

- [ ] 检查完整边界保存后下一序列、动作、噪声、更新结果可复现；旧MLP/旧协议checkpoint硬拒绝；恢复不自动发布待审episode。trainer级故障注入须覆盖采样之后失败、replay RNG回滚、失败锁存与成本保留。
- [ ] 运行`python -m pytest -q tests/test_recovery_learning_contract.py tests/test_recovery_learning_audit.py tests/test_recurrent_replay.py tests/test_recurrent_sac.py tests/test_recurrent_lifecycle.py tests/test_recurrent_source_audit.py tests/test_recurrent_checkpoint.py`，再运行受影响既有纯回归。
- [ ] 做纯tensor推理延迟、序列更新吞吐、内存测量与完整prefix对照，登记测量硬件/线程/预热。控制2 ms是仿真语义；是否达到实时时限须单列实测，不能默认保证。
- [ ] 独立复核本计划Review Focus全部有测试覆盖；记录通过项与未解决问题。通过后只获得纯实现资格。

### Task 6 新协议动态准入与小试

**Files:** 新建`tools/validation/run_recurrent_sac_pilot.py`及对应manifest校验测试；阶段证据存`deliverables/learning_chain/recurrent_sac_<日期>/`。启动器默认`--dry-run`，实际执行需完整已登记manifest，保持现有STOP/退出/成本机制。

- [ ] G1先登记最多8次共同动态准入尝试：覆盖已有正负yaw、正常无超力、确实触发可恢复超力、已有不可恢复分支。少量物理配合合成边界检查，不为“凑覆盖”反复强碰撞。未实际触发的恢复分支必须列为动态未覆盖。
- [ ] 审核真实卸载、实际250 μm回撤、100 ms低载尾、重新搜索、30 s截止及最终2 s审核；原生峰值、恢复中再超力、其他硬保护和无效原因保留。安全问题先修再重新登记，不能直接扩大训练。
- [ ] 若8次预算结束仍没有合格的实际卸载—回撤—停稳—重搜证据，动态准入未完成，结束该批并报告，不自动补跑或进入G2。
- [ ] G2链路小试：MLP/GRU各1个训练种子；每支最多8个尝试、120000有效控制转移、256次更新，以先达到者为止，单次更新最多256有效loss行；不足两份完整准入episode不更新。上限只是检查链路，不用于宣称算法优劣。
- [ ] 小试分别报告达到的有效交互/优化量、合格episode、任务与审计计算、墙钟及残差执行效果。数值、来源、停止或恢复审核失败则暂停本阶段；不能用追加种子稀释异常。

### Task 7 配对开发与独立评价

**Files:** 扩展pilot runner的冻结manifest及结果汇总；新建`tools/validation/recurrent_sac_evaluation.py`、`tests/test_recurrent_metrics.py`。复用现逐针有限圆柱裁判，不重写另一套成功规则。

- [ ] G3仅在G1/G2通过后登记。所有G3分支重新初始化，G2回放/权重/更新不继承，开发成本单列。建议首档每算法每训练种子120000有效交互转移、至多1000次更新、最多24个尝试，先用3个独立训练种子；每个回合边界更新，更新预算随有效数据按比例释放，不在首批少量数据上一次做完1000次。记录有效loss行差异，超过一batch时补齐计算比较或标明未匹配。
- [ ] 有效交互预算在完整episode边界可能超出，记录实际超出量；达到尝试上限却不足交互预算的分支属于预算未完成，不能与完成分支直接声称公平胜负。冻结模型前不按测试结果挑最好seed。
- [ ] 注册train/dev/test三类manifest及独立RNG流：模型初始化、初态、行为epsilon、回放、评价分别设seed；两方法使用配对初态和评价采样seed。历史七工况及已看过的yaw试验始终为开发资料。
- [ ] 开发集建议先6个联合点：yaw正负各配XY两个对角方向和一个偏轴方向；范围在现模型资格内，数值在manifest冻结后才能跑。roll/pitch先固定共同值，后做范围内扰动；禁止宣称只测两个yaw就覆盖联合配合。
- [ ] 仅根据开发集决定是否增加消融或教师方案；这些选择和待比较方法、checkpoint选择规则冻结后，才打开独立评价。建议预先生成12个未用于训练/选择的连续联合偏差点，含正负yaw、四象限XY及边界附近点；每个模型逐点同初态。主报告固定mean action，50 ms随机策略评价另列配对附组。具体幅度和随机分布先写入合同，不能查看结果后改样本。
- [ ] 按第4节指标生成每seed、每工况及配对结果，给成功率区间与时间差分布并注明统计假设；3个训练种子共用12点不能当36个独立训练重复，保留训练种子及工况两层配对。小样本稳定性结论有限。共同成功点耗时单列，完整自主回合与所有尝试双分母并列。
- [ ] 若开发集有稳定增益，追加训练/评价一致的短历史堆叠MLP或受限历史GRU消融，并核对参数量/调参预算；此步骤须在上条独立测试之前完成选择。测试时清hidden、打乱历史仅作敏感性诊断，不能单独证明记忆必要。若已查看最终测试再修改方法，该测试转为开发资料，另登记新独立测试。

按上述上限，G1最多8尝试、G2两支合计16、G3六支合计144；首档只在预算终点做一次6点开发评价（36次），一次12点最终评价为72次，合计上限276次初始化尝试。消融、随机附组、F4000额外参考、450检查和教师默认关闭，另登记后才计入计划。这是分阶段的成本上限，不是一次性运行清单；每阶段完成后报告是否值得继续。有效转移包括可学习的inactive恢复/停止尾，同时另报30 s内的任务交互量，防止恢复/停止时间差掩盖资源差异。

## 4 结果判定与教师分支

主顺序为：通过共同安全和审核门，再比较完整成功率，再比较截顶完成时间`T*=成功时刻（含100 ms保持）或失败30 s`。另报首次目标深度时刻、成功子集时间和共同成功工况的配对时间；最终2 s审核成本另报，不混作插入耗时。无超力成功、验证恢复后成功、不可恢复保护失败、有效任务失败、外部中止和无效仿真分别统计；不让早保护终止成为“速度优势”。

联合几何评价保存触发、最深、任务判定、审核末态四种时刻：九针入口/主孔有限圆柱余量和Z交叠、共同配合时长、最差针编号、推进深度；同时记录body XY/yaw/roll/pitch、搜索实际覆盖、请求→受限→实际运动。无Z交叠不算已通过、轴线近似不替代有限针裁判、XY与yaw分别变小不等于联合可插入。

原生安全统计包括峰力、峰扭矩、峰穿透、超5 N持续时间、实际速度瞬态、恢复次数/耗时及累计历史。所有尝试计入成本，外部STOP不伪装自主失败也不删除；缺失配对不用于算法胜负。记录物理子步、任务/审核推理、优化次数、有效loss转移、burn-in前向和墙钟，不能仅以“同1000更新”宣称成本一致。

继续GRU的证据应是跨训练种子、不同联合初态的成功/时间改善，并能排除新增协议、动作幅度和预算差异。小试无成功但链路正确，只说明当前预算未证实收益，不立即判定GRU无效。

教师分支在预定开发预算后再决定：先检查动作是否有效、历史是否包含可辨识信息、reward/终局是否可信及正向样本是否长期稀缺。只有主要瓶颈落在探索/样本稀缺时，才设计“同GRU无教师/有教师”对照；若是限幅/接触模型/信息歧义，先修对应问题。教师可用特权几何产生示范，但须登记来源、成本和训练用途，部署策略不得访问这些真值；冻结测试不能用于挑示范。当前不实施教师或reward重塑。

## 5 交付与阶段结束

- [ ] 每阶段提交代码差异、纯检查/动态证据、来源与checkpoint摘要、全部尝试成本及失败分析，按AGENTS同步五份滚动记录与前后快照。
- [ ] 将“计划完成、代码纯检查、动态准入、训练完成、独立评价”分别记录；禁止勾选尚未执行任务。
- [ ] 完整B.2达到验收条件、准备进入C之前，先主动汇总阶段成果；本计划本身不构成B.2验收。

本轮计划交付只读取现有代码与研究资料；GRU实现、上述测试、动态准入、训练及评价均待后续阶段执行。
