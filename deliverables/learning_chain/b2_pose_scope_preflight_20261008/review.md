# B2-SCOPE-02｜一次独立审查与作者修复

2026-10-08。审查者 `/root/b2_scope_final_review`，独立上下文，模型 gpt-6-astra/high。按照 executing-plans/requesting-code-review 做一次只读审查、作者一次反例修复，不作第二次审查。

工作目录及分支保持原样。BASE/HEAD 均为 `d2e7e4fa4ed0631d9dd1b7b98a121c1e46ea6406`；用户要求保留未提交修改，故审查范围以本目录的新 Python 文件和原方案明确界定，不冒称 Git 提交差分为空就无改动。

## 独立审查原始结论

审查原判：**not ready for physical execution or final implementation acceptance**。审查者运行25项已有新测试全部通过、未导入引擎或学习模块，但纯反例指出以下缺项。这是修复前结论，不能改写为一次审查直接通过。

| 项 | 原级别 | 原发现/位置 | 实际影响 |
|---|---|---|---|
| I1 | Important | run_preflight.py原11–18/46–58/177；prepare_binding.py原18/34–37：复制目录仍验证旧绝对路径，却使用新OUT/claims | 同一grant可能重新领取，副本代码没有受实际来源绑定 |
| I2 | Important | assess.py原67–75/125–134：仅信保护原因列表，失败分支不核对峰值/采样数 | 巨大力/相对角或checked_substeps=0仍能被记为普通失败并继续 |
| I3 | Important | assess.py原78–123/139–145/174–178：删除所有policy_observation/policy_raw仍通过 | 缺信息证据的全矩阵可能被建议匹配训练登记 |
| I4 | Important | run_preflight.py原157–162/169–174：源复核/解压/审核在子进程结束后同步运行，初始准备也无硬限 | 卡死审核可无限超出整轮6h或单次时限 |
| I5 | Minor | run_preflight.py原120–123/149–153：Job首次绑定失败只结束空Job | 已启动但未被接管的子进程可能残留，物理仍受GO门阻挡 |

原测试结果：25/25，4.179s；审查者没有修改代码，只产生测试保留夹具。纯反例无MuJoCo/Torch/SB3导入。

## 作者按实际影响分级与一次修复

I1–I4保留Important。I5上调为Important：它影响所承诺的进程退出确认和时限收口，且I4引入外层监督后同样必须保持所有权；虽不产生未授权物理，仍不能把未接管进程留作隐性开销。

| 项 | 修复 | RED→GREEN证据 |
|---|---|---|
| I1 | 强制固定worktree、实现目录、实际入口及已加载私有模块；claims固定至登记目录 | `test_I1_relocated_entrypoint_rejected_before_claim` |
| I2 | 核对全部保护子步数、每周期10个峰值样本、有限峰值/转角、阈值与原因/事件，核对采样下界 | `test_I2_guard_contradictions_rejected_for_ordinary_failure`，6类损坏 |
| I3 | 记录原观测capture输入、按固定构建器复算137维向量/原值/模式及权限；接触前后/对称点/两臂运动差分列；缺信息禁止登记路线 | `test_I3_missing_or_fabricated_observations_rejected`及`test_I3_missing_information_prevents_training_route` |
| I4 | 单次来源复核/原始审核放入原受限worker；外层独立进程Job监督覆盖准备、执行与最终矩阵审核；强停后只关闭本次唯一gate创建的claim | `test_I4_stalled_inert_audit_is_killed_by_production_deadline_guard`及`test_I4_outer_timeout_closes_only_this_launch_claim` |
| I5 | Job绑定未成功时以持有的Popen句柄终止本进程并确认退出；进程树不明保持未知且不发GO | `test_I5_assignment_failure_terminates_owned_handle` |

首次新增6个审查回归测试产生12个失败和2个缺接口错误，见[RED](review_regressions_red.txt)；额外超时收口反例先产生缺接口错误，见[RED](review_timeout_closure_red.txt)。同一修复回合最终 **32/32新测试通过**，见[GREEN](review_correction_green.txt)；另有[12项既有纯父进程检查](existing_parent_tests.txt)，4项会导入MuJoCo/Torch的旧probe明确未运行。全新无引擎检查另见[最终检查汇总](offline_tests.json)。没有声称实际引擎集成或物理可行性已通过。

绑定后检查另检出WindowsPath按大小写折叠排序与字符串序排序不一致；830个NumPy文件集合/内容无变化，不能因此错误拒绝合法候选。追加顺序反例先RED，修正生成器采用相同字符串排序后重新绑定。最终 **33/33新测试通过**，见[最终全套日志](final_tests.txt)；独立CLI无引擎检查通过，使用真实CPU解释器/父子监督启动的未授权请求在grant门被拒绝，没有创建输出或claim。该集成修正属于同一作者收口回合，没有第二次审查。

## 对审查者未判定事项的裁决

1. 实际物理可行性、接触行为、非零姿态性能：同意留待明确新预算；本轮引擎/真实reset/step均0，错误成本是未来预检可能首点即关闭。
2. 引擎参与的完整Windows执行链：同意不冒称已验证；当前证明无仿真进程监督与纯接口，实际连接仍需获批后验证。
3. 旧候选绑定/报告/封存/计划更新：它们只是制作中的临时状态；交付前重算绑定并验证快照，不能以“预期过期”为理由交付过期pin。
4. 原模型/控制器行为及历史验收：本轮只读复核，保持旧边界；成本是旧模型本身的范围局限仍然存在。
5. 手工伪造授权或任意直接调用Python内部函数：支持的授权入口为本目录CLI，授权文字需要真实用户证据；不把本地任意代码执行设计成安全沙箱。复制目录正常CLI绕过已由I1修复。
6. 没有恢复事件：继续判为覆盖不足，不扩展为“恢复通过”；未来匹配训练登记仍须列出恢复缺口。

## 实施裁决与限制

- Windows用Python提取计划brief和记录测试，代替依赖bash/sed的辅助脚本；保留同一任务账本语义。
- 用户要求优先：沿用worktree/分支，保留全部既有未提交工作及临时证据，不提交、合并、推送或删除；finishing-a-development-branch采用keep-as-is，省去已回答的集成选项。
- 本轮仅跑相关纯测试与无仿真进程测试；全项目pytest会加载引擎或学习运行时，超出本轮范围。未运行部分不能声称通过。
- 采用PC-06实际ContinuationResidualSession，未退回更早基础会话；失败罚时保持26s。错误使用旧类/25s会改变共同条件，故明确纠正。
- 默认TEMP受限，夹具保存在worktree/tmp并保留；代价为磁盘占用，不修改权限。
- Windows Job Object控制与原parent/venv身份函数配合；从固定源码提取纯数值定义，记录真实合成及观测采集输入。无需引擎导入，但仍不能替代真实端到端物理验证。
- 原方案未登记信息可区分的量化阈值；报告实际差分及裁剪，返回信息待解释审阅，不把非零浮点差直接当训练准入。代价是未来仍需基于实际档案作路线判断，避免临时发明准入阈值。

没有遗留Minor项；原I5已按实际收口影响上调并修复。未做第二次代码审查，修复充分性由作者反例与完整纯测试证明。

**Final disposition: OFFLINE_IMPLEMENTATION_READY**

该作者收口结论仅指本次离线交付准备，不表示物理执行已获授权、B.2已完成或训练已准入。下一步只办理固定9静态/最多16动态的新物理授权。
