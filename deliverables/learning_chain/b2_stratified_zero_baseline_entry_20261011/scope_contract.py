"""Independent 25-point / 21-new scope contract, standard library only."""
from datetime import datetime,timedelta,timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
BASE=ROOT/'deliverables/learning_chain'
OLD=BASE/'b2_pure_baseline_preparation_20261011'
SCOPE=BASE/'b2_stratified_scope_preparation_20261011'
PREV=BASE/'b2_pure_baseline_execution_20261011'
SEED=2026092716
LIMITS=dict(dynamic_episodes=21,environment_creations=21,resets=21,
    control_cycles=304500,native_steps=3045000,per_episode_cycles=14500,
    per_episode_native_steps=145000,per_episode_wall_s=1200,whole_wall_s=21600,
    policy_calls=0,learner_constructions=0,tensor_loads=0,formal_updates=0,
    replay_publications=0,independent_tests=0)
_modules={}


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(value):return hashlib.sha256(canonical(value).encode()).hexdigest()


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1048576),b''):h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),
        parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON: '+x)))


def frozen_module(name):
    if name not in _modules:
        spec=importlib.util.spec_from_file_location('stratified_frozen_'+name,OLD/(name+'.py'))
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);_modules[name]=module
    return _modules[name]


def helper(name):return frozen_module('contract').helper(name)
def write(path,value):return helper('bounded_io').write(Path(path),value)
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()


def validate_registry(points):
    expected=read(SCOPE/'case_registry_candidate.json')['cases']
    try:
        good=canonical(points)==canonical(expected)
    except (ValueError,TypeError):good=False
    if not good:raise ValueError('Exact ordered 25-point development registry required')
    return points


def registered_cases():return validate_registry(read(OUT/'case_registry.json')['cases'])


def new_cases():
    reused={'J11','J22','J33','J44'}
    return [point for point in registered_cases() if point['id'] not in reused]


def case_kwargs(point):
    if canonical(point) not in {canonical(p) for p in registered_cases()}:
        raise ValueError('Unregistered or modified development pose')
    return dict(name=point['id'],x_offset_m=point['x_um']*1e-6,y_offset_m=point['y_um']*1e-6,
        roll_rad=math.radians(point['roll_deg']),pitch_rad=math.radians(point['pitch_deg']),
        start_origin_z_m=point['start_origin_z_m'],target_depth_m=point['target_depth_m'])


def finite_vector(value,width):
    if (not isinstance(value,(list,tuple)) or len(value)!=width or
        any(type(x) not in (int,float) or not math.isfinite(x) for x in value)):
        raise ValueError('Complete finite physical vector required')
    return list(value)


def check_pose(point,row):
    kw=case_kwargs(point)
    try:
        pos=finite_vector(row['position_m'],3);q=finite_vector(row['quaternion_wxyz'],4)
        r=kw['roll_rad']/2;p=kw['pitch_rad']/2
        target=[math.cos(p)*math.cos(r),math.cos(p)*math.sin(r),
                math.sin(p)*math.cos(r),-math.sin(p)*math.sin(r)]
        xyz=[kw['x_offset_m'],kw['y_offset_m'],kw['start_origin_z_m']]
        if max(abs(a-b) for a,b in zip(pos,xyz))>1e-12 or min(
            max(abs(a-b) for a,b in zip(q,target)),max(abs(a+b) for a,b in zip(q,target)))>1e-12:
            raise ValueError('Actual initial pose differs from registered pose')
    except (KeyError,TypeError,OverflowError) as exc:raise ValueError('Incomplete initial pose') from exc


def check_initial_state(point,row,common,facts):
    check_pose(point,row)
    try:
        wrench=finite_vector(row['contact_wrench_M'],6)
        grip=finite_vector(row['contact_wrench_G'],6)
        velocity=finite_vector(row['velocity_world'],6)
        count=row['contact_count'];penetration=row['penetration_m']
        if type(count) is not int or count<0 or type(penetration) not in (int,float) or not math.isfinite(penetration) or penetration<0:
            raise ValueError('Invalid initial contact facts')
        # Frozen ordinary approach reset rejects any initial contact or >1nm overlap.
        if count!=0 or penetration>1e-9:raise ValueError('Ordinary no-initial-contact reset rule failed')
        force=math.sqrt(sum(v*v for v in wrench[:3]));torque=math.sqrt(sum(v*v for v in grip[3:]))
        speed=math.sqrt(sum(v*v for v in velocity[:3]));angular=math.sqrt(sum(v*v for v in velocity[3:]))
        c=common['dynamic_config']
        if force>c['stop_force_N'] or torque>c['stop_torque_Nm'] or speed>c['actual_speed_limit'] or angular>c['actual_angular_speed_limit']:
            raise ValueError('Initial physical guard exceeded')
        if facts['simulation_valid'] is not True or any(facts[k] for k in ('invalid_reasons','contact_reasons','motion_reasons')):
            raise ValueError('Initial simulation or guard latch failed')
        return dict(passed=True,actual_pose_checked=True,contact_count=count,penetration_m=penetration,
            force_N=force,torque_G_Nm=torque,speed_m_s=speed,angular_speed_rad_s=angular,
            full_model_native_reset_checked=True,nonzero_SAC_qualified=False,training_admitted=False)
    except (KeyError,TypeError,OverflowError) as exc:raise ValueError('Incomplete initial audit facts') from exc


def grant_template(binding_pin,run_id):
    config=read(OUT/'configuration.json')
    return dict(version='b2_stratified_21_zero_grant_v1',binding_sha256=binding_pin,
        run_id=run_id,status='DRAFT',explicit_user_authorized=False,human_evidence='',
        purpose='21_new_pure_B2_development_cases',matrix_scope_key=config['common_key'],
        shared_common_key=config['parent_common_key'],new_case_ids=[p['id'] for p in new_cases()],
        limits=dict(LIMITS),cumulative_before=258,old_budget_closed=True,retries=0)


def require_grant(grant,binding_pin,run_id):
    expected=grant_template(binding_pin,run_id)
    if (not isinstance(grant,dict) or set(grant)!=set(expected) or
        grant.get('explicit_user_authorized') is not True or grant.get('status')!='OPEN' or
        not isinstance(grant.get('human_evidence'),str) or not grant['human_evidence'].strip() or
        not isinstance(run_id,str) or re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{1,90}',run_id) is None or
        run_id=='pending-new-run-id' or re.fullmatch(r'[0-9a-f]{64}',binding_pin or '') is None or
        any(canonical(grant[k])!=canonical(expected[k]) for k in expected if k not in
            ('status','explicit_user_authorized','human_evidence'))):
        raise PermissionError('Separately bound explicit 21-case physical grant required')


def check_receipt_costs(row):
    caps=dict(environment_creation_attempted=1,environment_created=1,reset_attempted=1,reset_completed=1,
        control_cycles=14500,physical_substeps=145000,policy_calls=0,formal_updates=0,
        learner_constructions=0,tensor_loads=0,replay_publications=0)
    for key,cap in caps.items():
        value=row.get(key,0)
        if type(value) is not int or not 0<=value<=cap:raise ValueError('Attempt cost exceeded or invalid: '+key)
    if row.get('environment_created',0)>row.get('environment_creation_attempted',0) or row.get('reset_completed',0)>row.get('reset_attempted',0):
        raise ValueError('Completed physical operation lacks charged attempt')


def receipt_healthy(row):
    check_receipt_costs(row)
    out=row.get('outcome',{});supervisor=row.get('supervisor',{})
    archive=row.get('archive_sha256')
    return bool(row.get('status')=='finished' and row.get('healthy') is True and
        row.get('initial_audit',{}).get('passed') is True and
        isinstance(archive,str) and re.fullmatch(r'[0-9a-f]{64}',archive) and
        all(row.get(k)==1 for k in ('environment_creation_attempted','environment_created','reset_attempted','reset_completed')) and
        row.get('physical_substeps')==10*row.get('control_cycles',-1) and
        out.get('simulation_valid') is True and out.get('physical_stopped') is True and
        out.get('guard_violations')==dict(contact=False,motion=False) and
        out.get('task_outcome') in ('FULL_SUCCESS','TASK_FAILURE') and
        supervisor.get('go_issued') is True and supervisor.get('process_exit_confirmed') is True and
        supervisor.get('owned_launcher_exit_confirmed') is True and type(supervisor.get('returncode')) is int and supervisor['returncode']==0)


def next_case(entries):
    points=new_cases()
    if not isinstance(entries,list) or len(entries)>len(points):raise ValueError('21-attempt ceiling exceeded')
    for index,row in enumerate(entries):
        if row.get('case_id')!=points[index]['id']:raise ValueError('Duplicate, omitted or reordered attempt')
        if not receipt_healthy(row):return None
    return points[len(entries)] if len(entries)<len(points) else None


def verify_binding():
    binding=read(OUT/'source_binding.json')
    for path,pin in binding['files'].items():
        if sha(Path(path))!=pin:raise ValueError('Bound source changed: '+path)
    frozen_module('contract').check_runtime(binding['numerical_runtime'])
    config=read(OUT/'configuration.json');registry=read(OUT/'case_registry.json')
    old=read(OLD/'configuration.json')
    if (canonical(config['common'])!=canonical(old['common']) or
        config['parent_common_key']!=digest(config['common']) or
        config['common_key']!=digest(dict(parent_common_key=config['parent_common_key'],cases=registered_cases())) or
        config['legacy_four_point_comparison_key']!=old['common_key'] or
        canonical(config['cases'])!=canonical(registry['cases']) or canonical(config['methods'])!=canonical(old['methods']) or
        config['data_use']!='development' or binding['matrix_scope_key']!=config['common_key']):
        raise ValueError('Shared physics, registry, method or scope identity changed')
    return binding,config
