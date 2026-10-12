"""Narrow, separately authorized reconstruction capability; no scientific imports."""
from contextlib import contextmanager
import hashlib,json,os,time
from pathlib import Path
from joint_contract import OUT,ROOT,read,write,digest,sha,canonical
LIMITS=dict(learner_constructions=2,tensor_loads=2,checkpoint_saves=1,deterministic_forwards=2,archive_rebuilds=8,
    physical_episodes=0,formal_updates=0,new_experience=0)
ROLE_LIMITS={role:dict(learner_constructions=1,tensor_loads=1,checkpoint_saves=int(role=='parent'),deterministic_forwards=1,archive_rebuilds=4,
    physical_episodes=0,formal_updates=0,new_experience=0) for role in ('parent','reader')}
WHOLE_WALL_S=1800
READER_WALL_S=900

def verify_grant(candidate,grant,pin,binding_pin):
    if (digest(grant)!=pin or grant.get('version')!='b2_warm_restore_grant_v1' or grant.get('status')!='OPEN' or
        grant.get('explicit_user_authorized') is not True or not isinstance(grant.get('human_evidence'),str) or not grant['human_evidence'].strip()):
        raise PermissionError('New explicit reconstruction grant required')
    if (grant.get('candidate_sha256')!=digest(candidate) or grant.get('binding_sha256')!=binding_pin or
        canonical(grant.get('limits'))!=canonical(LIMITS) or grant.get('cumulative_before')!=245 or
        grant.get('whole_wall_s')!=WHOLE_WALL_S or grant.get('reader_wall_s')!=READER_WALL_S or
        candidate.get('status')!='PREPARED_NOT_AUTHORIZED' or candidate.get('training_admitted') is not False or candidate.get('numeric_verified') is not False):
        raise ValueError('Wrong reconstruction scope/source/candidate')

class Counter:
    def __init__(self,path):self.path=Path(path)
    @classmethod
    def create(cls,path):
        path=Path(path)
        with path.open('x',encoding='utf8') as f:
            f.write(canonical(dict(status='OPEN',started=time.time(),deadline=time.monotonic()+WHOLE_WALL_S,limits=LIMITS,
                attempted={k:0 for k in LIMITS},roles={r:dict(claimed=False,attempted={k:0 for k in LIMITS}) for r in ROLE_LIMITS})))
            f.flush();os.fsync(f.fileno())
        return cls(path)
    @contextmanager
    def locked(self):
        lock=self.path.with_suffix('.lock');end=time.monotonic()+.5
        while True:
            try:fd=os.open(lock,os.O_WRONLY|os.O_CREAT|os.O_EXCL);break
            except FileExistsError:
                if time.monotonic()>=end:raise TimeoutError('Counter lock unavailable; no retry of computation')
                time.sleep(.005)
        try:
            os.close(fd);yield
        finally:lock.unlink()
    def checked(self):
        d=read(self.path)
        if d['status']!='OPEN' or time.monotonic()>=d['deadline'] or canonical(d['limits'])!=canonical(LIMITS):
            raise PermissionError('Closed/expired/changed reconstruction counter')
        for key,limit in LIMITS.items():
            counts=[d['roles'][r]['attempted'][key] for r in ROLE_LIMITS]
            if (type(d['attempted'][key]) is not int or any(type(n) is not int for n in counts) or
                not 0<=d['attempted'][key]<=limit or sum(counts)!=d['attempted'][key] or
                any(not 0<=n<=ROLE_LIMITS[r][key] for r,n in zip(ROLE_LIMITS,counts))):
                raise ValueError('Inconsistent operation accounting')
        return d
    def require_complete(self):
        d=self.checked()
        if (any(d['roles'][r]['claimed'] is not True for r in ROLE_LIMITS) or
            canonical(d['attempted'])!=canonical(LIMITS)):
            raise ValueError('Incomplete operation accounting')
    def claim(self,role):
        with self.locked():
            d=self.checked()
            if role not in ROLE_LIMITS or d['roles'][role]['claimed']:raise PermissionError('Role absent or already consumed')
            d['roles'][role]['claimed']=True;write(self.path,d,deadline=d['deadline'])
    def take(self,role,key):
        with self.locked():
            d=self.checked()
            if (role not in ROLE_LIMITS or key not in LIMITS or not d['roles'][role]['claimed'] or
                d['roles'][role]['attempted'][key]>=ROLE_LIMITS[role][key] or d['attempted'][key]>=LIMITS[key]):
                raise PermissionError('Unclaimed/closed/exhausted operation '+key)
            d['attempted'][key]+=1;d['roles'][role]['attempted'][key]+=1;write(self.path,d,deadline=d['deadline'])
    def close(self,*,owned_exit_confirmed=False):
        # Caller may remove a stale lock only after the supervisor confirms all owned processes exited.
        if owned_exit_confirmed is True:self.path.with_suffix('.lock').unlink(missing_ok=True)
        with self.locked():
            d=read(self.path);d['status']='CLOSED';d['unused_closed']={k:LIMITS[k]-d['attempted'][k] for k in LIMITS};write(self.path,d)

def require_zero_updates(state):
    if (state['history']!=[] or type(state['update_attempts']) is not int or state['update_attempts']!=0 or
        state['journal']!='' or state['stop_reason'] is not None or
        canonical(state['updater']['counts'])!=canonical(dict(critic=0,actor=0,temperature=0,target=0))):
        raise ValueError('Reconstruction requires zero updates and no unresolved history')

def require_zero_metadata(state):
    require_zero_updates(state)
    if state['attempts']!=[] or state['archives']!={} or state['replay']['size']!=0 or state['warm']!=dict(draws=0,held=[0.]*4):
        raise ValueError('Not a zero-state source checkpoint')

def require_warm_metadata(state):
    require_zero_updates(state)
    keys=['warmup_F50_J0'+str(i) for i in range(1,5)]
    if ([r['episode_id'] for r in state['attempts']]!=keys or set(state['archives'])!=set(keys) or
        [(r['stage'],r['case_index']) for r in state['attempts']]!=[('warmup',i) for i in range(4)] or
        state['replay']['size']!=19300 or state['warm']['draws']!=388):raise ValueError('Not the complete prior warmup boundary')

def verify_reply(expected,reply):
    if not expected or reply.get('state_digest')!=expected or reply.get('verified') is not True:raise ValueError('Independent complete restore differs')

def verify_sources(binding):
    for path,pin in binding['files'].items():
        if sha(path)!=pin:raise ValueError('Bound source changed '+path)
    for folder,expected in binding['inventories'].items():
        actual=sorted(p.relative_to(folder).as_posix() for p in Path(folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
        if actual!=expected:raise ValueError('Source inventory differs '+folder)

class Gate:
    def __init__(self,folder,role):
        self.folder=Path(folder);self.role=role;self.counter=Counter(self.folder/'counter.json')
        self.binding=read(OUT/'source_binding.json');self.binding_pin=sha(OUT/'source_binding.json')
        self.candidate=read(OUT/'candidate.json');self.spec=read(OUT/'input_spec.json')
        self.grant=read(self.folder/'grant.json');self.pin=read(self.folder/'grant_pin.json')['sha256']
        self.verify()
    def verify(self):
        verify_grant(self.candidate,read(self.folder/'grant.json'),self.pin,self.binding_pin)
        if (sha(OUT/'source_binding.json')!=self.binding_pin or (self.folder/'STOP').exists() or
            (self.folder/'authorization_closure.json').exists()):raise PermissionError('Changed binding, STOP or closed authorization')
        self.counter.checked()
        claim=read(OUT/'future_claims/consumed.json')
        if claim!=dict(grant_sha256=self.pin,output=str(self.folder.resolve())):raise PermissionError('Run identity differs')
    def take(self,key):self.verify();self.counter.take(self.role,key)
    def bytes(self,path):
        path=Path(path).resolve();data=path.read_bytes()
        if hashlib.sha256(data).hexdigest()!=self.binding['files'][str(path)]:raise ValueError('Read source changed '+str(path))
        return data
    def json(self,path):return json.loads(self.bytes(path))
