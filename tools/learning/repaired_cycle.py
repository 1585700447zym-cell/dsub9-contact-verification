"""Explicit repaired-runtime admission and authorized finite continuation."""
from copy import deepcopy
import gzip
import io
import json
from pathlib import Path
import time
import torch
from .runtime import ROOT, select_runtime, active_package
from .admission import canonical, digest, verify_files
from .admitted_collection import _write_json
from .bounded_contact import BoundedAdmission, RunLedger, bounded_config, current_sources, validate_case, SEED, guard_clear
from . import bounded_checkpoint as cp
from .sac_checkpoint import _same

DELIVERY = ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928'
PREVIOUS = ROOT/'deliverables/learning_chain/b2_repaired_cycle_20260928'
OLD = ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927'
REPAIR = ROOT/'deliverables/learning_chain/b2_native_crash_20260928'
PARENT_PIN = '1df0c0919e998e281dc910d314c54114efe521b7248922fc2733290c242994a9'
INITIAL_PIN = 'e5a7524a128124cd33b414dbfd0ae62a5d8e5a7947ed5bde18dfd07f261605d7'
REPAIR_PIN = 'b3a4b0fa1d05fbb1398f512316e73f47d1edf715c2cac04d85f8f33d98e972f1'
RETRY_BINDING_PIN = '282f4b57ab5e479ac42bde4b41529bcd238e01868bdaec4b2cbaff929de8aa73'
PREVIOUS_FILES_PIN = 'd6a34d09e02a56f327a3d7d2deb8549692f61d97b6b7b6acdbc151f5947de5a2'


def read(path): return json.loads(Path(path).read_text(encoding='utf-8'))


def pinned_manifest(path,pin):
    if digest(path)!=pin:raise ValueError('Manifest pin changed: '+str(path))
    return read(path)


def require_learning_runtime_unchanged(parent,current):
    if canonical({k:v for k,v in parent.items() if k!='native'}) != canonical({k:v for k,v in current.items() if k!='native'}):
        raise ValueError('Repair cannot requalify changed learning dependencies')


def require_complete_tests(actual,expected):
    if not expected or len(set(expected))!=len(expected) or sorted(actual)!=sorted(expected):
        raise ValueError('Missing, duplicated or unregistered qualification tests')


def verify_parent():
    if digest(OLD/'admission.json') != PARENT_PIN:
        raise ValueError('Parent admission changed')
    snapshots = {f'tools/learning/{name}.py':f'source_snapshot/{name}.py' for name in ('runtime','environment','session')}
    parent = read(OLD/'admission.json')
    # The trusted parent pins the evidence inventories themselves, not only their entries.
    verify_files(ROOT,parent['evidence_sha256'])
    for name, expected in parent['source_sha256'].items():
        path = DELIVERY/snapshots[name] if name in snapshots else ROOT/name
        if digest(path) != expected: raise ValueError('Parent source changed: '+name)
    verify_files(ROOT, read(OLD/'historical_files.json'))
    verify_files(ROOT, pinned_manifest(OLD/'retry_01/binding.json',RETRY_BINDING_PIN)['files'])
    verify_files(REPAIR, pinned_manifest(REPAIR/'manifest.json',REPAIR_PIN)['files'])
    verify_files(ROOT,pinned_manifest(DELIVERY/'previous_failure_files.json',PREVIOUS_FILES_PIN))
    prior_sources = read(PREVIOUS/'admission.json')['source_sha256']
    prior_snapshots = {'tools/learning/session.py':'source_snapshot/session.py',
        'tools/learning/repaired_cycle.py':'prior_execution_sources/repaired_cycle.py',
        'tests/learning/test_repaired_cycle.py':'prior_execution_sources/test_repaired_cycle.py',
        'tests/learning/test_repaired_runtime.py':'prior_execution_sources/test_repaired_runtime.py'}
    for name,expected in prior_sources.items():
        path=DELIVERY/prior_snapshots[name] if name in prior_snapshots else ROOT/name
        if digest(path)!=expected:raise ValueError('Prior failed execution source changed: '+name)
    return parent


class RepairedAdmission(BoundedAdmission):
    def verify(self, case=None):
        if self.path.resolve() != (DELIVERY/'admission.json').resolve() or digest(self.path) != self.expected_digest:
            raise ValueError('Repaired admission pin/path changed')
        record = read(self.path)
        if (record.get('capability') != 'repaired_bounded_contact_cycle_v1' or
            record.get('parent_admission_sha256') != PARENT_PIN or
            any(record.get(k) is not True for k in ('collection_admitted','update_admitted','restore_admitted')) or
            canonical(record['config']) != canonical(bounded_config())):
            raise ValueError('Invalid repaired execution qualification')
        parent=verify_parent()
        if record['source_sha256'] != current_sources(): raise ValueError('Repaired source changed')
        verify_files(ROOT, record['evidence_sha256'])
        select_runtime(DELIVERY/'runtime.json',expected_digest=record['runtime_record_sha256'])
        from tools.validation.verify_residual_interface import qualified_runtime
        current_runtime=qualified_runtime(active_package())
        require_learning_runtime_unchanged(parent['runtime'],current_runtime)
        if canonical(current_runtime) != canonical(record['runtime']):
            raise ValueError('Runtime or CPU learning dependencies changed')
        if case is not None: validate_case(case)
        self._record = record
        return deepcopy(record)


def accounting(state):
    n = state['dynamic_starts']
    if type(n) is not int or not 0 <= n <= 36 or len(state['attempts']) != n:
        raise ValueError('Invalid repaired cumulative budget')
    return dict(previous_training_and_retry_starts=6,previous_diagnostic_starts=2,
        previous_rejected_setup_starts=1,new_dynamic_starts=n,cumulative_dynamic_starts=9+n,cumulative_cap=45,
        new_dynamic_cap=36,formal_update_cap=4500,automatic_retry=False)


class RepairedLedger(RunLedger):
    CAPS = dict(baseline=4, **RunLedger.CAPS)

    def start(self,stage,identity):
        s = self.state; accounting(s)
        if s['status'] != 'healthy' or s['active'] is not None or stage not in self.CAPS:
            raise RuntimeError('Unhealthy repaired run or unknown stage')
        for earlier in list(self.CAPS)[:list(self.CAPS).index(stage)]:
            rows = [r for r in s['attempts'] if r['stage']==earlier]
            if len(rows)!=self.CAPS[earlier] or any(r['status']!='finished' for r in rows):
                raise RuntimeError('Prior repaired stage incomplete: '+earlier)
        if (s['dynamic_starts']>=36 or sum(r['stage']==stage for r in s['attempts'])>=self.CAPS[stage] or
            any(r['stage']==stage and r['id']==identity for r in s['attempts'])):
            raise RuntimeError('Repaired start budget exhausted or duplicate')
        s['attempts'].append(dict(stage=stage,id=identity,status='started'))
        s.update(dynamic_starts=s['dynamic_starts']+1,active=len(s['attempts'])-1)
        _write_json(self.path,s)
        _write_json(self.path.parent/'cumulative_budget.json',accounting(s))


def compare_initial_states(before, after):
    for state in (before,after):
        if (any(state['updater']['counts'].values()) or state['budget']['total'] or state['budget']['completed'] or
            state['sampler_count'] or state['update_attempts'] or state['archives'] or state['attempts'] or state['history']):
            raise ValueError('Initial learning state is not empty')
    if not _same({k:v for k,v in before.items() if k!='binding'},
                 {k:v for k,v in after.items() if k!='binding'}):
        raise ValueError('Initial learning state changed beyond qualification binding')


def verify_initial_chain(chain):
    path=OLD/'run/initial_checkpoint'
    if digest(path/'manifest.json')!=INITIAL_PIN: raise ValueError('Old initial pin changed')
    payload=(path/'state.pt').read_bytes()
    if digest(path/'state.pt')!=read(path/'manifest.json')['state_sha256']:
        raise ValueError('Old initial state changed')
    old=torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)
    if old['binding']['qualification_sha256']!=PARENT_PIN or not _same(old['binding']['record'],read(OLD/'admission.json')):
        raise ValueError('Old initial qualification differs')
    compare_initial_states(old,cp.capture(chain))
    return dict(initial_state_exact_except_binding=True,old_initial_manifest_sha256=INITIAL_PIN,
                optimizer_calls=0,physical_starts=0)


def evaluate_baseline(chain,*,ledger,output,checkpoint_sha256):
    from .bounded_cycle import BoundedEvaluationCollector,cases,progress
    from .engineering_evaluation import ZeroPolicy,episode_metrics
    before=cp.capture(chain);output=Path(output);output.mkdir(exist_ok=False)
    collector=BoundedEvaluationCollector(admission=chain.admission,output=output/'episodes',
        updater=chain.updater,method='zero_b2',checkpoint_sha256=checkpoint_sha256)
    rows=[];start=time.perf_counter()
    try:
        for case in cases():
            ledger.start('baseline',case['name'])
            progress(output.parent/'progress.json',stage='baseline',case=case['name'],cycles=0)
            collector.start(case['name'],case=case,seed=SEED)
            while collector.active:
                collector.collect(ZeroPolicy(),500,deterministic=True)
                progress(output.parent/'progress.json',stage='baseline',case=case['name'],cycles=collector._record['steps'])
            raw=json.loads(gzip.decompress((collector.output/case['name']/'episode.json.gz').read_bytes()))
            if collector._blocked or not guard_clear(raw) or len(collector.replay):
                raise RuntimeError('Repaired baseline audit failed')
            cp._audit_physics(raw)
            row=dict(case=case['name'],**episode_metrics(raw));rows.append(row);ledger.finish(row)
            _write_json(output/'results.json',rows)
            print(json.dumps(dict(stage='baseline',**row),ensure_ascii=False),flush=True)
        if not _same(before,cp.capture(chain)): raise RuntimeError('Baseline changed learning state')
        _write_json(output/'verification.json',dict(training_state_unchanged=True,wall_s=time.perf_counter()-start))
    except BaseException as exc:
        if collector.active:collector._abort(exc)
        collector.retain_failure(exc);ledger.fail(repr(exc));raise
    finally: _write_json(output/'attempts.json',collector.attempts)


def development_decision(run):
    from .bounded_cycle import compare_success
    result=dict(learning=compare_success(read(run/'initial/results.json'),read(run/'final/results.json')),
        baseline=compare_success(read(run/'baseline/results.json'),read(run/'final/results.json')),
        same_runtime=True,independent_evaluation_pending=True)
    _write_json(run/'development_decision.json',result)
    if not result['baseline']['improved_without_regression']:
        _write_json(run/'notification.json',dict(kind='development_benefit_requirement_not_met',result=result))
    return result
