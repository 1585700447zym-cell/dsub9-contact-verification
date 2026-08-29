"""Generate the data-backed Markdown report for V1 contact validation."""

from __future__ import annotations

from pathlib import Path


CHART_LINKS = (
    "01_横向偏移接触力_深度曲线.png",
    "02_倾斜接触力矩_深度曲线.png",
    "03_联合偏差载荷_深度曲线.png",
    "04_穿透量与接触数_深度曲线.png",
    "05_时间步收敛对比.png",
)


def _percent(value: float | None) -> str:
    return "—" if value is None else f"{value * 100.0:.2f}%"


def _micrometres(value: float) -> str:
    return f"{value * 1_000_000.0:.3f}"


def _validate_documents(trace_document: dict, convergence_document: dict) -> None:
    if trace_document.get("schema_version") != 1:
        raise ValueError("trace schema_version must be 1")
    if convergence_document.get("schema_version") != 1:
        raise ValueError("convergence schema_version must be 1")
    if convergence_document.get("overall_status") not in {"PASS", "FAIL"}:
        raise ValueError("convergence overall_status must be PASS or FAIL")
    if not isinstance(convergence_document.get("cases"), list):
        raise ValueError("convergence document must contain cases")


def _comparison_rows(convergence_document: dict) -> list[str]:
    rows = []
    for case in convergence_document["cases"]:
        for timestep_key in ("0.0002", "0.0004"):
            comparison = case["comparisons"][timestep_key]
            rows.append(
                "| {case} | {timestep} s | {status} | {force} | {torque} | "
                "{rmse} | {depth} | {termination} |".format(
                    case=case["case"],
                    timestep=timestep_key,
                    status=comparison["status"],
                    force=_percent(comparison["peak_force_relative_error"]),
                    torque=_percent(comparison["peak_torque_relative_error"]),
                    rmse=_percent(
                        comparison["primary_component_normalized_rmse"]
                    ),
                    depth=_micrometres(
                        comparison["termination_depth_delta_m"]
                    ),
                    termination=(
                        "一致" if comparison["termination_match"] else "不一致"
                    ),
                )
            )
    return rows


def _failure_details(convergence_document: dict) -> list[str]:
    details = []
    depth_limit = convergence_document["limits"]["depth_delta_limit_m"]
    zero_limit = convergence_document["limits"]["zero_contact_absolute_limit"]
    metric_fields = {
        "peak_force_relative_pass": "peak_force_relative_error",
        "peak_torque_relative_pass": "peak_torque_relative_error",
        "primary_component_rmse_pass": "primary_component_normalized_rmse",
    }
    for case in convergence_document["cases"]:
        for timestep_key in ("0.0002", "0.0004"):
            comparison = case["comparisons"][timestep_key]
            for check in comparison.get("failed_checks", []):
                if check in metric_fields:
                    measured = _percent(comparison[metric_fields[check]])
                    limit = _percent(comparison["relative_limit"])
                elif check == "termination_depth_pass":
                    measured = f"{_micrometres(comparison['termination_depth_delta_m'])} 微米"
                    limit = f"{_micrometres(depth_limit)} 微米"
                elif check == "zero_contact_absolute_pass":
                    measured = "超过绝对零载荷门槛"
                    limit = f"{zero_limit:.1e}"
                elif check == "termination_match":
                    measured = (
                        f"{comparison['termination_candidate']} / "
                        f"{comparison['termination_reference']}"
                    )
                    limit = "必须一致"
                elif check == "no_numerical_error":
                    measured = comparison["termination_candidate"]
                    limit = "不得为 NUMERICAL_ERROR"
                elif check == "primary_sign_pass":
                    measured = "主要分量符号不一致或为零"
                    limit = "必须同号且非零"
                elif check == "finite_pass":
                    measured = "存在非有限数"
                    limit = "全部有限"
                else:
                    measured = "未通过"
                    limit = "必须通过"
                details.append(
                    f"- `{case['case']}`，{timestep_key} s，`{check}`："
                    f"实测 {measured}；冻结门槛 {limit}。"
                )
    return details


def build_v1_report(trace_document: dict, convergence_document: dict) -> str:
    """Render a deterministic report whose measured values come from JSON."""

    _validate_documents(trace_document, convergence_document)
    status = convergence_document["overall_status"]
    case_count = len(trace_document.get("cases", []))
    trace_count = int(trace_document["trace_count"])
    timestep_text = "、".join(
        f"{value:g} s" for value in trace_document["timestep_values_s"]
    )
    chart_lines = [
        f"- [{name}](../deliverables/chinese_visual_package/charts/v1_contact_validation/{name})"
        for name in CHART_LINKS
    ]
    convergence_rows = _comparison_rows(convergence_document)
    failure_details = _failure_details(convergence_document)
    if not failure_details:
        failure_details = ["- 未发现超限项。"]

    lines = [
        "# D-sub9 V1 接触验证报告",
        "",
        f"> 总体验收：**{status}**。全部载荷均未经实物标定，只能作为数值诊断证据。",
        "",
        "## 验证范围",
        "",
        "本报告补齐 Model V1 的规定姿态准静态接触验证：逐深度六维载荷、穿透量、接触数和固定深度网格时间步收敛。它不验证控制器、机器人自由动力学插入、实物插入力、Failure Boundary 或 RL episode。",
        "",
        "## 模型与固定配置",
        "",
        f"- MuJoCo：`{trace_document['mujoco_version']}`",
        f"- 碰撞模型：`{trace_document['collision_mode']}`",
        f"- 接触配置：`{trace_document['contact_profile']}`（未经实物标定）",
        f"- 求解器：`{trace_document['solver']}`",
        f"- schema-3 源结果 SHA-256：`{trace_document['source_contact_results_sha256']}`",
        "- 扫描方法：规定姿态逐点调用 `mj_forward`，不是自由动力学或力控制过程。",
        "",
        "## 工况与深度网格",
        "",
        f"共 {case_count} 个冻结工况、{trace_count} 条轨迹。时间步为 {timestep_text}；三组均使用 `{trace_document['spatial_step_m']:.8f} m`（10 微米）固定深度增量。",
        "",
        "固定深度网格使同一工况的比较点对应同一规定姿态，避免把空间采样变粗误当成时间步求解器差异。",
        "",
        "## 接触曲线证据",
        "",
        *chart_lines,
        "",
        "图中力使用 N、力矩使用 N·m、插入深度使用 mm、穿透量使用微米；图内和 PNG metadata 均保留未标定声明。",
        "",
        "## 时间步收敛",
        "",
        f"精细参考时间步为 `{convergence_document['reference_timestep_s']:g} s`。中时间步门槛为 {_percent(convergence_document['limits']['medium_relative_limit'])}，粗时间步门槛为 {_percent(convergence_document['limits']['coarse_relative_limit'])}。",
        "",
        "| 工况 | 对比时间步 | 状态 | 峰值合力相对差 | 峰值合力矩相对差 | 主要分量归一化 RMSE | 终止深度差（微米） | 终止 |",
        "|---|---:|:---:|---:|---:|---:|---:|:---:|",
        *convergence_rows,
        "",
        "相对指标为 `—` 表示参考值为零，未使用人为 epsilon 制造相对误差；这类工况改用绝对零载荷门槛。",
        "",
        "## 穿透与数值稳定性",
        "",
        "| 工况 | 参考终止 | 参考终止深度（mm） | 参考最大穿透量（微米） | 状态 |",
        "|---|:---:|---:|---:|:---:|",
        *[
            "| {case} | {termination} | {depth:.4f} | {penetration} | {status} |".format(
                case=case["case"],
                termination=case["reference_termination"],
                depth=case["reference_final_depth_m"] * 1000.0,
                penetration=_micrometres(case["reference_max_penetration_m"]),
                status=case["status"],
            )
            for case in convergence_document["cases"]
        ],
        "",
        "硬门槛检查有限数、`NUMERICAL_ERROR`、终止一致性、主要分量方向、10 微米终止深度差和理想/分离工况的绝对零载荷。",
        "",
        "## 总体验收",
        "",
        f"总体验收结果为 **{status}**。该结论由结构化 convergence schema-1 直接生成。",
        "这里的 `PASS` 只表示冻结的数值有限性、方向、终止一致性和时间步收敛门槛通过，不表示所有偏差工况都成功插到底，也不表示实物装配成功。",
        "",
        "超限或硬门槛失败明细：",
        "",
        *failure_details,
        "",
        "即使状态为 `FAIL`，原始轨迹和全部实测指标仍保留；不得修改门槛、接触参数或删除工况来制造通过。",
        "",
        "## 局限性与后续工作",
        "",
        "本结果没有材料与实物标定，不代表真实插入力，也不是控制器或自由动力学性能。后续应在独立工作中增加 V2 pin/socket 等效柔顺、控制器基线、Failure Boundary、机器人与 F/T 传感器证据，再决定是否进入学习策略与安全监督验证。",
    ]
    return "\n".join(lines).rstrip() + "\n"


def write_v1_report(
    trace_document: dict, convergence_document: dict, output_path: Path
) -> Path:
    """Write UTF-8/LF Markdown with exactly one final newline."""

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(build_v1_report(trace_document, convergence_document))
    return output
