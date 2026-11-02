"""Fixed action profile and checkpoint binding; no physics or optimization."""
from copy import deepcopy
from types import SimpleNamespace
import numpy as np
import pytest
from tools.learning.action import map_residual, compose_command

SMALL=(.00015,.00015,.0005,.0005)


def test_fixed_profile_changes_only_rotation_and_preserves_experience_action():
    a=[1.,-1.,.8,-.6]
    mapped=map_residual(a,enabled=True,action_scale=SMALL)
    np.testing.assert_array_equal(mapped,[.00015,-.00015,0.,.0004,-.0003,0.])
    _,log=compose_command(np.zeros(6),a,phase='SEARCH',enabled=True,
        previous_limited=np.zeros(6),dt=.002,action_scale=SMALL)
    assert log['raw_action']==log['experience_action']==a
    assert log['requested_residual']==log['applied_residual']==mapped.tolist()


@pytest.mark.parametrize('enabled',[True,False])
def test_zero_actions_have_identical_complete_logs_for_both_profiles(enabled):
    args=dict(phase='INSERT',enabled=enabled,previous_limited=np.ones(6)*.0001,dt=.002)
    old=compose_command(np.ones(6)*.0002,[0.]*4,**args)
    new=compose_command(np.ones(6)*.0002,[0.]*4,action_scale=SMALL,**args)
    np.testing.assert_array_equal(old[0],new[0]);assert old[1]==new[1]


def test_disabled_nonzero_request_is_recorded_but_never_executed():
    _,log=compose_command(np.zeros(6),[1.]*4,phase='SEARCH',enabled=False,
        previous_limited=np.zeros(6),dt=.002,action_scale=SMALL)
    assert log['experience_action']==[0.]*4 and log['applied_residual']==[0.]*6
    assert log['requested_residual']==[.00015,.00015,0.,.0005,.0005,0.]


@pytest.mark.parametrize('bad',[[1.,1.,1.,1.],[-1.,0.,0.,0.],[.0001]*3,[.0001,.0001,float('nan'),.001]])
def test_invalid_or_expanded_profile_is_rejected(bad):
    with pytest.raises(ValueError):map_residual([0.]*4,enabled=False,action_scale=bad)


def test_new_session_factory_passes_profile_and_session_owns_immutable_copy(monkeypatch):
    from tools.learning import admitted_collection as ac
    from tools.learning import residual_session as rs
    from tools.learning import guarded_environment as ge
    monkeypatch.setattr(ge,'LearningEnvironment',lambda **kw:object())
    monkeypatch.setattr(rs.CandidateEpisodeSession,'__init__',lambda self,**kw:None)
    config=dict(guard=dict(max_rotation_from_start_rad=.04363323129985824,
        initial_roll_pitch_limit_rad=.026179938779914945),action={'scale':list(SMALL)})
    session=ac._new_session(config)
    config['action']['scale'][2]=.005
    session.env=SimpleNamespace(command=np.zeros(6),config=SimpleNamespace(control_period=.002))
    snap=SimpleNamespace(base_command=np.zeros(6),controller_state={'phase':'SEARCH'},residual_enabled=True)
    session._command_for_action(snap,np.ones(4))
    assert session.last_action_log['requested_residual'][3:5]==[.0005,.0005]


def test_new_profile_checkpoint_roundtrip_and_old_binding_refusal(tmp_path):
    from tools.learning.bounded_contact import BoundedAdmission,BoundedCollection,BoundedUpdater,bounded_config
    from tools.learning import bounded_checkpoint as cp
    from tools.learning.sac_checkpoint import _same
    class SmallUpdater(BoundedUpdater):
        @staticmethod
        def config_validator(config):
            assert config['action']['scale']==list(SMALL)
    class Permit(BoundedAdmission):
        updater_type=SmallUpdater
        def __init__(self):
            self.expected_digest='SYNTHETIC-NO-PHYSICS-OR-UPDATE'
            config=bounded_config();config['action']['scale']=list(SMALL)
            self._record=dict(config=config,synthetic_only=True)
        def verify(self,case=None):return deepcopy(self._record)
    permit=Permit();chain=BoundedCollection(admission=permit,output=tmp_path/'original')
    state=cp.capture(chain);pin=cp.save_checkpoint(chain,tmp_path/'checkpoint')
    restored=cp.load_checkpoint(tmp_path/'checkpoint',expected_digest=pin,admission=permit,output=tmp_path/'restored')
    assert isinstance(chain.updater,SmallUpdater) and isinstance(restored.updater,SmallUpdater)
    assert _same(state,cp.capture(restored)) and not chain.updater.counts['critic']
    wrong=deepcopy(state);wrong['binding']['record']['config']['action']['scale'][2]=.005
    with pytest.raises(ValueError,match='qualification'):cp.validate_state(wrong,permit)
