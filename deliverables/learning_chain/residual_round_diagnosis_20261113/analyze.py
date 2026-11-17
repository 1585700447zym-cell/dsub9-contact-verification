"""Existing checkpoint inference and local command diagnostics only."""
from pathlib import Path
import json,gzip,sys,importlib.util,ast
import numpy as np
import torch
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
BASE=OUT.parent/'threeway_online_yaw025_20261112'
spec=importlib.util.spec_from_file_location('run',BASE/'run_experiment.py');run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
run.helper.select()
from tools.validation.analyze_g1_recovery import JsonStream
from tools.learning.threeway_online import load
# Reuse only the archived streaming reader, without running its analysis main.
source=OUT.parent/'threeway_diagnosis_20261113/analyze.py'
tree=ast.parse(source.read_text(encoding='utf8'))
reader=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='read_archive')
exec(compile(ast.Module(body=[reader],type_ignores=[]),str(source),'exec'))
reg=run.verify(run.sha(BASE/'registration.json'))
report=dict(new_training=0,new_simulations=0,reader_sha256=run.sha(source),trajectories={},rounds={})
stored={}
for g in 'ABC':
    p=BASE/'resume_C' if g=='C' else BASE
    for case in ('E01','E02'):
        key=g+'_'+case;trace,rows=read_archive(p/'run'/key/'episode.json.gz')
        t=np.array([r['time_s'] for r in trace[:-1]]);pos=np.array([r['position_m'] for r in trace[:-1]])
        eff=np.array([r['effective'] for r in rows]);mask=np.array([r['enabled'] and r['phase']=='SEARCH' for r in rows]);start=t[mask][0]
        phases={}
        for label,m in [('first_SEARCH_1s',mask&(t<start+1)),('SEARCH_before6s',mask&(t<6)),('all_SEARCH',mask)]:
            dot=pos[m,:2]*eff[m,:2]
            phases[label]=dict(rows=int(m.sum()),effective_xy_um_s=(eff[m,:2].mean(0)*1e6).tolist(),
                toward_origin_fraction=(dot<0).mean(0).tolist(),away_origin_fraction=(dot>0).mean(0).tolist(),
                minus_position_dot_delta_mean_mm2_s=(-dot.mean(0)*1e6).tolist(),
                integrated_delta_command_xy_um=(eff[m,:2].sum(0)*.002*1e6).tolist())
        result=run.read(BASE/'review_final'/(key+'.json'))
        report['trajectories'][key]=dict(first_search_s=float(start),phases=phases,task_frame=result['geometry']['frames']['task'],
            receipt_finish_criteria=run.read(p/'run'/key/'receipt.json')['finish_criteria'])
        if key in ('B_E01','C_E01'):stored[key]=(torch.tensor(np.array([r['observation'] for r in rows]),dtype=torch.float32),t,mask,start)
        print('trajectory',key,flush=True)
for g in 'BC':
    p=BASE/'resume_C' if g=='C' else BASE;report['rounds'][g]={}
    for n in (0,1,2,3):
        meta=reg['groups'][g]['initial'] if n==0 else run.read(p/f'{g}_optimization_{n}.json')
        obj=load(p/meta['path'],config=reg['groups'][g]['config'],expected_digest=meta['checkpoint_sha256'],group=g)
        actor=obj.actor.eval();up=obj._updater;result={}
        with torch.no_grad():
            for key,(obs,t,mask,start) in stored.items():
                if g=='B':mu,ls,_=actor.forward_sequence(obs[None]);mu,ls=mu[0],ls[0]
                else:mu,ls,_=actor.get_action_dist_params(obs)
                pred=mu.tanh();data={}
                for label,m in [('first_SEARCH_1s',mask&(t<start+1)),('SEARCH_before6s',mask&(t<6)),('all_SEARCH',mask)]:
                    data[label]=dict(mean_action=pred[m].mean(0).tolist(),std_action=pred[m].std(0).tolist())
                # Fixed-observation local critic contrast, no dynamics rollout:
                # hold other actor coordinates fixed; compare Y=-.05 vs +.05.
                ids=np.flatnonzero(mask&(t<start+1))[::25]
                low=pred[ids].clone();high=low.clone();low[:,1]=-.05;high[:,1]=.05
                if g=='B':
                    encoded=[q.encode_sequence(obs[None])[0][0,ids] for q in up.critics]
                    qlo=torch.stack([q.q(h,low) for q,h in zip(up.critics,encoded)]).min(0).values
                    qhi=torch.stack([q.q(h,high) for q,h in zip(up.critics,encoded)]).min(0).values
                else:
                    qlo=torch.cat(up.policy.critic(obs[ids],low),1).min(1).values
                    qhi=torch.cat(up.policy.critic(obs[ids],high),1).min(1).values
                data['critic_negative_vs_positive_Y']=dict(mean_Qminus_Qplus=float((qlo-qhi).mean()),negative_Y_preferred_fraction=float(((qlo-qhi)>0).float().mean()),sampled_states=len(ids),alpha=float(up.log_alpha.exp()))
                result[key]=data
        report['rounds'][g][str(n*101)]=result
        print('checkpoint',g,n*101,flush=True)
run.write(OUT/'diagnostics.json',report)
print('READ ONLY COMPLETE')
