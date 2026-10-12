"""Bounded F/S experiment: one durable owner, independent of old C-success gates."""
from copy import deepcopy
import hashlib,importlib.util,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
PARENT=HERE.with_name('b2_stage_permission_20261002')
PARENT_PIN='842e2270080f853a77ca52e769dceedb2ff25b0b9b7c54566d73d5945217d6cb'
PARENT_LEDGER_PIN='1f8770b91e24ca7654db3ef42a5bc3776c8a23901ff3c8c2df442198640cda61'
PARENT_BINDING='399367199645decfed696c31e48dee0727117485b3673d028c52a0c5db392a46'
PLAN=ROOT/'docs/superpowers/plans/2026-10-03-stage-permission-resume.md'
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
def inherited_attempts():
    path=PARENT/'run/ledger.json'
    if digest(path)!=PARENT_LEDGER_PIN:raise ValueError('Inherited ledger changed')
    s=read(path)
    if (s['status']!='failed' or s['binding_sha256']!=PARENT_BINDING or len(s['attempts'])!=12 or
            any(v!=dict(attempted=0,completed=0) for v in s['updates'].values()) or
            any(a['status']!='finished' or a['identity']!=attempts()[i] or a['result']['guard_hit'] or
                not a['result']['simulation_valid'] or not a['result']['physical_stopped'] for i,a in enumerate(s['attempts']))):
        raise ValueError('Exact completed zero-update source prefix required')
    return s['attempts']

def source_binding(arm,role,current_binding):
    pin(current_binding)
    if arm not in ('F','S') or role not in ('warmup','online'):raise ValueError('Registered data role required')
    return PARENT_BINDING if role=='warmup' else current_binding

def scope():
    return dict(previous_dynamic=102,dynamic_cap=18,cumulative_dynamic_cap=120,cycles_per_episode=13000,
        total_control_cycles_cap=234000,physical_substeps_cap=2340000,actor_state_cap=234000,
        training_batches_cap=5000,arm_training_batches_cap=2500,optimizer_steps_cap=15000,
        model_module_calls_cap=8128000,module_calls_per_control_cap=32,module_calls_per_batch_cap=128,
        seed=2026092716,batch_size=256,boundary_quota=16,action_scale=[.00005,.00005,.0005,.0005],
        warmup_hold_cycles=50,warmup_min_active_rows=256,warmup_min_active_cases=2,
        stop_on_any_guard=True,automatic_retry=False,automatic_tracking=False,independent_test=0,
        old_unused_consumed=0,extra_critic_diagnostics=0,attempts=attempts(),inherited_prefix=12,
        parent_ledger_sha256=PARENT_LEDGER_PIN,reader_timeout_s=300)
def config(arm):
    if arm not in ('F','S'):raise ValueError('F or S required')
    from tools.learning.actor_lr_contract import execution_config
    c=execution_config('A');c['version']='stage_permission_resume_learning_v1'
    c['action']['scale']=scope()['action_scale'].copy()
    c['learning']['max_gradient_batches']=2500
    c['sampling'].update(max_attempts=4,stop_at='inherited_warmup_four_online_2500_batches')
    c['execution'].update(new_training_collection=4,authorized_dynamic_starts=18,authorized_optimizer_calls=2500)
    c['comparison']=dict(arm=arm,condition='paired_stage_permission_v1',warmup_hold_cycles=50,automatic_retry=False)
    c['stage_permission']=dict(version='stage_permission_v1',mode=arm,phases=['INSERT','SEARCH'] if arm=='F' else ['SEARCH'])
    return c
def verify_parent():
    p=PARENT/'result_analysis/delivery_verification.json'
    if digest(p)!=PARENT_PIN:raise ValueError('Parent seal changed')
    seal=read(p);verify_files(seal['sha256'])
    # Keep the failed parent's full authority chain intact, under a distinct module name.
    old_path=sys.path.copy()
    try:
        spec=importlib.util.spec_from_file_location('_resume_parent_contract',PARENT/'paired_contract.py')
        old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
        pins=read(PARENT/'execution_pins.json');old.verify(pins['binding_sha256'],pins['authorization_sha256'])
        for arm in ('F','S'):
            prior=old.config(arm);current=config(arm)
            for key in set(prior)-{'version','sampling','execution'}:
                if prior[key]!=current[key]:raise ValueError('Scientific condition changed during recovery: '+key)
        inherited_attempts()
    finally:sys.path[:]=old_path
    return seal
def verify(binding_pin,auth_pin,with_runtime=False):
    pin(binding_pin);pin(auth_pin)
    if digest(HERE/'binding.json')!=binding_pin or digest(HERE/'authorization.json')!=auth_pin:raise ValueError('Authority changed')
    b=read(HERE/'binding.json');a=read(HERE/'authorization.json')
    if (b.get('version')!='paired_resume_binding_v1' or b.get('scope')!=scope() or
        b.get('configs')!={k:config(k) for k in ('F','S')} or b.get('protocol_passed') is not True or
        a.get('version')!='paired_resume_authority_v1' or a.get('approved') is not True or
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

def validate_reader(proof,arm,checkpoint_pin,binding_pin,auth_pin):
    pin(checkpoint_pin)
    if (proof.get('complete_equal') is not True or proof.get('arm')!=arm or proof.get('batches')!=0 or
            proof.get('binding_sha256')!=binding_pin or proof.get('authorization_sha256')!=auth_pin or
            proof.get('manifest_sha256')!=checkpoint_pin or type(proof.get('pid')) is not int or
            proof['pid']<=0 or
            proof.get('calls')!=dict(model_forward=0,optimizer=0,physics=0)):
        raise ValueError('Complete independent zero-computation reader proof required')

def verify_reader_process(proof,process):
    from tools.validation.process_parent import validate_chain
    import time
    chain=proof['parent_chain']
    checked=validate_chain(expected_pid=process['parent_pid'],registered_at=process['wall_timestamp'],now=time.time(),
        child=chain['child'],parent=chain['parent'],registered=chain['registered'],
        python_image=sys._base_executable,launcher_image=sys.executable)
    if checked!=chain or chain['pid']!=proof['pid']:
        raise ValueError('Reader parent-chain proof differs')
    launch_pid=chain['pid'] if chain['route']=='direct' else chain['parent_pid']
    if process['pid']!=launch_pid:raise ValueError('Reader does not belong to supervised launcher')

class Ledger:
    def __init__(self,path,state):
        self.path=Path(path);self.state=deepcopy(state);self.live_guard=None;self.write_failed=False;self.validate()
    @classmethod
    def create(cls,path,binding_pin,auth_pin):
        pin(binding_pin);pin(auth_pin)
        s=dict(version='paired_resume_ledger_v1',binding_sha256=binding_pin,authorization_sha256=auth_pin,
            scope=scope(),status='healthy',active=None,update_lease=None,attempts=inherited_attempts(),datasets={},warmup_gate=None,
            updates={k:dict(attempted=0,completed=0) for k in ('F','S')},frozen={},zero_readers={})
        with Path(path).open('x',encoding='utf-8') as f:json.dump(s,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        return cls(path,s)
    @classmethod
    def load(cls,path,binding_pin,auth_pin):
        s=read(path)
        if s['binding_sha256']!=binding_pin or s['authorization_sha256']!=auth_pin:raise ValueError('Ledger identity differs')
        return cls(path,s)
    def validate(self):
        s=self.state;pin(s['binding_sha256']);pin(s['authorization_sha256'])
        if s.get('version')!='paired_resume_ledger_v1' or s.get('scope')!=scope() or s['status'] not in ('healthy','failed','stopped','method_failed','complete'):raise ValueError('Ledger scope/state differs')
        if not isinstance(s['attempts'],list) or not 12<=len(s['attempts'])<=30:raise ValueError('Dynamic/inherited prefix count differs')
        if s['attempts'][:12]!=inherited_attempts():raise ValueError('Inherited prefix changed')
        for arm,proof in s.get('zero_readers',{}).items():
            if arm not in ('F','S'):raise ValueError('Unknown reader branch')
            validate_reader(proof,arm,proof.get('manifest_sha256'),s['binding_sha256'],s['authorization_sha256'])
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
            cap=0 if arm not in s['datasets'] or s['warmup_gate'] is None or set(s.get('zero_readers',{}))!={'F','S'} else min(2500,500*(1+len(self.rows('online',arm))))
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
    def register_zero_reader(self,arm,checkpoint_pin,proof):
        self.healthy()
        if arm not in ('F','S') or arm in self.state['zero_readers'] or self.state['warmup_gate'] is None or any(v['attempted'] for v in self.state['updates'].values()):raise RuntimeError('Fresh zero reader boundary required')
        validate_reader(proof,arm,checkpoint_pin,self.state['binding_sha256'],self.state['authorization_sha256'])
        if proof['pid']==os.getpid():raise ValueError('Reader must run in a separate process')
        s=deepcopy(self.state);s['zero_readers'][arm]=deepcopy(proof);self.commit(s)
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
        if s['warmup_gate'] is None or set(s['datasets'])!={'F','S'} or set(s['zero_readers'])!={'F','S'} or i<12 or i>20:raise RuntimeError('Both reader proofs, warmup gate and learning stage required')
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
        s=self.state;n=len(s['attempts'])-12;rows=[a['result'] for a in s['attempts'][12:] if a['status']=='finished']
        return dict(previous_dynamic=102,inherited_attempts=12,new_dynamic_starts=n,cumulative_dynamic=102+n,cumulative_dynamic_cap=120,unused_dynamic=18-n,
            control_cycles_reserved=n*13000,control_cycles_confirmed=sum(r['cycles'] for r in rows),
            formal_batches_attempted=sum(v['attempted'] for v in s['updates'].values()),formal_batches_completed=sum(v['completed'] for v in s['updates'].values()),
            updates=deepcopy(s['updates']),status=s['status'],independent_test=0,old_unused_consumed=0)
