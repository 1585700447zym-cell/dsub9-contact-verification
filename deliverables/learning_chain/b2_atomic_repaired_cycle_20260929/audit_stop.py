"""Offline audit of a stopped run; never creates a model/session or predicts."""
import os,sys,json,gzip,hashlib,math
from pathlib import Path
from datetime import datetime
D=Path(__file__).resolve().parent;ROOT=D.parents[2];sys.path.insert(0,str(ROOT))
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.learning.runtime import verify_runtime
verify_runtime(ROOT/'tmp/mujoco_3_13_probe')
import mujoco,torch
from tools.learning.sac_update import SACUpdater
calls=dict(physics=0,optimizer=0,prediction=0)
def deny(kind):
    def fail(*a,**k):calls[kind]+=1;raise AssertionError('Forbidden offline call: '+kind)
    return fail
torch.optim.Adam.step=deny('optimizer');SACUpdater.predict=deny('prediction')
for n in ('mj_forward','mj_step','mj_step1','mj_step2','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,n,deny('physics'))
from tools.learning.sac_checkpoint import _audit_physics
from tools.validation.run_atomic_repaired_cycle import bound_runner
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
run=D/'run';ledger=read(run/'ledger.json');budget=read(run/'training_episodes/update_budget.json')
exit_record=read(D/'process_exit.json')
assert exit_record['returncode']==20 and not (run/'failure.json').exists()
with bound_runner() as runner:assert runner.valid_controlled_stop(run)
assert ledger['dynamic_starts']==13 and ledger['active'] is None
assert budget==dict(attempted=2500,completed=2500,failed_or_invalidated=0,remaining=2000)
assert all(not (run/n).exists() for n in ('final','restored','holdout_b2','holdout_sac','completed.json','frozen.json'))
rows=[];inputs={};last=None
for a in ledger['attempts']:
    folder=run/('initial/episodes' if a['stage']=='initial' else 'training_episodes')/a['id']
    receipt=read(folder/'status.json');archive=folder/'episode.json.gz'
    assert sha(archive)==receipt['archive_sha256']
    raw=json.loads(gzip.decompress(archive.read_bytes()));_audit_physics(raw)
    assert raw['outcome']['simulation_valid'] and raw['outcome']['physical_stopped']
    assert raw['qualification_sha256']=='ab2fefe0ae4eb6850d5aae768dff7a7c952302e3893f68721fb41a4adf3de379'
    metric=a['result'];r=dict(stage=a['stage'],episode=a['id'],**metric,physical_audit_passed=True,
        committed=receipt['committed'],contact_reasons=raw['guard_facts']['contact_reasons'],
        max_rotation_deg=math.degrees(raw['guard_facts']['max_rotation_from_start_rad']))
    if a['stage']=='training':
        assert receipt['status']=='published' and receipt['committed']==len(raw['transitions'])
        if metric['task_outcome']=='CONTACT_GUARD':
            assert raw['guard_facts']['contact_reasons']==['FORCE_LIMIT'] and not raw['guard_facts']['motion_reasons']
            assert receipt['learning_eligibility']['kind']=='force_failure'
            assert raw['transitions'][-1]['reward_terms']['terminal']==-10.
    rows.append(r);inputs[archive.relative_to(ROOT).as_posix()]=sha(archive)
    if a['id']=='train_08':last=raw
checkpoints=read(run/'training/checkpoints.json');assert len(checkpoints)==8 and checkpoints[-1]['updates']==2500
for c in checkpoints:
    cp=run/c['path'];assert sha(cp/'manifest.json')==c['sha256'];m=read(cp/'manifest.json')
    with (cp/'state.pt').open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==m['state_sha256']
history=read(run/'training/updates.json');assert len(history)==2500
assert [r['critic_batches'] for r in history]==list(range(1,2501))
training=[r for r in rows if r['stage']=='training'];forces=[r for r in training if r['task_outcome']=='CONTACT_GUARD']
assert [r['episode'] for r in forces]==['train_04','train_06','train_08']
warnings=[s for s in (D/'fault.log').read_text(encoding='utf-8').splitlines() if s.strip()]
assert len(warnings)==10 and all(s.startswith('atomic_json_replace_recovered:') for s in warnings)
assert not any(calls.values())
result=dict(status='controlled_stop_verified',kind='force_failure_frequency',reason='three_total_force_failures',
    stopped_at=datetime.fromtimestamp(exit_record['wall_timestamp']).astimezone().isoformat(),
    recorded_at=datetime.now().astimezone().isoformat(),returncode=20,native_crash=False,entry_rejection=False,
    write_failure=False,recovered_write_warnings=10,new_dynamic_starts=13,cumulative_dynamic_starts=57,
    unused_dynamic_starts=19,completed_formal_batches=2500,unused_formal_batches=2000,
    initial_successes=4,initial_cases=4,training_successes=1,training_cases=9,
    training_task_failures=5,training_force_failures=3,
    audited_published_transitions=sum(r['committed'] for r in training),physical_audits=rows,
    last_checkpoint=checkpoints[-1],last_stopped_episode_has_checkpoint=False,
    forbidden_call_counts=calls,archives_sha256=inputs,final_development_executed=False,
    restoration_executed=False,independent_executed=False,automatic_retry=False,b2_complete=False,
    automation_status='PAUSED',limitation='Exploratory intermediate-policy outcomes are not a frozen-policy success rate.')
(D/'stop_assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'figure.dpi':140})
fig,axs=plt.subplots(2,2,figsize=(12,7),layout='constrained')
x=list(range(1,10));colors=['#28846d' if r['success'] else '#c96548' if r['task_outcome']=='CONTACT_GUARD' else '#91a0ad' for r in training]
axs[0,0].bar(x,[r['final_xy_error_m']*1e6 for r in training],color=colors);axs[0,0].set(title='训练回合末端 XY 误差（不同中间策略）',ylabel='μm')
axs[0,1].bar(x,[r['force_peak_N'] for r in training],color=colors);axs[0,1].set(title='记录采样点的力峰值（非全部原始子步峰值）',ylabel='N')
axs[1,0].bar(x,[r['sampled_penetration_peak_m']*1e6 for r in training],color=colors);axs[1,0].set(title='记录采样点的穿透峰值',ylabel='μm',xlabel='训练回合')
axs[1,1].bar(x,[r['max_rotation_deg'] for r in training],color=colors);axs[1,1].set(title='守卫记录的最大转角',ylabel='度',xlabel='训练回合')
fig.suptitle('受控停止：训练 1 成功 / 5 普通失败 / 3 力保护失败；最终开发与独立评价未执行\n绿=成功，灰=普通失败，橙=力保护；不作为最终策略成功率',fontsize=12)
fig.savefig(D/'停止前回合结果.png');plt.close(fig)
fig,axs=plt.subplots(1,3,figsize=(12,3.8),layout='constrained')
for ax,key,title in zip(axs,('critic_loss','actor_loss','alpha_after'),('Critic 损失','Actor 损失','温度 alpha')):
    ax.plot([r['critic_batches'] for r in history],[r[key] for r in history],linewidth=.7,color='#277e72');ax.set(title=title,xlabel='更新批次')
fig.suptitle('2500 批已保存更新诊断；损失变化不等于任务改善');fig.savefig(D/'停止前更新诊断.png');plt.close(fig)
t=[r['trace_row']['time_s'] for r in last['transitions']]
fig,axs=plt.subplots(3,1,figsize=(11,8),layout='constrained')
for i,label in ((3,'roll'),(4,'pitch')):
    axs[0].plot(t,[r['action_log']['requested_residual'][i] for r in last['transitions']],label=label,linewidth=.65)
    axs[1].plot(t,[r['action_log']['actual_end_limited_command'][i] for r in last['transitions']],label=label,linewidth=.65)
angles=[]
for r in last['transitions']:
    w,xq,yq,zq=r['trace_row']['quaternion_wxyz']
    angles.append((math.degrees(math.atan2(2*(w*xq+yq*zq),1-2*(xq*xq+yq*yq))),math.degrees(math.asin(max(-1,min(1,2*(w*yq-zq*xq)))))))
axs[2].plot(t,[a[0] for a in angles],label='实际 roll',linewidth=.7);axs[2].plot(t,[a[1] for a in angles],label='实际 pitch',linewidth=.7)
for ax,title,y in zip(axs,('残差请求','周期末总限幅命令（含基线）','实际姿态'),('rad/s','rad/s','度')):
    ax.set(title=title,ylabel=y);ax.legend(loc='upper right');ax.axvline(last['stop_time'],color='#c96548',linestyle='--',linewidth=.8)
axs[2].set_xlabel('仿真时间 / s');fig.suptitle('第9训练回合：请求—命令—实际姿态；虚线为停止触发');fig.savefig(D/'停止回合动作与姿态.png');plt.close(fig)
print(json.dumps({k:v for k,v in result.items() if k not in ('physical_audits','archives_sha256')},ensure_ascii=False))
