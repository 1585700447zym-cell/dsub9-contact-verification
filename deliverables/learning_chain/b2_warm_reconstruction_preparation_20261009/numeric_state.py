"""Scientific operations for the separately granted restore gate; imported after GO."""
from copy import deepcopy
import gzip,hashlib,io,json,os
from pathlib import Path
import numpy as np
import torch
from tools.learning.v4_sac import V4Updater
from tools.learning.v4_replay import V4Replay,V4BoundaryIndex
from joint_contract import learning_config,validate_config,canonical,digest,SEED,sha
from gate_contract import require_zero_metadata,require_warm_metadata
from recovery_audit import inspect_warmup

def state_digest(value):
    h=hashlib.sha256()
    def visit(x):
        def put(b):h.update(len(b).to_bytes(8,'big'));h.update(b)
        put(type(x).__name__.encode())
        if isinstance(x,torch.Tensor):
            put(str(x.dtype).encode());put(str(tuple(x.shape)).encode());put(x.detach().cpu().contiguous().numpy().tobytes())
        elif isinstance(x,np.ndarray):
            put(str(x.dtype).encode());put(str(x.shape).encode());put(x.tobytes())
        elif isinstance(x,dict):
            put(str(len(x)).encode())
            for k in sorted(x,key=lambda k:(type(k).__name__,repr(k))):visit(k);visit(x[k])
        elif isinstance(x,(list,tuple)):
            put(str(len(x)).encode())
            for item in x:visit(item)
        elif isinstance(x,bytes):put(x)
        else:put(canonical(x).encode())
    visit(value);return h.hexdigest()

def require_equal(a,b,label):
    if state_digest(a)!=state_digest(b):raise ValueError(label+' differs (complete typed state)')

class RestoreOnlyUpdater(V4Updater):
    config_validator=staticmethod(validate_config)
    def update(self,*args,**kwargs):raise PermissionError('Updates forbidden in restore gate')

def replay_state(replay):
    # Same tensor serialization as tools.learning.sac_checkpoint._replay_state.
    return dict(capacity=replay.capacity,size=len(replay),seen=sorted(replay._state.seen),
        episodes=[[key,{k:torch.tensor(v.copy()) for k,v in arrays.items()}] for key,arrays in replay._state.episodes])

class NumericState:
    def __init__(self,gate):
        self.gate=gate;self.spec=gate.spec;self.config=learning_config()
        gate.take('learner_constructions');self.model=RestoreOnlyUpdater(self.config)
        self.origin=self.model.fingerprints();self.snapshot=self.model._snapshot()
        self.source_binding=dict(mode='F50',purpose='bounded_physical_pilot',qualification_sha256=self.spec['source_grant_sha256'],config_sha256=digest(self.config))
        self.streams=lambda:[np.random.default_rng(np.random.SeedSequence([SEED,i])) for i in (1,2,3)]

    def expected_zero(self):
        wr,rr,br=self.streams();replay=V4Replay(mode='F50',capacity=self.config['learning']['replay_capacity'])
        return dict(version='v4_pilot_checkpoint_v1',config=self.config,binding=self.source_binding,origin=self.origin,
            updater=deepcopy(self.snapshot),replay=replay_state(replay),archives={},attempts=[],history=[],update_attempts=0,
            stop_reason=None,journal='',rng=dict(warm=wr.bit_generator.state,replay=rr.bit_generator.state,boundary=br.bit_generator.state),
            warm=dict(draws=0,held=[0.]*4))

    def load_zero(self):
        manifest=self.gate.json(self.spec['zero_manifest'])
        data=self.gate.bytes(self.spec['zero_state'])
        if manifest.get('version')!='v4_checkpoint_manifest_v1' or hashlib.sha256(data).hexdigest()!=manifest['state_sha256']:
            raise ValueError('Old zero manifest differs')
        self.gate.take('tensor_loads');zero=torch.load(io.BytesIO(data),map_location='cpu',weights_only=True)
        require_zero_metadata(zero);require_equal(zero,self.expected_zero(),'Registered zero checkpoint')
        return zero

    def deterministic_probe(self):
        raw=json.loads(gzip.decompress(self.gate.bytes(self.spec['probe_archive'])))
        row=next(r for r in raw['transitions'] if r['action_active'])
        before=self.model._snapshot();self.gate.take('deterministic_forwards')
        self.model.predict(np.asarray(row['observation'],dtype=np.float32),deterministic=True)
        require_equal(before,self.model._snapshot(),'Deterministic prediction mutated snapshot/RNG')

    def reconstruct(self,zero):
        # Sources retain their historical binding. No new training admission is minted.
        require_equal(zero,self.expected_zero(),'Zero origin before rebuilding')
        replay=V4Replay(mode='F50',capacity=self.config['learning']['replay_capacity']);boundary=V4BoundaryIndex('F50')
        wr,rr,br=self.streams();draws=0;held=[0.]*4;archives={};receipts=[];active=0
        for source in self.spec['warmup']:
            self.gate.verify();key=source['id'];data=self.gate.bytes(source['archive']);receipt=self.gate.json(source['receipt'])
            if hashlib.sha256(data).hexdigest()!=receipt['archive_sha256']:raise ValueError('Archive/receipt byte mismatch')
            raw=json.loads(gzip.decompress(data));audit=inspect_warmup(raw,receipt,key,draws)
            if (raw['policy_sha256']!=self.origin['actor'] or raw['qualification_sha256']!=self.source_binding['qualification_sha256'] or
                raw['config_sha256']!=self.source_binding['config_sha256']):raise ValueError('Source policy/binding differs')
            for i,row in enumerate(raw['transitions']):
                if i%50==0:held=wr.uniform(-1.,1.,4).tolist();draws+=1
                if row['sampling_request']!=held:raise ValueError('Recorded warm RNG stream differs')
            if draws!=audit['warm_draws']:raise ValueError('Warm stream count differs')
            self.gate.take('archive_rebuilds')
            result=replay.publish(key,raw['transitions'],outcome=raw['outcome'],training_admitted=True)
            expected=dict(episode_id=key,stage='warmup',case_index=raw['case_index'],archive_sha256=receipt['archive_sha256'],
                steps=len(raw['transitions']),optimizer_steps=0,policy_sha256=self.origin['actor'],outcome=raw['outcome'],**result)
            if canonical(expected)!=canonical(receipt):raise ValueError('Rebuilt replay receipt differs')
            boundary.add(raw);archives[key]=data;receipts.append(receipt);active+=audit['active_rows']
        if len(replay)!=19300 or draws!=388 or active!=14127:raise ValueError('Incomplete reconstruction')
        state=deepcopy(zero);state.update(replay=replay_state(replay),archives=archives,attempts=receipts,
            rng=dict(warm=wr.bit_generator.state,replay=rr.bit_generator.state,boundary=br.bit_generator.state),warm=dict(draws=draws,held=held))
        require_warm_metadata(state)
        tails={k:dict(targets=torch.tensor(v[0].copy()),mask=torch.tensor(v[1].copy()),last_active=v[2]) for k,v in boundary.entries.items()}
        provenance=dict(input_spec_sha256=digest(self.spec),binding_sha256=self.gate.binding_pin,
            source_grant_sha256=self.spec['source_grant_sha256'],source_zero_sha256=self.spec['zero_state_sha256'],
            boundary=self.spec['source_boundary'],old_run_remains_closed=True)
        self.replay=replay;self.boundary=boundary
        return dict(version='b2_archived_warm_checkpoint_v1',training_admitted=False,provenance=provenance,state=state,boundary=tails)

    def restore_readback(self,envelope):
        # Replay and terminal labels were independently rebuilt and fully compared first.
        saved=envelope['state'];require_warm_metadata(saved)
        self.model._restore(deepcopy(saved['updater']));self.model._finite_state()
        self.restored_streams=self.streams()
        for key,stream in zip(('warm','replay','boundary'),self.restored_streams):
            stream.bit_generator.state=deepcopy(saved['rng'][key])
        self.warm=deepcopy(saved['warm'])
        readback=deepcopy(envelope)
        readback['state'].update(updater=self.model._snapshot(),replay=replay_state(self.replay),warm=deepcopy(self.warm),
            rng={key:stream.bit_generator.state for key,stream in zip(('warm','replay','boundary'),self.restored_streams)})
        readback['boundary']={k:dict(targets=torch.tensor(v[0].copy()),mask=torch.tensor(v[1].copy()),last_active=v[2]) for k,v in self.boundary.entries.items()}
        require_equal(readback,envelope,'Live restored model/replay/boundary/RNG state')

    def save(self,envelope):
        self.gate.take('checkpoint_saves');folder=self.gate.folder/'checkpoint';folder.mkdir()
        path=folder/'state.pt';stage=folder/'state.pt.staging'
        with stage.open('xb') as f:torch.save(envelope,f);f.flush();os.fsync(f.fileno())
        os.replace(stage,path)
        from joint_contract import write
        write(folder/'manifest.json',dict(version='b2_archived_warm_manifest_v1',state_sha256=sha(path),state_digest=state_digest(envelope)))
        return sha(folder/'manifest.json')

    def load_rebuilt(self,pin):
        from joint_contract import read
        folder=self.gate.folder/'checkpoint'
        if sha(folder/'manifest.json')!=pin:raise ValueError('Rebuilt checkpoint manifest changed')
        manifest=read(folder/'manifest.json');data=(folder/'state.pt').read_bytes()
        if manifest['version']!='b2_archived_warm_manifest_v1' or hashlib.sha256(data).hexdigest()!=manifest['state_sha256']:raise ValueError('Rebuilt payload changed')
        self.gate.take('tensor_loads');state=torch.load(io.BytesIO(data),map_location='cpu',weights_only=True)
        if state_digest(state)!=manifest['state_digest']:raise ValueError('Saved complete state differs')
        return state
