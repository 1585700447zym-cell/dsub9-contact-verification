"""Bounded F/S experiment: one durable owner, independent of old C-success gates."""
from copy import deepcopy
import hashlib,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
PARENT=HERE.with_name('b2_frozen_c2000_closeout_20261001')
PARENT_PIN='bf1126f7e9813ca0d6e0ebbdb65a2260d4172b3834a6a5ca219b0ee50d977072'
PLAN=ROOT/'docs/superpowers/plans/2026-10-02-stage-residual-feasibility.md'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def pin(p):
    if type(p) is not str or len(p)!=64 or any(x not in '0123456789abcdef' for x in p):raise ValueError('SHA256 required')
def write(p,x):
    from tools.learning.admitted_collection import _write_json
    _write_json(Path(p),x)
def verify_files(files):
    for rel,sha in files.items():
        p=(ROOT/rel).resolve()
        if not p.is_relative_to(ROOT) or digest(p)!=sha:raise ValueError('Pinned file changed: '+rel)
def cases():
    return [dict(name=n,x_offset_m=x,y_offset_m=y,roll_rad=0.,pitch_rad=0.,start_origin_z_m=-.004,target_depth_m=.004)
            for n,(x,y) in zip(('x_pos_100','x_neg_100','y_pos_100','y_neg_100'),((.0001,0.),(-.0001,0.),(0.,.0001),(0.,-.0001)))]
def attempts():
    out=[]
    def add(stage,arm,i):
        c=cases()[i];out.append(dict(id=stage+'_'+arm+'_'+c['name'],stage=stage,arm=arm,case_index=i,case=c))
    for i in range(4):add('b2','B2',i)
    for stage in ('warmup','online','final'):
        for i in range(4):
            for arm in ('F','S'):add(stage,arm,i)
    for arm in ('F','S'):add('restore',arm,0)
    return out
def scope():
    return dict(previous_dynamic=90,dynamic_cap=30,cumulative_dynamic_cap=120,cycles_per_episode=13000,
        total_control_cycles_cap=390000,physical_substeps_cap=3900000,actor_state_cap=234000,
        training_batches_cap=5000,arm_training_batches_cap=2500,optimizer_steps_cap=15000,
        model_module_calls_cap=8128000,module_calls_per_control_cap=32,module_calls_per_batch_cap=128,
        seed=2026092716,batch_size=256,boundary_quota=16,action_scale=[.00005,.00005,.0005,.0005],
        warmup_hold_cycles=50,warmup_min_active_rows=256,warmup_min_active_cases=2,
        stop_on_any_guard=True,automatic_retry=False,automatic_tracking=False,independent_test=0,
        old_unused_consumed=0,extra_critic_diagnostics=0,attempts=attempts())
def config(arm):
    if arm not in ('F','S'):raise ValueError('F or S required')
    from tools.learning.actor_lr_contract import execution_config
    c=execution_config('A');c['version']='stage_permission_learning_v1'
    c['action']['scale']=scope()['action_scale'].copy()
    c['learning']['max_gradient_batches']=2500
    c['sampling'].update(max_attempts=8,stop_at='four_warmup_four_online_2500_batches')
    c['execution'].update(new_training_collection=8,authorized_dynamic_starts=30,authorized_optimizer_calls=2500)
    c['comparison']=dict(arm=arm,condition='paired_stage_permission_v1',warmup_hold_cycles=50,automatic_retry=False)
    c['stage_permission']=dict(version='stage_permission_v1',mode=arm,phases=['INSERT','SEARCH'] if arm=='F' else ['SEARCH'])
    return c
def verify_parent():
    p=PARENT/'result_analysis/delivery_verification.json'
    if digest(p)!=PARENT_PIN:raise ValueError('Parent seal changed')
    seal=read(p);verify_files(seal['sha256'])
    # The parent itself binds the previous full learning/physics implementation.
    old_path=sys.path.copy()
    try:
        sys.path.insert(0,str(PARENT))
        import night_contract as N
        pins=read(PARENT/'execution_pins.json');N.verify(pins['binding_sha256'],pins['authorization_sha256'],'base')
    finally:sys.path[:]=old_path
    return seal
def verify(binding_pin,auth_pin,with_runtime=False):
    pin(binding_pin);pin(auth_pin)
    if digest(HERE/'binding.json')!=binding_pin or digest(HERE/'authorization.json')!=auth_pin:raise ValueError('Authority changed')
    b=read(HERE/'binding.json');a=read(HERE/'authorization.json')
    if (b.get('version')!='paired_stage_binding_v1' or b.get('scope')!=scope() or
        b.get('configs')!={k:config(k) for k in ('F','S')} or b.get('protocol_passed') is not True or
        a.get('version')!='paired_stage_authority_v1' or a.get('approved') is not True or
        a.get('binding_sha256')!=binding_pin or a.get('scope')!=scope() or not a.get('user_confirmation')):raise ValueError('Registered scope required')
    verify_files(b['inputs_sha256']);verify_parent()
    if with_runtime:
        from tools.validation.verify_residual_interface import qualified_runtime
        from tools.learning.runtime import active_package
        if canonical(qualified_runtime(active_package()))!=canonical(b['runtime']):raise ValueError('Qualified runtime changed')
    return b
def validate_result(r,identity):
    if (any(r.get(k)!=v for k,v in identity.items()) or r.get('completed') is not True or
        any(type(r.get(k)) is not bool for k in ('success','simulation_valid','physical_stopped','guard_hit')) or
        type(r.get('cycles')) is not int or not 0<r['cycles']<=13000 or
        (r['success'] and (r['guard_hit'] or not r['simulation_valid'] or not r['physical_stopped']))):raise ValueError('Complete physical result required')
    canonical(r)
class Ledger:
    def __init__(self,path,state):
        self.path=Path(path);self.state=deepcopy(state);self.live_guard=None;self.write_failed=False;self.validate()
    @classmethod
    def create(cls,path,binding_pin,auth_pin):
        pin(binding_pin);pin(auth_pin)
        s=dict(version='paired_stage_ledger_v1',binding_sha256=binding_pin,authorization_sha256=auth_pin,
            scope=scope(),status='healthy',active=None,update_lease=None,attempts=[],datasets={},warmup_gate=None,
            updates={k:dict(attempted=0,completed=0) for k in ('F','S')},frozen={})
        with Path(path).open('x',encoding='utf-8') as f:json.dump(s,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        return cls(path,s)
    @classmethod
    def load(cls,path,binding_pin,auth_pin):
        s=read(path)
        if s['binding_sha256']!=binding_pin or s['authorization_sha256']!=auth_pin:raise ValueError('Ledger identity differs')
        return cls(path,s)
    def validate(self):
        s=self.state;pin(s['binding_sha256']);pin(s['authorization_sha256'])
        if s.get('version')!='paired_stage_ledger_v1' or s.get('scope')!=scope() or s['status'] not in ('healthy','failed','stopped','method_failed','complete'):raise ValueError('Ledger scope/state differs')
        if not isinstance(s['attempts'],list) or len(s['attempts'])>30:raise ValueError('Too many dynamic attempts')
        active=[]
        for i,a in enumerate(s['attempts']):
            if a['identity']!=attempts()[i] or a['reserved_cycles']!=13000 or a['status'] not in ('started','finished','failed'):raise ValueError('Attempt identity/order differs')
            if a['status']=='started':active.append(i)
            if a['status']=='finished':
                validate_result(a['result'],attempts()[i]);r=a['result']
                if (r['guard_hit'] or not r['simulation_valid'] or not r['physical_stopped']) and (i!=len(s['attempts'])-1 or s['status']=='healthy'):raise ValueError('Continuation after physical stop')
        if active!=([s['active']] if s['active'] is not None else []) or (active and active!=[len(s['attempts'])-1]):raise ValueError('Active reservation differs')
        if set(s['updates'])!={'F','S'}:raise ValueError('Both branch counters required')
        for arm,n in s['updates'].items():
            if (set(n)!={'attempted','completed'} or any(type(v) is not int or not 0<=v<=2500 for v in n.values()) or not 0<=n['attempted']-n['completed']<=1):raise ValueError('Update counters differ')
            cap=0 if arm not in s['datasets'] or s['warmup_gate'] is None else min(2500,500*(1+len(self.rows('online',arm))))
            if n['attempted']>cap:raise ValueError('Unearned update credit')
        lease=s['update_lease']
        if lease is not None:
            arm=lease.get('arm');n=s['updates'].get(arm,{})
            if lease!=dict(arm=arm,batch=n.get('attempted'),binding_sha256=s['binding_sha256']) or n.get('attempted',0)!=n.get('completed',0)+1 or s['active'] is not None:raise ValueError('Update lease differs')
        elif s['status']=='healthy' and any(n['attempted']!=n['completed'] for n in s['updates'].values()):raise ValueError('Unaccounted attempted batch')
        if s['status']!='healthy' and (active or lease is not None):raise ValueError('Closed ledger has active work')
        for arm,d in s['datasets'].items():
            if arm not in ('F','S') or d['ids']!=[r['id'] for r in self.rows('warmup',arm)] or len(d['ids'])!=4:raise ValueError('New warmup dataset required')
            pin(d['manifest_sha256'])
        for arm,p in s['frozen'].items():
            pin(p)
            if arm not in ('F','S') or s['updates'][arm]['completed']!=2500:raise ValueError('Final2500 freeze required')
    def rows(self,stage,arm=None):return [a['result'] for a in self.state['attempts'] if a['status']=='finished' and a['identity']['stage']==stage and (arm is None or a['identity']['arm']==arm)]
    def check_live(self):
        if self.write_failed or canonical(read(self.path))!=canonical(self.state):raise RuntimeError('Failed write or stale ledger owner')
        if self.live_guard:self.live_guard()
    def commit(self,s):
        self.check_live();Ledger(self.path,s)
        try:write(self.path,s)
        except BaseException:self.write_failed=True;raise
        self.state=s
    def healthy(self):
        self.check_live()
        if self.state['status']!='healthy' or self.state['active'] is not None or self.state['update_lease'] is not None:raise RuntimeError('Healthy idle ledger required')
    def register_dataset(self,arm,manifest_pin,ids):
        self.healthy();pin(manifest_pin)
        if arm not in ('F','S') or arm in self.state['datasets']:raise RuntimeError('New branch dataset only')
        s=deepcopy(self.state);s['datasets'][arm]=dict(manifest_sha256=manifest_pin,ids=ids);self.commit(s)
    def admit_warmup(self,proof_pin):
        self.healthy();pin(proof_pin)
        if len(self.rows('warmup'))!=8 or set(self.state['datasets'])!={'F','S'} or self.state['warmup_gate'] is not None:raise RuntimeError('Both new warmups required')
        s=deepcopy(self.state);s['warmup_gate']=proof_pin;self.commit(s)
    def start(self,identity):
        self.healthy();i=len(self.state['attempts'])
        if i>=30 or identity!=attempts()[i]['id']:raise RuntimeError('Ordered dynamic reservation required')
        a=attempts()[i];arm=a['arm'];stage=a['stage']
        if stage=='online' and (self.state['warmup_gate'] is None or self.state['updates'][arm]['completed']!=500*(a['case_index']+1)):raise RuntimeError('Exact online update boundary required')
        if stage in ('final','restore') and (set(self.state['frozen'])!={'F','S'} or any(n['completed']!=2500 for n in self.state['updates'].values())):raise RuntimeError('Both frozen final branches required')
        s=deepcopy(self.state);s['attempts'].append(dict(identity=a,status='started',reserved_cycles=13000));s['active']=i;self.commit(s)
    def finish(self,r):
        self.check_live();i=self.state['active']
        if i is None or self.state['status']!='healthy':raise RuntimeError('Current physical lease required')
        validate_result(r,attempts()[i]);s=deepcopy(self.state);s['attempts'][i].update(status='finished',result=deepcopy(r));s['active']=None
        if not r['simulation_valid'] or not r['physical_stopped']:s.update(status='failed',error='invalid_or_unstopped')
        elif r['guard_hit']:s.update(status='stopped',error='physical_guard')
        self.commit(s)
    def reserve_update(self,arm):
        self.healthy();s=self.state;i=len(s['attempts'])
        if s['warmup_gate'] is None or set(s['datasets'])!={'F','S'} or i<12 or i>20:raise RuntimeError('Warmup gate and learning stage required')
        expected=attempts()[i]['arm'] if i<20 else ('F' if s['updates']['F']['completed']<2500 else 'S')
        if arm!=expected:raise RuntimeError('Paired branch order differs')
        cap=min(2500,500*(1+len(self.rows('online',arm))));n=s['updates'][arm]
        if n['completed']>=cap or n['attempted']!=n['completed']:raise RuntimeError('Update credit exhausted')
        token=dict(arm=arm,batch=n['attempted']+1,binding_sha256=s['binding_sha256'])
        t=deepcopy(s);t['updates'][arm]['attempted']+=1;t['update_lease']=token;self.commit(t);return token
    def finish_update(self,token):
        self.check_live()
        if self.state['status']!='healthy' or self.state['update_lease']!=token or token is None:raise RuntimeError('Exact update lease required')
        s=deepcopy(self.state);s['updates'][token['arm']]['completed']+=1;s['update_lease']=None;self.commit(s)
    def freeze(self,arm,manifest_pin):
        self.healthy();pin(manifest_pin)
        if arm in self.state['frozen'] or self.state['updates'][arm]['completed']!=2500:raise RuntimeError('One final freeze required')
        s=deepcopy(self.state);s['frozen'][arm]=manifest_pin;self.commit(s)
    def fail(self,error):
        if self.state['status']!='healthy':return
        s=deepcopy(self.state)
        if s['active'] is not None:s['attempts'][s['active']].update(status='failed',error=str(error))
        s.update(status='failed',error=str(error),active=None,update_lease=None);self.commit(s)
    def method_failed(self,reason):
        self.healthy();s=deepcopy(self.state);s.update(status='method_failed',error=str(reason));self.commit(s)
    def complete(self):
        self.healthy()
        if len(self.state['attempts'])!=30 or any(not r.get('restoration_equal') for r in self.rows('restore')):raise RuntimeError('Both complete representative restores required')
        s=deepcopy(self.state);s['status']='complete';self.commit(s)
    def accounting(self):
        s=self.state;n=len(s['attempts']);rows=[a['result'] for a in s['attempts'] if a['status']=='finished']
        return dict(previous_dynamic=90,new_dynamic_starts=n,cumulative_dynamic=90+n,cumulative_dynamic_cap=120,unused_dynamic=30-n,
            control_cycles_reserved=n*13000,control_cycles_confirmed=sum(r['cycles'] for r in rows),
            formal_batches_attempted=sum(v['attempted'] for v in s['updates'].values()),formal_batches_completed=sum(v['completed'] for v in s['updates'].values()),
            updates=deepcopy(s['updates']),status=s['status'],independent_test=0,old_unused_consumed=0)
