"""Single bounded paired run, followed by independent representative restores."""
import argparse,gzip,importlib.util,json,os,subprocess,sys,time
from copy import deepcopy
from pathlib import Path
import paired_contract as C
os.environ['MPLCONFIGDIR']=str(C.ROOT/'tmp/learning_mpl_cache')

def select_runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()

def live_guard(folder):
    from tools.validation.process_parent import require_registered_parent
    record=C.read(folder/'started.json')
    def check():
        if (C.HERE/'stop_requested.json').exists() or (folder/'stop_requested.json').exists():raise RuntimeError('Supervisor stop fence')
        require_registered_parent(record['supervisor_pid'],record['wall_timestamp'])
    return check

class Physics:
    def __init__(self,ledger):
        self.ledger=ledger;self.token=None;self.episode_substeps=0;self.total_substeps=0;self.substep_forwards=0;self.episode_forwards=0;self.initializations={}
    def active(self):
        s=self.ledger.state
        if self.ledger.write_failed or s['status']!='healthy' or self.token is None or s['active']!=self.token:raise RuntimeError('Current physics reservation required')
    def begin(self):
        self.ledger.check_live();s=self.ledger.state
        if s['status']!='healthy' or s['active'] is None or self.token==s['active']:raise RuntimeError('New physical reservation required')
        self.token=s['active'];self.episode_substeps=0;self.episode_forwards=0
    def step(self,original,*a,**kw):
        self.active()
        if len(a)!=2 or set(kw)-{'nstep'} or type(kw.get('nstep',1)) is not int or kw.get('nstep',1)!=1:raise ValueError('One substep required')
        if self.episode_substeps>=130000 or self.total_substeps>=C.scope()['physical_substeps_cap']:raise RuntimeError('Physical substep budget')
        self.episode_substeps+=1;self.total_substeps+=1;return original(*a,**kw)
    def initialize(self,kind,original,*a,**kw):
        self.ledger.check_live();self.active();self.initializations[kind]=self.initializations.get(kind,0)+1;return original(*a,**kw)
    def forward(self,original,*a,**kw):
        self.active()
        if self.episode_substeps==0:return self.initialize('initial_forward',original,*a,**kw)
        if self.episode_forwards>=self.episode_substeps:raise RuntimeError('One paired forward per substep')
        self.episode_forwards+=1;self.substep_forwards+=1;return original(*a,**kw)

class LearningMeter:
    def __init__(self,ledger):
        self.ledger=ledger;self.module_calls=0;self.optimizer_calls=0;self.policy_states=0;self.mode=None;self.token=None;self.local_modules=0;self.local_optimizers=0
    def healthy(self):
        if self.ledger.write_failed or self.ledger.state['status']!='healthy':raise RuntimeError('Healthy durable computation lease required')
    def begin_control(self):
        self.healthy();s=self.ledger.state
        if self.mode is not None or s['active'] is None or s['update_lease'] is not None or self.policy_states>=C.scope()['actor_state_cap']:raise RuntimeError('Control lease required')
        if C.attempts()[s['active']]['stage'] not in ('online','final','restore'):raise RuntimeError('Warmup/baseline cannot call model')
        self.mode='control';self.token=s['active'];self.local_modules=self.local_optimizers=0;self.policy_states+=1
    def begin_update(self,token):
        self.healthy();s=self.ledger.state
        if self.mode is not None or s['update_lease']!=token or s['active'] is not None:raise RuntimeError('Exact update lease required')
        self.mode='update';self.token=deepcopy(token);self.local_modules=self.local_optimizers=0
    def current(self):
        self.healthy();s=self.ledger.state
        if self.mode=='control' and s['active']==self.token and s['update_lease'] is None:return
        if self.mode=='update' and s['active'] is None and s['update_lease']==self.token:return
        raise RuntimeError('No inference/update context')
    def module(self,original,*a,**kw):
        self.current();cap=32 if self.mode=='control' else 128
        if self.local_modules>=cap or self.module_calls>=C.scope()['model_module_calls_cap']:raise RuntimeError('Model call budget')
        self.local_modules+=1;self.module_calls+=1;return original(*a,**kw)
    def optimizer(self,original,*a,**kw):
        self.current()
        if self.mode!='update' or self.local_optimizers>=3 or self.optimizer_calls>=15000:raise RuntimeError('Adam call budget')
        self.local_optimizers+=1;self.optimizer_calls+=1;return original(*a,**kw)
    def end_context(self):self.mode=None;self.token=None
    def capture(self):return dict(model_module_calls_attempted=self.module_calls,optimizer_steps_attempted=self.optimizer_calls,policy_states_attempted=self.policy_states)

def install(ledger):
    import torch,mujoco
    p=Physics(ledger);m=LearningMeter(ledger)
    call=torch.nn.Module._call_impl;torch.nn.Module._call_impl=lambda *a,**k:m.module(call,*a,**k)
    step=torch.optim.Adam.step;torch.optim.Adam.step=lambda *a,**k:m.optimizer(step,*a,**k)
    fn=mujoco.mj_step;mujoco.mj_step=lambda *a,**k:p.step(fn,*a,**k)
    forward=mujoco.mj_forward;mujoco.mj_forward=lambda *a,**k:p.forward(forward,*a,**k)
    for name in ('mj_resetData','mj_resetDataKeyframe'):
        original=getattr(mujoco,name)
        def reset(*a,_name=name,_fn=original,**k):return p.initialize(_name,_fn,*a,**k)
        setattr(mujoco,name,reset)
    def refuse(*a,**kw):raise RuntimeError('Split physical step forbidden')
    for name in ('mj_step1','mj_step2'):setattr(mujoco,name,refuse)
    return p,m

def costs(p,m):return dict(**m.capture(),physical_substeps_attempted=p.total_substeps,substep_forwards_attempted=p.substep_forwards,initializations=p.initializations)
def raw_at(row):return json.loads(gzip.decompress((C.ROOT/row['archive_path']).read_bytes()))
def equal_trace(a,b):
    from tools.learning.sac_checkpoint import _same
    return all(_same(a[k],b[k]) for k in ('case','seed','outcome','transitions','guard_facts','events','stop_samples','stop_time','audit_end_time_s','final_session'))

def finish_and_publish(ledger,row,branch,raw,path,receipt):
    ledger.finish(row)
    if branch is not None and row['stage']=='online' and not row['guard_hit']:
        branch.append_archive(dict(id=row['id'],path=path.relative_to(C.ROOT).as_posix(),sha256=C.digest(path),role='online'),path.read_bytes(),row['training_batches'])
        receipt.update(committed=len(raw['transitions']),discarded=0,current_replay_published=True)
        C.write(path.parent/'status.json',receipt)

def episode(identity,ledger,physics,meter,updater=None,branch=None,restore=False):
    from paired_collection import Permit,Collector,ContextPolicy
    from tools.learning.engineering_evaluation import episode_metrics
    ledger.start(identity['id']);physics.begin();mode=identity['arm'] if identity['arm']!='B2' else 'F'
    c=Collector(admission=Permit(ledger,mode),output=C.HERE/'run/collections'/identity['id'],identity=identity,updater=updater)
    try:
        c.start(identity['id'],case=identity['case'],seed=C.scope()['seed']);policy=ContextPolicy(c,meter)
        while c.active:
            c.collect(policy,500,deterministic=identity['stage']!='online')
            C.write(C.HERE/'run/progress.json',dict(id=identity['id'],stage=identity['stage'],arm=identity['arm'],cycles=c._record['steps'],updates=ledger.state['updates'],wall_timestamp=time.time()))
        p=c.output/identity['id']/'episode.json.gz';raw=json.loads(gzip.decompress(p.read_bytes()));facts=raw['guard_facts']
        if C.digest(p)!=c.attempts[-1]['archive_sha256'] or physics.episode_substeps!=10*len(raw['transitions']) or len(c.replay):raise ValueError('Archive/cost/isolation differs')
        guard=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons'])
        row=dict(**identity,completed=True,**episode_metrics(raw),guard_hit=guard,archive_path=p.relative_to(C.ROOT).as_posix(),archive_sha256=C.digest(p),
            training_batches=0 if updater is None else updater.counts['critic'],physical_substeps=physics.episode_substeps,worker_pid=os.getpid())
        if restore:
            prior=ledger.rows('final',identity['arm'])[0]
            if prior['worker_pid']==os.getpid() or not equal_trace(raw_at(prior),raw):raise ValueError('Independent full physical trajectory differs')
            row.update(restoration_equal=True,source_worker_pid=prior['worker_pid'],restore_worker_pid=os.getpid())
        finish_and_publish(ledger,row,branch,raw,p,c._record)
        C.write(C.HERE/'run/results.json',[a['result'] for a in ledger.state['attempts'] if a['status']=='finished']);C.write(C.HERE/'run/accounting.json',ledger.accounting())
        print(json.dumps(dict(id=row['id'],success=row['success'],xy_um=row['final_xy_error_m']*1e6,guard=guard),ensure_ascii=False),flush=True)
        return ledger.state['status']=='healthy'
    except BaseException as exc:
        if c.active:c._abort(exc)
        C.write(c.output/'failure.json',dict(error=repr(exc),attempts=c.attempts,raw_retained=(c._folder/'episode.json.gz').exists() if hasattr(c,'_folder') else False));raise

def warmup_report(ledger):
    report={}
    for arm in ('F','S'):
        rows=[]
        for result in ledger.rows('warmup',arm):
            raw=raw_at(result);active=sum(r['action_active'] for r in raw['transitions'])
            rows.append(dict(id=result['id'],active=active,cycles=result['cycles'],success=result['success']))
        total=sum(r['active'] for r in rows);cases=sum(r['active']>0 for r in rows)
        report[arm]=dict(rows=rows,active_rows=total,active_cases=cases,passed=len(rows)==4 and total>=256 and cases>=2)
    return dict(arms=report,passed=all(x['passed'] for x in report.values()),thresholds=dict(active_rows=256,active_cases=2),statistical_sufficiency_claim=False)

def save_boundary(b,run):
    n=len(b.history)
    if n not in (0,500,1000,1500,2000,2500):raise ValueError('Registered save boundary')
    path=run/(f'checkpoint_{b.arm}_{n:04d}');pin=b.save(path)
    C.write(run/('latest_checkpoint_'+b.arm+'.json'),dict(path=path.name,sha256=pin,batches=n,arm=b.arm));return path,pin

def verify_checkpoint_child(path,pin,arm,ledger):
    args=[sys.executable,'-X','utf8','-B',str(Path(__file__).resolve()),'--binding-sha256',ledger.state['binding_sha256'],
        '--authorization-sha256',ledger.state['authorization_sha256'],'--verify-checkpoint',str(path),'--checkpoint-pin',pin,'--arm',arm,'--parent-pid',str(os.getpid())]
    from reader_supervision import run_reader
    r=run_reader(args,C.ROOT,path.parent/('zero_reader_'+arm),timeout_s=C.scope()['reader_timeout_s'],guard=ledger.check_live)
    proof=json.loads(r['stdout'])
    C.validate_reader(proof,arm,pin,ledger.state['binding_sha256'],ledger.state['authorization_sha256'])
    C.verify_reader_process(proof,r['process'])
    if proof['pid']==os.getpid():raise ValueError('Separate reader required')
    return proof

def worker(binding,auth,restore=False):
    import learning_runtime as R
    from tools.learning.sac_checkpoint import _same
    run=C.HERE/'run';process=C.HERE/('restore_process' if restore else 'process')
    if restore:l=C.Ledger.load(run/'ledger.json',binding,auth)
    else:run.mkdir(exist_ok=False);l=C.Ledger.create(run/'ledger.json',binding,auth)
    l.live_guard=live_guard(process);p,m=install(l);phase='restore' if restore else 'main'
    try:
        if restore:
            for identity in C.attempts()[28:]:
                arm=identity['arm'];b=R.restore(run/f'checkpoint_{arm}_2500',l.state['frozen'][arm],arm,l);before=b.capture()
                if not episode(identity,l,p,m,b.updater,restore=True):return 20
                if not _same(before,b.capture()):raise ValueError('Restore evaluation altered full learning state')
            l.complete();return 0
        C.write(run/'inherited.json',dict(parent_ledger_sha256=C.PARENT_LEDGER_PIN,attempts=l.state['attempts'][:12],new_dynamic_cost=0))
        C.write(run/'accounting.json',l.accounting())
        gate=warmup_report(l);C.write(run/'warmup_gate.json',gate)
        if not gate['passed']:l.method_failed('insufficient_active_warmup');return 20
        branches={}
        for arm in ('F','S'):
            manifest,pin=R.qualify_dataset(arm,l,run);branches[arm]=R.Branch(arm,l,manifest,pin)
        if not _same(branches['F'].updater._snapshot(),branches['S'].updater._snapshot()):raise ValueError('Paired initial complete network/Adam/RNG differs')
        l.admit_warmup(C.digest(run/'warmup_gate.json'))
        for arm,b in branches.items():
            path,pin=save_boundary(b,run);proof=verify_checkpoint_child(path,pin,arm,l)
            C.write(run/('origin_verified_'+arm+'.json'),proof)
            l.register_zero_reader(arm,pin,proof)
        for identity in C.attempts()[12:20]:
            b=branches[identity['arm']];target=500*(identity['case_index']+1)
            while len(b.history)<target:b.update_one(m)
            save_boundary(b,run)
            if not episode(identity,l,p,m,b.updater,b):return 20
        for arm,b in branches.items():
            while len(b.history)<2500:b.update_one(m)
            path,pin=save_boundary(b,run);l.freeze(arm,pin)
        before={k:b.capture() for k,b in branches.items()}
        for identity in C.attempts()[20:28]:
            b=branches[identity['arm']]
            if not episode(identity,l,p,m,b.updater):return 20
            if not _same(before[b.arm],b.capture()):raise ValueError('Frozen evaluation changed full branch')
        C.write(run/'await_restore.json',dict(main_worker_pid=os.getpid(),frozen=l.state['frozen']));return 0
    except BaseException as exc:
        try:l.fail(repr(exc))
        finally:C.write(run/(phase+'_failure.json'),dict(error=repr(exc),retry_allowed=False))
        raise
    finally:
        C.write(run/(phase+'_costs.json'),costs(p,m));C.write(run/'accounting.json',l.accounting())

def supervise(command,folder):
    source=C.ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/driver.py'
    spec=importlib.util.spec_from_file_location('paired_supervisor',source);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);helper.write=C.write
    return helper.supervise(command,folder,C.ROOT)

def confirm_exit(folder):
    p=folder/'process_exit.json'
    if not p.exists():raise RuntimeError('Worker exit unconfirmed')
    r=C.read(p)
    if not ((r.get('status') in ('finished','failed') and type(r.get('returncode')) is int) or
            (r.get('status')=='supervisor_error' and r.get('worker_stopped') is True and r.get('cleanup_error') is None)):raise RuntimeError('Worker cleanup unconfirmed')
    return r

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--binding-sha256',required=True);parser.add_argument('--authorization-sha256',required=True)
    mode=parser.add_mutually_exclusive_group();mode.add_argument('--worker',action='store_true');mode.add_argument('--restore-worker',action='store_true');mode.add_argument('--verify-checkpoint')
    parser.add_argument('--checkpoint-pin');parser.add_argument('--arm',choices=('F','S'));parser.add_argument('--parent-pid',type=int)
    a=parser.parse_args();C.verify(a.binding_sha256,a.authorization_sha256);select_runtime();C.verify(a.binding_sha256,a.authorization_sha256,with_runtime=True)
    if a.verify_checkpoint:
        from tools.validation.process_parent import require_registered_parent
        claim=C.read(C.HERE/'main_claim.json')
        if a.parent_pid!=claim['pid']:raise ValueError('Registered reader parent required')
        parent_chain=require_registered_parent(a.parent_pid,claim['wall_timestamp'])
        reader_started=time.perf_counter()
        import torch,mujoco,learning_runtime as R
        calls=dict(model_forward=0,optimizer=0,physics=0)
        def forbid(kind):
            def fail(*x,**kw):calls[kind]+=1;raise RuntimeError('Reader forbids '+kind)
            return fail
        torch.nn.Module._call_impl=forbid('model_forward');torch.optim.Adam.step=forbid('optimizer')
        for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbid('physics'))
        l=C.Ledger.load(C.HERE/'run/ledger.json',a.binding_sha256,a.authorization_sha256)
        def reader_guard():
            require_registered_parent(a.parent_pid,claim['wall_timestamp'])
            if (C.HERE/'stop_requested.json').exists() or (C.HERE/'process/stop_requested.json').exists():raise RuntimeError('Reader stop fence')
            if time.perf_counter()-reader_started>C.scope()['reader_timeout_s']:raise RuntimeError('Reader self deadline')
        l.live_guard=reader_guard
        progress=Path(a.verify_checkpoint).parent/('zero_reader_'+a.arm)/'progress.json'
        started=time.perf_counter()
        C.write(progress,dict(event='full_state_restore_started',pid=os.getpid(),wall_timestamp=time.time()))
        source=R._source
        def audited_source(*args,**kwargs):
            l.check_live()
            value=source(*args,**kwargs)
            l.check_live()
            C.write(progress,dict(event='archive_reaudited',pid=os.getpid(),elapsed_s=time.perf_counter()-started,wall_timestamp=time.time()))
            return value
        R._source=audited_source
        b=R.restore(Path(a.verify_checkpoint),a.checkpoint_pin,a.arm,l)
        C.write(progress,dict(event='full_state_restore_complete',pid=os.getpid(),elapsed_s=time.perf_counter()-started,wall_timestamp=time.time()))
        l.check_live()
        print(json.dumps(dict(complete_equal=True,pid=os.getpid(),manifest_sha256=a.checkpoint_pin,calls=calls,batches=len(b.history),arm=a.arm,binding_sha256=a.binding_sha256,authorization_sha256=a.authorization_sha256,parent_chain=parent_chain)));return 0
    if a.worker or a.restore_worker:
        folder=C.HERE/('restore_process' if a.restore_worker else 'process');live_guard(folder)()
        with (C.HERE/('restore_claim.json' if a.restore_worker else 'main_claim.json')).open('x',encoding='utf-8') as f:
            json.dump(dict(pid=os.getpid(),parent_pid=os.getppid(),wall_timestamp=time.time()),f);f.flush();os.fsync(f.fileno())
        if os.name=='nt':
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0002)
        return worker(a.binding_sha256,a.authorization_sha256,a.restore_worker)
    if (C.HERE/'process/started.json').exists():raise FileExistsError('Already launched; no automatic retry')
    cmd=[sys.executable,'-X','utf8','-X','faulthandler','-B',str(Path(__file__).resolve()),'--binding-sha256',a.binding_sha256,'--authorization-sha256',a.authorization_sha256]
    try:
        code=supervise(cmd+['--worker'],C.HERE/'process');confirm_exit(C.HERE/'process')
        l=C.Ledger.load(C.HERE/'run/ledger.json',a.binding_sha256,a.authorization_sha256)
        if code==0 and l.state['status']=='healthy' and len(l.state['attempts'])==28:
            code=supervise(cmd+['--restore-worker'],C.HERE/'restore_process');confirm_exit(C.HERE/'restore_process')
            l=C.Ledger.load(C.HERE/'run/ledger.json',a.binding_sha256,a.authorization_sha256)
        controlled=code==20 and l.state['status'] in ('stopped','method_failed');complete=code==0 and l.state['status']=='complete'
        if not controlled and not complete:raise RuntimeError('Paired worker failed')
        C.write(C.HERE/'exit_classification.json',dict(controlled_stop=controlled,execution_complete=complete,status=l.state['status'],returncode=code,worker_stop_confirmed=True,retry_allowed=False))
        return code
    except BaseException as exc:
        confirmed=False;error=None
        try:
            for folder in (C.HERE/'process',C.HERE/'restore_process'):
                if (folder/'started.json').exists():confirm_exit(folder)
            confirmed=True
            if (C.HERE/'run/ledger.json').exists():
                l=C.Ledger.load(C.HERE/'run/ledger.json',a.binding_sha256,a.authorization_sha256)
                C.write(C.HERE/'run/ledger_before_exit.json',l.state);l.fail(repr(exc));C.write(C.HERE/'run/accounting.json',l.accounting())
        except BaseException as other:error=repr(other)
        C.write(C.HERE/'launch_failure.json',dict(error=repr(exc),worker_stop_confirmed=confirmed,reconciliation_error=error,retry_allowed=False,unknown_costs_use_reserved_upper_bound=True));raise

if __name__=='__main__':raise SystemExit(main())
