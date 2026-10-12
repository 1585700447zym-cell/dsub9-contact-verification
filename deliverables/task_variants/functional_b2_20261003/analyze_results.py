"""Offline audit of this stage's saved traces, no physics calls or relabeling."""
import gzip
import hashlib
import json
import math
import os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_functional_b2'))
import sys
sys.path.insert(0,str(ROOT))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import numpy as np
from tools.model.clearance_task import finish_criteria, pin_fit, pin_clearance_m
from tools.model.functional_task import functional_finish
from tools.validation.run_b1_baseline import geometric_finish
from tools.validation.native313_matrix_audit import actual_stop_pass
from tools.validation.run_contact_candidate_stop import physical_tail_pass


def read(path):
    return json.loads(gzip.decompress(path.read_bytes()))


def hold_pass(trace,stop,predicate,criteria):
    since=None
    if stop is None:return False
    for r in trace:
        if r['time_s']<stop-1e-10:continue
        if r['time_s']>stop+1.+1e-10:break
        if predicate(r):
            if since is None:since=r['time_s']
            if r['time_s']-since>=criteria['hold_s']-1e-12:return True
        else:since=None
    return False


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output cannot be regenerated')
    ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf-8'))
    assert ledger['status'] in ('complete','controlled_stop')
    criteria=finish_criteria();rows=[];archives={}
    for entry in ledger['episodes']:
        path=OUT/'run'/f"{entry['id']}.json.gz"
        assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['archive_sha256']
        d=read(path);archives[entry['id']]=d;r=d['trace'][-1];facts=d['guard_facts']
        stopped=bool(actual_stop_pass(d['stop_samples'],d['events'],entry['stop_time'],entry['end_time'],.0002)
                     and physical_tail_pass(d['stop_samples'],entry['end_time'],.0002))
        valid=facts['simulation_valid'];guard=bool(facts['contact_reasons'] or facts['motion_reasons'])
        peaks=entry['peaks'];peaks_ok=peaks['force_N']<criteria['force_N'] and peaks['torque_G_Nm']<criteria['torque_Nm'] and peaks['penetration_m']<criteria['penetration_m']
        functional=bool(valid and stopped and not guard and peaks_ok and hold_pass(d['trace'],entry['stop_time'],lambda x:functional_finish(x,criteria),criteria))
        strict=bool(functional and hold_pass(d['trace'],entry['stop_time'],lambda x:geometric_finish(x,criteria) and pin_fit(x),criteria))
        assert functional==(entry['outcome']['task_outcome']=='FULL_SUCCESS')
        q=np.array(r['quaternion_wxyz']);angle=2*math.degrees(math.acos(min(1.,abs(q[0])/np.linalg.norm(q))))
        rows.append(dict(id=entry['id'],outcome=entry['outcome']['task_outcome'],reason=entry['reason'],
            functional_success=functional,strict_precision_success=strict,valid=valid,stopped=stopped,
            xy_um=entry['xy_um'],angle_deg=angle,z_um=entry['z_um'],pin_clearance_um=pin_clearance_m(r)*1e6,
            peak_force_mN=peaks['force_N']*1000,peak_penetration_um=peaks['penetration_m']*1e6,
            control_cycles=entry['control_cycles'],physical_substeps=entry['physical_substeps'],
            contact_cycles=entry['contact_cycles'],search_cycles=entry['search_cycles'],
            stop_time_s=entry['stop_time'],end_time_s=entry['end_time'],
            controller_events=d['controller_events'],guard_facts=facts))
    summary=dict(status=ledger['status'],episodes=len(rows),unused_closed=ledger['unused_closed'],
        cumulative=117+len(rows),functional_success=sum(r['functional_success'] for r in rows),
        strict_precision_success=sum(r['strict_precision_success'] for r in rows),
        control_cycles=sum(r['control_cycles'] for r in rows),physical_substeps=sum(r['physical_substeps'] for r in rows),
        training_updates=0,network_calls=0,independent_tests=0,inputs_unchanged=ledger['inputs_unchanged'],rows=rows)
    (OUT/'assessment.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    old=read(ROOT/'deliverables/task_variants/clearance120_20261003/run/y_pos_150.json.gz')
    new=archives['y_pos_150']
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(3,1,figsize=(9,8),sharex=True,layout='constrained')
    for label,data in [('Old B2',old),('Loaded-rotation unload B2',new)]:
        trace=data['trace'];t=np.array([r['time_s'] for r in trace]);q=np.array([r['quaternion_wxyz'] for r in trace])
        angle=2*np.degrees(np.arccos(np.clip(np.abs(q[:,0])/np.linalg.norm(q,axis=1),0,1)))
        ax[0].plot(t,angle,label=label)
        ax[1].plot(t,[-r['contact_wrench_M'][2]*1000 for r in trace])
        ax[2].plot(t,[(r['position_m'][2]+.004)*1000 for r in trace])
    ax[0].axhline(2.5,ls='--',c='red',label='Unchanged rotation guard')
    for event in new['controller_events']:
        if event['phase'] in ('UNLOAD','SEARCH','WAIT_RECOVERY','FAILED'):
            for axis in ax:axis.axvline(event['time_s'],ls=':',c='gray',alpha=.5)
    ax[0].set_ylabel('Relative rotation (deg)');ax[0].legend(fontsize=8)
    ax[1].set_ylabel('Axial compression (mN)');ax[2].set_ylabel('Insertion advance (mm)');ax[2].set_xlabel('Simulation time (s)')
    for axis in ax:axis.grid(alpha=.2)
    fig.suptitle('Development case +Y 150 um: common B2 repair verification')
    fig.savefig(OUT/'results.png',dpi=150);fig.savefig(OUT/'results.pdf');plt.close(fig)
    if 'y_neg_150' in archives:
        data=archives['y_neg_150'];trace=data['trace']
        guard_time=next(e['time_s'] for e in data['events'] if e['reason']=='FORCE_LIMIT')
        pre=max((r for r in trace if r['time_s']<guard_time),key=lambda r:r['time_s'])
        w=np.array(pre['contact_wrench_M'][:3])
        from tools.control.search_recovery import SearchRecovery,SearchConfig,Observation
        from tools.control.risk_search import RiskSearchRecovery,PoseObservation
        from tools.learning.guarded_environment import relative_rotation_rad
        config=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'))
        original=SearchRecovery(SearchConfig(**config['b2_config']));revised=RiskSearchRecovery(SearchConfig(**config['b2_config']))
        initial=trace[0];same=True;compared=0
        for r in trace:
            if r['time_s']>=guard_time:break
            obs=Observation(r['time_s'],tuple(np.array(r['position_m'])-initial['position_m']),tuple(r['contact_wrench_M']))
            pose=PoseObservation(obs.time_s,obs.displacement_m,obs.wrench_M,relative_rotation_rad(initial['quaternion_wxyz'],r['quaternion_wxyz']))
            same=bool(same and np.array_equal(original.command(obs,.002),revised.command(pose,.002)))
            compared+=1
        diagnosis=dict(guard_time_s=guard_time,physical_peak_force_N=data['summary']['peaks']['force_N'],
            preceding_control_sample_time_s=pre['time_s'],preceding_force_M_N=w.tolist(),
            preceding_lateral_force_mN=float(np.linalg.norm(w[:2])*1000),preceding_axial_force_mN=float(-w[2]*1000),
            preceding_total_force_mN=float(np.linalg.norm(w)*1000),
            loaded_rotation_events=sum(e['reason']=='LOADED_ROTATION_RISK' for e in data['controller_events']),
            old_new_controller_commands_equal_on_saved_observations=same,compared_samples=compared,
            scope='offline input replay, not an additional old-controller dynamic experiment',
            finding='Search regulates axial load but spiral/tracking can build lateral load; small rotation does not activate INSERT-only rotation trigger')
        (OUT/'negative_y_diagnosis.json').write_text(json.dumps(diagnosis,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        t=np.array([r['time_s'] for r in trace]);w=np.array([r['contact_wrench_M'][:3] for r in trace])*1000
        fig,axes=plt.subplots(2,1,figsize=(9,6),sharex=True,layout='constrained')
        axes[0].plot(t,np.linalg.norm(w,axis=1),label='Total contact force')
        axes[0].plot(t,np.linalg.norm(w[:,:2],axis=1),label='Lateral force')
        axes[0].plot(t,-w[:,2],label='Axial compression')
        axes[0].axhline(25,ls='--',c='red',label='Unchanged total-force guard')
        axes[0].set_ylabel('Force (mN)');axes[0].legend(fontsize=8)
        axes[1].plot(t,[(r['position_m'][2]+.004)*1000 for r in trace],label='Actual insertion advance')
        axes[1].set_ylabel('Advance (mm)');axes[1].set_xlabel('Simulation time (s)');axes[1].legend(fontsize=8)
        for axis in axes:axis.axvline(guard_time,ls=':',c='red');axis.grid(alpha=.2)
        fig.suptitle('Development case -Y 150 um: unresolved lateral loading in SEARCH')
        fig.savefig(OUT/'negative_y_failure.png',dpi=150);fig.savefig(OUT/'negative_y_failure.pdf');plt.close(fig)
    print(json.dumps({k:v for k,v in summary.items() if k!='rows'},ensure_ascii=False))


if __name__=='__main__':main()
