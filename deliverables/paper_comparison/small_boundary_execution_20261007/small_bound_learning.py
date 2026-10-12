"""Reuse the original numeric core; qualify the physical profile outside it.

Protocol packaging is pure file work. Core construction, serialization and
restoration are lazy and require a separate current admission capability.
"""
from copy import deepcopy
from pathlib import Path, PurePosixPath
import gzip, hashlib, json, os, re, shutil, uuid
from small_bound_profile import (canonical,digest,sha,validate_outer_contract,
                                audit_small_bound_episode)


def _binding(value,contract):
    if (not isinstance(value,dict) or set(value)!={'mode','purpose','qualification_sha256','config_sha256'} or
        value['mode']!='F50' or value['purpose'] not in ('synthetic_qualification','bounded_physical_pilot') or
        not re.fullmatch('[0-9a-f]{64}',value['qualification_sha256']) or
        value['config_sha256']!=contract['engine_config_sha256']):
        raise ValueError('Unique qualified outer run must bind original F50 engine')
    return value


def _safe_file(folder,relative):
    p=PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative or ':' in relative:
        raise ValueError('Unsafe checkpoint member')
    result=folder.joinpath(*p.parts)
    if result.is_symlink() or not result.resolve().is_relative_to(folder.resolve()):
        raise ValueError('Checkpoint member escapes package')
    return result


def package_outer_checkpoint(engine_path,path,*,contract,engine_binding,archives):
    """Package already-saved core bytes. This operation grants no runtime rights."""
    pin=validate_outer_contract(contract);_binding(engine_binding,contract)
    engine_path=Path(engine_path);path=Path(path)
    if path.exists():raise FileExistsError(path)
    manifest=json.loads((engine_path/'manifest.json').read_bytes())
    if manifest.get('version')!='v4_checkpoint_manifest_v1' or sha(engine_path/'state.pt')!=manifest.get('state_sha256'):
        raise ValueError('Complete original core checkpoint required')
    audited={}
    for key,data in archives.items():
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}',key) or not isinstance(data,bytes):
            raise ValueError('Safe complete archive bytes required')
        raw=json.loads(gzip.decompress(data));audit_small_bound_episode(raw,contract)
        if raw['episode_id']!=key:raise ValueError('Witness identity differs')
        audited[key]=data
    path.parent.mkdir(parents=True,exist_ok=True)
    staging=path.with_name(path.name+'.stage-'+uuid.uuid4().hex);staging.mkdir()
    (staging/'engine').mkdir();(staging/'archives').mkdir()
    for name in ('state.pt','manifest.json'):shutil.copyfile(engine_path/name,staging/'engine'/name)
    for key,data in audited.items():(staging/'archives'/(key+'.json.gz')).write_bytes(data)
    files={p.relative_to(staging).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
           for p in sorted(staging.rglob('*')) if p.is_file()}
    outer=dict(version='pc12_small_bound_checkpoint_v1',contract=contract,profile_sha256=pin,
        engine_binding=engine_binding,engine_manifest_sha256=sha(staging/'engine/manifest.json'),
        archives={k:'archives/'+k+'.json.gz' for k in audited},files=files)
    with (staging/'manifest.json').open('x',encoding='utf8') as f:
        f.write(canonical(outer));f.flush();os.fsync(f.fileno())
    os.rename(staging,path)
    return sha(path/'manifest.json')


def read_outer_checkpoint(path,*,expected_digest,expected_profile_digest):
    """Reject wrong profiles, naked old checkpoints and witnesses before torch."""
    path=Path(path)
    try:
        if sha(path/'manifest.json')!=expected_digest:raise ValueError('Outer checkpoint pin differs')
        m=json.loads((path/'manifest.json').read_bytes())
        if m.get('version')!='pc12_small_bound_checkpoint_v1':raise ValueError('Naked old checkpoint rejected')
        pin=validate_outer_contract(m['contract'])
        if pin!=m['profile_sha256'] or pin!=expected_profile_digest:raise ValueError('Physical profile pin differs')
        _binding(m['engine_binding'],m['contract'])
        listed=set(m['files']);actual={p.relative_to(path).as_posix() for p in path.rglob('*') if p.is_file() and p!=path/'manifest.json'}
        if listed!=actual:raise ValueError('Checkpoint member inventory differs')
        for rel,item in m['files'].items():
            p=_safe_file(path,rel)
            if p.stat().st_size!=item['bytes'] or sha(p)!=item['sha256']:raise ValueError('Checkpoint member hash differs')
        if sha(path/'engine/manifest.json')!=m['engine_manifest_sha256']:raise ValueError('Inner manifest pin differs')
        inner=json.loads((path/'engine/manifest.json').read_bytes())
        if inner.get('version')!='v4_checkpoint_manifest_v1' or sha(path/'engine/state.pt')!=inner.get('state_sha256'):
            raise ValueError('Inner opaque payload differs')
        expected_files={'engine/manifest.json','engine/state.pt'}
        for key,rel in m['archives'].items():
            if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}',key) or rel!='archives/'+key+'.json.gz':
                raise ValueError('Unsafe witness identity')
            data=_safe_file(path,rel).read_bytes();raw=json.loads(gzip.decompress(data))
            audit_small_bound_episode(raw,m['contract'])
            if raw['episode_id']!=key:raise ValueError('Witness identity differs')
            expected_files.add(rel)
        if expected_files!=listed:raise ValueError('Unregistered member or missing witness')
        return m
    except (OSError,KeyError,TypeError,json.JSONDecodeError) as exc:
        raise ValueError('Incomplete outer checkpoint') from exc


class EngineAdmissionBridge:
    def __init__(self,admission,contract,binding):
        self.admission=admission;self.contract=contract;self.binding=binding
    def verify(self,mode):
        if mode!='F50':raise ValueError('Internal permission identity differs')
        current=self.admission.verify('engine',validate_outer_contract(self.contract))
        if current!=self.binding:raise ValueError('Outer qualification changed')
        return deepcopy(self.binding)


class SmallBoundChain:
    def __init__(self,contract,*,output,admission):
        self.contract=deepcopy(contract);self.pin=validate_outer_contract(contract);self.admission=admission
        self.binding=_binding(admission.verify('construct',self.pin),self.contract)
        # Nothing above this line imports torch or constructs a model.
        from tools.learning.v4_pilot_chain import V4Chain
        from tools.learning.v4_pilot_contract import learning_config
        bridge=EngineAdmissionBridge(admission,self.contract,self.binding)
        self.inner=V4Chain(learning_config('F50'),output=output,binding=self.binding,
            admission=bridge if self.binding['purpose']=='bounded_physical_pilot' else None)
        if self.inner.origin!=self.contract['zero_origin'] or any(self.inner.updater.counts.values()) or self.inner.attempts:
            raise ValueError('Fresh same-seed zero-update origin required')

    def verify(self,operation):
        if validate_outer_contract(self.contract)!=self.pin:raise ValueError('Outer contract changed')
        if self.admission.verify(operation,self.pin)!=self.binding:raise ValueError('Admission binding changed')
        self.inner.verify()

    def begin(self,stage,index):
        self.verify('episode');return self.inner.begin(stage,index)

    def warm_action(self,cycle):
        self.verify('warmup');return self.inner.warm_action(cycle)

    def predict(self,observations,*,deterministic):
        self.verify('forward');return self.inner.updater.predict(observations,deterministic=deterministic)

    def publish(self,raw):
        if raw.get('stage') not in ('warmup','online') or raw.get('scope')!=self.binding.get('purpose'):
            raise ValueError('Only new matching warmup/online data can enter replay')
        self.verify('publish');audit_small_bound_episode(raw,self.contract)
        if raw['qualification_sha256']!=self.binding['qualification_sha256'] or raw['config_sha256']!=self.binding['config_sha256']:
            raise ValueError('Raw qualification differs')
        result=self.inner.publish(raw);self.verify('publish');return result

    def update(self,n,*,before_update=None,after_update=None):
        if self.inner.stop_reason:raise RuntimeError('Guard-stopped branch has no further update credit')
        self.verify('update')
        def before(core):
            self.verify('update')
            if before_update is not None:before_update(self)
        def after(core,stats):
            if after_update is not None:after_update(self,stats)
        return self.inner.update(n,before_update=before,after_update=after if after_update is not None else None)


def save_small_bound_checkpoint(chain,path):
    chain.verify('checkpoint');archives={}
    for receipt in chain.inner.attempts:
        key=receipt['episode_id'];data=(chain.inner.output/key/'episode.json.gz').read_bytes()
        if hashlib.sha256(data).hexdigest()!=receipt['archive_sha256']:raise ValueError('Receipt differs')
        audit_small_bound_episode(json.loads(gzip.decompress(data)),chain.contract);archives[key]=data
    from tools.learning.v4_checkpoint import save_checkpoint
    path=Path(path)
    if path.exists():raise FileExistsError(path)
    engine=path.with_name(path.name+'.inner-'+uuid.uuid4().hex)
    save_checkpoint(chain.inner,engine);chain.verify('checkpoint')
    return package_outer_checkpoint(engine,path,contract=chain.contract,engine_binding=chain.binding,archives=archives)


def _admitted_package(path,expected_digest,expected_profile_digest,admission):
    m=read_outer_checkpoint(path,expected_digest=expected_digest,expected_profile_digest=expected_profile_digest)
    binding=admission.verify('checkpoint',expected_profile_digest)
    if binding!=m['engine_binding']:raise ValueError('New checkpoint qualification binding differs')
    return m,EngineAdmissionBridge(admission,m['contract'],binding)


def _match_witnesses(state,path,m):
    witnesses={k:(Path(path)/rel).read_bytes() for k,rel in m['archives'].items()}
    if state['archives']!=witnesses:raise ValueError('Inner complete replay archives differ from outer witnesses')


def _read_inner_payload(path,m):
    """Admitted tensor decoding only, before importing/constructing the core."""
    import io
    payload=(Path(path)/'engine/state.pt').read_bytes()
    if hashlib.sha256(payload).hexdigest()!=m['files']['engine/state.pt']['sha256']:
        raise ValueError('Inner payload changed before decode')
    import torch
    return torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)


def _validate_inner_before_core(state,path,m):
    if (not isinstance(state,dict) or state.get('version')!='v4_pilot_checkpoint_v1' or
        canonical(state.get('binding'))!=canonical(m['engine_binding']) or
        digest(state.get('config'))!=m['contract']['engine_config_sha256']):
        raise ValueError('Inner identity/config differs before numeric restoration')
    _match_witnesses(state,path,m)


def read_small_bound_checkpoint(path,*,expected_profile_digest,expected_digest,admission):
    m,bridge=_admitted_package(path,expected_digest,expected_profile_digest,admission)
    _validate_inner_before_core(_read_inner_payload(path,m),path,m)
    from tools.learning.v4_checkpoint import read_checkpoint
    state,components=read_checkpoint(Path(path)/'engine',expected_digest=m['engine_manifest_sha256'],
        expected_binding=m['engine_binding'],admission=bridge)
    _match_witnesses(state,path,m)
    return state,components


def load_small_bound_checkpoint(path,*,expected_profile_digest,expected_digest,admission,output):
    m,bridge=_admitted_package(path,expected_digest,expected_profile_digest,admission)
    _validate_inner_before_core(_read_inner_payload(path,m),path,m)
    from tools.learning.v4_checkpoint import load_checkpoint
    inner=load_checkpoint(Path(path)/'engine',expected_digest=m['engine_manifest_sha256'],
        expected_binding=m['engine_binding'],output=output,admission=bridge)
    # The pinned writer copied these exact audited bytes; check again after restore.
    restored={r['episode_id']:(inner.output/r['episode_id']/'episode.json.gz').read_bytes() for r in inner.attempts}
    _match_witnesses({'archives':restored},path,m)
    c=object.__new__(SmallBoundChain);c.contract=deepcopy(m['contract']);c.pin=expected_profile_digest
    c.admission=admission;c.binding=deepcopy(m['engine_binding']);c.inner=inner;c.verify('checkpoint')
    return c
