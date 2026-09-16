"""Small fixed-parameter B1 development matrix, not a formal success-rate study."""
from dataclasses import asdict, replace
import argparse
import hashlib
import json
import math
import time
from pathlib import Path
import numpy as np
from tools.control.fixed_admittance import FixedAdmittance, AdmittanceConfig
from tools.dynamics.cartesian import CartesianEnvironment, DynamicConfig
from tools.validation.run_contact_cases import ROOT, ContactCase
from tools.validation.diagnose_v1_applicability import fingerprint

OUTPUT=ROOT/'deliverables/b1_fixed_admittance'
FINISH={'z_tolerance_m':20e-6,'xy_tolerance_m':50e-6,'angle_tolerance_rad':math.radians(.5),
        'linear_speed_m_s':1e-5,'angular_speed_rad_s':.001,'hold_s':.1,
        'force_N':.025,'torque_Nm':.0005,'penetration_m':30e-6}


def geometric_finish(row):
    p=np.asarray(row['position_m']);q=np.asarray(row['quaternion_wxyz']);v=np.asarray(row['velocity_world'])
    if not np.isfinite(np.r_[p,q,v,row['contact_wrench_G'],row['penetration_m']]).all():return False
    if np.linalg.norm(q)<1e-12:return False
    angle=2*math.acos(min(1.,abs(float(q[0]))/float(np.linalg.norm(q))))
    return bool(abs(p[2])<=FINISH['z_tolerance_m'] and np.linalg.norm(p[:2])<=FINISH['xy_tolerance_m']
                and angle<=FINISH['angle_tolerance_rad'] and np.linalg.norm(v[:3])<=FINISH['linear_speed_m_s']
                and np.linalg.norm(v[3:])<=FINISH['angular_speed_rad_s']
                and np.linalg.norm(row['contact_wrench_G'][:3])<FINISH['force_N']
                and np.linalg.norm(row['contact_wrench_G'][3:])<FINISH['torque_Nm']
                and row['penetration_m']<FINISH['penetration_m'])


def run_episode(env,case,controller,*,max_time=6.,settle_time=1.):
    env.reset(case);controller.reset();dt=env.config.control_period
    trace=[];hold_start=None;reason=None;stop_time=None;start=time.perf_counter()
    initial=env.observe()
    initial.update(admittance_velocity=[0]*4,commanded_correction=[0]*4)
    trace.append(initial)
    for _ in range(math.ceil((max_time+settle_time)/dt)):
        if env.phase=='TERMINAL':reason='INVALID_SIMULATION';break
        if env.phase=='RUNNING':
            cmd=controller.command(env.observe()['contact_wrench_M'],dt)
        else:cmd=np.zeros(6)
        row=env.step(cmd)
        row.update(admittance_velocity=cmd[[0,1,3,4]].tolist(),commanded_correction=controller.offset.tolist())
        trace.append(row)
        if env.phase=='TERMINAL':reason=env.events[-1]['reason'];break
        if env.phase=='STOPPING' and stop_time is None:
            stop_time=row['time_s'];reason=env.events[-1]['reason']
        if env.phase=='RUNNING':
            if row['position_m'][2]>=-10e-6:
                reason='TARGET_PLANE_REACHED';env.stop(reason);stop_time=row['time_s']
            elif row['time_s']>=max_time-1e-10:
                reason='TIME_LIMIT';env.stop(reason);stop_time=row['time_s']
            elif row['time_s']>1.2 and row['contact_count']:
                earlier=trace[max(0,len(trace)-1-round(1./dt))]
                delta=np.asarray(row['position_m'])-earlier['position_m']
                qdot=abs(float(np.dot(row['quaternion_wxyz'],earlier['quaternion_wxyz'])))
                dangle=2*math.acos(min(1.,qdot))
                if abs(delta[2])<10e-6 and np.linalg.norm(delta[:2])<5e-6 and dangle<.001:
                    reason='NO_PROGRESS';env.stop(reason);stop_time=row['time_s']
        if env.phase=='STOPPING':
            peaks_ok=(env.peaks['force_N']<FINISH['force_N'] and env.peaks['torque_G_Nm']<FINISH['torque_Nm']
                      and env.peaks['penetration_m']<FINISH['penetration_m'])
            if reason=='TARGET_PLANE_REACHED' and geometric_finish(row) and peaks_ok:
                if hold_start is None:hold_start=row['time_s']
            else:hold_start=None
            if hold_start is not None and row['time_s']-hold_start>=FINISH['hold_s']-1e-12:
                reason='GEOMETRIC_SUCCESS';break
            if row['time_s']-stop_time>=settle_time-1e-10:
                if reason=='TARGET_PLANE_REACHED':reason='TARGET_POSE_NOT_SETTLED'
                break
    elapsed=time.perf_counter()-start
    return {'case':asdict(case),'controller':controller.metadata(),'environment':env.metadata(),
            'termination':reason or 'TIME_LIMIT','finish_criteria':FINISH,'max_time_s':max_time,'settle_time_s':settle_time,
            'contact_observed':env.first_contact is not None,'first_contact':env.first_contact,'stop_time_s':stop_time,
            'final':env.observe(),'peaks':env.peaks,'events':env.events,'physical_steps':env.physical_steps,
            'controller_limited_steps':controller.limited_steps,'control_steps':len(trace)-1,
            'trace':trace,'wall_seconds':elapsed,'physical_steps_per_second':env.physical_steps/elapsed,
            'scope':'fixed_development_cases_not_statistical_success_rate_or_hardware_validation'}


def cases():
    out=[ContactCase.aligned(),ContactCase.x_offset(100e-6),ContactCase.y_offset(-100e-6),ContactCase.roll(math.radians(1.5))]
    for c in (ContactCase.combined(),ContactCase.combined_b()):
        out.append(replace(c,name=c.name+'_scale_0.75',x_offset_m=c.x_offset_m*.75,y_offset_m=c.y_offset_m*.75,
                           roll_rad=c.roll_rad*.75,pitch_rad=c.pitch_rad*.75))
    out.append(ContactCase.combined())
    return out


def hashes():
    files=[ROOT/'tools/control/fixed_admittance.py',ROOT/'tools/validation/run_b1_baseline.py',
           ROOT/'tools/model/contact_development.py',ROOT/'tools/dynamics/cartesian.py',ROOT/'tools/dynamics/safety.py']
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


def dump(path,r):path.write_text(json.dumps(r,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8',newline='\n')


def read_checkpoint(path,code,historical):
    result=json.loads(path.read_text(encoding='utf-8'))
    if result.get('source_sha256')!=code or result.get('historical_source_sha256')!=historical:
        raise RuntimeError('Stale B1 checkpoint: code or historical inputs differ')
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=[c.name for c in cases()]);parser.add_argument('--resume',action='store_true')
    args=parser.parse_args();OUTPUT.mkdir(parents=True,exist_ok=True);(OUTPUT/'runs').mkdir(exist_ok=True)
    code=hashes();old=fingerprint();index=[]
    env=CartesianEnvironment(segments=256)
    for case in cases():
        if args.case and args.case!=case.name:continue
        for feedback in (False,True):
            controller=FixedAdmittance(feedback_enabled=feedback)
            file=OUTPUT/'runs'/(case.name+('_b1.json' if feedback else '_reference.json'))
            if args.resume and file.exists():
                result=read_checkpoint(file,code,old)
            else:
                result=run_episode(env,case,controller)
                result['source_sha256']=code;result['historical_source_sha256']=old;dump(file,result)
            index.append({'file':file.relative_to(OUTPUT).as_posix(),'case':case.name,'controller':result['controller']['name'],
                          'termination':result['termination'],'contact_observed':result['contact_observed'],
                          'final_depth_m':result['final']['position_m'][2]-case.start_origin_z_m,
                          'peak_force_N':result['peaks']['force_N'],'wall_seconds':result['wall_seconds']})
            print(index[-1],flush=True)
    if code!=hashes() or old!=fingerprint():raise RuntimeError('Inputs changed during B1 evaluation')
    dump(OUTPUT/('pilot_index.json' if args.case else 'results_index.json'),{'source_sha256':code,'historical_source_sha256':old,
         'protocol':'7 prespecified development cases, paired zero-feedback/B1, fixed parameters, no retuning between cases',
         'finish_criteria':FINISH,'runs':index})


if __name__=='__main__':main()
