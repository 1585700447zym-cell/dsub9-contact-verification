"""Analyze already saved actor parameters only; prohibit all compute imports."""
import builtins
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent;RUN=HERE/'run'
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
original_import=builtins.__import__
def no_learning(name,*a,**k):
    if name.split('.')[0] in ('torch','mujoco','stable_baselines3'):raise AssertionError('Distribution summary cannot perform new learning/physics')
    return original_import(name,*a,**k)
builtins.__import__=no_learning
raw=(RUN/'diagnostics.json').read_bytes();record=json.loads(raw)
ledger=json.loads((RUN/'ledger.json').read_text(encoding='utf-8'))
pin=hashlib.sha256(raw).hexdigest()
if pin!=ledger['gates']['diagnostics']:raise ValueError('Frozen diagnostic pin differs')
axes=('x','y','roll','pitch');result={}
def percentile(values,p):
    values=sorted(values);position=(len(values)-1)*p;i=math.floor(position);fraction=position-i
    return values[i]*(1-fraction)+values[min(i+1,len(values)-1)]*fraction
threshold=math.atanh(.95)
reference=record['parameters']['initial']
for role,p in record['parameters'].items():
    rows=[]
    for j,name in enumerate(axes):
        deterministic=[math.tanh(mu[j]) for mu in p['mean']]
        deviations=[abs(math.tanh(mu[j])-math.tanh(ref[j])) for mu,ref in zip(p['mean'],reference['mean'])]
        saturation=[]
        for mu,ls in zip(p['mean'],p['log_std']):
            sd=math.exp(ls[j]);saturation.append(.5*math.erfc((threshold-mu[j])/(sd*math.sqrt(2)))+.5*math.erfc((threshold+mu[j])/(sd*math.sqrt(2))))
        rows.append(dict(axis=name,deterministic_mean=statistics.mean(deterministic),
            deterministic_abs_p95=percentile([abs(v) for v in deterministic],.95),
            deterministic_abs_max=max(abs(v) for v in deterministic),
            deterministic_mean_abs_change_from_initial=statistics.mean(deviations),
            saturation_probability_mean=statistics.mean(saturation),saturation_probability_p95=percentile(saturation,.95),
            saturation_probability_max=max(saturation),log_std_mean=statistics.mean(ls[j] for ls in p['log_std'])))
    kl=[r['kl_to_reference'] for r in record['reports'][role]] if role!='initial' else [0.]*256
    result[role]=dict(per_axis=rows,kl_to_initial_mean=statistics.mean(kl),kl_to_initial_p95=percentile(kl,.95),kl_to_initial_max=max(kl))
out=HERE/'run_analysis';out.mkdir(exist_ok=False)
summary=dict(status='saved_distribution_parameters_summarized_no_new_forward',diagnostics_sha256=pin,
    state_selection_sha256=record['state_selection_sha256'],states_per_role=256,
    roles=result,new_model_forwards=0,new_optimizer_steps=0,new_physics_starts=0,
    limitation='Fixed archived active states, not physical outcome or unseen-state safety; tanh(mu) is not E[tanh(U)]')
with (out/'distribution_summary.json').open('x',encoding='utf-8') as stream:json.dump(summary,stream,indent=2);stream.write('\n')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
colors=dict(initial='#727782',A='#c74343',B='#2473ad');x=np.arange(4);width=.24
fig,plots=plt.subplots(1,2,figsize=(10.2,4.2),layout='constrained')
for k,role in enumerate(('initial','A','B')):
    rows=result[role]['per_axis'];offset=(k-1)*width
    plots[0].bar(x+offset,[100*r['saturation_probability_mean'] for r in rows],width,color=colors[role],label=role)
    plots[1].bar(x+offset,[r['deterministic_abs_p95'] for r in rows],width,color=colors[role],label=role)
for plot in plots:
    plot.set_xticks(x,axes);plot.spines[['top','right']].set_visible(False);plot.grid(axis='y',alpha=.2);plot.set_axisbelow(True)
plots[0].set_title('Mean probability of |action| >= 0.95');plots[0].set_ylabel('Probability (%)');plots[0].legend(frameon=False)
plots[1].set_title('P95 of deterministic |tanh(mean)|');plots[1].set_ylabel('Normalized action magnitude');plots[1].set_ylim(0,1)
fig.suptitle('Fixed archived active states (256 per policy); A/B after 500 updates',fontsize=11)
fig.savefig(out/'fixed_state_distribution_comparison.png',dpi=180);fig.savefig(out/'fixed_state_distribution_comparison.pdf');plt.close(fig)
print(json.dumps(dict(kl_mean={r:result[r]['kl_to_initial_mean'] for r in result},
    saturation_mean={r:[v['saturation_probability_mean'] for v in result[r]['per_axis']] for r in result},new_forwards=0)))
