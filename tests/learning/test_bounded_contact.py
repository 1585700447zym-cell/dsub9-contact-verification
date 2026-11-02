"""Schedule, credit and start accounting without physical or optimizer work."""
import importlib
from copy import deepcopy
import pytest


def api(): return importlib.import_module('tools.learning.bounded_contact')


def receipt(i,steps=5000):
    return dict(episode_id=f'train_{i:02d}',status='published',valid_for_learning=True,
        simulation_valid=True,physical_stopped=True,guard_clear=True,committed=steps,discarded=0)


def test_twelve_attempts_guarantee_three_per_direction_and_refuse_thirteenth():
    s=api().BalancedSampler(); cases=[s.next_case() for _ in range(12)]
    xy=[(r['x_offset_m'],r['y_offset_m']) for r in cases]
    assert xy==[(.0001,0.),(-.0001,0.),(0.,.0001),(0.,-.0001)]*3
    with pytest.raises(RuntimeError): s.next_case()
    assert s.count==12


def test_credit_waits_for_all_four_warmups_and_caps_at_4500():
    b=api().EpisodeBudget()
    for i in range(12):
        assert b.record(receipt(i))
        assert not b.record(receipt(i))
        assert b.available==(0 if i<3 else 500)
        for _ in range(b.available): b.consume()
    assert b.completed==4500 and b.total==60000 and b.available==0
    with pytest.raises(RuntimeError): b.consume()
    with pytest.raises(ValueError): b.record(receipt(12))


def test_unconsumed_updates_block_next_credit_and_rejected_receipts_never_earn_it():
    b=api().EpisodeBudget()
    for i in range(4): b.record(receipt(i))
    with pytest.raises(ValueError): b.record(receipt(4))
    bad=receipt(4); bad['guard_clear']=False
    with pytest.raises(ValueError): b.record(bad)
    assert len(b._receipts)==4 and b.available==500


def test_failed_start_counts_and_cannot_be_restarted_or_reset(tmp_path):
    journal=api().RunLedger(tmp_path/'run.json')
    journal.start('initial', 'case_a')
    reloaded=api().RunLedger(tmp_path/'run.json')
    with pytest.raises(RuntimeError): reloaded.start('initial','case_a')
    reloaded.fail('fault')
    with pytest.raises(RuntimeError): reloaded.start('initial','case_b')
    assert reloaded.state['dynamic_starts']==1


def test_per_stage_caps_apply_before_start_and_completed_id_cannot_repeat(tmp_path):
    journal=api().RunLedger(tmp_path/'run.json')
    for i in range(4): journal.start('initial',str(i)); journal.finish(dict(ok=True))
    with pytest.raises(RuntimeError): journal.start('initial','extra')
    assert journal.state['dynamic_starts']==4


def test_case_scope_rejects_continuous_interpolation_and_nonzero_tilt():
    case=api().case_at('x',.000095,0.)
    api().validate_case(case)
    with pytest.raises(ValueError): api().validate_case(case,training=True)
    case['x_offset_m']=.000096
    with pytest.raises(ValueError): api().validate_case(case)
    case=api().case_at('x',.0001,0.);case['roll_rad']=.001
    with pytest.raises(ValueError): api().validate_case(case)


def test_initialization_failure_can_be_retained_without_a_session(tmp_path):
    from tools.learning.bounded_contact import BoundedCollector
    collector=object.__new__(BoundedCollector)
    collector._folder=tmp_path;collector.session=None;collector._pending=None
    collector._record=dict(episode_id='initialization_failed',status='rejected_before_reset')
    collector.retain_failure(ValueError('reset failed'))
    assert (tmp_path/'failure_before_session.json').exists()


def test_failed_update_attempt_remains_spent_and_locks_the_chain(tmp_path,monkeypatch):
    from tests.learning.test_bounded_checkpoint import SyntheticPermit
    from types import SimpleNamespace
    chain=api().BoundedCollection(admission=SyntheticPermit(),output=tmp_path/'episodes')
    for i in range(4):chain.budget.record(receipt(i))
    monkeypatch.setattr(chain.index,'sample',lambda *a,**k:SimpleNamespace(actor=None,critic=None,targets=None,mask=None))
    # Represents a later-stage optimizer failure. No real optimizer is invoked.
    monkeypatch.setattr(chain.updater,'update',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('after critic attempt')))
    with pytest.raises(RuntimeError,match='critic attempt'):chain.update(1)
    import json
    spent=json.loads((tmp_path/'episodes/update_budget.json').read_text(encoding='utf-8'))
    assert spent==dict(attempted=1,completed=0,failed_or_invalidated=1,remaining=4499)
    assert chain.failed
    with pytest.raises(RuntimeError):chain.update(1)
