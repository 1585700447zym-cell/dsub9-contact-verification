"""Bounded current-authority experiment with supervised independent restore."""
import argparse,gzip,importlib.util,json,os,sys,time,subprocess
from copy import deepcopy
from pathlib import Path
from validation_contract import (HERE,ROOT,PREFLIGHT,Ledger,attempts,scope,config,read,digest,write,canonical,
    require_authorization,verify_binding)
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')

def select_runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()

def entry_checks(binding_pin,auth_pin):
    require_authorization(binding_pin,auth_pin);verify_binding(binding_pin);select_runtime();verify_binding(binding_pin,with_runtime=True)

def live_guard(restore=False):
    from tools.validation.process_parent import require_registered_parent,windows_process,same_image
    record=read(HERE/('run/restore_process/started.json' if restore else 'started.json'))
    root=read(HERE/'started.json')
    def check():
        if (HERE/'stop_requested.json').exists() or (restore and (HERE/'run/restore_process/stop_requested.json').exists()):raise RuntimeError('Supervisor requested stop')
        require_registered_parent(record['supervisor_pid'],record['wall_timestamp'])
        if restore:
            with windows_process(root['supervisor_pid']) as ancestor:
                if not ancestor['alive'] or ancestor['created_at']>root['wall_timestamp'] or not same_image(ancestor['image'],sys._base_executable):raise RuntimeError('Root supervisor identity changed')
    return check

def reader_guard(worker_pid):
    from contextlib import ExitStack
    from tools.validation.process_parent import require_registered_parent,windows_process,validate_chain
    if (HERE/'stop_requested.json').exists():raise RuntimeError('Supervisor requested stop')
    claim=read(HERE/'claim.json')
    if type(worker_pid) is not int or claim['pid']!=worker_pid:raise ValueError('Registered zero-reader worker changed')
    route=require_registered_parent(worker_pid,claim['wall_timestamp'])
    root=read(HERE/'started.json')
    with ExitStack() as stack:
        worker=stack.enter_context(windows_process(worker_pid))
        parent=stack.enter_context(windows_process(worker['parent_pid']))
        registered=parent if parent['pid']==root['supervisor_pid'] else stack.enter_context(windows_process(root['supervisor_pid']))
        ancestry=validate_chain(expected_pid=root['supervisor_pid'],registered_at=root['wall_timestamp'],now=time.time(),
            child=worker,parent=parent,registered=registered,python_image=sys._base_executable,launcher_image=sys.executable)
    return dict(reader_route=route['route'],worker_route=ancestry['route'],registered_worker_id=worker_pid,registered_supervisor_id=root['supervisor_pid'])

sys.path.insert(0,str(PREFLIGHT))
from run_preflight import PhysicsBudget as PreviousPhysicsBudget

class PhysicsBudget(PreviousPhysicsBudget):
    def step(self,original,*args,**kwargs):
        self.active()
        if len(args)!=2 or set(kwargs)-{'nstep'} or type(kwargs.get('nstep',1)) is not int or kwargs.get('nstep',1)!=1:raise ValueError('One physical substep required')
        if self.episode_substeps>=130000 or self.total_substeps>=scope()['physical_substeps_cap']:raise RuntimeError('Physical substep cap exceeded')
        self.episode_substeps+=1;self.total_substeps+=1;return original(*args,**kwargs)

class LearningMeter:
    def __init__(self,ledger):
        self.ledger=ledger;self.module_calls=0;self.optimizer_calls=0;self.policy_states=0;self.mode=None;self.token=None;self.local_modules=0;self.local_optimizers=0
    def healthy(self):
        if self.ledger.write_failed or self.ledger.state['status']!='healthy':raise RuntimeError('Healthy durable learning reservation required')
    def begin_control(self):
        self.healthy()
        if self.mode is not None or self.ledger.state['active'] is None or self.ledger.state['update_lease'] is not None:raise RuntimeError('Physical control lease required')
        if self.policy_states>=scope()['total_control_cycles_cap']:raise RuntimeError('Policy state cap exceeded')
        self.mode='control';self.token=self.ledger.state['active'];self.local_modules=0;self.local_optimizers=0;self.policy_states+=1
    def begin_update(self,token):
        self.healthy()
        if self.mode is not None or self.ledger.state['update_lease']!=token or self.ledger.state['active'] is not None:raise RuntimeError('Exact update lease required')
        self.mode='update';self.token=deepcopy(token);self.local_modules=0;self.local_optimizers=0
    def current(self):
        self.healthy();s=self.ledger.state
        if self.mode=='control' and s['active']==self.token and s['update_lease'] is None:return
        if self.mode=='update' and s['active'] is None and s['update_lease']==self.token:return
        raise RuntimeError('No current inference/update permit')
    def module(self,original,*a,**kw):
        self.current();cap=scope()['module_calls_per_control_cap' if self.mode=='control' else 'module_calls_per_batch_cap']
        if self.local_modules>=cap or self.module_calls>=scope()['model_module_calls_cap']:raise RuntimeError('Model call cap exceeded')
        self.local_modules+=1;self.module_calls+=1;return original(*a,**kw)
    def optimizer(self,original,*a,**kw):
        self.current()
        if self.mode!='update' or self.local_optimizers>=3 or self.optimizer_calls>=scope()['optimizer_steps_cap']:raise RuntimeError('Optimizer cap exceeded')
        self.local_optimizers+=1;self.optimizer_calls+=1;return original(*a,**kw)
    def end_context(self):self.mode=None;self.token=None
    def capture(self):return dict(model_module_calls_attempted=self.module_calls,optimizer_steps_attempted=self.optimizer_calls,policy_states_attempted=self.policy_states)

def install_meters(ledger):
    import torch,mujoco
    physics=PhysicsBudget(ledger);learning=LearningMeter(ledger)
    call=torch.nn.Module._call_impl;torch.nn.Module._call_impl=lambda *a,**k:learning.module(call,*a,**k)
    step=torch.optim.Adam.step;torch.optim.Adam.step=lambda *a,**k:learning.optimizer(step,*a,**k)
    original=mujoco.mj_step;mujoco.mj_step=lambda *a,**k:physics.step(original,*a,**k)
    forward=mujoco.mj_forward;mujoco.mj_forward=lambda *a,**k:physics.forward(forward,*a,**k)
    for name in ('mj_resetData','mj_resetDataKeyframe'):
        fn=getattr(mujoco,name)
        def init(*a,_name=name,_fn=fn,**k):return physics.initialize(_name,_fn,*a,**k)
        setattr(mujoco,name,init)
    for name in ('mj_step1','mj_step2'):
        def refuse(*a,**k):raise RuntimeError('Unregistered split physics call')
        setattr(mujoco,name,refuse)
    return physics,learning

class Permit:
    def __init__(self,ledger,arm):
        self.ledger=ledger;self.arm=arm;self.expected_digest=ledger.state['binding_sha256'];self.auth_pin=ledger.state['authorization_sha256'];self.config=config(arm)
    def verify(self,case=None):
        self.ledger.check_live()
        if self.ledger.state['status']!='healthy':raise RuntimeError('Validation ledger closed')
        require_authorization(self.expected_digest,self.auth_pin);verify_binding(self.expected_digest,with_runtime=True)
        if canonical(self.config)!=canonical(config(self.arm)):raise ValueError('Configuration changed')
        if case is not None:
            i=self.ledger.state['active']
            if i is None or canonical(case)!=canonical(attempts()[i]['case']) or attempts()[i]['arm'] not in (self.arm,'shared'):raise ValueError('Reserved branch/case required')
        return dict(collection_admitted=True,update_admitted=True,current_training_authorization=True)

class ContextPolicy:
    def __init__(self,collector,meter,deterministic):self.collector=collector;self.meter=meter;self.deterministic=deterministic
    def predict(self,observation,deterministic=False):
        import numpy as np
        c=self.collector;c.admission.ledger.check_live()
        if deterministic is not self.deterministic or c.session.cycle_id>=13000:raise ValueError('Registered policy mode/cycle required')
        snap=c.session.prepare_cycle()
        if not np.array_equal(np.asarray(snap.policy_observation,dtype=np.float32),observation):raise ValueError('Policy snapshot differs from upcoming physical cycle')
        facts=c.session.env.guard_facts
        if facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons']:
            return np.zeros(4,dtype=np.float32),None
        self.meter.begin_control()
        try:return c.updater.predict(observation,deterministic=deterministic)
        finally:self.meter.end_context()

def collector_type():
    from run_preflight import collector_type as previous_type
    from tools.learning.admitted_collection import AdmittedCollector,_write_archive
    from tools.learning.sac_checkpoint import _audit_physics,_same
    from tools.learning.contact_contract import guard_clear
    from tools.learning.episode_rules import FORCE_ONLY
    class Collector(previous_type()):
        admission_type=Permit
        def __init__(self,*,admission,replay,output,updater,online):
            AdmittedCollector.__init__(self,admission=admission,replay=replay,output=output);self.updater=updater;self.online=online
        def start(self,*a,**k):
            self.before=self.updater._snapshot();self.policy_sha=self.updater.fingerprints()['actor'];return super().start(*a,**k)
        def collect(self,policy,steps,*,cut_at_end=False,deterministic=False):
            if cut_at_end or deterministic is self.online or type(policy) is not ContextPolicy or policy.collector is not self:raise ValueError('Complete current-policy episode required')
            return AdmittedCollector.collect(self,policy,steps,deterministic=deterministic)
        def retry_publication(self):
            if self._status_pending:
                write(self._folder/'status.json',self._record);self._status_pending=False
                self._blocked=not self._record['simulation_valid'] or not self._record['physical_stopped'];return
            if self._pending is None:raise RuntimeError('No pending archive')
            raw=self._pending;raw.update(training_admitted=self.online,evaluation_method='sac',sampling_mode='sac_policy' if self.online else 'frozen_sac',
                policy_sha256=self.policy_sha,optimizer_steps_start=self.before['counts']['critic'],optimizer_steps=self.updater.counts['critic'],
                current_identity=deepcopy(attempts()[self.admission.ledger.state['active']]),fault_tail_transitions=deepcopy(getattr(self,'fault_tail_transitions',[])))
            raw['guard_clear']=guard_clear(raw);sha=_write_archive(self._folder/'episode.json.gz',raw)
            self.admission.verify(raw['case']);_audit_physics(raw)
            if raw['fault'] is not None:raise ValueError('Faulted attempt retained, not admitted')
            facts=raw['guard_facts'];stamp=None
            if not facts['motion_reasons'] and not facts['invalid_reasons'] and all(x=='FORCE_LIMIT' for x in facts['contact_reasons']):stamp=FORCE_ONLY.classify(raw)
            self.replay._prepare(raw['transitions'])
            if self.updater.counts!=self.before['counts'] or self.updater.fingerprints()['actor']!=self.policy_sha or (not self.online and not _same(self.before,self.updater._snapshot())):raise ValueError('Frozen evaluation or in-episode learning state changed')
            self._record.update(committed=0,discarded=len(raw['transitions']),training_admitted=self.online,
                learning_eligibility=stamp,archive_sha256=sha,physical_stopped=raw['outcome']['physical_stopped'],
                simulation_valid=raw['outcome']['simulation_valid'],valid_for_learning=raw['outcome']['valid_for_learning'],
                task_outcome=raw['outcome']['task_outcome'],policy_sha256=self.policy_sha,optimizer_steps=self.updater.counts['critic'],status='audited_archived')
            self._pending=None;self._status_pending=True;self.session=None;self.buffer=None;self.retry_publication()
    return Collector

def episode(identity,ledger,physics,learning,updater,branch=None):
    from tools.learning.audited_replay import AuditedReplay
    from tools.learning.engineering_evaluation import episode_metrics
    online=identity['stage'].endswith('_online');ledger.start(identity['id']);physics.begin()
    c=collector_type()(admission=Permit(ledger,identity['arm'] if identity['arm']!='shared' else 'C'),replay=AuditedReplay(capacity=13000),
        output=HERE/'run/collections'/identity['id'],updater=updater,online=online)
    try:
        c.start(identity['id'],case=identity['case'],seed=scope()['seed']);policy=ContextPolicy(c,learning,not online)
        while c.active:
            ledger.check_live();c.collect(policy,500,deterministic=not online)
            write(HERE/'run/progress.json',dict(id=identity['id'],cycles=c._record['steps'],updates=ledger.state['updates'],wall_timestamp=time.time()))
        p=c.output/identity['id']/'episode.json.gz';raw=json.loads(gzip.decompress(p.read_bytes()));facts=raw['guard_facts']
        if digest(p)!=c.attempts[-1]['archive_sha256'] or physics.episode_substeps!=10*len(raw['transitions']) or len(c.replay):raise ValueError('Durable archive/physical cost/evaluation isolation differs')
        guard=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons'])
        if online and not guard:
            branch.append_archive(dict(id=identity['id'],path=p.relative_to(ROOT).as_posix(),sha256=digest(p),role='online'),p.read_bytes(),updater.counts['critic'])
            c._record.update(committed=len(raw['transitions']),discarded=0,current_replay_published=True);write(p.parent/'status.json',c._record)
        row=dict(**identity,completed=True,**episode_metrics(raw),guard_hit=guard,archive_path=p.relative_to(ROOT).as_posix(),archive_sha256=digest(p),training_batches=updater.counts['critic'])
        ledger.finish(row);write(HERE/'run/results.json',[x['result'] for x in ledger.state['attempts'] if x['status']=='finished']);write(HERE/'run/accounting.json',ledger.accounting())
        return ledger.state['status']=='healthy'
    except BaseException as exc:
        if c.active:c._abort(exc)
        write(c.output/'failure.json',dict(error=repr(exc),attempts=c.attempts,raw_retained=(c._folder/'episode.json.gz').exists() if hasattr(c,'_folder') else False));raise

def supervise(command,output):
    source=ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/driver.py'
    spec=importlib.util.spec_from_file_location('temporal_learning_supervisor',source);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);helper.write=write
    return helper.supervise(command,output,ROOT)

def command(binding_pin,auth_pin,restore=False):
    return [sys.executable,'-X','utf8','-X','faulthandler','-B',str(Path(__file__).resolve()),'--binding-sha256',binding_pin,'--authorization-sha256',auth_pin,'--restore-worker' if restore else '--worker']

def costs(physics,learning):return dict(**learning.capture(),physical_substeps_attempted=physics.total_substeps,substep_forwards_attempted=physics.substep_forwards,initializations=physics.initializations)

def save_boundary(branch,run):
    n=len(branch.history)
    if n not in (500,1000,1500,2000,2500):raise ValueError('Registered 500-batch boundary required')
    name='checkpoint_'+branch.arm+(f'_{n:04d}' if n<2500 else '')
    pin=branch.save(Path(run)/name);record=dict(path=name,sha256=pin,batches=n,arm=branch.arm)
    write(Path(run)/('latest_checkpoint_'+branch.arm+'.json'),record);return record

def zero_checkpoint_gate(branch,run,binding_pin,auth_pin):
    import torch
    from tools.learning.sac_checkpoint import _same
    if branch.history or any(branch.updater.counts.values()):raise ValueError('Pristine complete zero branch required')
    before=branch.capture();path=Path(run)/'origin_checkpoint_C';pin=branch.save(path)
    manifest=read(path/'manifest.json')
    if digest(path/'manifest.json')!=pin or digest(path/'state.pt')!=manifest['state_sha256']:raise ValueError('Zero disk payload pin changed')
    saved=torch.load(path/'state.pt',map_location='cpu',weights_only=True)
    if not _same(saved,before) or not _same(branch.capture(),before):raise ValueError('Zero full state file or live branch differs')
    child=subprocess.run([sys.executable,'-X','utf8','-B',str(HERE/'verify_zero_checkpoint.py'),
        '--path',str(path),'--sha256',pin,'--binding-sha256',binding_pin,'--authorization-sha256',auth_pin,'--parent-pid',str(os.getpid())],
        cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=60)
    write(Path(run)/'origin_reader_exit.json',dict(returncode=child.returncode,stdout=child.stdout,stderr=child.stderr))
    if child.returncode:raise RuntimeError('Independent zero-state reader failed')
    proof=json.loads(child.stdout)
    if (proof.get('complete_state_equal') is not True or proof.get('checkpoint_sha256')!=pin or proof.get('process_id')==os.getpid() or
        proof.get('registered_worker_id')!=os.getpid() or proof.get('batches')!=0 or set(proof.get('actual_calls',{}))!={'model_forward','optimizer','physics'} or
        any(proof['actual_calls'].values())):raise ValueError('Independent zero-state proof malformed')
    write(Path(run)/'origin_checkpoint_verified.json',proof);return proof

def worker(binding_pin,auth_pin,restored=False):
    import learning_runtime as R
    from tools.learning.sac_checkpoint import _same
    run=HERE/'run'
    if restored:ledger=Ledger.load(run/'ledger.json',binding_pin,auth_pin)
    else:run.mkdir(exist_ok=False);ledger=Ledger.create(run/'ledger.json',binding_pin,auth_pin)
    ledger.live_guard=live_guard(restored);physics,learning=install_meters(ledger);name='restore' if restored else 'main'
    try:
        if restored:
            checkpoint_pin=ledger.state['frozen']['C'];b=R.restore(run/'checkpoint_C',checkpoint_pin,'C',ledger);before=b.capture()
            for identity in attempts()[12:16]:
                if not episode(identity,ledger,physics,learning,b.updater):return 20
                prior=next(x['result'] for x in ledger.state['attempts'] if x['identity']['id']==identity['id'].replace('C_restored_','C_final_'))
                original=json.loads(gzip.decompress((ROOT/prior['archive_path']).read_bytes()));current=json.loads(gzip.decompress((ROOT/ledger.rows('C_restored')[-1]['archive_path']).read_bytes()))
                for key in ('case','seed','outcome','transitions','guard_facts','events','stop_samples','stop_time','audit_end_time_s','final_session'):
                    if not _same(original[key],current[key]):
                        ledger.method_failed('Independent restored trajectory differs: '+key);return 20
            if not _same(before,b.capture()):raise RuntimeError('Restored evaluation changed complete learning state')
            proof=run/'restoration.json';write(proof,dict(exact_full_learning_state=True,exact_physical_replay=True,checkpoint_sha256=checkpoint_pin,
                process_id=os.getpid(),parent_id=os.getppid(),restored_success=4,independent_performance_samples_added=0))
            ledger.restored(digest(proof));return 0
        manifests={a:R.qualify_dataset(a,ledger,run) for a in ('C','A')}
        u=R.zero_updater('C');zero=u._snapshot();write(run/'origin.json',dict(updater_zero=True,replay_imported_from_old_origin=False,fingerprints=u.fingerprints()))
        starting_C=R.Branch('C',ledger,*manifests['C'],updater=u)
        zero_checkpoint_gate(starting_C,run,binding_pin,auth_pin)
        for identity in attempts()[:4]:
            if not episode(identity,ledger,physics,learning,u):return 20
        if not _same(zero,u._snapshot()):raise RuntimeError('Initial evaluation changed zero learning state')
        for arm in ('C','A'):
            b=starting_C if arm=='C' else R.Branch(arm,ledger,*manifests[arm])
            if not _same(zero,b.updater._snapshot()):raise RuntimeError('Cross-arm common zero state differs')
            for chunk in range(5):
                for _ in range(500):
                    b.update_one(learning)
                    if len(b.history)%25==0:write(run/'progress.json',dict(stage=arm+'_updates',batch=len(b.history),updates=ledger.state['updates'],wall_timestamp=time.time()))
                write(run/('history_'+arm+'.json'),b.history)
                boundary=save_boundary(b,run)
                if chunk<4:
                    identity=next(a for a in attempts() if a['stage']==arm+'_online' and a['case_index']==chunk)
                    if not episode(identity,ledger,physics,learning,b.updater,b):return 20
            checkpoint_pin=boundary['sha256'];ledger.freeze(arm,checkpoint_pin)
            before=b.capture()
            for identity in [a for a in attempts() if a['stage']==arm+'_final']:
                if not episode(identity,ledger,physics,learning,b.updater):return 20
            if not _same(before,b.capture()):raise RuntimeError('Final evaluation changed complete learning state')
            if arm=='C':
                code=supervise(command(binding_pin,auth_pin,True),run/'restore_process')
                ledger=Ledger.load(run/'ledger.json',binding_pin,auth_pin);ledger.live_guard=live_guard();physics.ledger=ledger;learning.ledger=ledger
                if code==20 and ledger.state['status'] in ('stopped','method_failed'):return 20
                if code!=0 or ledger.state['restoration_pin']!=digest(run/'restoration.json'):raise RuntimeError('Independent restoration did not pass')
        ledger.complete();write(run/'completed.json',dict(status='complete',limited_candidate_target_passed=True,b2_complete=False,accounting=ledger.accounting()));return 0
    except BaseException as exc:
        if ledger.state['status']=='healthy':
            try:ledger.fail(repr(exc))
            except BaseException as cleanup:write(run/(name+'_ledger_cleanup_error.json'),dict(error=repr(cleanup)))
        write(run/(name+'_failure.json'),dict(error=repr(exc),retry_allowed=False));raise
    finally:
        write(run/(name+'_costs.json'),costs(physics,learning));write(run/'accounting.json',ledger.accounting())

def finalize_exception(binding_pin,auth_pin,exc):
    process=read(HERE/'process_exit.json') if (HERE/'process_exit.json').exists() else {}
    uncertain=(HERE/'stop_requested.json').exists() or not process or (process.get('status')=='supervisor_error' and
        (process.get('worker_stopped') is not True or process.get('cleanup_error') is not None))
    if uncertain:write(HERE/'stop_requested.json',dict(error=repr(exc),worker_stop_confirmed=False))
    elif (HERE/'run/ledger.json').exists():
        ledger=Ledger.load(HERE/'run/ledger.json',binding_pin,auth_pin)
        if ledger.state['status']=='healthy':ledger.fail(repr(exc))
        write(HERE/'run/accounting.json',ledger.accounting())
    write(HERE/'exit_classification.json',dict(status='failed',error=repr(exc),worker_stop_confirmed=not uncertain,ledger_preserved_pending_process_confirmation=uncertain,retry_allowed=False,b2_complete=False))

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--binding-sha256',required=True);p.add_argument('--authorization-sha256')
    mode=p.add_mutually_exclusive_group();mode.add_argument('--worker',action='store_true');mode.add_argument('--restore-worker',action='store_true');mode.add_argument('--verify-only',action='store_true');a=p.parse_args(argv)
    if a.verify_only:verify_binding(a.binding_sha256);print('Binding verified; no computation.');return 0
    entry_checks(a.binding_sha256,a.authorization_sha256)
    if a.worker or a.restore_worker:
        live_guard(a.restore_worker)()
        claim=HERE/('run/restore_claim.json' if a.restore_worker else 'claim.json')
        with claim.open('x',encoding='utf-8') as f:json.dump(dict(pid=os.getpid(),parent_pid=os.getppid(),wall_timestamp=time.time()),f);f.flush();os.fsync(f.fileno())
        if os.name=='nt':
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0002)
        return worker(a.binding_sha256,a.authorization_sha256,a.restore_worker)
    try:
        code=supervise(command(a.binding_sha256,a.authorization_sha256),HERE);ledger=Ledger.load(HERE/'run/ledger.json',a.binding_sha256,a.authorization_sha256)
        terminal=ledger.state['status'];complete=code==0 and terminal=='complete';controlled=code==20 and terminal in ('stopped','baseline_failed','method_failed')
        if not complete and not controlled:raise RuntimeError('Validation worker failed: '+str(code))
        write(HERE/'exit_classification.json',dict(execution_complete=complete,controlled_stop=controlled,status=terminal,returncode=code,accounting=ledger.accounting(),retry_allowed=False,b2_complete=False));return code
    except FileExistsError:raise
    except BaseException as exc:
        finalize_exception(a.binding_sha256,a.authorization_sha256,exc);raise

if __name__=='__main__':raise SystemExit(main())
