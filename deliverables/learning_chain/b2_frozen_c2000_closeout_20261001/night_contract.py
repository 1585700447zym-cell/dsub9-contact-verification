"""Bounded frozen deployment screening; no learning authority."""
from copy import deepcopy
import hashlib,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
PARENT=HERE.with_name('b2_temporal_learning_restart_20261001')
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(PARENT))
import validation_contract as P
PARENT_SEAL='1f86e9ece11d5244401470cf1c684a689a7e590169b3b22073dc2ade1a77fb59'
CHECKPOINT=PARENT/'run/checkpoint_C_2000'
CHECKPOINT_PIN='3f7a9097e191eb0a0a016141916ee31e8b1c551188d61b8157e0530960819aa6'
ACTOR_PIN='6bc46f2c058ac49fb057a789065cffd16a956da7191d8860eeb92d38ea9ebeda'
read=P.read;digest=P.digest;canonical=P.canonical;write=P.write

def scope():
    return dict(previous_dynamic=80,dynamic_cap=10,variant_dynamic_cap=5,cumulative_dynamic_cap=90,
        cycles_per_start=13000,actor_state_cap=130000,module_call_cap=4160000,physical_substep_cap=1300000,
        training_batches=0,critic_diagnostic_states=0,independent_test=0,old_unused_consumed=0,
        stop_on_any_guard_per_variant=True,automatic_retry=False,automatic_tracking=False,
        checkpoint_manifest_sha256=CHECKPOINT_PIN,parent_delivery_sha256=PARENT_SEAL,
        variants=['base','small'],small_xy_scale=.00005)

def config(variant):
    if variant not in ('base','small'):raise ValueError('Registered deployment required')
    c=P.config('C')
    if variant=='small':c['action']['scale']=[.00005,.00005,.0005,.0005]
    return c

def identities():return P.cases()+[P.cases()[0]]

def verify_parent():
    seal=PARENT/'result_analysis/delivery_verification.json'
    if digest(seal)!=PARENT_SEAL:raise ValueError('Parent delivery changed')
    d=read(seal);P.verify_files(d['sha256'])
    pins=read(PARENT/'execution_pins.json');P.require_authorization(pins['binding_sha256'],pins['authorization_sha256']);P.verify_binding(pins['binding_sha256'])
    a=read(PARENT/'result_analysis/assessment.json');P.verify_files(a['result_input_sha256'])
    m=read(CHECKPOINT/'manifest.json')
    verified=next(x for x in a['checkpoints'] if x['manifest_sha256']==CHECKPOINT_PIN)
    if digest(CHECKPOINT/'manifest.json')!=CHECKPOINT_PIN or digest(CHECKPOINT/'state.pt')!=m['state_sha256'] or m['batches']!=2000 or verified['actor_sha256']!=ACTOR_PIN or not verified['complete_state_verified']:
        raise ValueError('Wrong source state or full audit')
    if a['accounting']['cumulative_dynamic']!=80 or a['status']!='stopped':raise ValueError('Source accounting differs')
    return m

def validate_authority(record,binding_pin):
    P.pin(binding_pin)
    if record.get('approved') is not True or record.get('version')!='frozen_c2000_night_authority_v1' or record.get('binding_sha256')!=binding_pin or record.get('scope')!=scope() or not record.get('user_confirmation'):
        raise ValueError('Current delegated authority required')

def verify(binding_pin,auth_pin,variant):
    P.pin(binding_pin);P.pin(auth_pin);config(variant)
    if digest(HERE/'binding.json')!=binding_pin or digest(HERE/'authorization.json')!=auth_pin:raise ValueError('Authority digest differs')
    b=read(HERE/'binding.json');validate_authority(read(HERE/'authorization.json'),binding_pin)
    if b['scope']!=scope() or b['configs']!={k:config(k) for k in ('base','small')} or not b['protocol_passed']:raise ValueError('Unregistered scope/configuration')
    P.verify_files(b['inputs_sha256']);verify_parent()
    if variant=='small':
        gate=read(HERE/'small_gate.json');a=read(HERE/'base/assessment.json')
        if gate['base_assessment_sha256']!=digest(HERE/'base/assessment.json') or not small_allowed(a):raise ValueError('Conditional small deployment gate refused')
    return b

def small_allowed(a):
    return bool(not a.get('operational_fault',True) and a.get('ordinary_or_guard_failures',0)>0 and
        (a.get('status')=='stopped' or (a.get('status')=='complete' and a.get('restore_ok') is True)))

def validate_result(r):
    if (not isinstance(r,dict) or r.get('completed') is not True or
        any(type(r.get(k)) is not bool for k in ('success','simulation_valid','physical_stopped','guard_hit')) or
        type(r.get('cycles')) is not int or not 0<r['cycles']<=13000 or
        type(r.get('actor_states')) is not int or r['actor_states']!=r['cycles'] or
        r.get('physical_substeps')!=10*r['cycles'] or
        (r['success'] and (r['guard_hit'] or not r['simulation_valid'] or not r['physical_stopped']))):raise ValueError('Complete physical result required')
    json.dumps(r,allow_nan=False)

class Ledger:
    def __init__(self,path,state):
        self.path=Path(path);self.state=deepcopy(state);self.live_guard=None;self.write_failed=False;self.validate()
    @classmethod
    def create(cls,path,binding_pin,auth_pin,variant):
        P.pin(binding_pin);P.pin(auth_pin);config(variant)
        s=dict(version='frozen_c2000_night_ledger_v1',binding_sha256=binding_pin,authorization_sha256=auth_pin,variant=variant,
            scope=scope(),status='healthy',active=None,attempts=[])
        with Path(path).open('x',encoding='utf-8') as f:json.dump(s,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        return cls(path,s)
    @classmethod
    def load(cls,path,binding_pin,auth_pin,variant):
        s=read(path)
        if s['binding_sha256']!=binding_pin or s['authorization_sha256']!=auth_pin or s['variant']!=variant:raise ValueError('Ledger identity differs')
        return cls(path,s)
    def validate(self):
        s=self.state;config(s['variant']);P.pin(s['binding_sha256']);P.pin(s['authorization_sha256'])
        if s['version']!='frozen_c2000_night_ledger_v1' or s['scope']!=scope() or s['status'] not in ('healthy','await_restore','stopped','failed','complete') or not isinstance(s['attempts'],list) or len(s['attempts'])>5:raise ValueError('Ledger scope/state differs')
        active=[];terminal=[]
        for i,a in enumerate(s['attempts']):
            if a.get('index')!=i or a.get('case')!=identities()[i] or a.get('reserved_cycles')!=13000 or a.get('status') not in ('started','finished','failed'):raise ValueError('Unregistered attempt')
            if a['status']=='started':active.append(i)
            elif a['status']=='failed':terminal.append(i)
            else:
                validate_result(a['result'])
                if a['result']['guard_hit'] or not a['result']['simulation_valid'] or not a['result']['physical_stopped']:terminal.append(i)
        if active!=([s['active']] if s['active'] is not None else []) or (active and active!=[len(s['attempts'])-1]):raise ValueError('Active reservation differs')
        if terminal and (terminal!=[len(s['attempts'])-1] or s['status'] not in ('stopped','failed')):raise ValueError('Computation after terminal result')
        if s['status'] not in ('healthy',) and active:raise ValueError('Closed ledger active')
        if s['status']=='stopped' and (not terminal or not s['attempts'][-1].get('result',{}).get('guard_hit') or not s['attempts'][-1]['result']['simulation_valid'] or not s['attempts'][-1]['result']['physical_stopped']):raise ValueError('Invalid controlled stop')
        if s['status']=='await_restore' and (len(s['attempts'])!=4 or terminal or active):raise ValueError('Wrong restoration boundary')
        if s['status']=='complete' and (len(s['attempts'])!=5 or terminal or active or not restoration_valid(s['attempts'][-1]['result'])):raise ValueError('Incomplete independent restoration')
    def check_live(self):
        if self.write_failed or read(self.path)!=self.state:raise RuntimeError('Stale owner or failed write')
        if self.live_guard:self.live_guard()
    def commit(self,s):
        self.check_live();Ledger(self.path,s)
        try:write(self.path,s)
        except BaseException:self.write_failed=True;raise
        self.state=s
    def start(self,index):
        self.check_live();s=self.state
        if type(index) is not int or index!=len(s['attempts']) or index>=5 or s['active'] is not None or s['status']!=('await_restore' if index==4 else 'healthy'):raise RuntimeError('Ordered reserved start required')
        n=deepcopy(s);n.update(status='healthy',active=index);n['attempts'].append(dict(index=index,case=identities()[index],status='started',reserved_cycles=13000));self.commit(n)
    def finish(self,result):
        validate_result(result)
        if self.state['status']!='healthy' or self.state['active'] is None:raise RuntimeError('No current reservation')
        n=deepcopy(self.state);n['attempts'][n['active']].update(status='finished',result=deepcopy(result));n['active']=None
        if not result['simulation_valid'] or not result['physical_stopped']:n.update(status='failed',error='invalid_or_unstopped')
        elif result['guard_hit']:n.update(status='stopped',error='evaluation_guard')
        elif len(n['attempts'])==4:n['status']='await_restore'
        self.commit(n)
    def fail(self,error):
        if self.state['status'] in ('stopped','complete'):return
        n=deepcopy(self.state)
        if n['active'] is not None:n['attempts'][n['active']].update(status='failed',error=str(error));n['active']=None
        n.update(status='failed',error=str(error));self.commit(n)
    def complete(self):
        if self.state['status']!='healthy' or self.state['active'] is not None or len(self.state['attempts'])!=5 or not restoration_valid(self.state['attempts'][-1]['result']):raise RuntimeError('Full frozen/replayed boundary required')
        n=deepcopy(self.state);n['status']='complete';self.commit(n)
    def accounting(self):
        self.validate();n=len(self.state['attempts'])
        return dict(new_dynamic_starts=n,unused_dynamic=5-n,reserved_control_cycles=13000*n,
            confirmed_control_cycles=sum(a.get('result',{}).get('cycles',0) for a in self.state['attempts']),
            training_batches=0,independent_test=0,old_unused_consumed=0,status=self.state['status'])

def restoration_valid(r):
    return bool(r.get('restoration_equal') is True and type(r.get('source_worker_pid')) is int and type(r.get('restore_worker_pid')) is int and r['source_worker_pid']>0 and r['restore_worker_pid']>0 and r['source_worker_pid']!=r['restore_worker_pid'])

def confirm_stopped(folder):
    """Bound supervisor writes an exit record only after wait/confirmed cleanup."""
    evidence={}
    for phase in ('process','restore_process'):
        p=Path(folder)/phase
        if not (p/'started.json').exists():continue
        if not (p/'process_exit.json').exists():raise RuntimeError('Worker stop not confirmed: '+phase)
        r=read(p/'process_exit.json')
        normal=r.get('status') in ('finished','failed') and type(r.get('returncode')) is int
        cleaned=r.get('status')=='supervisor_error' and r.get('worker_stopped') is True and r.get('cleanup_error') is None
        if not normal and not cleaned:raise RuntimeError('Worker cleanup uncertain: '+phase)
        evidence[phase]=digest(p/'process_exit.json')
    if not evidence:raise RuntimeError('No supervised exit evidence')
    return evidence

def finalize_failed_exit(folder,binding_pin,auth_pin,variant,error):
    """Offline terminalization, only after the registered supervisor reaped workers."""
    folder=Path(folder);exits=confirm_stopped(folder);path=folder/'ledger.json'
    if path.exists():
        before=path.read_bytes()
        with (folder/'ledger_before_exit.json').open('xb') as f:f.write(before);f.flush();os.fsync(f.fileno())
        l=Ledger.load(path,binding_pin,auth_pin,variant)
    else:
        # Worker reserves before reset; failure before ledger creation consumed no dynamics.
        l=Ledger.create(path,binding_pin,auth_pin,variant)
    n=deepcopy(l.state)
    if n['active'] is not None:
        n['attempts'][n['active']].update(status='failed',error=str(error));n['active']=None
    n.update(status='failed',error=str(error));l.commit(n)
    write(folder/'exit_reconciliation.json',dict(worker_stop_confirmed=True,supervised_exit_sha256=exits,error=str(error),
        ledger_terminalized=True,retained_dynamic_starts=len(n['attempts']),retry_allowed=False,exact_costs_require_worker_records=True))
    write(folder/'accounting.json',l.accounting());return l

def started_variants(here):
    here=Path(here)
    return [v for v in ('base','small') if (here/v).exists() or any((here/(v+s)).exists() for s in ('_claim.json','_restore_claim.json','_launch_failure.json'))]
