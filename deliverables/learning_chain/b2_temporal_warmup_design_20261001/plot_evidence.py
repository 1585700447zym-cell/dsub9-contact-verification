import builtins,json,os
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
original=builtins.__import__
def guard(name,*a,**k):
    if name.split('.')[0] in ('torch','mujoco','stable_baselines3','tools'):raise RuntimeError('Saved-statistics plotting only')
    return original(name,*a,**k)
builtins.__import__=guard
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
a=json.loads((HERE/'archive_analysis.json').read_text(encoding='utf-8'))
windows=['0.02','0.1','0.4'];times=[20,100,400]
fig,ax=plt.subplots(figsize=(8.3,4.6),layout='constrained')
entries=[('Warmup: 4 archived episodes',a['pooled_warmup_windows'],'#727d8b'),
    ('Initial +X: historical success',a['episodes']['initial_x_pos_100']['windows'],'#389b6d'),
    ('B +X: task failure',a['episodes']['B_x_pos_100']['windows'],'#2471a3'),
    ('B -X: contact guard',a['episodes']['B_x_neg_100']['windows'],'#bb4141')]
for label,data,color in entries:ax.plot(times,[data[w]['axes'][0]['rms_mean'] for w in windows],marker='o',label=label,color=color)
ax.set(xscale='log',xticks=times,xticklabels=['20','100','400'],ylim=(0,1.08),
    xlabel='Complete active window duration (ms)',ylabel='RMS of window-mean normalized X request',
    title='Saved requests: temporal persistence differs from warmup')
ax.spines[['top','right']].set_visible(False);ax.minorticks_off();ax.grid(alpha=.2);ax.legend(loc='center right',fontsize=9)
fig.text(.5,-.045,'Request statistics only; not displacement, state coverage, or causal proof.',ha='center',fontsize=9)
for ext in ('png','pdf'):fig.savefig(HERE/('request_persistence.'+ext),dpi=180,bbox_inches='tight')
print('Saved 1 figure as PNG/PDF; no model or physics calls.')
