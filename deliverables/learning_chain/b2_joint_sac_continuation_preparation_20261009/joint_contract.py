"""Four discrete joint poses and the ordinary F50 pilot; standard library only."""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import math
import os
import uuid
from bounded_io import read,write

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
COMMON=ROOT/'deliverables/paper_comparison/v4_learning_requalification_20261006'
COMMON_PIN='da6b1d4207aeb2f35a0695fff9a33e5a097329ebdace54dd2c0e1e08b7e8cca5'
SEED=2026092716
LIMITS=dict(dynamic_episodes=9,environment_creations=9,resets=9,control_cycles=130500,
    native_steps=1305000,observations=130509,formal_updates=2000,policy_calls=130500,
    learner_constructions=8,tensor_loads=3,checkpoint_saves=2,replay_publications=4,archive_rebuilds=28,
    per_episode_cycles=14500,per_episode_wall_s=1200,whole_wall_s=21600,reader_wall_s=1800)


def canonical(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()
def training_cases():
    return [dict(id='J0'+str(i),x_um=x,y_um=y,roll_deg=r,pitch_deg=p,yaw_deg=0,
        start_origin_z_m=-.004,target_depth_m=.004)
        for i,(x,y,r,p) in enumerate([(75,75,.25,.25),(-75,75,-.25,.25),(-75,-75,-.25,-.25),(75,-75,.25,-.25)],1)]


def case_kwargs(point):
    if canonical(point) not in [canonical(c) for c in training_cases()]:raise ValueError('Unregistered joint pose')
    return dict(name=point['id'],x_offset_m=point['x_um']*1e-6,y_offset_m=point['y_um']*1e-6,
        roll_rad=math.radians(point['roll_deg']),pitch_rad=math.radians(point['pitch_deg']),
        start_origin_z_m=point['start_origin_z_m'],target_depth_m=point['target_depth_m'])


def check_initial_pose(point,row):
    kw=case_kwargs(point)
    try:
        pos=row['position_m'];quat=row['quaternion_wxyz']
        if len(pos)!=3 or len(quat)!=4 or any(type(x) not in (float,int) or not math.isfinite(x) for x in pos+quat):raise ValueError('Nonfinite pose')
        r=kw['roll_rad']/2;p=kw['pitch_rad']/2
        want=[math.cos(p)*math.cos(r),math.cos(p)*math.sin(r),math.sin(p)*math.cos(r),-math.sin(p)*math.sin(r)]
        xyz=[kw['x_offset_m'],kw['y_offset_m'],kw['start_origin_z_m']]
        if max(abs(a-b) for a,b in zip(pos,xyz))>1e-12 or min(max(abs(a-b) for a,b in zip(quat,want)),max(abs(a+b) for a,b in zip(quat,want)))>1e-12:
            raise ValueError('Actual pose differs from joint registration')
    except (KeyError,TypeError,OverflowError) as exc:raise ValueError('Incomplete initial pose') from exc
    return True


def validate_raw_identity(raw):
    index=raw['case_index']
    if type(index) is not int or not 0<=index<4:raise ValueError('Invalid joint case index')
    point=training_cases()[index]
    if (canonical(raw['case'])!=canonical(point) or raw['case_id']!=point['id'] or
        canonical(raw['simulation_case'])!=canonical(case_kwargs(point))):raise ValueError('Joint simulation/learning identity differs')
    check_initial_pose(point,raw['trace'][0])


def common_configuration():
    if sha(COMMON/'configuration.json')!=COMMON_PIN:raise ValueError('Common configuration drift')
    return read(COMMON/'configuration.json')


def learning_config():
    c=deepcopy(common_configuration()['methods']['F50'])
    c.update(version='b2_joint_sac_config_v1',joint_cases=training_cases(),joint_scope='four_discrete_development_cases')
    return c


def validate_config(config):
    if canonical(config)!=canonical(learning_config()):raise ValueError('Complete new joint F50 configuration required')


def schedule():
    return [dict(id=stage+'_F50_'+case['id'],stage=stage,mode='F50',case_index=i,case=case,
        optimizer_steps=(0 if stage in ('zero','warmup') else 500*i if stage=='online' else 2000))
        for stage in ('online','final','restore')
        for i,case in enumerate(training_cases()) if stage!='restore' or i==0]


def advance(records):
    specs=schedule()
    if len(records)>len(specs):raise ValueError('Attempt ceiling exceeded')
    for spec,row in zip(specs,records):
        if row.get('id')!=spec['id']:raise ValueError('Skipped, duplicate or reordered episode')
        if row.get('healthy') is not True:return None
    return deepcopy(specs[len(records)]) if len(records)<len(specs) else None


def metric(rows):
    if len(rows)!=4 or {r['case_id'] for r in rows}!={'J01','J02','J03','J04'}:raise ValueError('All four cases exactly once required')
    valid=all(r['simulation_valid'] is True and r['physical_stopped'] is True for r in rows)
    penalties=[]
    for row in rows:
        t=row['task_time_s']
        if row['task_outcome']=='FULL_SUCCESS':
            if type(t) not in (int,float) or not math.isfinite(t) or not 0<=t<=26+1e-9:raise ValueError('Invalid successful task time')
            penalties.append(t)
        else:penalties.append(26.)
    return dict(comparable=valid,mean_penalized_time_s=sum(penalties)/4 if valid else None,
        success_count=sum(r['task_outcome']=='FULL_SUCCESS' for r in rows),guards=sum(bool(r['guard']) for r in rows))
