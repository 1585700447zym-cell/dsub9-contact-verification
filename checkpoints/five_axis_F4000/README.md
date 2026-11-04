> 2026-11-04：本目录权重与manifest保持原字节。下文及manifest中的“当前10 nm”是2026-11-02打包口径；现源码容差为100 nm。新恢复协议与GRU计划见[本次更新说明](../../docs/releases/版本更新_2026-11-04.md)。

# F4000 精简网络权重

原 2026-10-29 F4000，所有网络/目标网络张量及 log_alpha 与原文件相同。配置见 config.json，来源及摘要见 manifest.json。

不含回放、优化器或完整随机数状态；不能传入旧 load_checkpoint 作为断点续训文件。使用 tools.publication.five_axis_policy.load_policy 显式装入；命令行模块默认只做字节核对，不做推理。

训练时成功几何容差 1nm，当前源码 10nm。未重新训练、未重新评价，不能把口径修订作为训练收益。
