"""Single-owner durable reservations; exceptions consume attempts and stop work."""
from copy import deepcopy
import json
import os
from pathlib import Path
from .actor_lr_contract import compute_budget,valid_pin,CASE_NAMES
from .admitted_collection import _write_json as write


class ComparisonLedger:
    @classmethod
    def create(cls,path,candidate_pin,authorization_pin):
        valid_pin(candidate_pin);valid_pin(authorization_pin)
        state=dict(version='actor_lr_budget_v1',candidate_sha256=candidate_pin,authorization_sha256=authorization_pin,
            budget=compute_budget(),phase='validation',status='healthy',active=None,attempts=[],gates={})
        path=Path(path)
        with path.open('x',encoding='utf-8') as stream:
            json.dump(state,stream,ensure_ascii=False,allow_nan=False,indent=2);stream.flush();os.fsync(stream.fileno())
        return cls(path,state)

    @classmethod
    def load(cls,path,candidate_pin,authorization_pin):
        valid_pin(candidate_pin);valid_pin(authorization_pin)
        state=json.loads(Path(path).read_text(encoding='utf-8'))
        result=cls(Path(path),state)
        if state.get('candidate_sha256')!=candidate_pin or state.get('authorization_sha256')!=authorization_pin:
            raise ValueError('Budget authorization differs')
        result._validate();return result

    def __init__(self,path,state):
        self.path=Path(path);self.state=deepcopy(state);self._write_failed=False;self.execution_guard=None

    def set_execution_guard(self,check):
        if not callable(check):raise TypeError('Live supervisor guard required')
        self.execution_guard=check

    def check_execution(self):
        if self.execution_guard is not None:
            self.execution_guard()
            if json.loads(self.path.read_text(encoding='utf-8'))!=self.state:
                raise RuntimeError('Comparison durable owner state changed')

    def _count(self,kind,branch,*,finished=False):
        return sum(row['units'] for row in self.state['attempts'] if row['kind']==kind and row['branch']==branch
            and (not finished or row['status']=='finished'))

    def _validate(self):
        s=self.state
        if (s.get('version')!='actor_lr_budget_v1' or s.get('budget')!=compute_budget() or
            s.get('status') not in ('healthy','failed','stopped','complete') or
            s.get('phase') not in ('validation','A_training','B_training','diagnostic','evaluation','complete','stopped','failed') or
            not isinstance(s.get('attempts'),list) or not isinstance(s.get('gates'),dict)):
            raise ValueError('Malformed comparison ledger')
        if s['active'] is not None and (type(s['active']) is not int or not 0<=s['active']<len(s['attempts'])):
            raise ValueError('Malformed active reservation')
        identities=set();active=[];ordered={};rank=-1
        ranks={('synthetic','shared'):0,('test_forward','shared'):0,('formal','A'):1,('formal','B'):2,
            ('diagnostic','initial'):3,('diagnostic','A'):3,('diagnostic','B'):3,('physical','A'):4,('physical','B'):5}
        for i,row in enumerate(s['attempts']):
            try:
                cap=self._cap(row['kind'],row['branch'])
                identity=(row['kind'],row['branch'],row['identity'])
                valid=type(row['units']) is int and 0<row['units']<=cap and isinstance(row['identity'],str) and row['identity']
            except (KeyError,TypeError,ValueError):valid=False
            if not valid or identity in identities or row.get('status') not in ('started','finished','failed'):
                raise ValueError('Malformed or duplicate charged attempt')
            identities.add(identity)
            if row['status']=='started':active.append(i)
            role=(row['kind'],row['branch']);position=ordered.get(role,0);row_rank=ranks[role]
            if row_rank<rank:raise ValueError('Attempt stage order differs')
            rank=row_rank;ordered[role]=position+row['units']
            if row['status']=='finished' and (not isinstance(row.get('result'),dict) or row['result'].get('completed') is not True):
                raise ValueError('Missing completed operation result')
            if row['kind'] in ('formal','physical'):
                expected=f'batch_{position:03d}' if row['kind']=='formal' else CASE_NAMES[position] if position<4 else None
                if row['units']!=1 or row['identity']!=expected:raise ValueError('Individual registered update/start order required')
            if row['kind']=='physical' and row['status']=='finished' and any(type(row['result'].get(k)) is not bool
                for k in ('simulation_valid','physical_stopped','guard_hit','success')):raise ValueError('Incomplete physical outcome')
        if active!=([s['active']] if s['active'] is not None else []):raise ValueError('Active attempt differs')
        for kind,roles in (('formal',('A','B')),('physical',('A','B')),('diagnostic',('initial','A','B')),
                           ('synthetic',('shared',)),('test_forward',('shared',))):
            for role in roles:
                if self._count(kind,role)>self._cap(kind,role):raise ValueError('Charged budget exceeds hard cap')
        gates=s['gates']
        if set(gates)-{'real_validation','a_reproduced','b_frozen','diagnostics','evaluation_checkpoints'}:raise ValueError('Unknown gate')
        for name in ('real_validation','a_reproduced','b_frozen','diagnostics'):
            if name in gates:valid_pin(gates[name])
        level={'validation':0,'A_training':1,'B_training':2,'diagnostic':3,'evaluation':4,'complete':5,
               'failed':rank,'stopped':rank}[s['phase']]
        if 'a_reproduced' in gates:level=max(level,2)
        if 'b_frozen' in gates:level=max(level,3)
        if 'evaluation_checkpoints' in gates:level=max(level,4)
        level=max(level,rank)
        if level>=1 and 'real_validation' not in gates:raise ValueError('Real validation gate missing')
        if level>=2 and ('a_reproduced' not in gates or self._count('formal','A',finished=True)!=500):raise ValueError('Exact A gate missing')
        if level>=3 and ('b_frozen' not in gates or self._count('formal','B',finished=True)!=500):raise ValueError('Fixed B gate missing')
        if level>=4:
            pins=gates.get('evaluation_checkpoints')
            if 'diagnostics' not in gates or not isinstance(pins,dict) or set(pins)!={'A','B'} or any(self._count('diagnostic',r,finished=True)!=256
                for r in ('initial','A','B')):raise ValueError('Complete diagnostic/checkpoint gate missing')
            for pin in pins.values():valid_pin(pin)
        expected_phase=('evaluation' if 'evaluation_checkpoints' in gates else 'diagnostic' if 'b_frozen' in gates else
                        'B_training' if 'a_reproduced' in gates else 'A_training' if 'real_validation' in gates else 'validation')
        if s['status']=='healthy' and s['phase']!=expected_phase:raise ValueError('Healthy phase differs from completed gates')
        if self._count('physical','B') and self._count('physical','A',finished=True)!=4:raise ValueError('A evaluation incomplete')
        terminal=[r for r in s['attempts'] if r['status']=='failed' or (r['kind']=='physical' and r['status']=='finished' and
            (r['result']['guard_hit'] or not r['result']['simulation_valid'] or not r['result']['physical_stopped']))]
        if terminal and (s['status'] not in ('failed','stopped') or terminal!=[s['attempts'][-1]]):raise ValueError('Attempt after a stopping outcome')
        if (s['status']=='healthy' and s['phase'] in ('failed','stopped','complete')) or (
            s['status'] in ('failed','stopped','complete') and s['phase']!=s['status']):raise ValueError('Status/phase differs')
        if s['phase']=='complete' and any(self._count('physical',r,finished=True)!=4 for r in ('A','B')):raise ValueError('Incomplete final evaluation')

    def assert_binding(self,candidate_pin,authorization_pin,branch,completed):
        self._healthy()
        if (self.state['candidate_sha256']!=candidate_pin or self.state['authorization_sha256']!=authorization_pin or
            self.state['phase']!=branch+'_training' or self._count('formal',branch)!=completed or
            self._count('formal',branch,finished=True)!=completed):raise ValueError('Branch state and durable authorization/attempts differ')

    @staticmethod
    def _cap(kind,branch):
        b=compute_budget()
        if kind in ('formal','physical','diagnostic') and branch in b[kind]:return b[kind][branch]
        if kind in ('synthetic','test_forward') and branch=='shared':return b[kind]
        raise ValueError('Unknown comparison budget category or branch')

    def _healthy(self):
        if self._write_failed or self.state['status']!='healthy' or self.state['active'] is not None:
            raise RuntimeError('Unhealthy or unfinished budget boundary')
        self.check_execution();self._validate()

    def _commit(self,new):
        if self._write_failed:raise RuntimeError('Previous budget write failed')
        ComparisonLedger(self.path,new)._validate()
        if self.execution_guard is not None and json.loads(self.path.read_text(encoding='utf-8'))!=self.state:
            raise RuntimeError('Comparison durable owner state changed')
        try:write(self.path,new)
        except BaseException:
            self._write_failed=True
            raise
        self.state=new

    def reserve(self,kind,branch,identity,*,units=1):
        self._healthy();cap=self._cap(kind,branch)
        if type(units) is not int or units<=0:raise ValueError('Positive integer reservation required')
        phase=self.state['phase']
        allowed=(kind in ('synthetic','test_forward') and phase=='validation') or (
            kind=='formal' and phase==branch+'_training') or (kind=='diagnostic' and phase=='diagnostic') or (
            kind=='physical' and phase=='evaluation')
        if (not allowed or not isinstance(identity,str) or not identity or self._count(kind,branch)+units>cap or
            any((r['kind'],r['branch'],r['identity'])==(kind,branch,identity) for r in self.state['attempts'])):
            raise RuntimeError('Comparison gate, cap or duplicate attempt refused')
        if kind in ('formal','physical') and units!=1:raise ValueError('Each update/start must be reserved separately')
        if kind=='formal' and identity!=f'batch_{self._count(kind,branch):03d}':
            raise RuntimeError('Registered batch order required')
        if kind=='physical':
            if identity!=CASE_NAMES[self._count(kind,branch)]:raise RuntimeError('Registered evaluation point order required')
            if branch=='B' and self._count('physical','A',finished=True)!=4:
                raise RuntimeError('A evaluation incomplete')
        new=deepcopy(self.state)
        token=len(new['attempts']);new['attempts'].append(dict(kind=kind,branch=branch,identity=identity,units=units,status='started'))
        new['active']=token;self._commit(new);return token

    def finish(self,token,result):
        if self._write_failed or type(token) is not int or token!=self.state['active'] or not isinstance(result,dict):
            raise RuntimeError('Matching active reservation required')
        if result.get('completed') is not True:raise ValueError('Explicit completed operation required')
        self.check_execution()
        row=self.state['attempts'][token]
        if row['kind']=='physical' and any(type(result.get(k)) is not bool for k in ('simulation_valid','physical_stopped','guard_hit','success')):
            raise ValueError('Complete physical outcome required')
        new=deepcopy(self.state);new['attempts'][token].update(status='finished',result=deepcopy(result));new['active']=None
        if row['kind']=='physical':
            if not result['simulation_valid'] or not result['physical_stopped']:
                new.update(status='failed',phase='failed',stop_reason='invalid_or_unstopped_evaluation')
            elif result['guard_hit']:
                new.update(status='stopped',phase='stopped',stop_reason='evaluation_guard')
        self._commit(new)

    def _gate(self,phase,name,pin,next_phase):
        self._healthy();valid_pin(pin)
        if self.state['phase']!=phase or name in self.state['gates']:raise RuntimeError('Gate order or duplicate gate refused')
        new=deepcopy(self.state);new['gates'][name]=pin;new['phase']=next_phase;self._commit(new)

    def complete_validation(self,pin):self._gate('validation','real_validation',pin,'A_training')

    def reproduce_a(self,pin):
        if self._count('formal','A',finished=True)!=500:raise RuntimeError('Exact A learning gate requires all 500 completed batches')
        self._gate('A_training','a_reproduced',pin,'B_training')

    def freeze_b(self,pin):
        if self._count('formal','B',finished=True)!=500:raise RuntimeError('Fixed B checkpoint requires all 500 completed batches')
        self._gate('B_training','b_frozen',pin,'diagnostic')

    def begin_evaluation(self,pins,diagnostics_pin):
        self._healthy()
        if (self.state['phase']!='diagnostic' or not isinstance(pins,dict) or set(pins)!=set(('A','B')) or
            any(self._count('diagnostic',role,finished=True)!=256 for role in ('initial','A','B'))):
            raise RuntimeError('Complete fixed diagnostics before evaluation required')
        for pin in pins.values():valid_pin(pin)
        valid_pin(diagnostics_pin)
        new=deepcopy(self.state);new['gates'].update(evaluation_checkpoints=deepcopy(pins),diagnostics=diagnostics_pin)
        new['phase']='evaluation';self._commit(new)

    def complete(self):
        self._healthy()
        if self.state['phase']!='evaluation' or any(self._count('physical',role,finished=True)!=4 for role in ('A','B')):
            raise RuntimeError('All eight retained evaluation attempts required')
        new=deepcopy(self.state);new.update(status='complete',phase='complete');self._commit(new)

    def fail(self,error):
        if self.state['status'] in ('stopped','complete'):return
        new=deepcopy(self.state)
        if new['active'] is not None:new['attempts'][new['active']].update(status='failed',error=str(error));new['active']=None
        new.update(status='failed',phase='failed',error=str(error));self._commit(new)

    def accounting(self):
        self._validate();dynamic=sum(self._count('physical',role) for role in ('A','B'))
        return dict(previous_dynamic=57,new_dynamic_starts=dynamic,cumulative_dynamic_starts=57+dynamic,
            cumulative_dynamic_cap=65,formal={role:self._count('formal',role) for role in ('A','B')},
            synthetic=self._count('synthetic','shared'),test_forward_states=self._count('test_forward','shared'),
            diagnostic_states={role:self._count('diagnostic',role) for role in ('initial','A','B')},
            status=self.state['status'],phase=self.state['phase'],old_unused_consumed=0,automatic_retry=False)
