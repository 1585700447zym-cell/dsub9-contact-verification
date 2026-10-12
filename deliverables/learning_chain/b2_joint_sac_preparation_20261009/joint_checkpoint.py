"""Pinned, self-contained 137D checkpoints; reconstruct every raw episode first."""
from copy import deepcopy
from pathlib import Path
import gzip,hashlib,io,json,os,re,uuid
import numpy as np
import torch
from joint_contract import canonical,sha,validate_config
from joint_chain import V4Chain,audit_raw,streams,validate_warm
from tools.learning.v4_replay import V4Replay,V4BoundaryIndex
from joint_runtime import V4Updater
from tools.learning.sac_checkpoint import _same,_integer,_tensor,_optimizer,_rng,_replay_state,_flush_write
from joint_runtime import metered_load
flush_write=_flush_write

def capture(c):
    c.verify()
    if c.active or c.failed or c.updater.failed or c.update_attempts!=c.updater.counts['critic'] or len(c.history)!=c.update_attempts:
        raise RuntimeError('Checkpoint requires a healthy complete publication/update boundary')
    archives={}
    for r in c.attempts:
        folder=c.output/r['episode_id']
        if json.loads((folder/'status.json').read_bytes())!=r:raise ValueError('Durable receipt differs')
        archives[r['episode_id']]=(folder/'episode.json.gz').read_bytes()
    return deepcopy(dict(version='v4_pilot_checkpoint_v1',config=c.config,binding=c.binding,origin=c.origin,
        updater=c.updater._snapshot(),replay=_replay_state(c.replay),archives=archives,attempts=c.attempts,history=c.history,
        update_attempts=c.update_attempts,stop_reason=c.stop_reason,
        journal=(c.output/'update_journal.jsonl').read_text(encoding='utf8') if (c.output/'update_journal.jsonl').exists() else '',
        rng=dict(warm=c.warm_rng.bit_generator.state,replay=c.replay_rng.bit_generator.state,boundary=c.boundary_rng.bit_generator.state),
        warm=dict(draws=c.warm_draws,held=c.held)))

def validate_state(state,*,expected_binding,admission=None):
    if state.get('version')!='v4_pilot_checkpoint_v1' or canonical(state.get('binding'))!=canonical(expected_binding):
        raise ValueError('Checkpoint version or mode/qualification binding differs')
    config=state['config'];validate_config(config)
    if (config['mode']!=expected_binding['mode'] or hashlib.sha256(canonical(config).encode()).hexdigest()!=expected_binding['config_sha256']):raise ValueError('Config binding differs')
    formal=expected_binding['purpose']=='bounded_physical_pilot'
    if formal and (admission is None or admission.verify(config['mode'])!=expected_binding):raise ValueError('Physical restore is not admitted')
    if expected_binding['purpose'] not in ('bounded_physical_pilot','synthetic_qualification'):raise ValueError('Unknown capability')
    replay=V4Replay(mode=config['mode'],capacity=config['learning']['replay_capacity']);boundary=V4BoundaryIndex(config['mode'])
    updater=V4Updater(config)
    if state['origin']!=updater.fingerprints():raise ValueError('Origin is not registered zero-update network')
    attempts=state['attempts'];history=state['history'];canonical(history)
    if len(attempts)>8 or len({r['episode_id'] for r in attempts})!=len(attempts) or set(state['archives'])!={r['episode_id'] for r in attempts}:raise ValueError('Attempt/archive ledger mismatch')
    wr,rr,br=streams();draws=0;held=[0.]*4;expected_stop=None
    for j,r in enumerate(attempts):
        key=r['episode_id'];stage,index=('warmup',j) if j<4 else ('online',j-4)
        if expected_stop or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,79}',key):raise ValueError('Post-stop or unsafe episode')
        data=state['archives'][key]
        if not isinstance(data,bytes) or hashlib.sha256(data).hexdigest()!=r['archive_sha256']:raise ValueError('Archive digest differs')
        raw=json.loads(gzip.decompress(data));out=audit_raw(raw,config,expected_binding)
        steps=_integer(raw['optimizer_steps'],0,2000)
        if (raw['stage'],raw['case_index'])!=(stage,index) or steps!=sum(h['audited_episodes']<=j for h in history):raise ValueError('Raw chronological update history differs')
        if formal and steps!=(0 if stage=='warmup' else 500*index):raise ValueError('Physical update schedule changed')
        actor=state['origin']['actor'] if steps==0 else history[steps-1]['actor_after']
        if raw['policy_sha256']!=actor:raise ValueError('Raw policy fingerprint differs')
        if stage=='warmup':draws,held=validate_warm(raw,wr,draws)
        elif raw['warmup_draws']!=draws:raise ValueError('Online warmup draw count differs')
        result=replay.publish(key,raw['transitions'],outcome=out,training_admitted=True)
        if not result['committed']:raise ValueError('Ineligible checkpoint source')
        expected=dict(episode_id=key,stage=stage,case_index=index,archive_sha256=r['archive_sha256'],steps=len(raw['transitions']),
            optimizer_steps=steps,policy_sha256=raw['policy_sha256'],outcome=out,**result)
        if not _same(r,expected):raise ValueError('Publication receipt differs')
        boundary.add(raw)
        if out['task_outcome'] in ('CONTACT_GUARD','MOTION_VIOLATION'):expected_stop=out['task_outcome']
    if not _same(_replay_state(replay),state['replay']):raise ValueError('Replay differs from audited raw archives')
    if state['stop_reason']!=expected_stop:raise ValueError('Guard stop state differs')
    saved=state['updater'];reference=updater._snapshot();counts=saved['counts']
    if saved.keys()!=reference.keys() or set(counts)!={'critic','actor','temperature','target'}:raise ValueError('Incomplete updater state')
    for v in counts.values():_integer(v,0,2000)
    completed=_integer(state['update_attempts'],0,2000)
    if completed!=counts['critic'] or completed!=len(history) or counts['target']!=completed or counts['actor']!=counts['temperature'] or counts['actor']!=sum(h['active_rows']>0 for h in history):raise ValueError('Update/Adam/history counters differ')
    if completed>min(2000,500*max(len(attempts)-4,0)):raise ValueError('Unearned optimizer credit')
    journal=[json.loads(line) for line in state['journal'].splitlines()]
    if len(journal)!=2*completed:raise ValueError('Missing/unresolved durable update record')
    running=dict(critic=0,actor=0,temperature=0,target=0)
    for i,h in enumerate(history,1):
        if journal[2*i-2]!=dict(event='attempt',attempt=i,counts=running):raise ValueError('Durable attempt differs')
        running=dict(critic=i,target=i,actor=running['actor']+int(h['active_rows']>0),temperature=running['temperature']+int(h['active_rows']>0))
        if journal[2*i-1]!=dict(event='complete',attempt=i,counts=running,stats=h):raise ValueError('Durable completion differs')
    previous=0;actor=state['origin']['actor']
    for i,h in enumerate(history,1):
        total=_integer(h['audited_episodes'],5,len(attempts));credit=min(2000,500*(total-4))
        if total<previous or h['critic_batches']!=i or h['batch_rows']!=256 or h['credit_remaining']!=credit-i or credit-i<0 or h['actor_before']!=actor:raise ValueError('Update history/credit changed')
        subset=replay._state.episodes[:total];keys=[k for k,_ in subset];ends=np.cumsum([len(a['rewards']) for _,a in subset]);starts=np.r_[0,ends[:-1]]
        if h['replay_rows']!=int(ends[-1]):raise ValueError('History replay size differs')
        uniform=rr.integers(0,int(ends[-1]),256);owners=np.searchsorted(ends,uniform,side='right')
        base=[(keys[o],int(t-starts[o])) for o,t in zip(owners,uniform)]
        candidates=[(k,boundary.entries[k][2]) for k in keys if boundary.entries[k][2] is not None]
        selected=base[:240]+[candidates[int(t)] for t in br.integers(0,len(candidates),16)]
        if h['indices']!=[list(p) for p in selected] or h['active_rows']!=sum(bool(dict(subset)[k]['action_active'][t,0]) for k,t in base):raise ValueError('Sampler or actor mask history differs')
        actor=h['actor_after'];previous=total
    if saved['policy'].keys()!=reference['policy'].keys():raise ValueError('Incomplete policy')
    for k,v in reference['policy'].items():_tensor(saved['policy'][k],v)
    _tensor(saved['alpha'],reference['alpha']);_tensor(saved['rng'],reference['rng']);torch.Generator().set_state(saved['rng'])
    for k,opt in zip(('critic','actor','temperature'),updater._optimizers()):_optimizer(saved[k],opt,counts[k])
    updater._restore(deepcopy(saved));updater._finite_state()
    if updater.fingerprints()['actor']!=actor:raise ValueError('Final actor differs from history')
    expected_rng=dict(warm=wr.bit_generator.state,replay=rr.bit_generator.state,boundary=br.bit_generator.state)
    if state['rng']!=expected_rng or state['warm']!=dict(draws=draws,held=held):raise ValueError('RNG/draw state differs from ledger')
    return updater,replay,boundary,[_rng(state['rng'][k]) for k in ('warm','replay','boundary')]

def save_checkpoint(chain,path):
    path=Path(path).resolve()
    if path.exists():raise FileExistsError(path)
    state=capture(chain);validate_state(state,expected_binding=chain.binding,admission=chain.admission)
    path.parent.mkdir(parents=True,exist_ok=True);staging=path.with_name(path.name+'.stage-'+uuid.uuid4().hex);staging.mkdir()
    with (staging/'state.pt').open('xb') as f:torch.save(state,f);f.flush();os.fsync(f.fileno())
    manifest=dict(version='v4_checkpoint_manifest_v1',state_sha256=sha(staging/'state.pt'))
    flush_write(staging/'manifest.json',canonical(manifest));chain.verify();os.rename(staging,path)
    return sha(path/'manifest.json')

def read_checkpoint(path,*,expected_digest,expected_binding,admission=None):
    path=Path(path);data=(path/'manifest.json').read_bytes()
    if hashlib.sha256(data).hexdigest()!=expected_digest:raise ValueError('Checkpoint pin differs')
    manifest=json.loads(data)
    if manifest['version']!='v4_checkpoint_manifest_v1':raise ValueError('Checkpoint manifest version differs')
    payload=(path/'state.pt').read_bytes()
    if hashlib.sha256(payload).hexdigest()!=manifest['state_sha256']:raise ValueError('Checkpoint payload differs')
    state=metered_load(io.BytesIO(payload),map_location='cpu',weights_only=True)
    components=validate_state(state,expected_binding=expected_binding,admission=admission)
    return state,components

def load_checkpoint(path,*,expected_digest,expected_binding,output,admission=None):
    output=Path(output).resolve()
    if output.exists():raise FileExistsError(output)
    state,(updater,replay,boundary,rngs)=read_checkpoint(path,expected_digest=expected_digest,expected_binding=expected_binding,admission=admission)
    c=V4Chain(state['config'],output=output,binding=expected_binding,admission=admission)
    c.updater=updater;c.replay=replay;c.boundary=boundary;c.warm_rng,c.replay_rng,c.boundary_rng=rngs
    c.warm_draws=state['warm']['draws'];c.held=state['warm']['held'];c.origin=state['origin']
    c._audited_warm_rng=_rng(state['rng']['warm']);c._audited_warm_draws=c.warm_draws
    c.attempts=state['attempts'];c.history=state['history'];c.update_attempts=state['update_attempts'];c.stop_reason=state['stop_reason']
    for r in c.attempts:
        folder=output/r['episode_id'];folder.mkdir();flush_write(folder/'episode.json.gz',state['archives'][r['episode_id']]);flush_write(folder/'status.json',canonical(r))
    if state['journal']:flush_write(output/'update_journal.jsonl',state['journal'])
    return c
