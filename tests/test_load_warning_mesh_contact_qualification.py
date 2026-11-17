"""Read-only qualification tests; no simulator, policy or optimizer is created."""
from copy import deepcopy
import importlib
import math

import pytest

from tools.learning.recovery_learning_contract import digest, experiment_config


def api():
    return importlib.import_module('tools.validation.load_warning_mesh_contact_qualification')


@pytest.fixture(scope='module')
def proof():
    return api().build_mesh_contact_qualification()


def config(**changes):
    return experiment_config(changes.get('mode','gru'), physical_protocol=changes.get('protocol','load_warning_7pct_mesh_contact'),
                             seed=changes.get('seed',2026110801), focus_search_entry=changes.get('focus',True))


def test_mesh_contact_qualification_api_exists():
    assert importlib.util.find_spec('tools.validation.load_warning_mesh_contact_qualification') is not None


def test_real_frozen_repair_qualifies_only_bounded_fresh_gru(proof):
    assert proof['qualified_episode_ids']==['T04_contact_fixed']
    assert proof['dynamic_successes']==0
    assert proof['actual_search_resumptions']==4
    assert proof['replay_import_allowed'] is proof['development_replay_allowed'] is False
    assert len(proof['excluded_archive_sha256'])==4
    assert len(proof['training_cases'])==4 and len(proof['development_cases'])==2
    assert proof['training_initialization']=='fresh_actor_critics_targets_optimizers_replay'
    assert proof['coverage']['static_true_deep_contact'] is True
    assert all(v is False for k,v in proof['coverage'].items() if k!='static_true_deep_contact')
    assert proof['common']['dynamic_config']['invalid_penetration_m']==80e-6
    api().verify_mesh_contact_qualification(proof,config=config())


@pytest.mark.parametrize('change', [dict(mode='mlp',focus=False),dict(protocol='load_warning_7pct'),
                                   dict(protocol='load_warning',focus=False),dict(seed=42),dict(focus=False)])
def test_old_domain_or_policy_seed_cannot_reuse_repair_qualification(proof,change):
    with pytest.raises(ValueError):
        api().verify_mesh_contact_qualification(proof,config=config(**change))


@pytest.mark.parametrize('field,value', [('dynamic_successes',1),('replay_import_allowed',True),
    ('excluded_archive_sha256',[]),('policy_modes',['gru','mlp']),('actual_search_resumptions',5)])
def test_resigned_proof_cannot_promote_its_scope(proof,field,value,monkeypatch):
    module=api();monkeypatch.setattr(module,'build_mesh_contact_qualification',lambda:deepcopy(proof))
    changed=deepcopy(proof);changed[field]=value
    changed['proof_sha256']=digest({k:v for k,v in changed.items() if k!='proof_sha256'})
    with pytest.raises(ValueError,match='frozen evidence'):
        module.verify_mesh_contact_qualification(changed,config=config())


@pytest.mark.parametrize('relative', ['verification.json','frozen_after.json','runtime.json',
    'T04_contact_fixed/audit.json','T04_contact_fixed/episode.json.gz','static_recompute/input_manifest.json'])
def test_changed_frozen_evidence_is_rejected(relative,monkeypatch):
    module=api();original=module._sha;target=module.DEFAULT_BATCH/relative
    monkeypatch.setattr(module,'_sha',lambda path:'0'*64 if path==target else original(path))
    with pytest.raises(ValueError,match='digest'):
        module.build_mesh_contact_qualification()


@pytest.mark.parametrize('relative', ['tools/learning/load_warning_mesh_contact_trial.py',
    'tools/learning/global_residual_action.py','tools/learning/reward.py',
    'tools/validation/recovery_learning_audit.py','tools/model/layered_task.py',
    'assets/collision/d_guide_male_seg_057.stl',
    'tmp/mujoco_3_13_mesh_contact_runtime_20261110/mujoco/mujoco.dll'])
def test_changed_physics_asset_or_runtime_cannot_reuse_qualification(relative,monkeypatch):
    module=api();original=module._sha;target=module.ROOT/relative
    monkeypatch.setattr(module,'_sha',lambda path:'0'*64 if path==target else original(path))
    with pytest.raises(ValueError,match='digest'):
        module.build_mesh_contact_qualification()


@pytest.mark.parametrize('identity', ['T04_GRU','T04_GRU_RETRY','T04_GRU_YM200'])
def test_original_failure_archives_remain_bound(identity,monkeypatch):
    module=api();original=module._sha;target=module.PRIOR_BATCH/'run'/identity/'episode.json.gz'
    monkeypatch.setattr(module,'_sha',lambda path:'0'*64 if path==target else original(path))
    with pytest.raises(ValueError,match='digest'):
        module.build_mesh_contact_qualification()


@pytest.mark.parametrize('y,yaw',[(y,yaw) for y in (-.0003,.0003) for yaw in (-1.5,1.5)])
def test_only_four_fresh_training_poses_are_accepted(y,yaw):
    job=dict(episode_id='T04_GRU',policy_mode='gru',split='train',deterministic=False,
        seed=2026110824,exploration_seed=2026110844,case=dict(name='TRAIN',x_offset_m=.0003,
        y_offset_m=y,roll_rad=math.radians(-1),pitch_rad=math.radians(1),yaw_rad=math.radians(yaw),
        start_origin_z_m=-.005,target_depth_m=.005))
    api().verify_mesh_contact_training_job(job)
    changes=[dict(episode_id=x) for x in ('E01_GRU','E02_GRU','T04_contact_fixed','T04_GRU_RETRY','T04_GRU_YM200')]
    changes += [dict(split='diagnostic'),dict(deterministic=True),dict(policy_mode='mlp'),dict(seed=True),
                dict(case=dict(job['case'],y_offset_m=-.0002)),dict(case=dict(job['case'],x_offset_m=.00028))]
    for changed in changes:
        with pytest.raises(ValueError):
            api().verify_mesh_contact_training_job(dict(job,**changed))
