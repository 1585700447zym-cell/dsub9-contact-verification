"""Paired 500-update fixed-replay entropy mechanism screen; never runs physics."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.learning.five_axis_preparation import read,sha,verify_inputs,freeze_sources,OUT as ORIGINAL
from tools.validation.run_yaw_pilot import write
OUT=ROOT/'deliverables/learning_chain/five_axis_execution_entropy_screen_20261026'
BASE=ORIGINAL/'training/checkpoint_4'
UPDATES=500


def prepare():
    parent=read(ORIGINAL/'registration.json');verify_inputs(parent['inputs'])
    admission=read(ORIGINAL/'admission.json')
    if sha(ORIGINAL/'initial_checkpoint/manifest.json')!=admission['checkpoint_digest']:
        raise ValueError('Original untrained checkpoint binding differs')
    close=ROOT/'deliverables/learning_chain/five_axis_training_execution_20261024/completion_verification.json'
    proof=read(close)
    if sha(ORIGINAL/'training/ledger.json')!=proof['ledger_sha256']:
        raise ValueError('Closed previous ledger differs')
    pins=dict(parent['inputs'])
    paths=[Path(__file__),ROOT/'tools/validation/diagnose_exploration_contact.py',
           BASE/'manifest.json',BASE/'state.pt',ORIGINAL/'initial_checkpoint/manifest.json',
           ORIGINAL/'initial_checkpoint/state.pt',ORIGINAL/'training/ledger.json',close]
    pins.update(freeze_sources(paths,folder=OUT/'screen_source_snapshot'))
    protocol=dict(version='five_axis_fixed_replay_entropy_mechanism_v1',inputs=pins,
        base_checkpoint=str(BASE.relative_to(ROOT)),base_digest=sha(BASE/'manifest.json'),
        untrained_digest=admission['checkpoint_digest'],base_config=parent['training_plan']['config'],
        arms=[dict(id='A0',alpha_initial=.01,alpha_rate_initial=5.),
              dict(id='A1',alpha_initial=.00002,alpha_rate_initial=.01)],
        updates_per_arm=UPDATES,total_updates=1000,shared_replay_episodes=4,shared_replay_rows=54000,
        policy_period_s=.002,shared_batches=True,probe_rows=2048,probe_updates=[0,100,500],
        max_wall_s=600,new_initializations=0,new_physical_substeps=0,final_tests=0,
        neural_control_calls=0,new_replay_publications=0,
        interpretation='Fixed data mechanism screen only; not online SAC efficacy or a candidate selection test',
        only_treatment='entropy_initial; same dt gives alpha_rate=alpha/dt, no production reparameterization',
        stop='Any source, shared-state, numerical or update failure ends screen; no retry or extension',
        authority='User continues the two goals: check execution then controlled entropy strength; efficient minimal work')
    with (OUT/'screen_registration.json').open('x',encoding='utf-8') as f:
        json.dump(protocol,f,ensure_ascii=False,indent=2,allow_nan=False)
    (OUT/'实施计划.md').write_text(
        '# 接触执行定位与熵强度机制筛查\n\n2026-10-26，B.2第3项。\n\n'
        '目标：先定位命令与运动差距，再以最低必要成本检查熵强度是否改变策略中心。\n\n'
        '1. 已完成：同4份V1档案的接触反力、驱动饱和采样、参考前导及保持对照；0次新仿真。\n'
        '2. 已登记：复用首轮checkpoint_4内4个已准入预热回合（54000行），重新从相同未训练权重开始，'
        'A0/A1各500更新；初值alpha=0.01/0.00002，其余配置、批次、RNG起点一致。'
        '不使用本轮V1保持数据，不新增物理经验，也不接续旧2000更新策略。\n'
        '3. 待执行：数值/来源核对后做1000个总更新；固定2048个旧训练状态于0/100/500记录中心、随机宽度、熵、Q对动作的区分。'
        '没有自动延长、重复种子、在线控制或成功率评价；原28回合方案不启动。\n'
        '4. 待收口：报告单因素响应及局限，同步五份滚动材料，保留所有旧档案。\n\n'
        '范围决定：将原完整同期在线对照缩为机制筛查，避免在接触执行仍受约束时直接扩大物理训练；'
        '因此本轮不能回答成功率、收敛或最终候选选择，后续在线试验另登记。'
        '固定2 ms下现有实现已支持不同alpha初值，alpha_rate仅做等价量纲标注，未宣称实现宏动作训练或通用熵率版本。\n',encoding='utf-8')
    print('Prepared paired fixed-replay screen: 500 updates per arm, no physics.')


def tensor_digest(tensors):
    digest=hashlib.sha256()
    for name,value in sorted(tensors.items()):
        digest.update(name.encode());digest.update(value.detach().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


def probe(trainer,states,seed):
    import torch
    from torch.distributions import Normal
    actor=trainer.updater.policy.actor
    with torch.no_grad():
        mu,logs,_=actor.get_action_dist_params(states);sigma=logs.exp()
        generator=torch.Generator().manual_seed(seed)
        noise=torch.randn((16,len(states),5),generator=generator)
        noise=torch.cat((noise,-noise),0)
        z=mu[None]+sigma[None]*noise;a=torch.tanh(z)
        lp=Normal(mu,sigma).log_prob(z)-torch.log(1-a*a+1e-6)
        zero=torch.zeros((len(states),5));q0=torch.cat(trainer.updater.policy.critic(states,zero),1).min(1).values
        differences=[]
        for axis in range(5):
            ap=zero.clone();am=zero.clone();ap[:,axis]=1;am[:,axis]=-1
            qp=torch.cat(trainer.updater.policy.critic(states,ap),1).min(1).values
            qm=torch.cat(trainer.updater.policy.critic(states,am),1).min(1).values
            differences.append(float(abs(qp-qm).mean()))
        return dict(deterministic_mean_abs=torch.tanh(mu).abs().mean(0).tolist(),
            sigma_mean=sigma.mean(0).tolist(),sample_mean_abs=a.abs().mean((0,1)).tolist(),
            joint_entropy_nats=float(-lp.sum(-1).mean()),
            q_plus_minus_full_action_mean_abs_difference=differences,q_zero_mean=float(q0.mean()),
            alpha=float(trainer.updater.log_alpha.detach().exp()))


def run():
    import torch
    from tools.learning.five_axis_checkpoint import load_checkpoint,save_checkpoint
    from tools.learning.five_axis_training import FiveAxisTrainer
    protocol=read(OUT/'screen_registration.json');verify_inputs(protocol['inputs'])
    (OUT/'screen_run').mkdir()  # No repeat or resume.
    started=time.monotonic()
    ledger=dict(status='PREPARING',updates=dict(A0=0,A1=0),new_initializations=0,
        new_physical_substeps=0,neural_control_calls=0,diagnostic_forward_batches=0,
        registration_sha256=sha(OUT/'screen_registration.json'))
    write(OUT/'screen_ledger.json',ledger)
    try:
        base=load_checkpoint(BASE,expected_digest=protocol['base_digest'],config=protocol['base_config'])
        initial=load_checkpoint(ORIGINAL/'initial_checkpoint',expected_digest=protocol['untrained_digest'],
                                config=protocol['base_config'])
        if (base.update_attempts or base.policy_calls or len(base.replay)!=54000
                or len(base.replay._state.episodes)!=4
                or tensor_digest(base.updater.policy.state_dict())!=tensor_digest(initial.updater.policy.state_dict())):
            raise ValueError('Expected four warmups and identical untrained network')
        for episode_id,_ in base.replay._state.episodes:
            if not episode_id.startswith('warmup_'):raise ValueError('Unexpected replay provenance')
        initial_network=tensor_digest(initial.updater.policy.state_dict());del initial
        a0=base;state=deepcopy(base.state_dict())
        config=deepcopy(protocol['base_config']);config['learning']['entropy_initial']=.00002
        state['config']=config;state['updater']['alpha']=torch.tensor(math.log(.00002),dtype=torch.float32)
        a1=FiveAxisTrainer(config);a1.load_state_dict(state);del state
        if (tensor_digest(a0.updater.policy.state_dict())!=tensor_digest(a1.updater.policy.state_dict())
                or not torch.equal(a0.updater.rng_state,a1.updater.rng_state)
                or a0.replay_rng.bit_generator.state!=a1.replay_rng.bit_generator.state):
            raise ValueError('Paired initial weights/RNG differ')
        active=np.concatenate([v['observations'][v['action_active'][:,0]] for _,v in a0.replay._state.episodes])
        chosen=np.linspace(0,len(active)-1,protocol['probe_rows'],dtype=int)
        states=torch.from_numpy(active[chosen].copy())
        np.save(OUT/'screen_run/probe_states.npy',states.numpy(),allow_pickle=False)
        arms={'A0':a0,'A1':a1};probes={name:{'0':probe(t,states,2026102602)} for name,t in arms.items()}
        ledger.update(status='RUNNING',initial_network_sha256=initial_network,shared_replay_rows=len(a0.replay),
            diagnostic_forward_batches=2)
        write(OUT/'screen_ledger.json',ledger)
        batches=hashlib.sha256();history=[]
        for step in range(1,UPDATES+1):
            if time.monotonic()-started>protocol['max_wall_s']:raise RuntimeError('Screen wall bound')
            batch=a0.replay.sample(256,rng=a0.replay_rng)
            for key in batch.__dataclass_fields__:
                batches.update(getattr(batch,key).numpy().tobytes())
            a1.replay_rng.bit_generator.state=deepcopy(a0.replay_rng.bit_generator.state)
            record=dict(update=step)
            for name,trainer in arms.items():
                trainer.update_attempts+=1
                result=trainer.updater.update(batch);trainer.history.append(deepcopy(result))
                ledger['updates'][name]=trainer.update_attempts;record[name]=result
            history.append(record)
            if not torch.equal(a0.updater.rng_state,a1.updater.rng_state):
                raise ValueError('Paired training-noise RNG differs')
            if step in protocol['probe_updates']:
                for name,trainer in arms.items():probes[name][str(step)]=probe(trainer,states,2026102602)
                ledger['diagnostic_forward_batches']+=2
            if step%50==0:write(OUT/'screen_ledger.json',ledger)
        checkpoints={name:save_checkpoint(t,OUT/'screen_run'/name/'checkpoint') for name,t in arms.items()}
        write(OUT/'screen_run/update_history.json',history)
        write(OUT/'screen_result.json',dict(probes=probes,shared_batch_stream_sha256=batches.hexdigest(),
            initial_network_sha256=initial_network,paired_update_noise_rng_equal=True,
            probe_states_sha256=sha(OUT/'screen_run/probe_states.npy'),checkpoint_digests=checkpoints,
            total_updates=sum(ledger['updates'].values()),new_initializations=0,new_physical_substeps=0,
            neural_control_calls=0,diagnostic_forward_batches=ledger['diagnostic_forward_batches'],
            outcome='Mechanism observations only; no performance or convergence decision'))
        verify_inputs(protocol['inputs']);ledger['status']='COMPLETED'
    except BaseException as exc:
        ledger.update(status='STOPPED',error=repr(exc));raise
    finally:
        ledger['elapsed_wall_s']=time.monotonic()-started;write(OUT/'screen_ledger.json',ledger)
    print(json.dumps(probes,ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true');group.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if args.prepare:prepare()
    else:run()


if __name__=='__main__':main()
