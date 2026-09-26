"""Reproduction v2: actual stop clock and tagged invalid archives for seven-case B1/B2 reevaluation in the exact isolated 3.13 runtime."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'deliverables/native313_baseline_matrix'


def classify_episode(*,termination,phase,events,finite,stopped,safe,final_geometry):
    invalid=not finite or any('INVALID' in e['reason'] or e['reason'] in ('SIMULATION_ERROR','OUT_OF_BOUNDS') for e in events)
    invalid=invalid or 'INVALID' in termination or termination in ('SIMULATION_ERROR','OUT_OF_BOUNDS')
    guard=any(any(k in e['reason'] for k in ('FORCE_LIMIT','TORQUE_LIMIT','PENETRATION_LIMIT')) for e in events)
    full=bool(not invalid and stopped and safe and final_geometry and termination=='GEOMETRIC_SUCCESS' and phase=='STOPPING')
    if invalid:category='INVALID_SIMULATION'
    elif not stopped or phase!='STOPPING':category='STOP_NOT_QUALIFIED'
    elif not safe:category='VALID_GUARD_FAILURE' if guard else 'UNEXPLAINED_SAFETY_FAILURE'
    elif full:category='FULL_SUCCESS'
    else:category='VALID_TASK_FAILURE'
    return dict(category=category,full_success=full,numerically_valid=not invalid,
                candidate_data_valid=category in ('FULL_SUCCESS','VALID_TASK_FAILURE','VALID_GUARD_FAILURE'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--policy',choices=['b1','b2'],required=True)
    p.add_argument('--tag',required=True)
    p.add_argument('--package-path',type=Path,required=True)
    args=p.parse_args();sys.path.insert(0,str(args.package_path.resolve()))
    import mujoco
    import numpy as np
    from tools.validation.validate_training_readiness import sha,verify_hashes,new_target
    from tools.validation.run_native313_stop import verify_static_dependencies
    from tools.validation.verify_native313_delivery import main as prior_verify
    from tools.dynamics.contact_candidate import candidate_environment
    from tools.control.fixed_admittance import FixedAdmittance
    from tools.control.search_recovery import SearchRecovery,SearchConfig
    from tools.validation.run_b1_baseline import cases,run_episode,geometric_finish,dump as strict_dump,FINISH
    from tools.validation.run_b2_search import hashes,run_search_episode,save_run as strict_save_run
    from tools.validation.native313_matrix_audit import archive_nonfinite,actual_stop_start,actual_stop_pass,samples_finite
    def save_run(path,value):strict_save_run(path,archive_nonfinite(value))
    def dump(path,value):strict_dump(path,archive_nonfinite(value))
    from tools.validation.run_contact_candidate_stop import stop_steps,physical_tail_pass
    from tools.validation.measure_readiness_stop import stop_qualified
    target=new_target(OUT,args.tag)
    previous=ROOT/'deliverables/native313_validation'
    runtime=json.loads((previous/'compatibility_3.13.0.json').read_text(encoding='utf-8'))
    if mujoco.__version__!='3.13.0' or Path(mujoco.__file__).resolve()!=Path(runtime['module_file']).resolve():
        raise ValueError('Use the exact qualified isolated runtime')
    verify_hashes(ROOT,runtime['dll_sha256']);verify_static_dependencies();prior_verify()
    assessment=json.loads((previous/'report_v1/assessment.json').read_text(encoding='utf-8'))
    assert assessment['status']=='READY_FOR_PAIRED_BASELINE_REEVALUATION'
    oldpath=ROOT/'deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json'
    old=json.loads(oldpath.read_text(encoding='utf-8'));verify_hashes(ROOT,old['source_sha256'])
    historical=old['historical_source_sha256'];verify_hashes(ROOT,historical)
    config=SearchConfig(**old['config'])
    code={**hashes(),**{name:sha(ROOT/name) for name in [
        'tools/dynamics/contact_candidate.py','tools/validation/run_contact_candidate_stop.py',
        'tools/validation/measure_readiness_stop.py','tools/validation/run_native313_matrix.py',
        'tools/validation/run_native313_matrix_v2.py','tools/validation/native313_matrix_audit.py',
        'tools/validation/run_native313_stop.py','tools/validation/run_native313_validation.py']}}
    protected={**code,**runtime['dll_sha256'],**{p.relative_to(ROOT).as_posix():sha(p) for p in [
        oldpath,OUT/'执行协议.md',previous/'report_v1/assessment.json',previous/'compatibility_3.13.0.json',
        ROOT/'deliverables/baseline_training_readiness/数据划分_v1.json']}}
    target.mkdir(parents=True)
    for name in code:
        dest=target/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/name).read_bytes())
    status=dict(status='RUNNING',policy=args.policy,mujoco_version=mujoco.__version__,module_file=mujoco.__file__,
                config=asdict(config),cases=[asdict(c) for c in cases()],finish_criteria=FINISH,
                protected_inputs=protected,historical_source_sha256=historical,runs=[])
    dump(target/'results_index.json',status)
    for case in cases():
        folder=target/case.name;folder.mkdir();partial=[];started=time.perf_counter()
        env=candidate_environment(timestep=.0002);original_step=env.step;next_progress=[5.]
        def capture(command):
            row=original_step(command);partial.append(dict(row))
            if row['time_s']>=next_progress[0]:
                print(args.policy,case.name,'t',round(row['time_s'],3),'phase',env.phase,flush=True);next_progress[0]+=5.
            return row
        env.step=capture
        print('START',args.policy,case.name,flush=True)
        try:
            with stop_steps(env) as samples:
                if args.policy=='b1':
                    run=run_episode(env,case,FixedAdmittance(),max_time=config.total_action_time_s,settle_time=config.settle_time_s)
                else:run=run_search_episode(env,case,SearchRecovery(config))
                save_run(folder/'original.json.gz',run)
                stop=actual_stop_start(env.events,run['stop_time_s']);extension=[env.observe()]
                if stop is not None:
                    while env.phase=='STOPPING' and env.data.time<stop+2.-1e-10:
                        extension.append(env.step(np.zeros(6)))
            end=float(env.data.time);tail=samples_finite(samples) and physical_tail_pass(samples,end,.0002)
            budget_pass=actual_stop_pass(samples,env.events,run['stop_time_s'],end,.0002)
            stopped=bool(budget_pass and env.phase=='STOPPING' and tail)
            finite=bool(env._state_valid())
            safe=bool(stop is not None and stop_qualified(phase=env.phase,events=env.events,recorded_time_s=end,
                      deadline_s=stop+2.,confirmed=budget_pass,final_stable=tail,peaks=env.peaks))
            result=classify_episode(termination=run['termination'],phase=env.phase,events=env.events,
                        finite=finite,stopped=stopped,safe=safe,final_geometry=geometric_finish(env.observe()))
            save_run(folder/'stop_extension.json.gz',dict(trace=extension,physical_stop_samples=samples,
                                                         events=env.events,peaks=env.peaks))
            verify_hashes(ROOT,protected);verify_hashes(ROOT,historical)
            record=dict(status='COMPLETE',policy=args.policy,case=asdict(case),termination=run['termination'],
                        stop_time_s=stop,recorded_stop_decision_s=run['stop_time_s'],end_time_s=end,physical_stopped=stopped,physical_tail_pass=bool(tail),
                        strict_safe_stop=safe,finite=finite,final=env.observe(),events=env.events,peaks=env.peaks,
                        search_count=run.get('search_count',0),recovery_count=env.recovery_count,
                        wall_seconds=time.perf_counter()-started,physical_stop_samples=len(samples),**result,
                        files={p.name:sha(p) for p in folder.glob('*.json.gz')})
            dump(folder/'audit.json',record)
            status['runs'].append(dict(case=case.name,file=(folder/'audit.json').relative_to(target).as_posix(),
                                       sha256=sha(folder/'audit.json'),category=record['category'],full_success=record['full_success']))
            dump(target/'results_index.json',status)
            print('DONE',args.policy,case.name,record['category'],record['termination'],
                  'stop',stopped,'max_depth_um',env.peaks['penetration_m']*1e6,flush=True)
        except (Exception,KeyboardInterrupt) as error:
            save_run(folder/'partial.json.gz',dict(trace=partial,error=repr(error)))
            status.update(status='ERROR',error=repr(error),failed_case=case.name)
            dump(target/'results_index.json',status);raise
    verify_hashes(ROOT,protected);verify_hashes(ROOT,historical)
    status['status']='COMPLETE';dump(target/'results_index.json',status)
    print('COMPLETE',args.policy,len(status['runs']),'prespecified cases',flush=True)


if __name__=='__main__':main()
