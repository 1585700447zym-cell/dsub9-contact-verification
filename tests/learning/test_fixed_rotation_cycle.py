"""Experiment boundary tests; all native and optimizer work is forbidden."""
from copy import deepcopy
import importlib
import pytest


def api():return importlib.import_module('tools.learning.fixed_rotation_cycle')


def test_config_has_only_version_and_rotation_difference():
    from tools.learning.bounded_contact import bounded_config
    old=bounded_config();new=api().fixed_config()
    assert new['action']['scale']==[.00015,.00015,.0005,.0005]
    assert new['version']!=old['version']
    new['version']=old['version'];new['action']['scale']=old['action']['scale']
    assert new==old


@pytest.mark.parametrize('field',['scale','seed','reward','batches'])
def test_unapproved_configuration_changes_rejected(field):
    c=api().fixed_config()
    if field=='scale':c['action']['scale'][2]=.005
    if field=='seed':c['sampling']['seed']+=1
    if field=='reward':c['learning']['reward']='different'
    if field=='batches':c['learning']['max_gradient_batches']+=1
    with pytest.raises(ValueError):api().validate_fixed_config(c)


def test_32_starts_and_59_lineage_cap_in_order(tmp_path):
    m=api();ledger=m.FixedLedger(tmp_path/'ledger.json')
    with pytest.raises(RuntimeError):ledger.start('training','train_00')
    for stage,cap in ledger.CAPS.items():
        for i in range(cap):ledger.start(stage,str(i));ledger.finish({})
    assert m.accounting(ledger.state)['cumulative_dynamic_starts']==59
    assert m.accounting(ledger.state)['new_dynamic_starts']==32
    with pytest.raises(RuntimeError):ledger.start('initial','extra')


def test_failed_start_consumes_budget_and_prevents_reopening(tmp_path):
    path=tmp_path/'ledger.json';m=api();ledger=m.FixedLedger(path)
    ledger.start('initial','0');ledger.fail('guard')
    with pytest.raises(RuntimeError):m.FixedLedger(path).start('initial','1')
    assert m.accounting(ledger.state)['cumulative_dynamic_starts']==28


def test_changed_parent_source_is_not_accepted_as_new_evidence(tmp_path,monkeypatch):
    m=api();monkeypatch.setattr(m,'ROOT',tmp_path)
    (tmp_path/'file.py').write_text('original')
    parent={'source_sha256':{'file.py':m.digest(tmp_path/'file.py')}}
    m.verify_parent_sources(parent,{})
    (tmp_path/'file.py').write_text('changed')
    with pytest.raises(ValueError):m.verify_parent_sources(parent,{})


def test_qualification_rejects_wrong_capability_and_profile():
    m=api();r=dict(capability='fixed_rotation_cycle_v1',synthetic_only=False,
        collection_admitted=True,update_admitted=True,restore_admitted=True,config=m.fixed_config(),parent_admission_sha256=m.PARENT_PIN)
    m.validate_record(r)
    for name,value in [('capability','old'),('synthetic_only',True),('update_admitted',False),('parent_admission_sha256','changed')]:
        wrong=deepcopy(r);wrong[name]=value
        with pytest.raises(ValueError):m.validate_record(wrong)


def test_one_shot_claim_does_not_allow_automatic_retry(tmp_path,monkeypatch):
    m=importlib.import_module('tools.validation.run_fixed_rotation_cycle')
    monkeypatch.setattr(m,'DELIVERY',tmp_path)
    m.claim('worker')
    with pytest.raises(FileExistsError):m.claim('worker')


def test_reused_supervisor_and_its_test_are_in_current_source_binding():
    sources=api().fixed_sources()
    for name in ('driver.py','test_driver.py'):
        key='deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/'+name
        assert key in sources


@pytest.mark.parametrize('changed',['driver.py','test_driver.py'])
def test_supervisor_tampering_is_rejected_against_trusted_old_binding(tmp_path,monkeypatch,changed):
    import json
    m=api();old=tmp_path/'old';folder=old/'retry_01';folder.mkdir(parents=True)
    for name in ('driver.py','test_driver.py'):(folder/name).write_text('original')
    binding=folder/'binding.json'
    binding.write_text(json.dumps(dict(files={f'old/retry_01/{n}':m.digest(folder/n) for n in ('driver.py','test_driver.py')})))
    monkeypatch.setattr(m,'ROOT',tmp_path);monkeypatch.setattr(m,'OLD',old)
    monkeypatch.setattr(m,'RETRY_BINDING_PIN',m.digest(binding))
    assert len(m.verify_supervisor_sources())==2
    (folder/changed).write_text('changed')
    with pytest.raises((ValueError,RuntimeError)):m.verify_supervisor_sources()
