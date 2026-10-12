"""Real replay/file transactions; lightweight physics fixture for failure branches."""
from copy import deepcopy
import gzip
import importlib
import json
from types import SimpleNamespace

import numpy as np
import pytest


@pytest.fixture(autouse=True)
def qualified_native_import(runtime):
    """The case type imports MuJoCo; select the genuine isolated package first."""
    return runtime


def api():
    return importlib.import_module('tools.learning.admitted_collection')


def row(end=False):
    return dict(observation=[0.] * 120, next_observation=[0.] * 120,
        action=[0.] * 4, reward=-.1, terminated=end, truncated=False,
        action_active=True, next_action_active=False, dt=.002,
        discount=0.9998000199986667)


@pytest.mark.parametrize('permission', ['false', 1, None])
def test_formal_buffer_rejects_ambiguous_permission(permission):
    b, sink = api().FormalEpisodeBuffer(), []
    b.stage(row(True))
    with pytest.raises(TypeError):
        b.finalize(valid_for_learning=permission, sink=sink)
    assert sink == []


def test_formal_buffer_cannot_publish_unfinished_or_empty_episode():
    b, sink = api().FormalEpisodeBuffer(), []
    with pytest.raises(ValueError):
        b.finalize(valid_for_learning=True, sink=sink)
    b.stage(row())
    with pytest.raises(ValueError):
        b.finalize(valid_for_learning=True, sink=sink)
    assert sink == []


def test_engineering_sampler_is_repeatable_and_does_not_reuse_initializations():
    from tools.learning.admission import short_training_config
    a, b = api().EngineeringSampler(short_training_config()), api().EngineeringSampler(short_training_config())
    first, second = a.next_case(), a.next_case()
    assert first == b.next_case() and second == b.next_case()
    assert first['name'] != second['name']
    assert (first['x_offset_m'], first['y_offset_m']) != (second['x_offset_m'], second['y_offset_m'])
    for _ in range(25):
        case = a.next_case()
        assert abs(case['x_offset_m']) <= 50e-6 and abs(case['y_offset_m']) <= 50e-6
        assert case['roll_rad'] == case['pitch_rad'] == 0



class Permit:
    expected_digest = 'test-permit'
    config = {'guard': {}, 'learning': {'replay_capacity': 100},
              'sampling': {'watchdog_cycles': 13000}}
    def __init__(self): self.checks = 0; self.stale = False
    def verify(self, case=None):
        from tools.learning.admission import validate_case
        self.checks += 1
        if self.stale: raise ValueError('Stale qualification')
        if case is not None: validate_case(case)


class Session:
    def __init__(self):
        self.i = 0; self.done = False; self.external_cut = False
        self.stop_time = 0.; self.interface_fault = None; self.reason = 'TIME_LIMIT'
        self.env = SimpleNamespace(data=SimpleNamespace(time=0.), events=[], stop_samples=[],
            guard_facts={'simulation_valid': True, 'invalid_reasons': [],
                         'contact_reasons': [], 'motion_reasons': []})
    def snapshot(self):
        return SimpleNamespace(policy_observation=[self.i / 100.] * 120,
                               residual_enabled=self.i < 2, time_s=self.env.data.time)
    def reset(self, case, seed=None): return self.snapshot()
    def prepare_cycle(self): return self.snapshot()
    def advance_cycle(self, action):
        from tools.learning.action import normalized_action
        normalized_action(action)
        self.i += 1; self.env.data.time = self.i * .002
        self.done = self.i >= (4 if self.external_cut else 3)
        return SimpleNamespace(next_snapshot=self.snapshot(), done=self.done, dt=.002,
            reward_terms={'total': -.1, 'terminal': -2. if self.done else 0.},
            action_log={'experience_action': list(action)},
            trace_row={'time_s': self.env.data.time}, events=[])
    def start_external_tail(self): self.external_cut = True


class Policy:
    def predict(self, obs, deterministic=False): return np.zeros(4), None


def make(tmp_path, monkeypatch):
    m = api()
    monkeypatch.setattr(m, 'CollectionAdmission', Permit)
    monkeypatch.setattr(m, '_new_session', lambda config: Session())
    monkeypatch.setattr(m, '_physical_audit', lambda s: dict(
        simulation_valid=True, task_outcome='TASK_FAILURE', physical_stopped=s.done,
        valid_for_learning=s.done, guard_violations={'contact': False, 'motion': False}))
    from tools.learning.audited_replay import AuditedReplay
    c = m.AdmittedCollector(admission=Permit(), replay=AuditedReplay(capacity=100),
                           output=tmp_path / 'run')
    case = SimpleNamespace(name='test', x_offset_m=0., y_offset_m=0., roll_rad=0.,
        pitch_rad=0., start_origin_z_m=-.004, target_depth_m=.004)
    return c, case


def test_batch_pause_preserves_episode_and_publication_is_audited(tmp_path, monkeypatch):
    c, case = make(tmp_path, monkeypatch)
    c.start('one', case=vars(case), seed=1)
    c.collect(Policy(), 1)
    assert c.active and len(c.replay) == 0
    with pytest.raises(RuntimeError): c.start('two', case=vars(case), seed=2)
    c.collect(Policy(), 10)
    assert not c.active and len(c.replay) == 3
    assert c.admission.checks >= 2
    raw = json.loads(gzip.decompress((tmp_path / 'run/one/episode.json.gz').read_bytes()))
    assert raw['outcome']['valid_for_learning'] is True
    assert raw['transitions'][-1]['terminated'] is True
    assert c.attempts[0]['committed'] == 3
    assert 'transitions' not in c.attempts[0]


def test_real_cut_keeps_original_next_state_not_stop_tail(tmp_path, monkeypatch):
    c, case = make(tmp_path, monkeypatch)
    c.start('cut', case=vars(case), seed=2)
    c.collect(Policy(), 1, cut_at_end=True)
    assert len(c.replay) == 1
    batch = c.replay.sample(1, rng=np.random.default_rng(0))
    assert batch.truncated.item() and not batch.terminated.item()
    assert batch.next_observations[0, 0].item() == pytest.approx(.01)
    assert c.attempts[0]['audit_end_time_s'] == .008


def test_domain_failure_is_archived_and_does_not_silently_resample(tmp_path, monkeypatch):
    c, case = make(tmp_path, monkeypatch)
    case.x_offset_m = 51e-6
    with pytest.raises(ValueError): c.start('outside', case=vars(case), seed=1)
    assert len(c.replay) == 0
    assert c.attempts[0]['status'] == 'rejected_before_reset'
    assert (tmp_path / 'run/outside/status.json').is_file()


def test_stale_source_after_collection_blocks_publication(tmp_path, monkeypatch):
    c, case = make(tmp_path, monkeypatch)
    c.start('stale', case=vars(case), seed=1)
    c.admission.stale = True
    with pytest.raises(ValueError): c.collect(Policy(), 10)
    assert len(c.replay) == 0
    assert c.attempts[0]['status'] == 'pending_publication'
    with pytest.raises(RuntimeError): c.start('next', case=vars(case), seed=2)


def test_archive_failure_cannot_eagerly_publish_and_retry_does_not_resimulate(tmp_path, monkeypatch):
    c, case = make(tmp_path, monkeypatch)
    c.start('io', case=vars(case), seed=1)
    write = api()._write_archive
    def fail(*args): raise OSError('disk unavailable')
    monkeypatch.setattr(api(), '_write_archive', fail)
    with pytest.raises(OSError): c.collect(Policy(), 10)
    assert len(c.replay) == 0 and c.session.i == 3
    monkeypatch.setattr(api(), '_write_archive', write)
    c.retry_publication()
    assert len(c.replay) == 3 and c.session is None
    with pytest.raises(RuntimeError): c.retry_publication()
    with pytest.raises(FileExistsError): c.start('io', case=vars(case), seed=1)


def test_policy_exception_is_stopped_archived_and_never_learned(tmp_path, monkeypatch):
    c, case = make(tmp_path, monkeypatch)
    class Broken:
        def predict(self, *args, **kwargs): raise RuntimeError('policy broken')
    c.start('bad', case=vars(case), seed=1)
    with pytest.raises(RuntimeError, match='policy broken'): c.collect(Broken(), 1)
    assert len(c.replay) == 0
    assert c.attempts[0]['status'] == 'rejected'
    assert c.attempts[0]['physical_stopped']
    with pytest.raises(RuntimeError): c.start('retry', case=vars(case), seed=2)


def test_failed_audit_latches_reset_closed(tmp_path, monkeypatch):
    c, case = make(tmp_path, monkeypatch)
    c.start('audit-error', case=vars(case), seed=1)
    def broken_audit(session): raise RuntimeError('audit unavailable')
    monkeypatch.setattr(api(), '_physical_audit', broken_audit)
    with pytest.raises(RuntimeError, match='audit unavailable'): c.collect(Policy(), 3)
    assert len(c.replay) == 0
    with pytest.raises(RuntimeError): c.start('new', case=vars(case), seed=2)
    raw = json.loads(gzip.decompress((tmp_path / 'run/audit-error/episode.json.gz').read_bytes()))
    assert raw['outcome']['valid_for_learning'] is False and len(raw['transitions']) == 3
    assert 'audit unavailable' in raw['fault']['audit_error']


def test_early_status_failure_retains_a_retriable_complete_episode(tmp_path, monkeypatch):
    c, case = make(tmp_path, monkeypatch)
    c.start('early-status', case=vars(case), seed=1)
    write = api()._write_json
    def fail_status(path, value):
        if value.get('status') == 'pending_publication': raise OSError('early status unavailable')
        return write(path, value)
    monkeypatch.setattr(api(), '_write_json', fail_status)
    with pytest.raises(OSError): c.collect(Policy(), 3)
    assert len(c.replay) == 0 and c.session.i == 3
    monkeypatch.setattr(api(), '_write_json', write)
    c.retry_publication()
    assert len(c.replay) == 3 and c.session is None


def test_status_write_retry_after_commit_never_republishes(tmp_path, monkeypatch):
    c, case = make(tmp_path, monkeypatch)
    c.start('status', case=vars(case), seed=1)
    write = api()._write_json
    def fail_status(path, value):
        if value.get('status') == 'published': raise OSError('status write failed')
        return write(path, value)
    monkeypatch.setattr(api(), '_write_json', fail_status)
    with pytest.raises(OSError): c.collect(Policy(), 3)
    assert len(c.replay) == 3
    with pytest.raises(RuntimeError): c.start('new', case=vars(case), seed=2)
    monkeypatch.setattr(api(), '_write_json', write)
    c.retry_publication()
    assert len(c.replay) == 3
    status = json.loads((tmp_path / 'run/status/status.json').read_text(encoding='utf-8'))
    assert status['status'] == 'published' and status['committed'] == 3


@pytest.mark.parametrize('outcome', ['CONTACT_GUARD', 'MOTION_VIOLATION'])
def test_valid_protection_failure_is_preserved_not_discarded(tmp_path, monkeypatch, outcome):
    c, case = make(tmp_path, monkeypatch)
    monkeypatch.setattr(api(), '_physical_audit', lambda s: dict(simulation_valid=True,
        task_outcome=outcome, physical_stopped=True, valid_for_learning=True))
    c.start('guard', case=vars(case), seed=1)
    c.collect(Policy(), 3)
    assert len(c.replay) == 3 and c.attempts[0]['task_outcome'] == outcome


@pytest.mark.parametrize('invalid,stopped', [(True, True), (False, False)])
def test_invalid_or_unstopped_whole_episode_is_archived_not_published(tmp_path, monkeypatch, invalid, stopped):
    c, case = make(tmp_path, monkeypatch)
    monkeypatch.setattr(api(), '_physical_audit', lambda s: dict(simulation_valid=not invalid,
        task_outcome='INVALID_SIMULATION' if invalid else 'STOP_NOT_QUALIFIED',
        physical_stopped=stopped, valid_for_learning=False))
    c.start('rejected', case=vars(case), seed=1)
    c.collect(Policy(), 3)
    assert len(c.replay) == 0 and c.attempts[0]['discarded'] == 3
    assert (tmp_path / 'run/rejected/episode.json.gz').is_file()
    with pytest.raises(RuntimeError): c.start('new', case=vars(case), seed=2)


def test_nonfinite_reward_latches_whole_episode_rejection(tmp_path, monkeypatch):
    c, case = make(tmp_path, monkeypatch)
    class InvalidData(Session):
        def advance_cycle(self, action):
            result = super().advance_cycle(action)
            if self.i == 1: result.reward_terms['total'] = float('nan')
            return result
    monkeypatch.setattr(api(), '_new_session', lambda config: InvalidData())
    c.start('invalid-data', case=vars(case), seed=1)
    c.collect(Policy(), 3)
    assert len(c.replay) == 0 and c.attempts[0]['status'] == 'rejected'
    assert c.attempts[0]['discarded'] == 3
