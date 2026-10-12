from pathlib import Path
import json,gzip,os,math
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_compliant_search'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
d=json.loads(gzip.decompress((OUT/'run/y_neg_150.json.gz').read_bytes()));rows=d['trace']
diagnosis=json.loads((OUT/'diagnosis.json').read_text(encoding='utf-8'))
phase=diagnosis['searches'][0];start=min(rows,key=lambda r:abs(r['time_s']-phase['start_s']))
first=[r for r in rows if phase['start_s']<r['time_s']<=phase['end_s']+1e-9 and r['search_composition'] is not None]
fig,ax=plt.subplots(2,1,figsize=(9,7.5));t=[r['time_s'] for r in first]
ax[0].plot(t,[40*r['search_composition']['theta_rad']/(2*math.pi) for r in first],label='Nominal spiral radius')
ax[0].plot(t,[np.linalg.norm(r['search_composition']['target_xy_m'])*1e6 for r in first],label='Combined reference radius')
ax[0].plot(t,[np.linalg.norm(np.array(r['position_m'][:2])-start['position_m'][:2])*1e6 for r in first],label='Actual XY excursion')
ax[0].set(ylabel='Distance from search origin (um)',xlabel='Simulation time (s)',title='First search: compliance cancels most of the intended sweep')
ax[0].legend(fontsize=9)
ax[1].plot([r['time_s'] for r in rows],[r['position_m'][2]*1000 for r in rows],label='Actual Z')
a=diagnosis['recovered_advance']
ax[1].axhline(a['deepest_before_recovery_z_mm'],ls='--',c='gray',label='Deepest Z before recovery')
ax[1].scatter([diagnosis['searches'][1]['start_s'],a['time_s']],[a['second_search_start_z_mm'],a['advance_z_mm']],c=['orange','red'],zorder=4)
ax[1].annotate('Recovered search starts',(diagnosis['searches'][1]['start_s'],a['second_search_start_z_mm']),xytext=(5.1,-3.97),arrowprops=dict(arrowstyle='->'),fontsize=9)
ax[1].annotate('SEARCH_ADVANCED\nstill 161 um before previous depth',(a['time_s'],a['advance_z_mm']),xytext=(7.4,-3.83),arrowprops=dict(arrowstyle='->'),fontsize=9)
ax[1].set(ylabel='Z position (mm)',xlabel='Simulation time (s)',title='Recovery: 100 um relative advance occurs before reaching the prior contact depth')
ax[1].legend(fontsize=8,loc='lower left')
for axis in ax:axis.grid(alpha=.2)
fig.tight_layout(pad=1.5)
fig.savefig(OUT/'search_diagnosis.png',dpi=150);fig.savefig(OUT/'search_diagnosis.pdf');plt.close(fig)
