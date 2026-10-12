"""Read sealed evidence only; no simulator, network inference or optimization."""
import sys, json, gzip, math, hashlib, os
from pathlib import Path
from collections import Counter
import importlib.abc

class NoLearningRuntime(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('torch', 'mujoco', 'stable_baselines3'):
            raise RuntimeError('Offline archive analysis cannot import learning/physics runtime')
sys.meta_path.insert(0, NoLearningRuntime())
D=Path(__file__).resolve().parent
ROOT=D.parents[2]
OLD=D.parent/'b2_atomic_repaired_cycle_20260929'
RUN=OLD/'run'
read=lambda p: json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
sealed=read(OLD/'sealed_files.json')
inputs={}
def checked(p):
    key=p.relative_to(ROOT).as_posix()
    actual=sha(p)
    assert actual==sealed[key],key
    inputs[key]=actual
    return p.read_bytes()
ledger=json.loads(checked(RUN/'ledger.json'))
updates=json.loads(checked(RUN/'training/updates.json'))
assert len(updates)==2500 and ledger['dynamic_starts']==13
assert sha(OLD/'candidate.json')=='ab2fefe0ae4eb6850d5aae768dff7a7c952302e3893f68721fb41a4adf3de379'
assert sha(OLD/'authorization.json')=='74602d300a656257becf57d7db56a7c273426bb1dba2ccdcd322e34fef936b4c'
def peak(r):
    # Inverse of the archived reward formula, using its physical duration.
    return .025*math.sqrt(max(0.,-r['reward_terms']['force']/(.2*r['dt'])))
def snapshot(r):
    t=r['trace_row'];f=t['contact_wrench_M'][:3]
    return dict(time_s=t['time_s'],phase=t['policy_phase'],force_vector_N=f,
        sampled_norm_N=math.sqrt(sum(v*v for v in f)),cycle_peak_from_reward_N=peak(r),
        reference_error_um=[(t['reference_qpos'][i]-t['position_m'][i])*1e6 for i in range(3)],
        normalized_action=r['action'],limited_command=r['action_log']['actual_end_limited_command'])
episodes=[]; force_windows=[]
for entry in ledger['attempts']:
    folder=RUN/('initial/episodes' if entry['stage']=='initial' else 'training_episodes')/entry['id']
    raw=json.loads(gzip.decompress(checked(folder/'episode.json.gz')))
    rs=raw['transitions'];active=[r for r in rs if r['action_active']]
    boundary=max(i for i,r in enumerate(rs) if r['action_active'])
    label=0.
    for r in reversed(rs[boundary:]): label=r['reward']+r['discount']*label
    occurrences=[u for u in updates if any(k==raw['episode_id'] for k,i in u['boundary_indices'])]
    for u in occurrences:
        assert all(i==boundary for k,i in u['boundary_indices'] if k==raw['episode_id'])
    tail=[r for r in active if raw['stop_time']-.5 <=r['trace_row']['time_s']<=raw['stop_time']+1e-8]
    sat=lambda rows: [sum(abs(r['action'][j])>.95 for r in rows)/len(rows) for j in range(4)]
    transitions=[]
    for i,r in enumerate(rs):
        phase=r['trace_row']['policy_phase']
        if i==0 or phase!=rs[i-1]['trace_row']['policy_phase']:
            transitions.append(dict(index=i,time_s=r['trace_row']['time_s'],phase=phase))
    result=dict(id=raw['episode_id'],stage=entry['stage'],updates_at_start=raw['optimizer_steps_start'],
        outcome=entry['result']['task_outcome'],return_=entry['result']['return'],
        stop_s=raw['stop_time'],cycle_peak_from_reward_N=max(map(peak,rs)),
        sampled_peak_N=entry['result']['force_peak_N'],initial_force_margin_pct=100*(1-max(map(peak,rs))/.025),
        active_rows=len(active),saturation_fraction=sat(active),last_half_second_saturation=sat(tail),
        boundary_index=boundary,exact_boundary_label=label,
        boundary_draws=sum(k==raw['episode_id'] for u in updates for k,i in u['boundary_indices']),
        boundary_batches=len(occurrences),boundary_update_range=[occurrences[0]['critic_batches'],occurrences[-1]['critic_batches']] if occurrences else None,
        recovery_used=any(e.get('reason')=='B2_RECOVERY_RESUMED' for e in raw['events']),
        phase_transitions=transitions)
    if result['outcome']=='CONTACT_GUARD':
        hit=next(i for i,r in enumerate(rs) if any(e.get('reason')=='FORCE_LIMIT' for e in r['events']))
        assert hit==boundary and peak(rs[hit])>.025 and rs[-1]['reward_terms']['terminal']==-10
        result['force_event']=rs[hit]['events']
        result['before_force_snapshots']=[snapshot(rs[j]) for j in (hit-250,hit-50,hit-1,hit)]
        force_windows.append((raw['episode_id'],raw['stop_time'],rs[max(0,hit-500):hit+1]))
    episodes.append(result)
assert [e['boundary_draws'] for e in episodes if e['outcome']=='CONTACT_GUARD']==[5116,2134,0]
assert all(e['cycle_peak_from_reward_N']+1e-12>=e['sampled_peak_N'] for e in episodes)
out=dict(kind='offline_force_mechanism_review',physics_starts=0,optimizer_updates=0,model_forward_calls=0,
    episodes=episodes,inputs_sha256=inputs,
    conclusions=dict(real_force_limit=True,failure_boundary_samples_used=True,
        recovery_only_explanation_rejected=True,unique_learning_cause_established=False,
        code_bug_established=False,policy_improvement_established=False))
(D/'assessment.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False})
fig,axs=plt.subplots(2,3,figsize=(13,7),layout='constrained')
for col,(name,stop,rows) in enumerate(force_windows):
    t=[r['trace_row']['time_s']-stop for r in rows]
    axs[0,col].plot(t,[1000*peak(r) for r in rows],label='由奖励反算周期子步峰值',lw=1)
    axs[0,col].plot(t,[1000*math.sqrt(sum(v*v for v in r['trace_row']['contact_wrench_M'][:3])) for r in rows],label='周期末采样合力',alpha=.6,lw=.8)
    axs[0,col].axhline(25,color='red',ls='--',lw=.8);axs[0,col].set(title=name,ylabel='mN')
    for j,label in ((0,'X'),(1,'Y'),(2,'Z')):
        axs[1,col].plot(t,[(r['trace_row']['reference_qpos'][j]-r['trace_row']['position_m'][j])*1e6 for r in rows],label=label,lw=.9)
    axs[1,col].set(ylabel='参考—实际位置 / μm',xlabel='相对停止触发 / s')
    axs[0,col].legend(fontsize=7);axs[1,col].legend(fontsize=8)
fig.suptitle('三次力保护前1秒：真实周期峰值越限；末端采样不能代替周期峰值\n不同中间策略；轨迹相关性不等于已证明残差动作的反事实因果效应',fontsize=12)
fig.savefig(D/'力保护机制对照.png',dpi=150);plt.close(fig)
assert not any(m in sys.modules for m in ('torch','mujoco','stable_baselines3'))
print(json.dumps({'episodes':len(episodes),'verified_inputs':len(inputs),'force_boundary_draws':[5116,2134,0], 'new_physics_updates_inference':[0,0,0]},ensure_ascii=False))
