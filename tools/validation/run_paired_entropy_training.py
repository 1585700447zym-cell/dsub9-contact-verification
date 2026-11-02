"""One-shot A0/A2 closed-loop trial: shared old warmup, 24 new resets, 8000 updates."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.learning.five_axis_preparation import (OUT as ORIGINAL,COMMON,canonical,read,sha,
    verify_inputs,freeze_sources,audit_archive,compare_zero_trace)
from tools.learning.paired_entropy_trial import ARMS,arm_configs,schedule,summarize_run
from tools.validation.run_yaw_pilot import (PYTHON,write,publish_archive,actual_common,
    model_archive_bytes,supervise)
from tools.validation.run_five_axis_training import select
from tools.validation.run_five_axis_entropy_screen import tensor_digest,probe

OUT=ROOT/'deliverables/learning_chain/five_axis_entropy_closed_loop_20261026'
SCREEN=ROOT/'deliverables/learning_chain/five_axis_execution_entropy_screen_20261026'
BASE=ORIGINAL/'training/checkpoint_4'
MAX_CYCLES=13500


def prepare():
    import torch
    from tools.learning.five_axis_checkpoint import load_checkpoint,save_checkpoint
    from tools.learning.five_axis_training import FiveAxisTrainer
    from tools.learning.five_axis_replay import FiveAxisReplay
    parent=read(ORIGINAL/'registration.json');verify_inputs(parent['inputs'])
    screen=read(SCREEN/'screen_registration.json');verify_inputs(screen['inputs'])
    closed=read(SCREEN/'verification.json')
    if closed['cumulative_initializations']!=391 or closed['new_initializations']:
        raise ValueError('Scientific cost boundary changed')
    for name,digest in closed['artifacts'].items():
        if sha(SCREEN/name)!=digest:raise ValueError('Closed mechanism evidence changed')
    admission=read(ORIGINAL/'admission.json')
    if sha(ORIGINAL/'registration.json')!=admission['registration_sha256']:
        raise ValueError('Original admission differs')
    base=load_checkpoint(BASE,expected_digest=screen['base_digest'],config=screen['base_config'])
    initial=load_checkpoint(ORIGINAL/'initial_checkpoint',expected_digest=admission['checkpoint_digest'],
                            config=screen['base_config'])
    network=tensor_digest(initial.updater.policy.state_dict());del initial
    if (base.update_attempts or base.policy_calls or len(base.replay)!=54000
            or tensor_digest(base.updater.policy.state_dict())!=network):
        raise ValueError('Untrained common network and four-warmup boundary required')
    OUT.mkdir()  # Preserve any previous/partial preparation; never silently replace it.
    sources=dict(parent['inputs']);provenance=[]
    for episode_id,arrays in base.replay._state.episodes:
        folder=ORIGINAL/'training'/episode_id
        receipt=read(folder/'receipt.json');audit=read(folder/'audit.json');pub=read(folder/'publication.json')
        if (not episode_id.startswith('warmup_') or not audit['verified']
                or not receipt['valid'] or not receipt['stopped']
                or sha(folder/'episode.json.gz')!=receipt['archive_sha256']
                or audit['archive_sha256']!=receipt['archive_sha256']
                or pub['archive_sha256']!=receipt['archive_sha256']
                or pub['audit_sha256']!=sha(folder/'audit.json')
                or pub['admission_sha256']!=sha(ORIGINAL/'admission.json')):
            raise ValueError('Shared warmup provenance differs')
        raw=json.loads(gzip.decompress((folder/'episode.json.gz').read_bytes()))
        prepared=FiveAxisReplay(capacity=172000)._prepare(raw['transitions'])
        if any(not np.array_equal(arrays[k],prepared[k]) for k in arrays):
            raise ValueError('Checkpoint replay differs from admitted physical archive')
        provenance.append(dict(episode=episode_id,rows=len(raw['transitions']),
            archive_sha256=receipt['archive_sha256'],audit_sha256=sha(folder/'audit.json'),
            publication_sha256=sha(folder/'publication.json'),new_physical_cost=0))
        for name in ('receipt.json','audit.json','publication.json','episode.json.gz'):
            sources[(folder/name).relative_to(ROOT).as_posix()]=sha(folder/name)
        del raw,prepared
    if len(provenance)!=4:raise ValueError('Four shared complete warmup episodes required')
    configs=arm_configs(screen['base_config']);digests={};initial_probes={};shared_receipts={}
    probe_bytes=(SCREEN/'screen_run/probe_states.npy').read_bytes()
    (OUT/'probe_states.npy').write_bytes(probe_bytes)
    states=torch.from_numpy(np.load(OUT/'probe_states.npy',allow_pickle=False).copy())
    for arm in ARMS:
        state=base.state_dict();state['config']=configs[arm]
        state['replay']['capacity']=172000
        state['updater']['alpha']=torch.tensor(math.log(configs[arm]['learning']['entropy_initial']),dtype=torch.float32)
        trainer=FiveAxisTrainer(configs[arm]);trainer.load_state_dict(state)
        if (tensor_digest(trainer.updater.policy.state_dict())!=network
                or not torch.equal(trainer.updater.rng_state,base.updater.rng_state)):
            raise ValueError('Derived initial network/RNG differs')
        digests[arm]=save_checkpoint(trainer,OUT/'initial'/arm)
        initial_probes[arm]=probe(trainer,states,2026102602)
        shared_receipts[arm]=dict(episodes=provenance,logical_rows=54000,physical_initializations=0,
            derived_checkpoint_sha256=digests[arm],inherited_warmup_draws=trainer.warmup_draws)
        del state,trainer
    for key in initial_probes['A0']:
        if key!='alpha' and initial_probes['A0'][key]!=initial_probes['A2'][key]:
            raise ValueError('Initial paired diagnostics differ')
    write(OUT/'shared_warmup_receipts.json',shared_receipts)
    write(OUT/'initial_diagnostics.json',initial_probes)
    new_files=[Path(__file__),ROOT/'tools/learning/paired_entropy_trial.py',
        ROOT/'tests/test_paired_entropy_trial.py']
    sources.update(freeze_sources(new_files,folder=OUT/'source_snapshot'))
    extra=[BASE/'manifest.json',BASE/'state.pt',ORIGINAL/'registration.json',ORIGINAL/'admission.json',
        SCREEN/'verification.json',SCREEN/'screen_registration.json',SCREEN/'screen_result.json',
        ROOT/'tools/validation/run_five_axis_entropy_screen.py',OUT/'probe_states.npy',
        OUT/'shared_warmup_receipts.json',OUT/'initial_diagnostics.json']
    for arm in ARMS:extra += [OUT/'initial'/arm/'manifest.json',OUT/'initial'/arm/'state.pt']
    for path in extra:sources[path.relative_to(ROOT).as_posix()]=sha(path)
    reg=dict(version='five_axis_paired_entropy_closed_loop_v1',inputs=sources,common=parent['common'],
        configs=configs,schedule=schedule(),initial_checkpoint_digests=digests,
        seed=screen['base_config']['learning']['seed'],paired_environment_seed_offset=4,
        max_initializations=24,cumulative_before=391,max_physical_substeps=3240000,
        max_control_cycles=MAX_CYCLES,updates_per_online_episode=500,total_updates=8000,
        max_worker_wall_s=1800,max_batch_wall_s=21600,max_parallel_workers=2,
        shared_old_warmup_episodes=4,shared_old_rows=54000,new_warmup_initializations=0,
        final_test_episodes=0,retries=0,resume=False,
        initial_network_sha256=network,
        first_pair_equivalence='same policy and physical traces before first optimizer update; tolerance1e-12',
        treatment='only entropy_initial 0.01 versus0.001; alpha_rate initial5 versus0.5 at2ms',
        online_pairing='same initial RNG/environment seeds; later experience and RNG consumption may diverge',
        selection='A2 strictly more full successes and >=2/4, guards/validity not worse: confirmation candidate only; ties no selection',
        stop='invalid/unqualified motion, audit/source/checkpoint/update failure stops batch; valid task/contact failures retained; no rerun',
        authorization='2026-10-26 user continued the documented A0/A2 closed-loop plan; no history or held-policy training')
    write(OUT/'registration.json',reg)
    write(OUT/'admission.json',dict(ready=True,registration_sha256=sha(OUT/'registration.json'),
        shared_warmup_archive_arrays_equal=True,initial_networks_and_rng_equal=True,
        original_qualified_code_unchanged=True,new_physical_qualifications=0,new_optimizer_updates=0))
    (OUT/'实施计划与启动记录.md').write_text(
        '# A0/A2五维残差SAC同期闭环对照\n\n2026-10-26，B.2第3项。\n\n'
        '用户已继续本轮。任务1：新参数/日程/中断记账离线检查、旧4预热字节/回放逐项一致性与初始权重/RNG准入。'
        '任务2：每对两个独立进程运行，审核通过才启动下一对；各8在线×500更新及4点确定性开发评价。'
        '任务3：结束后核对实际成本、训练更新与逐点评价，更新五份滚动记录。\n\n'
        '冻结上限24次新初始化、3240000物理子步、8000总更新，累计起点391、最多415。'
        '复用旧4预热（54000行），两支从共同未训练网络开始；A0/A2熵初值0.01/0.001，'
        '回放容量共同172000，2 ms决策、N2/450、奖励/保护/成功标准不变。已有短历史保留，不加新历史或20 ms保持训练。\n\n'
        '第一对在更新之前使用相同初始策略、随机状态和环境种子，其预算内物理轨迹应一致；'
        '后续由于策略/经验不同，不能宣称两支所有批次或噪声调用仍逐项相同。'
        '正常超时与有效接触保护失败保留；无效、超出已资格运动域、来源/审核/更新/检查点错误停批，无自动重跑、恢复或扩量。\n\n'
        'A2只有完整成功数高于A0且至少2/4、保护和有效性不劣时才列为进一步确认候选；'
        '平局不能以输出变大挑优。单种子四开发点、4000更新/支不代表收敛或泛化，无最终测试。'
        '实施复用当前隔离工作区与原审核链，仅新增入口及记账，不改旧冻结代码；首对成功不触发额外资格试验。\n',encoding='utf-8')
    print(json.dumps(dict(ready=True,shared_rows=54000,jobs=24,new_qualifications=0,new_updates=0)))


def ready():
    reg=read(OUT/'registration.json');admission=read(OUT/'admission.json')
    if (not admission['ready'] or admission['registration_sha256']!=sha(OUT/'registration.json')
            or reg['schedule']!=schedule() or reg['configs']!=arm_configs(reg['configs']['A0'])
            or reg['total_updates']!=8000 or reg['max_initializations']!=24):
        raise ValueError('Frozen trial registration differs')
    verify_inputs(reg['inputs']);return reg


def source_checkpoint(reg,arm,index):
    if index==0:return OUT/'initial'/arm,reg['initial_checkpoint_digests'][arm]
    previous=OUT/'run'/arm/reg['schedule'][index-1]['id']
    result=read(previous/'job_result.json')
    if result['status']!='FINISHED':raise ValueError('Complete previous boundary required')
    return previous/'checkpoint',result['checkpoint_sha256']


def worker(arm,index):
    reg=ready()
    if arm not in ARMS or not 0<=index<12:raise ValueError('Registered arm/index required')
    job=reg['schedule'][index];folder=OUT/'run'/arm/job['id']
    with (folder/'worker.claim').open('x'):pass
    started=time.monotonic();trainer=env=session=None;raw={}
    receipt=dict(case_id=job['id'],status='initializing',reset_attempted=0,physical_substeps=0,
                 policy_calls=0,control_cycles=0,valid=False,stopped=False)
    result=dict(status='LOADING',arm=arm,index=index,actual_updates_for_job=0,attempted_updates_for_job=0,
        registration_sha256=sha(OUT/'registration.json'))
    write(folder/'receipt.json',receipt);write(folder/'job_result.json',result)
    before_calls=before_updates=before_attempts=0
    batch_start=read(OUT/'batch_started.json')['unix_s']
    def enforce():
        if (time.monotonic()-started>reg['max_worker_wall_s'] or time.time()-batch_start>reg['max_batch_wall_s']
                or (OUT/'STOP').exists()):raise RuntimeError('Trial runtime/stop bound; no retry')
    try:
        from tools.learning.five_axis_checkpoint import load_checkpoint,save_checkpoint
        source,digest=source_checkpoint(reg,arm,index)
        trainer=load_checkpoint(source,expected_digest=digest,config=reg['configs'][arm])
        before_updates=trainer.updater.counts['critic'];before_attempts=trainer.update_attempts
        before_calls=trainer.policy_calls
        if before_updates!=min(index,8)*500:raise ValueError('Update boundary differs')
        result.update(source_checkpoint_sha256=digest,status='COLLECTING')
        write(folder/'job_result.json',result)
        runtime=select()
        from tools.learning.five_axis_session import session_class
        from tools.learning.five_axis_collection import CollectionError
        from tools.learning.newton_profile import build_model_xml
        from tools.validation.yaw_pilot import environment_class,YawContactCase
        try:
            env=environment_class()();model_bytes=model_archive_bytes(build_model_xml(env.profile))
            (folder/'model_used.xml').write_bytes(model_bytes)
            receipt.update(actual_common(env,runtime,model_bytes))
            if any(canonical(receipt[k])!=canonical(reg['common'][k]) for k in COMMON):
                raise ValueError('Physical/runtime domain differs')
            Base=session_class()
            class BoundedSession(Base):
                def advance_cycle(self,action):
                    enforce();cycle=super().advance_cycle(action)
                    if self.cycle_id%100==0:
                        write(folder/'progress.json',dict(cycles=self.cycle_id,physical_substeps=env.physical_steps,
                            reset_attempted=1,policy_calls=trainer.policy_calls-before_calls,
                            phase=cycle.next_snapshot.controller_state['phase']))
                    return cycle
            session=BoundedSession(env);point=YawContactCase(**job['case'])
            receipt.update(case=asdict(point),reset_attempted=1,
                seed=reg['seed']+reg['paired_environment_seed_offset']+index)
            write(folder/'receipt.json',receipt)
            raw=trainer.collect(session,point,seed=receipt['seed'],max_cycles=MAX_CYCLES,
                                deterministic=job['stage']=='development')
            receipt.update(status='finished',valid=raw['outcome']['simulation_valid'],
                stopped=raw['outcome']['physical_stopped'],outcome=raw['outcome']['task_outcome'],
                final_reason=session.reason,finish_criteria=session.finish_criteria)
        except CollectionError as exc:
            raw=exc.archive;receipt.update(status='error',error=repr(exc));raise
        except BaseException as exc:
            receipt.update(status='error',error=repr(exc));raise
        finally:
            if env is not None:
                receipt.update(physical_substeps=env.physical_steps,guard_facts=env.guard_facts,
                    control_cycles=getattr(session,'cycle_id',0),
                    actuator_counters={k:getattr(env,k) for k in
                        ('command_limited_steps','drive_saturation_steps','reference_limited_steps')})
            receipt.update(policy_calls=trainer.policy_calls-before_calls,elapsed_wall_s=time.monotonic()-started)
            publish_archive(folder,raw,receipt)
        result['status']='AUDITING';write(folder/'job_result.json',result)
        raw,receipt,audit=audit_archive(folder,reg)
        write(folder/'audit.json',dict(audit,archive_sha256=receipt['archive_sha256'],
            admission_sha256=sha(OUT/'admission.json')))
        result['physical_trace_sha256']=hashlib.sha256(canonical(raw['trace']).encode()).hexdigest()
        if job['publish']:
            publication=trainer.publish(job['id'],raw['transitions'],
                outcome=dict(raw['outcome'],valid_for_learning=True),training_admitted=True)
            write(folder/'publication.json',dict(publication,archive_sha256=receipt['archive_sha256'],
                audit_sha256=sha(folder/'audit.json'),admission_sha256=sha(OUT/'admission.json')))
        del raw
        result['status']='UPDATING' if job['updates_after'] else 'SAVING'
        write(folder/'job_result.json',result);telemetry=[]
        for _ in range(job['updates_after']):
            enforce()
            batch=trainer.replay.sample(trainer.config['learning']['batch_size'],rng=trainer.replay_rng)
            trainer.update_attempts+=1;log=trainer.updater.update(batch)
            trainer.history.append(deepcopy(log))
            telemetry.append(dict(update=trainer.update_attempts,terminal_rows=int(batch.terminated.sum()),
                                  truncated_rows=int(batch.truncated.sum()),**log))
            if len(telemetry)%25==0:
                write(folder/'update_progress.json',dict(actual_updates_for_job=trainer.updater.counts['critic']-before_updates,
                    attempted_updates_for_job=trainer.update_attempts-before_attempts,alpha=log['alpha_after']))
        if telemetry:
            write(folder/'update_telemetry.json',telemetry)
            import torch
            states=torch.from_numpy(np.load(OUT/'probe_states.npy',allow_pickle=False).copy())
            write(folder/'diagnostics.json',probe(trainer,states,2026102602))
        checkpoint=save_checkpoint(trainer,folder/'checkpoint')
        result.update(status='FINISHED',checkpoint_sha256=checkpoint,replay_rows=len(trainer.replay),
            outcome=receipt['outcome'],final_reason=receipt['final_reason'])
        verify_inputs(reg['inputs'])
    except BaseException as exc:
        result.update(status='ERROR',error=repr(exc));raise
    finally:
        if trainer is not None:
            result.update(actual_updates_for_job=trainer.updater.counts['critic']-before_updates,
                          attempted_updates_for_job=trainer.update_attempts-before_attempts)
        result['elapsed_wall_s']=time.monotonic()-started;write(folder/'job_result.json',result)


def run():
    reg=ready();(OUT/'run').mkdir()
    for arm in ARMS:(OUT/'run'/arm).mkdir()
    write(OUT/'batch_started.json',dict(unix_s=time.time()))
    started=time.monotonic();status='RUNNING';error=None
    def publish_ledger():
        data=summarize_run(OUT/'run');data.update(status=status,error=error,
            elapsed_wall_s=time.monotonic()-started,registration_sha256=sha(OUT/'registration.json'))
        write(OUT/'ledger.json',data);return data
    def launch(arm,index):
        folder=OUT/'run'/arm/reg['schedule'][index]['id'];folder.mkdir()
        return supervise([str(PYTHON),'-B','-X','utf8',str(Path(__file__)),'--worker',arm,'--index',str(index)],
                         folder,timeout=reg['max_worker_wall_s']+180)
    publish_ledger()
    try:
        for index in range(12):
            ready()
            if time.monotonic()-started>reg['max_batch_wall_s'] or (OUT/'STOP').exists():
                raise RuntimeError('Batch bound before next pair')
            with ThreadPoolExecutor(max_workers=2) as pool:
                proofs=list(pool.map(lambda arm:launch(arm,index),ARMS))
            publish_ledger()
            for arm,proof in zip(ARMS,proofs):
                folder=OUT/'run'/arm/reg['schedule'][index]['id']
                result=read(folder/'job_result.json') if (folder/'job_result.json').exists() else {}
                if (proof.get('returncode')!=0 or not proof.get('process_exit_confirmed')
                        or result.get('status')!='FINISHED'):
                    raise RuntimeError('Job invalid/unverified; no next pair: '+arm+' '+str(index))
            if index==0:
                a,b=[OUT/'run'/arm/reg['schedule'][0]['id'] for arm in ARMS]
                same=read(a/'job_result.json')['physical_trace_sha256']==read(b/'job_result.json')['physical_trace_sha256']
                equivalence=dict(verified=True,trace_bytes_equal=same,tolerance=1e-12)
                if not same:
                    traces=[json.loads(gzip.decompress((f/'episode.json.gz').read_bytes()))['trace'] for f in (a,b)]
                    equivalence['differences']=compare_zero_trace(*traces)
                write(OUT/'initial_pair_equivalence.json',equivalence)
            print(json.dumps(dict(pair=index+1,case=reg['schedule'][index]['case']['name'],
                updates=summarize_run(OUT/'run')['updates_by_arm'])),flush=True)
        status='COMPLETED'
    except BaseException as exc:
        status='STOPPED';error=repr(exc);raise
    finally:publish_ledger()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true');group.add_argument('--check-ready',action='store_true')
    group.add_argument('--run',action='store_true');group.add_argument('--launch',action='store_true')
    group.add_argument('--worker',choices=ARMS);parser.add_argument('--index',type=int)
    args=parser.parse_args()
    if args.prepare:prepare()
    elif args.check_ready:ready();select();print('Ready; no new physics or updates.')
    elif args.worker:worker(args.worker,args.index)
    elif args.run:run()
    else:
        ready()
        with (OUT/'launcher.claim').open('x'):pass
        with (OUT/'launcher.log').open('xb') as log:
            proc=subprocess.Popen([str(PYTHON),'-B','-X','utf8',str(Path(__file__)),'--run'],cwd=ROOT,
                stdout=log,stderr=subprocess.STDOUT,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            write(OUT/'process_started.json',dict(pid=proc.pid,supervisor_pid=os.getpid(),unix_s=time.time()))
            code=proc.wait()
        write(OUT/'process_exit.json',dict(process_exit_confirmed=True,exit_code=code))
        return code
    return 0


if __name__=='__main__':raise SystemExit(main())
