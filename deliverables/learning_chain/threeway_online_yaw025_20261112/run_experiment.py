"""Frozen 18-simulation / 909-update from-scratch A/B/C online pilot."""
import argparse
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
OLD=OUT.parent/'reward_shaping_yaw025_minimal_20261112'
import importlib.util
spec=importlib.util.spec_from_file_location('frozen_reward_helpers',OLD/'run_experiment.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
read,write,sha,now=helper.read,helper.write,helper.sha,helper.now
REG=OUT/'registration.json'


@contextmanager
def loaders(group):
    from tools.learning import switchable_capture
    from tools.validation import recovery_learning_audit
    from tools.learning.threeway_online import load
    def bound(*args,**kwargs): return load(*args,**kwargs,group=group)
    with patch.object(switchable_capture,'load_checkpoint',bound),patch.object(recovery_learning_audit,'load_checkpoint',bound):
        yield


def binding(reg,group,source):
    from tools.learning.recovery_learning_contract import ARCHIVE_VERSION,digest
    cfg=reg['groups'][group]['config']
    return dict(stage='G2',common=reg['common'],experiment=dict(version=ARCHIVE_VERSION,
        config_sha256=digest(cfg),policy_mode=cfg['policy_mode'],source_checkpoint=source['checkpoint_sha256'],
        optimizer_updates=source['optimizer_updates'],physical_protocol=cfg['physical_protocol']))


def entry(experiment,path):
    from tools.learning.threeway_online import save
    from tools.learning.switchable_sac import tensor_digest
    return dict(path=path.relative_to(OUT).as_posix(),checkpoint_sha256=save(experiment,path),
        actor_sha256=tensor_digest(experiment.actor.state_dict()),**experiment.training_summary)


def prepare():
    helper.select()
    from tools.learning.recovery_learning_contract import experiment_config,digest
    from tools.learning.threeway_online import OnlineExperiment,SAMPLER
    from tools.learning.geometry_reward_shaping import SPEC
    from tools.validation.load_warning_mesh_contact_qualification import build_mesh_contact_qualification
    if REG.exists(): raise FileExistsError(REG)
    previous=read(OLD/'registration.json')
    if read(OLD/'verification.json').get('verified') is not True: raise ValueError('Prior verified physical evidence required')
    physical=build_mesh_contact_qualification();write(OUT/'physical_basis.json',physical)
    groups={}
    for group,mode in [('A','gru'),('B','gru'),('C','mlp')]:
        cfg=experiment_config(mode,seed=2026110801,physical_protocol='load_warning_7pct_mesh_contact',focus_search_entry=mode=='gru')
        obj=OnlineExperiment(cfg,group)
        jobs=[]
        for i,old in enumerate(previous['train']):
            job=deepcopy(old);job['episode_id']=group+'_'+old['episode_id'].split('_')[0]
            job['policy_mode']=mode
            job['required_updates']=[0,0,101,202][i];jobs.append(job)
        evaluation=[]
        for old in previous['evaluate']:
            job=deepcopy(old);job['episode_id']=group+'_'+old['episode_id'].split('_')[0]
            job.update(policy_mode=mode,method=mode)
            job['required_updates']=303;evaluation.append(job)
        groups[group]=dict(config=cfg,initial=entry(obj,OUT/'checkpoints'/(group+'_initial')),train=jobs,evaluate=evaluation,
                           actor_parameters=sum(p.numel() for p in obj.actor.parameters()))
    if groups['A']['initial']['actor_sha256']!=groups['B']['initial']['actor_sha256']: raise ValueError('A/B initialization differs')
    for name in ('run','requests','monitor','rewards','qualifications'): (OUT/name).mkdir(exist_ok=True)
    sources={p.relative_to(ROOT).as_posix():sha(p) for folder,suffix in [('tools','*.py'),('models','*.xml')]
             for p in (ROOT/folder).rglob(suffix)}
    for p in (Path(__file__),OLD/'run_experiment.py',OLD/'verification.json',OLD/'registration.json',
              helper.YAW1/'run_e01.py',OUT/'physical_basis.json',ROOT/'docs/superpowers/plans/2026-11-12-threeway-online.md'):
        sources[p.relative_to(ROOT).as_posix()]=sha(p)
    reg=dict(version='threeway_online_pilot_v1',prepared_utc=now(),common=physical['common'],groups=groups,
        source_sha256=sources,physical_basis_sha256=sha(OUT/'physical_basis.json'),
        sampler=SAMPLER,rewards=dict(A='original_NewtonReward',B=SPEC,C=SPEC),
        intervention=previous['intervention'],updates_per_round=101,rounds=3,
        budget=dict(training_simulations=12,evaluation_simulations=6,optimizer_updates=909),
        previous_initializations=read(OLD/'verification.json')['cumulative_initializations'],
        admission_rule='Each group requires its own two zero-update warmup archives to pass unchanged full physical/source and yaw/authority audits before any replay publication or training.',
        evaluation_rule='Only final303, one paired seed, E01/E02 development; no best-checkpoint selection or automatic retries.',
        inference_limit='Pilot only; no convergence/generalization verdict. C has short force history in 140D input; no D group interaction estimate.')
    write(REG,reg);print('REGISTERED',sha(REG),flush=True)


def verify(pin):
    if sha(REG)!=pin: raise ValueError('Registration changed')
    reg=read(REG)
    for name,value in reg['source_sha256'].items():
        if sha(ROOT/name)!=value: raise ValueError('Frozen source changed: '+name)
    return reg


def qualification(reg,group):
    cfg=reg['groups'][group]
    records=[]
    for job in cfg['train'][:2]:
        folder=OUT/'run'/job['episode_id'];proof=read(folder/'audit.json');receipt=read(folder/'receipt.json')
        if (proof.get('verified') is not True or proof.get('source_replay_verified') is not True
                or proof['policy_mode']!=cfg['config']['policy_mode'] or proof['optimizer_updates']!=0
                or proof['source_checkpoint_sha256']!=cfg['initial']['checkpoint_sha256']
                or sha(folder/'episode.json.gz')!=receipt['archive_sha256']): raise ValueError('Own warmup qualification failed')
        records.append(dict(job=job,archive_sha256=receipt['archive_sha256'],audit_sha256=sha(folder/'audit.json')))
    result=dict(version='threeway_per_mode_dynamic_qualification_v1',verified=True,group=group,
        registration_sha256=sha(REG),physical_basis_sha256=reg['physical_basis_sha256'],warmup=records,
        scope='Only registered four training cases and this algorithm/config, with fresh per-episode physical/source audit; no general runtime qualification claim.')
    path=OUT/'qualifications'/(group+'.json')
    if path.exists(): raise FileExistsError(path)
    write(path,result)
    return sha(path)


def worker(reg,action,request):
    import numpy as np
    from tools.learning.recovery_learning_contract import digest
    from tools.learning.threeway_online import load,training_batches
    from tools.learning.switchable_sac import _episode_digest,tensor_digest
    group=request['group']; cfg=reg['groups'][group]['config'];source=request['source']
    checkpoint=OUT/source['path'];job=request.get('job')
    helper.select()
    if action=='optimize':
        exp=load(checkpoint,config=cfg,expected_digest=source['checkpoint_sha256'],group=group)
        round_=request['round']; expected_episodes=round_+1
        if (round_ not in (1,2,3) or exp.optimizer_updates!=(round_-1)*101
                or exp.training_summary['admitted_episodes']!=expected_episodes): raise ValueError('Online schedule differs')
        overlays={};pins={}
        for key,arrays in exp._replay._state.episodes:
            path=OUT/'rewards'/(key+'.npz');meta=read(path.with_suffix('.json'))
            if sha(path)!=meta['overlay_sha256']: raise ValueError('Overlay changed')
            data=np.load(path)
            if not np.array_equal(data['old'].astype(np.float32),arrays['rewards'][:,0]): raise ValueError('Raw rewards differ')
            overlays[key]=data['new'];pins[key]=sha(path)
        progress=OUT/'monitor'/(group+'_optimizer.json')
        try:
            with training_batches(exp,overlays,pins) as records:
                for i in range(101):
                    write(progress,dict(round=round_,updates=exp.optimizer_updates,in_progress=True,failed_attempts=0,status='RUNNING'))
                    exp.update_from_replay()
                    if cfg['policy_mode']=='mlp': exp._training['updates'][-1].update(records[-1])
                    write(progress,dict(round=round_,updates=exp.optimizer_updates,in_progress=False,failed_attempts=0,status='RUNNING'))
        except BaseException:
            write(progress,dict(round=round_,updates=exp.optimizer_updates,in_progress=False,
                                failed_attempts=exp.failed_update_attempts,status='ERROR'))
            raise
        target=OUT/'checkpoints'/(group+'_trained_'+str(round_))
        result=entry(exp,target)
        restored=load(target,config=cfg,expected_digest=result['checkpoint_sha256'],group=group)
        if tensor_digest(restored.actor.state_dict())!=result['actor_sha256']: raise ValueError('Restored actor differs')
        write(OUT/(group+'_optimization_'+str(round_)+'.json'),dict(result,batches=records,updates=exp._training['updates'][-101:],source=source))
        write(progress,dict(round=round_,updates=exp.optimizer_updates,in_progress=False,failed_attempts=0,status='CHECKPOINTED'))
        return
    if job not in reg['groups'][group]['train']+reg['groups'][group]['evaluate']: raise ValueError('Unregistered job')
    if source['optimizer_updates']!=job['required_updates']: raise ValueError('Behavior policy update count differs')
    folder=OUT/'run'/job['episode_id'];bind=binding(reg,group,source)
    if action=='capture':
        from tools.learning.switchable_capture import capture_quarantined
        with loaders(group),helper.capture_intervention():
            capture_quarantined(folder,bind,job,config=cfg,checkpoint_path=checkpoint)
        return
    if action=='audit':
        from tools.validation.recovery_learning_audit import audit_recovery_learning_archive
        with loaders(group): raw,receipt,proof=audit_recovery_learning_archive(folder,bind,job,checkpoint_path=checkpoint,config=cfg)
        proof.update(experiment_intervention=helper.supplement(raw),registration_sha256=sha(REG),archive_sha256=receipt['archive_sha256'])
        write(folder/'audit.json',proof)
        if job['split']=='train':
            from tools.learning.search_entry_replay import build_focus_labels
            write(folder/'focus.json',build_focus_labels(raw))
        del raw
        if job['split']=='train':
            old,new,summary=helper.score(folder);path=OUT/'rewards'/(job['episode_id']+'.npz')
            if path.exists(): raise FileExistsError(path)
            np.savez_compressed(path,old=old,new=new)
            write(path.with_suffix('.json'),dict(summary,overlay_sha256=sha(path)))
        return
    if action!='admit' or job['split']!='train': raise ValueError('Only registered training data may enter replay')
    from tools.validation.consistent_sac_audit import _read_archive
    from tools.learning.search_entry_replay import validate_focus_labels
    qualified=OUT/'qualifications'/(group+'.json');q=read(qualified)
    if (sha(qualified)!=request['qualification_sha256'] or q.get('verified') is not True
            or q['group']!=group or q['registration_sha256']!=sha(REG)): raise ValueError('Separate group qualification required')
    for item in q['warmup']:
        f=OUT/'run'/item['job']['episode_id']
        if sha(f/'audit.json')!=item['audit_sha256'] or sha(f/'episode.json.gz')!=item['archive_sha256']:
            raise ValueError('Qualified warmup changed')
    if sha(folder/'audit.json')!=request['audit_sha256'] or sha(folder/'focus.json')!=request['focus_sha256']:
        raise ValueError('Trusted admission evidence changed')
    proof=read(folder/'audit.json');raw,receipt=_read_archive(folder)
    if (proof.get('verified') is not True or proof.get('source_replay_verified') is not True
            or proof['archive_sha256']!=receipt['archive_sha256'] or proof['registration_sha256']!=sha(REG)
            or proof['episode_id']!=job['episode_id'] or proof['optimizer_updates']!=job['required_updates']):
        raise ValueError('Complete same-source audit required')
    exp=load(checkpoint,config=cfg,expected_digest=source['checkpoint_sha256'],group=group)
    # Warmup two was captured at the initial checkpoint before warmup one entered
    # replay. Admission can change replay but must not change behavior parameters.
    captured=read(OUT/'requests'/(job['episode_id']+'.audit.json'))['source']
    if proof['source_checkpoint_sha256']!=captured['checkpoint_sha256'] or source['actor_sha256']!=captured['actor_sha256']:
        raise ValueError('Admission behavior actor differs')
    labels=read(folder/'focus.json')
    validate_focus_labels(labels,episode_id=job['episode_id'],transition_count=len(raw['transitions']))
    if len(raw['transitions'])<128: raise ValueError('Insufficient complete learning window; no automatic extra collection')
    publication=exp._replay.publish(job['episode_id'],raw['transitions'],training_admitted=True,
        outcome=dict(raw['outcome'],valid_for_learning=True))
    arrays=exp._replay._state.episodes[-1][1]
    record=dict(episode_id=job['episode_id'],transitions=publication['committed'],optimizer_updates=exp.optimizer_updates,
        archive_sha256=receipt['archive_sha256'],registration_sha256=sha(REG),qualification_sha256=sha(qualified),
        source_checkpoint_sha256=proof['source_checkpoint_sha256'],job_sha256=digest(job),audit_sha256=digest(proof),replay_sha256=_episode_digest(arrays))
    if cfg['policy_mode']=='gru': record.update(search_entry_focus=labels,search_entry_focus_sha256=digest(labels))
    if exp._training is None: exp._training=dict(episodes=[],updates=[])
    exp._training['episodes'].append(record);exp._approved_replay_state=exp._replay._state
    exp.online['labels'][job['episode_id']]=labels
    exp.online.update(qualification_sha256=sha(qualified),registration_sha256=sha(REG))
    result=entry(exp,OUT/'checkpoints'/(job['episode_id']+'_admitted'))
    write(folder/'admission.json',dict(result,source=source,proof=record))


def launch(reg,pin):
    with (OUT/'launch.claim').open('x') as f: f.write(pin)
    ledger=dict(status='RUNNING',registration_sha256=pin,started_utc=now(),attempts=[],updates={},sources={})
    def persist():
        counters={g:read(p) for g in reg['groups'] if (p:=OUT/'monitor'/(g+'_optimizer.json')).exists()}
        ledger['update_costs']=dict(known_completed={g:r['updates'] for g,r in counters.items()},
            failed_attempts=sum(r['failed_attempts'] for r in counters.values()),
            unknown_in_progress=sum(bool(r['in_progress']) for r in counters.values()))
        ledger.update(helper.cost_totals(ledger['attempts'],reg['previous_initializations']));write(OUT/'ledger.json',ledger)
    def run(action,group,source,job=None,**extra):
        identity=job['episode_id'] if job else group+'_round'+str(extra['round'])
        req=OUT/'requests'/(identity+'.'+action+'.json')
        if req.exists(): raise FileExistsError(req)
        write(req,dict(group=group,source=source,job=job,**extra))
        args=[sys.executable,'-B','-X','utf8',str(__file__),action,'--pin',pin,'--request',str(req),'--request-pin',sha(req)]
        with (OUT/'monitor'/(identity+'.'+action+'.log')).open('xb') as log:
            subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=3600,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    def capture(group,job,source):
        folder=OUT/'run'/job['episode_id']
        row=dict(id=job['episode_id'],group=group,split=job['split'],status='CAPTURE',started_utc=now(),source=source)
        ledger['attempts'].append(row);persist();print(row['id'],'CAPTURE',flush=True)
        try:
            run('capture',group,source,job);row['status']='AUDIT';persist()
            run('audit',group,source,job);row['status']='AUDITED'
        except BaseException as exc: row.update(status='ERROR',error=repr(exc));raise
        finally:
            if (folder/'receipt.json').exists():
                r=read(folder/'receipt.json');row.update(outcome=r.get('outcome'),reset_attempted=r.get('reset_attempted'),
                    native_steps=r.get('physical_substeps'),reason=r.get('final_reason'),task_end_s=r.get('task_end_time_s'))
            row['ended_utc']=now();persist()
        print(row['id'],row['status'],row['outcome'],flush=True)
    def admit(group,job,source,qpin):
        folder=OUT/'run'/job['episode_id']
        run('admit',group,source,job,qualification_sha256=qpin,audit_sha256=sha(folder/'audit.json'),focus_sha256=sha(folder/'focus.json'))
        return read(folder/'admission.json')
    try:
        for group,settings in reg['groups'].items():
            source=settings['initial'];train=settings['train']
            for job in train[:2]: capture(group,job,source)
            qpin=qualification(reg,group)
            for job in train[:2]: source=admit(group,job,source,qpin)
            for round_ in (1,2,3):
                if round_>1:
                    job=train[round_];capture(group,job,source);source=admit(group,job,source,qpin)
                run('optimize',group,source,round=round_)
                source=read(OUT/(group+'_optimization_'+str(round_)+'.json'))
                # Avoid recursively embedding full optimization history into requests.
                source={k:source[k] for k in ('path','checkpoint_sha256','actor_sha256','admitted_episodes','admitted_transitions','optimizer_updates')}
                ledger['updates'][group]=source['optimizer_updates'];ledger['sources'][group]=source;persist()
            for job in settings['evaluate']: capture(group,job,source)
        ledger['status']='COMPLETED'
    except BaseException as exc:
        ledger.update(status='STOPPED',error=repr(exc));raise
    finally: ledger['ended_utc']=now();persist()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['prepare','launch','capture','audit','admit','optimize'])
    parser.add_argument('--pin');parser.add_argument('--request',type=Path);parser.add_argument('--request-pin')
    args=parser.parse_args()
    if args.action=='prepare': return prepare()
    reg=verify(args.pin)
    if args.action=='launch': return launch(reg,args.pin)
    if sha(args.request)!=args.request_pin: raise ValueError('Request changed')
    worker(reg,args.action,read(args.request))


if __name__=='__main__': main()
