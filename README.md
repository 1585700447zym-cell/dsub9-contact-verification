# D-sub9五维残差SAC与新电脑迁移

截至2026-11-04，沿用分支`snapshot/five-axis-sac-20261102`。本次覆盖更新当前文件，保留F4000和三个迁移包及提交历史。

- [本次更新说明](docs/releases/版本更新_2026-11-04.md)：30 s预算、450/900、100 nm容差和真实超力恢复。
- [当前配置](configs/five_axis_current/CURRENT.json) · [项目进度](项目进度跟踪.md) · [当前入口](项目当前入口.md)。
- [GRU简明计划](deliverables/planning/gru_sac_20261104/给用户的实施计划.md) · [AI实施计划](docs/superpowers/plans/2026-11-04-gru-residual-sac.md)。
- [新电脑使用说明](docs/releases/新电脑使用说明_2026-11-02.md) · [迁移包清单](migration/package.json) · [上传清单](publication_manifest.json)。

100 nm与超力恢复代码已实现，尚未实跑新恢复回合；GRU仅完成计划，未实现或训练。完整B.2/C未验收，科学初始化累计455。11月3日450/900共8次尝试、7个完整结果和1次外部中止，当时10 nm严格成功2次，全部零更新。

Windows x64、Python 3.13新电脑仍使用原安装入口：

```powershell
powershell -ExecutionPolicy Bypass -File tools\migration\install_windows.ps1
```

安装/恢复/默认检查不启动仿真或训练。migration/完整F4000和冻结引擎保持原1 nm/2 ms训练条件；当前100 nm/50 ms/恢复协议另行登记，不能直接混用旧回放。三个迁移包约86.3 MiB，未重复上传全部历史实验档案。
