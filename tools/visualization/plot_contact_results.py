"""Create Chinese charts and a CSV from the immutable schema-3 results."""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable, Sequence

import matplotlib

matplotlib.use("Agg")
from matplotlib import pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.patches import Patch

from tools.visualization.font_support import find_chinese_font
from tools.visualization.runtime import CONTACT_RESULTS, PROJECT_ROOT


DISCLAIMER = "未经过实物标定，仅用于数值敏感性分析"

CASE_LABELS = {
    "separated": "分离",
    "aligned": "对齐",
    "x_offset_pos_100um": "+X 偏移 100 微米",
    "x_offset_neg_100um": "-X 偏移 100 微米",
    "y_offset_pos_100um": "+Y 偏移 100 微米",
    "y_offset_neg_100um": "-Y 偏移 100 微米",
    "roll_pos_1.5deg": "+滚转 1.5°",
    "roll_neg_1.5deg": "-滚转 1.5°",
    "pitch_pos_1.5deg": "+俯仰 1.5°",
    "pitch_neg_1.5deg": "-俯仰 1.5°",
    "combined_a": "组合偏差 A",
    "combined_b": "组合偏差 B",
}
MODEL_LABELS = {
    "sdf": "正式解析 SDF",
    "polygon32": "polygon32 近似回退",
}
PROFILE_LABELS = {
    "uncalibrated_diagnostic_v1": "基线未标定诊断",
    "uncalibrated_low_response_v1": "低响应敏感性",
    "uncalibrated_high_response_v1": "高响应敏感性",
}
PROFILE_COLORS = {
    "uncalibrated_diagnostic_v1": "#2878B5",
    "uncalibrated_low_response_v1": "#57A773",
    "uncalibrated_high_response_v1": "#D95F59",
}
TERMINATION_LABELS = {
    "SUCCESS": "正常完成",
    "EXCESS_PENETRATION": "达到穿透量终止条件",
    "NUMERICAL_ERROR": "数值错误",
}
REQUIRED_FIELDS = {
    "case",
    "collision_mode",
    "contact_profile",
    "termination",
    "peak_force_n",
    "peak_torque_nm",
    "max_penetration_m",
    "timestep_s",
    "spatial_step_m",
}


@dataclass(frozen=True)
class ResultRow:
    case: str
    collision_mode: str
    contact_profile: str
    termination: str
    peak_force_n: float
    peak_torque_nm: float
    max_penetration_m: float
    timestep_s: float
    spatial_step_m: float

    @property
    def case_label(self) -> str:
        return CASE_LABELS[self.case]

    @property
    def model_label(self) -> str:
        return MODEL_LABELS[self.collision_mode]

    @property
    def profile_label(self) -> str:
        return PROFILE_LABELS[self.contact_profile]

    @property
    def display_label(self) -> str:
        timestep_us = self.timestep_s * 1_000_000
        spatial_um = self.spatial_step_m * 1_000_000
        return (
            f"{self.case_label}｜{self.model_label}｜{self.profile_label}｜"
            f"Δt={timestep_us:g}µs, Δs={spatial_um:g}µm"
        )


def load_result_rows(path: Path) -> list[ResultRow]:
    """Validate and convert the existing schema-3 result document."""

    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if document.get("schema_version") != 3:
        raise ValueError("仅支持现有 contact validation schema-3 数据。")
    raw_results = document.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("schema-3 数据缺少 results 列表。")

    rows: list[ResultRow] = []
    for index, raw in enumerate(raw_results, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"第 {index} 条结果不是对象。")
        missing = sorted(REQUIRED_FIELDS.difference(raw))
        if missing:
            raise ValueError(f"第 {index} 条结果缺少字段：{', '.join(missing)}")
        try:
            row = ResultRow(
                case=str(raw["case"]),
                collision_mode=str(raw["collision_mode"]),
                contact_profile=str(raw["contact_profile"]),
                termination=str(raw["termination"]),
                peak_force_n=float(raw["peak_force_n"]),
                peak_torque_nm=float(raw["peak_torque_nm"]),
                max_penetration_m=float(raw["max_penetration_m"]),
                timestep_s=float(raw["timestep_s"]),
                spatial_step_m=float(raw["spatial_step_m"]),
            )
            row.case_label
            row.model_label
            row.profile_label
            TERMINATION_LABELS[row.termination]
        except KeyError as error:
            raise ValueError(f"第 {index} 条结果包含未知分类：{error.args[0]}") from error
        rows.append(row)

    labels = [row.display_label for row in rows]
    if len(labels) != len(set(labels)):
        raise ValueError("schema-3 结果无法用工况、模型、配置和步长唯一标识。")
    return rows


CSV_FIELDS = (
    "工况",
    "模型类型",
    "接触配置",
    "终止原因",
    "峰值力_N_未标定",
    "峰值力矩_Nm_未标定",
    "最大穿透量_微米",
    "时间步_秒",
    "空间步长_米",
)


def write_summary_csv(rows: Sequence[ResultRow], path: Path) -> Path:
    """Write all result records with scientific context preserved."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "工况": row.case_label,
                    "模型类型": row.model_label,
                    "接触配置": row.profile_label,
                    "终止原因": TERMINATION_LABELS[row.termination],
                    "峰值力_N_未标定": f"{row.peak_force_n:.9f}",
                    "峰值力矩_Nm_未标定": f"{row.peak_torque_nm:.12f}",
                    "最大穿透量_微米": f"{row.max_penetration_m * 1_000_000:.6f}",
                    "时间步_秒": f"{row.timestep_s:.7g}",
                    "空间步长_米": f"{row.spatial_step_m:.7g}",
                }
            )
    return output


def _plot_metric(
    rows: Sequence[ResultRow],
    output: Path,
    *,
    title: str,
    xlabel: str,
    value: Callable[[ResultRow], float],
) -> Path:
    font = FontProperties(fname=str(find_chinese_font()))
    values = [value(row) for row in rows]
    labels = [row.display_label for row in rows]
    colors = [PROFILE_COLORS[row.contact_profile] for row in rows]

    figure, axis = plt.subplots(figsize=(16, 10), dpi=100)
    positions = list(range(len(rows)))
    bars = axis.barh(positions, values, color=colors, edgecolor="#333333", linewidth=0.5)
    for bar, row in zip(bars, rows):
        if row.collision_mode == "polygon32":
            bar.set_hatch("///")
    axis.set_yticks(positions, labels=labels, fontproperties=font, fontsize=8)
    axis.invert_yaxis()
    axis.set_title(title, fontproperties=font, fontsize=18, pad=16)
    axis.set_xlabel(xlabel, fontproperties=font, fontsize=12)
    axis.grid(axis="x", alpha=0.25)
    axis.tick_params(axis="x", labelsize=9)
    legend = [
        Patch(color=PROFILE_COLORS[key], label=label)
        for key, label in PROFILE_LABELS.items()
    ]
    legend.append(Patch(facecolor="white", edgecolor="#333333", hatch="///", label="polygon32 近似"))
    axis.legend(handles=legend, prop=font, loc="lower right")
    figure.text(
        0.5,
        0.015,
        DISCLAIMER,
        ha="center",
        fontproperties=font,
        fontsize=12,
        color="#A61B1B",
    )
    figure.tight_layout(rect=(0.0, 0.04, 1.0, 1.0))
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        output,
        dpi=100,
        metadata={"Disclaimer": DISCLAIMER, "SourceSchema": "3"},
    )
    plt.close(figure)
    return output


def generate_charts(input_path: Path, output_dir: Path) -> list[Path]:
    """Generate the three required charts and one Chinese summary CSV."""

    rows = load_result_rows(Path(input_path))
    output = Path(output_dir)
    outputs = [
        _plot_metric(
            rows,
            output / "01_各工况峰值力.png",
            title="各工况峰值合力对比",
            xlabel="峰值合力（N，未标定）",
            value=lambda row: row.peak_force_n,
        ),
        _plot_metric(
            rows,
            output / "02_各工况峰值力矩.png",
            title="各工况峰值合力矩对比",
            xlabel="峰值合力矩（N·m，未标定）",
            value=lambda row: row.peak_torque_nm,
        ),
        _plot_metric(
            rows,
            output / "03_各工况最大穿透量.png",
            title="各工况最大穿透量对比",
            xlabel="最大穿透量（微米）",
            value=lambda row: row.max_penetration_m * 1_000_000,
        ),
    ]
    outputs.append(write_summary_csv(rows, output / "接触结果中文摘要.csv"))
    return outputs


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成 D-sub9 接触结果中文图表。")
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / CONTACT_RESULTS,
        help="schema-3 接触结果 JSON",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "deliverables/chinese_visual_package/charts",
        help="图表和 CSV 输出目录",
    )
    args = parser.parse_args(argv)
    for path in generate_charts(args.input, args.output_dir):
        print(f"已生成：{path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

