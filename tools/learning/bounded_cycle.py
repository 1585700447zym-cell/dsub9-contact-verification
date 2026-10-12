"""Finite experiment runner; all starts are durable before touching physics."""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import subprocess
import sys
import time
from .admitted_collection import _write_json
from .bounded_contact import (BoundedCollector,BoundedCollection,BoundedAdmission,RunLedger,
    DELIVERY,ROOT,SEED,POINTS,HOLDOUT,case_at,guard_clear,ForceFailureStop)
from .engineering_evaluation import EvaluationCollector,FrozenPolicy,ZeroPolicy,episode_metrics
from .audited_replay import AuditedReplay
from . import bounded_checkpoint as cp
from .sac_checkpoint import _same
from .admission import digest

STAGES=('initial','training','final','restored','holdout_b2','holdout_sac')


def require_stage(ledger,stage):
    if stage not in STAGES: raise ValueError('Unknown stage')
    for earlier in STAGES[:STAGES.index(stage)]:
        rows=[r for r in ledger.state['attempts'] if r['stage']==earlier]
        if len(rows)!=ledger.CAPS[earlier] or any(r['status']!='finished' for r in rows):
            raise RuntimeError('Prior stage incomplete: '+earlier)


def compare_success(before,after):
    a={r['case']:r['success'] for r in before};b={r['case']:r['success'] for r in after}
    if a.keys()!=b.keys():raise ValueError('Unpaired comparison')
    gained=[k for k in a if not a[k] and b[k]];lost=[k for k in a if a[k] and not b[k]]
    return dict(before=sum(a.values()),after=sum(b.values()),gained=gained,lost=lost,
                improved_without_regression=bool(gained) and not lost)


def same_physical_result(a,b):
    keys=('transitions','outcome','stop_samples','events','stop_time','audit_end_time_s','guard_facts')
    return all(_same(a[k],b[k]) for k in keys)


def validate_holdout_evidence(evidence):
    if [r['case'] for r in evidence]!=[c['name'] for c in cases(True)]:
        raise ValueError('Missing, duplicated or unregistered holdout cases')
    for r in evidence:
        if (type(r['contact_cycles']) is not int or r['contact_cycles']<=0 or
            any(r[k] is not True for k in ('guard_clear','physical_stopped','simulation_valid'))):
            raise ValueError('New scope lacks contact or safe dynamic evidence')


def holdout_scope_gate(run,admission):
    evidence=[];bindings={}
    for case in cases(True):
        path=run/'holdout_b2/episodes'/case['name']/'episode.json.gz'
        raw=json.loads(gzip.decompress(path.read_bytes()))
        if raw['case']!=case or raw['evaluation_method']!='zero_b2':raise ValueError('Holdout baseline identity mismatch')
        cp._audit_physics(raw)
        evidence.append(dict(case=case['name'],guard_clear=guard_clear(raw),
            physical_stopped=raw['outcome']['physical_stopped'],simulation_valid=raw['outcome']['simulation_valid'],
            contact_cycles=sum(r['trace_row']['contact_count']>0 for r in raw['transitions'])))
        bindings[path.relative_to(ROOT).as_posix()]=digest(path)
    validate_holdout_evidence(evidence);admission.verify()
    _write_json(run/'holdout_scope_gate.json',dict(passed=True,evidence=evidence,archives=bindings,
        qualification_sha256=admission.expected_digest,frozen_checkpoint_sha256=digest(run/'frozen.json')))


class BoundedEvaluationCollector(BoundedCollector):
    def __init__(self,*,admission,output,updater,method,checkpoint_sha256):
        self.method=method;self.checkpoint_sha256=checkpoint_sha256
        super().__init__(admission=admission,output=output,updater=updater,replay=AuditedReplay(capacity=156000))
    def start(self,episode_id,*,case,seed):
        self.sampling_mode='deterministic_evaluation'
        super().start(episode_id,case=case,seed=seed);self._start_count=deepcopy(self.updater.counts)
    def retry_publication(self):
        if self._pending is not None:
            from .episode_rules import rules_for, STRICT, stamp_pending
            rules=rules_for(self.admission)
            if rules is STRICT:
                self._pending['guard_clear']=guard_clear(self._pending)
            else:
                self._pending.update(evaluation_method=self.method,
                    optimizer_steps_start=self._start_count['critic'],optimizer_steps=self.updater.counts['critic'])
                stamp_pending(self._pending,self._record,rules)
        return EvaluationCollector.retry_publication(self)


def cases(holdout=False):
    suffix='95' if holdout else '100'
    return [case_at(name+'_'+suffix,*point) for name,point in
            zip(('x_pos','x_neg','y_pos','y_neg'),HOLDOUT if holdout else POINTS)]


def progress(path,**values):
    values['wall_timestamp']=time.time();_write_json(path,values)


def evaluate(chain,stage,*,ledger,output,checkpoint_sha256):
    require_stage(ledger,stage);before=cp.capture(chain)
    if stage=='holdout_sac':
        gate=json.loads((Path(output).parent/'holdout_scope_gate.json').read_text(encoding='utf-8'))
        from .admission import verify_files
        if (gate.get('passed') is not True or gate['qualification_sha256']!=chain.admission.expected_digest or
            gate['frozen_checkpoint_sha256']!=digest(Path(output).parent/'frozen.json')):
            raise ValueError('New scope gate is stale')
        validate_holdout_evidence(gate['evidence']);verify_files(ROOT,gate['archives'])
    output=Path(output);output.mkdir(exist_ok=False)
    method='zero_b2' if stage=='holdout_b2' else 'sac'
    collector=BoundedEvaluationCollector(admission=chain.admission,output=output/'episodes',
        updater=chain.updater,method=method,checkpoint_sha256=checkpoint_sha256)
    results=[];started=time.perf_counter()
    try:
        for case in cases(stage.startswith('holdout')):
            ledger.start(stage,case['name']);progress(output.parent/'progress.json',stage=stage,case=case['name'],cycles=0)
            collector.start(case['name'],case=case,seed=SEED)
            policy=ZeroPolicy() if method=='zero_b2' else FrozenPolicy(chain.updater)
            while collector.active:
                collector.collect(policy,500,deterministic=True)
                progress(output.parent/'progress.json',stage=stage,case=case['name'],cycles=collector._record['steps'])
            raw=json.loads(gzip.decompress((collector.output/case['name']/'episode.json.gz').read_bytes()))
            from .episode_rules import rules_for
            accepted=guard_clear(raw) if method=='zero_b2' else rules_for(chain.admission).accepts(raw)
            if collector._blocked or not accepted or len(collector.replay):raise RuntimeError('Evaluation audit failed')
            cp._audit_physics(raw)
            row=dict(case=case['name'],**episode_metrics(raw));results.append(row)
            _write_json(output/'results.json',results);ledger.finish(row)
            print(json.dumps(dict(stage=stage,**row),ensure_ascii=False),flush=True)
        if not _same(before,cp.capture(chain)):raise RuntimeError('Evaluation changed learning state')
        _write_json(output/'verification.json',dict(training_state_unchanged=True,wall_s=time.perf_counter()-started))
        return results
    except BaseException as exc:
        if collector.active:collector._abort(exc)
        collector.retain_failure(exc);ledger.fail(repr(exc))
        _write_json(output/'failure.json',dict(error=repr(exc),attempts=collector.attempts));raise
    finally:_write_json(output/'attempts.json',collector.attempts)


def train(chain,*,ledger,output):
    require_stage(ledger,'training');output=Path(output);output.mkdir(exist_ok=False)
    checkpoints=[];started=time.perf_counter()
    try:
        for i in range(12):
            identity=f'train_{i:02d}';ledger.start('training',identity);chain.start(identity)
            while chain.collector.active:
                chain.collect(500)
                progress(output.parent/'progress.json',stage='training',episode=i+1,
                    cycles=chain.collector._record['steps'],updates=chain.updater.counts['critic'])
            raw=json.loads(gzip.decompress((chain.collector.output/identity/'episode.json.gz').read_bytes()))
            metric=episode_metrics(raw);ledger.finish(metric)
            if chain.budget.available:chain.update(500)
            if chain.budget.available:raise RuntimeError('Unconsumed update credit')
            path=output/'checkpoints'/identity;pin=cp.save_checkpoint(chain,path)
            checkpoints.append(dict(path=path.relative_to(output.parent).as_posix(),sha256=pin,
                                    episodes=i+1,updates=chain.updater.counts['critic']))
            _write_json(output/'checkpoints.json',checkpoints);_write_json(output/'updates.json',chain.history)
            print(json.dumps(dict(stage='training',episode=i+1,updates=chain.updater.counts['critic'],**metric)),flush=True)
        result=dict(episodes=12,updates=chain.updater.counts,wall_s=time.perf_counter()-started,
            update_wall_s=sum(r['wall_s'] for r in chain.history),audited_transitions=len(chain.replay),final=checkpoints[-1])
        _write_json(output/'result.json',result);return checkpoints[-1]
    except ForceFailureStop as exc:
        raw=json.loads(gzip.decompress((chain.collector.output/exc.episode_id/'episode.json.gz').read_bytes()))
        ledger.finish(episode_metrics(raw));ledger.stop(exc);chain.fail(exc)
        _write_json(output/'controlled_stop.json',dict(**exc.record(),checkpoints=checkpoints))
        progress(output.parent/'progress.json',stage='stopped',**exc.record())
        raise
    except BaseException as exc:
        chain.fail(exc);ledger.fail(repr(exc));_write_json(output/'failure.json',dict(error=repr(exc),checkpoints=checkpoints));raise
    finally:
        _write_json(output/'attempts.json',chain.collector.attempts);_write_json(output/'updates.json',chain.history)


def summarize_development(run):
    read=lambda path:json.loads(path.read_text(encoding='utf-8'))
    initial=read(run/'initial/results.json');final=read(run/'final/results.json')
    historical=read(ROOT/'deliverables/learning_chain/b2_contact_short_train_20260927/assessment.json')
    baseline=[dict(case=r['point'],success=r['zero_b2']['success']) for r in historical['paired_development']]
    result=dict(learning=compare_success(initial,final),baseline=compare_success(baseline,final),
                developer_only=True,independent_evaluation_pending=True)
    _write_json(run/'development_decision.json',result)
    if not result['baseline']['improved_without_regression']:
        _write_json(run/'notification.json',dict(kind='development_benefit_requirement_not_met',result=result,
            next='Complete registered restoration and independent evaluation; do not add training.'))
    return result


def execute(admission,*,restore_only=False):
    run=DELIVERY/'run'
    if restore_only:
        frozen=json.loads((run/'frozen.json').read_text(encoding='utf-8'))
        chain=cp.load_checkpoint(run/frozen['path'],expected_digest=frozen['sha256'],admission=admission,output=run/'restored_training_state')
        ledger=RunLedger(run/'ledger.json')
        evaluate(chain,'restored',ledger=ledger,output=run/'restored',checkpoint_sha256=frozen['sha256'])
        for case in cases():
            a=json.loads(gzip.decompress((run/'final/episodes'/case['name']/'episode.json.gz').read_bytes()))
            b=json.loads(gzip.decompress((run/'restored/episodes'/case['name']/'episode.json.gz').read_bytes()))
            if not same_physical_result(a,b):raise RuntimeError('Restored physical trajectory differs')
        _write_json(run/'restoration.json',dict(exact_physical_replay=True,independent_performance_samples_added=0));return
    run.mkdir(exist_ok=False);ledger=RunLedger(run/'ledger.json');chain=None
    try:
        chain=BoundedCollection(admission=admission,output=run/'training_episodes')
        initial_pin=cp.save_checkpoint(chain,run/'initial_checkpoint')
        evaluate(chain,'initial',ledger=ledger,output=run/'initial',checkpoint_sha256=initial_pin)
        final=train(chain,ledger=ledger,output=run/'training')
        _write_json(run/'frozen.json',final)
        evaluate(chain,'final',ledger=ledger,output=run/'final',checkpoint_sha256=final['sha256'])
        print(json.dumps(dict(stage='development_decision',**summarize_development(run))),flush=True)
        cmd=[sys.executable,'-X','utf8','-B','-m','tools.validation.run_bounded_contact_cycle',
             '--admission-sha256',admission.expected_digest,'--restore-evaluate']
        with (run/'restore_process.log').open('w',encoding='utf-8') as stream:
            result=subprocess.run(cmd,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        ledger=RunLedger(run/'ledger.json')
        if result.returncode:raise RuntimeError('Separate restoration process failed')
        evaluate(chain,'holdout_b2',ledger=ledger,output=run/'holdout_b2',checkpoint_sha256=final['sha256'])
        holdout_scope_gate(run,admission)
        evaluate(chain,'holdout_sac',ledger=ledger,output=run/'holdout_sac',checkpoint_sha256=final['sha256'])
        independent=compare_success(json.loads((run/'holdout_b2/results.json').read_text(encoding='utf-8')),
                                    json.loads((run/'holdout_sac/results.json').read_text(encoding='utf-8')))
        _write_json(run/'completed.json',dict(status='execution_complete',dynamic_starts=ledger.state['dynamic_starts'],
            formal_updates=chain.updater.counts,independent=independent,checkpoint=final))
        progress(run/'progress.json',stage='completed',independent=independent)
    except ForceFailureStop as exc:
        _write_json(run/'controlled_stop.json',dict(**exc.record(),ledger=ledger.state))
        progress(run/'progress.json',stage='stopped',**exc.record());raise
    except BaseException as exc:
        if chain is not None:chain.fail(exc)
        ledger.fail(repr(exc));_write_json(run/'failure.json',dict(error=repr(exc),ledger=ledger.state))
        progress(run/'progress.json',stage='failed',error=repr(exc));raise
