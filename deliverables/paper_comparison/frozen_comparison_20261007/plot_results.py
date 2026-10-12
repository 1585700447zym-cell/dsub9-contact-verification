"""Standard scientific plots of frozen comparisons; never creates training data."""
from pathlib import Path
import json,os
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed; regenerate only in a full copy')
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_pc07'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
def read(p):return json.loads(p.read_text(encoding='utf8'))
a=read(OUT/'assessment.json');c=read(OUT/'configuration.json')
colors={'B2':'#777777','F0':'#83b6db','S0':'#f4b370','F2000':'#2474b5','S2000':'#dc791a'}
data={}
for scope,filename,title,methods,cases in [
    ('development','development_comparison.png','Matched development: initial vs trained policies\nTrained development archives inherited unchanged; one seed',
     ['B2','F0','S0','F2000','S2000'],[x['id'] for x in c['common']['cases']]),
    ('first_use_frozen_position_test','first_use_positions.png','First-use position evaluation after checkpoint freeze\nFour prospectively fixed positions; one training seed; no retuning',
     ['B2','F2000','S2000'],list(dict.fromkeys(s['case']['id'] for s in c['attempts'] if s['evaluation_scope']!='development')))]:
    fig,axes=plt.subplots(2,1,figsize=(11,7.4),sharex=True);plotted=[];width=.78/len(methods)
    for j,method in enumerate(methods):
        rows={r['case_id']:r for r in a['records'][scope][method]}
        for i,case in enumerate(cases):
            x=i+(j-(len(methods)-1)/2)*width;row=rows.get(case)
            if row is None:
                axes[0].text(x,.25,'not run',ha='center',va='bottom',rotation=90,fontsize=6,color='#888888')
                axes[1].text(x,.25,'not run',ha='center',va='bottom',rotation=90,fontsize=6,color='#888888')
                plotted.append(dict(method=method,case=case,attempted=False));continue
            success=row.get('outcome')=='FULL_SUCCESS' and row['status']=='finished'
            value=row['task_end_time_s'] if success else 26.
            axes[0].bar(x,value,width=width*.9,color=colors[method],hatch=None if success else '//',alpha=1 if success else .5)
            axes[0].text(x,value+.25,f'{value:.2f}' if success else 'error' if row['status']!='finished' else 'fail',ha='center',va='bottom',fontsize=6)
            force=row.get('peak_force_N')
            if force is not None:
                axes[1].bar(x,force*1000,width=width*.9,color=colors[method])
            else:axes[1].text(x,.25,'unassessed',ha='center',va='bottom',rotation=90,fontsize=6)
            plotted.append(dict(method=method,case=case,attempted=True,status=row['status'],outcome=row.get('outcome'),
                plotted_penalized_time_s=value,peak_force_mN=None if force is None else force*1000,provenance=row.get('provenance')))
    axes[0].set_ylim(0,30);axes[0].set_ylabel('Task time (s); failure penalty 26 s');axes[0].set_title(title)
    axes[1].set_ylabel('Whole-episode peak force (mN)');axes[1].axhline(25,color='#b33131',linestyle='--',lw=1)
    axes[1].text(len(cases)-.55,25.2,'25 mN guard',ha='right',fontsize=8,color='#b33131');axes[1].set_ylim(0,29)
    axes[1].set_xticks(range(len(cases)),[s.replace('_',' ') for s in cases])
    axes[0].legend(handles=[Patch(facecolor=colors[m],label=m) for m in methods],ncol=len(methods),fontsize=8)
    for ax in axes:ax.grid(axis='y',alpha=.2)
    fig.tight_layout();fig.savefig(OUT/filename,dpi=180);plt.close(fig);data[scope]=plotted
(OUT/'figure_data.json').write_text(json.dumps(dict(plots=data,positions=[s['case'] for s in c['attempts'] if s['provider']=='B2' and s['evaluation_scope']!='development']),indent=2,allow_nan=False)+'\n',encoding='utf8')
print('Two comparison figures generated from audited records')
