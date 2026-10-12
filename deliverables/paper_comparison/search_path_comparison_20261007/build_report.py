"""Create static scientific figures and source-grounded reports, no rollout."""
from pathlib import Path
import csv,json,math,os
OUT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(OUT/'plot_cache'))
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    font=Path('C:/Windows/Fonts/msyh.ttc')
    if font.exists():font_manager.fontManager.addfont(str(font));plt.rcParams['font.family']=font_manager.FontProperties(fname=str(font)).get_name()
    plt.rcParams.update({'axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    d=json.loads((OUT/'diagnosis.json').read_text(encoding='utf8'))
    data=list(csv.DictReader((OUT/'search_cycles.csv').open(encoding='utf8')))
    series={}
    colors={'F50':'#377eb8','F12.5':'#8a60ad','G50':'#d04b3a','S50':'#23966f'}
    for r in d['records']:
        for k,seg in enumerate(r['segments'],1):
            rows=[x for x in data if x['method']==r['method'] and int(x['search'])==k]
            series[(r['method'],k)]={key:np.asarray([float(x[key]) for x in rows]) for key in rows[0] if key not in ('method','search')}
    fig,axs=plt.subplots(2,2,figsize=(13,9.2),constrained_layout=True)
    for (name,k),s in series.items():
        style='--' if k==2 else '-';label=f'{name} 搜索{k}';kw=dict(color=colors[name],linestyle=style,label=label,lw=1.6)
        seg=next(r for r in d['records'] if r['method']==name)['segments'][k-1]
        actual=seg['exit']['actual_position_um'];elapsed=np.r_[s['elapsed_s'],seg['duration_s']]
        x=np.r_[s['actual_x'],actual[0]];y=np.r_[s['actual_y'],actual[1]]
        rx=np.r_[s['reference_local_x'],s['reference_local_x'][-1]+s['command_xy_x'][-1]*s['dt'][-1]]
        ry=np.r_[s['reference_local_y'],s['reference_local_y'][-1]+s['command_xy_y'][-1]*s['dt'][-1]]
        axs[0,0].plot(x,y,**kw);axs[0,0].scatter(x[0],y[0],s=18,color=colors[name]);axs[0,0].scatter(x[-1],y[-1],marker='x',s=24,color=colors[name])
        axs[0,1].plot(rx,ry,**kw)
        axs[1,0].plot(elapsed,np.r_[s['net_depth_um'],seg['end_net_depth_beyond_frozen_peak_um']],**kw)
        axs[1,1].plot(elapsed,np.hypot(rx,ry),**kw)
    a=np.linspace(0,2*math.pi,500)
    for radius,style,label in [(80,':','80 μm附加精度'),(100,'--','100 μm主孔径向间隙示意')]:
        axs[0,0].plot(radius*np.cos(a),radius*np.sin(a),style,color='#aaa',lw=.9,label=label)
    axs[0,0].set(title='真实XY路径（孔中心坐标，仅SEARCH）',xlabel='X / μm',ylabel='Y / μm',aspect='equal')
    axs[0,1].plot(120*np.cos(a),120*np.sin(a),':',color='#555',label='120 μm参考圆')
    axs[0,1].set(title='驱动参考路径（相对各段搜索原点）',xlabel='参考X / μm',ylabel='参考Y / μm',aspect='equal')
    axs[1,0].axhline(100,color='#555',ls=':',label='100 μm净推进退出门')
    axs[1,0].axhline(0,color='#aaa',ls=':',lw=.7)
    axs[1,0].set(title='净深度：超过搜索前冻结历史峰值',xlabel='段内时间 / s',ylabel='净深度 / μm')
    axs[1,1].axhline(120,color='#555',ls=':',label='120 μm参考边界')
    axs[1,1].set(title='参考半径与耗尽位置',xlabel='段内时间 / s',ylabel='参考半径 / μm')
    for ax in axs.flat:ax.grid(alpha=.18);ax.legend(fontsize=8,loc='best')
    fig.suptitle('PC-10：四份既有负Y开发档案，五段搜索；新增物理/推理/训练均0',fontsize=14)
    fig.savefig(OUT/'search_paths.png',dpi=170);fig.savefig(OUT/'search_paths.svg');plt.close(fig)
    fig,axs=plt.subplots(4,2,figsize=(13,11),sharex=True,constrained_layout=True)
    for j,axis in enumerate(('x','y','roll','pitch')):
        for (name,k),s in series.items():
            if k==2:continue
            kw=dict(color=colors[name],lw=1.2,label=name)
            axs[j,0].plot(s['elapsed_s'],s['action_'+axis],**kw)
            key='command_xy_'+axis if j<2 else 'command_'+axis+'_mrad_s'
            axs[j,1].plot(s['elapsed_s'],s[key],**kw)
        axs[j,0].set(ylabel=f'{axis} 归一化请求',ylim=(-1.05,1.05))
        axs[j,1].set(ylabel=f'{axis} 总命令 / '+('μm/s' if j<2 else 'mrad/s'))
        for ax in axs[j]:ax.grid(alpha=.18)
    axs[0,0].set_title('第一段四维实际部署请求（F12.5已乘0.25）');axs[0,1].set_title('限幅/过滤后真实执行总命令')
    axs[0,0].legend(ncol=4,fontsize=9);axs[3,0].set_xlabel('段内时间 / s');axs[3,1].set_xlabel('段内时间 / s')
    fig.suptitle('同一共同控制版本；G/F为F2000演员，S为匹配训练S2000演员',fontsize=14)
    fig.savefig(OUT/'actions_commands.png',dpi=170);fig.savefig(OUT/'actions_commands.svg');plt.close(fig)
    table=['| 方法/段 | SEARCH区间s | 真实XY净位移μm | 真实/参考路径μm | 最大净深度μm | 退出 |',
           '|---|---|---|---|---:|---|']
    for r in d['records']:
        for k,s in enumerate(r['segments'],1):
            xy=s['actual_xy_net_um'];reason=s['exit_event']['reason']
            table.append(f"| {r['method']}/{k} | {s['start_time_s']:.3f}–{s['end_time_s']:.3f} | ({xy[0]:+.2f}, {xy[1]:+.2f}) | {s['actual_xy_path_um']:.2f}/{s['reference_xy_path_um']:.2f} | {s['max_net_depth_beyond_frozen_peak_um']:.3f} | {reason} |")
    report='''# PC-10 离线搜索路径对照

**结论：停止直接移植F2000演员到G50门控的部署路线；保留已有匹配训练S50及合理小固定边界的公平对照方向。** 确认的直接失败链是“真实针未超过旧峰值 → 驱动参考到达120μm圆 → 两次正常搜索结束 → TASK_FAILURE”。本轮没有定位需要修复的动作执行/参考积分错误；训练与权限不匹配仅为有支持的假设，没有证明G不可学或唯一根因。

本轮只读F50、F12.5、G50和匹配训练S50的既有负Y150μm开发档案：4份、28,465控制周期，其中5段SEARCH、15,626周期。新增动态/物理子步/网络推理/更新/发布均0，累计动态208；旧预算关闭、自动跟踪PAUSED、新训练准入无。S的10.760s旧成功仅是本轮归因参考，不能增加成功样本。

## 分段证据

'''+ '\n'.join(table)+'''

实际XY使用原始物理位置；参考路径使用驱动参考。总命令积分是参考运动的核验，不能替换为残差造成的物理位移。SEARCH按动作前137维观测解码，不用滞后一周期的trace阶段，也不把停止尾段混入搜索。

![真实、参考与净深度](search_paths.png)

## G为何耗尽

G第一段在8.996s、θ=18.655666rad结束；当前参考半径119.999999μm，下一**共同零残差**命令预测120.005279μm，超界5.279286nm。第二段在17.000s、θ=18.579837rad结束；下一预测120.000046μm，超界0.046079nm。两者均超过120μm+1pm判据，螺旋最终相位18.849556rad尚未达到，段内8s分别尚余0.530/0.590s。依据原始相位、参考、上周期命令独立复算了割线前馈、5/s跟踪、速度和加速度限幅，逐值匹配原事件；属于当前冻结规则的正常搜索结束，没有参考运行故障。它揭示边界规则会结束本路径，不证明此规则是应改的实现错误。

G第一段最大净深度−6.140μm，第二段−6.355μm，均未回到搜索前冻结峰值，更未跨越其后100μm的退出门。第二段实际向前251.097μm主要是在回收回撤距离，结束仍低于旧峰值17.953μm；不能把这段推进当作插入进展。两段最小中心XY误差98.527/106.537μm、末值154.323/154.599μm。参考走了约1100/1087μm，真实路径约260/383μm，参考已转圈不等于针在孔内按参考转圈。

15个参考过滤周期（第一段1、第二段14）均留档。四档案16,910个有权限周期的预测与真实执行命令一致；15,626个SEARCH周期参考积分最大误差见diagnosis.json。恢复第二段首周期4795的参考Z在prepare内按真实位姿重置4.043μm，有原B2_RECOVERY_RESUMED事件；专门复核，未放宽误差门，不把正常重置误报为命令丢失。

## S为何能成功，以及不能推出什么

S第一段6.864s在净深度100.021μm处退出，然后完成10.760s功能成功。F50和F12.5分别在6.326/7.760s跨过同一100μm门，亦成功。S搜索结束中心XY约102.080μm；完整功能成功依据深度、实际分层几何和停稳，不等于附加80μm精度成功。

G/S第一段入口真实位置差仅(0.004114,0.009406,0.000081)μm，但驱动参考、接触历史及演员不同，原始trace从第176行起已不同。F50/F12.5进入SEARCH之前已有不同的XY侧移，不能把F/G后续差异仅归因于搜索权限。

第一段部署四维请求的时间均值G为(0.1953,0.2974,−0.1610,−0.1283)，S为(−0.0122,0.7210,0.3440,−0.4267)。S的Y纠偏请求和roll/pitch方向组合明显不同；G仍保留F在INSERT+SEARCH训练下的响应。四维总命令、参考方向和真实路径在逐周期CSV与下图分列。角命令积分也是描述量，不能独立定位九针的哪一接触导致成功。

![四维请求与总命令](actions_commands.png)

G请求相对当前参考径向分量的时间均值为−5.374/−7.106μm/s，两段均以内向为主；因此“持续向外残差把参考推到边界”也不受数据支持。到边界是前馈/跟踪/历史请求共同形成的完整路径结果，不能只凭总积分或均值定唯一因果。

**证据等级：** 已确认命令执行、参考积分、正常边界退出、净深度不足及S的成功路径；支持但未隔离演员与新权限/状态分布不匹配；没有支持门控抖动、残差未执行、参考崩溃或全部SAC插入无效。单点单训练种子、不同演员与前段历史，不构成受控学习因果或论文优势证据。

## 使用与验收

新目录`analyze.py`只读统计；`test_analysis.py`为6项手算专项，关联PC-08纯档案检查21项，共27项；不运行全历史物理/学习套件。`search_cycles.csv`含所有15,626搜索周期；`alignment.csv`按整数秒及共同θ=0,2,…,18rad取最近已存周期（不插值、不跑策略、不选阈值）。`diagnosis.json`包含完整入口/出口位姿、力、速度、四维均值、请求积分、执行命令积分与重算事件。

生产1057输入、PC-06/07/08/09全部658封存文件已逐项核验保持。冻结目录不重跑分析；纯检查可以再读，若要重新生成可在完整副本中进行。本次验收限于离线证据交付，完整B.2/C、合理边界公平重训、多种子及新的最终测试均未验收。

[一页路线决定](路线决定.md)、[原始统计](diagnosis.json)、[全部搜索周期](search_cycles.csv)、[对齐表](alignment.csv)、[计划](../../../docs/superpowers/plans/2026-10-07-search-path-comparison.md)。
'''
    # Count is data-driven; metadata differs between PC-06 and PC-09.
    report=report.replace('16,910个有权限周期',f"{d['active_command_prediction_checks']:,}个有权限周期")
    (OUT/'结果说明.md').write_text(report,encoding='utf8')
    decision='''# PC-10 一页路线决定（2026-10-07）

**决定：停止G50直接套用F2000演员的部署路线，本轮不申请G训练。保留已匹配训练的S50作为阶段约束参照，以及合理小固定边界的公平对照方向。**

依据是四份同共同版本负Y档案：G两段最大净深度−6.140/−6.355μm，未超过旧峰值；参考抵达120μm圆后，下一共同命令按原规则耗尽，最终普通任务失败。S在第一段超过峰值100.021μm并完成旧10.760s成功；F50/F12.5同样完成。G/S入口真实位置仅约0.010μm差异，但S的Y与角响应不同，演员、驱动参考和接触历史存在混杂。

16,910个启用周期命令核对、15,626个搜索周期参考积分与两次边界公式复算没有发现需要修复的执行错误。G的平均径向请求以内向为主，也不支持“持续外推导致耗尽”。当前证据支持新权限与F演员训练分布不匹配的假设，不能证明它是唯一成因，更不能保证同权限G重训会成功。S的成功不证明S整体优于F；PC-07该整体继续信号仍未满足。

**不推进的项：** 不扫描5mN门槛、不加迟滞、不放大参考圆、不扩观测/网络/critic、不直接复制F权重补训G、不重开PC-09或任何旧预算。缺少这些动作的具体收益依据。

**下一项的具体范围：** 仅准备S50与合理小固定边界的公平对照登记草案。F12.5当前是F演员输出乘0.25的部署敏感性，不能冒称小边界匹配重训对照；若未来训练，须从共同零更新起点、各自匹配权限/尺度数据、相同登记预算和开发分布开始，成本分列，并先通过新来源/权限/保存恢复准入。最终测试需另冻结未消费位置，四个已消费点不能再次称未见。

本决定没有新预算、训练资格或启动指令。本轮新增物理/推理/训练/发布0，累计208，旧预算关闭、自动跟踪PAUSED；完整B.2/C仍待验收。阶段完成后暂停汇报。

[五段搜索与四维证据](结果说明.md)、[逐周期数据](search_cycles.csv)、[原始复算](diagnosis.json)。
'''
    decision=decision.replace('16,910个启用周期',f"{d['active_command_prediction_checks']:,}个启用周期")
    (OUT/'路线决定.md').write_text(decision,encoding='utf8')
    figure_data=dict(source='diagnosis.json + search_cycles.csv',source_rows=d['search_cycles'],
        series={f'{k[0]}_{k[1]}':{name:v.tolist() for name,v in values.items()} for k,values in series.items()},
        caution='100um XY circle is a main-hole clearance illustration, not the tilted multi-pin functional referee')
    (OUT/'figure_data.json').write_text(json.dumps(figure_data,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf8')
    print('Two scientific figures and reports built from existing archives')

if __name__=='__main__':main()
