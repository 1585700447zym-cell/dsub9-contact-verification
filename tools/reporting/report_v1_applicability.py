"""Produce Chinese scientific diagnostic figures and an evidence-led report."""
import json
import hashlib
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Polygon
import numpy as np

from tools.validation.diagnose_v1_applicability import (
    ROOT, PINS, DEFAULT_HOLE, ContactCase, rotation, material_distance, fingerprint,
)
from tools.visualization.font_support import find_chinese_font


OUT = ROOT/'deliverables/v1_applicability'


def verify_sources(expected):
    if fingerprint() != expected:
        raise ValueError('source fingerprints differ; regenerate diagnosis before reporting')


def save(fig, name):
    fig.text(.5, .014, '规定姿态准静态诊断；载荷未经实物标定；不代表闭环插接或材料变形',
             ha='center', color='#a32a27', fontsize=10)
    fig.savefig(OUT/name, dpi=170, bbox_inches='tight', metadata={'Description': '未实物标定的准静态诊断'})
    plt.close(fig)


def main():
    d = json.loads((OUT/'diagnostic_results.json').read_text(encoding='utf-8'))
    verify_sources(d['source_sha256'])
    font_manager.fontManager.addfont(str(find_chinese_font()))
    plt.rcParams.update({'font.family': font_manager.FontProperties(fname=str(find_chinese_font())).get_name(),
                         'axes.unicode_minus': False, 'font.size': 11})
    scans = {s['case']['name']: s for s in d['scans']}
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.3))
    for ax, name in zip(axes, ('combined_a', 'combined_b')):
        s = scans[name]
        w = next(w for w in d['geometry_witnesses'] if w['case'] == name and w['event'] == 'first_exceed')
        pin = next(p for p in PINS if p[0] == w['deepest']['pin'])
        _, center, radius, half_length, hc = pin
        t, z = np.meshgrid(np.arange(180)*math.pi/90, np.linspace(-half_length, half_length, 161))
        points = np.column_stack([radius*np.cos(t.ravel()), radius*np.sin(t.ravel()), z.ravel()])+center
        c = ContactCase(**s['case'])
        world = points @ rotation(c).T + [c.x_offset_m, c.y_offset_m, c.start_origin_z_m+s['final_depth_m']]
        local = world-hc
        radial = np.hypot(local[:,0], local[:,1])
        inside = material_distance(local, DEFAULT_HOLE) < -1e-12
        visible = (local[:,2] > -.00005) & (local[:,2] < .00065) & (radial > .00044)
        ax.add_patch(Polygon([(0,.675),(0,1),(.65,1),(.65,.575),(.25,.575),(.25,.675)],
                             facecolor='#dbe1e8', edgecolor='#596574', label='孔壁实体轮廓'))
        ax.scatter(local[visible,2]*1000, radial[visible]*1000, s=3, color='#8699b0', alpha=.5,
                   label='针表面投影采样')
        selected = visible & inside
        ax.scatter(local[selected,2]*1000, radial[selected]*1000, s=5, color='#c73535',
                   label='位于孔壁实体内')
        p = w['deepest']['point_in_hole_m']
        ax.scatter([p[2]*1000], [math.hypot(p[0],p[1])*1000], color='black', marker='*', s=90,
                   label='最深采样见证点', zorder=5)
        ax.set(xlim=(-.03,.65), ylim=(.44,.86), xlabel='孔局部轴向位置 z（mm）', ylabel='距孔轴半径 r（mm）',
               title=f'{name} · {w["deepest"]["pin"]} · 扫描深度 {s["final_depth_m"]*1000:.2f} mm')
        ax.axvline(.25, color='#566b85', ls='--', lw=1)
        ax.legend(loc='upper right', fontsize=8)
        ax.grid(alpha=.18)
    fig.suptitle('针孔异常定位：入口为阶梯扩孔，针表面已进入主孔壁', fontsize=16)
    fig.subplots_adjust(top=.84, bottom=.16, wspace=.25)
    save(fig, '01_针孔几何重叠定位.png')

    fig, axes = plt.subplots(1, 2, figsize=(12, 6))
    suffixes = ['', '_translation_only', '_rotation_only', '_without_x_offset_m', '_without_y_offset_m',
                '_without_roll_rad', '_without_pitch_rad', '_scale_0.75', '_scale_0.5', '_scale_0.25']
    labels = ['原始组合','仅位置偏差','仅双轴倾角','去掉 X 偏差','去掉 Y 偏差','去掉滚转','去掉俯仰',
              '整体缩至 75%','整体缩至 50%','整体缩至 25%']
    for ax, name in zip(axes, ('combined_a', 'combined_b')):
        values = [scans[name+s]['max_penetration_m']*1e6 for s in suffixes]
        bars = ax.barh(labels, values, color=['#c73535' if v > 30 else '#4778a7' for v in values])
        for b, v in zip(bars, values): ax.text(v+.3,b.get_y()+b.get_height()/2,f'{v:.2f}',va='center',fontsize=9)
        ax.axvline(30,color='#c73535',ls='--',label='历史停止门槛 30 μm')
        ax.invert_yaxis()
        ax.set(title=name, xlabel='扫描至终止时的最大接触穿透（μm）', xlim=(0,40))
        ax.legend(loc='lower right',fontsize=8)
        ax.grid(axis='x',alpha=.2)
    fig.suptitle('规定姿态对照：偏差组合方式会改变早期干涉',fontsize=16)
    fig.tight_layout(rect=(0,.065,1,.93))
    save(fig, '02_偏差拆分与缩放对照.png')

    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
    names = ['roll_pos_1.5deg','pitch_pos_1.5deg','dev_corner_02','dev_corner_04','dev_corner_11','dev_corner_13']
    short = ['滚转 1.5°','俯仰 1.5°','开发角点02','开发角点04','开发角点11','开发角点13']
    x=np.arange(len(names))
    for j, n in enumerate((40,200,1000)):
        values = [next(s['contact_count'] for s in d['search_sensitivity']
                       if s['case']['name']==name and s['sdf_initpoints']==n and s['sdf_iterations']==10) for name in names]
        bars=axes[0].bar(x+(j-1)*.25,values,.25,label=f'搜索起点 {n}')
        for b,v in zip(bars,values): axes[0].text(b.get_x()+b.get_width()/2,v+1,str(v),ha='center',fontsize=8)
    axes[0].set_xticks(x,short,rotation=25,ha='right')
    axes[0].set(title='相同姿态，仅改变搜索起点数',ylabel='接触点数量')
    axes[0].legend(fontsize=9)
    overlap = [next(s['geometry_witness']['sampled_max_material_overlap_m']*1e6 for s in d['search_sensitivity']
                    if s['case']['name']==name) for name in names]
    bars=axes[1].bar(short,overlap,color='#c73535')
    for b,v in zip(bars,overlap): axes[1].text(b.get_x()+b.get_width()/2,v+.4,f'{v:.2f}',ha='center',fontsize=9)
    axes[1].tick_params(axis='x',rotation=25)
    axes[1].set(title='同一姿态的独立几何见证',ylabel='针表面采样的实体重叠深度（μm）',ylim=(0,max(overlap)*1.2))
    fig.suptitle('接触覆盖缺陷：有实体重叠的姿态，原配置仍可能报告零接触',fontsize=15)
    fig.tight_layout(rect=(0,.07,1,.92))
    save(fig, '03_接触漏检与搜索敏感性.png')

    dev=[s for s in d['scans'] if s['case']['name'].startswith('dev_')]
    audit=[a for a in d['coverage_audit'] if a['case']['name'].startswith('dev_')]
    failed=[a for a in audit if a['missing_overlap_pairs']]
    head = '''# V1 控制开发适用性诊断

日期 2026年9月14日

**结论：接触异常诊断已形成证据，当前 V1 碰撞配置尚不满足接触反馈控制开发的进入条件。** 可以继续设计接口和搭建自由空间动态框架，但接触闭环、B1 验收和 SAC 正式训练应等待接触检出覆盖问题修正并复验。

这次未修改原始几何、接触参数、30 μm 停止门槛或 V1 报告。全部新增结果来自规定姿态 `mj_forward`；不存在自由动力学或实物实验。

## 组合工况为什么超限

独立解析几何计算确认：组合姿态下，部分针表面已经进入主孔壁实体。孔入口是直径 1.35 mm、深 0.25 mm 的圆柱浅扩孔，其后接直径 1.15 mm 主孔，存在入口台阶。公头姿态在扫描中保持固定，接触反力不能让公头自行纠偏，所以继续推进会保持或增加干涉。

这支持“规定组合姿态与阶梯孔存在真实的模型几何干涉”，不是实物卡滞结论，也不代表针脚发生等量材料变形。位置偏差、双轴倾斜及九针阵列的空间位置共同决定干涉，不能归结为单一 X 偏差或直接认定应扩大孔径。

| 工况 | 首次接触深度 mm | 首次超限深度 mm | 超限时最大接触穿透 μm | 最深接触对象 |
|---|---:|---:|---:|---|
'''
    lines=[head]
    for name in ('combined_a','combined_b'):
        s=scans[name];e=s['events']
        lines.append(f'| {name} | {e["first_contact"]["depth_m"]*1000:.3f} | {s["final_depth_m"]*1000:.3f} | {s["max_penetration_m"]*1e6:.3f} | {" / ".join(e["first_exceed"]["contacts"][0]["pair"])} |')
    lines.append('''
![针孔几何重叠定位](01_针孔几何重叠定位.png)

图为径向—轴向投影，不是 CAD 干涉体积或单一剖面。红点是针表面采样中位于孔壁内部的点。

## 两类穿透指标必须分开

原指标 `max(0,-contact.dist)` 是 MuJoCo 实际找到的接触点中的最大负距离；独立指标是在针表面采样，计算该点距孔壁实体边界的负距离。两者的采样位置和定义不同，不能要求数值相等，不能把独立值直接代入原有 30 μm 门槛。

独立采样的最大值是已发现的重叠证据下界，不是连续表面最大值的证明。采样未发现重叠也不代表绝对无干涉。检查只覆盖相应针孔，不认证 D 形壳或其他交叉碰撞的完整性。

| 工况与姿态 | 针表面实体重叠见证 μm | 见证针 | 360角点/161轴点细化到720/321 |
|---|---:|---|---|
''')
    for name in ('combined_a','combined_b'):
        w=next(w for w in d['geometry_witnesses'] if w['case']==name and w['event']=='first_exceed')
        fine=next(w for w in d['geometry_witnesses'] if w['case']==name and w['event']=='surface_sampling_refinement')
        lines.append(f'| {name} 首次超限姿态 | {w["sampled_max_material_overlap_m"]*1e6:.3f} | {w["deepest"]["pin"]} | {fine["sampled_max_material_overlap_m"]*1e6:.3f} μm |')
    lines.append('''
## 新发现的接触覆盖缺陷

在相同的几何、姿态和接触参数下，独立几何见证存在实体重叠，但原 SDF 搜索配置会遗漏相应针孔接触。滚转 +1.5°、4 mm 深度的姿态中，约 30.02 μm 的采样重叠与零接触同时出现。仅提高搜索起点数就能检出接触，说明 SDF 接触搜索覆盖不足是实际问题；只增迭代次数在已测姿态中没有相同效果。

MuJoCo 的 SDF 接触搜索使用多个初始点寻找局部极小值，搜索起点和迭代次数是独立设置。依据：[MuJoCo SDF 扩展文档](https://mujoco.readthedocs.io/en/3.1.2/programming/extension.html)。本次具体数值来自本机 MuJoCo 3.9.0 实测，不由该旧版说明推定。

![接触漏检与搜索敏感性](03_接触漏检与搜索敏感性.png)

开发角点04和13在200个搜索起点时仍然零接触，1000个起点才检出。增加到200或1000个搜索起点不是已经验收的修复方案。需要对完整开发集复验接触覆盖、方向、载荷和动态性能，并测量计算成本；不能仅凭某一姿态重新出现接触就放行。

## 偏差拆分与开发范围

![偏差拆分与缩放对照](02_偏差拆分与缩放对照.png)

保持其他项不变时，去掉滚转或 Y 偏差可使原组合扫描不再触发 30 μm 门槛；仅保留双轴倾斜仍会超限。整体缩小到 75% 后，A/B 均扫描到目标深度，最大接触穿透约 18 μm。它们仍只是扫描对照，不能算成装配成功或控制能力。
''')
    lines.append(f'候选开发集使用 X/Y 各 ±25 μm、roll/pitch 各 ±0.5° 的16个角点及16个固定种子随机点（种子20260914）。{len(dev)} 条扫描均到达4 mm，最大接触穿透 {max(s["max_penetration_m"] for s in dev)*1e6:.3f} μm。')
    lines.append(f'但对该开发集在0.5、1、2、4 mm的 {len(audit)} 个姿态进行独立抽样核对后，发现 {len(failed)} 个姿态遗漏了至少一对存在超过1 μm实体重叠见证的针孔接触。因此这个候选范围也不能按原SDF配置宣布通过。1 μm仅用于避免将数值边界误差标作漏检，不是新的安全阈值。')
    lines.append('''
## 敏感性与夹持参考点

| 工况 | 对照 | 终止深度 mm | 最大接触穿透 μm |
|---|---|---:|---:|
''')
    for s in d['sensitivity']:
        label = '绕建议夹持点旋转' if s['pivot_local_m'] else (s['profile'] if s['profile']!='baseline' else f'空间步长 {s["step_m"]*1e6:g} μm')
        lines.append(f'| {s["case"]["name"]} | {label} | {s["final_depth_m"]*1000:.3f} | {s["max_penetration_m"]*1e6:.3f} |')
    lines.append('''
加密空间网格将A/B首次超限定位到0.176/0.258 mm，改变了阈值跨越的采样位置，没有消除几何干涉。这不是动态时间步收敛试验。low/high response同时改变多个等效接触参数，只是参数包对照，不能分离出单个摩擦或刚度参数的因果贡献。

夹持点对照保持名义夹持中心位置，再绕 `(0,0,-14.5 mm)` 旋转，因此改变了公头插合原点的实际位置，不能与“同一最终姿态只换坐标表达”混淆。该构造在扫描起点就已超限，提示动态 reset 必须先给出实际公头目标姿态，再计算夹持点位置并检查初始重叠。它不证明建议夹持位置不可行；当前夹持中心仍未经实测。

## 进入下一步的处理结论

1. 保留V1全部历史结果和压力工况；不改孔径、不放宽门槛来掩盖问题。
2. 优先解决SDF接触搜索覆盖：固定同姿态见证点，评估搜索设置、碰撞表示及几何边缘处理。回退polygon32可作独立对照，但也需要覆盖及精度核验。
3. 修复后至少复查原12工况、组合拆分工况、候选开发角点和随机点；同时核对接触方向与计算成本。需要增加开发区间内的深度采样，不能将现有离散点外推为连续域保证。
4. 可同步建立自由空间动力学、命名坐标系和接口。接触闭环要先通过上述覆盖复验；随后独立检查受力运动、停止回撤及动态时间步敏感性。
5. `闭环接口协议.md` 是下一阶段的接口设计，不代表环境、B1、安全守卫或SAC已经实现。

## 复现与证据

从项目工作树运行：

```powershell
& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.validation.diagnose_v1_applicability
& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.reporting.report_v1_applicability
& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m pytest tests/contact/test_applicability.py -q -p no:cacheprovider
```

主数据为 `diagnostic_results.json`：包含62条主扫描、10条扫描敏感性、几何见证、接触覆盖审计、同姿态搜索参数对照、源文件SHA-256及生效参数。两份用户提供的模型备忘录保存在 `inputs/`，其中建议和待验证项不当作实测事实。

分支基线为 `a289a277d69a445e7491aaf74af92b1201d4f5d9`；新增诊断代码以结果中的源码哈希追溯。正式输出均在本目录，与旧 `reports/` 分开。
''')
    (OUT/'V1开发适用性诊断报告.md').write_text('\n'.join(lines).rstrip()+'\n',encoding='utf-8',newline='\n')
    paths = [p for p in OUT.rglob('*') if p.is_file() and p.name != 'delivery_manifest.json']
    paths.extend([Path(__file__), ROOT/'tools/validation/diagnose_v1_applicability.py',
                  ROOT/'tests/contact/test_applicability.py'])
    manifest = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(paths)}
    (OUT/'delivery_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print('Chinese report and 3 figures generated')


if __name__ == '__main__':
    main()
