"""Admitted worker. CLI admission and GO gate precede every runtime import."""
from pathlib import Path
import argparse
import gzip
import hashlib
import importlib.util
import sys
import time
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(OUT))
from joint_contract import read,write,sha,canonical,learning_config,schedule,advance,validate_raw_identity,metric,LIMITS
from execution import Admission,Counter,verify_sources,verify_execution_copies,restore_equal,PHYSICAL_FIELDS


def state_digest(value):
    """Exact typed complete state fingerprint, including tensor/Adam/replay/RNG bytes."""
    h=hashlib.sha256()
    def visit(x):
        import numpy as np
        import torch
        def put(b):h.update(len(b).to_bytes(8,'big'));h.update(b)
        put(type(x).__name__.encode())
        if isinstance(x,torch.Tensor):
            put(str(x.dtype).encode());put(str(tuple(x.shape)).encode());put(x.detach().cpu().contiguous().numpy().tobytes())
        elif isinstance(x,np.ndarray):
            put(str(x.dtype).encode());put(str(x.shape).encode());put(x.tobytes())
        elif isinstance(x,dict):
            for k in sorted(x,key=lambda k:(type(k).__name__,repr(k))):visit(k);visit(x[k])
        elif isinstance(x,(list,tuple)):
            put(str(len(x)).encode())
            for item in x:visit(item)
        elif isinstance(x,bytes):put(x)
        else:put(canonical(x).encode())
    visit(value);return h.hexdigest()


def prepare_runtime(binding):
    expected=binding['runtime']
    if not sys.flags.isolated or Path(sys.executable).resolve()!=Path(binding['executable']).resolve():raise PermissionError('Frozen isolated CPU runtime required')
    for name,path in binding['runtime_package_paths'].items():
        spec=importlib.util.find_spec(name)
        if spec is None or spec.origin is None or Path(spec.origin).resolve()!=Path(path).resolve():raise ValueError('Unexpected package: '+name)
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    from tools.validation.run_v4_learning_pilot import verify_learning_runtime
    select_qualified_runtime();verify_learning_runtime(expected)


def physical(folder,chain,spec,ledger):
    verify_execution_copies(folder)
    if advance(ledger['episodes'])!=spec:raise ValueError('Physical sequence differs from registration')
    import joint_runtime as runtime
    from joint_rollout import rollout,audit_evaluation
    from joint_chain import audit_raw
    from joint_contract import learning_config
    if chain.updater.counts['critic']!=spec['optimizer_steps']:raise ValueError('Wrong policy/update boundary')
    entry=dict(id=spec['id'],healthy=False,status='running',started_at=time.time())
    ledger['episodes'].append(entry);write(folder/'run/ledger.json',ledger)
    write(folder/'phase_deadline.json',dict(started=time.time(),limit_s=1200,kind='physical',id=spec['id']))
    runtime.open_episode(spec['stage'])
    raw=rollout(folder,chain,spec,entry,ledger,stop_file=folder/'STOP')
    runtime.close_episode(raw['policy_calls']);validate_raw_identity(raw)
    if raw['control_cycles']>14500 or raw['physical_substeps']>145000:raise ValueError('Actual physical cost exceeds registered ceiling')
    if spec['stage'] in ('warmup','online'):audit_raw(raw,learning_config(),chain.binding)
    else:audit_evaluation(raw)
    out=raw['outcome']
    entry['healthy']=bool(out['simulation_valid'] and out['physical_stopped'] and out['task_outcome'] in ('FULL_SUCCESS','TASK_FAILURE') and not any(out['guard_violations'].values()))
    write(folder/'run/ledger.json',ledger)
    write(folder/'phase_deadline.json',dict(started=time.time(),limit_s=1800,kind='between_episodes'))
    if not entry['healthy']:raise RuntimeError('Episode failed validity/guard/stop; no further attempt')
    return raw


def launch_reader(folder,label,pin,expected_state,ledger):
    from supervised import bounded_process
    write(folder/'run'/(label+'.request.json'),dict(checkpoint_pin=pin,state_digest=expected_state))
    binding=read(OUT/'source_binding.json')
    bounded_process([binding['executable'],'-I','-X','utf8','-B',str(OUT/'pilot_worker.py'),'reader',str(folder),label],
        folder/'run'/(label+'.reader'),1800)
    reply=read(folder/'run'/(label+'.reply.json'))
    if reply['state_digest']!=expected_state:raise ValueError('Independent complete state differs')
    if label=='final':
        final=json.loads(gzip.decompress((folder/'run/final_F50_J01.json.gz').read_bytes()))
        restored=json.loads(gzip.decompress((folder/'run/restore_F50_J01.json.gz').read_bytes()))
        restore_equal(dict(state_digest=expected_state,physical={k:final[k] for k in PHYSICAL_FIELDS}),
            dict(state_digest=reply['state_digest'],physical={k:restored[k] for k in PHYSICAL_FIELDS}))
        ledger['episodes'].append(reply['entry']);ledger['policy_calls']+=restored['policy_calls']
        write(folder/'run/ledger.json',ledger)
    return reply


def execute(folder,admission,counter):
    import joint_runtime as runtime
    from joint_chain import V4Chain
    from joint_checkpoint import save_checkpoint,capture
    ledger=dict(status='RUNNING',episodes=[],policy_calls=0,training_admitted=False,independent_tests=0)
    write(folder/'run/ledger.json',ledger)
    chain=V4Chain(learning_config(),output=folder/'run/chain',binding=admission.verify('F50'),admission=admission)
    counter.take('checkpoint_saves');pin=save_checkpoint(chain,folder/'run/checkpoints/zero')
    launch_reader(folder,'zero',pin,state_digest(capture(chain)),ledger)
    ledger['zero_state_restore_verified']=True;write(folder/'run/ledger.json',ledger)
    for spec in schedule()[:-1]:
        admission.verify('F50')
        if spec['stage'] in ('warmup','online'):chain.begin(spec['stage'],spec['case_index'])
        raw=physical(folder,chain,spec,ledger)
        if spec['stage'] in ('warmup','online'):
            counter.take('replay_publications');chain.publish(raw)
            if spec['stage']=='online':
                # Same original credit/warmup/reward/mask machinery; no optimizer in rollout.
                runtime.allow_updates(500);chain.update(500,before_update=lambda current:current.verify())
        if spec['id']=='warmup_F50_J04':
            if not chain.warm_gate():raise ValueError('Original warmup gate failed')
            ledger['training_admitted']=True;write(folder/'run/ledger.json',ledger)
        if spec['id']=='online_F50_J04':
            counter.take('checkpoint_saves');pin=save_checkpoint(chain,folder/'run/checkpoints/final')
            final_state=state_digest(capture(chain))
    launch_reader(folder,'final',pin,final_state,ledger)
    scores={}
    for stage in ('zero','final'):
        rows=[]
        for c in ('J01','J02','J03','J04'):
            raw=json.loads(gzip.decompress((folder/'run'/(stage+'_F50_'+c+'.json.gz')).read_bytes()));out=raw['outcome']
            rows.append(dict(case_id=c,simulation_valid=out['simulation_valid'],physical_stopped=out['physical_stopped'],
                task_outcome=out['task_outcome'],task_time_s=raw['task_end_time_s'],guard=any(out['guard_violations'].values()),peaks=raw['peaks']))
        scores[stage]=dict(metric=metric(rows),rows=rows)
    f0=scores['zero']['metric'];f2=scores['final']['metric']
    improvement=1-f2['mean_penalized_time_s']/f0['mean_penalized_time_s'] if f0['comparable'] and f2['comparable'] and f0['mean_penalized_time_s']>0 else None
    passed=improvement is not None and improvement>=.10 and f2['success_count']==4 and not f2['guards']
    write(folder/'assessment.json',dict(scores=scores,relative_improvement=improvement,development_continue=passed,
        independent_tests=0,full_B2_accepted=False,C_accepted=False,restore_exact=True))
    ledger.update(status='CLOSED_COMPLETE',training_admitted=False,formal_updates=chain.updater.counts,restore_exact=True)
    write(folder/'run/ledger.json',ledger)


def reader(folder,label,admission):
    from joint_checkpoint import load_checkpoint,capture
    r=read(folder/'run'/(label+'.request.json'))
    chain=load_checkpoint(folder/'run/checkpoints'/label,expected_digest=r['checkpoint_pin'],expected_binding=admission.verify('F50'),
        output=folder/'run/readers'/label,admission=admission)
    actual=state_digest(capture(chain))
    if actual!=r['state_digest']:raise ValueError('Independent full state mismatch')
    result=dict(state_digest=actual)
    if label=='final':
        # Parent is blocked: retain full history, including an interrupted reader attempt.
        ledger=read(folder/'run/ledger.json')
        physical(folder,chain,schedule()[-1],ledger);result['entry']=ledger['episodes'][-1]
    write(folder/'run'/(label+'.reply.json'),result)


def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=['parent','reader']);p.add_argument('folder');p.add_argument('label');
    p.add_argument('gate');p.add_argument('parent_pid',type=int);p.add_argument('registered',type=float);args=p.parse_args()
    from supervised import enter_gate
    enter_gate(args.gate,args.parent_pid,args.registered)
    folder=Path(args.folder).resolve();admission=Admission(folder);admission.verify('F50')
    binding=read(OUT/'source_binding.json');verify_sources(binding);verify_execution_copies(folder);prepare_runtime(binding)
    import joint_runtime
    counter=Counter(folder/'counter.json');joint_runtime.configure(counter)
    if args.role=='reader':reader(folder,args.label,admission)
    else:execute(folder,admission,counter)


import json
if __name__=='__main__':main()
