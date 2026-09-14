# V1 开发适用性诊断交付

日期 2026年9月14日

当前结论：已确认组合姿态下的针孔几何干涉，并发现原SDF配置的接触漏检。**当前配置不能直接进入依赖接触反馈的B1/SAC开发。** 本轮完成诊断和处理结论；接触覆盖修复尚未完成，闭环接口为设计稿。

## 阅读顺序

1. [V1开发适用性诊断报告](V1开发适用性诊断报告.md)：原因、证据、限制及下一步。
2. [接触漏检与搜索敏感性](03_接触漏检与搜索敏感性.png)：直观看到几何相交但原配置零接触。
3. [针孔几何重叠定位](01_针孔几何重叠定位.png)和[偏差拆分与缩放对照](02_偏差拆分与缩放对照.png)。
4. [闭环接口协议](闭环接口协议.md)：坐标、观测、四维速度残差、终止、停止恢复和日志。
5. [结构化原始结果](diagnostic_results.json)：全部扫描、逐接触事件和独立几何见证。

## 本轮实际完成

- 62条主扫描：原12工况、18条组合拆分/缩放对照、16个开发角点及16个固定种子随机点。
- 10条扫描敏感性：两种更细空间网格、两种等效接触参数包及建议夹持点旋转对照，各2个工况。
- 140个相同姿态的独立几何/接触覆盖检查，其中17个存在对应针孔接触漏检；候选开发集为15/128。它们是离散姿态计数，不是装配失败率。
- 30个同姿态SDF搜索设置对照；不是动态时间步验证，也没有将较高搜索量宣布为修复。
- 3张中文图、技术报告、接口设计、模型备忘录输入副本与源文件指纹。

## 文件与单位

JSON长度用m、角度rad、力N、力矩N·m；图中另按mm/μm换算。`depth_m`为规定扫描深度；`SCAN_TARGET_REACHED`只表示扫到目标，separated到0mm也属于此标记，不代表装配成功。

接触事件的`position_world_m`是接触点位置，`normal_geom1_to_geom2_world`从第一几何指向第二几何；`wrench_on_male_about_mate_world`始终表示作用在公头、关于公头插合原点、以世界坐标表达的力/力矩。几何见证的`point_male_local_m`属于公头插合坐标，不是相对单根针中心。

`source_sha256`覆盖实际模型、includes、网格资产、插件、接触参数生成代码、运行器、诊断代码和模型备忘录；`delivery_manifest.json`记录本包文件和新增源码的哈希，不包含它自身。结果记录基线Git提交及新增源码哈希，不把祖先提交写成已包含本轮新增文件。

报告生成前检查源指纹，防止使用旧数据和新几何混合绘图。重新生成诊断后，再生成报告和本包清单。历史`reports/final_file_manifest.txt`保持原样；本轮新增文件由独立清单管理。

## 运行入口

在本工作树根目录（包含models、tools和reports的目录）运行：

```powershell
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.validation.diagnose_v1_applicability
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m tools.reporting.report_v1_applicability
& 'D:\KEYANRUJIAN\python.exe' -X utf8 -B -m pytest tests/contact/test_applicability.py tests/contact/test_contact_cases.py tests/contact/test_contact_traces.py tests/sdf/test_hole_reference.py -q -p no:cacheprovider
```

诊断输入使用本工作树的V1，输出仅允许写入`deliverables/v1_applicability/`内的JSON。模型和原始报告不会被改写。换机需要MuJoCo 3.9.0及对应Windows SDF插件；插件DLL属于构建产物，不由本交付重新编译或保证随Git仓库分发。

## 下一项工作的具体范围

优先修复或替换不可靠的SDF接触搜索设置，并用本包的漏检姿态作回归集。固定公头实际姿态和几何，比较搜索点数、迭代次数及必要的碰撞表示改进；以独立几何见证、检出的针孔配对、载荷方向、稳定性和计算成本共同验收。不能把全部接触数越多视为越正确，也不能只让原组合工况到达4mm来验收。

修复后复查整个开发集及更多深度，才进入简化夹持执行器的接触动态开发；自由空间接口和坐标工作可以并行。CR5、标准二指夹爪和六维力传感器保留为后续适配方向，当前未仿真真实夹持滑移或机械臂运动学。
