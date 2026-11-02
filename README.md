## 2026-11-02迁移补充

完整F4000、专用MuJoCo及必要来源引擎已新增到本分支的`migration/`，合计约86.3MiB。见[新电脑使用说明](docs/releases/新电脑使用说明_2026-11-02.md)。安装/恢复/默认检查不会训练；显式仿真或续训才启动。迁移续训沿用原1nm/2ms条件，当前10nm/50ms主体代码保留。

以下精简版本说明保留首次主体上传时的范围；其“未附完整保存文件”现由迁移包补齐，仍不包含全部历史实验档案。

# D-sub9 五维残差 SAC 当前主体

截至 2026-11-02，分支 `snapshot/five-axis-sac-20261102`。

- [本版本说明](docs/releases/版本说明_2026-11-02.md)：内容、安装、权重、成功判据及限制。
- [当前进度](项目进度跟踪.md) · [当前入口](项目当前入口.md) · [当前计划](研究推进计划_当前版.md)。
- [关键结果与资料范围](docs/releases/当前结果与资料范围_2026-11-02.md)。
- [F4000 权重](checkpoints/five_axis_F4000/README.md) · [必要配置和模型](configs/five_axis_current/) · [上传清单](publication_manifest.json)。

保留传统搜索/导纳与五维残差 SAC。控制和网络仍 2ms；50ms 仅为最近诊断的探索噪声保持时长。当前 10nm 数值成功判据与旧 1nm 训练/记录明确区分。原四次保存点按新口径为 1/4，不代表已证明的 SAC 增益或泛化成功率；B.2/C 未验收。

```powershell
python -m pip install -r requirements-core-20261102.txt
python -B -m tools.publication.five_axis_policy
```

核对命令只读参数/配置字节，无仿真、推理或训练。旧批次执行器依赖本地冻结资料和指定运行时，不是此精简包的开箱重跑命令。完整轨迹、回放、环境、历史大包未重复上传，本地保留。
