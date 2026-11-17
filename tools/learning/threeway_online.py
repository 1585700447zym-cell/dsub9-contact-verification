"""Isolated online pilot adapter. Legacy checkpoints/admission remain untouched.

Physical/source qualification is issued by the pinned pilot runner, not this
numerical adapter. Raw replay always retains original rewards. The distinct
checkpoint version prevents legacy loaders from resuming an overlay experiment.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import fields
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import numpy as np
import torch
from .audited_replay import ReplayBatch, _State
from .recurrent_replay import RecurrentReplay, _compact
from .switchable_sac import Experiment, STATE_VERSION, TRAINING_STATE_VERSION, _episode_digest
from .recovery_learning_contract import digest

VERSION='threeway_online_checkpoint_v1'
SAMPLER='half_uniform_half_event_full128_v1'


def sample_common(replay, labels, rng):
    """Two full 128-transition windows; same learning positions for MLP and GRU."""
    view=RecurrentReplay(capacity=replay.capacity)
    episodes=tuple((key,arrays if 'frames' in arrays else _compact(arrays))
                   for key,arrays in replay._state.episodes if len(arrays['rewards'])>=128)
    if not episodes: raise ValueError('No complete 128-step window')
    view._state=_State(episodes=episodes, seen=replay._state.seen,
                      size=sum(len(a['rewards']) for _,a in episodes))
    sizes=np.array([len(a['rewards'])-127 for _,a in episodes])
    ends=np.cumsum(sizes)
    def uniform():
        offset=int(rng.integers(int(ends[-1])))
        owner=int(np.searchsorted(ends,offset,side='right'))
        return episodes[owner][0],offset-int(np.r_[0,ends[:-1]][owner])
    first=uniform(); pools={}
    lengths={key:len(a['rewards']) for key,a in episodes}
    for key,_ in episodes:
        for anchor in labels[key]['anchors']:
            cycle=anchor['cycle']
            if type(cycle) is not int or not 0<=cycle<lengths[key]: raise ValueError('Invalid focus cycle')
            pools.setdefault(anchor['kind'],[]).append((key,cycle))
    kind=cycle=key=None
    if pools:
        kinds=sorted(pools); kind=kinds[int(rng.integers(len(kinds)))]
        key,cycle=pools[kind][int(rng.integers(len(pools[kind])))]
        start=int(rng.integers(max(0,cycle-127),min(cycle,lengths[key]-128)+1))
        second=(key,start)
    else: second=uniform()
    batch=view.sample_sequences_from_starts((first[0],second[0]),(first[1],second[1]),256,128)
    if int(batch.learn_mask.sum())!=256: raise ValueError('Exactly 256 learning rows required')
    info=dict(sampler=SAMPLER,episode_ids=list(batch.episode_ids),start_cycles=list(batch.start_cycles),
              focus_kind=kind,anchor_episode_id=key,anchor_cycle=cycle,
              learning_rows=256,burn_in_rows=sum(batch.prefix_lengths))
    return batch,info


def flatten(batch):
    mask=batch.learn_mask[:,:,0]
    return ReplayBatch(observations=batch.observations[:,:-1][mask],
        next_observations=batch.observations[:,1:][mask],
        **{f.name:getattr(batch,f.name)[mask] for f in fields(ReplayBatch)
           if f.name not in ('observations','next_observations')})


class OnlineExperiment(Experiment):
    def __init__(self,config,group):
        if group not in ('A','B','C') or config['policy_mode']!=('mlp' if group=='C' else 'gru'):
            raise ValueError('Registered group/architecture required')
        super().__init__(config)
        self.online=dict(group=group,sampler=SAMPLER,labels={},qualification_sha256=None,registration_sha256=None)


def save(experiment,path):
    path=Path(path)
    if path.exists(): raise FileExistsError(path)
    state=dict(base=experiment.state_dict(),online=deepcopy(experiment.online))
    digest(state['online'])
    path.parent.mkdir(parents=True,exist_ok=True)
    with TemporaryDirectory(dir=path.parent,prefix='.online-') as temp:
        staging=Path(temp)/'checkpoint'; staging.mkdir()
        payload=staging/'state.pt'; torch.save(state,payload)
        manifest=dict(version=VERSION,group=experiment.online['group'],config_sha256=digest(experiment.config),
                      state_sha256=hashlib.sha256(payload.read_bytes()).hexdigest())
        encoded=json.dumps(manifest,sort_keys=True).encode()
        (staging/'manifest.json').write_bytes(encoded)
        staging.rename(path)
    pin=hashlib.sha256(encoded).hexdigest()
    experiment._checkpoint=experiment._checkpoint_identity(pin)
    return pin


def load(path,*,config,expected_digest,group=None):
    path=Path(path); encoded=(path/'manifest.json').read_bytes(); meta=json.loads(encoded)
    if (hashlib.sha256(encoded).hexdigest()!=expected_digest or meta.get('version')!=VERSION
            or meta.get('config_sha256')!=digest(config) or (group is not None and group!=meta.get('group'))):
        raise ValueError('Online checkpoint binding differs')
    payload=(path/'state.pt').read_bytes()
    if hashlib.sha256(payload).hexdigest()!=meta['state_sha256']: raise ValueError('Checkpoint payload changed')
    saved=torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)
    if set(saved)!={'base','online'}: raise ValueError('Complete online checkpoint required')
    online=saved['online']; base=saved['base']
    if (set(online)!={'group','sampler','labels','qualification_sha256','registration_sha256'}
            or online['sampler']!=SAMPLER or online['group']!=meta['group']):
        raise ValueError('Online protocol differs')
    result=OnlineExperiment(config,meta['group'])
    # Restore through the unchanged numerical validators. The legacy trained
    # mesh/MLP eligibility restriction is replaced only in THIS version by the
    # pilot's separately pinned per-mode dynamic qualification and provenance.
    tracked=base.get('version')==TRAINING_STATE_VERSION
    clean=deepcopy(base)
    if tracked: clean.pop('training'); clean['version']=STATE_VERSION
    restored=Experiment.from_state(clean,config)
    result.__dict__.update(restored.__dict__); result.online=online
    if tracked:
        result._training=deepcopy(base['training'])
        result._validate_training_state()
        result._approved_replay_state=result._replay._state
        from .search_entry_replay import validate_focus_labels
        if set(online['labels'])!=set(result._replay._state.seen): raise ValueError('Missing online labels')
        for row in result._training['episodes']:
            if (row['qualification_sha256']!=online['qualification_sha256']
                    or row['registration_sha256']!=online['registration_sha256']):
                raise ValueError('Qualification or registration changed within checkpoint')
            validate_focus_labels(online['labels'][row['episode_id']],episode_id=row['episode_id'],transition_count=row['transitions'])
    elif online['labels'] or result.optimizer_updates or len(result._replay):
        raise ValueError('Untracked replay/updates are forbidden')
    result._checkpoint=result._checkpoint_identity(expected_digest)
    return result


@contextmanager
def training_batches(experiment,overlays,overlay_pins):
    """Scope the common sampler around unchanged transactional update kernels."""
    from . import search_entry_replay
    from .geometry_reward_shaping import replace_batch_rewards
    from .switchable_sac import _episode_digest
    originals={key:_episode_digest(a) for key,a in experiment._replay._state.episodes}
    records=[]
    def sequence(rng):
        batch,info=sample_common(experiment._replay,experiment.online['labels'],rng)
        learned=flatten(batch)
        h=hashlib.sha256()
        for f in fields(learned):
            if f.name!='rewards': h.update(getattr(learned,f.name).numpy().tobytes())
        actual=replace_batch_rewards(batch,overlays) if experiment.online['group']!='A' else batch
        info.update(learning_inputs_sha256=h.hexdigest(),
            learning_reward_sha256=hashlib.sha256(flatten(actual).rewards.numpy().tobytes()).hexdigest(),
            reward_overlay_sha256=digest(overlay_pins),reward_scheme='original' if experiment.online['group']=='A' else 'potential',
            changed_learning_rewards=int(torch.count_nonzero(flatten(actual).rewards-learned.rewards)))
        records.append(info)
        return actual,info
    def gru(*args,**kwargs): return sequence(kwargs['rng'])
    def mlp(batch_size,*,rng):
        if batch_size!=256: raise ValueError('Common batch size differs')
        return flatten(sequence(rng)[0])
    target=patch.object(experiment._replay,'sample',mlp) if experiment.policy_mode=='mlp' else patch.object(search_entry_replay,'sample_focus_sequences',gru)
    try:
        with target: yield records
    finally:
        if originals!={key:_episode_digest(a) for key,a in experiment._replay._state.episodes}:
            raise ValueError('Raw replay was mutated')
