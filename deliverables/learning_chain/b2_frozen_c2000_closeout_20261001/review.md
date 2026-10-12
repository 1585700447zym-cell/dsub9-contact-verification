# 一次独立源码审查与实施者修复记录

日期：2026-10-02。独立审查者 `/root/night_closeout_review`，fresh context，只读；原结论 Critical 0 / Important 4 / Minor 0 / Ready No。以下为实施者逐条核实、反例及修复记录，不冒称审查者再次审查或批准。未启动新动态、学习或critic诊断。

1. 许可构造向父类只读config属性赋值，实际构造即失败。`permit_review_red.txt`记录AttributeError；新许可保存私有配置并返回副本，`permit_review_green.txt`通过真实构造和case许可核验。
2. 多个Collector共用一个要求独占新建的目录，第二点和恢复必失败。`integration_review_red.txt`记录真实构造的FileExistsError；每次按预约index使用独占collections目录，读取/审核同步。`directories_review_green.txt`五个实际构造通过，无物理。
3. 历史FORCE_ONLY动作审核硬编码XY150，拒绝合法XY50部署。`small_publication_red.txt`实际发布后被阻塞；新增本阶段DeploymentRules，沿用物理/时钟/奖励/终末/停稳审核，仅使用登记动作映射；Collector与离线审核共同核对。`small_publication_green.txt`非零XY50合成映射档案通过真实出版函数，经验入池0。该内存合成夹具不代表新的物理效果，不改历史原档案或旧规则。
4. 原生退出/停止栅栏故障可能遗留活动预约，原报告可能漏掉已启动而无assessment的候选。新增监督退出确认；确认后保留原账本字节并以失败终结预约，不退成本；不确定退出拒绝终结。报告先枚举所有启动目录/claim，再要求逐候选退出和审核。缺失计算记录标不完整和预约上限，不将未知视为0。`integration_review_green.txt`覆盖确认退出、未确认退出不改账本、已启动未审核拒绝报告，连同2/3共5项通过。

测试夹具首次缺MuJoCo导入路径，已加现有qualified runtime选择后重新取得针对动作映射错误的RED，两个日志均保留。不改任何已封存历史源码。最终完整协议由prepare.py执行并写入final_protocol.txt，未通过则不签发。

审查边界：未重新审查全部历史实现；未知策略效果、真实新进程轨迹一致性待实际执行；公平的小边界重新训练、独立测试、正式B.2验收不在本轮范围。一次必要修复后运行完整协议，不追加源码审查轮次。
