"""Exact current learning authority, whole-stage order and durable costs."""
from copy import deepcopy
import hashlib,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(ROOT))
PREFLIGHT=ROOT/'deliverables/learning_chain/b2_temporal_warmup_execution_20261001'
PREFLIGHT_PIN='f62e8893b1172f5696c2a6462e3cba7806e2302bc0b4f01c8dc5f2cfa2393531'
FAILED=HERE.with_name('b2_temporal_learning_validation_20261001')
FIX=HERE.with_name('b2_temporal_checkpoint_write_fix_20261001')
FAILED_SEAL_PIN='bbe2885f8a5c56d2f014cb9cec1b39b9f00c48c92992de3f43c211b485fb9235'
FIX_SEAL_PIN='216fb9e486db5a52a36d3c21178959299b5ec32202986f12c87023dbd6daeb92'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def pin(x):
    if type(x) is not str or len(x)!=64 or any(c not in '0123456789abcdef' for c in x):raise ValueError('External SHA256 required')
def write(p,x):
    from tools.learning.admitted_collection import _write_json
    _write_json(p,x)
def verify_files(files):
    for rel,pin in files.items():
        p=(ROOT/rel).resolve()
        if not p.is_relative_to(ROOT) or digest(p)!=pin:raise ValueError('Pinned bytes changed: '+rel)
def cases():
    return [dict(name=name,x_offset_m=x,y_offset_m=y,roll_rad=0.,pitch_rad=0.,start_origin_z_m=-.004,target_depth_m=.004)
        for name,(x,y) in zip(('x_pos_100','x_neg_100','y_pos_100','y_neg_100'),((.0001,0.),(-.0001,0.),(0.,.0001),(0.,-.0001)))]
def attempts():
    return [dict(id=stage+'_'+case['name'],stage=stage,arm=stage[0] if stage!='initial' else 'shared',case_index=i,case=case)
        for stage in ('initial','C_online','C_final','C_restored','A_online','A_final') for i,case in enumerate(cases())]
def scope():
    return dict(dynamic_cap=24,previous_dynamic=72,cumulative_dynamic_cap=96,cycles_per_episode=13000,
        previous_temporal_batches=500,temporal_family_batches_cap=5500,restart_from_zero=True,
        failed_parent_sha256=FAILED_SEAL_PIN,writer_fix_sha256=FIX_SEAL_PIN,real_zero_disk_gate_required=True,
        total_control_cycles_cap=312000,physical_substeps_cap=3120000,training_batches_cap=5000,
        arm_training_batches_cap=2500,optimizer_steps_cap=15000,model_module_calls_cap=10624000,
        module_calls_per_batch_cap=128,module_calls_per_control_cap=32,attempts=attempts(),
        seed=2026092716,batch_size=256,boundary_quota=16,warmup_episodes_per_arm=4,new_online_per_arm=4,
        actor_learning_rate=3e-4,critic_learning_rate=3e-4,temperature_learning_rate=3e-4,
        control_period_s=.002,policy_period_s=.002,physics_period_s=.0002,action_scale=[.00015,.00015,.0005,.0005],
        stop_on_any_guard=True,automatic_retry=False,automatic_tracking=False,independent_test=0,old_unused_consumed=0)
def config(arm):
    if arm not in ('A','C'):raise ValueError('Registered arm required')
    from tools.learning.actor_lr_contract import execution_config
    c=execution_config('A');c['version']='temporal_learning_restart_v1'
    c['learning']['max_gradient_batches']=2500
    c['sampling'].update(max_attempts=8,stop_at='eight_audited_learning_episodes_and_2500_batches')
    c['execution'].update(new_training_collection=4,authorized_dynamic_starts=24,authorized_optimizer_calls=2500)
    c['comparison']=dict(arm=arm,condition='C_then_A_complete_validation',warmup_hold_cycles=50 if arm=='C' else 1,
        source_preflight_sha256=PREFLIGHT_PIN,automatic_retry=False)
    return c
def validate_authorization(a,binding_pin):
    pin(binding_pin)
    if (a.get('version')!='temporal_learning_authorization_v1' or a.get('approved') is not True or
        a.get('binding_sha256')!=binding_pin or canonical(a.get('scope'))!=canonical(scope()) or
        not isinstance(a.get('user_confirmation'),str) or not a['user_confirmation'].strip()):raise ValueError('Exact current explicit authorization required')
def require_authorization(binding_pin,auth_pin):
    pin(auth_pin)
    if digest(HERE/'authorization.json')!=auth_pin:raise ValueError('Authorization changed')
    a=read(HERE/'authorization.json');validate_authorization(a,binding_pin);return a
def verify_parent():
    p=PREFLIGHT/'result_analysis/delivery_verification.json'
    if digest(p)!=PREFLIGHT_PIN:raise ValueError('Physical preflight seal changed')
    r=read(p);verify_files(r['sha256'])
    verify_files(read(PREFLIGHT/'binding.json')['input_sha256'])
    if r['actual_status']!='complete' or not r['candidate_collection_preflight_passed'] or r['accounting']['cumulative_dynamic']!=68:
        raise ValueError('Complete preflight boundary required')
    verify_restart_parents()
def verify_restart_parents():
    p=FAILED/'result_analysis/delivery_verification.json';f=FIX/'delivery_verification.json'
    if digest(p)!=FAILED_SEAL_PIN or digest(f)!=FIX_SEAL_PIN:raise ValueError('Restart parent seal changed')
    r=read(p);v=read(f);verify_files(r['sha256']);verify_files(v['sha256'])
    verify_files(read(FAILED/'binding.json')['input_sha256'])
    if (r['actual_status']!='failed' or r['judgement']!='operational_verification_blocked' or
        r['accounting']['cumulative_dynamic']!=72 or r['accounting']['formal_batches_completed']!=500 or
        r['actual_C500_recoverable'] is not False or r['learned_policy_dynamic_attempts']!=0 or
        v['tests']!=7 or any(v['actual_calls'].values()) or v['policy_effect_validated'] or
        r['separate_offline_repair_sha256']!=FIX_SEAL_PIN):raise ValueError('Pinned failed72/500 and offline-only repair required')
def verify_binding(binding_pin,with_runtime=False):
    pin(binding_pin)
    if digest(HERE/'binding.json')!=binding_pin:raise ValueError('Validation binding changed')
    b=read(HERE/'binding.json')
    if (b.get('version')!='temporal_learning_binding_v1' or canonical(b.get('scope'))!=canonical(scope()) or
        b.get('parent_preflight_sha256')!=PREFLIGHT_PIN or b.get('protocol_passed') is not True or
        canonical(b.get('configs'))!=canonical({a:config(a) for a in ('A','C')})):raise ValueError('Registered learning binding required')
    verify_parent();verify_files(b['input_sha256'])
    for name in ('validation_contract.py','learning_runtime.py','run_validation.py','verify_zero_checkpoint.py','test_protocol.py','protocol_runner.py','验证方案.md'):
        if (HERE/name).relative_to(ROOT).as_posix() not in b['input_sha256']:raise ValueError('Required source not bound')
    if with_runtime:
        from tools.validation.verify_residual_interface import qualified_runtime
        from tools.learning.runtime import active_package
        if canonical(qualified_runtime(active_package()))!=canonical(b['runtime']):raise ValueError('Qualified runtime changed')
    return b
def validate_result(row,identity):
    if (not isinstance(row,dict) or row.get('completed') is not True or any(canonical(row.get(k))!=canonical(v) for k,v in identity.items()) or
        any(type(row.get(k)) is not bool for k in ('success','simulation_valid','physical_stopped','guard_hit')) or
        type(row.get('cycles')) is not int or not 0<row['cycles']<=13000 or
        (row['success'] and (row['guard_hit'] or not row['simulation_valid'] or not row['physical_stopped']))):raise ValueError('Audited complete result required')
    canonical(row)

class Ledger:
    def __init__(self,path,state):
        self.path=Path(path);self.state=deepcopy(state);self.live_guard=None;self.write_failed=False;self.validate()
    @classmethod
    def create(cls,path,binding_pin,auth_pin):
        pin(binding_pin);pin(auth_pin)
        s=dict(version='temporal_learning_ledger_v1',binding_sha256=binding_pin,authorization_sha256=auth_pin,scope=scope(),
            status='healthy',active=None,attempts=[],datasets={},updates={a:dict(attempted=0,completed=0) for a in ('A','C')},update_lease=None,frozen={},restoration_pin=None)
        with Path(path).open('x',encoding='utf-8') as f:json.dump(s,f,indent=2);f.flush();os.fsync(f.fileno())
        return cls(path,s)
    @classmethod
    def load(cls,path,binding_pin,auth_pin):
        s=read(path)
        if s.get('binding_sha256')!=binding_pin or s.get('authorization_sha256')!=auth_pin:raise ValueError('Ledger binding changed')
        return cls(path,s)
    def validate(self):
        s=self.state;pin(s['binding_sha256']);pin(s['authorization_sha256'])
        if s.get('version')!='temporal_learning_ledger_v1' or canonical(s.get('scope'))!=canonical(scope()) or s.get('status') not in ('healthy','failed','stopped','baseline_failed','method_failed','complete'):
            raise ValueError('Malformed ledger')
        if len(s['attempts'])>24:raise ValueError('Dynamic cap exceeded')
        active=[]
        for i,row in enumerate(s['attempts']):
            if row['identity']!=attempts()[i] or row['reserved_cycles']!=13000 or row['status'] not in ('started','finished','failed'):raise ValueError('Attempt order differs')
            if row['status']=='started':active.append(i)
            if row['status']=='finished':
                validate_result(row['result'],attempts()[i]);r=row['result']
                if (r['guard_hit'] or not r['simulation_valid'] or not r['physical_stopped']) and (i!=len(s['attempts'])-1 or s['status']=='healthy'):
                    raise ValueError('Closed physical boundary cannot resume')
        if active!=([s['active']] if s['active'] is not None else []) or (active and active!=[len(s['attempts'])-1]):raise ValueError('Active reservation differs')
        for arm,n in s['updates'].items():
            if arm not in ('A','C') or any(type(n.get(k)) is not int or not 0<=n[k]<=2500 for k in ('attempted','completed')) or not 0<=n['attempted']-n['completed']<=1:
                raise ValueError('Update counters differ')
        if set(s['updates'])!={'A','C'} or (s['active'] is not None and s['update_lease'] is not None):raise ValueError('Concurrent physical/update lease')
        if s['status']!='healthy' and (active or s['update_lease'] is not None):raise ValueError('Closed ledger has active work')
        lease=s['update_lease']
        if lease is not None:
            arm=lease.get('arm');n=s['updates'].get(arm,{})
            if lease!=dict(arm=arm,batch=n.get('attempted'),binding_sha256=s['binding_sha256']) or n.get('attempted',0)!=n.get('completed',0)+1:raise ValueError('Update lease/counters disagree')
        elif s['status']=='healthy' and any(n['attempted']!=n['completed'] for n in s['updates'].values()):raise ValueError('Unaccounted attempted update')
        for arm,dataset in s['datasets'].items():
            if arm not in ('A','C') or len(dataset['ids'])!=4 or len(set(dataset['ids']))!=4:raise ValueError('Dataset credit malformed')
            pin(dataset['manifest_sha256'])
        for arm,n in s['updates'].items():
            cap=0 if arm not in s['datasets'] else min(2500,500*(1+len(self.rows(arm+'_online'))))
            if n['attempted']>cap:raise ValueError('Unearned update reservation')
        for arm,frozen_pin in s['frozen'].items():
            pin(frozen_pin)
            if arm not in ('A','C') or s['updates'][arm]['completed']!=2500:raise ValueError('Invalid frozen boundary')
        if s['restoration_pin'] is not None:
            pin(s['restoration_pin'])
            if len(self.rows('C_restored'))!=4 or not all(r['success'] for r in self.rows('C_restored')):raise ValueError('Restoration proof without four successes')
    def check_live(self):
        if self.write_failed:raise RuntimeError('Durable write failed; budget poisoned')
        if self.live_guard:self.live_guard()
        if canonical(read(self.path))!=canonical(self.state):raise RuntimeError('Stale ledger owner')
    def commit(self,s):
        self.check_live();Ledger(self.path,s)
        try:write(self.path,s)
        except BaseException:self.write_failed=True;raise
        self.state=s
    def healthy(self):
        self.check_live()
        if self.state['status']!='healthy' or self.state['active'] is not None or self.state['update_lease'] is not None:raise RuntimeError('Healthy idle reservation required')
    def register_dataset(self,arm,manifest_pin,ids):
        self.healthy();pin(manifest_pin)
        if arm not in ('A','C') or type(ids) is not list or len(ids)!=4 or len(set(ids))!=4 or any(not isinstance(x,str) or not x for x in ids):raise ValueError('Four unique new warmup IDs required')
        if arm in self.state['datasets']:raise RuntimeError('Dataset already admitted; no duplicate credit')
        s=deepcopy(self.state);s['datasets'][arm]=dict(manifest_sha256=manifest_pin,ids=ids.copy());self.commit(s)
    def rows(self,stage):return [x['result'] for x in self.state['attempts'] if x['status']=='finished' and x['identity']['stage']==stage]
    def credit_cap(self,arm):
        return 0 if arm not in self.state['datasets'] else 500*(1+len(self.rows(arm+'_online')))
    def start(self,identity):
        self.healthy();i=len(self.state['attempts'])
        if i>=24 or identity!=attempts()[i]['id']:raise RuntimeError('Ordered dynamic reservation refused')
        a=attempts()[i];stage=a['stage'];arm=a['arm']
        if stage!='initial':
            if len(self.rows('initial'))!=4 or not all(r['success'] for r in self.rows('initial')):raise RuntimeError('Initial four successes required')
            n=self.state['updates'][arm]['completed']
            if stage.endswith('_online') and (n!=500*(a['case_index']+1) or n!=self.credit_cap(arm)):raise RuntimeError('Online episode requires exact spent credit')
            if stage.endswith(('_final','_restored')) and (n!=2500 or arm not in self.state['frozen']):raise RuntimeError('Frozen 2500 checkpoint required')
            if stage=='C_restored' and not all(r['success'] for r in self.rows('C_final')):raise RuntimeError('Failed candidate cannot retry')
            if arm=='A' and self.state['restoration_pin'] is None:raise RuntimeError('Candidate restoration must finish first')
        s=deepcopy(self.state);s['attempts'].append(dict(identity=a,reserved_cycles=13000,status='started'));s['active']=i;self.commit(s)
    def finish(self,row):
        self.check_live();i=self.state['active']
        if i is None or self.state['status']!='healthy':raise RuntimeError('Active physical reservation required')
        validate_result(row,attempts()[i]);s=deepcopy(self.state);s['attempts'][i].update(status='finished',result=deepcopy(row));s['active']=None
        if not row['simulation_valid'] or not row['physical_stopped']:s['status']='failed'
        elif row['guard_hit']:s.update(status='stopped',stop_reason='any_physical_guard')
        elif i==3 and not all(x['result']['success'] for x in s['attempts']):s['status']='baseline_failed'
        elif i==11 and not all(x['result']['success'] for x in s['attempts'][8:12]):s['status']='method_failed'
        self.commit(s)
    def reserve_update(self,arm):
        self.healthy()
        if (arm not in ('A','C') or len(self.rows('initial'))!=4 or not all(r['success'] for r in self.rows('initial')) or
            (arm=='A' and self.state['restoration_pin'] is None)):raise RuntimeError('Approved update stage required')
        n=self.state['updates'][arm]
        if n['attempted']!=n['completed'] or n['completed']>=min(2500,self.credit_cap(arm)):raise RuntimeError('Audited credit exhausted')
        token=dict(arm=arm,batch=n['attempted']+1,binding_sha256=self.state['binding_sha256'])
        s=deepcopy(self.state);s['updates'][arm]['attempted']+=1;s['update_lease']=token;self.commit(s);return token
    def finish_update(self,token):
        self.check_live()
        if self.state['status']!='healthy' or self.state['update_lease']!=token or token is None:raise RuntimeError('Exact active update lease required')
        s=deepcopy(self.state);s['updates'][token['arm']]['completed']+=1;s['update_lease']=None;self.commit(s)
    def freeze(self,arm,manifest_pin):
        self.healthy();pin(manifest_pin)
        if arm in self.state['frozen'] or self.state['updates'][arm]['completed']!=2500:raise RuntimeError('One final freeze required')
        s=deepcopy(self.state);s['frozen'][arm]=manifest_pin;self.commit(s)
    def restored(self,proof_pin):
        self.healthy();pin(proof_pin)
        if len(self.rows('C_restored'))!=4 or not all(r['success'] for r in self.rows('C_restored')):raise RuntimeError('Complete successful restoration required')
        s=deepcopy(self.state);s['restoration_pin']=proof_pin;self.commit(s)
    def fail(self,error):
        s=deepcopy(self.state)
        if s['active'] is not None:s['attempts'][s['active']].update(status='failed',error=str(error))
        s.update(active=None,update_lease=None,status='failed',error=str(error));self.commit(s)
    def method_failed(self,reason):
        self.healthy();s=deepcopy(self.state);s.update(status='method_failed',stop_reason=reason);self.commit(s)
    def complete(self):
        self.healthy()
        if len(self.state['attempts'])!=24 or any(n['completed']!=2500 for n in self.state['updates'].values()) or not self.state['restoration_pin']:raise RuntimeError('All validation stages required')
        s=deepcopy(self.state);s['status']='complete';self.commit(s)
    def accounting(self):
        s=self.state;n=len(s['attempts']);rows=[x['result'] for x in s['attempts'] if x['status']=='finished']
        return dict(previous_dynamic=72,new_dynamic_starts=n,cumulative_dynamic=72+n,cumulative_dynamic_cap=96,unused_dynamic=24-n,
            previous_temporal_batches=500,cumulative_temporal_batches_attempted=500+sum(x['attempted'] for x in s['updates'].values()),
            cumulative_temporal_batches_completed=500+sum(x['completed'] for x in s['updates'].values()),
            control_cycles_reserved=n*13000,control_cycles_confirmed=sum(r['cycles'] for r in rows),
            formal_batches_attempted=sum(x['attempted'] for x in s['updates'].values()),formal_batches_completed=sum(x['completed'] for x in s['updates'].values()),
            updates=deepcopy(s['updates']),independent_test=0,old_unused_consumed=0,status=s['status'])
