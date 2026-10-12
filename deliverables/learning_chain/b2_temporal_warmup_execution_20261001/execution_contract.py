"""Exact, independently authorized temporal-warmup preflight and durable budget."""
from copy import deepcopy
import hashlib,json,os
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(ROOT))
DESIGN=ROOT/'deliverables/learning_chain/b2_temporal_warmup_design_20261001'
DESIGN_PIN='34a6b409a8a7ac71d6f4a90ad7fe1fcc741769285b3f2bb0f5f36a072c3f1497'
PRIOR=ROOT/'deliverables/learning_chain/b2_actor_lr_b_eval_20261001'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
def digest(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def canonical(r):return json.dumps(r,sort_keys=True,separators=(',',':'),allow_nan=False)
def pin(r):
    if type(r) is not str or len(r)!=64 or any(c not in '0123456789abcdef' for c in r):raise ValueError('SHA256 pin required')
def verify_files(files):
    for rel,expected in files.items():
        path=(ROOT/rel).resolve()
        if not path.is_relative_to(ROOT) or digest(path)!=expected:raise ValueError('Bound input differs: '+rel)
def write(path,value):
    from tools.learning.admitted_collection import _write_json
    _write_json(path,value)

def attempts():
    result=[]
    for i,(name,xy) in enumerate(zip(('x_pos_100','x_neg_100','y_pos_100','y_neg_100'),((.0001,0.),(-.0001,0.),(0.,.0001),(0.,-.0001)))):
        case=dict(name=name,x_offset_m=xy[0],y_offset_m=xy[1],roll_rad=0.,pitch_rad=0.,start_origin_z_m=-.004,target_depth_m=.004)
        for arm,hold in (('A',1),('C',50)):
            result.append(dict(id=name+'_'+arm,arm=arm,hold_cycles=hold,case_index=i,case=case.copy()))
    return result
def scope():
    return dict(dynamic_cap=8,previous_dynamic=60,cumulative_dynamic_cap=68,cycles_per_episode=13000,
        total_control_cycles_cap=104000,physical_substeps_cap=1040000,training_batches=0,model_forwards=0,
        attempts=attempts(),seed=2026092716,seed_rule='PCG64/SeedSequence([seed,1,case_index])',
        physics_period_s=.0002,control_period_s=.002,policy_period_s=.002,replay_period_s=.002,
        action_scale=[.00015,.00015,.0005,.0005],stop_on_any_guard=True,automatic_retry=False,
        automatic_tracking=False,independent_test=0,old_unused_consumed=0)
def config():
    c=deepcopy(read(ROOT/'deliverables/learning_chain/b2_actor_lr_execution_20260930/candidate.json')['configs']['A'])
    c['version']='temporal_warmup_preflight_v1'
    c['sampling'].update(stop_at='eight_preflight_episodes_or_first_guard',max_attempts=8,
        total_audited_cycles_upper_bound=104000,seed_rule=scope()['seed_rule'])
    c['learning']['max_gradient_batches']=0
    c['execution'].update(preparation_only=False,independent_test_used=False)
    return c
def validate_authorization(r,binding_pin):
    pin(binding_pin)
    if (r.get('version')!='temporal_preflight_authorization_v1' or r.get('approved') is not True or
            r.get('binding_sha256')!=binding_pin or canonical(r.get('scope'))!=canonical(scope()) or
            not isinstance(r.get('user_confirmation'),str) or not r['user_confirmation'].strip()):
        raise ValueError('Exact explicit preflight authorization required')
def require_authorization(binding_pin,auth_pin):
    pin(auth_pin);path=HERE/'authorization.json'
    if digest(path)!=auth_pin:raise ValueError('Authorization changed')
    r=read(path);validate_authorization(r,binding_pin);return r
def verify_parent():
    if digest(DESIGN/'delivery_verification.json')!=DESIGN_PIN:raise ValueError('Prepared sampler seal changed')
    r=read(DESIGN/'delivery_verification.json')
    for key in ('input_sha256','source_sha256','artifact_sha256'):verify_files(r[key])
    if r['status']!='preparation_verified' or r['protocol_passed']!=18 or r['cumulative_dynamic']!=60:
        raise ValueError('Unregistered preparation')
    prior=read(PRIOR/'run/ledger.json')
    if prior['status']!='stopped' or prior['active'] is not None or read(PRIOR/'run/accounting.json')['cumulative_dynamic']!=60:
        raise ValueError('Prior run is not the fixed closed boundary')
def verify_binding(binding_pin,*,with_runtime=False):
    pin(binding_pin)
    if digest(HERE/'binding.json')!=binding_pin:raise ValueError('Preflight binding changed')
    b=read(HERE/'binding.json')
    if (b.get('version')!='temporal_preflight_binding_v1' or b.get('parent_design_sha256')!=DESIGN_PIN or
            canonical(b.get('scope'))!=canonical(scope()) or canonical(b.get('config'))!=canonical(config()) or b.get('protocol_passed') is not True):
        raise ValueError('Unregistered preflight binding')
    verify_parent();verify_files(b['input_sha256'])
    required=[HERE/name for name in ('execution_contract.py','sampling_runtime.py','run_preflight.py','test_protocol.py','protocol_runner.py')]
    required += [DESIGN/'warmup_hold.py',ROOT/'tools/learning/admitted_collection.py',ROOT/'tools/validation/process_parent.py']
    if any(p.relative_to(ROOT).as_posix() not in b['input_sha256'] for p in required):raise ValueError('Required source not bound')
    if with_runtime:
        from tools.validation.verify_residual_interface import qualified_runtime
        from tools.learning.runtime import active_package
        if canonical(qualified_runtime(active_package()))!=canonical(b['runtime']):raise ValueError('Qualified runtime changed')
    return b

def validate_result(r):
    if not isinstance(r,dict) or r.get('completed') is not True:raise ValueError('Complete physical result required')
    identity={k:r.get(k) for k in attempts()[0]}
    if not any(canonical(identity)==canonical(a) for a in attempts()):raise ValueError('Unknown attempt')
    if (any(type(r.get(k)) is not bool for k in ('success','simulation_valid','physical_stopped','guard_hit')) or
            type(r.get('cycles')) is not int or not 0<r['cycles']<=13000 or
            type(r.get('draw_count')) is not int or not 0<=r['draw_count']<=r['cycles'] or
            type(r.get('model_forwards')) is not int or r['model_forwards']!=0 or
            type(r.get('training_batches')) is not int or r['training_batches']!=0 or
            (r['success'] and (r['guard_hit'] or not r['simulation_valid'] or not r['physical_stopped']))):raise ValueError('Invalid outcome or cost')
    canonical(r)

class Ledger:
    def __init__(self,path,state):
        self.path=Path(path);self.state=deepcopy(state);self.live_guard=None;self.write_failed=False;self.validate()
    @classmethod
    def create(cls,path,binding_pin,auth_pin):
        pin(binding_pin);pin(auth_pin)
        r=dict(version='temporal_preflight_ledger_v1',binding_sha256=binding_pin,authorization_sha256=auth_pin,
            scope=scope(),status='healthy',active=None,attempts=[])
        with Path(path).open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.flush();os.fsync(f.fileno())
        return cls(path,r)
    @classmethod
    def load(cls,path,binding_pin,auth_pin):
        r=read(path)
        if r.get('binding_sha256')!=binding_pin or r.get('authorization_sha256')!=auth_pin:raise ValueError('Ledger identity differs')
        return cls(path,r)
    def validate(self):
        s=self.state;pin(s['binding_sha256']);pin(s['authorization_sha256'])
        if s.get('version')!='temporal_preflight_ledger_v1' or canonical(s.get('scope'))!=canonical(scope()) or s.get('status') not in ('healthy','failed','stopped','complete'):
            raise ValueError('Malformed ledger')
        if type(s.get('attempts')) is not list or len(s['attempts'])>8:raise ValueError('Attempt cap differs')
        active=[];terminal=[]
        for i,a in enumerate(s['attempts']):
            if canonical(a.get('identity'))!=canonical(attempts()[i]) or a.get('cycles_reserved')!=13000 or a.get('status') not in ('started','finished','failed'):
                raise ValueError('Attempt order, reservation or status differs')
            if a['status']=='started':active.append(i)
            elif a['status']=='failed':terminal.append(i)
            else:
                validate_result(a['result'])
                if any(a['result'][k]!=v for k,v in attempts()[i].items()):raise ValueError('Result identity differs')
                if a['result']['guard_hit'] or not a['result']['simulation_valid'] or not a['result']['physical_stopped']:terminal.append(i)
        if active!=([s['active']] if s['active'] is not None else []) or (s['active'] is not None and (type(s['active']) is not int or s['active']!=len(s['attempts'])-1)):
            raise ValueError('Active reservation differs')
        if s['status']!='healthy' and active:raise ValueError('Terminal ledger still active')
        if terminal and (terminal!=[len(s['attempts'])-1] or s['status'] not in ('stopped','failed')):raise ValueError('Work after terminal result')
        if s['status']=='stopped':
            if not terminal or s.get('stop_reason')!='preflight_guard':raise ValueError('Guard stop evidence missing')
            r=s['attempts'][-1].get('result',{})
            if not (r.get('guard_hit') and r.get('simulation_valid') and r.get('physical_stopped')):raise ValueError('Controlled stop is not valid and stopped')
        if s['status']=='complete' and (len(s['attempts'])!=8 or active or terminal):raise ValueError('Not all preflight episodes completed')
    def check_live(self):
        if self.write_failed:raise RuntimeError('Prior durable write failed')
        if self.live_guard is not None:self.live_guard()
        if canonical(read(self.path))!=canonical(self.state):raise RuntimeError('Stale ledger owner')
    def commit(self,r):
        self.check_live();Ledger(self.path,r)
        try:write(self.path,r)
        except BaseException:self.write_failed=True;raise
        self.state=r
    def start(self,identity):
        self.check_live();s=self.state;i=len(s['attempts'])
        if s['status']!='healthy' or s['active'] is not None or i>=8 or identity!=attempts()[i]['id']:
            raise RuntimeError('Persistent ordered physical reservation refused')
        r=deepcopy(s);r['attempts'].append(dict(identity=attempts()[i],cycles_reserved=13000,status='started'));r['active']=i;self.commit(r)
    def finish(self,result):
        self.check_live()
        if self.state['status']!='healthy' or self.state['active'] is None:raise RuntimeError('Active reservation required')
        validate_result(result);i=self.state['active']
        if any(result[k]!=v for k,v in attempts()[i].items()):raise ValueError('Wrong result identity')
        r=deepcopy(self.state);r['attempts'][i].update(status='finished',result=deepcopy(result));r['active']=None
        if not result['simulation_valid'] or not result['physical_stopped']:r.update(status='failed',error='invalid_or_unstopped')
        elif result['guard_hit']:r.update(status='stopped',stop_reason='preflight_guard')
        self.commit(r)
    def fail(self,error):
        r=deepcopy(self.state)
        if r['active'] is not None:r['attempts'][r['active']].update(status='failed',error=str(error));r['active']=None
        r.update(status='failed',error=str(error));self.commit(r)
    def complete(self):
        if self.state['status']!='healthy' or self.state['active'] is not None or len(self.state['attempts'])!=8:raise RuntimeError('Eight audited episodes required')
        r=deepcopy(self.state);r['status']='complete';self.commit(r)
    def accounting(self):
        n=len(self.state['attempts']);finished=[a['result'] for a in self.state['attempts'] if a['status']=='finished']
        return dict(previous_dynamic=60,new_dynamic_starts=n,cumulative_dynamic=60+n,cumulative_dynamic_cap=68,
            unused_new_dynamic=8-n,control_cycles_reserved=13000*n,control_cycles_confirmed=sum(a['cycles'] for a in finished),
            random_draw_vectors_confirmed=sum(a['draw_count'] for a in finished),training_batches=0,model_forwards=0,
            replay_committed=0,independent_test=0,old_unused_consumed=0,status=self.state['status'])
