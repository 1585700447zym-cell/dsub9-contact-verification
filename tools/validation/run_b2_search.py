"""Versioned B2 pilot / paired development matrix with preserved B1 inputs."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import time
import numpy as np

from tools.control.fixed_admittance import FixedAdmittance
from tools.control.search_recovery import SearchConfig, SearchRecovery, Observation, resume_after_recovery, latched_contact_guard
from tools.dynamics.cartesian import CartesianEnvironment
from tools.validation.run_b1_baseline import cases, run_episode, FINISH, geometric_finish, hashes as b1_hashes, dump
from tools.validation.run_contact_cases import ROOT
from tools.validation.diagnose_v1_applicability import fingerprint
from tools.reporting.report_b1 import read_verified

OUT=ROOT/'deliverables/b2_search_recovery'


def hashes():
    result=b1_hashes()
    for file in ('tools/control/search_recovery.py','tools/validation/run_b2_search.py'):
        result[file]=hashlib.sha256((ROOT/file).read_bytes()).hexdigest()
    return result


def read_run(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)


def save_run(path,run):
    # Deterministic gzip header; preserve all 2 ms samples, no trace decimation.
    path.write_bytes(gzip.compress(json.dumps(run,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode('utf-8'),mtime=0))


def policy_observation(row,initial):
    return Observation(row['time_s'],tuple(np.asarray(row['position_m'])-initial),tuple(row['contact_wrench_M']))


def stable_for_recovery(env):
    r=env.observe();c=env.config
    return (not latched_contact_guard(env) and np.linalg.norm(r['velocity_world'][:3])<=c.stopped_speed and
            np.linalg.norm(r['velocity_world'][3:])<=c.stopped_angular_speed and
            np.linalg.norm(r['contact_wrench_M'][:3])<=c.recovery_force_N and
            np.linalg.norm(r['contact_wrench_G'][3:])<=c.stop_torque_Nm and r['penetration_m']<c.stop_penetration_m)


def run_search_episode(env,case,controller):
    env.reset(case);c=controller.config;dt=env.config.control_period
    initial=np.array(env.observe()['position_m']);trace=[]
    reason=None;stop_time=None;hold_start=None;recovery_state=None;wait_start=None
    start=time.perf_counter();guard_latched=False;next_progress=1.

    def record(row):
        row.update(policy_phase=controller.phase,search_count=controller.search_count,
                   spiral_theta_rad=controller.theta,admittance_velocity=controller.admittance.velocity.tolist(),
                   commanded_correction=controller.admittance.offset.tolist(),recovery_state=recovery_state)
        trace.append(row)

    def finish(why):
        nonlocal reason,stop_time,recovery_state
        reason=why;stop_time=float(env.data.time);recovery_state=None
        if env.phase not in ('TERMINAL','STOPPING'):env.stop(why)

    record(env.observe())
    for _ in range(math.ceil((c.total_action_time_s+c.settle_time_s)/dt)+1):
        row=env.observe();obs=policy_observation(row,initial);command=np.zeros(6)
        if env.phase=='TERMINAL':reason=env.events[-1]['reason'];break
        if reason is None and row['time_s']>=c.total_action_time_s-1e-10:finish('TIME_LIMIT')
        if reason is None:
            if recovery_state=='WAIT_STOP':
                if stable_for_recovery(env):
                    try:env.request_recovery();recovery_state='RETRACT'
                    except RuntimeError:finish('RECOVERY_REJECTED')
                elif row['time_s']-wait_start>=c.wait_stable_s:finish('RECOVERY_NOT_STABLE')
            elif recovery_state=='WAIT_RESUME':
                if stable_for_recovery(env):
                    try:
                        resume_after_recovery(env,c.recovery_min_actual_m)
                        controller.start_recovered_search(obs);recovery_state=None
                    except RuntimeError:finish('RECOVERY_RESUME_REJECTED')
                elif row['time_s']-wait_start>=c.wait_stable_s:finish('RECOVERY_NOT_STABLE')
            if recovery_state is None and reason is None:
                command=controller.command(obs,dt)
                if controller.phase=='FAILED':finish(controller.reason)
                elif controller.phase=='WAIT_RECOVERY':
                    env.stop('B2_SEARCH_EXHAUSTED');recovery_state='WAIT_STOP';wait_start=row['time_s']
        row=env.step(command);record(row)
        if env.phase=='TERMINAL':reason=env.events[-1]['reason'];break
        guard_reason=latched_contact_guard(env)
        if guard_reason and not guard_latched:
            guard_latched=True
            env.events.append({'time_s':row['time_s'],'reason':'B2_LATCHED_'+guard_reason,'phase':env.phase})
            finish(guard_reason)
        if row['time_s']>=next_progress:
            print(f"  t={row['time_s']:.1f}s phase={controller.phase}/{env.phase} advance={(row['position_m'][2]-initial[2])*1000:.3f}mm",flush=True)
            next_progress+=1.
        if reason is None and env.phase=='STOPPING':
            why=env.events[-1]['reason']
            if recovery_state=='RETRACT' and why=='RECOVERY_DISTANCE_REACHED':
                recovery_state='WAIT_RESUME';wait_start=row['time_s']
            elif recovery_state in ('WAIT_STOP','WAIT_RESUME') and why in ('B2_SEARCH_EXHAUSTED','RECOVERY_DISTANCE_REACHED'):
                pass
            else:finish(why)
        if reason is None and env.phase=='RUNNING' and row['position_m'][2]>=-10e-6:finish('TARGET_PLANE_REACHED')
        if reason is not None:
            peaks_ok=(env.peaks['force_N']<FINISH['force_N'] and env.peaks['torque_G_Nm']<FINISH['torque_Nm']
                      and env.peaks['penetration_m']<FINISH['penetration_m'])
            if reason=='TARGET_PLANE_REACHED' and geometric_finish(row) and peaks_ok:
                if hold_start is None:hold_start=row['time_s']
                if row['time_s']-hold_start>=FINISH['hold_s']-1e-12:reason='GEOMETRIC_SUCCESS';break
            else:hold_start=None
            if row['time_s']-stop_time>=c.settle_time_s-1e-10:
                if reason=='TARGET_PLANE_REACHED':reason='TARGET_POSE_NOT_SETTLED'
                break
    elapsed=time.perf_counter()-start
    return {'case':asdict(case),'controller':controller.metadata(),'environment':env.metadata(),
            'termination':reason or 'TIME_LIMIT','finish_criteria':FINISH,'max_time_s':c.total_action_time_s,'settle_time_s':c.settle_time_s,
            'contact_observed':env.first_contact is not None,'first_contact':env.first_contact,'stop_time_s':stop_time,
            'final':env.observe(),'peaks':env.peaks,'events':env.events,'policy_events':controller.events,
            'search_count':controller.search_count,'recovery_count':env.recovery_count,'physical_steps':env.physical_steps,
            'controller_limited_steps':controller.admittance.limited_steps,'control_steps':len(trace)-1,
            'trace':trace,'wall_seconds':elapsed,'physical_steps_per_second':env.physical_steps/elapsed,
            'scope':'fixed_development_cases_not_statistical_success_rate_or_hardware_validation'}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case',choices=[c.name for c in cases()])
    parser.add_argument('--tag',required=True,help='New, preserved output folder; never overwrite an earlier attempt')
    parser.add_argument('--config',default='deliverables/b2_search_recovery/candidate_v1.json')
    parser.add_argument('--b2-only',action='store_true',help='Pilot only; a full comparison always pairs both policies')
    args=parser.parse_args()
    if Path(args.tag).name!=args.tag or args.tag in ('.','..'):raise ValueError('Use one plain folder name')
    target=OUT/args.tag
    if target.exists():raise FileExistsError('Preserve previous attempts; choose a new tag')
    raw=json.loads((ROOT/args.config).read_text(encoding='utf-8'));candidate=raw.pop('candidate');config=SearchConfig(**raw)
    if args.b2_only and not args.case:raise ValueError('B2-only is limited to a single pilot')
    read_verified();code=hashes();historical=fingerprint()
    target.mkdir(parents=True);(target/'runs').mkdir()
    for relative in code:
        snapshot=target/'source_snapshot'/relative;snapshot.parent.mkdir(parents=True,exist_ok=True)
        snapshot.write_bytes((ROOT/relative).read_bytes())
    protocol={'candidate':candidate,'config':asdict(config),'source_sha256':code,'historical_source_sha256':historical,
              'case_names':[c.name for c in cases() if not args.case or c.name==args.case],
              'paired':not args.b2_only,'runs':[],'status':'RUNNING'}
    dump(target/'results_index.json',protocol)
    env=CartesianEnvironment(segments=256)
    for case in cases():
        if args.case and case.name!=args.case:continue
        for policy in (['b2'] if args.b2_only else ['b1','b2']):
            print(f'START {case.name} {policy}',flush=True)
            if policy=='b1':run=run_episode(env,case,FixedAdmittance(),max_time=config.total_action_time_s,settle_time=config.settle_time_s)
            else:run=run_search_episode(env,case,SearchRecovery(config))
            run.update(source_sha256=code,historical_source_sha256=historical,candidate=candidate)
            name=f'runs/{case.name}_{policy}.json.gz';save_run(target/name,run)
            entry={'file':name,'sha256':hashlib.sha256((target/name).read_bytes()).hexdigest(),'case':case.name,'policy':policy,
                   'termination':run['termination'],'advance_mm':(run['final']['position_m'][2]-case.start_origin_z_m)*1000,
                   'end_time_s':run['final']['time_s'],'peak_force_N':run['peaks']['force_N'],
                   'peak_penetration_m':run['peaks']['penetration_m'],'search_count':run.get('search_count',0),
                   'recovery_count':run.get('recovery_count',0),'wall_seconds':run['wall_seconds']}
            protocol['runs'].append(entry);dump(target/'results_index.json',protocol);print(json.dumps(entry),flush=True)
    if code!=hashes() or historical!=fingerprint():raise RuntimeError('Inputs changed during B2 evaluation')
    protocol['status']='COMPLETE';dump(target/'results_index.json',protocol)


if __name__=='__main__':main()
