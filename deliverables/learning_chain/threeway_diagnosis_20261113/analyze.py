"""Read-only records and fixed-observation inference; no simulator or optimizer."""
from pathlib import Path
import sys,json,gzip,importlib.util,hashlib
import numpy as np
import torch
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
BASE=OUT.parent/'threeway_online_yaw025_20261112'
spec=importlib.util.spec_from_file_location('runner',BASE/'run_experiment.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
run.helper.select()
from tools.validation.analyze_g1_recovery import JsonStream
from tools.learning.threeway_online import load
reg=run.read(BASE/'registration.json');run.verify(run.sha(BASE/'registration.json'))
report=dict(scope='Existing records and fixed observation inference only; no new trajectories or optimizer updates',training={},evaluation={},inference={})
actors={}
for g in 'ABC':
    p=BASE/'resume_C' if g=='C' else BASE
    cfg=reg['groups'][g]['config']; rounds=[]
    for n in (1,2,3):
        r=run.read(p/f'{g}_optimization_{n}.json');u=r['updates'];b=r['batches']
        rounds.append(dict(round=n,transitions=r['admitted_transitions'],active_rows=sum(x['active_rows'] for x in u),
            focus_counts={str(k):sum(x['focus_kind']==k for x in b) for k in {x['focus_kind'] for x in b}},
            **{k:dict(first=u[0][k],last=u[-1][k],median=float(np.median([x[k] for x in u if x[k] is not None])))
               for k in ('critic_loss','actor_loss','critic_grad_norm','actor_grad_norm','alpha_after')}))
    episodes=[]
    for job in reg['groups'][g]['train']:
        receipt=run.read(p/'run'/job['episode_id']/'receipt.json');labels=run.read(p/'run'/job['episode_id']/'focus.json')
        reward=run.read(p/'rewards'/(job['episode_id']+'.json'))
        episodes.append(dict(id=job['episode_id'],outcome=receipt['outcome'],time_s=receipt['task_end_time_s'],
            anchors=len(labels['anchors']),anchor_kinds=[x['kind'] for x in labels['anchors']],reward_phases=reward['phases']))
    report['training'][g]=dict(rounds=rounds,episodes=episodes)
    for tag,meta in [('initial',reg['groups'][g]['initial']),('final',r)]:
        obj=load(p/meta['path'],config=cfg,expected_digest=meta['checkpoint_sha256'],group=g)
        actors[g+'_'+tag]=obj.actor.eval()

def read_archive(path):
    with gzip.open(path,'rt',encoding='utf8') as f:
        stream=JsonStream(f);trace=rows=None
        for key in stream.members(as_object=True):
            if key=='trace':
                trace=[{k:r[k] for k in ('time_s','position_m','quaternion_wxyz')} for _ in stream.members() for r in [stream.value()]]
            elif key=='transitions':
                rows=[]
                for _ in stream.members():
                    r=stream.value();l=r['action_log']
                    rows.append(dict(observation=r['observation'],enabled=r['action_active'],action=r['action'],
                        phase=l['composition_inputs']['phase'],requested=l['requested_residual'],effective=l['effective_command_delta'],
                        zero=l['zero_residual_limited_command'],predicted=l['predicted_limited_command']))
            else:stream.discard()
    return trace,rows

def yaw(q):
    w,x,y,z=q.T;return np.degrees(np.arctan2(2*(w*z+x*y),1-2*(y*y+z*z)))

@torch.no_grad()
def predict(key,obs):
    actor=actors[key]
    if key.startswith('C'): mu,ls,_=actor.get_action_dist_params(obs)
    else:
        mu,ls,_=actor.forward_sequence(obs[None]);mu,ls=mu[0],ls[0]
    return mu.tanh().numpy(),ls.exp().numpy()

plot={}
for g in 'ABC':
    p=BASE/'resume_C' if g=='C' else BASE
    for case in ('E01','E02'):
        key=g+'_'+case;path=p/'run'/key/'episode.json.gz'
        trace,rows=read_archive(path);t=np.array([r['time_s'] for r in trace[:-1]])
        xyz=np.array([r['position_m'] for r in trace[:-1]])*1000;angles=yaw(np.array([r['quaternion_wxyz'] for r in trace[:-1]]))
        mask=np.array([r['phase']=='SEARCH' and r['enabled'] for r in rows]);start=t[mask][0]
        action=np.array([r['action'] for r in rows]);req=np.array([r['requested'] for r in rows]);eff=np.array([r['effective'] for r in rows]);zero=np.array([r['zero'] for r in rows])
        entry={}
        for label,m in [('all_search',mask),('first_search_1s',mask&(t<start+1)),('search_before_6s',mask&(t<6)),('search_6_10s',mask&(t>=6)&(t<10))]:
            if not m.any():continue
            entry[label]=dict(rows=int(m.sum()),action_mean=action[m].mean(0).tolist(),action_std=action[m].std(0).tolist(),
                requested_mean=req[m].mean(0).tolist(),effective_mean=eff[m].mean(0).tolist(),zero_mean=zero[m].mean(0).tolist())
        entry['snapshots']=[dict(time=float(t[i]),xyz_mm=xyz[i].tolist(),yaw_deg=float(angles[i]),phase=rows[i]['phase']) for sec in (0,4,6,8,10,15,20,30) for i in [int(np.argmin(abs(t-sec)))]]
        entry['first_search_s']=float(start);entry['archive_sha256']=run.sha(path)
        metrics=run.read(BASE/'review_final'/(key+'.json'))
        entry['first_main_axial_overlap_s']=metrics['geometry']['first_main_axial_overlap_s'];entry['first_all_main_fit_s']=metrics['geometry']['first_all_main_fit_s']
        report['evaluation'][key]=entry
        if key in ('B_E01','C_E01'):
            obs=torch.tensor(np.array([r['observation'] for r in rows]),dtype=torch.float32)
            checks={}
            for candidate in ('B_initial','B_final','C_initial','C_final'):
                pred,std=predict(candidate,obs)
                checks[candidate]=dict(search_mean=pred[mask].mean(0).tolist(),search_std=pred[mask].std(0).tolist(),gaussian_std=std[mask].mean(0).tolist(),
                    early_search_mean=pred[mask&(t<6)].mean(0).tolist())
                if candidate==g+'_final': checks[candidate]['recorded_max_error']=float(abs(pred[mask]-action[mask]).max())
                if candidate=='B_final':
                    indices=np.flatnonzero(mask)[::100];errors=[]
                    for i in indices:
                        short,_=predict(candidate,obs[max(0,i-256):i+1]);errors.append(abs(short[-1]-pred[i]))
                    checks[candidate]['256_prefix_vs_full_max_error']=float(np.max(errors))
            report['inference'][key]=checks
        pick=np.arange(0,len(t),25)
        plot[key]=dict(t=t[pick].tolist(),xyz=xyz[pick].tolist(),yaw=angles[pick].tolist(),action=action[pick].tolist())
        print('analyzed',key,flush=True)
run.write(OUT/'diagnostics.json',report);run.write(OUT/'plot_data.json',plot)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,axs=plt.subplots(3,2,figsize=(11,8),sharex='col')
for col,case in enumerate(('E01','E02')):
    for g,c,s in [('A','#4866b2','-'),('B','#d77528','--'),('C','#398456',':')]:
        d=plot[g+'_'+case];pos=np.array(d['xyz'])
        for i,values in enumerate((pos[:,0],pos[:,1],d['yaw'])):axs[i,col].plot(d['t'],values,label=g,color=c,linestyle=s)
    axs[0,col].set_title(case);axs[2,col].set_xlabel('Time (s)')
    for ax in axs[:,col]:ax.grid(alpha=.25)
for i,label in enumerate(('Origin X (mm)','Origin Y (mm)','Yaw (deg)')):axs[i,0].set_ylabel(label)
fig.legend(*axs[0,0].get_legend_handles_labels(),loc='upper center',ncol=3);fig.tight_layout(rect=(0,0,1,.96));fig.savefig(OUT/'trajectory_diagnosis.png',dpi=150)
print('READ-ONLY DIAGNOSIS COMPLETE',flush=True)
