"""Code inventory, feature redundancy and reference-only math; no dynamics/RL."""
from pathlib import Path
import json,gzip,hashlib,difflib,math
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def archive(p):return json.loads(gzip.decompress(p.read_bytes()))
def put(n,x):(OUT/n).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

paths=[ROOT/'deliverables/paper_comparison/v4_continuation_20261006/run/F50_boundary_y_neg_150.json.gz']
paths += [ROOT/'deliverables/paper_comparison/v4_learning_pilot_20261006/run'/n for n in
    ('warmup_F50_y_neg_150.json.gz','warmup_S50_y_neg_150.json.gz')]
records=[];new_schema=None;near=[]
for p in paths:
    raw=archive(p);schema=raw['observation_schema'];s={f['name']:slice(f['start'],f['start']+f['width']) for f in schema}
    new_schema=[f for f in schema if f['start']>=120];obs=np.array([t['observation'] for t in raw['transitions']],dtype=float)
    ref=obs[:,s['relative_position_m']]+obs[:,s['reference_position_error_m']]
    search=(ref[:,:2]-obs[:,s['search_origin_m']][:,:2])*(.004/.00012)
    ref_error=float(np.max(np.abs(ref-obs[:,s['relative_drive_reference_m']])))
    valid=obs[:,s['search_reference_valid']][:,0].astype(bool)
    search_error=float(np.max(np.abs(search[valid]-obs[valid,s['search_reference_xy_m']]))) if valid.any() else None
    validity_same=bool(np.array_equal(obs[:,s['search_reference_valid']],obs[:,s['search_origin_valid']]))
    active=obs[:,s['action_active']][:,0].astype(bool)
    peak_error=float(np.max(np.abs(obs[active,s['episode_peak_z_m']]-obs[active,s['maximum_advance_m']]))) if active.any() else None
    assert ref_error<1e-6 and (search_error is None or search_error<1e-5) and validity_same
    records.append(dict(archive=p.relative_to(ROOT).as_posix(),sha256=sha(p),rows=len(obs),active_rows=int(active.sum()),
        drive_reference_reconstruction_max_error=ref_error,search_reference_reconstruction_max_error=search_error,
        search_valid_equals_old_origin_valid=validity_same,active_episode_peak_vs_old_max_error=peak_error))
    actions=raw['actions']
    for i,log in enumerate(actions):
        if log.get('continuation_checked') and np.linalg.norm(log['predicted_reference_xy_m'])>=.000119:
            near.append(dict(archive=p.relative_to(ROOT).as_posix(),cycle=i+1,
                ref=log['predicted_reference_xy_m'],previous=log['predicted_limited_command'][:2],theta=log['next_search_theta_rad']))
    if p.name=='warmup_S50_y_neg_150.json.gz':sraw=raw

config=read(ROOT/'deliverables/paper_comparison/v4_learning_pilot_20261006/configuration.json')['common']['b2_config']
b=config['spiral_pitch_m']/(2*math.pi);theta_max=config['spiral_radius_m']/b;dt=.002
e=sraw['reference_problems'][0];i=next(i for i,r in enumerate(sraw['trace']) if abs(r['time_s']-e['time_s'])<1e-9)
ref=np.array(e['reference_xy_m']);previous=np.array(sraw['trace'][i]['limited_command_world'][:2])
lo=np.maximum(-.001,previous-.005*dt);hi=np.minimum(.001,previous+.005*dt)
closest=np.clip(np.zeros(2),ref+dt*lo,ref+dt*hi)
reach=dict(time_s=e['time_s'],current_radius_um=float(np.linalg.norm(ref)*1e6),previous_xy_m_s=previous.tolist(),
    minimum_next_radius_um=float(np.linalg.norm(closest)*1e6),minimum_excess_nm=float((np.linalg.norm(closest)-.00012)*1e9),
    any_next_xy_velocity_in_full_speed_slew_box_can_keep_120um=bool(np.linalg.norm(closest)<=.00012+1e-12))
assert not reach['any_next_xy_velocity_in_full_speed_slew_box_can_keep_120um']

# Forced-zero reference continuation only. No force, actual-body position,
# phase transition or future nonzero policy is predicted by this calculation.
future=[]
for item in near:
    r=np.array(item['ref']);v=np.array(item['previous']);theta=item['theta'];peak=np.linalg.norm(r);steps=0
    for _ in range(50):
        if theta>=theta_max-1e-12:break
        radius=b*theta;target=radius*np.array([math.cos(theta),math.sin(theta)])
        nt=min(theta_max,theta+config['spiral_speed_m_s']/math.hypot(radius,b)*dt)
        nxt=b*nt*np.array([math.cos(nt),math.sin(nt)])
        command=np.clip((nxt-target)/dt+config['search_tracking_gain_s']*(target-r),
            -config['search_xy_component_speed_m_s'],config['search_xy_component_speed_m_s'])
        v=np.clip(np.clip(command,-.001,.001),v-.005*dt,v+.005*dt);r=r+v*dt;theta=nt;steps+=1
        peak=max(peak,np.linalg.norm(r))
    future.append(dict(archive=item['archive'],cycle=item['cycle'],steps=steps,peak_radius_um=float(peak*1e6),
        excess_nm=float(max(0,peak-.00012)*1e9)))
worst=max(future,key=lambda x:x['peak_radius_um'])
put('reference_counterfactual.json',dict(scope='100ms forced-zero drive-reference math only, no future physical/success guarantee',
    snapshots=len(future),worst=worst,known_failure_reachability=reach,
    candidate_note='虚拟参考半径/容差与物理安全边界应分开审核；本计算只能支持缓冲量级筛查，不能签发训练或证明新随机动作安全。'))

names=['v4_action','v4_observation','v4_session','v4_continuation','v4_pilot_contract','v4_replay','v4_sac','v4_pilot_chain','v4_checkpoint']
sizes=[dict(path='tools/learning/'+n+'.py',lines=len((ROOT/'tools/learning'/(n+'.py')).read_text(encoding='utf8').splitlines())) for n in names]
a=(ROOT/'tools/learning/sac_update.py').read_text(encoding='utf8').splitlines();c=(ROOT/'tools/learning/v4_sac.py').read_text(encoding='utf8').splitlines()
matching=sum(m.size for m in difflib.SequenceMatcher(None,a,c,autojunk=False).get_matching_blocks())
runner='tools/validation/run_v4_learning_pilot.py'
source_paths=[r['path'] for r in sizes]+[runner,'tools/learning/observation.py','tools/learning/session.py',
    'tools/control/reference_search.py','tools/learning/boundary_targets.py','tools/learning/sac_update.py']
result=dict(observation_width=137,original_width=120,added_width=sum(f['width'] for f in new_schema),action_width=4,
    added_schema=new_schema,archive_checks=records,validated_rows=sum(r['rows'] for r in records),
    six_added_reference_coordinates_or_validity_reconstructible_in_checked_archives=True,
    reconstruction_is_not_universal_necessity_or_ablation_proof=True,
    current_v4_learning_family=sizes,family_lines=sum(r['lines'] for r in sizes),runner_lines=len((ROOT/runner).read_text(encoding='utf8').splitlines()),
    old_sac_lines=len(a),v4_sac_lines=len(c),same_literal_lines=matching,
    only_input_layer_change_actor_parameters=17*256,
    only_input_layer_change_actor_twin_critic_and_targets_parameters=5*17*256,
    latest_formal_updates=0,latest_policy_calls=0,new_physics=0,new_optimizer_batches=0,
    source_sha256={n:sha(ROOT/n) for n in source_paths})
put('audit_metrics.json',result)
print(json.dumps(dict(added_width=result['added_width'],action_width=4,validated_rows=result['validated_rows'],
    family_lines=result['family_lines'],runner_lines=result['runner_lines'],literal_sac_lines_in_common=matching,
    known_state_minimum_excess_nm=reach['minimum_excess_nm'],forced_zero_worst=worst),ensure_ascii=False))
