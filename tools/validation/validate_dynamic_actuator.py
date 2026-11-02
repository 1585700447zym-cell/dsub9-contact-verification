"""Reproducible dynamic-drive evidence; endpoint arrival is not assembly success."""
from dataclasses import asdict, replace
import hashlib
import json
import math
from pathlib import Path
import platform
import time
import argparse

import mujoco
import numpy as np

from tools.dynamics.cartesian import CartesianEnvironment, DynamicConfig
from tools.validation.run_contact_cases import ROOT, ContactCase
from tools.validation.diagnose_v1_applicability import fingerprint

OUTPUT=ROOT/'deliverables/dynamic_actuator_v1'


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def sources():
    files=[ROOT/'tools/model/contact_development.py',ROOT/'tools/validation/validate_dynamic_actuator.py']
    files+=list((ROOT/'tools/dynamics').glob('*.py'))+list((ROOT/'tests/dynamics').glob('*.py'))
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}


def scenarios():
    out=[('aligned_full',ContactCase.aligned(),4.10,False)]
    for base in (ContactCase.combined(),ContactCase.combined_b()):
        for scale in (.5,.75):
            c=replace(base,name=base.name+f'_scale_{scale}',x_offset_m=base.x_offset_m*scale,
                      y_offset_m=base.y_offset_m*scale,roll_rad=base.roll_rad*scale,pitch_rad=base.pitch_rad*scale)
            out.append((c.name,c,1.2,True))
    out.append(('pressure_a',ContactCase.combined(),1.2,True))
    out.append(('lateral_x',ContactCase.x_offset(100e-6),1.2,True))
    return out


def run_episode(env,name,case,duration,recover=False,command=None):
    env.reset(case); trace=[env.observe()]; wall=time.perf_counter()
    cmd=np.array([0,0,.001,0,0,0] if command is None else command,dtype=float)
    end_drive=None;stop_check=None;first_stop=None
    for _ in range(round(duration/env.config.control_period)):
        row=env.step(cmd);trace.append(row)
        if env.phase in ('STOPPING','TERMINAL'):break
    end_drive=env.observe()
    if env.phase!='TERMINAL':
        if env.phase!='STOPPING':env.stop('DRIVE_WINDOW_ENDED')
        first_stop=dict(env.stop_snapshot)
        stop_check=end_drive
        for _ in range(round(.25/env.config.control_period)):
            trace.append(env.step(np.zeros(6)))
            if trace[-1]['time_s']<=first_stop['time_s']+.2+1e-10:
                stop_check=trace[-1]
            if env.phase=='TERMINAL':break
        if env.data.time<first_stop['time_s']+.2-1e-10:stop_check=None
    stopped=env.observe();recovery='NOT_REQUESTED'
    if recover and env.phase!='TERMINAL':
        try:
            env.request_recovery();recovery='ACCEPTED'
        except RuntimeError:
            recovery='REFUSED_PRECONDITIONS'
        if recovery=='ACCEPTED':
            for _ in range(round(.85/env.config.control_period)):
                trace.append(env.step(np.zeros(6)))
                if env.phase=='TERMINAL':break
    elapsed=time.perf_counter()-wall
    # A contact-free route to this plane only validates free-space tracking.
    desired=np.array(trace[0]['position_m'])+cmd[:3]*max(0.,duration-env.config.linear_speed/env.config.linear_acceleration/2)
    return {'name':name,'case':asdict(case),'command_world':cmd.tolist(),'drive_duration_s':duration,
            'metadata':env.metadata(),'end_drive':end_drive,'stopped':stopped,'stop_check_0p2':stop_check,'final':env.observe(),
            'peaks':env.peaks,'first_contact':env.first_contact,'first_stop_snapshot':first_stop,
            'final_stop_snapshot':env.stop_snapshot,
            'events':env.events,'recovery':recovery,'trace':trace,
            'physical_steps':env.physical_steps,'control_steps':len(trace)-1,
            'drive_saturation_steps':env.drive_saturation_steps,
            'reference_limited_steps':env.reference_limited_steps,'command_limited_steps':env.command_limited_steps,
            'free_tracking_error_m':float(np.linalg.norm(np.array(end_drive['position_m'])-desired)),
            'timing':{'wall_seconds':elapsed,'physical_steps_per_second':env.physical_steps/elapsed,
                      'control_steps_per_second':(len(trace)-1)/elapsed,
                      'includes_python_drive_guard_and_logging':True,'excludes_model_compilation':True}}


def orientation_difference(a,b):
    dot=abs(float(np.dot(a,b)))
    return 2*math.acos(min(1.,max(-1.,dot)))


def compare(a,b):
    pa=np.array(a['end_drive']['position_m']);pb=np.array(b['end_drive']['position_m'])
    df=float(np.linalg.norm(pa-pb))
    da=orientation_difference(a['end_drive']['quaternion_wxyz'],b['end_drive']['quaternion_wxyz'])
    fa=a['peaks']['force_N'];fb=b['peaks']['force_N']
    force_difference=abs(fa-fb)/max(fa,fb) if max(fa,fb)>.001 else None
    reasons_a=[e['reason'] for e in a['events']];reasons_b=[e['reason'] for e in b['events']]
    return {'case':a['name'],'end_drive_position_difference_m':df,'end_drive_angle_difference_rad':da,
            'peak_force_relative_difference':force_difference,'same_events':reasons_a==reasons_b,
            'pass':df<20e-6 and da<math.radians(.1) and reasons_a==reasons_b
                   and (force_difference is None or force_difference<.2)}


def evaluate(runs,free_axes,counterfactual,guard_test):
    base=runs['n128_dt0.0002']
    comparisons={key:[compare(a,b) for a,b in zip(base,rows)] for key,rows in runs.items() if key!='n128_dt0.0002'}
    contact=next(r for r in base if r['name']=='combined_a_scale_0.75')
    displacement=float(np.linalg.norm(np.array(contact['end_drive']['position_m'])-
                                     np.array(counterfactual['end_drive']['position_m'])))
    all_runs=[r for rows in runs.values() for r in rows]+free_axes+[counterfactual,guard_test]
    free=base[0]
    gates={'free_tracking':free['free_tracking_error_m']<50e-6,
           'stops':all(r['stop_check_0p2'] is not None and np.linalg.norm(r['stop_check_0p2']['velocity_world'][:3])<1e-5 for r in all_runs),
           'finite_no_simulation_error':all(not any(e['reason'] in ('INVALID_SIMULATION','INVALID_PENETRATION','SIMULATION_ERROR','OUT_OF_BOUNDS') for e in r['events']) for r in all_runs),
           'effort_bounded':all(max(r['peaks']['drive_force_components_N'])<=r['metadata']['config']['force_limit_N']+1e-12 and max(r['peaks']['drive_torque_components_Nm'])<=r['metadata']['config']['torque_limit_Nm']+1e-12 for r in all_runs),
           'contact_changes_trajectory':displacement>2e-6,
           'force_guard_triggered':any('FORCE_LIMIT' in e['reason'] for e in guard_test['events']),
           'recovery_demonstrated':any(r['recovery']=='ACCEPTED' and r['final']['position_m'][2]<r['stopped']['position_m'][2]-100e-6 for r in base),
           'resolution_and_timestep':all(row['pass'] for rows in comparisons.values() for row in rows)}
    return {'gates':gates,'verdict':'DYNAMIC_DEVELOPMENT_GATE_PASS' if all(gates.values()) else 'DYNAMIC_DEVELOPMENT_GATE_FAIL',
            'comparisons':comparisons,'contact_counterfactual_position_difference_m':displacement,
            'thresholds':{'free_error_m':50e-6,'stopped_speed_m_s':1e-5,'comparison_position_m':20e-6,
                          'comparison_angle_rad':math.radians(.1),'relative_peak_force':.2},
            'not_assembly_success_or_physical_calibration':True}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--resume',action='store_true');args=parser.parse_args()
    OUTPUT.mkdir(parents=True,exist_ok=True)
    code=sources();old=fingerprint()
    runs={}
    for n,dt in ((128,.0002),(256,.0002),(128,.0001),(128,.0004)):
        key=f'n{n}_dt{dt}';target=OUTPUT/(key+'.json')
        if args.resume and target.exists():
            cached=json.loads(target.read_text(encoding='utf-8'))
            if cached['source_sha256']!=code or cached['historical_source_sha256']!=old:
                raise RuntimeError('Stale checkpoint '+key)
            runs[key]=cached['runs'];continue
        env=CartesianEnvironment(DynamicConfig(timestep=dt),n)
        rows=[]
        for name,case,duration,recover in scenarios():
            row=run_episode(env,name,case,duration,recover);rows.append(row)
            print(key,name,'peakF',round(row['peaks']['force_N'],6),'events',row['events'],
                  'wall',round(row['timing']['wall_seconds'],2),flush=True)
        runs[key]=rows
        dump(target,{'source_sha256':code,'historical_source_sha256':old,'runs':rows})
    free_axes=[];env=CartesianEnvironment()
    for axis in range(6):
        cmd=np.zeros(6);cmd[axis]=.001 if axis<3 else .01
        free_axes.append(run_episode(env,f'free_axis_{axis}',ContactCase.separated(),.3,command=cmd))
    _,case,duration,_=next(s for s in scenarios() if s[0]=='combined_a_scale_0.75')
    counterfactual=run_episode(CartesianEnvironment(contacts_enabled=False),'contact_disabled',case,duration,True)
    guard_test=run_episode(CartesianEnvironment(DynamicConfig(stop_force_N=.003,recovery_force_N=.001)),
                           'force_guard_probe',case,duration,True)
    summary=evaluate(runs,free_axes,counterfactual,guard_test)
    if code!=sources() or old!=fingerprint():raise RuntimeError('Inputs changed during experiment')
    dump(OUTPUT/'auxiliary.json',{'source_sha256':code,'historical_source_sha256':old,
                                'free_axes':free_axes,'contact_disabled':counterfactual,'force_guard_probe':guard_test})
    dump(OUTPUT/'dynamic_results.json',{'mujoco_version':mujoco.__version__,'python':platform.python_version(),
         'processor':platform.processor(),'source_sha256':code,'historical_source_sha256':old,
         'summary':summary,'run_files':[key+'.json' for key in runs],'auxiliary_file':'auxiliary.json'})
    print(json.dumps(summary,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
