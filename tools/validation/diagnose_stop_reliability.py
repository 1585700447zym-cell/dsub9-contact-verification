"""Bounded same-checkpoint diagnostics of passive stopping, not a new baseline."""
import argparse
import copy
from contextlib import contextmanager
from dataclasses import replace
import json
import time
import mujoco
import numpy as np
from tools.dynamics.cartesian import CartesianEnvironment
from tools.control.search_recovery import SearchRecovery,SearchConfig
from tools.reporting.report_b2 import verified
from tools.validation.run_b1_baseline import cases,dump
from tools.validation.run_b2_search import hashes,run_search_episode,save_run,read_run
from tools.validation.validate_training_readiness import ROOT,sha,verify_hashes,new_target
from tools.validation.diagnose_v1_applicability import fingerprint

OUT=ROOT/'deliverables/stop_reliability'
PRIOR=ROOT/'deliverables/baseline_training_readiness/old_b2_y_stop_extension_v1'


def clone_environment(source):
    result=object.__new__(CartesianEnvironment)
    for key,value in vars(source).items():
        if key not in ('model','data'):
            if callable(value):raise ValueError('Remove instance instrumentation before cloning')
            setattr(result,key,copy.deepcopy(value))
    result.model=copy.deepcopy(source.model)
    result.data=mujoco.MjData(result.model)
    mujoco.mj_copyData(result.data,result.model,source.data)
    return result


@contextmanager
def integration_capture(env):
    original=mujoco.mj_step;records=[];mass=env.model.body_mass[env.male]
    def step(model,data):
        if data is not env.data:return original(model,data)
        before=data.qvel[:3].copy();start=float(data.time);applied=data.qfrc_applied[:3].copy()
        original(model,data)
        # This force was used by mj_step, before the caller's post-step mj_forward.
        acceleration=(data.qvel[:3]-before)/model.opt.timestep
        total=data.qfrc_smooth[:3]+data.qfrc_constraint[:3]
        records.append({'evaluated_at_s':start,'integrated_to_s':float(data.time),
                        'velocity_before_m_s':before.tolist(),'velocity_after_m_s':data.qvel[:3].tolist(),
                        'applied_N':applied.tolist(),'integration_constraint_N':data.qfrc_constraint[:3].tolist(),
                        'qacc_translation_m_s2':data.qacc[:3].tolist(),
                        'translation_balance_residual_N':(mass*acceleration-total).tolist(),
                        'contact_count':int(data.ncon),'constraint_rows':int(data.nefc),
                        'solver_iterations':int(np.max(data.solver_niter)),
                        'minimum_contact_distance_m':float(np.min(data.contact.dist)) if data.ncon else None})
    mujoco.mj_step=step
    try:yield records
    finally:mujoco.mj_step=original


def summarize(env,rows,steps,initial_time):
    vel=np.array([r['velocity_world'] for r in rows]);linear=np.linalg.norm(vel[:,:3],axis=1);angular=np.linalg.norm(vel[:,3:],axis=1)
    since=None;longest=0.;first=None
    for r,l,a in zip(rows,linear,angular):
        stable=l<=1e-5 and a<=.001
        since=r['time_s'] if stable and since is None else since if stable else None
        if since is not None:
            longest=max(longest,r['time_s']-since)
            if first is None and r['time_s']-since>=.1-1e-9:first=r['time_s']-initial_time
    invalid=any('INVALID' in e['reason'] or e['reason'] in ('SIMULATION_ERROR','OUT_OF_BOUNDS') for e in env.events)
    values=[r['position_m']+r['velocity_world']+r['contact_wrench_G'] for r in rows]
    finite=bool(np.isfinite(values).all())
    coverage=rows[-1]['time_s']>=initial_time+1-1e-9
    tail_stable=since is not None and rows[-1]['time_s']-since>=.1-1e-9
    forces=np.array([r['integration_constraint_N'] for r in steps]);iterations=np.array([r['solver_iterations'] for r in steps])
    return {'valid':bool(finite and not invalid and env.phase=='STOPPING' and coverage),
            'settled_at_end':bool(finite and not invalid and env.phase=='STOPPING' and coverage and tail_stable),
            'final_linear_um_s':float(linear[-1]*1e6),'final_angular_rad_s':float(angular[-1]),
            'longest_stable_span_s':longest,'first_confirmation_after_checkpoint_s':first,
            'sampled_linear_rms_um_s':float(np.sqrt(np.mean(linear**2))*1e6),
            'integration_force_peak_mN':float(np.max(np.linalg.norm(forces,axis=1))*1000),
            'post_forward_force_peak_mN':float(max(np.linalg.norm(r['contact_wrench_M'][:3]) for r in rows)*1000),
            'max_integration_balance_error_N':float(max(np.linalg.norm(r['translation_balance_residual_N']) for r in steps)),
            'solver_iteration_min_max':[int(iterations.min()),int(iterations.max())],
            'solver_iteration_cap_hits':int(np.sum(iterations>=env.model.opt.iterations)),
            'position_range_per_axis_um':(np.ptp(np.array([r['position_m'] for r in rows]),axis=0)*1e6).tolist(),
            'new_control_steps':len(rows)-1,'new_physical_steps':len(steps)}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--tag',required=True);args=parser.parse_args()
    target=new_target(OUT,args.tag)
    folder,index,old=verified('matrix_v1_7cases')
    reference=next(r for r in old if r['case']['name']=='y_offset_neg_100um' and 'search_count' in r)
    prior=json.loads((PRIOR/'results_index.json').read_text(encoding='utf-8'))
    verify_hashes(PRIOR,prior['files']);verify_hashes(ROOT,index['source_sha256'])
    history=fingerprint();assert history==index['historical_source_sha256']
    code={**hashes(),'tools/validation/diagnose_stop_reliability.py':sha(ROOT/'tools/validation/diagnose_stop_reliability.py')}
    protected={**code,(OUT/'诊断协议.md').relative_to(ROOT).as_posix():sha(OUT/'诊断协议.md'),
               (PRIOR/'results_index.json').relative_to(ROOT).as_posix():sha(PRIOR/'results_index.json')}
    target.mkdir(parents=True)
    for name in code:
        dest=target/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/name).read_bytes())
    (target/'诊断协议.md').write_bytes((OUT/'诊断协议.md').read_bytes())
    status={'status':'RUNNING_PREFIX','protected_inputs':protected,'source_sha256':code,'historical_source_sha256':history,
            'mujoco_version':mujoco.__version__,'branches':[]}
    dump(target/'results_index.json',status)
    partial=[];env=CartesianEnvironment(segments=256);original=env.step
    def capture(command):
        row=original(command);partial.append(dict(row));return row
    env.step=capture
    try:
        case=next(c for c in cases() if c.name=='y_offset_neg_100um')
        run=run_search_episode(env,case,SearchRecovery(SearchConfig(**index['config'])))
        del env.step
        status['prefix_exact']=all(run[k]==reference[k] for k in ('trace','events','peaks','termination','physical_steps','environment'))
        if not status['prefix_exact']:raise ValueError('Original trajectory failed exact reproduction')
        save_run(target/'reproduced_prefix.json.gz',run)
        checkpoint=clone_environment(env);checkpoint_time=float(env.data.time)
        signature=mujoco.mjtState.mjSTATE_INTEGRATION
        state=np.empty(mujoco.mj_stateSize(env.model,signature));mujoco.mj_getState(env.model,env.data,state,signature)
        np.savez_compressed(target/'checkpoint_integration_state.npz',state=state,signature=int(signature),reference=env.reference)
        status.update(status='RUNNING_BRANCHES',checkpoint_time_s=checkpoint_time,original_stop_time_s=run['stop_time_s'],
                      solver={'type':int(env.model.opt.solver),'iterations':env.model.opt.iterations,'tolerance':env.model.opt.tolerance,
                              'cone':int(env.model.opt.cone),'integrator':int(env.model.opt.integrator)})
        dump(target/'results_index.json',status)
        previous=read_run(PRIOR/'passive_extension.json.gz')
        for name,dt,contacts in [('baseline_0p2ms',.0002,True),('half_0p1ms',.0001,True),
                                  ('quarter_0p05ms',.00005,True),('contact_disabled',.0002,False)]:
            branch=clone_environment(checkpoint);branch.config=replace(branch.config,timestep=dt);branch.model.opt.timestep=dt
            if not contacts:
                branch.model.geom_contype[:]=0;branch.model.geom_conaffinity[:]=0;branch.contacts_enabled=False
            rows=[branch.observe()];start=time.perf_counter()
            print('BRANCH',name,flush=True)
            with integration_capture(branch) as physics:
                for _ in range(500):
                    rows.append(branch.step(np.zeros(6)))
                    if branch.phase=='TERMINAL':break
            exact=rows==previous['trace'] if name=='baseline_0p2ms' else None
            result={'name':name,'metadata':branch.metadata(),'diagnostic_only':True,'reference_exact':exact,
                    'trace':rows,'integration_steps':physics,'events':branch.events,
                    'summary':summarize(branch,rows,physics,checkpoint_time),'wall_seconds':time.perf_counter()-start}
            file=name+'.json.gz';save_run(target/file,result)
            entry={'name':name,'file':file,'sha256':sha(target/file),'reference_exact':exact,'summary':result['summary'],'wall_seconds':result['wall_seconds']}
            status['branches'].append(entry);dump(target/'results_index.json',status);print(json.dumps(entry),flush=True)
            if exact is False:raise ValueError('Cloning/instrumentation altered baseline continuation')
        verify_hashes(ROOT,protected);assert fingerprint()==history
        status.update(status='COMPLETE',files={p.name:sha(p) for p in target.iterdir() if p.suffix in ('.gz','.npz')})
        dump(target/'results_index.json',status)
    except (Exception,KeyboardInterrupt) as error:
        status.update(status='ERROR',error=repr(error))
        if partial:save_run(target/'partial_prefix.json.gz',{'trace':partial,'termination':'INCOMPLETE_ERROR'})
        dump(target/'results_index.json',status);raise


if __name__=='__main__':main()
