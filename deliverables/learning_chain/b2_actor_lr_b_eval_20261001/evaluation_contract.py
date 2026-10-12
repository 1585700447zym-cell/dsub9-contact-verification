"""Independent, frozen-B evaluation authorization and durable start budget."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from tools.learning.actor_lr_contract import (read,digest,valid_pin,verify_files,verify_candidate,
    require_authorization as parent_authorization,execution_config,DELIVERY as PARENT,CASE_NAMES)
PARENT_PIN='79a9bd0084f871e2ab6c6b24ff96ac69a772aa0e9e53003205866a31c11d2fba'
PARENT_AUTH='3b2fc9f34643df5385158dc498f996535497afa93ed50082b8a9da94c40d6a1f'
B_PIN='4030ec22b8e78bcc9b255fdbade03184068b6cc59befddbf00a7462040fa3a04'
B_STATE='9bc6f5cfb3eb91da0e23aaa3048612b7a840fa0ba6b6c9e2e3401d1ef0084059'

def scope():
    return dict(branch='B',checkpoint_manifest_sha256=B_PIN,checkpoint_state_sha256=B_STATE,
        cases=list(CASE_NAMES),dynamic_cap=4,previous_dynamic=58,cumulative_dynamic_cap=62,
        cycles_per_start=13000,actor_state_cap=52000,training_batches=0,synthetic_transactions=0,
        extra_diagnostic_states=0,extra_critic_states=0,independent_test=0,
        old_unused_dynamic=19,old_unused_batches=2000,comparison_unused_dynamic=7,
        old_unused_consumed=0,stop_on_any_guard=True,automatic_retry=False,automatic_tracking=False)

def validate_authorization(record,binding_pin):
    valid_pin(binding_pin)
    if (record.get('version')!='frozen_B_evaluation_authorization_v1' or record.get('approved') is not True
        or record.get('binding_sha256')!=binding_pin or record.get('scope')!=scope()
        or not isinstance(record.get('user_confirmation'),str) or not record['user_confirmation'].strip()):
        raise ValueError('Explicit exact frozen-B evaluation authorization required')

def require_authorization(binding_pin,authorization_pin,*,folder=HERE):
    valid_pin(authorization_pin);path=Path(folder)/'authorization.json'
    if not path.exists() or digest(path)!=authorization_pin:raise ValueError('Missing or changed authorization')
    record=read(path);validate_authorization(record,binding_pin);return record

def verify_binding(binding_pin,*,with_runtime=False):
    valid_pin(binding_pin);path=HERE/'binding.json'
    if digest(path)!=binding_pin:raise ValueError('Evaluation binding changed')
    r=read(path)
    if (r.get('version')!='frozen_B_evaluation_binding_v1' or r.get('scope')!=scope()
        or r.get('config')!=execution_config('B') or r.get('parent_candidate_sha256')!=PARENT_PIN
        or r.get('parent_authorization_sha256')!=PARENT_AUTH or r.get('protocol_passed') is not True):
        raise ValueError('Unregistered frozen-B binding')
    verify_candidate(PARENT_PIN,check_runtime=with_runtime);parent_authorization(PARENT_PIN,PARENT_AUTH)
    verify_files(r['inputs_sha256'])
    required=[HERE/'evaluation_contract.py',HERE/'run_evaluation.py',HERE/'test_protocol.py',HERE/'protocol_runner.py',
        PARENT/'run/checkpoint_B/manifest.json',PARENT/'run/checkpoint_B/state.pt',PARENT/'run/ledger.json',
        PARENT/'run/accounting.json',PARENT/'run_analysis/execution_audit.json',PARENT/'run_analysis/delivery_verification.json']
    if any(p.relative_to(ROOT).as_posix() not in r['inputs_sha256'] for p in required):
        raise ValueError('Required bound input missing')
    if digest(required[4])!=B_PIN or digest(required[5])!=B_STATE:raise ValueError('Frozen B differs')
    prior=read(PARENT/'run/ledger.json');cost=read(PARENT/'run/accounting.json')
    if (prior['status']!='stopped' or prior['stop_reason']!='evaluation_guard' or prior['active'] is not None
        or cost['cumulative_dynamic_starts']!=58 or (PARENT/'run/evaluation_B').exists()):
        raise ValueError('Prior run is not the registered completed stop')
    return r

def write(path,value):
    from tools.learning.admitted_collection import _write_json
    _write_json(path,value)

def validate_result(r):
    if (not isinstance(r,dict) or r.get('completed') is not True
        or any(type(r.get(k)) is not bool for k in ('success','simulation_valid','physical_stopped','guard_hit'))
        or type(r.get('cycles')) is not int or not 0<r['cycles']<=13000
        or type(r.get('actor_states')) is not int or r['actor_states']!=r['cycles']
        or (r['success'] and (r['guard_hit'] or not r['simulation_valid'] or not r['physical_stopped']))):
        raise ValueError('Complete consistent frozen physical result required')
    json.dumps(r,allow_nan=False)

class Ledger:
    def __init__(self,path,state):
        self.path=Path(path);self.state=deepcopy(state);self.live_guard=None;self.write_failed=False
        self._validate()

    @classmethod
    def create(cls,path,binding_pin,auth_pin):
        valid_pin(binding_pin);valid_pin(auth_pin)
        state=dict(version='frozen_B_evaluation_ledger_v1',candidate_sha256=binding_pin,
            authorization_sha256=auth_pin,scope=scope(),status='healthy',active=None,attempts=[])
        with Path(path).open('x',encoding='utf-8') as stream:
            json.dump(state,stream,ensure_ascii=False,indent=2);stream.flush();os.fsync(stream.fileno())
        return cls(path,state)

    @classmethod
    def load(cls,path,binding_pin,auth_pin):
        valid_pin(binding_pin);valid_pin(auth_pin);state=read(path)
        if state.get('candidate_sha256')!=binding_pin or state.get('authorization_sha256')!=auth_pin:
            raise ValueError('Ledger identity differs')
        return cls(path,state)

    def _validate(self):
        s=self.state;valid_pin(s.get('candidate_sha256'));valid_pin(s.get('authorization_sha256'))
        if (s.get('version')!='frozen_B_evaluation_ledger_v1' or s.get('scope')!=scope()
            or s.get('status') not in ('healthy','stopped','failed','complete')
            or not isinstance(s.get('attempts'),list) or len(s['attempts'])>4):raise ValueError('Malformed ledger')
        active=[];terminal=[]
        for i,r in enumerate(s['attempts']):
            if r.get('case')!=CASE_NAMES[i] or r.get('actor_states_reserved')!=13000 or r.get('status') not in ('started','finished','failed'):
                raise ValueError('Unregistered attempt order or reservation')
            if r['status']=='started':active.append(i)
            elif r['status']=='failed':terminal.append(i)
            else:
                validate_result(r.get('result'))
                if r['result']['guard_hit'] or not r['result']['simulation_valid'] or not r['result']['physical_stopped']:terminal.append(i)
        if ((s['active'] is not None and (type(s['active']) is not int or s['active']!=len(s['attempts'])-1))
            or active!=([s['active']] if s['active'] is not None else [])):
            raise ValueError('Active reservation differs')
        if terminal and (terminal!=[len(s['attempts'])-1] or s['status'] not in ('stopped','failed')):
            raise ValueError('Computation after terminal outcome')
        if s['status']!='healthy' and active:raise ValueError('Terminal ledger still active')
        if s['status']=='stopped':
            if not terminal or s.get('stop_reason')!='evaluation_guard':raise ValueError('Stop evidence missing')
            r=s['attempts'][-1].get('result',{})
            if not (r.get('guard_hit') and r.get('simulation_valid') and r.get('physical_stopped')):
                raise ValueError('Controlled stop requires valid stopped guard')
        if s['status']=='complete' and (len(s['attempts'])!=4 or terminal or active):raise ValueError('Incomplete evaluation')

    def check_live(self):
        if self.write_failed:raise RuntimeError('Prior ledger write failed')
        if self.live_guard is not None:self.live_guard()
        if read(self.path)!=self.state:raise RuntimeError('Stale ledger owner or modified budget')

    def _commit(self,state):
        self.check_live();Ledger(self.path,state)
        try:write(self.path,state)
        except BaseException:self.write_failed=True;raise
        self.state=state

    def start(self,case):
        self.check_live();s=self.state
        if s['status']!='healthy' or s['active'] is not None or len(s['attempts'])>=4 or case!=CASE_NAMES[len(s['attempts'])]:
            raise RuntimeError('Healthy ordered start required')
        new=deepcopy(s);new['active']=len(new['attempts'])
        new['attempts'].append(dict(case=case,status='started',actor_states_reserved=13000));self._commit(new)

    def finish(self,result):
        self.check_live();validate_result(result)
        if self.state['status']!='healthy' or self.state['active'] is None:raise RuntimeError('No active evaluation')
        new=deepcopy(self.state);new['attempts'][new['active']].update(status='finished',result=deepcopy(result));new['active']=None
        if not result['simulation_valid'] or not result['physical_stopped']:new.update(status='failed',error='invalid_or_unstopped')
        elif result['guard_hit']:new.update(status='stopped',stop_reason='evaluation_guard')
        self._commit(new)

    def fail(self,error):
        if self.state['status'] in ('stopped','complete'):return
        new=deepcopy(self.state)
        if new['active'] is not None:new['attempts'][new['active']].update(status='failed',error=str(error));new['active']=None
        new.update(status='failed',error=str(error));self._commit(new)

    def complete(self):
        self.check_live()
        if self.state['status']!='healthy' or self.state['active'] is not None or len(self.state['attempts'])!=4:
            raise RuntimeError('Four completed attempts required')
        new=deepcopy(self.state);new['status']='complete';self._commit(new)

    def accounting(self):
        self._validate();n=len(self.state['attempts'])
        return dict(previous_dynamic=58,new_dynamic_starts=n,cumulative_dynamic=58+n,cumulative_dynamic_cap=62,
            unused_new_dynamic=4-n,actor_states_reserved=13000*n,
            actor_states_confirmed=sum(r.get('result',{}).get('actor_states',0) for r in self.state['attempts']),
            training_batches=0,extra_diagnostic_states=0,independent_test=0,old_unused_consumed=0,status=self.state['status'])
