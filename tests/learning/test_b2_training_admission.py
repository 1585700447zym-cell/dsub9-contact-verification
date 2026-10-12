from copy import deepcopy
import importlib
import pytest
from tools.learning.admission import short_training_config


def api(): return importlib.import_module('tools.learning.b2_training_admission')


def unit_permit():
    m = api(); p = object.__new__(m.TrainingAdmission)
    p.expected_digest = 'unit-test-admission'
    p._record = dict(config=short_training_config(), capability='engineering_short_train',
        runnable_trainer=True, collection_admitted=True, update_admitted=True, restore_admitted=True)
    p.verify = lambda case=None: deepcopy(p._record)
    return p


def test_probe_stays_at_16_and_only_training_class_gets_8250():
    from tools.learning.sac_collection import qualified_update_limit
    from tools.learning.b2_sac_admission import SACAdmission
    p = unit_permit()
    assert qualified_update_limit(p) == 8250
    old = object.__new__(SACAdmission)
    old.verify = lambda: {'config': short_training_config()}
    assert qualified_update_limit(old) == 16
    old.verify = p.verify
    with pytest.raises(ValueError): qualified_update_limit(old)
    p._record['runnable_trainer'] = False
    with pytest.raises(ValueError): qualified_update_limit(p)


def test_source_delta_only_allows_two_named_learning_changes():
    m = api()
    old = {p: 'old' for p in m.MODIFICATIONS}; old['physics.py'] = 'physics'
    current = dict(old, **{p: 'new' for p in m.MODIFICATIONS}, **{p: 'added' for p in m.ADDITIONS})
    delta = m.validate_delta(old, current)
    assert set(delta['modified']) == m.MODIFICATIONS and set(delta['added']) == m.ADDITIONS
    for name in ('physics.py', 'extra.py'):
        bad = current.copy(); bad[name] = 'unexpected'
        with pytest.raises(ValueError): m.validate_delta(old, bad)
    bad = current.copy(); del bad['physics.py']
    with pytest.raises(ValueError): m.validate_delta(old, bad)


def record():
    m = api(); r = unit_permit()._record
    r.update(version='b2_engineering_training_admission_v1', parent_sha256=m.PARENT_SHA256,
        runtime={'test': 1}, source_sha256={'a': 'b'}, execution_contract=m.execution_contract(),
        gates={k: True for k in m.GATES})
    return r


@pytest.mark.parametrize('change', [dict(runnable_trainer=False), dict(update_admitted=False),
    dict(restore_admitted=False), dict(parent_sha256='wrong'), dict(source_sha256={}),
    dict(runtime={}), dict(execution_contract={}), dict(gates={})])
def test_incomplete_training_permission_is_rejected(change):
    m = api(); r = record(); r.update(change)
    with pytest.raises(ValueError): m.validate_record(r, current_sources={'a': 'b'}, runtime={'test': 1})


def test_training_record_still_uses_frozen_config_and_fixed_evaluation():
    m = api(); r = record()
    m.validate_record(r, current_sources={'a': 'b'}, runtime={'test': 1})
    assert m.execution_contract()['evaluation_ids'] == [f'validation_small_xy_{i:02d}' for i in range(8)]
    r['config']['learning']['warmup_audited_transitions'] = 16
    with pytest.raises(ValueError): m.validate_record(r, current_sources={'a': 'b'}, runtime={'test': 1})


def test_historical_source_snapshots_reproduce_pinned_parent():
    from tools.validation.verify_residual_interface import qualified_runtime, all_sources
    from tools.learning.runtime import ROOT
    m = api(); parent = m._parent(qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe'))
    assert len(parent['source_sha256']) == 866
    m.validate_delta(parent['source_sha256'], all_sources())


def test_training_permission_requires_actual_complete_junit_evidence(tmp_path, monkeypatch):
    import xml.etree.ElementTree as ET
    m = api(); monkeypatch.setattr(m, 'ROOT', tmp_path)
    monkeypatch.setattr(m, 'verify_files', lambda *args: None)
    suite = ET.Element('testsuite')
    modules = ['test_b2_training_admission', 'test_engineering_training', 'test_sac_checkpoint',
               'test_sac_update', 'test_sac_collection', 'test_audited_replay']
    for i in range(400):
        ET.SubElement(suite, 'testcase', classname='tests.learning.' + modules[i % len(modules)], name=f'test_{i}')
    path = tmp_path / 'tests.xml'; ET.ElementTree(suite).write(path)
    from tools.learning.admission import digest, verify_test_report
    record = dict(test_report='tests.xml',
        tests=verify_test_report(path, required_modules=set(modules), minimum=400),
        evidence_sha256={'tests.xml': digest(path), m.SPLIT: m.SPLIT_SHA256,
            str(__import__('pathlib').PurePosixPath(m.PARENT).parent / 'manifest.json'): m.PARENT_MANIFEST_SHA256})
    m.verify_training_evidence(record)
    for key in ('test_report', 'tests'):
        bad = deepcopy(record); del bad[key]
        with pytest.raises(ValueError): m.verify_training_evidence(bad)
    bad = deepcopy(record); del bad['evidence_sha256']['tests.xml']
    with pytest.raises(ValueError): m.verify_training_evidence(bad)
    bad = deepcopy(record); bad['tests']['passed'] -= 1
    with pytest.raises(ValueError): m.verify_training_evidence(bad)
    bad = deepcopy(record); bad['tests']['sha256'] = bad['evidence_sha256']['tests.xml'] = 'wrong'
    with pytest.raises(ValueError): m.verify_training_evidence(bad)
    ET.SubElement(suite[0], 'failure'); ET.ElementTree(suite).write(path)
    record['evidence_sha256']['tests.xml'] = digest(path)
    with pytest.raises(ValueError): m.verify_training_evidence(record)
