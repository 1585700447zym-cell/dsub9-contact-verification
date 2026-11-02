# D-sub9五维残差SAC与新电脑迁移

截至2026-11-02，分支 `snapshot/five-axis-sac-20261102`。完整F4000、专用MuJoCo及必要来源引擎已作为三个压缩包放在`migration/`，合计约86.3MiB；无需重复下载旧12GB完整备份。

- [新电脑使用说明](docs/releases/新电脑使用说明_2026-11-02.md)：安装、恢复、仿真及续训命令。
- [当前进度](项目进度跟踪.md) · [当前入口](项目当前入口.md) · [当前计划](研究推进计划_当前版.md)。
- [版本说明与历史边界](docs/releases/版本说明_2026-11-02.md) · [迁移包清单](migration/package.json)。

在Windows x64、Python3.13下，进入项目根目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File tools\migration\install_windows.ps1
```

安装脚本联网安装通用依赖、核验/解包、生成本机路径并检查完整状态及模型XML；不启动仿真推进、策略前向或训练。只有以后明确执行指南中的`--run`命令才会启动相应批次。

迁移续训使用F4000原1nm/2ms训练引擎和回放；当前10nm判据及50ms诊断代码保留，不静默混用。完整原始检查点在迁移包内，`checkpoints/five_axis_F4000/`仍是约1.99MiB的精简网络参数副本。

10项小型逻辑检查、中文空格路径恢复、F4000/162274条回放恢复、MuJoCo导入和模型XML编译已通过；未实跑新仿真或训练回合，未在第二台电脑验收，完整B.2/C未验收。其余历史轨迹、中间模型及完整备份不重复上传，本地完整资料保留。
