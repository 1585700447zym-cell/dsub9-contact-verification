"""Standalone scientific figures from completed, independently audited records."""
from pathlib import Path
import json,os,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed; use a complete copy for regeneration')
sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_v4_requalification'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def read(p):return json.loads(p.read_text(encoding='utf8'))
result=read(OUT/'assessment.json');config=read(OUT/'configuration.json')
assert result['status'] in ('complete','controlled_stop','error')
cases=[p['id'] for p in config['common']['cases']]
colors={'F50':'#2474b5','S50':'#df7b19'}
fig,ax=plt.subplots(figsize=(10,4.8))
plotted=[]
for method,shift in [('F50',-.18),('S50',.18)]:
    rows={r['case_id']:r for r in result['rows'] if r['mode']==method and r['stage']=='final'}
    for i,case in enumerate(cases):
        row=rows.get(case);x=i+shift
        if row is None or row['status']!='finished':
            ax.text(x,.6,'not run' if row is None else 'error',rotation=90,ha='center',va='bottom',color='#777777',fontsize=8)
            plotted.append(dict(method=method,case=case,measured=False));continue
        success=row['outcome']=='FULL_SUCCESS';value=row['task_end_time_s'] if success else 26.
        ax.bar(x,value,width=.32,color=colors[method],alpha=1 if success else .45,hatch=None if success else '//',
               label=method if i==0 else None)
        ax.text(x,value+.35,f'{value:.2f}' if success else row['outcome'].replace('_','\n'),ha='center',va='bottom',fontsize=7)
        plotted.append(dict(method=method,case=case,measured=True,outcome=row['outcome'],plotted_time_s=value))
ax.set_xticks(range(len(cases)),[s.replace('_',' ') for s in cases]);ax.set_ylim(0,31)
ax.set_ylabel('Task time; failures penalized at 26 s')
ax.set_title('Frozen development evaluation, 2,000 updates per branch\nSingle seed; missing attempts are not failures; restore repeats excluded')
ax.legend();ax.grid(axis='y',alpha=.2);fig.tight_layout();fig.savefig(OUT/'frozen_development.png',dpi=180);plt.close(fig)

fig,axes=plt.subplots(2,1,figsize=(10,7),sharex=True)
history_data={}
for method in ('F50','S50'):
    p=OUT/'run'/(method+'_history.json');h=read(p) if p.exists() else []
    error=OUT/'run'/(method+'_history_at_error.json')
    if error.exists() and len(read(error)['history'])>len(h):h=read(error)['history']
    if not h:continue
    points=[]
    for start in range(0,len(h),50):
        block=h[start:start+50]
        points.append(dict(updates=start+len(block),critic_loss=float(np.mean([r['critic_loss'] for r in block])),
            weighted_entropy=float(np.mean([r['entropy_abs_mean'] for r in block])),
            absolute_physical_reward=float(np.mean([r['reward_abs_mean'] for r in block]))))
    x=[p['updates'] for p in points]
    axes[0].plot(x,[p['critic_loss'] for p in points],label=method,color=colors[method])
    axes[1].plot(x,[p['weighted_entropy'] for p in points],label=method+' active alpha * |log pi|',color=colors[method])
    axes[1].plot(x,[p['absolute_physical_reward'] for p in points],'--',label=method+' |reward|, all sampled rows',color=colors[method])
    history_data[method]=points
axes[0].set_yscale('log');axes[0].set_ylabel('Critic batch loss');axes[0].set_title('Actual completed updates; averages over 50 batches\nLoss decline and entropy/reward ratio do not establish policy benefit')
axes[1].set_yscale('log');axes[1].set_ylabel('Per-transition magnitude');axes[1].set_xlabel('Completed critic updates')
for ax in axes:
    ax.legend(fontsize=8);ax.grid(alpha=.2)
    for n in (500,1000,1500,2000):ax.axvline(n,color='#999999',lw=.5,alpha=.3)
fig.tight_layout();fig.savefig(OUT/'actual_learning_curves.png',dpi=180);plt.close(fig)
(OUT/'figure_data.json').write_text(json.dumps(dict(frozen=plotted,training=history_data),indent=2,allow_nan=False)+'\n',encoding='utf8')
print('2 audited standalone figures generated')
