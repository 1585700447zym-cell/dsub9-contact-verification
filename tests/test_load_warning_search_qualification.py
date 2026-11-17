"""Frozen 7pct dynamic qualification, with no simulator or optimizer."""
from copy import deepcopy
import importlib
import math

import pytest

from tools.learning.recovery_learning_contract import digest, experiment_config


def api():
    return importlib.import_module('tools.validation.load_warning_search_qualification')


def test_new_qualification_api_exists():
    assert importlib.util.find_spec('tools.validation.load_warning_search_qualification') is not None


@pytest.fixture(scope='module')
def proof():
    return api().build_search_authority_qualification()


def config(mode='gru', protocol='load_warning_7pct'):
    return experiment_config(mode, physical_protocol=protocol, seed=2026110801)


def test_five_audits_qualify_only_new_gru_development(proof):
    assert proof['qualified_episodes'] == 5
    assert proof['excluded_episode_ids'] == ['E01_ADMITTANCE']
    assert proof['actual_search_resumptions'] == 16
    assert proof['gru_search_resumptions'] == 8
    assert proof['replay_import_allowed'] is False
    assert len(proof['training_cases']) == 4
    assert len(proof['development_cases']) == 2
    assert proof['coverage']['force_gt5_dynamic'] is False
    assert proof['coverage']['force_gt6_dynamic'] is False
    assert proof['coverage']['rotation_gt2p5_dynamic'] is False
    api().verify_search_authority_qualification(proof, config=config())


@pytest.mark.parametrize('mode,protocol', [('mlp','load_warning_7pct'), ('gru','load_warning'), ('gru','recovery')])
def test_old_protocol_or_mlp_cannot_use_gru_qualification(proof, mode, protocol):
    with pytest.raises(ValueError):
        api().verify_search_authority_qualification(proof, config=config(mode, protocol))


@pytest.mark.parametrize('field,value', [
    ('qualified_episodes', 6), ('excluded_episode_ids', []), ('replay_import_allowed', True),
    ('actual_search_resumptions', 17), ('policy_modes', ['mlp','gru']),
])
def test_resigned_fabricated_proof_cannot_promote_itself(proof, field, value):
    changed = deepcopy(proof)
    changed[field] = value
    changed['proof_sha256'] = digest({k:v for k,v in changed.items() if k != 'proof_sha256'})
    with pytest.raises(ValueError):
        api().verify_search_authority_qualification(changed, config=config())


@pytest.mark.parametrize('name', [
    'tools/learning/load_warning_search_authority.py', 'tools/learning/global_residual_action.py',
    'tools/learning/reward.py', 'tools/learning/five_axis_observation.py',
    'tools/validation/load_warning_audit.py', 'tools/validation/yaw_pilot.py',
])
def test_changed_current_physics_cannot_reuse_dynamic_qualification(monkeypatch, name):
    module = api(); original = module._sha
    target = module.ROOT/name
    monkeypatch.setattr(module, '_sha', lambda path: '0'*64 if path == target else original(path))
    with pytest.raises(ValueError, match='source'):
        module.build_search_authority_qualification()


def test_changed_frozen_audit_or_receipt_is_rejected(monkeypatch):
    module = api(); original = module._sha
    for relative in ('run/E01_GRU/audit.json', 'run/E02_MLP/receipt.json'):
        target = module.DEFAULT_BATCH/relative
        monkeypatch.setattr(module, '_sha', lambda path: '0'*64 if path == target else original(path))
        with pytest.raises(ValueError, match='digest'):
            module.build_search_authority_qualification()


@pytest.mark.parametrize('y,yaw', [(y,yaw) for y in (-.0003,.0003) for yaw in (-1.5,1.5)])
def test_only_registered_four_training_pose_combinations(y, yaw):
    job = dict(episode_id='fresh_training', policy_mode='gru', split='train', deterministic=False,
               seed=101, exploration_seed=102, case=dict(name='TRAIN', x_offset_m=.0003,
               y_offset_m=y, roll_rad=math.radians(-1), pitch_rad=math.radians(1),
               yaw_rad=math.radians(yaw), start_origin_z_m=-.005, target_depth_m=.005))
    api().verify_search_authority_training_job(job)
    for change in (dict(split='dev_eval'), dict(deterministic=True), dict(policy_mode='mlp'),
                   dict(episode_id='E01_ADMITTANCE'),
                   dict(case=dict(job['case'], x_offset_m=.00028, y_offset_m=.00032))):
        with pytest.raises(ValueError):
            api().verify_search_authority_training_job(dict(job, **change))


def test_adjusted_qualification_api_exists():
    assert callable(getattr(api(), 'build_adjusted_search_authority_qualification', None))


@pytest.fixture(scope='module')
def adjusted():
    return api().build_adjusted_search_authority_qualification()


def test_adjustment_preserves_original_proof_and_binds_both_invalid_attempts(proof, adjusted):
    assert proof['proof_sha256'] == '1635e4cbfc441667a21701e4bc4baeee1e123f4016e12560e9252655df014d3e'
    assert adjusted['base_proof_sha256'] == proof['proof_sha256']
    assert adjusted['training_cases'] == proof['training_cases']
    assert adjusted['excluded_training_episode_ids'] == ['T04_GRU', 'T04_GRU_RETRY']
    assert adjusted['adjustment']['max_additional_attempts'] == 1
    assert len(adjusted['adjustment']['invalid_attempts']) == 2
    api().verify_search_authority_qualification(adjusted, config=config())


def test_adjustment_only_allows_exact_one_replacement_job(adjusted, monkeypatch):
    module = api()
    monkeypatch.setattr(module, 'build_adjusted_search_authority_qualification', lambda: deepcopy(adjusted))
    job = deepcopy(adjusted['adjustment']['job'])
    module.verify_search_authority_training_job(job, proof=adjusted)
    with pytest.raises(ValueError):
        module.verify_search_authority_training_job(job)
    for change in (dict(episode_id='another'), dict(episode_id='T04_GRU'),
                   dict(episode_id='T04_GRU_RETRY'), dict(seed=1), dict(exploration_seed=2026110944),
                   dict(deterministic=True), dict(split='dev_eval'),
                   dict(case=dict(job['case'], name='different')),
                   dict(case=dict(job['case'], y_offset_m=-.00021)),
                   dict(case=dict(job['case'], yaw_rad=math.radians(-1.5)))):
        with pytest.raises(ValueError):
            module.verify_search_authority_training_job(dict(job, **change), proof=adjusted)
    forged = deepcopy(adjusted)
    forged['adjustment']['job']['exploration_seed'] = 1
    forged['proof_sha256'] = digest({k:v for k,v in forged.items() if k!='proof_sha256'})
    with pytest.raises(ValueError):
        module.verify_search_authority_training_job(job, proof=forged)


@pytest.mark.parametrize('name', ['registration.json', 'continuation_registration.json',
    'run/T04_GRU/episode.json.gz', 'run/T04_GRU_RETRY/receipt.json'])
def test_adjustment_rejects_changed_frozen_invalid_evidence(monkeypatch, name):
    module=api(); original=module._sha; target=module.ADJUSTMENT_BATCH/name
    monkeypatch.setattr(module, '_sha', lambda path: '0'*64 if path==target else original(path))
    with pytest.raises(ValueError, match='digest'):
        module.build_adjusted_search_authority_qualification()
