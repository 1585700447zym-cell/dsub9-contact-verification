"""Pure admission and durable attempted-cost accounting; no compute capability by default."""
from pathlib import Path
import time
from joint_contract import OUT,ROOT,read,write,sha,digest,canonical,LIMITS
PHYSICAL_FIELDS=('trace','actions','transitions','outcome','controller_events','events','stop_samples','peaks')


def verify_execution_copies(folder):
    binding=read(OUT/'source_binding.json')
    for name in ('configuration.json','model.xml'):
        if sha(Path(folder)/name)!=binding['files'][str(OUT/name)]:raise ValueError('Execution copy changed: '+name)


def verify_grant(candidate,grant,pin,binding_pin):
    if (digest(grant)!=pin or grant.get('version')!='b2_joint_sac_grant_v1' or
        grant.get('status')!='OPEN' or grant.get('explicit_user_authorized') is not True or
        not isinstance(grant.get('human_evidence'),str) or not grant['human_evidence'].strip()):raise PermissionError('New explicit joint-SAC grant required')
    if (grant.get('candidate_sha256')!=digest(candidate) or grant.get('binding_sha256')!=binding_pin or
        grant.get('cumulative_before')!=237 or canonical(grant.get('limits'))!=canonical(LIMITS) or
        candidate.get('status')!='PREPARED_NOT_AUTHORIZED' or candidate.get('training_admitted') is not False):raise ValueError('Wrong scope, limits or candidate')


def verify_sources(binding):
    for path,pin in binding['files'].items():
        if sha(path)!=pin:raise ValueError('Bound source changed: '+path)
    for folder,expected in binding['inventories'].items():
        actual=sorted(p.relative_to(folder).as_posix() for p in Path(folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
        if actual!=expected:raise ValueError('Bound runtime inventory changed: '+folder)


class Counter:
    @classmethod
    def create(cls,path,limits):
        path=Path(path)
        with path.open('x',encoding='utf-8') as f:f.write(canonical(dict(status='OPEN',limits=limits,attempted={k:0 for k in limits},started=time.time())))
        return cls(path)
    def __init__(self,path):self.path=Path(path)
    def take(self,key,n=1):
        data=read(self.path)
        if data['status']!='OPEN' or type(n) is not int or n<1 or key not in data['limits'] or data['attempted'][key]+n>data['limits'][key]:raise RuntimeError('Closed or exhausted cost: '+key)
        data['attempted'][key]+=n;write(self.path,data)
    def close(self):
        data=read(self.path);data['status']='CLOSED';data['unused_closed']={k:v-data['attempted'][k] for k,v in data['limits'].items()};write(self.path,data)


def restore_equal(parent,child):
    if parent.get('state_digest')!=child.get('state_digest') or not parent.get('state_digest'):raise ValueError('Full checkpoint state differs')
    if set(parent.get('physical',{}))!=set(PHYSICAL_FIELDS) or set(child.get('physical',{}))!=set(PHYSICAL_FIELDS):raise ValueError('Incomplete restore transcript')
    if parent['physical']!=child['physical']:raise ValueError('Independent physical replay differs')


class Admission:
    def __init__(self,folder):
        self.folder=Path(folder);self.grant=read(self.folder/'grant.json');self.pin=read(self.folder/'grant_pin.json')['sha256']
        self.candidate=read(OUT/'candidate.json');self.binding_pin=sha(OUT/'source_binding.json')
        verify_grant(self.candidate,self.grant,self.pin,self.binding_pin)
        self.binding=dict(mode='F50',purpose='bounded_physical_pilot',qualification_sha256=self.pin,config_sha256=self.candidate['learning_config_sha256'])
    def verify(self,mode):
        if mode!='F50' or (self.folder/'STOP').exists():raise PermissionError('Only open F50 scope')
        data=read(self.folder/'counter.json')
        if data['status']!='OPEN' or time.time()-data['started']>LIMITS['whole_wall_s']:raise PermissionError('Closed or expired run')
        if sha(OUT/'source_binding.json')!=self.binding_pin:raise ValueError('Source binding changed')
        return dict(self.binding)
