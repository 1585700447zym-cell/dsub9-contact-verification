# v4接入整阶段独立审查

审查者/root/v4_adapter_review，gpt-6-astra/high，独立作者、全新上下文。只读/纯mock/纯数值，没有模型构造、reset/step、训练或子代理。

初评：0 Critical / 4 Important / 0 Minor。

1. claim后的外层异常没有统一封闭账本，模拟next_case读取失败后仍running。新增整轮异常收口；RED→GREEN。
2. STOP检查晚于领取和环境构造/reset。新增领取前、构造前、reset前检查；预先存在STOP不创建动态尝试；RED→GREEN。
3. 参考lead裁剪可能使实际参考越界而预测不越界。新增以动作前snapshot搜索原点检查RUNNING trace端点，越界触发受控停止并使验证门失败；STOPPING/恢复重置不误计；纯数值反例RED→GREEN。只验证控制端点，不宣称整个子步安全不变量。
4. 旧基线配置、runtime、admission三输入在prepare后缺少再次绑定。执行hash纳入全部冻结依赖，verify_inputs重查共同源文件和当前runtime证明；RED→GREEN。

6项新失败（包括下述内侧裕量增强）/19通过→25项通过。相关全套见tests_final.txt。未进行二次审查；无未解决Important，无延期Minor。

Ruling: 被过滤的命令使用R−1pm内侧目标，不消耗控制器已有1pm容差作为控制空间；零残差和原本可行候选保持原值。若基线落在容差壳内则保留基线。代价是残差可用范围微小收缩，保留动作请求与实际作用分别记录。

未发现多继承绕过参考释放/XY重置/分层裁判，或prepare重复更新；速度段凸性与再次限幅、阶段权限、live命令观测、原始请求和effective分离符合当前协议。动态零轨迹等价、恢复、停稳与完整训练准入仍需实际证据。
