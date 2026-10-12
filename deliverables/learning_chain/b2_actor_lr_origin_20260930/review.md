# 2026-09-30 共同起点重建独立只读审查

审查范围：actor_lr_origin.py、两份新测试、build_origin.py、inspect_origin.py及origin_v2元数据。审查者只读，不运行脚本/测试/模型/优化或物理。

初次结论：来源摘要、既有FORCE_ONLY整轨迹审核、初始_snapshot精确比较、回放/边界/随机序列重建及A/B深复制一致；未发现真实计算授权泄漏、历史学习权重污染或共享张量问题。

发现归档raw_action先降为float32会掩盖小于半ULP的原数值差异。实际封存摘要没有显示归档被改，不能由此认定共同起点错误；但“原请求精确一致”的接口声明应收紧。已改为将生成float32请求提升为float64，与原归档数值直接比较，追加nextafter舍入碰撞及形状/非有限反例。4反例先红后绿，联合原28项通过；严格重建另存origin_v2，旧origin不覆写。

复核通过，无剩余重要问题。origin_v2明确formal_updates=0、a_500_learning_reproduced=false、policy_effect_validated=false、真实前向/优化/物理0、资格/授权false。抽样和随机流核对不能替代梯度、Adam学习结果或在线策略效果。
