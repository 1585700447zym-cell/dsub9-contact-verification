"""Read-only scientific comparison of four paired development evaluations."""
import gc
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import numpy as np

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec);spec.loader.exec_module(obj);return obj


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--available',action='store_true',help='Cache audited cases only; do not publish a final comparison')
    args=parser.parse_args()
    run=load('reward_screening_runner',OUT/'run_experiment.py')
    run.select()
    reg=run.read(OUT/'registration.json'); ledger=run.read(OUT/'ledger.json')
    if not args.available and ledger['status']!='COMPLETED': raise ValueError('Completed bounded experiment required')
    run.verify(ledger['registration_sha256'])
    if not run.read(OUT/'pairing.json')['verified']: raise ValueError('Unpaired optimization')
    helper=load('mesh_review',run.BASE/'review_eval.py')
    from tools.learning.geometry_reward_shaping import potential
    review=OUT/'review';review.mkdir(exist_ok=True)
    cache_path=review/'cache_manifest.json'
    cache=run.read(cache_path) if cache_path.exists() else {}
    results={}; plot_data={}
    for branch in ('A','B'):
        optimization=run.read(OUT/f'optimization_{branch}.json')
        for job in reg['evaluate']:
            name=branch+'_'+job['episode_id']; folder=OUT/'run'/name
            if args.available and not (folder/'audit.json').exists(): continue
            receipt=helper.receipt_summary(folder/'receipt.json'); proof=run.read(folder/'audit.json')
            helper.verify_domain(receipt,proof,job,reg['common'],reg['config'],optimization['checkpoint_sha256'],101)
            if not proof['verified'] or not proof['experiment_intervention']['yaw']['verified']:
                raise ValueError('Full source/physics/intervention audit required')
            if run.sha(folder/'episode.json.gz')!=proof['archive_sha256']: raise ValueError('Audited archive changed')
            cache_inputs=dict(archive_sha256=proof['archive_sha256'],receipt_sha256=run.sha(folder/'receipt.json'),
                audit_sha256=run.sha(folder/'audit.json'),registration_sha256=run.sha(run.REG),
                analyzer_sha256=run.sha(Path(__file__)),helper_sha256=run.sha(run.BASE/'review_eval.py'),
                geometry_sha256=run.sha(ROOT/'tools/learning/geometry_reward_shaping.py'))
            result_path=review/(name+'.json');plot_path=review/(name+'.plot.json')
            saved=cache.get(name,{})
            if (saved.get('inputs')==cache_inputs and result_path.exists() and plot_path.exists()
                    and saved.get('result_sha256')==run.sha(result_path) and saved.get('plot_sha256')==run.sha(plot_path)):
                results[name]=run.read(result_path);plot_data[name]=run.read(plot_path)
                print(name,'verified cached analysis',flush=True)
                continue
            raw=helper.read_archive(folder/'episode.json.gz',receipt['task_end_time_s'])
            geometry=helper.geometry_metrics(raw,receipt)
            search=[r for r in raw['actions'] if r['phase']=='SEARCH' and r['enabled']]
            normalized=np.array([r['log']['raw_action'] for r in search])
            search_summary=dict(rows=len(search),duration_s=sum(r['dt'] for r in search),
                normalized_action_mean=normalized.mean(axis=0).tolist() if len(search) else None,
                requested_y_mean_um_s=float(np.mean([r['requested_y'] for r in search])*1e6) if search else None,
                effective_y_mean_um_s=float(np.mean([r['effective_y'] for r in search])*1e6) if search else None)
            result=dict(branch=branch,episode_id=job['episode_id'],outcome=receipt['outcome'],reason=receipt['final_reason'],
                success=receipt['outcome']=='FULL_SUCCESS',task_end_s=receipt['task_end_time_s'],
                geometry=geometry,load=raw['native_task_load'],search=search_summary,
                recovery_count=len(proof['load_warnings']['recoveries']),
                actual_search_resumptions=proof['load_warnings']['actual_search_resumptions'],
                source_checkpoint_sha256=optimization['checkpoint_sha256'],archive_sha256=proof['archive_sha256'],
                audited=True,terminal_geometry_phi=potential(raw['trace'][-1]))
            results[name]=result
            sampled=[r for i,r in enumerate(raw['trace']) if i%25==0 and r['time_s']<=receipt['task_end_time_s']+1e-9]
            plot_data[name]=dict(time_s=[r['time_s'] for r in sampled],phi=[potential(r) for r in sampled],
                                 origin_z_gap_mm=[abs(r['position_m'][2])*1000 for r in sampled])
            run.write(result_path,result);run.write(plot_path,plot_data[name])
            cache[name]=dict(inputs=cache_inputs,result_sha256=run.sha(result_path),plot_sha256=run.sha(plot_path))
            run.write(cache_path,cache)
            print(name,receipt['outcome'],geometry['frames']['task']['main_fit_count'],flush=True)
            del raw;gc.collect()
    if args.available:
        print('Audited analysis cached; final comparison pending',len(results),'/4',flush=True)
        return
    successes={branch:sum(r['success'] for r in results.values() if r['branch']==branch) for branch in ('A','B')}
    report=dict(stage='B.2',development_only=True,seed=reg['config']['learning']['seed'],successes=successes,
                results=results,costs={k:ledger[k] for k in ('stage_initializations','cumulative_initializations','native_steps','updates')},
                limitation='Single seed, shared fixed data,101 updates; does not test reward-guided online exploration.')
    run.write(review/'comparison.json',report);run.write(review/'plot_data.json',plot_data)
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axs=plt.subplots(2,2,figsize=(10,6),sharex='col')
        for col,ep in enumerate(('E01_GRU','E02_GRU')):
            for branch,label,color in [('A','Original reward','#4866b2'),('B','Geometry shaping','#d77528')]:
                d=plot_data[branch+'_'+ep]
                axs[0,col].plot(d['time_s'],d['phi'],label=label,color=color)
                axs[1,col].plot(d['time_s'],d['origin_z_gap_mm'],label=label,color=color)
            axs[0,col].set_title(ep.replace('_GRU',''));axs[1,col].set_xlabel('Time (s)')
            for ax in axs[:,col]: ax.grid(alpha=.25)
        axs[0,0].set_ylabel('Geometry potential');axs[1,0].set_ylabel('Origin Z gap (mm)')
        axs[0,0].legend();fig.tight_layout();fig.savefig(review/'reward_comparison.png',dpi=160);plt.close(fig)
    except ImportError:
        pass


if __name__=='__main__': main()
