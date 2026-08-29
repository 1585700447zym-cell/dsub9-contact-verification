# D-sub9 V1 接触验证报告

> 总体验收：**PASS**。全部载荷均未经实物标定，只能作为数值诊断证据。

## 验证范围

本报告补齐 Model V1 的规定姿态准静态接触验证：逐深度六维载荷、穿透量、接触数和固定深度网格时间步收敛。它不验证控制器、机器人自由动力学插入、实物插入力、Failure Boundary 或 RL episode。

## 模型与固定配置

- MuJoCo：`3.9.0`
- 碰撞模型：`sdf`
- 接触配置：`uncalibrated_diagnostic_v1`（未经实物标定）
- 求解器：`NEWTON(iterations=100)`
- schema-3 源结果 SHA-256：`ac767ea63a7e8a6866a974728a1256e688832003076170e270cd181e5c9d65ff`
- 扫描方法：规定姿态逐点调用 `mj_forward`，不是自由动力学或力控制过程。

## 工况与深度网格

共 12 个冻结工况、36 条轨迹。时间步为 0.0004 s、0.0002 s、0.0001 s；三组均使用 `0.00001000 m`（10 微米）固定深度增量。

固定深度网格使同一工况的比较点对应同一规定姿态，避免把空间采样变粗误当成时间步求解器差异。

## 接触曲线证据

- [01_横向偏移接触力_深度曲线.png](../deliverables/chinese_visual_package/charts/v1_contact_validation/01_横向偏移接触力_深度曲线.png)
- [02_倾斜接触力矩_深度曲线.png](../deliverables/chinese_visual_package/charts/v1_contact_validation/02_倾斜接触力矩_深度曲线.png)
- [03_联合偏差载荷_深度曲线.png](../deliverables/chinese_visual_package/charts/v1_contact_validation/03_联合偏差载荷_深度曲线.png)
- [04_穿透量与接触数_深度曲线.png](../deliverables/chinese_visual_package/charts/v1_contact_validation/04_穿透量与接触数_深度曲线.png)
- [05_时间步收敛对比.png](../deliverables/chinese_visual_package/charts/v1_contact_validation/05_时间步收敛对比.png)

图中力使用 N、力矩使用 N·m、插入深度使用 mm、穿透量使用微米；图内和 PNG metadata 均保留未标定声明。

## 时间步收敛

精细参考时间步为 `0.0001 s`。中时间步门槛为 10.00%，粗时间步门槛为 20.00%。

| 工况 | 对比时间步 | 状态 | 峰值合力相对差 | 峰值合力矩相对差 | 主要分量归一化 RMSE | 终止深度差（微米） | 终止 |
|---|---:|:---:|---:|---:|---:|---:|:---:|
| separated | 0.0002 s | PASS | — | — | — | 0.000 | 一致 |
| separated | 0.0004 s | PASS | — | — | — | 0.000 | 一致 |
| aligned | 0.0002 s | PASS | — | — | — | 0.000 | 一致 |
| aligned | 0.0004 s | PASS | — | — | — | 0.000 | 一致 |
| x_offset_pos_100um | 0.0002 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| x_offset_pos_100um | 0.0004 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| x_offset_neg_100um | 0.0002 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| x_offset_neg_100um | 0.0004 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| y_offset_pos_100um | 0.0002 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| y_offset_pos_100um | 0.0004 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| y_offset_neg_100um | 0.0002 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| y_offset_neg_100um | 0.0004 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| roll_pos_1.5deg | 0.0002 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| roll_pos_1.5deg | 0.0004 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| roll_neg_1.5deg | 0.0002 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| roll_neg_1.5deg | 0.0004 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| pitch_pos_1.5deg | 0.0002 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| pitch_pos_1.5deg | 0.0004 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| pitch_neg_1.5deg | 0.0002 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| pitch_neg_1.5deg | 0.0004 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| combined_a | 0.0002 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| combined_a | 0.0004 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| combined_b | 0.0002 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |
| combined_b | 0.0004 s | PASS | 0.00% | 0.00% | 0.00% | 0.000 | 一致 |

相对指标为 `—` 表示参考值为零，未使用人为 epsilon 制造相对误差；这类工况改用绝对零载荷门槛。

## 穿透与数值稳定性

| 工况 | 参考终止 | 参考终止深度（mm） | 参考最大穿透量（微米） | 状态 |
|---|:---:|---:|---:|:---:|
| separated | SUCCESS | 0.0000 | 0.000 | PASS |
| aligned | SUCCESS | 4.0000 | 0.000 | PASS |
| x_offset_pos_100um | SUCCESS | 4.0000 | 12.011 | PASS |
| x_offset_neg_100um | SUCCESS | 4.0000 | 12.039 | PASS |
| y_offset_pos_100um | SUCCESS | 4.0000 | 12.425 | PASS |
| y_offset_neg_100um | SUCCESS | 4.0000 | 12.352 | PASS |
| roll_pos_1.5deg | SUCCESS | 4.0000 | 13.528 | PASS |
| roll_neg_1.5deg | SUCCESS | 4.0000 | 13.668 | PASS |
| pitch_pos_1.5deg | SUCCESS | 4.0000 | 14.231 | PASS |
| pitch_neg_1.5deg | SUCCESS | 4.0000 | 14.007 | PASS |
| combined_a | EXCESS_PENETRATION | 0.1800 | 31.894 | PASS |
| combined_b | EXCESS_PENETRATION | 0.2600 | 30.802 | PASS |

硬门槛检查有限数、`NUMERICAL_ERROR`、终止一致性、主要分量方向、10 微米终止深度差和理想/分离工况的绝对零载荷。

## 总体验收

总体验收结果为 **PASS**。该结论由结构化 convergence schema-1 直接生成。
这里的 `PASS` 只表示冻结的数值有限性、方向、终止一致性和时间步收敛门槛通过，不表示所有偏差工况都成功插到底，也不表示实物装配成功。

超限或硬门槛失败明细：

- 未发现超限项。

即使状态为 `FAIL`，原始轨迹和全部实测指标仍保留；不得修改门槛、接触参数或删除工况来制造通过。

## 局限性与后续工作

本结果没有材料与实物标定，不代表真实插入力，也不是控制器或自由动力学性能。后续应在独立工作中增加 V2 pin/socket 等效柔顺、控制器基线、Failure Boundary、机器人与 F/T 传感器证据，再决定是否进入学习策略与安全监督验证。
