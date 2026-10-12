"""Future 4/32 synthetic gate. Unapproved CLI fails before runtime import."""
from copy import deepcopy
from contextlib import contextmanager
from pathlib import Path
import argparse,importlib.metadata,importlib.util,json,os,platform,subprocess,sys,time
DIR=Path(__file__).resolve().parent;sys.path.insert(0,str(DIR))
from numeric_contract import (OUT,ROOT,PC12,LIMITS,NumericLedger,canonical,digest,read,write,sha,
    profile_contract,profile_pin,verify_numeric_authorization,verify_runtime_files)


def verify_sources(candidate):
    from prepare_candidate import source_proof
    proof=source_proof()
    if digest(proof)!=candidate['source_proof_sha256']:raise ValueError('Frozen source/runtime metadata differs')
    for rel,pin in candidate['execution_source_sha256'].items():
        if sha(ROOT/rel)!=pin:raise ValueError('Numeric integration code changed')
    verify_runtime_files(candidate['runtime_file_sha256'])


def prepare_runtime(candidate):
    expected=candidate['runtime']
    if not sys.flags.isolated:raise PermissionError('Isolated -I CPU process required')
    if Path(sys.executable).resolve()!=Path(expected['executable']).resolve():raise PermissionError('Frozen CPU interpreter required')
    verify_runtime_files(candidate['runtime_file_sha256'])
    check_module_origins(candidate['runtime_package_paths'])
    if platform.python_version()!=expected['python']:raise ValueError('Python version changed')
    for name,version in expected['versions'].items():
        if importlib.metadata.version(name)!=version:raise ValueError('Learning dependency version changed')
    # Called only after new authorization, source binding and exclusive claim.
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    from tools.validation.run_v4_learning_pilot import verify_learning_runtime
    select_qualified_runtime();verify_learning_runtime(expected)
    for name,path in candidate['runtime_package_paths'].items():
        module=__import__(name)
        if Path(module.__file__).resolve()!=Path(path).resolve():raise ValueError('Imported package origin differs: '+name)


def check_module_origins(paths,finder=None):
    finder=finder or importlib.util.find_spec
    for name,path in paths.items():
        spec=finder(name)
        if spec is None or spec.origin is None or Path(spec.origin).resolve()!=Path(path).resolve():
            raise ValueError('CPU package origin differs: '+name)


@contextmanager
def capture_costs(torch_module,updater_class,on_change=None):
    """Transparent counters; all original constructors/load calls remain intact."""
    metrics=dict(model_constructions_attempted=0,model_constructions_completed=0,model_construction_wall_s=0.,
        tensor_reads_attempted=0,tensor_reads_completed=0,tensor_read_wall_s=0.)
    ctor=updater_class.__init__;load=torch_module.load
    def wrapper(fn,kind):
        def measured(*args,**kwargs):
            prefix='model_constructions' if kind=='model' else 'tensor_reads'
            duration='model_construction_wall_s' if kind=='model' else 'tensor_read_wall_s'
            metrics[prefix+'_attempted']+=1;start=time.perf_counter()
            if on_change:on_change(metrics)
            try:
                value=fn(*args,**kwargs);metrics[prefix+'_completed']+=1;return value
            finally:
                metrics[duration]+=time.perf_counter()-start
                if on_change:on_change(metrics)
        return measured
    updater_class.__init__=wrapper(ctor,'model');torch_module.load=wrapper(load,'tensor')
    try:yield metrics
    finally:updater_class.__init__=ctor;torch_module.load=load


class UnconfirmedStop(RuntimeError):pass


def stop_owned_tree(child):
    if child.poll() is not None:return True
    result=subprocess.run(['taskkill','/PID',str(child.pid),'/T','/F'],capture_output=True,timeout=15)
    child.wait(timeout=15)
    if result.returncode or child.poll() is None:raise UnconfirmedStop('Owned process tree stop not confirmed')
    return True


def managed_child(command,log,timeout,receipt):
    """Keep the venv launcher LIVE until the whole owned tree is stopped."""
    child=None
    try:
        child=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        code=child.wait(timeout=timeout)
        write(receipt,dict(returncode=code,worker_stopped=True,pid=child.pid));return code
    except BaseException as exc:
        stopped=child is None;cleanup_error=None
        try:stopped=child is None or stop_owned_tree(child)
        except BaseException as cleanup:cleanup_error=repr(cleanup)
        write(receipt,dict(error=repr(exc),cleanup_error=cleanup_error,worker_stopped=bool(stopped),pid=None if child is None else child.pid))
        if not stopped:raise UnconfirmedStop('Worker may still be running; grant stays consumed') from exc
        raise


def stop_registered_process(record):
    """Check creation time/image before stopping a recorded real Python PID."""
    proof=record.get('process_proof')
    if not proof:raise UnconfirmedStop('Missing real Python process identity')
    original=proof['child'];pid=original['pid']
    from tools.validation.process_parent import kernel_api
    import ctypes
    from ctypes import wintypes
    api=kernel_api();handle=api.OpenProcess(0x1000|0x100000,False,pid)
    if not handle:
        if ctypes.get_last_error()==87:return True # PID no longer exists
        raise UnconfirmedStop('Cannot inspect owned Python process')
    try:
        if api.WaitForSingleObject(handle,0)!=0x102:return True
        buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buffer))
        times=[wintypes.FILETIME() for _ in range(4)]
        if not api.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)) or not api.GetProcessTimes(handle,*(ctypes.byref(t) for t in times)):
            raise UnconfirmedStop('Cannot bind owned Python process')
        created=(((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)-116444736000000000)/10000000
        from tools.validation.process_parent import same_image
        if created!=original['created_at'] or not same_image(buffer.value,original['image']):return True # PID reused; leave it alone
        killed=subprocess.run(['taskkill','/PID',str(pid),'/T','/F'],capture_output=True,timeout=15)
        if api.WaitForSingleObject(handle,15000)!=0 or killed.returncode:
            raise UnconfirmedStop('Recorded Python process tree stop not confirmed')
        return True
    finally:api.CloseHandle(handle)


def close_failed(candidate,grant,pin,folder,error,include_worker=False):
    from numeric_contract import CLAIMS
    folder=Path(folder);cleanup=[]
    try:
        for name in (('reader_claim.json','worker_claim.json') if include_worker else ('reader_claim.json',)):
            record=CLAIMS/pin/name
            if record.exists():
                saved=read(record)
                if name=='reader_claim.json' and sha(folder/'reader_request.json')!=saved['request_pin']:
                    raise UnconfirmedStop('Reader registration changed')
                stop_registered_process(saved);cleanup.append(name)
        write(folder/'failure_supervision.json',dict(processes_stopped=True,records=cleanup,error=repr(error)))
    except BaseException as exc:
        write(folder/'STOP',dict(reason='supervision_uncertain'))
        write(folder/'failure_supervision.json',dict(processes_stopped=False,records=cleanup,error=repr(error),cleanup_error=repr(exc)))
        raise UnconfirmedStop('Quota cannot close while process stop is uncertain') from exc
    if (folder/'ledger.json').exists():NumericLedger.recover_failed(folder/'ledger.json',candidate,grant,pin,repr(error))


class NumericAdmission:
    def __init__(self,candidate,grant,pin,ledger,role):
        self.candidate=deepcopy(candidate);self.grant=deepcopy(grant);self.pin=pin;self.ledger=ledger;self.role=role
        self.binding=dict(mode='F50',purpose='synthetic_qualification',
            config_sha256=candidate['outer_contract']['engine_config_sha256'],
            qualification_sha256=digest(dict(scope='pc13_synthetic_only',candidate=digest(candidate),grant=pin)))
    def verify(self,operation,profile):
        verify_numeric_authorization(self.candidate,self.grant,self.pin)
        if profile!=self.candidate['profile_sha256']:raise ValueError('Profile differs')
        for rel,pin in self.candidate['hot_source_sha256'].items():
            if sha(ROOT/rel)!=pin:raise ValueError('Active numeric source changed')
        self.ledger._check()
        if (self.ledger.path.parent/'STOP').exists():raise RuntimeError('Numeric STOP requested')
        if operation not in ('construct','episode','warmup','publish','forward','update','checkpoint','engine'):
            raise PermissionError('No physical/formal training capability')
        if self.ledger.data['phase']!=self.role:raise PermissionError('Wrong numeric process phase')
        if self.role=='reader' and operation in ('construct','episode','warmup','publish'):
            raise PermissionError('Reader cannot construct a new learning branch or collect more data')
        if operation in ('forward','update'):
            active=self.ledger.data['active']
            if not active or active['role']!=self.role or active['kind']!=operation:raise PermissionError('Charge numeric attempt before core call')
        return deepcopy(self.binding)


def normalized_state(state):
    result=deepcopy(state)
    for row in result.get('history',[]):row.pop('wall_s',None)
    lines=[]
    for line in result.get('journal','').splitlines():
        event=json.loads(line)
        if 'stats' in event:event['stats'].pop('wall_s',None)
        lines.append(canonical(event))
    if 'journal' in result:result['journal']='\n'.join(lines)
    return result


def verify_zero_state(state,origin,expected_rng):
    if (state['origin']!=origin or any(state['updater']['counts'].values()) or
        any(state['updater'][k]['state'] for k in ('actor','critic','temperature')) or
        state['replay']['size'] or state['replay']['episodes'] or state['replay']['seen'] or
        any(state[k] for k in ('archives','attempts','history','journal','update_attempts','stop_reason')) or
        state['warm']!=dict(draws=0,held=[0.]*4) or canonical(state['rng'])!=canonical(expected_rng)):
        raise ValueError('Fresh empty optimizer/replay/boundary/three-RNG origin required')
    return dict(origin=origin,counts=state['updater']['counts'],optimizer_states_empty=True,replay_rows=0,
        attempts=0,history=0,warm_draws=0,rng=deepcopy(expected_rng))


def predict_states(chain,ledger,role):
    import numpy as np
    from synthetic_data import test_states
    from small_bound_profile import compose_small_bound_command
    values=[]
    for observation in test_states():
        token=ledger.reserve(role,'forward')
        value=chain.predict(np.asarray(observation,dtype=np.float32),deterministic=True)
        ledger.complete(token) # actual return is recorded even when the following audit fails
        a=np.asarray(value[0])
        if a.shape!=(4,) or not np.isfinite(a).all() or np.max(np.abs(a))>1:raise ValueError('Invalid normalized actor action')
        context=dict(base=[0.]*6,phase='INSERT',enabled=True,previous_limited=[0.]*6,dt=.002,
                     reference_xy=None,radius=.00012,next_theta=None,search_config=None)
        _,log=compose_small_bound_command(a,context,chain.contract)
        if not np.array_equal(log['experience_action'],a) or not np.allclose(
            np.asarray(log['requested_residual'])[[0,1,3,4]],a*np.asarray(chain.contract['physical_scale_SI']),rtol=0,atol=1e-15):
            raise ValueError('Actor normalized replay/physical scale differs')
        values.append(a.tolist())
    return values


def one_update(chain,ledger,role):
    """Inspect actual critic input inside the charged transaction; no extra Q call."""
    import numpy as np
    token=ledger.reserve(role,'update');seen=[];target_seen=[]
    hook=chain.inner.updater.policy.critic.register_forward_pre_hook(lambda module,args:seen.append(args[1].detach().cpu().numpy().copy()))
    target_hook=chain.inner.updater.policy.critic_target.register_forward_pre_hook(lambda module,args:target_seen.append(args[1].detach().cpu().numpy().copy()))
    before=chain.inner.updater.counts['critic']
    try:
        stats=chain.update(1)[0]
        if chain.inner.updater.counts['critic']!=before+1:raise ValueError('Actual numeric batch count differs')
        ledger.complete(token) # committed critic batch precedes output/hook auditing
        episodes=dict(chain.inner.replay._state.episodes);pairs=stats['indices']
        expected=np.asarray([episodes[key]['actions'][index] for key,index in pairs])
        inactive=np.asarray([not episodes[key]['next_action_active'][index,0] for key,index in pairs])
        if not seen or not np.array_equal(seen[0],expected) or not target_seen or np.any(target_seen[0][inactive]):
            raise ValueError('Actual critic input is scaled, mismatched or inactive target nonzero')
        return stats
    finally:
        hook.remove();target_hook.remove()
        if chain.inner.updater.counts['critic']==before+1 and ledger.data['active'] and ledger.data['active']['token']==token:
            ledger.complete(token) # core may raise after advancing the critic counter


def execute_numeric(candidate,grant,grant_pin,folder,process_proof=None):
    verify_numeric_authorization(candidate,grant,grant_pin)
    verify_sources(candidate)
    if Path(sys.executable).resolve()!=Path(candidate['runtime']['executable']).resolve():raise PermissionError('Use the qualified CPU worker')
    ledger=NumericLedger.create(folder,candidate,grant,grant_pin)
    try:
        from numeric_contract import exclusive
        exclusive(ledger.claim/'worker_claim.json',dict(process_proof=process_proof,pid=os.getpid()))
        os.environ['MPLCONFIGDIR']=str(Path(folder)/'matplotlib_parent')
        prepare_runtime(candidate)
        from tools.learning.v4_sac import V4Updater
        import torch
        with capture_costs(torch,V4Updater,lambda costs:write(Path(folder)/'parent_costs.json',costs)) as costs:
            return parent_work(candidate,grant,grant_pin,folder,ledger,costs)
    except BaseException as exc:
        if isinstance(exc,UnconfirmedStop):
            write(Path(folder)/'STOP',dict(reason='supervision_uncertain'))
            write(Path(folder)/'failure_supervision.json',dict(processes_stopped=False,error=repr(exc)))
        else:close_failed(candidate,grant,grant_pin,folder,exc)
        raise


def parent_work(candidate,grant,grant_pin,folder,ledger,costs):
    from small_bound_learning import SmallBoundChain,save_small_bound_checkpoint
    from synthetic_data import synthetic_episode
    from tools.learning.v4_checkpoint import capture
    import torch
    permit=NumericAdmission(candidate,grant,grant_pin,ledger,'parent')
    chain=SmallBoundChain(candidate['outer_contract'],output=Path(folder)/'parent_chain',admission=permit)
    origin=deepcopy(chain.inner.origin)
    from tools.learning.v4_pilot_chain import streams
    expected_rng={k:v.bit_generator.state for k,v in zip(('warm','replay','boundary'),streams())}
    write(Path(folder)/'zero_origin.json',verify_zero_state(capture(chain.inner),candidate['outer_contract']['zero_origin'],expected_rng))
    for i in range(4):chain.begin('warmup',i);chain.publish(synthetic_episode(chain,'warmup',i))
    chain.begin('online',0);chain.publish(synthetic_episode(chain,'online',0))
    one_update(chain,ledger,'parent');one_update(chain,ledger,'parent')
    checkpoint=Path(folder)/'checkpoint';pin=save_small_bound_checkpoint(chain,checkpoint)
    actions=predict_states(chain,ledger,'parent');one_update(chain,ledger,'parent')
    expected=normalized_state(capture(chain.inner))
    request=dict(candidate_sha256=digest(candidate),grant_pin=grant_pin,checkpoint_pin=pin,
        profile_sha256=candidate['profile_sha256'],parent_pid=os.getpid(),wall_timestamp=time.time(),
        ledger_path=str(ledger.path),expected_parent_completed=dict(update=3,forward=16))
    write(Path(folder)/'reader_request.json',request);request_pin=sha(Path(folder)/'reader_request.json')
    ledger.ready_reader(request_pin)
    remaining=LIMITS['whole_wall_s']-(time.time()-ledger.data['started_wall'])
    if remaining<LIMITS['reader_wall_s']:raise RuntimeError('Insufficient worst-case reader time; do not start')
    command=[sys.executable,'-I','-X','utf8','-B',str(Path(__file__).resolve()),'--reader','--folder',str(folder),
             '--grant',str(Path(folder)/'grant.json'),'--authorization-pin',grant_pin,'--request-pin',request_pin]
    write(Path(folder)/'grant.json',grant)
    with (Path(folder)/'reader.log').open('x',encoding='utf8') as log:
        code=managed_child(command,log,LIMITS['reader_wall_s'],Path(folder)/'reader_exit.json')
    if code:raise RuntimeError('Independent numeric reader failed; no restart')
    child_state=torch.load(Path(folder)/'reader_state.pt',map_location='cpu',weights_only=True)
    from tools.learning.sac_checkpoint import _same
    if not _same(expected,child_state) or read(Path(folder)/'reader_actions.json')!=actions:
        raise ValueError('Full next-step model/Adam/replay/boundary/RNG/indices differ')
    ledger=NumericLedger.load(ledger.path,candidate,grant,grant_pin);ledger.finish();verify_sources(candidate)
    result=dict(status='PASSED_NUMERIC_ONLY',training_admitted=False,dynamic_episodes=0,formal_update_batches=0,
        synthetic_update_attempts=4,synthetic_update_completed=4,test_state_forward_attempts=32,
        new_synthetic_replay_rows=400,origin=origin,checkpoint_pin=pin,complete_independent_restore=True,
        comparison='full state after equivalent next update; only measured wall_s excluded',cumulative_dynamic=208)
    result['parent_costs']=deepcopy(costs);result['reader_costs']=read(Path(folder)/'reader_costs.json')
    write(Path(folder)/'numeric_result.json',result);return result


def reader(candidate,grant,pin,folder,request_pin):
    verify_numeric_authorization(candidate,grant,pin);verify_sources(candidate)
    folder=Path(folder)
    if sha(folder/'reader_request.json')!=request_pin:raise ValueError('Reader request changed')
    request=read(folder/'reader_request.json')
    if request['candidate_sha256']!=digest(candidate) or request['grant_pin']!=pin:raise ValueError('Reader request binding differs')
    from tools.validation.process_parent import require_registered_parent
    process_proof=require_registered_parent(request['parent_pid'],request['wall_timestamp'])
    ledger=NumericLedger.load(request['ledger_path'],candidate,grant,pin)
    if ledger.data['role_completed']['parent']!=request['expected_parent_completed']:raise ValueError('Parent work changed')
    ledger.claim_reader(request_pin,process_proof)
    try:
        os.environ['MPLCONFIGDIR']=str(folder/'matplotlib_reader')
        prepare_runtime(candidate)
        from tools.learning.v4_sac import V4Updater
        import torch
        with capture_costs(torch,V4Updater,lambda costs:write(folder/'reader_costs.json',costs)):
            reader_work(candidate,grant,pin,folder,request,ledger)
    except BaseException as exc:
        NumericLedger.recover_failed(ledger.path,candidate,grant,pin,repr(exc));raise


def reader_work(candidate,grant,pin,folder,request,ledger):
    from small_bound_learning import load_small_bound_checkpoint
    from tools.learning.v4_checkpoint import capture
    import torch
    permit=NumericAdmission(candidate,grant,pin,ledger,'reader')
    c=load_small_bound_checkpoint(folder/'checkpoint',expected_profile_digest=request['profile_sha256'],
        expected_digest=request['checkpoint_pin'],admission=permit,output=folder/'reader_chain')
    actions=predict_states(c,ledger,'reader');one_update(c,ledger,'reader')
    torch.save(normalized_state(capture(c.inner)),folder/'reader_state.pt')
    write(folder/'reader_actions.json',actions)


def supervise(candidate,grant_path,pin,folder):
    grant=read(grant_path);verify_numeric_authorization(candidate,grant,pin);verify_sources(candidate)
    folder=Path(folder)
    if folder.exists():raise FileExistsError('No execution retry')
    supervision=folder.with_name(folder.name+'.supervision');supervision.mkdir()
    write(supervision/'started.json',dict(supervisor_pid=os.getpid(),wall_timestamp=time.time()))
    command=[candidate['runtime']['executable'],'-I','-X','utf8','-B',str(Path(__file__).resolve()),'--worker',
        '--folder',str(folder),'--grant',str(Path(grant_path).resolve()),'--authorization-pin',pin,
        '--supervisor',str(supervision/'started.json')]
    try:
        with (supervision/'execution.log').open('x',encoding='utf8') as log:
            code=managed_child(command,log,LIMITS['whole_wall_s'],supervision/'exit.json')
        if code:raise RuntimeError('Numeric worker failed; preserve journal, no retry')
    except BaseException as exc:
        if isinstance(exc,UnconfirmedStop):
            write(supervision/'uncertain.json',dict(error=repr(exc),quota_closed=False))
            if folder.exists():write(folder/'STOP',dict(reason='supervision_uncertain'))
        elif folder.exists():close_failed(candidate,grant,pin,folder,exc,include_worker=True)
        raise


def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group()
    g.add_argument('--inspect',action='store_true');g.add_argument('--execute',action='store_true')
    g.add_argument('--worker',action='store_true');g.add_argument('--reader',action='store_true')
    p.add_argument('--grant',type=Path);p.add_argument('--authorization-pin');p.add_argument('--request-pin')
    p.add_argument('--supervisor',type=Path);p.add_argument('--folder',type=Path,default=OUT/'numeric_run')
    args=p.parse_args();candidate=read(OUT/'numeric_candidate.json')
    if args.inspect or not any((args.execute,args.worker,args.reader)):
        print(canonical(dict(status=candidate['status'],limits=LIMITS,actual_new_compute=0,training_admitted=False)));return
    grant=read(args.grant) if args.grant else None
    verify_numeric_authorization(candidate,grant,args.authorization_pin)
    if args.execute:supervise(candidate,args.grant,args.authorization_pin,args.folder)
    elif args.reader:reader(candidate,grant,args.authorization_pin,args.folder,args.request_pin)
    else:
        from tools.validation.process_parent import require_registered_parent
        record=read(args.supervisor);proof=require_registered_parent(record['supervisor_pid'],record['wall_timestamp'])
        execute_numeric(candidate,grant,args.authorization_pin,args.folder,process_proof=proof)


if __name__=='__main__':main()
