"""Update credit and real collector transactions with lightweight physics."""
from copy import deepcopy
import gzip
import importlib
import json
import numpy as np
import pytest

from tools.learning.admission import short_training_config


def api(): return importlib.import_module('tools.learning.sac_collection')


def receipt(n, episode_id='one', **overrides):
    return dict(episode_id=episode_id, status='published', committed=n, discarded=0,
                valid_for_learning=True, simulation_valid=True, physical_stopped=True, **overrides)


def test_credit_starts_after_warmup_without_retroactive_backlog():
    b = api().UpdateBudget(short_training_config())
    b.record(receipt(5000))
    assert b.total == 5000 and b.available == 0
    b.record(receipt(3, 'two'))
    assert b.available == 0
    b.record(receipt(1, 'three'))
    assert b.available == 1
    b.consume()
    assert b.available == 0 and b.completed == 1
    with pytest.raises(RuntimeError): b.consume()


def test_duplicate_publication_and_eviction_do_not_add_or_remove_credit():
    b = api().UpdateBudget(short_training_config())
    b.record(receipt(9000))
    assert b.record(receipt(9000)) is False
    b.record(receipt(9000, 'two', evicted=9000))
    assert b.total == 18000 and b.available == 3250
    with pytest.raises(ValueError): b.record(receipt(5, 'one'))
    b.record(receipt(100000, 'large'))
    assert b.available == 8250


@pytest.mark.parametrize('change', [dict(status='collecting'), dict(valid_for_learning='true'),
    dict(committed=True), dict(committed=-1), dict(discarded=2), dict(physical_stopped=False)])
def test_unqualified_or_ambiguous_receipt_never_earns_credit(change):
    b = api().UpdateBudget(short_training_config())
    r = receipt(5004); r.update(change)
    with pytest.raises(ValueError): b.record(r)
    assert b.total == b.available == 0


def test_warmup_stream_is_reproducible_and_separate_from_initialization():
    from tools.learning.admitted_collection import EngineeringSampler
    cfg = short_training_config()
    a, b = api().WarmupPolicy(cfg), api().WarmupPolicy(cfg)
    sampler = EngineeringSampler(cfg)
    for _ in range(20): sampler.next_case()
    values = []
    for _ in range(20):
        x, _ = a.predict(np.zeros(120)); y, _ = b.predict(np.zeros(120))
        assert np.array_equal(x, y) and (abs(x) <= 1).all()
        values.append(x)
    assert np.std(values) > .3


def make(tmp_path, monkeypatch, runtime):
    from tests.learning.test_admitted_collection import Session
    import tools.learning.admitted_collection as collector_module
    m = api()
    from tools.learning.b2_sac_admission import SACAdmission
    permit = object.__new__(SACAdmission)
    permit._record = {'config': short_training_config()}
    permit.expected_digest = 'unit-test-admission'
    permit.verify = lambda case=None: deepcopy(permit._record)
    monkeypatch.setattr(collector_module, '_new_session', lambda config: Session())
    monkeypatch.setattr(collector_module, '_physical_audit', lambda s: dict(
        simulation_valid=True, task_outcome='TASK_FAILURE', physical_stopped=s.done,
        valid_for_learning=s.done, guard_violations={'contact': False, 'motion': False}))
    chain = m.SACCollection(admission=permit, output=tmp_path / 'episodes')
    return chain


def test_unfinished_and_unpublished_data_cannot_update(tmp_path, monkeypatch, runtime):
    c = make(tmp_path, monkeypatch, runtime)
    c.start('one')
    c.collect(1)
    assert c.budget.total == len(c.replay) == 0
    with pytest.raises(RuntimeError): c.update(1)
    c.collect(10)
    assert c.budget.total == 3 and len(c.replay) == 3
    assert c.update(1) == []


def test_publication_retry_records_credit_once_and_uses_updated_count(tmp_path, monkeypatch, runtime):
    c = make(tmp_path, monkeypatch, runtime)
    # The numerical updater is tested with real tensors; metadata must use its actual counter.
    c.updater.counts['critic'] = 7
    c.start('after_update')
    c.collect(10)
    raw = json.loads(gzip.decompress((tmp_path / 'episodes/after_update/episode.json.gz').read_bytes()))
    assert raw['optimizer_steps'] == raw['optimizer_steps_start'] == 7
    assert raw['policy_sha256'] == c.updater.fingerprints()['actor']
    assert c.budget.total == 3
    c.sync_publications()
    assert c.budget.total == 3
