# 独立整阶段审查与修复

审查者：`/root/paper_protocol_review`，独立作者、全新上下文，gpt-6-astra / high。仅只读及纯评价函数反例，没有物理/网络/训练调用，也未启动子代理。

范围：本轮计划、协议、评价源码和测试、机器共同配置及归档反事实审计。未重审所有历史物理有效性，也未审查尚未实现的v4残差接口或未来训练。

初评 **Critical 0 / Important 2 / Minor 0**：

1. `paper_comparison.py` 未校验失败标签与独立物理事实一致性。INVALID_SIMULATION却valid=true等矛盾记录可获得比较资格，极端构造还能获得pilot_signal。保留独立contact_guard/motion_violation事实并按现有裁决优先级检查每个终末类别；保护事实与原因列表必须一致，避免依赖成功标签的单向校验。
2. `prepare_and_audit.py` 的目录过滤漏绑 `run_b2_search.py`、`native313_matrix_audit.py`、`run_contact_candidate_stop.py`、`run_contact_cases.py` 和新评价源码。改为保守绑定TV-09原执行依赖（源码、模型、资产及runtime/准入引用，排除可变收口计划），增加新评价源码SHA、runtime证明摘要和完整初始姿态。

一次修复记录：新增11项反例，**11失败/25通过 RED → 36通过 GREEN**；最终相关套件见 `tests_final.txt`。没有请求二次审查。未解决Critical/Important为0，未延期Minor。

独立审查还核对了六个命令反例的原始时序、前一限幅命令、当前基线和坐标系；实际基线参考增量与limited×2ms误差小于7e−20m。最大超界16.60889075nm只证明一步预测接口缺口，不代表反事实物理失败或多步安全保证。

Ruling: 接受两项Important并修复，采用保守依赖绑定而不在本阶段构建动态导入分析。代价是未来无关旧工具变化也可能要求重新核对共同指纹；避免错误地把控制/裁判变化算作方法收益更重要。
