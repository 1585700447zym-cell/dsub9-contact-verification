"""Plot retained archives, never a simulated counterfactual."""
import gzip,json,os,math
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
a=read(OUT/'assessment.json');rows=a['rows'];names=['x_pos_100_A','x_pos_100_C','x_neg_100_A','x_neg_100_C','y_pos_100_A','y_pos_100_C','y_neg_100_A','y_neg_100_C']
byid={r['id']:r for r in rows};colors={'A':'#2874a6','C':'#dc7633'}
fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
ax=axes[0,0]
for i,name in enumerate(names):
    if name not in byid:ax.text(i,.0005,'未执行',rotation=90,ha='center',va='bottom',color='#777');continue
    r=byid[name];ax.bar(i,r['force_peak_N'],color=colors[r['arm']],edgecolor='#b33' if r['guard_hit'] else 'none')
    ax.text(i,r['force_peak_N']+.0005,'保护' if r['guard_hit'] else ('成功' if r['success'] else '任务失败'),rotation=90,ha='center',va='bottom',fontsize=8)
ax.axhline(.025,color='#b33',ls='--',lw=1);ax.set_ylim(0,max(.033,max((r['force_peak_N'] for r in rows),default=0)*1.3))
ax.set_xticks(range(8),['+X A','+X C','−X A','−X C','+Y A','+Y C','−Y A','−Y C'],rotation=35)
ax.set_ylabel('周期峰值力 / N');ax.set_title('全部预定回合：成功与普通失败均保留')
ax=axes[0,1]
for arm,offset in [('A',-.18),('C',.18)]:
    stats=a['pooled_request_windows'][arm]['0.1'];values=[x['rms_mean'] or 0 for x in stats['axes']]
    ax.bar([i+offset for i in range(4)],values,width=.35,color=colors[arm],label=f'{arm}: {stats["count"]}个完整活动窗口')
ax.set_xticks(range(4),['X','Y','roll','pitch']);ax.set_ylim(0,1.05);ax.set_ylabel('100 ms窗口平均请求的均方根');ax.legend(fontsize=8)
ax.set_title('请求持续性：统计不是状态覆盖或实际位移')
for axis_index,ax in enumerate(axes[1]):
    for arm in ('A','C'):
        key='x_pos_100_'+arm
        if key not in byid:continue
        raw=json.loads(gzip.decompress((HERE/'run/episodes'/key/'episode.json.gz').read_bytes()));data=raw['transitions']
        times=[r['trace_row']['time_s'] for r in data]
        if axis_index==0:
            ax.plot(times,[r['trace_row']['position_m'][0]*1e6 for r in data],color=colors[arm],label=arm)
        else:
            ax.plot(times,[r['action_log']['raw_action'][0] if r['action_active'] else float('nan') for r in data],color=colors[arm],alpha=.65,lw=.5,label=arm)
    ax.set_xlabel('仿真时间 / s');ax.grid(alpha=.2);ax.legend()
axes[1,0].axhline(0,color='#444',lw=.8);axes[1,0].set_ylabel('实际X位置 / μm');axes[1,0].set_title('正X：真实轨迹；没有重跑或物理反事实')
axes[1,1].set_ylabel('有权限周期X请求');axes[1,1].set_ylim(-1.1,1.1);axes[1,1].set_title('正X：完整2 ms请求与权限间断')
fig.suptitle(f'时间相关预热预检：{len(rows)}/8回合完成，训练/网络前向0；任何保护停止余量',fontsize=13)
for ext in ('png','pdf'):fig.savefig(OUT/('preflight_results.'+ext),dpi=180)
plt.close(fig)
if 'x_neg_100_A' in byid and 'x_neg_100_C' in byid:
    fig,axes=plt.subplots(2,2,figsize=(11,7),layout='constrained')
    for arm in ('A','C'):
        raw=json.loads(gzip.decompress((HERE/'run/episodes'/('x_neg_100_'+arm)/'episode.json.gz').read_bytes()));data=raw['transitions']
        times=[r['trace_row']['time_s'] for r in data]
        label=f'{arm}：'+('成功' if byid['x_neg_100_'+arm]['success'] else '任务失败')
        axes[0,0].plot(times,[r['trace_row']['position_m'][0]*1e6 for r in data],color=colors[arm],label=label)
        axes[0,1].plot(times,[math.hypot(*r['trace_row']['position_m'][:2])*1e6 for r in data],color=colors[arm],label=label)
        axes[1,0].plot(times,[.025*math.sqrt(max(0.,-r['reward_terms']['force']/(.2*r['dt']))) for r in data],color=colors[arm],label=label)
        blocks=[];block=[]
        for r in data:
            if not r['action_active']:
                block=[]
                if blocks and math.isfinite(blocks[-1][1]):blocks.append((r['trace_row']['time_s'],float('nan')))
                continue
            block.append(r)
            if len(block)==50:
                blocks.append((block[-1]['trace_row']['time_s'],sum(x['action'][0] for x in block)/50));block=[]
        axes[1,1].plot([x[0] for x in blocks],[x[1] for x in blocks],color=colors[arm],lw=1,label=label)
    axes[0,0].axhline(0,color='#444',lw=.8);axes[0,0].set_ylabel('实际X / μm');axes[0,0].set_title('负X：真实位置')
    axes[0,1].axhline(50,color='#b33',ls='--',label='50 μm成功门');axes[0,1].set_ylabel('实际XY误差 / μm');axes[0,1].set_title('候选终末误差未满足成功门')
    axes[1,0].axhline(.025,color='#b33',ls='--');axes[1,0].set_ylabel('周期峰值力 / N');axes[1,0].set_title('任务失败与力保护区分')
    axes[1,1].set_ylabel('完整100 ms窗口X平均请求');axes[1,1].set_ylim(-1.1,1.1);axes[1,1].set_title('双向持续请求扩大，不等于提高成功率')
    for ax in axes.flat:ax.set_xlabel('仿真时间 / s');ax.legend(fontsize=8);ax.grid(alpha=.2)
    fig.suptitle('负X100 μm：新A/C配对；原始失败保留',fontsize=13)
    for ext in ('png','pdf'):fig.savefig(OUT/('negative_x_comparison.'+ext),dpi=180)
    plt.close(fig)
print(json.dumps({'figure_pairs':2 if 'x_neg_100_C' in byid else 1,'completed':len(rows)}))
