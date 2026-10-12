"""Fresh supervised evaluation and one independent physical replay."""
import argparse,gzip,importlib.util,json,math,os,sys,time
from copy import deepcopy
from pathlib import Path
import night_contract as N
os.environ['MPLCONFIGDIR']=str(N.ROOT/'tmp/learning_mpl_cache')

def select_runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()

def live_guard(folder):
    from tools.validation.process_parent import require_registered_parent
    record=N.read(folder/'started.json')
    def check():
        if (folder/'stop_requested.json').exists():raise RuntimeError('Supervisor stop fence')
        require_registered_parent(record['supervisor_pid'],record['wall_timestamp'])
    return check

class Meter:
    def __init__(self,ledger):self.ledger=ledger;self.states=0;self.modules=0;self.in_predict=False;self.local=0;self.episode_states=0
    def module(self,original,*a,**kw):
        if not self.in_predict or self.local>=32 or self.modules>=2080000 or self.ledger.state['active'] is None or self.ledger.state['status']!='healthy':raise RuntimeError('Reserved actor context required')
        self.local+=1;self.modules+=1;return original(*a,**kw)
    def begin(self):self.episode_states=0
    def predict(self,original,observation,deterministic=True):
        import numpy as np
        self.ledger.check_live()
        if deterministic is not True or np.asarray(observation).shape!=(120,) or not np.isfinite(observation).all() or self.in_predict or self.ledger.state['active'] is None or self.ledger.state['status']!='healthy' or self.episode_states>=13000 or self.states>=65000:raise ValueError('Deterministic reserved single actor state required')
        self.states+=1;self.episode_states+=1;self.local=0;self.in_predict=True
        try:return original(observation,deterministic=True)
        finally:self.in_predict=False

def forbidden(kind):
    def reject(*a,**kw):raise RuntimeError('Frozen screening forbids '+kind)
    return reject

def install(ledger):
    import torch,mujoco
    sys.path.insert(0,str(N.P.PREFLIGHT))
    from run_preflight import PhysicsBudget
    class Physics(PhysicsBudget):
        def step(self,original,*a,**kw):
            self.active()
            if len(a)!=2 or set(kw)-{'nstep'} or type(kw.get('nstep',1)) is not int or kw.get('nstep',1)!=1:raise ValueError('Exactly one substep')
            if self.episode_substeps>=130000 or self.total_substeps>=650000:raise RuntimeError('Bounded physical budget')
            self.episode_substeps+=1;self.total_substeps+=1;return original(*a,**kw)
    physics=Physics(ledger);meter=Meter(ledger)
    call=torch.nn.Module._call_impl;torch.nn.Module._call_impl=lambda *a,**k:meter.module(call,*a,**k)
    torch.optim.Adam.step=forbidden('optimizer')
    step=mujoco.mj_step;mujoco.mj_step=lambda *a,**k:physics.step(step,*a,**k)
    forward=mujoco.mj_forward;mujoco.mj_forward=lambda *a,**k:physics.forward(forward,*a,**k)
    for name in ('mj_resetData','mj_resetDataKeyframe'):
        fn=getattr(mujoco,name)
        def wrapped(*a,_name=name,_fn=fn,**k):return physics.initialize(_name,_fn,*a,**k)
        setattr(mujoco,name,wrapped)
    for name in ('mj_step1','mj_step2'):setattr(mujoco,name,forbidden('split physics'))
    return physics,meter

def collector_type():
    from tools.learning.bounded_cycle import BoundedEvaluationCollector
    class Collector(BoundedEvaluationCollector):
        def retry_publication(self):
            from tools.learning.engineering_evaluation import EvaluationCollector
            from tools.learning.episode_rules import stamp_pending
            from deployment_rules import DeploymentRules
            if self._pending is not None:
                self._pending.update(evaluation_method=self.method,optimizer_steps_start=self._start_count['critic'],optimizer_steps=self.updater.counts['critic'])
                stamp_pending(self._pending,self._record,DeploymentRules(self.admission.config['action']['scale']))
            return EvaluationCollector.retry_publication(self)
        def _stop_tail(self):
            self.session.start_external_tail()
            for _ in range(1500):
                if self.session.done:return
                if math.ceil((float(self.session.env.data.time)-1e-9)/.002)>=13000:raise RuntimeError('Stop tail total cycle cap')
                self.session.advance_cycle([0.]*4)
            if not self.session.done:raise RuntimeError('Stop tail incomplete')
    return Collector

def permit_type():
    from tools.learning.bounded_contact import BoundedAdmission
    from tools.learning.episode_rules import FORCE_ONLY
    import learning_runtime as R
    class Permit(BoundedAdmission):
        episode_rules=FORCE_ONLY;updater_type=R.Updater
        def __init__(self,ledger,binding,auth):
            self.ledger=ledger;self.expected_digest=binding;self.auth=auth;self._config=N.config(ledger.state['variant']);self.verify()
        @property
        def config(self):return deepcopy(self._config)
        def verify(self,case=None):
            self.ledger.check_live()
            if self.ledger.state['status']!='healthy':raise RuntimeError('Candidate closed')
            N.verify(self.expected_digest,self.auth,self.ledger.state['variant'])
            if N.canonical(self.config)!=N.canonical(N.config(self.ledger.state['variant'])):raise ValueError('Deployment scale changed')
            if case is not None:
                i=self.ledger.state['active']
                if i is None or case!=N.identities()[i]:raise ValueError('Reserved case required')
            self._record=dict(capability='frozen_c2000_deployment_v1',config=deepcopy(self.config),synthetic_only=False,
                collection_admitted=False,update_admitted=False,evaluation_admitted=True,binding_sha256=self.expected_digest,
                checkpoint_sha256=N.CHECKPOINT_PIN,variant=self.ledger.state['variant'])
            return deepcopy(self._record)
    return Permit

def collector_output(folder,index):return folder/'collections'/str(index)

def raw_at(folder,index):
    identity=('restore_' if index==4 else '')+N.identities()[index]['name']
    p=collector_output(folder,index)/identity/'episode.json.gz';return p,json.loads(gzip.decompress(p.read_bytes()))

def equal_trace(original,current):
    from tools.learning.sac_checkpoint import _same
    return all(_same(original[k],current[k]) for k in ('case','seed','outcome','transitions','guard_facts','events','stop_samples','stop_time','audit_end_time_s','final_session'))

def worker(variant,binding,auth,restore=False):
    import torch
    from frozen_reader import load
    from tools.learning.sac_checkpoint import _same,_audit_physics
    from tools.learning.bounded_cycle import FrozenPolicy,episode_metrics
    folder=N.HERE/variant;process=folder/'restore_process' if restore else folder/'process'
    if restore:l=N.Ledger.load(folder/'ledger.json',binding,auth,variant)
    else:
        folder.mkdir(exist_ok=True);l=N.Ledger.create(folder/'ledger.json',binding,auth,variant)
    l.live_guard=live_guard(process);physics,meter=install(l);collector=None;phase='restore' if restore else 'main'
    try:
        l.check_live();u,s,proof=load();before=u._snapshot()
        u.update=forbidden('update');u.policy.critic.forward=forbidden('critic');u.policy.critic_target.forward=forbidden('target critic')
        predict=u.predict;u.predict=lambda observation,deterministic=False:meter.predict(predict,observation,deterministic)
        N.write(folder/(phase+'_load.json'),dict(**proof,pid=os.getpid(),new_model_calls=meter.modules,new_physics=physics.total_substeps))
        for index in ([4] if restore else range(4)):
            l.start(index);physics.begin();meter.begin()
            collector=collector_type()(admission=permit_type()(l,binding,auth),output=collector_output(folder,index),updater=u,method='sac',checkpoint_sha256=N.CHECKPOINT_PIN)
            identity=('restore_' if index==4 else '')+N.identities()[index]['name'];collector.start(identity,case=N.identities()[index],seed=N.P.scope()['seed'])
            while collector.active:
                l.check_live();collector.collect(FrozenPolicy(u),500,deterministic=True)
                N.write(folder/'progress.json',dict(variant=variant,index=index,cycles=collector._record['steps'],phase=phase,wall_timestamp=time.time()))
            path,raw=raw_at(folder,index);receipt=collector.attempts[-1];facts=raw['guard_facts'];_audit_physics(raw)
            if N.digest(path)!=receipt['archive_sha256'] or raw['fault'] is not None or raw['training_admitted'] is not False or receipt['committed']!=0 or len(collector.replay) or not _same(before,u._snapshot()) or collector._blocked:raise ValueError('Archive/frozen state/evaluation isolation failed')
            row=dict(index=index,completed=True,**episode_metrics(raw),actor_states=meter.episode_states,physical_substeps=physics.episode_substeps,
                guard_hit=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons']),archive_path=path.relative_to(N.ROOT).as_posix(),archive_sha256=N.digest(path),policy_sha256=N.ACTOR_PIN)
            if restore:
                prior=N.read(folder/'main_load.json');_,original=raw_at(folder,0)
                if prior['pid']==os.getpid() or not equal_trace(original,raw):raise ValueError('Independent complete physical replay differs')
                row.update(restoration_equal=True,source_worker_pid=prior['pid'],restore_worker_pid=os.getpid())
                N.write(folder/'restoration.json',dict(exact_physical_replay=True,full_updater_equal=True,source_worker_pid=prior['pid'],restore_worker_pid=os.getpid(),checkpoint_sha256=N.CHECKPOINT_PIN))
            l.finish(row);N.write(folder/'results.json',[a['result'] for a in l.state['attempts'] if a['status']=='finished'])
            if l.state['status']!='healthy' and l.state['status']!='await_restore':return 20 if l.state['status']=='stopped' else 1
        if restore:l.complete()
        N.write(folder/(phase+'_verification.json'),dict(frozen_updater_unchanged=True,source_complete_file_unchanged=True,training_batches=0,critic_forward=0,actor_sha256=N.ACTOR_PIN))
        return 0
    except BaseException as exc:
        cleanup=[]
        if collector is not None:
            try:
                if collector.active:collector._abort(exc)
                collector.retain_failure(exc)
            except BaseException as other:cleanup.append(repr(other))
        l.fail(repr(exc));N.write(folder/(phase+'_failure.json'),dict(error=repr(exc),cleanup_errors=cleanup,retry_allowed=False));raise
    finally:
        N.write(folder/(phase+'_costs.json'),dict(actor_states=meter.states,module_calls=meter.modules,physical_substeps=physics.total_substeps,
            substep_forwards=physics.substep_forwards,initializations=physics.initializations,training_batches=0,critic_forward=0))
        N.write(folder/'accounting.json',l.accounting())

def supervise(command,folder):
    source=N.ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/driver.py'
    spec=importlib.util.spec_from_file_location('night_frozen_supervisor',source);helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);helper.write=N.write
    return helper.supervise(command,folder,N.ROOT)

def command(a,restore=False):
    return [sys.executable,'-X','utf8','-X','faulthandler','-B',str(Path(__file__).resolve()),'--variant',a.variant,'--binding-sha256',a.binding_sha256,'--authorization-sha256',a.authorization_sha256,'--restore-worker' if restore else '--worker']

def main():
    p=argparse.ArgumentParser();p.add_argument('--variant',choices=['base','small'],required=True);p.add_argument('--binding-sha256',required=True);p.add_argument('--authorization-sha256',required=True)
    g=p.add_mutually_exclusive_group();g.add_argument('--worker',action='store_true');g.add_argument('--restore-worker',action='store_true');a=p.parse_args()
    N.verify(a.binding_sha256,a.authorization_sha256,a.variant);select_runtime();N.P.verify_binding(N.read(N.PARENT/'execution_pins.json')['binding_sha256'],with_runtime=True)
    folder=N.HERE/a.variant
    if a.worker or a.restore_worker:
        process=folder/'restore_process' if a.restore_worker else folder/'process';live_guard(process)()
        claim=N.HERE/(a.variant+'_restore_claim.json' if a.restore_worker else a.variant+'_claim.json')
        with claim.open('x',encoding='utf-8') as f:json.dump(dict(pid=os.getpid(),parent_pid=os.getppid(),wall_timestamp=time.time()),f);f.flush();os.fsync(f.fileno())
        if os.name=='nt':
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0002)
        return worker(a.variant,a.binding_sha256,a.authorization_sha256,a.restore_worker)
    if (folder/'process/started.json').exists():raise FileExistsError('Candidate already launched; no retry')
    try:
        code=supervise(command(a),folder/'process');N.confirm_stopped(folder);l=N.Ledger.load(folder/'ledger.json',a.binding_sha256,a.authorization_sha256,a.variant)
        if code==0 and l.state['status']=='await_restore':
            code=supervise(command(a,True),folder/'restore_process');N.confirm_stopped(folder);l=N.Ledger.load(folder/'ledger.json',a.binding_sha256,a.authorization_sha256,a.variant)
        controlled=code==20 and l.state['status']=='stopped';complete=code==0 and l.state['status']=='complete'
        if not controlled and not complete:raise RuntimeError('Frozen worker verification failed')
        N.write(folder/'exit_classification.json',dict(controlled_stop=controlled,execution_complete=complete,status=l.state['status'],returncode=code,retry_allowed=False,b2_complete=False));return code
    except FileExistsError:raise
    except BaseException as exc:
        reconciliation_error=None
        try:N.finalize_failed_exit(folder,a.binding_sha256,a.authorization_sha256,a.variant,repr(exc))
        except BaseException as other:reconciliation_error=repr(other)
        N.write(N.HERE/(a.variant+'_launch_failure.json'),dict(error=repr(exc),reconciliation_error=reconciliation_error,worker_stop_confirmed=reconciliation_error is None,retry_allowed=False,b2_complete=False));raise

if __name__=='__main__':raise SystemExit(main())
