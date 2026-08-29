"""Render the five Chinese V1 contact-validation figures from schema-1 JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.font_manager import FontProperties

from tools.validation.run_contact_cases import all_cases
from tools.validation.run_v1_contact_validation import TIMESTEP_VALUES_S
from tools.visualization.font_support import find_chinese_font


DISCLAIMER = "未经实物标定，仅用于准静态数值诊断"
MEDIUM_TIMESTEP_S = 0.0002
EXPECTED_FILENAMES = (
    "01_横向偏移接触力_深度曲线.png",
    "02_倾斜接触力矩_深度曲线.png",
    "03_联合偏差载荷_深度曲线.png",
    "04_穿透量与接触数_深度曲线.png",
    "05_时间步收敛对比.png",
)

CASE_LABELS = {
    "separated": "分离",
    "aligned": "理想对齐",
    "x_offset_pos_100um": "+X 偏移 100 微米",
    "x_offset_neg_100um": "−X 偏移 100 微米",
    "y_offset_pos_100um": "+Y 偏移 100 微米",
    "y_offset_neg_100um": "−Y 偏移 100 微米",
    "roll_pos_1.5deg": "+滚转 1.5°",
    "roll_neg_1.5deg": "−滚转 1.5°",
    "pitch_pos_1.5deg": "+俯仰 1.5°",
    "pitch_neg_1.5deg": "−俯仰 1.5°",
    "combined_a": "联合偏差 A",
    "combined_b": "联合偏差 B",
}


def load_v1_documents(trace_path: Path, convergence_path: Path) -> tuple[dict, dict]:
    """Load both schema-1 inputs and reject incomplete/incompatible evidence."""

    trace_document = json.loads(Path(trace_path).read_text(encoding="utf-8"))
    convergence_document = json.loads(
        Path(convergence_path).read_text(encoding="utf-8")
    )
    if trace_document.get("schema_version") != 1:
        raise ValueError("仅支持 V1 contact trace schema-1 数据。")
    if convergence_document.get("schema_version") != 1:
        raise ValueError("仅支持 V1 timestep convergence schema-1 数据。")
    traces = trace_document.get("traces")
    convergence_cases = convergence_document.get("cases")
    if not isinstance(traces, list):
        raise ValueError("trace schema-1 缺少 traces 列表。")
    if not isinstance(convergence_cases, list):
        raise ValueError("convergence schema-1 缺少 cases 列表。")

    index: dict[tuple[str, float], dict] = {}
    for trace in traces:
        if not isinstance(trace, dict):
            raise ValueError("trace schema-1 包含非对象轨迹。")
        try:
            key = (str(trace["case"]), float(trace["timestep_s"]))
            samples = trace["samples"]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("trace schema-1 轨迹缺少工况、时间步或样本。") from error
        if key in index:
            raise ValueError(f"trace schema-1 存在重复轨迹：{key}")
        if not isinstance(samples, list) or not samples:
            raise ValueError(f"trace schema-1 轨迹没有样本：{key}")
        index[key] = trace

    required_cases = [case.name for case in all_cases()]
    for case_name in required_cases:
        for timestep_s in TIMESTEP_VALUES_S:
            if (case_name, timestep_s) not in index:
                raise ValueError(
                    f"trace schema-1 缺少 {case_name} / {timestep_s} s。"
                )
    convergence_names = {
        item.get("case") for item in convergence_cases if isinstance(item, dict)
    }
    for case_name in required_cases:
        if case_name not in convergence_names:
            raise ValueError(f"convergence schema-1 缺少 {case_name}。")
    return trace_document, convergence_document


def _trace_index(document: dict) -> dict[tuple[str, float], dict]:
    return {
        (str(trace["case"]), float(trace["timestep_s"])): trace
        for trace in document["traces"]
    }


def _font() -> FontProperties:
    return FontProperties(fname=str(find_chinese_font()))


def _style_axis(axis, *, title: str, xlabel: str, ylabel: str, font) -> None:
    axis.set_title(title, fontproperties=font, fontsize=15, pad=12)
    axis.set_xlabel(xlabel, fontproperties=font, fontsize=11)
    axis.set_ylabel(ylabel, fontproperties=font, fontsize=11)
    axis.grid(alpha=0.25)
    axis.tick_params(labelsize=9)


def _finish_figure(figure, output: Path, font: FontProperties) -> Path:
    figure.text(
        0.5,
        0.012,
        DISCLAIMER,
        ha="center",
        fontproperties=font,
        fontsize=12,
        color="#A61B1B",
    )
    figure.tight_layout(rect=(0.015, 0.045, 0.985, 0.985))
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output,
        dpi=100,
        metadata={"Disclaimer": DISCLAIMER, "SourceSchema": "1"},
    )
    plt.close(figure)
    return output


def _values(trace: dict, field: str, component: str | None = None) -> list[float]:
    if component is None:
        return [float(sample[field]) for sample in trace["samples"]]
    return [float(sample[field][component]) for sample in trace["samples"]]


def _depth_mm(trace: dict) -> list[float]:
    return [float(sample["depth_m"]) * 1000.0 for sample in trace["samples"]]


def _plot_case_lines(
    axis,
    index: dict[tuple[str, float], dict],
    cases: Iterable[tuple[str, str]],
    *,
    field: str,
    component: str | None,
    scale: float,
    font: FontProperties,
) -> None:
    for case_name, label in cases:
        trace = index[(case_name, MEDIUM_TIMESTEP_S)]
        axis.plot(
            _depth_mm(trace),
            [value * scale for value in _values(trace, field, component)],
            linewidth=2.0,
            label=label,
        )
    axis.legend(prop=font, fontsize=9)


def _horizontal_figure(index, output: Path, font) -> Path:
    figure, axes = plt.subplots(1, 2, figsize=(18, 10), dpi=100)
    _plot_case_lines(
        axes[0],
        index,
        (("x_offset_pos_100um", "+X 100 微米"), ("x_offset_neg_100um", "−X 100 微米")),
        field="wrench",
        component="fx",
        scale=1.0,
        font=font,
    )
    _style_axis(
        axes[0], title="X 偏移：X 向接触力", xlabel="插入深度（mm）", ylabel="Fx（N）", font=font
    )
    _plot_case_lines(
        axes[1],
        index,
        (("y_offset_pos_100um", "+Y 100 微米"), ("y_offset_neg_100um", "−Y 100 微米")),
        field="wrench",
        component="fy",
        scale=1.0,
        font=font,
    )
    _style_axis(
        axes[1], title="Y 偏移：Y 向接触力", xlabel="插入深度（mm）", ylabel="Fy（N）", font=font
    )
    figure.suptitle("横向偏移接触力—深度曲线（Δt = 0.0002 s）", fontproperties=font, fontsize=19)
    return _finish_figure(figure, output, font)


def _tilt_figure(index, output: Path, font) -> Path:
    figure, axes = plt.subplots(1, 2, figsize=(18, 10), dpi=100)
    _plot_case_lines(
        axes[0],
        index,
        (("roll_pos_1.5deg", "+滚转 1.5°"), ("roll_neg_1.5deg", "−滚转 1.5°")),
        field="wrench",
        component="tx",
        scale=1.0,
        font=font,
    )
    _style_axis(
        axes[0], title="滚转误差：X 轴力矩", xlabel="插入深度（mm）", ylabel="Tx（N·m）", font=font
    )
    _plot_case_lines(
        axes[1],
        index,
        (("pitch_pos_1.5deg", "+俯仰 1.5°"), ("pitch_neg_1.5deg", "−俯仰 1.5°")),
        field="wrench",
        component="ty",
        scale=1.0,
        font=font,
    )
    _style_axis(
        axes[1], title="俯仰误差：Y 轴力矩", xlabel="插入深度（mm）", ylabel="Ty（N·m）", font=font
    )
    figure.suptitle("倾斜接触力矩—深度曲线（Δt = 0.0002 s）", fontproperties=font, fontsize=19)
    return _finish_figure(figure, output, font)


def _combined_figure(index, output: Path, font) -> Path:
    figure, axes = plt.subplots(1, 2, figsize=(18, 10), dpi=100)
    cases = (("combined_a", "联合偏差 A"), ("combined_b", "联合偏差 B"))
    _plot_case_lines(
        axes[0], index, cases, field="force_norm_n", component=None, scale=1.0, font=font
    )
    _style_axis(
        axes[0], title="联合偏差合力", xlabel="插入深度（mm）", ylabel="合力（N）", font=font
    )
    _plot_case_lines(
        axes[1], index, cases, field="torque_norm_nm", component=None, scale=1.0, font=font
    )
    _style_axis(
        axes[1], title="联合偏差合力矩", xlabel="插入深度（mm）", ylabel="合力矩（N·m）", font=font
    )
    figure.suptitle("联合偏差载荷—深度曲线（Δt = 0.0002 s）", fontproperties=font, fontsize=19)
    return _finish_figure(figure, output, font)


def _penetration_figure(index, output: Path, font) -> Path:
    figure, axes = plt.subplots(1, 2, figsize=(18, 10), dpi=100)
    cases = (
        ("aligned", "理想对齐"),
        ("x_offset_pos_100um", "+X 偏移"),
        ("roll_pos_1.5deg", "+滚转"),
        ("combined_a", "联合偏差 A"),
        ("combined_b", "联合偏差 B"),
    )
    _plot_case_lines(
        axes[0], index, cases, field="penetration_m", component=None, scale=1e6, font=font
    )
    _style_axis(
        axes[0], title="代表工况最大接触穿透量", xlabel="插入深度（mm）", ylabel="穿透量（微米）", font=font
    )
    _plot_case_lines(
        axes[1], index, cases, field="contact_count", component=None, scale=1.0, font=font
    )
    _style_axis(
        axes[1], title="代表工况接触点数量", xlabel="插入深度（mm）", ylabel="接触点数（个）", font=font
    )
    figure.suptitle("穿透量与接触数—深度曲线（Δt = 0.0002 s）", fontproperties=font, fontsize=19)
    return _finish_figure(figure, output, font)


def _convergence_figure(index, convergence: dict, output: Path, font) -> Path:
    figure, axes = plt.subplots(2, 1, figsize=(18, 10), dpi=100)
    colors = {0.0004: "#D95F59", 0.0002: "#E6A33D", 0.0001: "#2878B5"}
    for timestep_s in TIMESTEP_VALUES_S:
        trace = index[("combined_a", timestep_s)]
        axes[0].plot(
            _depth_mm(trace),
            _values(trace, "wrench", "tx"),
            linewidth=2.0,
            color=colors[timestep_s],
            label=f"Δt = {timestep_s:g} s",
        )
    axes[0].legend(prop=font)
    _style_axis(
        axes[0],
        title="联合偏差 A 主要力矩分量的三时间步重合程度",
        xlabel="插入深度（mm）",
        ylabel="Tx（N·m）",
        font=font,
    )

    cases = [item for item in convergence["cases"] if item["case"] not in {"separated", "aligned"}]
    positions = list(range(len(cases)))
    width = 0.36
    for offset, timestep_key, label, color in (
        (-width / 2, "0.0002", "0.0002 s 最大相对指标", "#E6A33D"),
        (+width / 2, "0.0004", "0.0004 s 最大相对指标", "#D95F59"),
    ):
        values = []
        for case in cases:
            comparison = case["comparisons"][timestep_key]
            metrics = [
                comparison["peak_force_relative_error"],
                comparison["peak_torque_relative_error"],
                comparison["primary_component_normalized_rmse"],
            ]
            values.append(max(value for value in metrics if value is not None) * 100.0)
        axes[1].bar(
            [position + offset for position in positions],
            values,
            width=width,
            color=color,
            label=label,
        )
    axes[1].axhline(10.0, color="#E6A33D", linestyle="--", linewidth=1.3, label="中时间步门槛 10%")
    axes[1].axhline(20.0, color="#D95F59", linestyle="--", linewidth=1.3, label="粗时间步门槛 20%")
    axes[1].set_xticks(
        positions,
        labels=[CASE_LABELS[case["case"]] for case in cases],
        rotation=25,
        ha="right",
        fontproperties=font,
    )
    axes[1].legend(prop=font, ncols=2)
    _style_axis(
        axes[1],
        title=f"各工况收敛指标｜总体验收：{convergence['overall_status']}",
        xlabel="工况",
        ylabel="最大相对指标（%）",
        font=font,
    )
    figure.suptitle("固定深度网格时间步收敛对比", fontproperties=font, fontsize=19)
    return _finish_figure(figure, output, font)


def generate_v1_charts(
    trace_path: Path, convergence_path: Path, output_dir: Path
) -> list[Path]:
    """Generate all five reviewed V1 figures."""

    trace_document, convergence_document = load_v1_documents(
        trace_path, convergence_path
    )
    index = _trace_index(trace_document)
    output = Path(output_dir)
    font = _font()
    return [
        _horizontal_figure(index, output / EXPECTED_FILENAMES[0], font),
        _tilt_figure(index, output / EXPECTED_FILENAMES[1], font),
        _combined_figure(index, output / EXPECTED_FILENAMES[2], font),
        _penetration_figure(index, output / EXPECTED_FILENAMES[3], font),
        _convergence_figure(
            index, convergence_document, output / EXPECTED_FILENAMES[4], font
        ),
    ]

