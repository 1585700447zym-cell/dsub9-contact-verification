"""Supervised, paired random-action preflight. No neural policy or optimizer."""
import argparse
from copy import deepcopy
import gzip,importlib.util,json,os,sys,time
from pathlib import Path
from execution_contract import (HERE,ROOT,Ledger,attempts,scope,config,read,digest,write,
    canonical,require_authorization,verify_binding)

def select_runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()

def live_guard():
    from tools.validation.process_parent import require_registered_parent
    record=read(HERE/'started.json')
    def check():
        if (HERE/'stop_requested.json').exists():raise RuntimeError('Supervisor requested stop')
        require_registered_parent(record['supervisor_pid'],record['wall_timestamp'])
    return check

class PhysicsBudget:
    """Durable episode reservation precedes reset; substeps charge before call.

    Supervision/disk ownership is checked at each control boundary by Schedule
    and before initialization. Ten physical substeps share that control permit.
    Local active reservation and substep limits are checked on every substep.
    """
    def __init__(self,ledger):
        self.ledger=ledger;self.token=None;self.episode_substeps=0;self.total_substeps=0;self.initializations={}
        self.substep_forwards=0;self.episode_forwards=0
    def active(self):
        s=self.ledger.state
        if self.ledger.write_failed or s['status']!='healthy' or self.token is None or s['active']!=self.token:
            raise RuntimeError('Active durable physics reservation required')
    def begin(self):
        self.ledger.check_live();s=self.ledger.state
        if s['status']!='healthy' or s['active'] is None:raise RuntimeError('Reserved start required')
        if self.token==s['active']:raise RuntimeError('Reservation already initialized')
        self.token=s['active'];self.episode_substeps=0;self.episode_forwards=0
    def step(self,original,*args,**kwargs):
        self.active()
        if len(args)!=2 or set(kwargs)-{'nstep'} or type(kwargs.get('nstep',1)) is not int or kwargs.get('nstep',1)!=1:
            raise ValueError('Exactly one physical substep required')
        if self.episode_substeps>=130000 or self.total_substeps>=1040000:raise RuntimeError('Physical substep cap exceeded')
        self.episode_substeps+=1;self.total_substeps+=1
        return original(*args,**kwargs)
    def initialize(self,kind,original,*args,**kwargs):
        self.ledger.check_live();self.active()
        self.initializations[kind]=self.initializations.get(kind,0)+1
        return original(*args,**kwargs)
    def forward(self,original,*args,**kwargs):
        self.active()
        if self.episode_substeps==0:return self.initialize('initial_forward',original,*args,**kwargs)
        if self.episode_forwards>=self.episode_substeps:raise RuntimeError('One paired forward per physical substep')
        self.episode_forwards+=1;self.substep_forwards+=1
        return original(*args,**kwargs)

class PreflightPermit:
    def __init__(self,binding_pin,auth_pin,ledger):
        self.expected_digest=binding_pin;self.auth_pin=auth_pin;self.ledger=ledger;self.config=config()
        self.verify()
    def verify(self,case=None):
        self.ledger.check_live()
        if self.ledger.state['status']!='healthy':raise RuntimeError('Preflight ledger closed')
        require_authorization(self.expected_digest,self.auth_pin);verify_binding(self.expected_digest,with_runtime=True)
        if canonical(self.config)!=canonical(config()):raise ValueError('Physical configuration changed')
        if case is not None:
            i=self.ledger.state['active']
            if i is None or canonical(case)!=canonical(attempts()[i]['case']):raise ValueError('Reserved paired case required')
        return dict(preflight_admitted=True,collection_admitted=False,update_admitted=False,training_admitted=False)

def collector_type():
    from tools.learning.admitted_collection import AdmittedCollector,_write_archive,_write_json
    from tools.learning.audited_replay import AuditedReplay
    from tools.learning.sac_checkpoint import _audit_physics
    from tools.learning.contact_contract import guard_clear
    from tools.learning.episode_rules import FORCE_ONLY
    from sampling_runtime import ContextPolicy,require_collection_mode,audit_sampling
    class PreflightCollector(AdmittedCollector):
        admission_type=PreflightPermit
        @staticmethod
        def case_validator(case):
            if not any(canonical(case)==canonical(a['case']) for a in attempts()):raise ValueError('Four registered cases only')
        def __init__(self,*,admission,output):
            super().__init__(admission=admission,replay=AuditedReplay(capacity=13000),output=output)
            self.schedule=None
        def collect(self,policy,steps,*,cut_at_end=False,deterministic=True):
            require_collection_mode(cut_at_end=cut_at_end,deterministic=deterministic)
            if type(policy) is not ContextPolicy or policy.session is not self.session or policy.schedule is not self.schedule:
                raise ValueError('Current session/schedule context policy required')
            return super().collect(policy,steps,deterministic=True)
        def _stop_tail(self):
            self.fault_tail_transitions=[]
            self.session.start_external_tail()
            for _ in range(1500):
                if self.session.done:return
                self.admission.ledger.check_live()
                if self.session.cycle_id>=13000:raise RuntimeError('Safety tail reached total cycle cap')
                before=self.session.prepare_cycle();result=self.session.advance_cycle([0.]*4)
                self.fault_tail_transitions.append(dict(cycle_id=before.cycle_id,
                    observation=deepcopy(before.policy_observation),next_observation=deepcopy(result.next_snapshot.policy_observation),
                    action=deepcopy(result.action_log['experience_action']),action_active=before.residual_enabled,
                    next_action_active=result.next_snapshot.residual_enabled,dt=result.dt,done=result.done,
                    reward_terms=deepcopy(result.reward_terms),action_log=deepcopy(result.action_log),
                    trace_row=deepcopy(result.trace_row),events=deepcopy(result.events),training_admitted=False))
            if not self.session.done:raise RuntimeError('Safety tail did not complete')
        def retry_publication(self):
            if self._status_pending:
                _write_json(self._folder/'status.json',self._record);self._status_pending=False
                self._blocked=not self._record['simulation_valid'] or not self._record['physical_stopped']
                return
            if self._pending is None:raise RuntimeError('No pending preflight archive')
            raw=self._pending
            raw.update(preflight_identity=deepcopy(self.schedule.identity),sampling_records=deepcopy(self.schedule.records),
                sampling_final=self.schedule.capture(),sampling_mode='temporal_uniform_preflight',
                fault_tail_transitions=deepcopy(getattr(self,'fault_tail_transitions',[])),
                training_admitted=False,evaluation_method='warmup_preflight',optimizer_steps_start=0,optimizer_steps=0)
            raw['guard_clear']=guard_clear(raw)
            # Archive before fallible qualification and offline audits. Never rerun physics.
            sha=_write_archive(self._folder/'episode.json.gz',raw)
            self.admission.verify(raw['case']);_audit_physics(raw);proof=audit_sampling(raw)
            if raw['fault'] is not None:raise ValueError('Faulted preflight retained, not accepted')
            self.replay._prepare(raw['transitions'])
            facts=raw['guard_facts']
            if not facts['motion_reasons'] and not facts['invalid_reasons'] and all(x=='FORCE_LIMIT' for x in facts['contact_reasons']):
                rule_audit=FORCE_ONLY.classify(raw)
            else:rule_audit='other_guard_stop'
            self._record.update(committed=0,discarded=len(raw['transitions']),training_admitted=False,
                physical_stopped=raw['outcome']['physical_stopped'],simulation_valid=raw['outcome']['simulation_valid'],
                task_outcome=raw['outcome']['task_outcome'],valid_for_learning=False,archive_sha256=sha,
                sampling_proof=proof,rule_audit=rule_audit,status='preflight_archived')
            self._pending=None;self._status_pending=True;self.session=None;self.buffer=None
            self.retry_publication()
    return PreflightCollector

def worker(binding_pin,auth_pin):
    import torch,mujoco
    from sampling_runtime import Schedule,ContextPolicy,audit_sampling
    from tools.learning.engineering_evaluation import episode_metrics
    from tools.learning.sac_checkpoint import _audit_physics
    run=HERE/'run';run.mkdir(exist_ok=False)
    ledger=Ledger.create(run/'ledger.json',binding_pin,auth_pin);ledger.live_guard=live_guard()
    budget=PhysicsBudget(ledger);collector=None;results=[];calls=dict(model_forward=0,optimizer=0)
    def forbidden(kind):
        def fail(*a,**k):calls[kind]+=1;raise RuntimeError('Preflight forbids '+kind)
        return fail
    torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer')
    original=mujoco.mj_step
    mujoco.mj_step=lambda *a,**k:budget.step(original,*a,**k)
    forward=mujoco.mj_forward
    mujoco.mj_forward=lambda *a,**k:budget.forward(forward,*a,**k)
    for name in ('mj_resetData','mj_resetDataKeyframe'):
        fn=getattr(mujoco,name)
        def initialize(*a,_name=name,_fn=fn,**k):return budget.initialize(_name,_fn,*a,**k)
        setattr(mujoco,name,initialize)
    for name in ('mj_step1','mj_step2'):
        def split(*a,**k):raise RuntimeError('Unregistered split physics step')
        setattr(mujoco,name,split)
    try:
        permit=PreflightPermit(binding_pin,auth_pin,ledger)
        collector=collector_type()(admission=permit,output=run/'episodes')
        for identity in attempts():
            ledger.start(identity['id']);budget.begin()
            def check(identity=identity):
                ledger.check_live();budget.active()
                if canonical(ledger.state['attempts'][ledger.state['active']]['identity'])!=canonical(identity):raise RuntimeError('Sampling reservation changed')
            collector.schedule=Schedule(identity,check)
            collector.start(identity['id'],case=identity['case'],seed=scope()['seed'])
            policy=ContextPolicy(collector.session,collector.schedule)
            while collector.active:
                ledger.check_live();collector.collect(policy,500,deterministic=True)
                write(run/'progress.json',dict(id=identity['id'],arm=identity['arm'],cycles=collector._record['steps'],
                    draw_count=collector.schedule.sampler.draw_count,physical_substeps=budget.episode_substeps,wall_timestamp=time.time()))
            path=collector.output/identity['id']/'episode.json.gz'
            raw=json.loads(gzip.decompress(path.read_bytes()));receipt=collector.attempts[-1]
            proof=audit_sampling(raw);_audit_physics(raw);facts=raw['guard_facts']
            if (receipt['archive_sha256']!=digest(path) or read(path.parent/'status.json')!=receipt or
                raw['episode_id']!=identity['id'] or canonical(raw['case'])!=canonical(identity['case']) or
                receipt['committed']!=0 or len(collector.replay) or raw['training_admitted'] is not False or
                budget.episode_substeps!=10*len(raw['transitions']) or any(calls.values()) or collector._blocked):
                raise ValueError('Physical transcript, isolation or budget differs')
            row=dict(**identity,completed=True,**episode_metrics(raw),draw_count=proof['draw_count'],
                model_forwards=0,training_batches=0,guard_hit=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons']))
            results.append(row);write(run/'results.json',results);ledger.finish(row)
            write(run/'verification.json',dict(all_attempts_completed=len(results)==8,sampling_state_restored=True,
                replay_committed=0,forbidden_calls=calls))
            write(run/'accounting.json',ledger.accounting())
            if ledger.state['status']!='healthy':return 20 if ledger.state['status']=='stopped' else 1
        ledger.complete();write(run/'completed.json',dict(status='preflight_complete',b2_complete=False,
            training_admitted=False,success=sum(r['success'] for r in results),accounting=ledger.accounting()))
        return 0
    except BaseException as exc:
        cleanup=[]
        if collector is not None and collector.active:
            try:collector._abort(exc)
            except BaseException as other:cleanup.append(repr(other))
        if ledger.state['status']=='healthy':
            try:ledger.fail(repr(exc))
            except BaseException as other:cleanup.append(repr(other))
        write(run/'failure.json',dict(error=repr(exc),cleanup_errors=cleanup,forbidden_calls=calls,retry_allowed=False))
        raise
    finally:
        if collector is not None:write(run/'attempts.json',collector.attempts)
        write(run/'accounting.json',ledger.accounting())
        write(run/'physics_calls.json',dict(total_substeps_attempted=budget.total_substeps,current_episode_substeps_attempted=budget.episode_substeps,
            substep_forwards_attempted=budget.substep_forwards,initializations=budget.initializations,forbidden_calls=calls))

def supervise(command):
    source=ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/driver.py'
    spec=importlib.util.spec_from_file_location('temporal_preflight_supervisor',source)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);helper.write=write
    return helper.supervise(command,HERE,ROOT)

def finalize_exception(binding_pin,auth_pin,exc):
    path=HERE/'process_exit.json';process=read(path) if path.exists() else {}
    uncertain=(HERE/'stop_requested.json').exists() or not process or (process.get('status')=='supervisor_error' and
        (process.get('worker_stopped') is not True or process.get('cleanup_error') is not None))
    if uncertain:write(HERE/'stop_requested.json',dict(error=repr(exc),worker_stop_confirmed=False))
    elif (HERE/'run/ledger.json').exists():
        ledger=Ledger.load(HERE/'run/ledger.json',binding_pin,auth_pin)
        if ledger.state['status']=='healthy':ledger.fail(repr(exc))
        write(HERE/'run/accounting.json',ledger.accounting())
    write(HERE/'exit_classification.json',dict(execution_complete=False,error=repr(exc),worker_stop_confirmed=not uncertain,
        ledger_preserved_pending_process_confirmation=uncertain,retry_allowed=False,b2_complete=False,process_exit=process))

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--binding-sha256',required=True);p.add_argument('--authorization-sha256')
    mode=p.add_mutually_exclusive_group();mode.add_argument('--worker',action='store_true');mode.add_argument('--verify-only',action='store_true')
    args=p.parse_args(argv)
    if args.verify_only:verify_binding(args.binding_sha256);print('Preflight binding verified; no computation started.');return 0
    require_authorization(args.binding_sha256,args.authorization_sha256)
    verify_binding(args.binding_sha256);select_runtime();verify_binding(args.binding_sha256,with_runtime=True)
    if args.worker:
        live_guard()()
        with (HERE/'claim.json').open('x',encoding='utf-8') as f:
            json.dump(dict(pid=os.getpid(),parent_pid=os.getppid(),wall_timestamp=time.time()),f);f.flush();os.fsync(f.fileno())
        if os.name=='nt':
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0002)
        return worker(args.binding_sha256,args.authorization_sha256)
    command=[sys.executable,'-X','utf8','-X','faulthandler','-B',str(Path(__file__).resolve()),
        '--binding-sha256',args.binding_sha256,'--authorization-sha256',args.authorization_sha256,'--worker']
    try:
        code=supervise(command);ledger=Ledger.load(HERE/'run/ledger.json',args.binding_sha256,args.authorization_sha256)
        complete=code==0 and ledger.state['status']=='complete' and (HERE/'run/completed.json').exists()
        controlled=code==20 and ledger.state['status']=='stopped'
        if not complete and not controlled:raise RuntimeError('Preflight worker failed: '+str(code))
        write(HERE/'exit_classification.json',dict(execution_complete=complete,controlled_stop=controlled,returncode=code,
            retry_allowed=False,b2_complete=False,accounting=ledger.accounting()))
        return code
    except FileExistsError:raise
    except BaseException as exc:finalize_exception(args.binding_sha256,args.authorization_sha256,exc);raise

if __name__=='__main__':raise SystemExit(main())
