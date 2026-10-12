"""Pure PC13 scope/one-claim accounting. Does not import torch/native code."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,os,re,sys,time,uuid
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
PC12=OUT.parent/'small_boundary_execution_20261007'
PC12_SEAL='702c5fe5138fa2621cf17b4cb5d3c441c84b1a506f7803a8492e3691ffab3ad8'
sys.path.insert(0,str(PC12));sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(OUT)) # stage helpers win over same-named sealed PC12 scripts
from small_bound_profile import outer_contract,validate_outer_contract

LIMITS=dict(synthetic_update_batches=4,test_state_forward_evaluations=32,dynamic_episodes=0,formal_update_batches=0,
            whole_wall_s=1200,reader_wall_s=300)
ROLE_CAPS={'parent':{'update':3,'forward':16},'reader':{'update':1,'forward':16}}
CLAIMS=OUT/'numeric_claims'


def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def digest(x):return hashlib.sha256(canonical(x).encode()).hexdigest()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,value):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);stage=p.with_name(p.name+'.write-'+uuid.uuid4().hex)
    with stage.open('x',encoding='utf8') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
    os.replace(stage,p)
def exclusive(p,value):
    p=Path(p)
    with p.open('x',encoding='utf8') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())


def profile_contract():
    if sha(PC12/'delivery_manifest.json')!=PC12_SEAL:raise ValueError('PC12 sealed adapter changed')
    for name in ('small_bound_profile.py','small_bound_session.py','small_bound_learning.py','run_small_bound_pilot.py'):
        if sha(PC12/name)!=read(PC12/'delivery_manifest.json')['files'][name]['sha256']:raise ValueError('PC12 adapter code changed')
    return outer_contract()
def profile_pin():return validate_outer_contract(profile_contract())


def verify_numeric_authorization(candidate,grant,expected_grant_digest):
    if (not isinstance(grant,dict) or digest(grant)!=expected_grant_digest or
        grant.get('version')!='pc13_numeric_authorization_v1' or grant.get('explicit_user_authorized') is not True or
        grant.get('scope')!='synthetic_numeric_only' or grant.get('status')!='OPEN' or
        grant.get('prior_dynamic')!=208 or canonical(grant.get('limits'))!=canonical(LIMITS)):
        raise PermissionError('Explicit new 4/32 synthetic-only authorization and out-of-band pin required')
    if (candidate.get('version')!='pc13_numeric_candidate_v1' or candidate.get('status')!='PREPARED_NOT_AUTHORIZED' or
        candidate.get('training_admitted') is not False or candidate.get('dynamic_authorized') is not False or
        canonical(candidate.get('limits'))!=canonical(LIMITS) or
        candidate.get('profile_sha256')!=profile_pin() or
        canonical(candidate.get('outer_contract'))!=canonical(profile_contract()) or
        grant.get('candidate_sha256')!=digest(candidate) or grant.get('profile_sha256')!=candidate['profile_sha256']):
        raise ValueError('Candidate/profile/scope binding differs')
    return dict(candidate_sha256=digest(candidate),authorization_sha256=expected_grant_digest,profile_sha256=profile_pin())


def verify_runtime_files(pins):
    for path,pin in pins.items():
        if sha(path)!=pin:raise ValueError('CPU runtime file changed: '+path)
    return len(pins)


class NumericLedger:
    @classmethod
    def create(cls,folder,candidate,grant,grant_pin):
        binding=verify_numeric_authorization(candidate,grant,grant_pin);folder=Path(folder).resolve()
        if folder.exists():raise FileExistsError('Never reopen a numeric run')
        CLAIMS.mkdir(parents=True,exist_ok=True);claim=CLAIMS/grant_pin
        claim.mkdir() # global exclusive claim; setup failures consume the grant
        exclusive(claim/'identity.json',dict(**binding,folder=str(folder)))
        (claim/'events').mkdir();folder.mkdir(parents=True)
        data=dict(version='pc13_numeric_ledger_v1',binding=binding,status='open',phase='parent',reader_claimed=False,
            request_pin=None,active=None,updates_attempted=0,updates_completed=0,forwards_attempted=0,forwards_completed=0,
            role_attempts={r:{k:0 for k in ('update','forward')} for r in ROLE_CAPS},
            role_completed={r:{k:0 for k in ('update','forward')} for r in ROLE_CAPS},
            started_wall=time.time(),results=[],closed_unused=None)
        write(folder/'ledger.json',data)
        return cls.load(folder/'ledger.json',candidate,grant,grant_pin)

    @classmethod
    def load(cls,path,candidate,grant,grant_pin):
        obj=object.__new__(cls);obj.path=Path(path).resolve();obj.candidate=deepcopy(candidate)
        obj.grant=deepcopy(grant);obj.grant_pin=grant_pin;obj.claim=CLAIMS/grant_pin
        binding=verify_numeric_authorization(candidate,grant,grant_pin)
        identity=read(obj.claim/'identity.json')
        if identity!={**binding,'folder':str(obj.path.parent)}:raise ValueError('Reader must reuse the one authorized ledger')
        obj.data=read(obj.path)
        if obj.data['binding']!=binding:raise ValueError('Ledger binding changed')
        obj._audit_events();return obj

    def _events(self):
        attempts={r:{k:0 for k in ('update','forward')} for r in ROLE_CAPS};completed=deepcopy(attempts)
        pending=[];results=[]
        for p in (self.claim/'events').glob('*.claim.json'):
            event=read(p);role=event['role'];kind=event['kind'];number=event['ordinal']
            if role not in ROLE_CAPS or kind not in ROLE_CAPS[role] or type(number) is not int or not 1<=number<=ROLE_CAPS[role][kind] or p.name!=f'{role}-{kind}-{number}.claim.json':
                raise ValueError('Invalid durable numeric attempt')
            attempts[role][kind]+=1;done=p.with_suffix('.complete.json')
            if done.exists():
                if read(done)!=event:raise ValueError('Completion receipt changed')
                completed[role][kind]+=1
                results.append(event)
            else:pending.append(event)
        return attempts,completed,pending,results

    def _audit_events(self):
        attempts,completed,_,_=self._events()
        if attempts!=self.data['role_attempts'] or completed!=self.data['role_completed']:
            raise ValueError('Numeric projection differs from durable attempt/completion receipts')
        for kind,a,b in [('update','updates_attempted','updates_completed'),('forward','forwards_attempted','forwards_completed')]:
            if self.data[a]!=sum(v[kind] for v in attempts.values()) or self.data[b]!=sum(v[kind] for v in completed.values()):raise ValueError('Actual numeric count differs')

    @classmethod
    def recover_failed(cls,path,candidate,grant,grant_pin,error):
        """Rebuild only a CLOSED projection from receipts; never resume work."""
        obj=object.__new__(cls);obj.path=Path(path).resolve();obj.claim=CLAIMS/grant_pin
        binding=verify_numeric_authorization(candidate,grant,grant_pin)
        if read(obj.claim/'identity.json')!={**binding,'folder':str(obj.path.parent)}:
            raise ValueError('Failure recovery requires the original global claim')
        attempts,completed,pending,results=obj._events()
        try:obj.data=read(obj.path)
        except (OSError,ValueError):obj.data={}
        obj.data.update(version='pc13_numeric_ledger_v1',binding=binding,status='closed',phase='failure_only',
            error=str(error),active=None,role_attempts=attempts,role_completed=completed,results=results,
            unacknowledged_transactions=pending,actual_completion_unknown=bool(pending))
        for kind,a,b in [('update','updates_attempted','updates_completed'),('forward','forwards_attempted','forwards_completed')]:
            obj.data[a]=sum(v[kind] for v in attempts.values());obj.data[b]=sum(v[kind] for v in completed.values())
        obj.data['completion_bounds']={kind:[obj.data[b],obj.data[a]] for kind,a,b in (
            ('update','updates_attempted','updates_completed'),('forward','forwards_attempted','forwards_completed'))}
        obj.data['unused_closed']=dict(updates=4-obj.data['updates_attempted'],forwards=32-obj.data['forwards_attempted'])
        write(obj.path,obj.data);return obj

    def _check(self,allow_expired=False):
        if read(self.path)!=self.data:raise ValueError('Numeric ledger changed outside this owner')
        self._audit_events()
        if self.data['status']!='open':raise RuntimeError('Closed numeric quota cannot be reopened')
        if not allow_expired and time.time()-self.data['started_wall']>LIMITS['whole_wall_s']:raise RuntimeError('Numeric wall limit reached')

    def reserve(self,role,kind):
        self._check()
        if self.data['active'] is not None:raise RuntimeError('Unresolved transaction; never retry')
        if role not in ROLE_CAPS or kind not in ROLE_CAPS[role] or self.data['phase']!=role:
            raise PermissionError('Numeric role does not own this phase')
        n=self.data['role_attempts'][role][kind]+1
        if n>ROLE_CAPS[role][kind]:raise ValueError('Role numeric quota exhausted')
        event=dict(role=role,kind=kind,ordinal=n,token=uuid.uuid4().hex)
        exclusive(self.claim/'events'/f'{role}-{kind}-{n}.claim.json',event)
        self.data['role_attempts'][role][kind]+=1
        self.data['updates_attempted' if kind=='update' else 'forwards_attempted']+=1
        self.data['active']=event;write(self.path,self.data)
        return event['token']

    def complete(self,token):
        self._check(allow_expired=True);event=self.data['active']
        if not event or event['token']!=token:raise ValueError('Exact pending transaction required')
        p=self.claim/'events'/f"{event['role']}-{event['kind']}-{event['ordinal']}.claim.json"
        exclusive(p.with_suffix('.complete.json'),event)
        self.data['role_completed'][event['role']][event['kind']]+=1
        self.data['updates_completed' if event['kind']=='update' else 'forwards_completed']+=1
        self.data['results'].append(deepcopy(event));self.data['active']=None;write(self.path,self.data)

    def ready_reader(self,request_pin):
        self._check()
        if self.data['phase']!='parent' or self.data['active'] or self.data['role_completed']['parent']!=ROLE_CAPS['parent']:
            raise ValueError('Reader starts only after the exact parent work is complete')
        self.data.update(phase='reader_ready',request_pin=request_pin);write(self.path,self.data)

    def claim_reader(self,request_pin,process_proof=None):
        self._check()
        if self.data['reader_claimed']:raise FileExistsError('Reader is never restarted')
        if self.data['phase']!='reader_ready' or request_pin!=self.data['request_pin']:raise PermissionError('Registered reader request required')
        exclusive(self.claim/'reader_claim.json',dict(request_pin=request_pin,pid=os.getpid(),process_proof=process_proof))
        self.data.update(phase='reader',reader_claimed=True);write(self.path,self.data)

    def fail(self,error):
        self.data.update(status='closed',error=str(error),unused_closed=dict(updates=4-self.data['updates_attempted'],forwards=32-self.data['forwards_attempted']))
        write(self.path,self.data)

    def finish(self):
        self._check()
        if self.data['active'] or self.data['role_completed']!=ROLE_CAPS:raise ValueError('Incomplete numeric matrix')
        self.data.update(status='complete',unused_closed=dict(updates=0,forwards=0));write(self.path,self.data)
