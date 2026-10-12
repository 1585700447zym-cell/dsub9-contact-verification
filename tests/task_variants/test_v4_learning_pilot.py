"""Offline schedule, admission, non-retry and branch guard rules."""
from copy import deepcopy
import pytest
from tools.learning.v4_pilot_contract import attempt_specs

def api():
    from tools.validation import run_v4_learning_pilot
    return run_v4_learning_pilot

def points():return {'cases':[dict(id=str(i),x_um=i,y_um=0) for i in range(5)]}

def test_registered_matrix_uses_same_order_and_exact_budget():
    specs=attempt_specs(points());assert len(specs)==28 and len({s['id'] for s in specs})==28
    assert [s['mode'] for s in specs[:8]]==['F50','S50']*4
    assert sum(s['stage']=='final' for s in specs)==10 and sum(s['stage']=='restore' for s in specs)==2

def test_branch_guard_skips_only_its_remaining_registered_attempts():
    m=api();specs=attempt_specs(points());ledger=m.new_ledger(specs)
    ledger['branches']['F50']='CONTACT_GUARD'
    assert m.next_spec(ledger,specs)==specs[1]
    assert ledger['skipped']==[specs[0]['id']]
    ledger['episodes'].append(dict(id=specs[1]['id'],status='finished'))
    assert m.next_spec(ledger,specs)==specs[3]

def test_unfinished_or_duplicate_attempt_cannot_be_retried():
    m=api();specs=attempt_specs(points());ledger=m.new_ledger(specs)
    ledger['episodes']=[dict(id=specs[0]['id'],status='running')]
    with pytest.raises(RuntimeError):m.next_spec(ledger,specs)
    ledger['episodes']=[dict(id=specs[0]['id'],status='finished')]*2
    with pytest.raises(RuntimeError):m.next_spec(ledger,specs)

def test_common_error_and_stop_close_whole_matrix():
    m=api();specs=attempt_specs(points());ledger=m.new_ledger(specs)
    for status in ('error','controlled_stop'):
        ledger['status']=status;assert m.next_spec(ledger,specs) is None

def test_qualification_must_include_all_evidence_and_no_physics():
    m=api()
    good=dict(version='v4_learning_qualification_v2',training_admitted=True,purpose='bounded_physical_pilot',
        tests_passed=True,review_critical=0,review_important=0,complete_restore_passed=True,independent_restore_passed=True,
        qualification_dynamic_episodes=0,formal_gradient_batches=0,max_new_episodes=28,max_formal_batches=4000,
        authorization='继续推进，如果没发现问题可以直接进入学习链准入和小规模训练',
        control_preflight_sha256='ae124ffa9d47d2ed2719b64cbf1202241ded4287c5be842b61ea962b13c8e8e5',
        prior_cumulative=145,cumulative_limit=173)
    m.check_qualification(good)
    for key,value in [('training_admitted',False),('complete_restore_passed',False),('review_important',1),
        ('qualification_dynamic_episodes',1),('max_new_episodes',29),('formal_gradient_batches',1)]:
        bad=deepcopy(good);bad[key]=value
        with pytest.raises(ValueError):m.check_qualification(bad)

def test_learning_runtime_mismatch_fails_closed(monkeypatch):
    m=api();monkeypatch.setattr(m,'learning_runtime_proof',lambda:{'torch':'changed'},raising=False)
    with pytest.raises(ValueError):m.verify_learning_runtime({'torch':'qualified'})

def test_old_test_or_review_source_cannot_qualify_changed_code():
    m=api();old={'tools/learning/v4_sac.py':'a'*64};new={'tools/learning/v4_sac.py':'b'*64}
    v=dict(passed=True,source_sha256=old);r=dict(reviewed_source_sha256=old,validated_source_sha256=old,fix_delta={})
    m.verify_qualification_sources(dict(input_sha256=old),v,r)
    with pytest.raises(ValueError):m.verify_qualification_sources(dict(input_sha256=new),v,r)
    v['source_sha256']=new
    with pytest.raises(ValueError):m.verify_qualification_sources(dict(input_sha256=new),v,r)
    r.update(validated_source_sha256=new,fix_delta={'tools/learning/v4_sac.py':dict(before='a'*64,after='b'*64)})
    m.verify_qualification_sources(dict(input_sha256=new),v,r)

def test_new_round_has_current_filter_and_fresh_cumulative_budget():
    from tools.learning.v4_pilot_contract import DELIVERY,learning_config
    from tools.learning.v4_continuation import VERSION
    assert DELIVERY.name=='v4_learning_requalification_20261006'
    assert learning_config('F50')['reference_filter']==VERSION
    ledger=api().new_ledger(attempt_specs(points()))
    assert (ledger['prior_cumulative'],ledger['cumulative_limit'])==(145,173)

def test_old_qualification_cannot_be_reopened():
    from tools.learning.v4_pilot_contract import ROOT,read
    q=read(ROOT/'deliverables/paper_comparison/v4_learning_pilot_20261006/qualification.json')
    with pytest.raises(ValueError):api().check_qualification(q)

def test_new_common_keeps_physics_and_records_registration_source_delta():
    from tools.learning.v4_pilot_contract import ROOT,read,sha
    from tools.evaluation.paper_comparison import comparison_key
    old=read(ROOT/'deliverables/paper_comparison/search_boundary_fix_20261006/configuration.json')['common']
    common,delta=api().registered_common()
    assert {k:v for k,v in common.items() if k!='frozen_common_source_sha256'}=={k:v for k,v in old.items() if k!='frozen_common_source_sha256'}
    assert set(delta)=={'tools/learning/v4_pilot_contract.py','tools/validation/run_v4_learning_pilot.py'}
    assert all(v['after']==sha(ROOT/k) for k,v in delta.items())
    assert {p.relative_to(ROOT).as_posix() for p in (ROOT/'tools').rglob('*.py')}<=set(common['frozen_common_source_sha256'])
    assert comparison_key(common)!=comparison_key(old)

def test_unexpected_control_source_change_blocks_new_registration(monkeypatch):
    m=api();real=m.sha
    def changed(path):
        if path==m.ROOT/'tools/control/reference_search.py':return 'f'*64
        return real(path)
    monkeypatch.setattr(m,'sha',changed)
    with pytest.raises(ValueError,match='Unexpected change'):m.registered_common()
