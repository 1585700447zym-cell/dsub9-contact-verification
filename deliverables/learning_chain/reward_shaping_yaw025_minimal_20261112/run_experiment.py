"""Bounded paired reward screening: four shared captures, 101+101 updates, 2+2 dev runs.

Physical/source audits remain unchanged; a supplemental audit binds the SEARCH
yaw intervention. Reward overlays affect sampled training batches only and are
identified in every optimizer record. Resume training only through this runner.
"""
import argparse
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))
BASE=OUT.parent/'load_warning_mesh_contact_gru_short_20261110'
YAW1=OUT.parent/'load_warning_mesh_contact_e01_search_yaw025_20261110'
YAW2=OUT.parent/'load_warning_mesh_contact_e02_search_yaw025_20261111'
REG=OUT/'registration.json'
GAIN=.25
UPDATES=101


def read(path): return json.loads(Path(path).read_bytes())
def sha(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def write(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix('.pending')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    tmp.replace(path)
def now(): return datetime.now(timezone.utc).isoformat()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    obj=importlib.util.module_from_spec(spec); spec.loader.exec_module(obj); return obj
def select():
    from tools.validation.run_consistent_sac import select as choose
    from tools.learning.load_warning_mesh_contact_trial import RUNTIME_SHA256
    choose({'runtime_sha256':RUNTIME_SHA256})
def yaw_helper(): return module('yaw025_frozen',YAW1/'run_e01.py')


@contextmanager
def capture_intervention():
    from tools.learning import load_warning_mesh_contact_trial as trial
    factory=trial.session_class
    helper=yaw_helper()
    def session_class(speed):
        class Session(factory(speed)):
            def __init__(self,env):
                super().__init__(env)
                controller_factory=self.controller_factory
                self.controller_factory=lambda: helper.attach_search_gain(controller_factory(),GAIN)
        return Session
    with patch.object(trial,'session_class',session_class): yield


def supplement(raw):
    import numpy as np
    from tools.learning.global_residual_action import recompose_logged_command
    try:
        proof=yaw_helper().verify_gain(raw,GAIN)
    except ValueError as error:
        # This exact final guard is reached only after all per-row checks passed.
        if str(error)!='No nonzero SEARCH passive yaw output exercised': raise
        proof=dict(verified=True,status='NOT_EXERCISED',nonzero_search_rows=0,passive_output_gain=GAIN)
    if raw['force_recovery_protocol']['search_authority'] != dict(search_xy_residual_m_s=.00075,search_xy_acceleration_m_s2=.020):
        raise ValueError('Registered SEARCH authority differs')
    count=0
    for row in raw['transitions']:
        inputs=row['action_log']['composition_inputs']
        if inputs['phase']=='SEARCH':
            log=row['action_log']
            _,expected=recompose_logged_command(log,search_xy_limit_m_s=.0009,
                search_xy_residual_m_s=.00075,search_xy_acceleration_m_s2=.020)
            for key in ('requested_residual','predicted_limited_command','zero_residual_limited_command'):
                if not np.allclose(log[key],expected[key],rtol=0,atol=1e-12):
                    raise ValueError('Executed SEARCH authority differs: '+key)
            count+=1
    return dict(yaw=proof,search_authority_rows=count)


@contextmanager
def supplemented_audit():
    from tools.validation import recovery_learning_audit as audit
    original=audit.audit_recovery_learning_archive
    def verified(*args,**kwargs):
        raw,receipt,proof=original(*args,**kwargs)
        proof=dict(proof,experiment_intervention=supplement(raw),experiment_registration_sha256=sha(REG))
        return raw,receipt,proof
    with patch.object(audit,'audit_recovery_learning_archive',verified): yield


def compact(folder):
    """Retain only geometry and reward fields; no unbounded native sample arrays."""
    from tools.validation.analyze_g1_recovery import JsonStream
    trace=rows=None
    with gzip.open(folder/'episode.json.gz','rt',encoding='utf8') as f:
        stream=JsonStream(f)
        for key in stream.members(as_object=True):
            if key=='trace':
                trace=[{k:r[k] for k in ('time_s','position_m','quaternion_wxyz','phase','policy_phase') if k in r}
                       for _ in stream.members() for r in [stream.value()]]
            elif key=='transitions':
                rows=[{k:r[k] for k in ('reward','discount','terminated','truncated','dt')}|
                      {'phase':r['action_log']['composition_inputs']['phase']}
                      for _ in stream.members() for r in [stream.value()]]
            else: stream.discard()
    if trace is None or rows is None or len(trace)!=len(rows)+1: raise ValueError('Incomplete geometry trajectory')
    return trace,rows


def score(folder):
    import numpy as np
    from tools.learning.geometry_reward_shaping import potential,shaping
    trace,rows=compact(folder)
    phi=np.array([potential(r) for r in trace])
    gamma=np.array([r['discount'] for r in rows])
    terminal=np.array([r['terminated'] for r in rows])
    if not terminal[-1] or terminal[:-1].any() or any(r['truncated'] for r in rows):
        raise ValueError('Complete terminal episode needed for screening')
    old=np.array([r['reward'] for r in rows])
    delta=shaping(phi,gamma,terminal)
    residual=float(np.r_[1.,np.cumprod(gamma[:-1])]@delta+phi[0])
    if abs(residual)>1e-10: raise ValueError('Potential telescoping failed')
    if not np.allclose(gamma,np.exp(-np.array([r['dt'] for r in rows])/10),rtol=0,atol=1e-12):
        raise ValueError('Reward discount differs from SAC time constant')
    by_phase={}
    for phase in sorted({r['phase'] for r in rows}):
        mask=np.array([r['phase']==phase for r in rows]) & ~terminal
        if mask.any():
            by_phase[phase]=dict(rows=int(mask.sum()),old_rms=float(np.sqrt(np.mean(old[mask]**2))),
                shaping_rms=float(np.sqrt(np.mean(delta[mask]**2))),positive_shaping=int((delta[mask]>0).sum()),
                phi_rise=float(np.maximum(0,np.diff(phi)[mask]).sum()),phi_fall=float(np.minimum(0,np.diff(phi)[mask]).sum()))
    checkpoints=[]
    for t in (0,5,10,15,20,25,28,30):
        i=min(range(len(trace)),key=lambda i:abs(trace[i]['time_s']-t))
        checkpoints.append(dict(time_s=trace[i]['time_s'],phi=float(phi[i])))
    summary=dict(archive_sha256=sha(folder/'episode.json.gz'),transitions=len(rows),
        initial_phi=float(phi[0]),final_physical_phi=float(phi[-1]),terminal_next_phi=0.,
        min_phi=float(phi.min()),max_phi=float(phi.max()),telescoping_residual=residual,
        phases=by_phase,checkpoints=checkpoints)
    return old,old+delta,summary


def preflight():
    select()
    results={}
    for name,folder in [('E01',YAW1/'run/E01_GRU'),('E02',YAW2/'run/E02_GRU')]:
        _,_,summary=score(folder); results[name]=summary
        print(name,json.dumps(summary,ensure_ascii=False),flush=True)
    write(OUT/'preflight.json',dict(status='SCORING_CHECKED',development_only=True,episodes=results))


def binding(reg,source):
    from tools.learning.recovery_learning_contract import ARCHIVE_VERSION,digest
    return dict(stage='G2',common=reg['common'],g1_sha256=reg['g1_sha256'],training_jobs=reg['train_digests'],
        experiment=dict(version=ARCHIVE_VERSION,config_sha256=digest(reg['config']),policy_mode='gru',
            source_checkpoint=source['checkpoint_sha256'],optimizer_updates=source['optimizer_updates'],
            physical_protocol=reg['config']['physical_protocol']))


def prepare():
    from tools.learning.recovery_learning_contract import experiment_config,digest,verify_training_registration
    from tools.learning.switchable_sac import Experiment,save_checkpoint,tensor_digest
    from tools.validation.load_warning_mesh_contact_qualification import build_mesh_contact_qualification
    from tools.learning.geometry_reward_shaping import SPEC
    if REG.exists(): raise FileExistsError(REG)
    if read(OUT/'preflight.json')['status']!='SCORING_CHECKED': raise ValueError('Scoring preflight required')
    cfg=experiment_config('gru',seed=2026110801,physical_protocol='load_warning_7pct_mesh_contact',focus_search_entry=True)
    previous=read(BASE/'registration.json')
    proof=build_mesh_contact_qualification()
    write(OUT/'qualification.json',proof)
    initial=Experiment(cfg)
    if tensor_digest(initial.actor.state_dict())!=previous['initial']['actor_sha256']: raise ValueError('Initial actor differs')
    entry=dict(path='checkpoints/initial',checkpoint_sha256=save_checkpoint(initial,OUT/'checkpoints/initial'),
               optimizer_updates=0,actor_sha256=tensor_digest(initial.actor.state_dict()))
    for name in ('run','requests','monitor','rewards'): (OUT/name).mkdir(exist_ok=True)
    pins={p.relative_to(ROOT).as_posix():sha(p) for folder,suffix in [('tools','*.py'),('models','*.xml')]
          for p in (ROOT/folder).rglob(suffix)}
    for p in (Path(__file__),YAW1/'run_e01.py',YAW1/'verification.json',YAW2/'verification.json',
              BASE/'registration.json',OUT/'preflight.json'):
        pins[p.relative_to(ROOT).as_posix()]=sha(p)
    reg=dict(version='paired_reward_yaw025_screening_v1',prepared_utc=now(),config=cfg,initial=entry,
        common=proof['common'],g1_sha256=sha(OUT/'qualification.json'),train=previous['train'],evaluate=previous['evaluate'],
        train_digests=[digest(j) for j in previous['train']],source_sha256=pins,
        intervention=dict(phase='SEARCH',passive_yaw_output_gain=GAIN,xy_residual_m_s=.00075,xy_acceleration_m_s2=.020),
        rewards=dict(A='original_NewtonReward',B=SPEC),max_train_attempts=4,max_eval_attempts=4,updates_per_branch=UPDATES,
        previous_initializations=read(YAW2/'verification.json')['cumulative_initializations'],
        qualification_scope='Frozen repaired-domain qualification plus archived yaw025 E01/E02 evidence and supplemental per-cycle audit.',
        checkpoint_scope='Physical replay keeps original rewards. B learning uses pinned batch reward overlays recorded in every update; use this runner for continuation.',
        evaluation_rule='One fixed seed, shared collection, paired samples, final101 only, E01/E02 development; no retuning or extra attempts.')
    for job in reg['train']:
        verify_training_registration(binding(reg,entry),job,config=cfg,qualification_path=OUT/'qualification.json',
                                     expected_digest=digest(binding(reg,entry)))
    write(REG,reg)
    print('REGISTERED',sha(REG),flush=True)


def verify(pin):
    if sha(REG)!=pin: raise ValueError('Experiment registration changed')
    reg=read(REG)
    if sha(OUT/'qualification.json')!=reg['g1_sha256']: raise ValueError('Qualification changed')
    for name,value in reg['source_sha256'].items():
        if sha(ROOT/name)!=value: raise ValueError('Frozen source changed: '+name)
    return reg


def worker(reg,action,request):
    import numpy as np
    from tools.learning.recovery_learning_contract import digest
    source=request['source']; job=request.get('job'); branch=request.get('branch')
    cfg=reg['config']; checkpoint=OUT/source['path']; bind=binding(reg,source)
    if action=='optimize': return optimize(reg,source,branch)
    if job not in reg['train']+reg['evaluate']: raise ValueError('Unregistered case')
    folder=OUT/'run'/((branch+'_'+job['episode_id']) if branch else job['episode_id'])
    if action=='capture':
        from tools.learning.switchable_capture import capture_quarantined
        with capture_intervention(): capture_quarantined(folder,bind,job,config=cfg,checkpoint_path=checkpoint)
        return
    select()
    if action=='admit':
        from tools.learning.load_warning_pilot_update import admit_episode
        target=OUT/'checkpoints'/(job['episode_id']+'_admitted')
        with supplemented_audit():
            result=admit_episode(folder,dict(config=cfg,reg=bind,job=job),checkpoint_path=checkpoint,
                output_checkpoint=target,qualification_path=OUT/'qualification.json',registration_digest=digest(bind))
        write(folder/'audit.json',result.pop('audit'))
        write(folder/'admission.json',dict(result,path=target.relative_to(OUT).as_posix()))
        old,new,summary=score(folder)
        overlay=OUT/'rewards'/(job['episode_id']+'.npz')
        if overlay.exists(): raise FileExistsError(overlay)
        np.savez_compressed(overlay,old=old,new=new)
        write(OUT/'rewards'/(job['episode_id']+'.json'),dict(summary,overlay_sha256=sha(overlay)))
    elif action=='audit':
        from tools.validation.recovery_learning_audit import audit_recovery_learning_archive
        with supplemented_audit():
            from tools.validation import recovery_learning_audit
            _,_,proof=recovery_learning_audit.audit_recovery_learning_archive(folder,bind,job,checkpoint_path=checkpoint,config=cfg)
        write(folder/'audit.json',proof)
    else: raise ValueError(action)


def optimize(reg,source,branch):
    import numpy as np
    import torch
    from tools.learning.switchable_sac import load_checkpoint,save_checkpoint,tensor_digest,_episode_digest
    from tools.learning.geometry_reward_shaping import replace_batch_rewards,SPEC
    from tools.learning.recovery_learning_contract import digest
    from tools.learning import search_entry_replay
    if branch not in ('A','B'): raise ValueError('Unknown reward branch')
    experiment=load_checkpoint(OUT/source['path'],config=reg['config'],expected_digest=source['checkpoint_sha256'])
    if experiment.optimizer_updates!=0 or experiment.training_summary['admitted_episodes']!=4: raise ValueError('Four shared zero-update admissions required')
    overlay={}; overlay_pins={}; originals={}
    for key,arrays in experiment._replay._state.episodes:
        meta=read(OUT/'rewards'/(key+'.json')); path=OUT/'rewards'/(key+'.npz')
        if sha(path)!=meta['overlay_sha256']: raise ValueError('Reward overlay changed')
        data=np.load(path)
        if not np.array_equal(data['old'].astype(np.float32),arrays['rewards'][:,0]): raise ValueError('Overlay and admitted original rewards differ')
        overlay[key]=data['new']; overlay_pins[key]=meta['overlay_sha256']; originals[key]=_episode_digest(arrays)
    original_sampler=search_entry_replay.sample_focus_sequences
    batch_records=[]
    def sample(*args,**kwargs):
        batch,info=original_sampler(*args,**kwargs)
        h=hashlib.sha256()
        for field in fields(batch):
            value=getattr(batch,field.name)
            if field.name=='rewards': continue
            h.update(field.name.encode())
            h.update(value.numpy().tobytes() if isinstance(value,torch.Tensor) else repr(value).encode())
        old=batch.rewards
        changed=replace_batch_rewards(batch,overlay) if branch=='B' else batch
        record=dict(input_except_reward_sha256=h.hexdigest(),episode_ids=list(batch.episode_ids),start_cycles=list(batch.start_cycles),
                    actual_reward_sha256=hashlib.sha256(changed.rewards.numpy().tobytes()).hexdigest(),
                    nonzero_reward_changes=int(torch.count_nonzero(changed.rewards-old)),
                    learning_reward_scheme='original' if branch=='A' else SPEC['version'],reward_overlay_sha256=digest(overlay_pins))
        batch_records.append(record)
        return changed,dict(info,**record)
    initial_actor=tensor_digest(experiment.actor.state_dict())
    with patch.object(search_entry_replay,'sample_focus_sequences',sample):
        for i in range(UPDATES):
            experiment.update_from_replay()
            write(OUT/'monitor'/(branch+'_optimizer.json'),dict(completed=i+1,target=UPDATES,updated_utc=now()))
    if originals!={key:_episode_digest(arrays) for key,arrays in experiment._replay._state.episodes}: raise ValueError('Original replay was mutated')
    target=OUT/'checkpoints'/('trained_'+branch)
    pin=save_checkpoint(experiment,target)
    actor=tensor_digest(experiment.actor.state_dict())
    restored=load_checkpoint(target,config=reg['config'],expected_digest=pin)
    if tensor_digest(restored.actor.state_dict())!=actor: raise ValueError('Saved actor differs')
    result=dict(path=target.relative_to(OUT).as_posix(),checkpoint_sha256=pin,actor_sha256=actor,initial_actor_sha256=initial_actor,
                **experiment.training_summary,source_checkpoint_sha256=source['checkpoint_sha256'],
                reward_scheme=reg['rewards'][branch],overlay_sha256=overlay_pins,batches=batch_records,
                replay_unchanged=True,updates=experiment._training['updates'])
    write(OUT/('optimization_'+branch+'.json'),result)
    print(branch,'optimized',UPDATES,actor,flush=True)


def cost_totals(attempts,previous):
    unknown=sum(r.get('reset_attempted') is None or r.get('native_steps') is None for r in attempts)
    known_init=sum(r.get('reset_attempted') or 0 for r in attempts)
    known_steps=sum(r.get('native_steps') or 0 for r in attempts)
    return dict(unknown_cost_attempts=unknown,known_initializations_lower_bound=known_init,
                known_native_steps_lower_bound=known_steps,stage_initializations=None if unknown else known_init,
                cumulative_initializations=None if unknown else previous+known_init,
                native_steps=None if unknown else known_steps)


def launch(reg,pin):
    with (OUT/'launch.claim').open('x') as f: f.write(pin)
    ledger=dict(status='RUNNING',started_utc=now(),registration_sha256=pin,attempts=[],updates={})
    def persist():
        ledger.update(cost_totals(ledger['attempts'],reg['previous_initializations']))
        write(OUT/'ledger.json',ledger)
    def run(action,job,source,branch=None):
        identity=(branch+'_' if branch else '')+(job['episode_id'] if job else 'OPTIMIZE')
        req=OUT/'requests'/(identity+'.'+action+'.json')
        write(req,dict(source=source,job=job,branch=branch))
        args=[sys.executable,'-B','-X','utf8',str(__file__),action,'--pin',pin,'--request',str(req),'--request-pin',sha(req)]
        with (OUT/'monitor'/(identity+'.'+action+'.log')).open('xb') as log:
            subprocess.run(args,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=3600,
                           creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    def episode(job,source,branch=None):
        name=(branch+'_' if branch else '')+job['episode_id']; folder=OUT/'run'/name
        row=dict(id=name,split=job['split'],status='CAPTURE',started_utc=now()); ledger['attempts'].append(row);persist()
        print(name,'CAPTURE',flush=True)
        try:
            run('capture',job,source,branch)
            row['status']='AUDIT';persist()
            run('audit' if branch else 'admit',job,source,branch)
            row['status']='AUDITED'
        except BaseException as exc:
            row.update(status='ERROR',error=repr(exc));raise
        finally:
            if (folder/'receipt.json').exists():
                r=read(folder/'receipt.json')
                row.update(outcome=r.get('outcome'),reset_attempted=r.get('reset_attempted'),native_steps=r.get('physical_substeps'),
                           reason=r.get('final_reason'),task_end_s=r.get('task_end_time_s'))
            row['ended_utc']=now();persist()
        print(name,row['status'],row['outcome'],flush=True)
        return folder
    source=reg['initial']
    try:
        for job in reg['train']:
            folder=episode(job,source);source=read(folder/'admission.json')
        ledger.update(status='OPTIMIZING',shared_checkpoint=source);persist()
        for branch in ('A','B'):
            run('optimize',None,source,branch);ledger['updates'][branch]=UPDATES;persist()
        a,b=[read(OUT/('optimization_'+branch+'.json')) for branch in ('A','B')]
        pairs=[x['input_except_reward_sha256']==y['input_except_reward_sha256'] for x,y in zip(a['batches'],b['batches'])]
        if len(pairs)!=UPDATES or not all(pairs) or a['initial_actor_sha256']!=b['initial_actor_sha256']: raise ValueError('Paired optimization differs beyond rewards')
        write(OUT/'pairing.json',dict(verified=True,batches=UPDATES,identical_nonreward_inputs=True,identical_initial_actor=True,
                                    shared_checkpoint_sha256=source['checkpoint_sha256']))
        ledger['status']='EVALUATING';persist()
        for branch,result in [('A',a),('B',b)]:
            for job in reg['evaluate']: episode(job,result,branch)
        ledger['status']='COMPLETED'
    except BaseException as exc:
        ledger.update(status='STOPPED',error=repr(exc));raise
    finally:
        ledger['ended_utc']=now();persist()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['preflight','prepare','launch','capture','admit','optimize','audit'])
    parser.add_argument('--pin');parser.add_argument('--request',type=Path);parser.add_argument('--request-pin')
    args=parser.parse_args()
    if args.action=='preflight': return preflight()
    if args.action=='prepare': return prepare()
    reg=verify(args.pin)
    if args.action=='launch': return launch(reg,args.pin)
    if sha(args.request)!=args.request_pin: raise ValueError('Worker request changed')
    worker(reg,args.action,read(args.request))


if __name__=='__main__': main()
