"""One authorized frozen-B evaluation. No training or diagnostic entry exists."""
import argparse
from copy import deepcopy
import gzip
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from evaluation_contract import (Ledger,read,digest,write,scope,verify_binding,require_authorization,
    PARENT,PARENT_PIN,PARENT_AUTH,B_PIN)

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

class PredictionMeter:
    """Reserve a whole episode before inference; count exactly one state per cycle."""
    def __init__(self,updater,ledger):
        self.original=updater.predict;self.ledger=ledger;self.count=0;self.token=None
    def begin(self):
        self.ledger.check_live()
        if self.ledger.state['status']!='healthy' or self.ledger.state['active'] is None:
            raise RuntimeError('Active durable episode reservation required')
        self.token=self.ledger.state['active'];self.count=0
    def predict(self,observation,deterministic=True):
        import numpy as np
        self.ledger.check_live();s=self.ledger.state
        if s['status']!='healthy' or self.token is None or s['active']!=self.token or self.count>=13000:
            raise RuntimeError('Frozen inference budget or active reservation refused')
        if deterministic is not True or np.asarray(observation).shape!=(120,) or not np.isfinite(observation).all():
            raise ValueError('Only a single deterministic control observation permitted')
        self.count+=1
        return self.original(observation,deterministic=True)

def collector_type():
    from tools.learning.bounded_cycle import BoundedEvaluationCollector
    class FrozenBCollector(BoundedEvaluationCollector):
        def _stop_tail(self):
            # The inherited error tail allowed 1500 extra cycles after the
            # watchdog. This evaluation's 13000 cap includes that tail.
            self.session.start_external_tail()
            for _ in range(1500):
                if self.session.done:return
                cycles=math.ceil((float(self.session.env.data.time)-1e-9)/.002)
                if cycles>=13000:raise RuntimeError('Safety tail reached total cycle cap')
                self.session.advance_cycle([0.]*4)
            if not self.session.done:raise RuntimeError('Safety tail did not complete')
    return FrozenBCollector

def admission_type():
    from tools.learning.bounded_contact import BoundedAdmission
    from tools.learning.actor_lr_engine import ComparisonUpdater
    from tools.learning.actor_lr_contract import execution_config
    from tools.learning.bounded_cycle import cases
    from tools.learning.episode_rules import FORCE_ONLY
    class FrozenBAdmission(BoundedAdmission):
        episode_rules=FORCE_ONLY;updater_type=ComparisonUpdater
        def __init__(self,binding_pin,auth_pin,ledger):
            self.expected_digest=binding_pin;self.auth_pin=auth_pin;self.ledger=ledger;self.verify()
        def verify(self,case=None):
            self.ledger.check_live()
            if self.ledger.state['status']!='healthy':raise RuntimeError('Evaluation ledger stopped')
            require_authorization(self.expected_digest,self.auth_pin,folder=HERE)
            verify_binding(self.expected_digest,with_runtime=True)
            if case is not None:
                i=self.ledger.state['active']
                if i is None or case!=cases()[i]:raise ValueError('Only reserved original development point allowed')
            self._record=dict(capability='frozen_B_development_evaluation_v1',config=execution_config('B'),
                synthetic_only=False,collection_admitted=False,update_admitted=False,evaluation_admitted=True,
                binding_sha256=self.expected_digest,authorization_sha256=self.auth_pin,checkpoint_sha256=B_PIN)
            return deepcopy(self._record)
    return FrozenBAdmission

def worker(binding_pin,auth_pin):
    import torch
    from tools.learning.actor_lr_engine import read_origin,load_checkpoint
    from tools.learning.sac_checkpoint import _same,_audit_physics
    from tools.learning.episode_rules import FORCE_ONLY
    from tools.learning.bounded_cycle import cases,FrozenPolicy,episode_metrics
    from tools.learning.bounded_contact import SEED
    run=HERE/'run';run.mkdir(exist_ok=False)
    ledger=Ledger.create(run/'ledger.json',binding_pin,auth_pin);ledger.live_guard=live_guard()
    collector=None;meter=None;results=[];calls=dict(optimizer_steps=0,critic_forward=0)
    def forbidden(kind):
        def fail(*a,**k):calls[kind]+=1;raise RuntimeError('Frozen evaluation forbids '+kind)
        return fail
    torch.optim.Adam.step=forbidden('optimizer_steps')
    try:
        ledger.check_live();origin,plan=read_origin()
        _,updater=load_checkpoint(PARENT/'run/checkpoint_B',B_PIN,origin,plan,'B',PARENT_PIN,PARENT_AUTH)
        updater.update=forbidden('optimizer_steps')
        updater.policy.critic.forward=forbidden('critic_forward');updater.policy.critic_target.forward=forbidden('critic_forward')
        before=updater._snapshot();meter=PredictionMeter(updater,ledger);updater.predict=meter.predict
        write(run/'restoration.json',dict(checkpoint_sha256=B_PIN,updates=updater.counts,
            complete_state_restored=True,new_optimizer_steps=0,new_model_forwards=0))
        permit=admission_type()(binding_pin,auth_pin,ledger)
        collector=collector_type()(admission=permit,output=run/'episodes',updater=updater,method='sac',checkpoint_sha256=B_PIN)
        for case in cases():
            ledger.start(case['name']);meter.begin()  # durable physical and actor budget first
            collector.start(case['name'],case=case,seed=SEED)
            while collector.active:
                ledger.check_live();collector.collect(FrozenPolicy(updater),500,deterministic=True)
                write(run/'progress.json',dict(case=case['name'],cycles=collector._record['steps'],
                    actor_states_observed=meter.count,wall_timestamp=time.time()))
            path=collector.output/case['name']/'episode.json.gz';raw=json.loads(gzip.decompress(path.read_bytes()))
            receipt=collector.attempts[-1];facts=raw['guard_facts'];_audit_physics(raw);FORCE_ONLY.classify(raw)
            if (receipt['archive_sha256']!=digest(path) or read(path.parent/'status.json')!=receipt
                or raw['training_admitted'] is not False or receipt['committed']!=0 or len(collector.replay)
                or not _same(before,updater._snapshot()) or any(calls.values()) or collector._blocked):
                raise ValueError('Frozen evaluation archive, state or isolation differs')
            row=dict(case=case['name'],completed=True,**episode_metrics(raw),actor_states=meter.count,
                guard_hit=bool(facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons']))
            results.append(row);write(run/'results.json',results);write(run/'attempts.json',collector.attempts)
            ledger.finish(row)
            write(run/'verification.json',dict(training_state_unchanged=True,all_points_completed=len(results)==4,
                checkpoint_sha256=B_PIN,forbidden_calls=calls))
            if ledger.state['status']!='healthy':return 20 if ledger.state['status']=='stopped' else 1
        ledger.complete()
        write(run/'completed.json',dict(status='evaluation_complete',success=sum(r['success'] for r in results),
            required_initial_success=4,retains_initial_success_count=all(r['success'] for r in results),
            b2_complete=False,developer_only=True,accounting=ledger.accounting()))
        return 0
    except BaseException as exc:
        cleanup=[]
        if collector is not None:
            try:
                if collector.active:collector._abort(exc)
                collector.retain_failure(exc)
            except BaseException as other:cleanup.append(repr(other))
        try:ledger.fail(repr(exc))
        except BaseException as other:cleanup.append(repr(other))
        write(run/'failure.json',dict(error=repr(exc),cleanup_errors=cleanup,forbidden_calls=calls,
            actor_states_observed_current=None if meter is None else meter.count,retry_allowed=False))
        raise
    finally:
        if collector is not None:write(run/'attempts.json',collector.attempts)
        write(run/'accounting.json',ledger.accounting())

def supervise(command):
    # Only the already bound process-lifetime helper is reused.
    source=ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/driver.py'
    spec=importlib.util.spec_from_file_location('frozen_B_supervisor',source)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper);helper.write=write
    return helper.supervise(command,HERE,ROOT)

def finalize_exception(binding_pin,auth_pin,exc):
    path=HERE/'process_exit.json';process=read(path) if path.exists() else {}
    uncertain=(HERE/'stop_requested.json').exists() or not process or (
        process.get('status')=='supervisor_error' and
        (process.get('worker_stopped') is not True or process.get('cleanup_error') is not None))
    if uncertain:
        write(HERE/'stop_requested.json',dict(error=repr(exc),worker_stop_confirmed=False))
    else:
        ledger_path=HERE/'run/ledger.json'
        if ledger_path.exists():
            ledger=Ledger.load(ledger_path,binding_pin,auth_pin);ledger.fail(repr(exc))
            write(HERE/'run/accounting.json',ledger.accounting())
    write(HERE/'exit_classification.json',dict(execution_complete=False,error=repr(exc),
        worker_stop_confirmed=not uncertain,ledger_preserved_pending_process_confirmation=uncertain,
        retry_allowed=False,b2_complete=False,process_exit=process))

def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--binding-sha256',required=True);p.add_argument('--authorization-sha256')
    mode=p.add_mutually_exclusive_group();mode.add_argument('--worker',action='store_true');mode.add_argument('--verify-only',action='store_true')
    args=p.parse_args(argv)
    if args.verify_only:
        verify_binding(args.binding_sha256);print('Frozen-B binding verified; no computation started.');return 0
    require_authorization(args.binding_sha256,args.authorization_sha256,folder=HERE)
    verify_binding(args.binding_sha256);select_runtime();verify_binding(args.binding_sha256,with_runtime=True)
    if args.worker:
        live_guard()()
        from tools.learning.sac_checkpoint import _flush_write
        _flush_write(HERE/'claim.json',json.dumps(dict(pid=os.getpid(),parent_pid=os.getppid(),wall_timestamp=time.time())))
        if os.name=='nt':
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0002)
        return worker(args.binding_sha256,args.authorization_sha256)
    os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
    command=[sys.executable,'-X','utf8','-X','faulthandler','-B',str(Path(__file__).resolve()),
        '--binding-sha256',args.binding_sha256,'--authorization-sha256',args.authorization_sha256,'--worker']
    try:
        code=supervise(command);ledger=Ledger.load(HERE/'run/ledger.json',args.binding_sha256,args.authorization_sha256)
        complete=code==0 and ledger.state['status']=='complete' and (HERE/'run/completed.json').exists()
        controlled=code==20 and ledger.state['status']=='stopped'
        if not complete and not controlled:raise RuntimeError('Evaluation worker failed: '+str(code))
        write(HERE/'exit_classification.json',dict(execution_complete=complete,controlled_stop=controlled,returncode=code,
            retry_allowed=False,b2_complete=False,accounting=ledger.accounting()))
        return code
    except FileExistsError:raise
    except BaseException as exc:
        finalize_exception(args.binding_sha256,args.authorization_sha256,exc);raise

if __name__=='__main__':raise SystemExit(main())
