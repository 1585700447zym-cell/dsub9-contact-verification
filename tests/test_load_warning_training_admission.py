"""Admission uses frozen evidence, never a new physical episode."""
from copy import deepcopy
import hashlib
from importlib import import_module, util
import json
from pathlib import Path

import pytest

from tools.learning.recovery_learning_contract import digest, experiment_config, verify_training_registration


def api():
    name = 'tools.validation.load_warning_training_admission'
    assert util.find_spec(name) is not None, 'Versioned load-warning admission is missing'
    return import_module(name)


@pytest.fixture(scope='module')
def proof():
    module = api()
    return module.build_load_warning_qualification(module.DEFAULT_BATCH)


def test_real_frozen_four_episode_evidence_builds_both_mode_qualification(proof):
    module = api()
    assert proof['verified'] and proof['qualified_episodes'] == 4
    assert proof['actual_search_resumptions'] == 6
    assert proof['coverage']['force_gt5_continued'] is True
    assert proof['coverage']['rotation_gt2p5_continued'] is True
    assert proof['coverage']['force_gt6_dynamic'] is False
    assert proof['replay_publications'] == 0 and proof['data_role'] == 'development_qualification_only'
    assert proof['coverage']['legacy_forced_force_recovery_100ms'] is False
    for mode in ('mlp', 'gru'):
        module.verify_load_warning_qualification(proof, config=experiment_config(mode, seed=123, physical_protocol='load_warning'))


@pytest.mark.parametrize('field,value', [
    ('version', 'legacy'), ('verified', False), ('qualified_episodes', 3),
    ('actual_search_resumptions', 0), ('replay_publications', 1),
    ('physical_protocol_sha256', '0'*64), ('data_role', 'test'),
])
def test_changed_qualification_cannot_authorize_training(proof, field, value):
    changed = deepcopy(proof)
    changed[field] = value
    with pytest.raises(ValueError):
        api().verify_load_warning_qualification(changed, config=experiment_config(physical_protocol='load_warning'))


def test_self_resigned_fabricated_coverage_still_rejected(proof):
    changed = deepcopy(proof)
    changed['coverage']['force_gt6_dynamic'] = True
    changed['proof_sha256'] = digest({k:v for k,v in changed.items() if k != 'proof_sha256'})
    with pytest.raises(ValueError):
        api().verify_load_warning_qualification(changed, config=experiment_config(physical_protocol='load_warning'))


def test_legacy_or_changed_physical_config_rejected(proof):
    with pytest.raises(ValueError):
        api().verify_load_warning_qualification(proof, config=experiment_config())
    changed = experiment_config(physical_protocol='load_warning')
    changed['physical_protocol']['task_deadline_s'] = 31.
    with pytest.raises(ValueError):
        api().verify_load_warning_qualification(proof, config=changed)


def test_changed_trusted_batch_cannot_build_a_qualification(tmp_path):
    module = api()
    for filename in ('registration.json', 'verification.json'):
        (tmp_path/filename).write_bytes((module.DEFAULT_BATCH/filename).read_bytes())
    reg = json.loads((tmp_path/'registration.json').read_bytes())
    reg['replay_publications'] = 1
    (tmp_path/'registration.json').write_text(json.dumps(reg), encoding='utf-8')
    with pytest.raises(ValueError, match='digest'):
        module.build_load_warning_qualification(tmp_path)


@pytest.mark.parametrize('source', [
    'tools/learning/load_warning_trial.py', 'tools/learning/reward.py',
    'tools/learning/axis_session.py', 'tools/learning/load_session.py',
    'tools/learning/functional_session.py', 'tools/learning/five_axis_contract.py',
    'tools/validation/yaw_pilot.py', 'tools/validation/run_b1_baseline.py',
    'tools/validation/run_b2_search.py', 'tools/validation/run_contact_cases.py',
])
def test_changed_current_physics_cannot_reuse_qualification(monkeypatch, source):
    module = api()
    original = module._sha
    target = module.ROOT/source
    monkeypatch.setattr(module, '_sha', lambda path: '0'*64 if Path(path) == target else original(path))
    with pytest.raises(ValueError, match='physical source'):
        module.build_load_warning_qualification(module.DEFAULT_BATCH)


@pytest.mark.parametrize('fault', ['common', 'binding', 'qualification_episode'])
def test_new_registration_cannot_waive_physics_or_import_g1_episode(tmp_path, proof, fault):
    path = tmp_path/'qualification.json'
    path.write_text(json.dumps(proof), encoding='utf-8')
    config = experiment_config('gru', physical_protocol='load_warning')
    job = dict(episode_id='training-1', split='train', deterministic=False)
    reg = dict(stage='G2', common=deepcopy(proof['common']),
        experiment=dict(config_sha256=digest(config),policy_mode='gru',physical_protocol=config['physical_protocol']),
        g1_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    if fault == 'common':
        reg['common']['dynamic_config']['recovery_distance_m'] = .00025
    elif fault == 'binding':
        reg['experiment']['config_sha256'] = '0'*64
    else:
        job['episode_id'] = proof['qualified_episode_ids'][0]
    reg['training_jobs'] = [digest(job)]
    with pytest.raises(ValueError, match='physical domain'):
        verify_training_registration(reg,job,config=config,qualification_path=path,expected_digest=digest(reg))


def test_new_registration_keeps_external_digest_job_and_report_binding(tmp_path, proof):
    path = tmp_path/'qualification.json'
    path.write_text(json.dumps(proof), encoding='utf-8')
    config = experiment_config('gru', physical_protocol='load_warning')
    job = dict(episode_id='training-1', split='train', deterministic=False)
    reg = dict(stage='G2', training_jobs=[digest(job)], g1_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        common=proof['common'], experiment=dict(config_sha256=digest(config), policy_mode='gru',
                                              physical_protocol=config['physical_protocol']))
    args = dict(config=config, qualification_path=path, expected_digest=digest(reg))
    assert verify_training_registration(reg, job, **args) is None
    for other_reg, other_job in ((dict(reg,stage='G1'),job),(reg,dict(job,split='test')),
                                  (reg,dict(job,episode_id='other'))):
        with pytest.raises(ValueError):
            verify_training_registration(other_reg, other_job, **args)
    path.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='G1'):
        verify_training_registration(reg, job, **args)
