"""Standalone plots from retained results; no inference or physical rerun."""
import gzip,json,math,os
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=HERE/'result_analysis'
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
font=Path('C:/Windows/Fonts/msyh.ttc')
if font.exists():plt.rcParams['font.family']=FontProperties(fname=str(font)).get_name()
plt.rcParams['axes.unicode_minus']=False
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
a=read(OUT/'assessment.json');rows=a['rows'];byid={r['id']:r for r in rows}
import validation_contract as C
stages=('initial','C_online','C_final','C_restored','A_online','A_final');labels=('零更新初始','C在线','C固定最终','C恢复复验','A在线','A固定最终')
colors=dict(success='#237a55',task='#df9b2d',guard='#bd3d3d',unused='#e2e5e8')
colors['fault']='#725c94'
from fault_evidence import display_status
fig,axes=plt.subplots(2,2,figsize=(13,8),layout='constrained')
for j,stage in enumerate(stages):
    for i,case in enumerate(C.cases()):
        identity=stage+'_'+case['name'];r=byid.get(identity);state=display_status(identity,byid,a['failed_attempts'])
        color=colors['fault' if state=='runtime_fault' else 'unused'] if r is None else colors['guard' if r['guard_hit'] else 'success' if r['success'] else 'task']
        axes[0,0].add_patch(plt.Rectangle((i-.45,j-.4),.9,.8,facecolor=color,edgecolor='white'))
        axes[0,0].text(i,j,'已启动故障' if state=='runtime_fault' else '未执行' if r is None else '保护失败' if r['guard_hit'] else '成功' if r['success'] else '任务失败',ha='center',va='center',fontsize=8,color='#333' if state=='unexecuted' else 'white')
axes[0,0].set(xlim=(-.6,3.6),ylim=(5.6,-.6),xticks=range(4),xticklabels=['+X','−X','+Y','−Y'],yticks=range(6),yticklabels=labels,title='24个预定动态：未执行项不补齐')
ax=axes[0,1]
for i,r in enumerate(rows):
    color=colors['guard' if r['guard_hit'] else 'success' if r['success'] else 'task'];ax.bar(i,r['force_peak_N'],color=color)
ax.axhline(.025,color='#b33',ls='--',label='0.025 N共同保护');ax.set_xticks(range(len(rows)),[r['id'].replace('initial_','初始\n').replace('C_online_','C在线\n').replace('C_final_','C最终\n').replace('C_restored_','C恢复\n').replace('A_online_','A在线\n').replace('A_final_','A最终\n').replace('_100','') for r in rows],rotation=60,ha='right',fontsize=7)
ax.set_ylabel('完整周期峰值力 / N');ax.set_title('全部实测回合载荷');ax.legend(fontsize=8);ax.grid(axis='y',alpha=.2)
ax=axes[1,0]
for arm,color in [('C','#d87533'),('A','#347ca9')]:
    p=HERE/'run'/('history_'+arm+'.json')
    if p.exists():
        history=read(p);ax.plot(range(1,len(history)+1),[r['alpha_after'] for r in history],color=color,label=arm)
ax.set_xlabel('本组正式更新批次');ax.set_ylabel('温度α');ax.set_title('已执行学习历史；空白部分未训练');ax.grid(alpha=.2)
if ax.lines:ax.legend()
ax=axes[1,1]
for j,stage in enumerate(stages):
    sub=[r for r in rows if r['stage']==stage];ax.barh(j,len(sub),color='#e2e5e8');ax.barh(j,sum(r['success'] for r in sub),color=colors['success'])
    fault_count=sum(x['identity']['stage']==stage for x in a['failed_attempts'])
    ax.text(4.05,j,f'{sum(r["success"] for r in sub)}/{len(sub)}成功；{fault_count}启动故障；{4-len(sub)-fault_count}未执行',va='center',fontsize=8)
ax.set_yticks(range(6),labels);ax.invert_yaxis();ax.set_xlim(0,6.2);ax.set_xticks(range(5));ax.set_title('成功分母仅包括已执行完整回合');ax.set_xlabel('回合数')
fig.suptitle(f'100ms预热学习验证：{a["judgement"]}\n新增{a["accounting"]["new_dynamic_starts"]}动态 / {a["accounting"]["formal_batches_completed"]}批；独立测试未使用，B.2未完成',fontsize=12)
for ext in ('png','pdf'):fig.savefig(OUT/('validation_results.'+ext),dpi=180)
plt.close(fig)
fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
if rows:
    r=rows[-1];raw=json.loads(gzip.decompress((ROOT/r['archive_path']).read_bytes()));data=raw['transitions'];times=[x['trace_row']['time_s'] for x in data]
    for j,label in [(0,'X'),(1,'Y')]:
        axes[0,0].plot(times,[x['trace_row']['position_m'][j]*1e6 for x in data],label=label+'实际')
        axes[0,0].plot(times,[x['trace_row']['reference_qpos'][j]*1e6 for x in data],ls='--',lw=.8,label=label+'参考')
    axes[0,0].set_ylabel('横向位置 / μm');axes[0,0].set_title('真实位置与控制参考')
    axes[0,1].plot(times,[math.hypot(*x['trace_row']['position_m'][:2])*1e6 for x in data],label='实际XY误差')
    axes[0,1].axhline(50,color='#b33',ls='--',label='50 μm成功门');axes[0,1].set_ylabel('XY误差 / μm');axes[0,1].set_title('原成功门未放宽')
    axes[1,0].plot(times,[.025*math.sqrt(max(0.,-x['reward_terms']['force']/(.2*x['dt']))) for x in data],label='周期峰值力')
    axes[1,0].axhline(.025,color='#b33',ls='--',label='0.025 N保护');axes[1,0].set_ylabel('接触力 / N');axes[1,0].set_title('完整停止尾段保留')
    for j,label in [(0,'X请求'),(1,'Y请求')]:axes[1,1].plot(times,[x['action_log']['raw_action'][j] if x['action_active'] else float('nan') for x in data],label=label,lw=.5,alpha=.7)
    axes[1,1].set_ylabel('有权限周期归一化动作');axes[1,1].set_ylim(-1.1,1.1);axes[1,1].set_title('实际策略请求；不是有效速度')
    e=next(x for x in a['episodes'] if x['id']==r['id']);guard=e['first_guard_s']
    for ax in axes.flat:
        if guard is not None:ax.axvline(guard,color='#b33',ls=':',lw=.8)
        ax.grid(alpha=.2);ax.set_xlabel('仿真时间 / s');ax.legend(fontsize=8)
    fig.suptitle(f'最后完整回合：{r["id"]}，{r["training_batches"]}批，{e["reason"]}\n周期峰值{r["force_peak_N"]:.9f} N；原始档案离线绘图，无重跑',fontsize=12)
else:
    for ax in axes.flat:ax.text(.5,.5,'无完整回合；不能伪造轨迹',ha='center',va='center');ax.set_axis_off()
for ext in ('png','pdf'):fig.savefig(OUT/('last_episode_trace.'+ext),dpi=180)
plt.close(fig)
print(json.dumps(dict(figure_pairs=2,completed=len(rows))))
