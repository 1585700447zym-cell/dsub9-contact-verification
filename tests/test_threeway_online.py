from copy import deepcopy
import numpy as np
import pytest
import torch
from test_recurrent_replay import episode as source_episode, publish
from tools.learning.recurrent_replay import RecurrentReplay
from tools.learning.five_axis_replay import FiveAxisReplay
from tools.learning.threeway_online import sample_common, flatten, OnlineExperiment, save, load
from tools.learning.recovery_learning_contract import experiment_config
from tools.learning.recovery_learning_contract import digest
from tools.learning.threeway_online import training_batches
from tools.learning.switchable_sac import _episode_digest
from tools.learning.search_entry_replay import LABEL_VERSION


def episode(label, phases):
    rows=source_episode(label,phases)
    for row in rows:
        row['observation'][0]/=100
        row['next_observation'][0]/=100
    return rows


def test_common_sampler_has_same_learning_rows_and_terminal_coverage():
    r, m = RecurrentReplay(capacity=1000), FiveAxisReplay(capacity=1000)
    for key, n in [('a', 128), ('b', 130)]:
        rows = episode(1, [True]*(n-1)+[False])
        publish(r, key, rows); publish(m, key, rows)
    labels = {key: dict(anchors=[]) for key in r.episode_ids}
    x, ix = sample_common(r, labels, np.random.default_rng(2))
    y, iy = sample_common(m, labels, np.random.default_rng(2))
    x.validate(); y.validate()
    assert ix == iy and x.learn_mask.sum() == 256
    torch.testing.assert_close(flatten(x).observations, flatten(y).observations)
    assert flatten(x).terminated.any()
    assert flatten(x).observations.shape == (256, 140)


@pytest.mark.parametrize('group,mode', [('A','gru'),('B','gru'),('C','mlp')])
def test_checkpoint_roundtrip_and_wrong_group_rejected(tmp_path, group, mode):
    cfg=experiment_config(mode, seed=2026110801, physical_protocol='load_warning_7pct_mesh_contact', focus_search_entry=mode=='gru')
    obj=OnlineExperiment(cfg, group)
    pin=save(obj,tmp_path/'saved')
    restored=load(tmp_path/'saved',config=cfg,expected_digest=pin,group=group)
    assert restored.optimizer_updates==0 and not len(restored._replay)
    for k,v in obj.actor.state_dict().items(): torch.testing.assert_close(v,restored.actor.state_dict()[k])
    with pytest.raises(ValueError): load(tmp_path/'saved',config=cfg,expected_digest=pin,group='C' if group!='C' else 'A')


def test_focus_window_includes_anchor_and_rejects_short_only():
    replay=RecurrentReplay(capacity=1000)
    publish(replay,'a',episode(1,[True]*200+[False]))
    labels={'a':dict(anchors=[dict(cycle=200,kind='main_fit')])}
    batch,info=sample_common(replay,labels,np.random.default_rng(5))
    assert info['anchor_cycle']==200 and batch.start_cycles[1]==73
    assert flatten(batch).terminated.any()
    short=RecurrentReplay(capacity=100)
    publish(short,'a',episode(1,[True,False]))
    with pytest.raises(ValueError): sample_common(short,{'a':dict(anchors=[])},np.random.default_rng(1))


@pytest.mark.parametrize('group,mode', [('A','gru'),('B','gru'),('C','mlp')])
def test_real_update_tracked_restore_and_continuation(tmp_path,group,mode):
    cfg=experiment_config(mode,seed=2026110801,physical_protocol='load_warning_7pct_mesh_contact',focus_search_entry=mode=='gru')
    obj=OnlineExperiment(cfg,group);obj._training=dict(episodes=[],updates=[])
    overlays={};pins={}
    for key in ('one','two'):
        rows=episode(1,[True]*139+[False]);publish(obj._replay,key,rows)
        arrays=obj._replay._state.episodes[-1][1]
        labels=dict(version=LABEL_VERSION,episode_id=key,transitions=len(rows),anchors=[])
        obj.online['labels'][key]=labels
        record={name:'a'*64 for name in ('archive_sha256','registration_sha256','qualification_sha256','source_checkpoint_sha256','job_sha256','audit_sha256')}
        record.update(episode_id=key,transitions=len(rows),optimizer_updates=0,replay_sha256=_episode_digest(arrays))
        if mode=='gru': record.update(search_entry_focus=labels,search_entry_focus_sha256=digest(labels))
        obj._training['episodes'].append(record)
        overlays[key]=arrays['rewards'][:,0].astype(np.float64)+.001;pins[key]='b'*64
    obj._approved_replay_state=obj._replay._state
    obj.online.update(qualification_sha256='a'*64,registration_sha256='a'*64)
    before={k:_episode_digest(a) for k,a in obj._replay._state.episodes}
    with training_batches(obj,overlays,pins) as records:
        result=obj.update_from_replay()
        if mode=='mlp': obj._training['updates'][-1].update(records[-1])
    assert result['batch_rows']==256 and obj.optimizer_updates==1
    assert (records[0]['changed_learning_rewards']>0)==(group!='A')
    assert before=={k:_episode_digest(a) for k,a in obj._replay._state.episodes}
    pin=save(obj,tmp_path/'trained')
    restored=load(tmp_path/'trained',config=cfg,expected_digest=pin,group=group)
    assert restored.training_summary==obj.training_summary
    with training_batches(restored,overlays,pins) as records:
        restored.update_from_replay()
        if mode=='mlp': restored._training['updates'][-1].update(records[-1])
    assert restored.optimizer_updates==2
    save(restored,tmp_path/'continued')
