"""Plots saved physical trajectories only; no model or environment imports."""
import builtins,gzip,json,math,os
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=HERE/'result_analysis'
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
original=builtins.__import__
def guard(name,*a,**k):
    if name.split('.')[0] in ('torch','mujoco','stable_baselines3'):raise AssertionError('Saved trajectory plot cannot compute')
    return original(name,*a,**k)
builtins.__import__=guard
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
raw=lambda p:json.loads(gzip.decompress(p.read_bytes()))
assessment=read(OUT/'assessment.json')
old=ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929/run/initial'
a=ROOT/'deliverables/learning_chain/b2_actor_lr_execution_20260930/run/evaluation_A'
initial=read(old/'results.json');arows=read(a/'results.json');brows=assessment['rows']
order=['x_pos_100','x_neg_100','y_pos_100','y_neg_100'];labels=['+X','-X','+Y','-Y']
fig,axes=plt.subplots(1,3,figsize=(13.5,4.2),layout='constrained')
colors=['#808995','#bf4650','#2677a5'];offsets=[-.25,0,.25]
for idx,(rows,label,color) in enumerate(zip([initial,arows,brows],['Initial (historical)','A500 (prior)','B500'],colors)):
    mapping={r['case']:r for r in rows}
    for k,name in enumerate(order):
        x=k+offsets[idx]
        if name not in mapping:
            for ax in axes:ax.text(x,0,'N/E',rotation=90,fontsize=8,ha='center',va='bottom',color=color)
            continue
        r=mapping[name]
        outcome=1 if r['success'] else -1 if r.get('guard_hit',r['task_outcome']=='CONTACT_GUARD') else 0
        axes[0].scatter(x,outcome,color=color,s=70,marker='o' if r['success'] else 'x',label=label if k==0 else None)
        axes[1].bar(x,r['force_peak_N']*1000,width=.23,color=color,label=label if k==0 else None)
        axes[2].bar(x,r['final_xy_error_m']*1e6,width=.23,color=color)
for ax in axes:
    ax.set_xticks(range(4),labels);ax.set_xlabel('100 um, zero-tilt development point')
    ax.spines[['top','right']].set_visible(False);ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
axes[0].set_yticks([-1,0,1],['Guard failure','Task failure','Success']);axes[0].set_ylim(-1.5,1.5)
axes[0].set_title('All recorded outcomes');axes[0].legend(fontsize=8,loc='lower right')
axes[1].set_title('Cycle-peak contact force');axes[1].set_ylabel('mN');axes[1].axhline(25,color='black',ls='--',lw=1)
axes[2].set_title('Final lateral error');axes[2].set_ylabel('um');axes[2].axhline(50,color='black',ls='--',lw=1)
fig.suptitle('Frozen B evaluation | N/E = not executed, not a measured failure',fontsize=12)
for ext in ('png','pdf'):fig.savefig(OUT/('development_results.'+ext),dpi=180)
plt.close(fig)
datasets=[('Initial (historical)',raw(old/'episodes/x_pos_100/episode.json.gz'),colors[0]),
    ('A500',raw(a/'episodes/x_pos_100/episode.json.gz'),colors[1]),
    ('B500',raw(HERE/'run/episodes/x_pos_100/episode.json.gz'),colors[2])]
fig,axes=plt.subplots(2,2,figsize=(12,7),layout='constrained')
for label,r,color in datasets:
    rows=r['transitions'];time=np.array([t['trace_row']['time_s'] for t in rows])
    force=[.025*math.sqrt(max(0,-t['reward_terms']['force']/(.2*t['dt'])))*1000 for t in rows]
    pos=np.array([t['trace_row']['position_m'] for t in rows])*1e6
    action=np.array([t['action_log']['raw_action'][0] if t['action_active'] else np.nan for t in rows])
    axes[0,0].plot(time,force,color=color,label=label,lw=1)
    axes[0,1].plot(time,pos[:,0],color=color,lw=1)
    axes[1,0].plot(time,np.linalg.norm(pos[:,:2],axis=1),color=color,lw=1)
    axes[1,1].plot(time,action,color=color,lw=1)
    for ax in axes.flat:ax.axvline(r['stop_time'],color=color,ls=':',lw=.7,alpha=.5)
axes[0,0].axhline(25,color='black',ls='--',lw=1);axes[0,0].set(title='Cycle-peak force',ylabel='mN');axes[0,0].legend(fontsize=9)
axes[0,1].axhline(0,color='black',lw=.7);axes[0,1].set(title='X position: center crossing and final offset',ylabel='um')
axes[1,0].axhline(50,color='black',ls='--',lw=1);axes[1,0].set(title='Lateral error (success threshold: 50 um)',ylabel='um')
axes[1,1].set(title='X residual request during enabled cycles',ylabel='Normalized action',ylim=(-1.05,1.05))
for ax in axes.flat:
    ax.set_xlabel('Simulation time (s)');ax.spines[['top','right']].set_visible(False);ax.grid(alpha=.2)
fig.suptitle('+X100 development point | saved trajectories, no new rollout',fontsize=13)
for ext in ('png','pdf'):fig.savefig(OUT/('x_positive_trajectories.'+ext),dpi=180)
plt.close(fig)
print(json.dumps(dict(plots=2,png=2,pdf=2,new_model_forwards=0,new_physics=0)))
