"""Contact execution checks: fake physical sessions, NO optimizer updates."""
from copy import deepcopy
import gzip
import importlib
import json
import numpy as np
import pytest

from tests.learning.test_admitted_collection import Session


def api(): return importlib.import_module('tools.learning.contact_execution')


def make(tmp_path, monkeypatch, runtime):
    m = api()
    class Permit(m.ContactAdmission):
        def __init__(self):
            self.expected_digest = 'synthetic-permit'
            self.stale = False; self.checks = 0
            self._record = dict(config=m.contact_config(), capability='contact_four_point_execution')
        def verify(self, case=None):
            self.checks += 1
            if self.stale: raise ValueError('stale')
            if case is not None: m.validate_case(case)
            return deepcopy(self._record)
    import tools.learning.admitted_collection as base
    monkeypatch.setattr(base, '_new_session', lambda config: Session())
    monkeypatch.setattr(base, '_physical_audit', lambda s: dict(simulation_valid=s.env.guard_facts['simulation_valid'],
        task_outcome='TASK_FAILURE', physical_stopped=s.done, valid_for_learning=s.done,
        guard_violations=dict(contact=bool(s.env.guard_facts['contact_reasons']), motion=bool(s.env.guard_facts['motion_reasons']))))
    return m.ContactCollection(admission=Permit(), output=tmp_path / 'episodes')


def test_config_version_and_seed():
    m=api(); c=m.contact_config(); m.validate_config(c)
    assert c['execution']['preparation_only'] is False
    s=m.ContactSampler(c)
    assert [(v['x_offset_m'],v['y_offset_m']) for v in [s.next_case() for _ in range(6)]] == [m.POINTS[i] for i in [1,0,0,0,0,2]]
    with pytest.raises(RuntimeError): s.next_case()
    c['learning']['seed']+=1
    with pytest.raises(ValueError): m.validate_config(c)


def test_four_point_real_collector_publishes_valid_failure(tmp_path,monkeypatch,runtime):
    c=make(tmp_path,monkeypatch,runtime); c.start('one'); c.collect(10)
    assert c.budget.total==len(c.replay)==3
    assert c.collector.attempts[0]['case']['x_offset_m']==.0001
    assert c.collector.attempts[0]['status']=='published'
    assert c.admission.checks>=3


@pytest.mark.parametrize('fact', ['contact_reasons','motion_reasons','simulation_valid'])
def test_guard_or_invalid_never_publishes(tmp_path,monkeypatch,runtime,fact):
    c=make(tmp_path,monkeypatch,runtime); c.start('one')
    c.collector.session.env.guard_facts[fact]=False if fact=='simulation_valid' else ['injected']
    with pytest.raises(RuntimeError): c.collect(10)
    assert len(c.replay)==c.budget.total==0 and c.failed
    with pytest.raises(RuntimeError): c.update(1)
    with pytest.raises(RuntimeError): c.start('two')
    assert (c.collector.output/'one/episode.json.gz').exists()


def test_six_attempts_and_frozen_episode_policy(tmp_path,monkeypatch,runtime):
    c=make(tmp_path,monkeypatch,runtime)
    for i in range(6): c.start(f'e{i}'); c.collect(10)
    with pytest.raises(RuntimeError): c.start('seventh')
    assert len(c.collector.attempts)==6 and c.sampler.count==6


def test_update_blocked_mid_episode_without_calling_optimizer(tmp_path,monkeypatch,runtime):
    c=make(tmp_path,monkeypatch,runtime); c.start('one')
    with pytest.raises(RuntimeError): c.update(1)
    assert c.updater.counts['critic']==0


def test_stale_publication_retains_archive_and_locks(tmp_path,monkeypatch,runtime):
    c=make(tmp_path,monkeypatch,runtime); c.start('one'); c.admission.stale=True
    with pytest.raises(ValueError): c.collect(10)
    assert len(c.replay)==0 and c.failed
    assert (c.collector.output/'one/episode.json.gz').exists()
    c.admission.stale=False
    with pytest.raises(RuntimeError): c.retry_publication()


def test_changed_actor_is_rejected(tmp_path,monkeypatch,runtime):
    c=make(tmp_path,monkeypatch,runtime); c.start('one')
    import torch
    with torch.no_grad(): next(c.updater.policy.actor.parameters()).add_(1.)
    with pytest.raises(RuntimeError): c.collect(10)
    assert len(c.replay)==0 and c.failed


def test_checkpoint_roundtrip_without_optimizer_or_physics(tmp_path,monkeypatch,runtime):
    from tools.learning import sac_checkpoint as cp
    c=make(tmp_path,monkeypatch,runtime); c.start('one'); c.collect(10)
    monkeypatch.setattr(cp,'_audit_physics',lambda raw: None)
    p=tmp_path/'checkpoint'; sha=cp.save_checkpoint(c,p)
    d=cp.load_checkpoint(p,expected_digest=sha,admission=c.admission,output=tmp_path/'restored')
    assert cp._same(cp.capture(c),cp.capture(d))
    assert c.sampler.next_case()==d.sampler.next_case()
    assert np.array_equal(c.warmup.predict(np.zeros(120))[0],d.warmup.predict(np.zeros(120))[0])
    assert cp._same(vars(c.replay.sample(2,rng=c.replay_rng)),vars(d.replay.sample(2,rng=d.replay_rng)))


def test_preparation_record_cannot_authorize_execution():
    m=api()
    from tools.learning.runtime import ROOT
    from tools.learning.admission import digest
    p=ROOT/'deliverables/learning_chain/b2_contact_preparation_20260927/preparation.json'
    with pytest.raises(ValueError): m.ContactAdmission(p,expected_digest=digest(p))


@pytest.mark.parametrize('failure',['interrupt','archive','reset','unstopped'])
def test_failures_lock_and_keep_attempt(tmp_path,monkeypatch,runtime,failure):
    c=make(tmp_path,monkeypatch,runtime)
    import tools.learning.admitted_collection as base
    if failure=='reset':
        monkeypatch.setattr(base,'_new_session',lambda config: (_ for _ in ()).throw(ValueError('reset')))
        with pytest.raises(ValueError): c.start('one')
    else:
        c.start('one')
        if failure=='interrupt':
            monkeypatch.setattr(c.warmup,'predict',lambda *a,**k: (_ for _ in ()).throw(KeyboardInterrupt()))
        elif failure=='archive':
            monkeypatch.setattr(base,'_write_archive',lambda *a,**k: (_ for _ in ()).throw(OSError('disk')))
        else:
            monkeypatch.setattr(base,'_physical_audit',lambda s:dict(simulation_valid=True,physical_stopped=False,
                valid_for_learning=False,task_outcome='STOP_NOT_QUALIFIED',guard_violations=dict(contact=False,motion=False)))
        with pytest.raises(BaseException): c.collect(10)
    assert c.failed and c.sampler.count==1 and len(c.collector.attempts)==1 and len(c.replay)==0
    assert (c.collector.output/'failure.json').exists()
    with pytest.raises(RuntimeError): c.start('two')
    with pytest.raises(RuntimeError): c.update(1)


def test_evaluation_uses_four_points_without_training_state_change(tmp_path,monkeypatch,runtime):
    from tools.learning import contact_evaluation as ev
    from tools.learning import sac_checkpoint as cp
    c=make(tmp_path,monkeypatch,runtime); c.start('one'); c.collect(10)
    monkeypatch.setattr(ev,'episode_metrics',lambda raw:dict(success=False))
    before=cp.capture(c)
    results=ev.evaluate(c,checkpoint_sha256='a'*64,output=tmp_path/'evaluation')
    assert len(results)==4 and cp._same(before,cp.capture(c))
    attempts=json.loads((tmp_path/'evaluation/attempts.json').read_text())
    assert all(r['committed']==0 and r['training_admitted'] is False for r in attempts)


@pytest.mark.parametrize('change',[
    lambda s:s['sampler'].update(count=2),
    lambda s:s['attempts'][0].update(guard_clear=False),
    lambda s:s['budget'].update(total=33000),
    lambda s:s.update(version='sac_checkpoint_v1'),
    lambda s:s['rng'].update(warmup={'bit_generator':'MT19937'}),
])
def test_contact_checkpoint_rejects_corruption(tmp_path,monkeypatch,runtime,change):
    from tools.learning import sac_checkpoint as cp
    c=make(tmp_path,monkeypatch,runtime); c.start('one'); c.collect(10)
    monkeypatch.setattr(cp,'_audit_physics',lambda raw:None)
    s=cp.capture(c); change(s)
    with pytest.raises((ValueError,KeyError,TypeError)): cp.validate_state(s,c.admission)


def test_runner_six_attempt_cap_without_optimization(tmp_path,monkeypatch,runtime):
    from tools.learning import contact_training as runner
    from tools.learning import sac_checkpoint as cp
    c=make(tmp_path,monkeypatch,runtime)
    monkeypatch.setattr(cp,'_audit_physics',lambda raw:None)
    result=runner.run_training(c,tmp_path/'training')
    assert result['attempts']==6 and result['audited_total']==18
    assert not result['training_completed'] and result['stop_reason']=='six_attempt_limit'
    assert c.updater.counts['critic']==0


def test_explicit_case_override_is_not_a_training_path(tmp_path,monkeypatch,runtime):
    c=make(tmp_path,monkeypatch,runtime)
    with pytest.raises(ValueError): c.start('one',case={})
    assert c.sampler.count==0


@pytest.mark.parametrize('point',['audit','after_finalize'])
def test_seal_interrupt_retains_raw_episode_without_publication(tmp_path,monkeypatch,runtime,point):
    import tools.learning.admitted_collection as base
    c=make(tmp_path,monkeypatch,runtime);c.start('one')
    if point=='audit':
        monkeypatch.setattr(base,'_physical_audit',lambda s:(_ for _ in ()).throw(KeyboardInterrupt()))
    else:
        original=base._write_json
        def interrupted(path,value):
            if value.get('status')=='pending_publication':raise KeyboardInterrupt()
            return original(path,value)
        monkeypatch.setattr(base,'_write_json',interrupted)
    with pytest.raises(KeyboardInterrupt):c.collect(10)
    raw=json.loads(gzip.decompress((c.collector.output/'one/failure_episode.json.gz').read_bytes()))
    assert len(raw['transitions'])==3 and 'stop_samples' in raw and 'events' in raw
    assert raw['training_admitted'] is False and c.failed and len(c.replay)==0
    assert c.updater.counts['critic']==0


def test_resume_runner_keeps_consumed_attempts_and_handles_exhausted_limit(tmp_path,monkeypatch,runtime):
    from tools.learning import contact_training as runner
    from tools.learning import sac_checkpoint as cp
    c=make(tmp_path,monkeypatch,runtime);c.start('first');c.collect(10)
    monkeypatch.setattr(cp,'_audit_physics',lambda raw:None)
    path=tmp_path/'checkpoint';sha=cp.save_checkpoint(c,path)
    d=cp.load_checkpoint(path,expected_digest=sha,admission=c.admission,output=tmp_path/'resume_episodes')
    with pytest.raises(ValueError):runner.run_training(d,tmp_path/'fresh')
    result=runner.run_training(d,tmp_path/'resumed_training',resume=True)
    assert result['attempts']==6 and result['audited_total']==18
    assert d.collector.attempts[0]['episode_id']=='first'
    end=runner.run_training(d,tmp_path/'already_exhausted',resume=True)
    assert end['attempts']==6 and end['stop_reason']=='six_attempt_limit' and end['final_checkpoint']


def test_resume_consumes_credit_before_next_start(tmp_path,monkeypatch,runtime):
    from tools.learning import contact_training as runner
    from tools.learning import sac_checkpoint as cp
    c=make(tmp_path,monkeypatch,runtime);c.start('one');c.collect(10)
    monkeypatch.setattr(cp,'_audit_physics',lambda raw:None)
    # Budget/driver ordering only; optimizer is replaced with a sentinel, never run.
    c.budget.total=5004
    calls=[]
    def update(count):calls.append('update');c.budget.completed+=count;return []
    def start(identity):calls.append('start');raise RuntimeError('sentinel')
    monkeypatch.setattr(c,'update',update);monkeypatch.setattr(c,'start',start)
    monkeypatch.setattr(runner,'save_checkpoint',lambda *a:'a'*64)
    monkeypatch.setattr(runner,'validate_state',lambda *a:None)
    with pytest.raises(RuntimeError,match='sentinel'):runner.run_training(c,tmp_path/'resume',resume=True)
    assert calls==['update','start'] and c.updater.counts['critic']==0


@pytest.mark.parametrize('status',['running','updating_restored_boundary','failed'])
def test_cli_resume_refuses_rollback_of_inflight_or_failed_attempt(tmp_path,status):
    from tools.learning.contact_training import validate_resume_source
    path=tmp_path/'checkpoints/one';path.mkdir(parents=True)
    receipt=dict(path='checkpoints/one',sha256='a'*64)
    (tmp_path/'checkpoints.json').write_text(json.dumps([receipt]))
    (tmp_path/'run_state.json').write_text(json.dumps(dict(status=status,checkpoint=receipt)))
    with pytest.raises(ValueError):validate_resume_source(path,'a'*64)
    (tmp_path/'run_state.json').write_text(json.dumps(dict(status='healthy_boundary',checkpoint=receipt)))
    validate_resume_source(path,'a'*64)
    with pytest.raises(ValueError):validate_resume_source(path,'b'*64)


def test_evaluation_audit_interrupt_retains_diagnostic_raw(tmp_path,monkeypatch,runtime):
    from tools.learning import contact_evaluation as ev
    import tools.learning.admitted_collection as base
    c=make(tmp_path,monkeypatch,runtime);c.start('one');c.collect(10)
    monkeypatch.setattr(base,'_physical_audit',lambda s:(_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):ev.evaluate(c,checkpoint_sha256='a'*64,output=tmp_path/'evaluation')
    raw=json.loads(gzip.decompress((tmp_path/'evaluation/episodes/x_neg_100/failure_episode.json.gz').read_bytes()))
    assert len(raw['transitions'])==3 and raw['training_admitted'] is False
    assert len(c.replay)==3 and c.updater.counts['critic']==0


def test_cycle_upper_bound_is_enforced_before_publication(tmp_path,monkeypatch,runtime):
    c=make(tmp_path,monkeypatch,runtime);c.start('one');c.budget.total=32998
    with pytest.raises(RuntimeError):c.collect(10)
    assert len(c.replay)==0 and c.failed


def test_contact_updater_does_not_accept_old_or_changed_config():
    from tools.learning.admission import short_training_config
    with pytest.raises(ValueError):api().ContactUpdater(short_training_config())
    c=api().contact_config();c['execution']['preparation_only']=True
    with pytest.raises(ValueError):api().ContactUpdater(c)


def test_stale_start_cannot_initialize_physics(tmp_path,monkeypatch,runtime):
    c=make(tmp_path,monkeypatch,runtime);c.admission.stale=True
    import tools.learning.admitted_collection as base
    monkeypatch.setattr(base,'_new_session',lambda config:pytest.fail('Must not reset'))
    with pytest.raises(ValueError):c.start('one')
    assert c.failed and c.sampler.count==1 and c.collector.session is None
