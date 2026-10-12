from copy import deepcopy
import importlib
from types import SimpleNamespace
import numpy as np
import pytest

from tools.learning.admission import short_training_config
from tests.learning.test_b2_training_admission import unit_permit


def train_api(): return importlib.import_module('tools.learning.engineering_training')
def eval_api(): return importlib.import_module('tools.learning.engineering_evaluation')


def test_more_than_sixteen_updates_and_full_adam_restore(tmp_path, monkeypatch, runtime):
    from tests.learning.test_sac_checkpoint import ready
    from tests.learning.test_admitted_collection import Session
    from tools.learning.sac_checkpoint import save_checkpoint, load_checkpoint, _same
    from tools.validation.verify_sac_update import comparable
    import tools.learning.admitted_collection as cm
    c = ready(tmp_path, monkeypatch, runtime)
    c.admission = c.collector.admission = unit_permit()
    class Long(Session):
        def snapshot(self):
            s = super().snapshot(); s.policy_observation = [self.i / 10000.] * 120; s.residual_enabled = True
            return s
        def advance_cycle(self, action):
            r = super().advance_cycle(action); self.done = self.i >= 2600; r.done = self.done; return r
    monkeypatch.setattr(cm, '_new_session', lambda config: Long())
    for name in ('long_a', 'long_b'):
        c.start(name); c.collect(3000)
    assert len(c.update(17)) == 17
    path = tmp_path / 'checkpoint'; sha = save_checkpoint(c, path)
    d = load_checkpoint(path, expected_digest=sha, admission=c.admission, output=tmp_path / 'resumed')
    assert _same(c.updater._snapshot(), d.updater._snapshot())
    assert comparable(c.update(3)) == comparable(d.update(3))
    assert _same(c.updater._snapshot(), d.updater._snapshot())


class FakeChain:
    def __init__(self, fail=False):
        from tools.learning.sac_collection import UpdateBudget
        self.config = short_training_config(); self.admission = unit_permit()
        self.budget = UpdateBudget(self.config); self.history = []; self.fail = fail
        self.collector = SimpleNamespace(active=False, attempts=[])
        self.updater = SimpleNamespace(counts=dict(critic=0, actor=0, temperature=0, target=0))
    def start(self, name):
        self.collector.active = True; self.name = name; self.steps = 0
    def collect(self, n):
        if self.fail: raise RuntimeError('invalid simulation retained')
        self.steps += n
        if self.steps >= 3000:
            from tests.learning.test_sac_collection import receipt
            r = receipt(3000, self.name); self.collector.attempts.append(r)
            self.budget.record(r); self.collector.active = False
        return dict(total_steps=self.steps, episode_finished=not self.collector.active)
    def update(self, n):
        assert not self.collector.active
        for _ in range(min(n, self.budget.available)):
            self.budget.consume()
            for k in self.updater.counts: self.updater.counts[k] += 1
            self.history.append(dict(critic_batches=self.budget.completed))
        return self.history[-n:]


def fake_checkpoint(chain, path):
    path.mkdir(parents=True); (path / 'state.pt').write_bytes(b'unit')
    return 'test-pin'


def test_target_finishes_whole_episode_and_consumes_only_earned_credit(tmp_path, monkeypatch):
    m = train_api(); c = FakeChain()
    monkeypatch.setattr(m, 'save_checkpoint', fake_checkpoint)
    report = m.run_training(c, tmp_path)
    assert report['cumulative_audited'] == 21000 and report['overshoot_cycles'] == 1000
    assert len(c.collector.attempts) == 7 and not c.collector.active
    assert c.updater.counts['critic'] == 4000 and c.budget.available == 0


def test_invalid_attempt_halts_without_resampling(tmp_path, monkeypatch):
    m = train_api(); c = FakeChain(fail=True)
    monkeypatch.setattr(m, 'save_checkpoint', fake_checkpoint)
    with pytest.raises(RuntimeError): m.run_training(c, tmp_path)
    assert c.name == 'train_000000' and c.updater.counts['critic'] == 0


def test_only_existing_eight_validation_cases_are_selected():
    rows = eval_api().evaluation_cases()
    assert [r['name'] for r in rows] == [f'validation_small_xy_{i:02d}' for i in range(8)]
    assert rows[0]['x_offset_m'] == -14.049548190230155e-6
    assert all(r['roll_rad'] == r['pitch_rad'] == 0 for r in rows)


def test_evaluation_is_deterministic_and_never_publishes_training_data(tmp_path, monkeypatch, runtime):
    from tests.learning.test_sac_collection import make
    c = make(tmp_path, monkeypatch, runtime); m = eval_api()
    # Use the lightweight session's outcome; real physics is audited in the run.
    e = m.EvaluationCollector(admission=c.admission, output=tmp_path / 'eval',
        checkpoint_sha256='fixed', method='zero_b2', updater=c.updater)
    e.start('one', case=m.evaluation_cases()[0], seed=2026092609)
    while e.active: e.collect(m.ZeroPolicy(), 10, deterministic=True)
    assert len(e.replay) == 0 and e.attempts[0]['committed'] == 0
    assert e.attempts[0]['training_admitted'] is False
    assert len(c.replay) == 0 and c.budget.total == 0 and c.updater.counts['critic'] == 0
    p = m.FrozenPolicy(c.updater)
    before = c.updater._snapshot()
    assert np.array_equal(p.predict(np.zeros(120))[0], p.predict(np.zeros(120))[0])
    from tools.learning.sac_checkpoint import _same
    assert _same(before, c.updater._snapshot())


def test_metrics_include_peak_load_and_effective_action_without_mixing_units():
    m = eval_api()
    row = dict(dt=.002, reward=1., action_active=True,
        reward_terms=dict(force=-.0004, torque=-.0016),
        action_log=dict(raw_action=[1., 0., 0., 0.], effective_command_delta=[.0001,0,0,0,0,0],
            applied_residual=[.00015,0,0,0,0,0], actual_end_limited_command=[.0001,0,.001,0,0,0],
            continuously_clipped_s=.002),
        trace_row=dict(contact_count=1, penetration_m=.00001, position_m=[.00002,0,0],
            velocity_world=[0,0,0,0,0,0]))
    raw = dict(transitions=[row], stop_time=1., audit_end_time_s=3.,
        outcome=dict(task_outcome='TASK_FAILURE', simulation_valid=True, physical_stopped=True))
    v = m.episode_metrics(raw)
    assert v['force_peak_N'] == pytest.approx(.025)
    assert v['torque_peak_Nm'] == pytest.approx(.001)
    assert v['effective_action_cycles'] == 1 and v['contact_cycles'] == 1
    assert v['success'] is False and v['return'] == 1.


def test_preregistration_fixes_final_checkpoint_selection_and_eval_set():
    m = importlib.import_module('tools.validation.run_engineering_short_train')
    p = m.verification_protocol(); m.validate_protocol(p)
    assert p['checkpoint_selection'] == 'final_after_target_whole_episode_and_updates'
    q = deepcopy(p); q['evaluation_cases'] = q['evaluation_cases'][:-1]
    with pytest.raises(ValueError): m.validate_protocol(q)


def test_completed_training_is_not_erased_when_evaluation_process_fails(tmp_path, monkeypatch):
    m = importlib.import_module('tools.validation.run_engineering_short_train')
    import tools.learning.sac_collection as sm
    monkeypatch.setattr(m, 'ROOT', tmp_path)
    monkeypatch.setattr(m, 'qualified_runtime', lambda path: {})
    monkeypatch.setattr(m, 'all_sources', lambda: {})
    monkeypatch.setattr(m, 'verification_protocol', lambda: {'checkpoint_selection': 'final'})
    monkeypatch.setattr(m, 'create_training_admission', lambda *a, **kw: None)
    monkeypatch.setattr(m, 'permit_for', lambda target: unit_permit())
    monkeypatch.setattr(sm, 'SACCollection', lambda **kw: object())
    monkeypatch.setattr(m, 'capture', lambda chain: {'history': []})
    def trained(chain, target):
        result = dict(training_completed=True, final_checkpoint={'sha256': 'final'})
        m.save(target / 'training.json', result)
        return result
    monkeypatch.setattr(m, 'run_training', trained)
    def logged(command, path):
        if path.name == 'evaluation_process.log': raise RuntimeError('evaluation subprocess failed')
    monkeypatch.setattr(m, 'run_logged', logged)
    target = tmp_path / 'run'
    with pytest.raises(RuntimeError): m.run(target)
    result = m.read(target / 'assessment.json')
    assert result['engineering_short_train_completed'] is True
    assert result['fixed_development_evaluation_completed'] is False
    assert result['delivery_verified'] is False


def test_invalid_evaluation_is_retained_and_blocks_next_reset(tmp_path, monkeypatch, runtime):
    from tests.learning.test_sac_collection import make
    import tools.learning.admitted_collection as cm
    from tools.learning.outcome import classify_outcome
    import gzip, json
    c = make(tmp_path, monkeypatch, runtime); m = eval_api()
    monkeypatch.setattr(cm, '_physical_audit', lambda session: classify_outcome(simulation_valid=False,
        contact_guard=False, motion_violation=False, full_success=False, physical_stopped=True))
    e = m.EvaluationCollector(admission=c.admission, output=tmp_path / 'invalid_eval',
        checkpoint_sha256='fixed', method='sac', updater=c.updater)
    e.start('failed', case=m.evaluation_cases()[0], seed=2026092202)
    while e.active: e.collect(m.FrozenPolicy(c.updater), 10)
    assert e._blocked and len(e.replay) == 0 and len(e.attempts) == 1
    raw = json.loads(gzip.decompress((e.output / 'failed/episode.json.gz').read_bytes()))
    assert raw['outcome']['simulation_valid'] is False and raw['training_admitted'] is False
    with pytest.raises(RuntimeError): e.start('resample', case=m.evaluation_cases()[1], seed=2026092202)
