"""Offline checks and figures from complete saved runs; no physics stepping."""
from pathlib import Path
import gzip,json,hashlib,math,os,sys
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_reference_search'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import numpy as np
from tools.model.clearance_task import finish_criteria,pin_fit,pin_clearance_m
from tools.model.functional_task import functional_finish
from tools.validation.run_b1_baseline import geometric_finish
from tools.validation.native313_matrix_audit import actual_stop_pass
from tools.validation.run_contact_candidate_stop import physical_tail_pass


def read(p):return json.loads(gzip.decompress(p.read_bytes()))


def hold(trace,stop,predicate):
    if stop is None:return False
    since=None
    for r in trace:
        if r['time_s']<stop-1e-10:continue
        if r['time_s']>stop+1.+1e-10:break
        if predicate(r):
            if since is None:since=r['time_s']
            if r['time_s']-since>=.1-1e-12:return True
        else:since=None
    return False


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
    ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf-8'))
    assert ledger['status'] in ('complete','controlled_stop')
    criteria=finish_criteria();rows=[];archives={}
    for e in ledger['episodes']:
        p=OUT/'run'/f"{e['id']}.json.gz";assert hashlib.sha256(p.read_bytes()).hexdigest()==e['archive_sha256']
        d=read(p);archives[e['id']]=d;r=d['trace'][-1];facts=d['guard_facts'];q=np.array(r['quaternion_wxyz'])
        stopped=bool(actual_stop_pass(d['stop_samples'],d['events'],e['stop_time'],e['end_time'],.0002) and physical_tail_pass(d['stop_samples'],e['end_time'],.0002))
        peaks=e['peaks'];eligible=(facts['simulation_valid'] and stopped and not facts['contact_reasons'] and not facts['motion_reasons'] and peaks['force_N']<criteria['force_N'] and peaks['torque_G_Nm']<criteria['torque_Nm'] and peaks['penetration_m']<criteria['penetration_m'])
        functional=bool(eligible and hold(d['trace'],e['stop_time'],lambda x:functional_finish(x,criteria)))
        strict=bool(functional and hold(d['trace'],e['stop_time'],lambda x:geometric_finish(x,criteria) and pin_fit(x)))
        assert functional==(e['outcome']['task_outcome']=='FULL_SUCCESS')
        rows.append(dict(id=e['id'],outcome=e['outcome']['task_outcome'],reason=e['reason'],functional_success=functional,strict_precision_success=strict,
            simulation_valid=facts['simulation_valid'],physical_stopped=stopped,xy_um=e['xy_um'],z_um=e['z_um'],
            angle_deg=2*math.degrees(math.acos(min(1.,abs(q[0])/np.linalg.norm(q)))),pin_clearance_um=pin_clearance_m(r)*1e6,
            peak_force_mN=peaks['force_N']*1000,peak_penetration_um=peaks['penetration_m']*1e6,
            control_cycles=e['control_cycles'],physical_substeps=e['physical_substeps'],wall_seconds=e['wall_seconds'],
            stop_time_s=e['stop_time'],task_end_time_s=e['task_end_time'],end_time_s=e['end_time'],
            contact_cycles=e['contact_cycles'],search_cycles=e['search_cycles'],controller_events=d['controller_events'],guard_facts=facts))
    summary=dict(status=ledger['status'],episodes=len(rows),unused_closed=ledger['unused_closed'],cumulative=ledger['prior_cumulative']+len(rows),
        functional_success=sum(r['functional_success'] for r in rows),strict_precision_success=sum(r['strict_precision_success'] for r in rows),
        control_cycles=sum(r['control_cycles'] for r in rows),physical_substeps=sum(r['physical_substeps'] for r in rows),
        wall_seconds=sum(r['wall_seconds'] for r in rows),training_updates=0,network_calls=0,independent_tests=0,
        inputs_unchanged=ledger['inputs_unchanged'],rows=rows)
    (OUT/'assessment.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    comparisons={};keys=['position_m','quaternion_wxyz','velocity_world','contact_wrench_M','limited_command_world','reference_qpos']
    for name,d in archives.items():
        folder='axis_search_20261004' if name=='y_neg_150' else ('functional_b2_20261003' if name=='y_pos_150' else 'clearance120_20261003')
        old=read(ROOT/'deliverables/task_variants'/folder/'run'/f'{name}.json.gz')
        trigger=next((e['time_s'] for e in d['controller_events'] if e['reason']=='LOW_LOAD_SEARCH'),None)
        pairs=[(x,y) for x,y in zip(old['trace'],d['trace']) if trigger is None or x['time_s']<=trigger+1e-10]
        comparisons[name]=dict(scope='full archived trajectory comparison' if trigger is None else 'before first search with new composition',
            before_time_s=trigger,samples=len(pairs),old_samples=len(old['trace']),new_samples=len(d['trace']),
            fields_equal={k:all(x[k]==y[k] for x,y in pairs) for k in keys})
    (OUT/'trajectory_comparisons.json').write_text(json.dumps(comparisons,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    old=read(ROOT/'deliverables/task_variants/axis_search_20261004/run/y_neg_150.json.gz');new=archives['y_neg_150']
    fig,ax=plt.subplots(4,1,figsize=(9,10),sharex=True)
    for label,d in [('Axis-separated search (v6)',old),('Drive-reference tracking (v7)',new)]:
        t=[r['time_s'] for r in d['trace']]
        ax[0].plot(t,[np.linalg.norm(r['contact_wrench_M'][:3])*1000 for r in d['trace']],label=label)
        ax[1].plot(t,[np.linalg.norm(np.array(r['reference_qpos'][:2])-r['position_m'][:2])*1e6 for r in d['trace']])
        ax[2].plot(t,[r['commanded_correction'][1]*1e6 for r in d['trace']])
        ax[3].plot(t,[(r['position_m'][2]+.004)*1000 for r in d['trace']])
    ax[0].axhline(25,ls='--',c='red',label='Unchanged force guard')
    ax[0].axhline(22,ls=':',c='gray',label='Load trigger (also lateral + hold)')
    for e in new['controller_events']:
        if e['reason']=='LOW_LOAD_SEARCH':
            for axis in ax:axis.axvline(e['time_s'],ls=':',c='green')
    handles,labels=ax[0].get_legend_handles_labels()
    fig.legend(handles,labels,fontsize=8,loc='upper center',bbox_to_anchor=(.5,.955),ncol=2)
    ax[0].set_ylabel('Total contact force (mN)')
    ax[1].set_ylabel('XY reference lead (um)');ax[2].set_ylabel('Y admittance integral (um)');ax[3].set_ylabel('Insertion advance (mm)');ax[3].set_xlabel('Simulation time (s)')
    for axis in ax:axis.grid(alpha=.2)
    fig.suptitle('Development case -Y 150 um: drive-reference tracking',y=.99)
    fig.subplots_adjust(top=.86,bottom=.07,hspace=.20)
    fig.savefig(OUT/'results.png',dpi=150);fig.savefig(OUT/'results.pdf');plt.close(fig)
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__':main()
