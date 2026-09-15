"""Chinese report and scientific figures for the collision coverage experiment."""
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

from tools.model.contact_development import OUTPUT_DIR
from tools.validation.run_contact_cases import ROOT
from tools.visualization.font_support import find_chinese_font


def main():
    result = json.loads((OUTPUT_DIR/'coverage_results.json').read_text(encoding='utf-8'))
    selected_path = OUTPUT_DIR/result['selected_model']
    if hashlib.sha256(selected_path.read_bytes()).hexdigest() != result['model_sha256']:
        raise RuntimeError('Result/model mismatch: rerun coverage validation before reporting')
    if not result.get('current_input_sha256'):
        raise RuntimeError('Missing current input fingerprints: rerun coverage validation')
    for path, expected in result['current_input_sha256'].items():
        if hashlib.sha256((ROOT/path).read_bytes()).hexdigest() != expected:
            raise RuntimeError(f'Stale validation input: {path}')
    timing = json.loads((OUTPUT_DIR/'timing.json').read_text(encoding='utf-8'))
    font_manager.fontManager.addfont(str(find_chinese_font()))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(find_chinese_font())).get_name(),
                         'axes.unicode_minus':False, 'font.size':11, 'figure.dpi':150})
    variants = result['variants']; labels = list(variants)
    fig, ax = plt.subplots(figsize=(11, 4.5), layout='constrained')
    missing = [sum(bool(r['missing_pins']) and r['status']=='OK' for r in variants[k]['rows']) for k in labels]
    errors = [variants[k]['summary']['simulation_errors'] for k in labels]
    ax.bar(labels, missing, label='成功计算但漏接触的姿态', color='#d97846')
    ax.bar(labels, errors, bottom=missing, label='仿真容量错误', color='#923c51')
    for i, (a,b) in enumerate(zip(missing, errors)):
        ax.text(i,a+b+.3,str(a+b),ha='center')
    ax.set(ylabel='失败姿态数 / 140', title='同一组重点姿态：凸分块补齐已发现的接触遗漏', ylim=(0,21))
    ax.tick_params(axis='x',labelrotation=20); ax.legend()
    fig.savefig(OUTPUT_DIR/'01_重点姿态接触覆盖.png'); plt.close(fig)

    a = variants['convex128']['rows']; b = variants['convex256']['rows']
    force128 = np.array([np.linalg.norm(r['wrench'][:3]) for r in a])
    force256 = np.array([np.linalg.norm(r['wrench'][:3]) for r in b])
    diff = np.array([np.linalg.norm(np.array(x['wrench'][:3])-np.array(y['wrench'][:3])) for x,y in zip(a,b)])
    active = np.maximum(force128,force256) > .001
    relative = diff[active]/np.maximum(force128,force256)[active]
    sensitivity = {'poses':len(a), 'active_force_threshold_N':.001,
                   'active_poses':int(active.sum()), 'maximum_force_vector_difference_N':float(diff.max()),
                   'relative_force_difference_median':float(np.median(relative)),
                   'relative_force_difference_max':float(relative.max()),
                   'relative_denominator':'max(norm(F128), norm(F256)); poses above 0.001 N only'}
    (OUTPUT_DIR/'force_resolution_sensitivity.json').write_text(json.dumps(sensitivity,indent=2)+'\n',encoding='utf-8',newline='\n')
    fig, axes = plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    axes[0].scatter(force128,force256,s=15,alpha=.65)
    limit=max(force128.max(),force256.max())*1.05
    axes[0].plot([0,limit],[0,limit],'--',color='gray')
    axes[0].set(xlabel='128段合力模长 / N',ylabel='256段合力模长 / N', title='分辨率敏感性：同姿态静态求解')
    axes[1].plot([r['contact_count'] for r in a], label='128段')
    axes[1].plot([r['contact_count'] for r in b], label='256段')
    axes[1].set(xlabel='重点姿态序号',ylabel='接触点数',title='分块增加会改变接触点数量'); axes[1].legend()
    fig.savefig(OUTPUT_DIR/'02_分辨率与接触力.png');plt.close(fig)

    fig, axes = plt.subplots(2,1,figsize=(10,7),layout='constrained',sharex=True)
    for name in ('aligned','roll_pos_1.5deg','combined_a','combined_b'):
        label={'aligned':'同轴插入','roll_pos_1.5deg':'横滚 +1.5°','combined_a':'组合误差 A','combined_b':'组合误差 B'}[name]
        rows=[r for r in result['dense_rows'] if r['case']==name]
        z=np.array([r['depth_m'] for r in rows])*1e3
        axes[0].plot(z,[r['max_penetration_m']*1e6 for r in rows],label=label)
        axes[1].plot(z,[np.linalg.norm(r['wrench'][:3]) for r in rows],label=label)
    axes[0].axhline(30,color='gray',linestyle='--',label='原V1诊断阈值30μm')
    axes[0].set(ylabel='接触算法最大穿透 / μm',title='强制姿态扫描：超过阈值的区段仅用于检测压力测试')
    axes[1].set(xlabel='从初始位置推进的深度 / mm',ylabel='求解合力模长 / N')
    axes[0].legend(ncol=2);axes[1].legend(ncol=2)
    fig.savefig(OUTPUT_DIR/'03_全深度接触诊断.png');plt.close(fig)

    dense=result['dense_summary']
    holdout=[r for r in result['dense_rows'] if r['case'].startswith('coverage_holdout_')]
    holdout_contact=sum(bool(r['contact_count']) for r in holdout)
    table='\n'.join(f"| {k} | {v['summary']['poses']} | {sum(bool(r['missing_pins']) and r['status']=='OK' for r in v['rows'])} | {v['summary']['simulation_errors']} |" for k,v in variants.items())
    text=f'''# 接触覆盖修复：开发模型验证记录

结论：**{result['verdict']}**。此结论只评价本次离散采样中的接触覆盖，尚未验证动态控制稳定性和实物力学精度。

## 为什么先做这一步

原解析SDF在部分明确发生几何交叠的针孔姿态中不生成接触，控制器因而可能看不到本应存在的碰撞。直接开始导纳或强化学习会把检测缺陷混入控制结果。

本次保留原模型和历史报告，新增独立的128段凸分块孔模型。圆孔由内切面包围的多边形逼近：主孔最大径向放大量{result['radial_error_m']['128']['bore']*1e6:.6f}μm，入口最大{result['radial_error_m']['128']['entry']*1e6:.6f}μm；外轮廓也有相应离散误差。入口仍为阶梯沉孔，没有改成倒角。针、D形外壳、质量、摩擦和接触响应参数沿用原模型；凸碰撞距离容差设为1nm，接触margin保持0。

这是一条替代碰撞建模路径，不能表述为“解析SDF算法已修复”。增大SDF初始搜索点从40到1000虽然减少部分遗漏，但出现容量错误，未通过本次门槛。

## 结果

| 模型 | 重点姿态数 | 成功计算但漏接触 | 仿真错误 |
|---|---:|---:|---:|
{table}

128段模型进一步检查了{len(result['dense_cases'])}个工况、{dense['poses']}个姿态：漏接触姿态{dense['missing_poses']}个，仿真错误{dense['simulation_errors']}个，非有限数值{dense['nonfinite_poses']}个。其中{dense['poses_with_witness_overlap']}个姿态具有超过1μm的独立交叠见证，{dense['poses_with_contacts']}个姿态产生接触，不能将全部姿态数当作有效碰撞样本数。工况包括原工况、组合误差拆解、±25μm/±0.5°开发域角点和随机点，以及额外32个固定种子20260915随机点。额外随机点对应的{len(holdout)}个姿态中有{holdout_contact}个产生接触；若没有接触，仅表示检查了自由间隙内姿态，对碰撞检出能力不增加证据。全程深度间隔50μm，入口前0.5mm加密到10μm。分离工况只检查其原始位置。

重点140姿态复用上一版高密度表面见证；新增密集扫描每根针使用48个圆周方向、33个轴向位置及两端面各9层半径。将针表面点代入独立的解析实体距离函数，交叠超过1μm时必须出现对应针孔接触。1μm只是检验报告门槛，不是实物损伤阈值。采样发现交叠可证明发生了交叠；没有发现不能证明整个连续空间无交叠。本次只检查对应针孔，未认证整个D形外壳的几何间隙。

128段与256段在140个重点姿态均检出预期接触，但接触点数不同。对至少一模型合力超过0.001N的{sensitivity['active_poses']}个姿态，合力向量差除以两者较大模长，中位数为{sensitivity['relative_force_difference_median']:.1%}、最大为{sensitivity['relative_force_difference_max']:.1%}；最大绝对合力向量差{sensitivity['maximum_force_vector_difference_N']:.6g}N。这些是未标定参数下的静态求解结果，不能当作实测插入力，也不能凭接触覆盖通过宣称力已收敛。

所有扫描直接规定位姿并清零速度。超出原30μm阈值后继续推进仅用于暴露漏检，绝不是允许机器人继续插入的策略。“最大穿透”指接触算法返回的最负距离幅值；独立几何见证是另一种量，二者不应混用。

## 计算成本与历史保留

128段的140姿态检查耗时{timing['convex128']['seconds_140_pose_checks']:.3f}s；密集扫描（含独立几何见证）耗时{timing['dense_scan_seconds_including_witness']:.1f}s。计时包含数据分配、接触力提取，不含编译；并发工作、CPU负载会影响结果。这不是GPU训练吞吐或动态仿真速度承诺。

运行前后比对{len(result['historical_source_sha256'])}项历史输入SHA-256，全部保持一致。导出的XML已实际重新加载并用于验证，依赖同一项目原始assets和models目录，不能单独复制XML当成完整模型。

## 紧接着做什么

1. 使用本开发模型建立动态笛卡尔执行器：明确位置与速度限制、控制周期、观测坐标系，以及力矩从配合原点到工具参考点的转换。先做无接触跟踪，再做低速单方向接触与撤退。
2. 验证接触力方向、能量与数值稳定性，并对128/256段、时间步和接触参数作动态敏感性检查。发生超限、非有限状态或异常速度时终止该回合，记录失败原因。
3. 通过上述检查后实现B1固定导纳，再做B2搜索恢复，随后才进入残差强化学习。用户提供的训练设备为4060和5070Ti，目前尚无吞吐和显存需求实测，不能据此承诺训练速度或论文录用。

现在无需等待真实夹持位置便可进行简化刚性夹持的数值开发。实际夹持位置、工具长度、负载惯量、传感器安装方向与标定、夹爪柔顺性需要在实机迁移前测定；当前暂定工具点不能写成已经标定。也不应把未来CR5整体模型的接入等同于完成实机验证。

## 复现

在项目根目录使用已安装MuJoCo3.9.0的Python依次运行：

```text
python -m tools.validation.repair_contact_coverage
python -m tools.reporting.report_contact_coverage_repair
```

测试结果和提交状态见“验证记录.md”。原始数据见coverage_results.json，单独计时见timing.json，分辨率指标见force_resolution_sensitivity.json。
'''
    (OUTPUT_DIR/'接触覆盖修复报告.md').write_text(text,encoding='utf-8',newline='\n')
    (OUTPUT_DIR/'README.md').write_text('''# 接触覆盖修复开发包

先看[接触覆盖修复报告](接触覆盖修复报告.md)，再看三张中文图。

- 01_重点姿态接触覆盖.png：原SDF与各凸分块模型对比。
- 02_分辨率与接触力.png：接触点数和合力对分块数的敏感性。
- 03_全深度接触诊断.png：强制插入姿态的穿透与合力曲线。
- dsub9_convex128_contact_dev_v1.xml：独立开发模型，依赖原项目资源。
- coverage_results.json：可复查的逐姿态结果及历史输入指纹。

本包通过与否只涉及接触覆盖；动态控制、实物力学标定、论文实验仍需后续工作。
''',encoding='utf-8',newline='\n')
    manifest_paths = sorted(p for p in OUTPUT_DIR.iterdir() if p.is_file() and p.name!='delivery_manifest.json')
    manifest_paths += [ROOT/'tools/model/contact_development.py', ROOT/'tools/validation/repair_contact_coverage.py',
                       ROOT/'tools/reporting/report_contact_coverage_repair.py', ROOT/'tests/contact/test_contact_development.py']
    manifest = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in manifest_paths}
    (OUTPUT_DIR/'delivery_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps(sensitivity,ensure_ascii=False))


if __name__=='__main__':
    main()
