"""Stage-local session factory and complete physical archives; no implicit replay."""
from copy import deepcopy
import importlib.util,re
import numpy as np
import paired_contract as C
from tools.learning.admitted_collection import AdmittedCollector,FormalEpisodeBuffer,_write_json,_write_archive,_vector
from tools.learning.audited_replay import AuditedReplay
from tools.learning.episode_buffer import _safe_error_archive
from tools.learning.contact_contract import guard_clear
from tools.learning.sac_checkpoint import _audit_physics,_same

def hold_type():
    p=C.HERE.with_name('b2_temporal_warmup_design_20261001')/'warmup_hold.py'
    s=importlib.util.spec_from_file_location('paired_warmup_hold',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m.WarmupHold

class Schedule:
    def __init__(self,identity):
        self.identity=deepcopy(identity)
        self.rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([C.scope()['seed'],1,identity['case_index']])))
        self.initial=deepcopy(self.rng.bit_generator.state);self.records=[]
        self.sampler=hold_type()(lambda:self.rng.uniform(-1.,1.,4).astype(np.float32),hold_cycles=50)
    def act(self,snapshot):
        r=self.sampler.next(snapshot.cycle_id,snapshot.controller_state['phase'],snapshot.residual_enabled)
        self.records.append(deepcopy(r));return np.asarray(r['action'],dtype=np.float32)
    def capture(self):return dict(identity=self.identity,rng_initial=self.initial,rng_final=deepcopy(self.rng.bit_generator.state),sampler=self.sampler.snapshot())

def audit_sampling(raw):
    from types import SimpleNamespace
    s=Schedule(raw['current_identity']);rows=raw['transitions']
    if len(rows)!=len(raw['sampling_records']):raise ValueError('Complete warmup transcript required')
    phases=('INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED')
    for i,(r,record) in enumerate(zip(rows,raw['sampling_records'])):
        phase=phases[r['observation'][53:58].index(1.)]
        action=s.act(SimpleNamespace(cycle_id=i,controller_state={'phase':phase},residual_enabled=r['action_active']))
        if C.canonical(s.records[-1])!=C.canonical(record) or action.tolist()!=r['action_log']['raw_action']:raise ValueError('Warmup request or RNG transcript differs')
    if C.canonical(s.capture())!=C.canonical(raw['sampling_final']):raise ValueError('Warmup final RNG differs')
    return dict(cycles=len(rows),active_cycles=s.sampler.active_cycles,draw_count=s.sampler.draw_count,model_forward=0)

class Permit:
    def __init__(self,ledger,mode):
        self.ledger=ledger;self.mode=mode;self.expected_digest=ledger.state['binding_sha256'];self.auth_pin=ledger.state['authorization_sha256']
    @property
    def config(self):return C.config(self.mode)
    def verify(self,case=None):
        self.ledger.check_live()
        if self.ledger.state['status']!='healthy':raise RuntimeError('Closed experiment')
        C.verify(self.expected_digest,self.auth_pin,with_runtime=True)
        i=self.ledger.state['active']
        if case is not None and (i is None or case!=C.attempts()[i]['case'] or (C.attempts()[i]['arm'] if C.attempts()[i]['arm']!='B2' else 'F')!=self.mode):raise ValueError('Reserved case/mode required')
        return dict(collection_admitted=True,current_training_authorization=True)

class Collector(AdmittedCollector):
    admission_type=Permit
    def __init__(self,*,admission,output,identity,updater=None):
        super().__init__(admission=admission,replay=AuditedReplay(capacity=13000),output=output)
        self.identity=deepcopy(identity);self.updater=updater
        self.schedule=Schedule(identity) if identity['stage']=='warmup' else None
    def start(self,episode_id,*,case,seed):
        if self.active or self._pending is not None or self._blocked:raise RuntimeError('Active or rejected collector')
        if episode_id!=self.identity['id'] or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}',episode_id):raise ValueError('Exact episode ID required')
        self._folder=self.output/episode_id;self._folder.mkdir(exist_ok=False);self._blocked=True
        self._record=dict(episode_id=episode_id,case=_safe_error_archive(case),seed=seed,qualification_sha256=self.admission.expected_digest,
            status='initializing',steps=0,committed=0,discarded=0,stage_mode=self.admission.mode)
        self.attempts.append(self._record);self.buffer=FormalEpisodeBuffer();self._fault_info=None;self.session=None
        self.before=None if self.updater is None else self.updater._snapshot()
        self.policy_sha=None if self.updater is None else self.updater.fingerprints()['actor']
        self.start_batches=0 if self.updater is None else self.updater.counts['critic']
        _write_json(self._folder/'status.json',self._record)
        try:
            if type(seed) is not int or seed!=C.scope()['seed'] or case!=self.identity['case']:raise ValueError('Exact reset scope required')
            self.admission.verify(case)
            from tools.validation.run_contact_cases import ContactCase
            from tools.learning.guarded_environment import GuardCandidateConfig,LearningEnvironment
            from stage_session import StageSession
            c=self.admission.config
            self.session=StageSession(environment=LearningEnvironment(guard_config=GuardCandidateConfig(**c['guard'])),mode=self.admission.mode,action_scale=c['action']['scale'])
            self._obs=_vector(self.session.reset(ContactCase(**case),seed=seed))
        except Exception as exc:
            self._record.update(status='rejected_before_reset',error=repr(exc));_write_json(self._folder/'status.json',self._record);raise
        self.active=True;self._blocked=False;self._record['status']='collecting';_write_json(self._folder/'status.json',self._record)
    def collect(self,policy,steps,*,cut_at_end=False,deterministic=False):
        if cut_at_end or type(policy) is not ContextPolicy or policy.collector is not self or deterministic!=(self.identity['stage']!='online'):raise ValueError('Registered complete policy mode required')
        return super().collect(policy,steps,deterministic=deterministic)
    def _stop_tail(self):
        self.fault_tail_transitions=[];self.session.start_external_tail()
        for _ in range(1500):
            if self.session.done:return
            self.admission.ledger.check_live()
            if self.session.cycle_id>=13000:raise RuntimeError('Safety tail cycle budget')
            before=self.session.prepare_cycle();result=self.session.advance_cycle([0.]*4)
            self.fault_tail_transitions.append(dict(cycle_id=before.cycle_id,trace_row=deepcopy(result.trace_row),action_log=deepcopy(result.action_log)))
        raise RuntimeError('Safety tail did not complete')
    def retry_publication(self):
        if self._status_pending:
            _write_json(self._folder/'status.json',self._record);self._status_pending=False
            self._blocked=not self._record['simulation_valid'] or not self._record['physical_stopped'];return
        if self._pending is None:raise RuntimeError('Pending archive required')
        raw=self._pending;stage=self.identity['stage'];training=stage in ('warmup','online')
        raw.update(current_identity=self.identity,stage_mode=self.admission.mode,training_admitted=training,
            evaluation_method='zero_b2' if stage=='b2' else 'sac',sampling_mode='uniform_hold' if stage=='warmup' else 'sac_policy',
            optimizer_steps_start=self.start_batches,optimizer_steps=self.start_batches,policy_sha256=self.policy_sha,
            fault_tail_transitions=deepcopy(getattr(self,'fault_tail_transitions',[])))
        raw['guard_clear']=guard_clear(raw)
        if self.schedule:raw.update(sampling_records=self.schedule.records,sampling_final=self.schedule.capture())
        # Persist before fallible qualification so no physical attempt can disappear.
        sha=_write_archive(self._folder/'episode.json.gz',raw)
        self.admission.verify(raw['case']);_audit_physics(raw)
        if raw['fault'] is not None:raise ValueError('Faulted physical archive retained')
        stamp=None
        if raw['guard_clear']:
            from stage_rules import StageRules
            stamp=StageRules(self.admission.mode).classify(raw)
            self.replay._prepare(raw['transitions'])
            if self.schedule:audit_sampling(raw)
        if self.updater is not None:
            if self.updater.counts!=self.before['counts'] or self.updater.fingerprints()['actor']!=self.policy_sha:raise ValueError('In-episode learning detected')
            if stage!='online' and not _same(self.before,self.updater._snapshot()):raise ValueError('Frozen evaluation modified learning state')
        self._record.update(committed=0,discarded=len(raw['transitions']),training_admitted=training,learning_eligibility=stamp,
            guard_clear=raw['guard_clear'],archive_sha256=sha,physical_stopped=raw['outcome']['physical_stopped'],
            simulation_valid=raw['outcome']['simulation_valid'],valid_for_learning=raw['outcome']['valid_for_learning'],
            task_outcome=raw['outcome']['task_outcome'],policy_sha256=self.policy_sha,optimizer_steps=self.start_batches,status='audited_archived')
        self._pending=None;self._status_pending=True;self.session=None;self.buffer=None;self.retry_publication()

class ContextPolicy:
    def __init__(self,collector,meter):self.collector=collector;self.meter=meter
    def predict(self,observation,deterministic=False):
        c=self.collector;c.admission.ledger.check_live();snap=c.session.prepare_cycle()
        if c.session.cycle_id>=13000 or not np.array_equal(np.asarray(snap.policy_observation,dtype=np.float32),observation):raise ValueError('Current physical policy snapshot required')
        if c.identity['stage']=='b2':return np.zeros(4,dtype=np.float32),None
        if c.schedule:return c.schedule.act(snap),None
        if deterministic!=(c.identity['stage']!='online'):raise ValueError('Wrong policy mode')
        facts=c.session.env.guard_facts
        if facts['contact_reasons'] or facts['motion_reasons'] or facts['invalid_reasons']:return np.zeros(4,dtype=np.float32),None
        self.meter.begin_control()
        try:return c.updater.predict(observation,deterministic=deterministic)
        finally:self.meter.end_context()
