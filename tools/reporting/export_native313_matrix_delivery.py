"""Generate Chinese capability handoff from the completed fixed matrix assessment."""
import json
from tools.validation.run_native313_matrix import ROOT,OUT
from tools.validation.validate_training_readiness import sha,verify_hashes


def main():
    path=OUT/'report_v1/assessment.json';a=json.loads(path.read_text(encoding='utf-8'))
    verify_hashes(ROOT,a['source_sha256'])
    ready=a['interface_implementation_admitted']
    title='可进入残差接口实现；首次训练仍须接口验收' if ready else '训练准入仍有阻塞；暂不进入残差训练'
    text=f'''# 新版共同环境 B1/B2 七工况重评与训练准入

2026-09-23。**{title}。**

本轮在相同的独立 MuJoCo 3.13.0 native 环境完成14个固定开发回合，B1/B2各7个。未调控制参数，未改变几何、材料、质量、驱动和保护阈值，未训练SAC。正式3.9.0安装保留。

## 结果

| 方法 | 完整成功 | 实际停止后2s合格且末端仍稳 | 全回合严格安全与停止 | 候选有效记录 |
|---|---:|---:|---:|---:|
| B1 固定导纳 | {a['counts']['b1']['full_success']}/7 | {a['counts']['b1']['physical_stopped']}/7 | {a['counts']['b1']['strict_safe_stop']}/7 | {a['counts']['b1']['candidate_data_valid']}/7 |
| B2 搜索与恢复 | {a['counts']['b2']['full_success']}/7 | {a['counts']['b2']['physical_stopped']}/7 | {a['counts']['b2']['strict_safe_stop']}/7 | {a['counts']['b2']['candidate_data_valid']}/7 |

这是已经用于开发的七个工况，不是独立测试成功率。“候选有效记录”只表示本轮回合可用于接口设计依据，尚未提交任何SAC经验池；有效保护失败仍是失败，不能算安全成功。

| 工况 | 方法 | 原终止原因 | 最终类别 | 推进mm | XY误差μm | 峰值力mN | 最大穿透μm |
|---|---|---|---|---:|---:|---:|---:|
'''
    for case in [r['case'] for r in a['rows'] if r['policy']=='b1']:
        for policy in ('b1','b2'):
            row=next(r for r in a['rows'] if r['case']==case and r['policy']==policy)
            text+=f"| {case} | {policy.upper()} | {row['termination']} | {row['category']} | {row['advance_mm']:.3f} | {row['xy_error_um']:.2f} | {row['peak_force_mN']:.3f} | {row['peak_penetration_um']:.3f} |\n"
    text+='''
## 怎样读失败

FULL_SUCCESS：原回合成功，额外停止审计也通过。VALID_TASK_FAILURE：有效计算和停稳，但任务未完成。VALID_GUARD_FAILURE：触发保护并有效停止的失败，不能说全回合安全指标通过。STOP_NOT_QUALIFIED：停止验收未过，阻塞当前共同环境准入。INVALID_SIMULATION：数值/状态无效，不能作为正常学习经验。UNEXPLAINED_SAFETY_FAILURE：安全峰值未过且缺少对应保护证据，需要核查。

原回合动作预算均为20s，原最终判定观察为1s，保留原先提前结束规则；额外停止审计不重新给失败回合成功机会。停止计时按实际STOPPING事件，不按可能更晚的恢复失败决定时间。原首版audit和物理日志保留，最终报告独立重算；见[计时与归档说明](停止计时与异常归档补充.md)。

## 准入结论与下一步

'''
    if ready:
        text+='''本矩阵未发现上述共享数值/停止阻塞，可进入普通四维残差SAC接口实现。保留B1为简单对照、原B2为搜索恢复基线；不再追加传统控制参数扫描。该结论不等于连续训练分布已完整验证，更不等于已经开始训练。

下一能力统一完成reset/step、四维残差叠加、共享守卫、观测与奖励、无效经验隔离、保存加载和固定评价。先验证零残差逐周期复现新版B2，以及小范围XY训练分布初始化；通过后才首次短训。联合偏差扩展和独立测试仍在后续阶段。
'''
    else:
        text+='当前阻塞记录：\n\n'
        for b in a['blockers']:text+=f"- {b['policy'].upper()} / {b['case']}：{b['category']}。\n"
        text+='\n不得以删掉困难工况或缩小训练范围绕开共享问题。本轮不扫描参数、不进入SAC；下一项应针对这些具体记录定位停止/数值阻塞。训练合同是后续实现依据，当前不构成许可。\n'
    text+='''
## 文件与复现

- [机器可读结论](report_v1/assessment.json)：完整比较、实际停止计时和准入理由。
- [七工况对比图](report_v1/01_七工况方法对照.png)、[预定X/Y真实轨迹](report_v1/02_代表工况真实轨迹.png)、[月报讲解](月报讲解.md)。
- [环境与基线冻结记录](冻结依据.json)、[训练合同v2](训练合同_v2.md)、[数据划分引用](数据划分引用.json)。原32验证/64独立测试清单保留，本轮没有运行这些测试集。
- `b1_v1/`、`b2_v1/`：每工况原回合original.json.gz、stop_extension.json.gz、首版audit.json和源码快照；完整保留失败。

代码关系：模型生成→native候选环境→原B1或B2控制器→原回合运行器→追加停止采样→独立审计/报告。新增入口不改变控制器内部行为。

在VS Code打开工作目录 `D:\\dsub9项目计划\\first_stage_sim\\.worktrees\\dsub9-v1-contact-validation`。复现使用修正版v2和新的tag：

```powershell
& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.validation.run_native313_matrix_v2 --policy b1 --tag b1_reproduce_01 --package-path tmp/mujoco_3_13_probe
& 'D:\\KEYANRUJIAN\\python.exe' -X utf8 -B -m tools.validation.run_native313_matrix_v2 --policy b2 --tag b2_reproduce_01 --package-path tmp/mujoco_3_13_probe
```

要求使用已验收的同一路径与DLL；文件夹已经存在则拒绝覆盖。v2仅修正真实停止计时和NaN/Inf证据归档。本轮14回合来自保留的首版入口，最终停止判定已按v2语义独立复核；没有为v2额外重复14回合。修正版有边界测试，不能把它说成已做第二轮完整矩阵验证。

图由真实记录生成；没有制作或验收新的交互回放窗口。原SolidWorks/SDF资产、正式Python环境、VS Code设置和历史实验均保留。
'''
    (OUT/'README.md').write_text(text,encoding='utf-8')
    frozen=dict(status=a['status'],environment=a['environment'],baseline_roles={'b1':'simple_fixed_admittance_comparator','b2':'original_fixed_search_recovery_residual_candidate'},
                interface_implementation_admitted=ready,training_admitted=False,
                evaluation_budget=dict(action_time_s=20,original_settle_time_s=1,safety_stop_observation_s=2),
                assessment_sha256=sha(path),source_sha256=a['source_sha256'])
    (OUT/'冻结依据.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    monthly=f'''# 月报：共同新版环境下的传统方法对照

本轮交付是完整14回合方法对照，不是单个参数调整。两种控制器共用几何、物理和安全条件。

完整成功：B1 {a['counts']['b1']['full_success']}/7，B2 {a['counts']['b2']['full_success']}/7；停止合格：B1 {a['counts']['b1']['physical_stopped']}/7，B2 {a['counts']['b2']['physical_stopped']}/7。这是固定开发案例计数，不能作为论文泛化成功率。

建议展示[七工况图](report_v1/01_七工况方法对照.png)说明传统方法的实际能力和失败，再用[X/Y真实轨迹](report_v1/02_代表工况真实轨迹.png)解释搜索对推进的作用及停止检查。深度到位不等于完整成功；保护失败与数值异常必须分开。

当前结论：{title}。没有学习策略、学习曲线或SAC改进成功率。本轮32验证/64独立测试均未使用。

复核中补严了实际停止计时，并保留首次入口记录；没有扩大速度、安全或成功阈值。后续以README的准入结论为准。
'''
    (OUT/'月报讲解.md').write_text(monthly,encoding='utf-8')
    print(title,flush=True)


if __name__=='__main__':main()
