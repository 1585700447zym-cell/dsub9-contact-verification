"""Durable learning-state boundaries; physical audit is exercised by native probe."""
from copy import deepcopy
import importlib
import json
from pathlib import Path

import numpy as np
import pytest
import torch

from tests.learning.test_sac_collection import make
from tests.learning.test_sac_update import equal


def api(): return importlib.import_module('tools.learning.sac_checkpoint')


def ready(tmp_path, monkeypatch, runtime):
    c = make(tmp_path, monkeypatch, runtime)
    monkeypatch.setattr(api(), '_audit_physics', lambda raw: None)
    c.start('one'); c.collect(10)
    return c


def save(c, tmp_path):
    path = tmp_path / 'checkpoint'
    sha = api().save_checkpoint(c, path)
    return path, sha


def mutate(path, change):
    from tools.learning.admission import digest
    state = torch.load(path / 'state.pt', weights_only=True)
    change(state)
    torch.save(state, path / 'state.pt')
    manifest = json.loads((path / 'manifest.json').read_text())
    manifest['state_sha256'] = digest(path / 'state.pt')
    (path / 'manifest.json').write_text(json.dumps(manifest))
    return digest(path / 'manifest.json')


def test_roundtrip_preserves_all_streams_and_consumed_ids(tmp_path, monkeypatch, runtime):
    c = ready(tmp_path, monkeypatch, runtime)
    path, sha = save(c, tmp_path)
    d = api().load_checkpoint(path, expected_digest=sha, admission=c.admission, output=tmp_path / 'resumed')
    equal(api().capture(c), api().capture(d))
    assert c.sampler.next_case() == d.sampler.next_case()
    assert np.array_equal(c.warmup.predict(np.zeros(120))[0], d.warmup.predict(np.zeros(120))[0])
    equal(vars(c.replay.sample(16, rng=c.replay_rng)), vars(d.replay.sample(16, rng=d.replay_rng)))
    assert np.array_equal(c.updater.predict(np.zeros(120))[0], d.updater.predict(np.zeros(120))[0])
    with pytest.raises((RuntimeError, FileExistsError)): d.start('one')


@pytest.mark.parametrize('where,value', [('active', True), ('_blocked', True), ('_pending', {}),
    ('_status_pending', True), ('session', object())])
def test_only_published_stopped_boundary_can_save(tmp_path, monkeypatch, runtime, where, value):
    c = ready(tmp_path, monkeypatch, runtime)
    setattr(c.collector, where, value)
    with pytest.raises((RuntimeError, ValueError)): save(c, tmp_path)
    assert not (tmp_path / 'checkpoint').exists()


@pytest.mark.parametrize('owner', ['chain', 'updater'])
def test_failed_chain_never_saves(tmp_path, monkeypatch, runtime, owner):
    c = ready(tmp_path, monkeypatch, runtime)
    (c if owner == 'chain' else c.updater).failed = True
    with pytest.raises((RuntimeError, ValueError)): save(c, tmp_path)


@pytest.mark.parametrize('change', [
    lambda s: s['budget'].update(total=99),
    lambda s: s['budget'].update(completed=1),
    lambda s: s['replay'].update(seen=[]),
    lambda s: s['sampler'].update(count=True),
    lambda s: s['sampler'].update(count=2),
    lambda s: s['attempts'][0].update(physical_stopped=False),
    lambda s: s['attempts'].append(deepcopy(s['attempts'][0])),
    lambda s: s['updater']['counts'].update(actor=1),
    lambda s: s['updater'].update(alpha=torch.tensor([0.])),
    lambda s: s['updater']['policy'].__setitem__(next(iter(s['updater']['policy'])), torch.zeros(1)),
    lambda s: s['replay']['episodes'][0][1]['actions'].fill_(float('nan')),
    lambda s: s['binding'].update(qualification_sha256='different'),
    lambda s: s['binding']['record'].update(source_sha256={'wrong': 'source'}),
    lambda s: s['rng'].update(replay={'bit_generator': 'MT19937'}),
    lambda s: s['updater'].update(rng=torch.zeros(2, dtype=torch.uint8)),
])
def test_inconsistent_state_is_rejected_before_creating_output(tmp_path, monkeypatch, runtime, change):
    c = ready(tmp_path, monkeypatch, runtime)
    path, _ = save(c, tmp_path); sha = mutate(path, change)
    with pytest.raises((RuntimeError, ValueError, KeyError, TypeError)):
        api().load_checkpoint(path, expected_digest=sha, admission=c.admission, output=tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()


def test_corruption_pin_and_no_overwrite(tmp_path, monkeypatch, runtime):
    c = ready(tmp_path, monkeypatch, runtime)
    path, sha = save(c, tmp_path)
    with pytest.raises(FileExistsError): api().save_checkpoint(c, path)
    with pytest.raises(ValueError):
        api().load_checkpoint(path, expected_digest='wrong', admission=c.admission, output=tmp_path / 'bad')
    with (path / 'state.pt').open('ab') as f: f.write(b'corrupt')
    with pytest.raises(ValueError):
        api().load_checkpoint(path, expected_digest=sha, admission=c.admission, output=tmp_path / 'bad')
    assert not (tmp_path / 'bad').exists()


def test_write_failure_never_publishes_checkpoint(tmp_path, monkeypatch, runtime):
    c = ready(tmp_path, monkeypatch, runtime)
    def fail(*a, **k): raise OSError('injected disk write failure')
    monkeypatch.setattr(torch, 'save', fail)
    with pytest.raises(OSError): save(c, tmp_path)
    assert not (tmp_path / 'checkpoint').exists()


def test_loaded_adam_moments_next_updates_match(tmp_path, monkeypatch, runtime):
    c = ready(tmp_path, monkeypatch, runtime)
    # Long, continuous synthetic episodes exercise real replay and Adam state.
    from tests.learning.test_admitted_collection import Session
    import tools.learning.admitted_collection as cm
    class Long(Session):
        def snapshot(self):
            s = super().snapshot(); s.policy_observation = [self.i / 10000.] * 120
            s.residual_enabled = True
            return s
        def advance_cycle(self, action):
            r = super().advance_cycle(action); self.done = self.i >= 2600
            r.done = self.done
            return r
    monkeypatch.setattr(cm, '_new_session', lambda config: Long())
    for name in ('long_a', 'long_b'):
        c.start(name); c.collect(3000)
    assert len(c.update(8)) == 8
    path, sha = save(c, tmp_path)
    d = api().load_checkpoint(path, expected_digest=sha, admission=c.admission, output=tmp_path / 'resumed')
    equal(api().capture(c), api().capture(d))
    from tools.validation.verify_sac_update import comparable
    assert comparable(c.update(8)) == comparable(d.update(8))
    equal(c.updater._snapshot(), d.updater._snapshot())
    assert c.update(100) == d.update(100) == []
    sha2 = mutate(path, lambda s: s['updater']['actor']['state'][0].update(exp_avg=torch.zeros(1)))
    with pytest.raises(ValueError):
        api().load_checkpoint(path, expected_digest=sha2, admission=c.admission, output=tmp_path / 'bad')


def test_evicted_ids_and_total_credit_survive_restore(tmp_path, monkeypatch, runtime):
    c = ready(tmp_path, monkeypatch, runtime)
    # Shrink only this fixture's pool so whole-episode eviction needs six rows.
    from tools.learning.audited_replay import AuditedReplay
    c.replay.capacity = 3
    monkeypatch.setattr(api(), 'AuditedReplay', lambda **kwargs: AuditedReplay(capacity=3))
    c.start('two'); c.collect(10)
    assert c.replay.episode_ids == ('two',) and c.budget.total == 6
    path, sha = save(c, tmp_path)
    d = api().load_checkpoint(path, expected_digest=sha, admission=c.admission, output=tmp_path / 'resumed')
    assert d.replay.episode_ids == ('two',) and d.replay._state.seen == {'one', 'two'}
    assert len(d.replay) == 3 and d.budget.total == 6
    with pytest.raises(RuntimeError): d.replay.publish('one', [], outcome={}, training_admitted=True)
    with pytest.raises(FileExistsError): d.start('one')


@pytest.mark.parametrize('point', ['manifest', 'rename'])
def test_late_write_failure_keeps_old_chain_and_no_committed_path(tmp_path, monkeypatch, runtime, point):
    c = ready(tmp_path, monkeypatch, runtime); before = api().capture(c)
    def fail(*a, **k): raise OSError('injected commit failure')
    if point == 'manifest': monkeypatch.setattr(api(), '_flush_write', fail)
    else: monkeypatch.setattr(api().os, 'rename', fail)
    with pytest.raises(OSError): save(c, tmp_path)
    assert not (tmp_path / 'checkpoint').exists()
    equal(before, api().capture(c))


def test_unflushed_receipt_and_stale_permission_prevent_save(tmp_path, monkeypatch, runtime):
    c = ready(tmp_path, monkeypatch, runtime)
    c.collector.attempts[0]['steps'] = 4
    with pytest.raises(ValueError): save(c, tmp_path)
    c.collector.attempts[0]['steps'] = 3
    def stale(*a, **k): raise ValueError('source changed')
    c.admission.verify = stale
    with pytest.raises(ValueError): save(c, tmp_path)


@pytest.mark.parametrize('start,end', [(100, 101), (1, 0), (-1, -1), (True, True), (1, 1)])
def test_consistently_rewritten_receipts_cannot_invent_episode_update_counts(tmp_path, monkeypatch, runtime, start, end):
    import gzip, hashlib
    from tools.learning.admission import canonical
    c = ready(tmp_path, monkeypatch, runtime)
    state = api().capture(c)
    raw = json.loads(gzip.decompress(state['archives']['one']))
    raw.update(optimizer_steps_start=start, optimizer_steps=end)
    state['archives']['one'] = gzip.compress(canonical(raw).encode(), mtime=0)
    r = state['attempts'][0]
    r.update(optimizer_steps_start=start, optimizer_steps=end,
        archive_sha256=hashlib.sha256(state['archives']['one']).hexdigest())
    state['budget']['receipts']['one'] = canonical(r)
    with pytest.raises(ValueError): api().validate_state(state, c.admission)


def test_duplicate_id_consumed_initializer_can_be_faithfully_saved(tmp_path, monkeypatch, runtime):
    c = ready(tmp_path, monkeypatch, runtime)
    with pytest.raises(FileExistsError): c.start('one')
    assert c.sampler.count == 2 and len(c.collector.attempts) == 1
    path, sha = save(c, tmp_path)
    d = api().load_checkpoint(path, expected_digest=sha, admission=c.admission, output=tmp_path / 'resumed')
    assert d.sampler.count == 2
    assert c.sampler.next_case() == d.sampler.next_case()

