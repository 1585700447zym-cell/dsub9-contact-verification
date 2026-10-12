# Windows虚拟环境父进程身份检查修复

2026-09-29，用户要求“开始修复问题”。本项只修复入口并做零物理验证，不重新启动训练、不生成新训练授权。旧失败包61项文件保持原字节；受影响入口源码修改前的原字节保存于snapshots/run_force_failure_cycle.py，并绑定原候选所记录的摘要。其他旧911项输入逐项保持，后续不能对已修改共享源码直接运行旧资格。

## 原因与限定改动

旧入口要求os.getppid()等于登记的监督器/工作进程PID，实际Windows虚拟环境python.exe先启动基础解释器，执行代码的进程与监督器之间因此有一层启动器。该假设在监督→工作和工作→恢复两个边界均不成立。

新入口调用同一个Windows身份校验函数，只接受直接登记父进程，或经过本虚拟环境确切路径的单层启动器。核对基础解释器路径、启动器路径、父子关系、进程存活、创建先后和登记时间；持有进程句柄到校验完成，信息读取失败即拒绝。不是搜索任意祖先进程，也没有取消身份检查。现阶段只验证项目当前Windows环境，不声称跨平台支持。

修改限于require_parent的调用及新工具模块process_parent.py。配置、学习算法、保护、奖励、初始状态、物理库、预算和独占claim逻辑不变。原监督器继续复用原字节。

## 验证方式

先运行新回归：旧实现13失败/3通过，真实Windows监督→工作→恢复正向链在原父进程检查处失败。修复后41项入口及新专项检查通过（16.71秒），主测试进程及探针子进程均屏蔽物理、SAC预测和Adam优化调用，计数全0。

真实进程探针使用原监督器启动，调用实际require_parent和claim函数，在独立临时输出目录内完成工作→恢复进程链。测试没有替换父进程检查，不调用训练main/worker，不构造物理回合，也不加载真实训练检查点。它验证本次入口故障，不代替真实训练或恢复验收。

拒绝反例覆盖错误父PID、过期登记、非本环境解释器/启动器、错误祖先及额外层级、死亡进程、PID复用、创建时间倒置、未来登记、查询失败和重复claim。直接基础解释器子进程也实测通过。

最终入口、授权、顺序预算、监督及新进程相关套件**57项全部通过**（15.53秒，含上述41项，不相加）。原16项新增测试在修复前13失败/3通过。一次限定只读审查无Critical/Important，1项Minor已修复：负向测试必须核对确切拒绝原因和完整子进程计数文件，避免无关导入失败伪装成正确拒绝。

证据：[最终测试绑定](final_related_binding.json)、[真实进程结果](real_process_results.json)、[审查及处理](独立审查.md)、[修复验收](assessment.json)。只运行与入口/授权/监督相关的检查，不把历史187项报告追改为当前源码的验证。新增物理、策略预测与优化均0。

## 历史与执行边界

旧入口尝试1次、物理启动0、SAC更新0的事实保持。此次修复的物理/预测/优化也为0，跟踪仍PAUSED。旧候选、授权、失败和未执行预算不自动迁移为重试许可；下一次实际执行须绑定修复源码和新的执行目录，不能覆盖或重启失败包。

本项不说明策略效果已改善，不宣告B.2完成。项目进度、交付总览和月报继续更新原三份滚动文档。

## Windows接口依据

父PID读取采用[PROCESSENTRY32W](https://learn.microsoft.com/en-us/windows/win32/api/tlhelp32/ns-tlhelp32-processentry32w)，镜像路径采用[QueryFullProcessImageNameW](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-queryfullprocessimagenamew)，创建时间采用[GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes)，句柄存活采用零等待的[WaitForSingleObject](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject)。这些文档支持API含义；本环境的虚拟启动层行为由原parentage_probe及本项真实进程测试证明。
