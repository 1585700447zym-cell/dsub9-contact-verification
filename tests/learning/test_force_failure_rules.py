"""Protocol-only fixtures derived from a sealed archive; never promote old data."""
from copy import deepcopy
from functools import lru_cache
import gzip,importlib,importlib.util,json,math
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]
@lru_cache(maxsize=1)
def historical():
    p=ROOT/'deliverables/learning_chain/b2_fixed_rotation_cycle_20260928/run/training_episodes/train_04/episode.json.gz'
    return json.loads(gzip.decompress(p.read_bytes()))

def api():
    assert importlib.util.find_spec('tools.learning.episode_rules') is not None,'Versioned episode rules not implemented'
    return importlib.import_module('tools.learning.episode_rules')

def fixture():
    raw=deepcopy(historical())
    # Only this in-memory protocol fixture models a NEW episode after successful
    # physical audit. The original rejected archive is tested separately below.
    raw['fault']=None
    raw['outcome']['valid_for_learning']=True
    raw['qualification_sha256']='SYNTHETIC-PROTOCOL-ONLY'
    return raw

def test_force_failure_stays_failure_and_preserves_negative_terminal():
    raw=fixture();before=deepcopy(raw);rules=api().FORCE_ONLY
    assert rules.accepts(raw)
    assert rules.classify(raw)==dict(version='force_only_v1',kind='force_failure')
    assert raw==before and raw['guard_clear'] is False
    assert raw['transitions'][-1]['reward_terms']['terminal']==-10
    assert not api().STRICT.accepts(raw)

def test_historical_rejection_cannot_be_relabelled_by_new_rules():
    assert not api().FORCE_ONLY.accepts(historical())

@pytest.mark.parametrize('change',('nan','invalid','penetration','torque','motion','stopped','fault',
    'substeps','missing_event','action_after_guard','terminal','continuity','discount','case',
    'in_episode_update','false_guard_clear','reward_total','action_mapping','truncated','wrong_outcome'))
def test_force_failure_rejects_unqualified_counterexamples(change):
    raw=fixture();rows=raw['transitions'];facts=raw['guard_facts']
    if change=='nan':rows[1]['observation'][0]=float('nan')
    elif change=='invalid':facts['invalid_reasons']=['INVALID_SIMULATION']
    elif change=='penetration':facts['contact_reasons'].append('PENETRATION_LIMIT')
    elif change=='torque':facts['contact_reasons']=['TORQUE_LIMIT']
    elif change=='motion':facts['motion_reasons']=['ROTATION_LIMIT']
    elif change=='stopped':raw['stop_samples'][-1]['linear_m_s']=.01
    elif change=='fault':raw['fault']={'contact_publication_rejected':True}
    elif change=='substeps':facts['checked_substeps']-=1
    elif change=='missing_event':raw['events']=[e for e in raw['events'] if e['reason']!='FORCE_LIMIT']
    elif change=='action_after_guard':rows[-2]['action']=[1.,0.,0.,0.]
    elif change=='terminal':rows[-1]['reward_terms']['terminal']=10.
    elif change=='continuity':rows[8]['observation'][0]+=.001
    elif change=='discount':rows[8]['discount']=.99
    elif change=='case':raw['case']['roll_rad']=.01
    elif change=='in_episode_update':raw['optimizer_steps']+=1
    elif change=='false_guard_clear':raw['guard_clear']=True
    elif change=='reward_total':rows[8]['reward']+=1
    elif change=='action_mapping':rows[8]['action_log']['requested_residual'][3]+=.001
    elif change=='truncated':rows[-1]['terminated']=False;rows[-1]['truncated']=True
    else:raw['outcome']['task_outcome']='FULL_SUCCESS'
    assert not api().FORCE_ONLY.accepts(raw)

def test_negative_tail_reaches_last_active_row_without_rewriting_rows():
    from tools.learning.boundary_targets import exact_tail
    raw=fixture();original=deepcopy(raw)
    rules=api().FORCE_ONLY
    targets,mask,boundary=exact_tail(raw,rules=rules)
    assert boundary==5292 and mask[boundary:].all() and not mask[:boundary].any()
    assert math.isclose(targets[boundary],-8.369161465682458,abs_tol=1e-11)
    assert raw==original
    with pytest.raises(ValueError):exact_tail(raw)

def test_preparation_admission_refuses_execution_even_with_existing_parent_pin(tmp_path):
    assert importlib.util.find_spec('tools.learning.force_failure_preparation') is not None,'Preparation-only gate missing'
    m=importlib.import_module('tools.learning.force_failure_preparation')
    with pytest.raises(ValueError,match='preparation'):
        m.ForcePreparationAdmission(tmp_path/'fake.json',expected_digest='d6ac62ef7e0114ab5c042b666ed69b29ad11df9663f6c5a1ff92c5a728ec71e2')

def receipt(identity,force=True):
    return dict(episode_id=identity,status='published',committed=1,discarded=0,valid_for_learning=True,
        simulation_valid=True,physical_stopped=True,guard_clear=not force,
        task_outcome='CONTACT_GUARD' if force else 'TASK_FAILURE',
        learning_eligibility=dict(version='force_only_v1',kind='force_failure' if force else 'guard_clear'))

def test_frequency_stops_second_consecutive_and_third_total_and_no_update_credit():
    from tools.learning.bounded_contact import EpisodeBudget
    rules=api().FORCE_ONLY
    for sequence in ((True,True),(True,False,True,False,True)):
        budget=EpisodeBudget(rules=rules)
        for i,force in enumerate(sequence):
            while budget.available:budget.consume()
            budget.record(receipt(str(i),force))
        assert budget.stop_reason and budget.available==0
        with pytest.raises(RuntimeError):budget.consume()
        with pytest.raises((ValueError,RuntimeError)):budget.record(receipt('another',False))

def test_forged_guard_clear_receipt_cannot_earn_credit_and_duplicates_are_idempotent():
    from tools.learning.bounded_contact import EpisodeBudget
    rules=api().FORCE_ONLY;b=EpisodeBudget(rules=rules)
    r=receipt('one');assert b.record(r);assert b.record(r) is False
    assert len(b._receipts)==1 and not b.stop_reason
    bad=receipt('two');bad['guard_clear']=True
    with pytest.raises(ValueError):b.record(bad)


@pytest.mark.parametrize('change',('row_penetration','row_torque','row_motion','moved_force_event',
    'row_event_time','matched_wrong_dt','trace_gap','audit_clock','shifted_clock'))
def test_review_event_and_frozen_clock_counterexamples(change):
    from tools.learning.boundary_targets import exact_tail
    raw=fixture();rows=raw['transitions']
    if change.startswith('row_') and change!='row_event_time':
        reason={'row_penetration':'PENETRATION_LIMIT','row_torque':'TORQUE_LIMIT','row_motion':'ROTATION_LIMIT'}[change]
        rows[5292]['events'].append(dict(time_s=10.5842,reason=reason,phase='STOPPING'))
    elif change=='moved_force_event':
        # Flattened events still equal the top-level stream, but cycle is wrong.
        rows[5293]['events']=rows[5292]['events'];rows[5292]['events']=[]
    elif change=='row_event_time':rows[5292]['events'][0]['time_s']+=.0002
    elif change=='matched_wrong_dt':
        rows[-2]['dt']=.004;rows[-2]['discount']=math.exp(-.004/10.)
    elif change=='trace_gap':rows[100]['trace_row']['time_s']+=.0002
    elif change=='audit_clock':raw['audit_end_time_s']+=.00001
    else:
        # Same row spacing, but a shifted episode origin is not the frozen clock.
        for row in rows:row['trace_row']['time_s']+=.0002
    assert not api().FORCE_ONLY.accepts(raw)
    with pytest.raises(ValueError):exact_tail(raw,rules=api().FORCE_ONLY)
