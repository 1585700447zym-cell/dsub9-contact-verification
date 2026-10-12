"""Current data requalification and complete independent SAC branch state."""
from copy import deepcopy
import gzip,hashlib,io,json,os,sys,uuid
from pathlib import Path
import numpy as np
import torch
import validation_contract as C
from tools.learning.audited_replay import AuditedReplay
from tools.learning.boundary_targets import BoundaryIndex
from tools.learning.episode_rules import FORCE_ONLY
from tools.learning.sac_update import SACUpdater
from tools.learning.sac_checkpoint import _same,_tensor,_optimizer,_replay_state,_audit_physics,_flush_write

sys.path.insert(0,str(C.PREFLIGHT))

def source_permission(raw,receipt):
    if (raw.get('training_admitted') is not False or receipt.get('training_admitted') is not False or
        receipt.get('committed')!=0 or receipt.get('status')!='preflight_archived' or
        raw.get('optimizer_steps')!=0 or raw.get('optimizer_steps_start')!=0 or raw.get('fault') is not None or
        any(raw.get('outcome',{}).get(k) is not True for k in ('valid_for_learning','simulation_valid','physical_stopped'))):
        raise ValueError('Unpublished complete preflight source required; historical permission is immutable')

def verify_dataset_bytes(manifest,data,manifest_pin):
    if type(data) is not bytes or hashlib.sha256(data).hexdigest()!=manifest_pin or C.canonical(json.loads(data))!=C.canonical(manifest):
        raise ValueError('Exact persisted dataset bytes/qualification changed')

def validate_counts(counts,history,completed):
    if (set(counts)!={'critic','target','actor','temperature'} or
        any(type(v) is not int or not 0<=v<=2500 for v in counts.values()) or
        counts['critic']!=completed or counts['target']!=completed or len(history)!=completed or
        counts['actor']!=counts['temperature'] or counts['actor']!=sum(r['active_rows']>0 for r in history) or
        any(r['critic_batches']!=i or r['batch_rows']!=256 or type(r['active_rows']) is not int or not 0<=r['active_rows']<=256 for i,r in enumerate(history,1))):
        raise ValueError('Optimizer, update history and permission masks disagree')

def check_snapshot_identity(s,arm,binding_pin,auth_pin):
    if (s.get('version')!='temporal_learning_checkpoint_v1' or s.get('arm')!=arm or
        s.get('binding_sha256')!=binding_pin or s.get('authorization_sha256')!=auth_pin or
        C.canonical(s.get('config'))!=C.canonical(C.config(arm))):raise ValueError('Checkpoint branch/configuration/authority changed')

def qualify_dataset(arm,ledger,output):
    from sampling_runtime import audit_sampling
    C.require_authorization(ledger.state['binding_sha256'],ledger.state['authorization_sha256']);C.verify_parent()
    refs=[];receipts=[]
    for case in C.cases():
        key=case['name']+'_'+arm;p=C.PREFLIGHT/'run/episodes'/key/'episode.json.gz'
        raw=json.loads(gzip.decompress(p.read_bytes()));old=C.read(p.parent/'status.json')
        source_permission(raw,old)
        if raw['episode_id']!=key or C.canonical(raw['case'])!=C.canonical(case) or old['archive_sha256']!=C.digest(p):raise ValueError('Paired preflight identity changed')
        _audit_physics(raw);stamp=FORCE_ONLY.classify(raw);proof=audit_sampling(raw)
        if raw['sampling_final']['sampler']['hold_cycles']!=(50 if arm=='C' else 1):raise ValueError('Wrong temporal treatment')
        refs.append(dict(id=key,path=p.relative_to(C.ROOT).as_posix(),sha256=C.digest(p),role='preflight'))
        receipts.append(dict(episode_id=key,training_admitted=True,current_qualification_sha256=ledger.state['binding_sha256'],
            historical_training_admitted=False,historical_committed=0,committed=len(raw['transitions']),discarded=0,
            archive_sha256=C.digest(p),learning_eligibility=stamp,sampling_proof=proof))
    manifest=dict(version='temporal_dataset_qualification_v1',arm=arm,binding_sha256=ledger.state['binding_sha256'],
        authorization_sha256=ledger.state['authorization_sha256'],parent_preflight_sha256=C.PREFLIGHT_PIN,
        references=refs,current_receipts=receipts,historical_bytes_modified=False)
    p=Path(output)/('dataset_'+arm+'.json');C.write(p,manifest)
    ledger.register_dataset(arm,C.digest(p),[r['id'] for r in refs]);return manifest,C.digest(p)

class Updater(SACUpdater):
    @staticmethod
    def config_validator(c):
        arm=c.get('comparison',{}).get('arm')
        if C.canonical(c)!=C.canonical(C.config(arm)):raise ValueError('Exact current SAC configuration required')

def zero_updater(arm):
    from tools.learning.actor_lr_engine import read_origin
    state,_=read_origin();u=Updater(C.config(arm));s=state['updater']
    if any(s['counts'].values()) or any(s[k]['state'] for k in ('actor','critic','temperature')):raise ValueError('Zero update/empty Adam origin required')
    u._restore(deepcopy(s));u._finite_state();return u

def rng(stream):return np.random.Generator(np.random.PCG64(np.random.SeedSequence([C.scope()['seed'],stream])))

def index_state(index):
    return {k:dict(targets=torch.tensor(v[0].copy()),mask=torch.tensor(v[1].copy()),boundary=v[2]) for k,v in index.entries.items()}

def sample_signature(indices):return hashlib.sha256(C.canonical([list(x) for x in indices]).encode()).hexdigest()

class Branch:
    def __init__(self,arm,ledger,manifest,manifest_pin,updater=None,dataset_bytes=None):
        self.arm=arm;self.ledger=ledger;self.manifest=deepcopy(manifest);self.manifest_pin=manifest_pin
        if manifest['arm']!=arm or ledger.state['datasets'][arm]['manifest_sha256']!=manifest_pin:raise ValueError('Current qualified branch dataset required')
        self.dataset_bytes=(C.HERE/'run'/('dataset_'+arm+'.json')).read_bytes() if dataset_bytes is None else dataset_bytes
        verify_dataset_bytes(self.manifest,self.dataset_bytes,self.manifest_pin)
        self.updater=zero_updater(arm) if updater is None else updater
        self.replay=AuditedReplay(capacity=156000);self.index=BoundaryIndex(rules=FORCE_ONLY)
        self.replay_rng=rng(2);self.boundary_rng=rng(3);self.history=[];self.refs=[];self.archives={}
        for ref in manifest['references']:
            data=(C.ROOT/ref['path']).read_bytes()
            if hashlib.sha256(data).hexdigest()!=ref['sha256']:raise ValueError('Dataset archive changed')
            self.append_archive(ref,data,expected_batches=0)
    def append_archive(self,ref,data,expected_batches):
        if ref['id'] in self.archives or hashlib.sha256(data).hexdigest()!=ref['sha256']:raise ValueError('Repeated/mismatched learning archive')
        raw=json.loads(gzip.decompress(data));_audit_physics(raw);FORCE_ONLY.classify(raw)
        if raw['episode_id']!=ref['id'] or raw['optimizer_steps']!=expected_batches or raw['optimizer_steps_start']!=expected_batches:raise ValueError('Learning episode optimizer boundary changed')
        if ref['role']=='preflight':
            if raw['training_admitted'] is not False or ref['id'] not in [x['id'] for x in self.manifest['references']]:raise ValueError('Unqualified preflight replay')
        elif ref['role']=='online':
            i=len(self.refs)-4
            if (ref['id']!=self.arm+'_online_'+C.cases()[i]['name'] or raw['training_admitted'] is not True or
                raw['qualification_sha256']!=self.ledger.state['binding_sha256'] or expected_batches!=500*(i+1)):
                raise ValueError('Wrong online arm/credit boundary')
        else:raise ValueError('Unregistered learning archive role')
        result=self.replay.publish(ref['id'],raw['transitions'],outcome=raw['outcome'],training_admitted=True)
        if result['committed']!=len(raw['transitions']):raise ValueError('Incomplete learning publication')
        self.index.add(raw);self.refs.append(deepcopy(ref));self.archives[ref['id']]=data
    def update_one(self,meter):
        n=len(self.history)
        if self.updater.failed or self.updater.counts['critic']!=n or self.ledger.state['updates'][self.arm]['completed']!=n:raise RuntimeError('Healthy synchronized branch required')
        token=self.ledger.reserve_update(self.arm);meter.begin_update(token)
        try:
            batch=self.index.sample(self.replay,rng=self.replay_rng,boundary_rng=self.boundary_rng)
            row=self.updater.update(batch.actor,critic_batch=batch.critic,exact_targets=(batch.targets,batch.mask))
            row.update(episode_count=len(self.refs),replay_size=len(self.replay),critic_sample_sha256=sample_signature(batch.indices))
            self.history.append(row);self.ledger.finish_update(token)
        finally:meter.end_context()
    def capture(self):
        self.ledger.healthy();n=len(self.history)
        validate_counts(self.updater.counts,self.history,n)
        return deepcopy(dict(version='temporal_learning_checkpoint_v1',arm=self.arm,config=C.config(self.arm),
            binding_sha256=self.ledger.state['binding_sha256'],authorization_sha256=self.ledger.state['authorization_sha256'],
            dataset=self.manifest,dataset_bytes=self.dataset_bytes,dataset_sha256=self.manifest_pin,updater=self.updater._snapshot(),replay=_replay_state(self.replay),
            boundary_index=index_state(self.index),references=self.refs,archives=self.archives,history=self.history,
            rng=dict(replay=self.replay_rng.bit_generator.state,boundary=self.boundary_rng.bit_generator.state)))
    def save(self,path):
        s=self.capture();path=Path(path)
        if path.exists():raise FileExistsError('Checkpoint already exists')
        staging=path.with_name(path.name+'.staging-'+uuid.uuid4().hex);staging.mkdir()
        _flush_write(staging/'state.pt',lambda f:torch.save(s,f))
        manifest=dict(version='temporal_checkpoint_manifest_v1',arm=self.arm,binding_sha256=s['binding_sha256'],authorization_sha256=s['authorization_sha256'],
            state_sha256=C.digest(staging/'state.pt'),batches=len(self.history),dataset_sha256=self.manifest_pin)
        _flush_write(staging/'manifest.json',lambda f:f.write(json.dumps(manifest,sort_keys=True,indent=2).encode()))
        os.rename(staging,path);return C.digest(path/'manifest.json')

def restore(path,manifest_pin,arm,ledger):
    path=Path(path)
    if C.digest(path/'manifest.json')!=manifest_pin:raise ValueError('Checkpoint manifest changed')
    m=C.read(path/'manifest.json');data=(path/'state.pt').read_bytes()
    if hashlib.sha256(data).hexdigest()!=m['state_sha256'] or m['arm']!=arm or m['batches']!=2500:raise ValueError('Final checkpoint payload changed')
    s=torch.load(io.BytesIO(data),map_location='cpu',weights_only=True)
    check_snapshot_identity(s,arm,ledger.state['binding_sha256'],ledger.state['authorization_sha256'])
    if s['dataset_sha256']!=ledger.state['datasets'][arm]['manifest_sha256'] or s['dataset_sha256']!=m['dataset_sha256']:
        raise ValueError('Current dataset qualification changed')
    verify_dataset_bytes(s['dataset'],s['dataset_bytes'],s['dataset_sha256'])
    # Privately rebuild all data and labels from complete immutable archives.
    u=Updater(C.config(arm));b=Branch.__new__(Branch);b.arm=arm;b.ledger=ledger;b.manifest=s['dataset'];b.manifest_pin=s['dataset_sha256'];b.dataset_bytes=s['dataset_bytes'];b.updater=u
    b.replay=AuditedReplay(capacity=156000);b.index=BoundaryIndex(rules=FORCE_ONLY);b.refs=[];b.archives={}
    if len(s['references'])!=8 or len(s['archives'])!=8:raise ValueError('Eight qualified learning episodes required')
    for i,ref in enumerate(s['references']):b.append_archive(ref,s['archives'][ref['id']],0 if i<4 else (i-3)*500)
    if not _same(_replay_state(b.replay),s['replay']) or not _same(index_state(b.index),s['boundary_index']):raise ValueError('Replay/index differs from complete audited source')
    b.history=s['history'];validate_counts(s['updater']['counts'],b.history,2500)
    # Regenerate both sampling streams without a neural or physical call.
    rr=rng(2);br=rng(3);episodes=b.replay._state.episodes
    for i,row in enumerate(b.history):
        count=4+i//500;prefix=episodes[:count];keys=[k for k,_ in prefix];ends=np.cumsum([len(a['rewards']) for _,a in prefix]);starts=np.r_[0,ends[:-1]]
        uniform=rr.integers(0,int(ends[-1]),size=256);owners=np.searchsorted(ends,uniform,side='right')
        base=tuple((keys[o],int(j-starts[o])) for o,j in zip(owners,uniform))
        candidates=[(k,b.index.entries[k][2]) for k in keys if b.index.entries[k][2] is not None]
        boundary=tuple(candidates[int(j)] for j in br.integers(0,len(candidates),size=16));selected=base[:240]+boundary
        arrays=dict(prefix);active=sum(bool(arrays[k]['action_active'][j,0]) for k,j in base)
        if (row['episode_count']!=count or row['replay_size']!=int(ends[-1]) or row['active_rows']!=active or row['critic_sample_sha256']!=sample_signature(selected)):
            raise ValueError('Training draw/credit/history changed')
    if rr.bit_generator.state!=s['rng']['replay'] or br.bit_generator.state!=s['rng']['boundary']:raise ValueError('Sampling RNG endpoint differs')
    reference=u._snapshot();saved=s['updater']
    if saved.keys()!=reference.keys() or saved['policy'].keys()!=reference['policy'].keys():raise ValueError('Missing complete updater state')
    for k in reference['policy']:_tensor(saved['policy'][k],reference['policy'][k])
    _tensor(saved['alpha'],reference['alpha']);_tensor(saved['rng'],reference['rng']);torch.Generator().set_state(saved['rng'])
    for k,opt in zip(('critic','actor','temperature'),u._optimizers()):_optimizer(saved[k],opt,saved['counts'][k])
    u._restore(deepcopy(saved));u._finite_state();b.replay_rng=rr;b.boundary_rng=br
    if not _same(b.capture(),s):raise ValueError('Complete restored learning state differs')
    return b
