"""No optimization: tampering, initial boundary and isolated state recovery."""
from copy import deepcopy
import importlib
import pytest
import torch
from tools.learning.bounded_contact import BoundedAdmission,BoundedCollection,bounded_config,validate_case
from tools.learning.sac_checkpoint import _same


class SyntheticPermit(BoundedAdmission):
    def __init__(self):
        self.expected_digest='SYNTHETIC-NOT-PHYSICAL-NOT-TRAINING'
        self._record=dict(capability='bounded_contact_cycle_v2',config=bounded_config(),synthetic_only=True)
    def verify(self,case=None):
        if case is not None: validate_case(case)
        return deepcopy(self._record)


def api(): return importlib.import_module('tools.learning.bounded_checkpoint')


def test_initial_boundary_roundtrip_contains_all_three_random_streams(tmp_path):
    permit=SyntheticPermit(); chain=BoundedCollection(admission=permit,output=tmp_path/'original')
    cp=api(); state=cp.capture(chain); pin=cp.save_checkpoint(chain,tmp_path/'checkpoint')
    restored=cp.load_checkpoint(tmp_path/'checkpoint',expected_digest=pin,admission=permit,output=tmp_path/'restored')
    assert _same(state,cp.capture(restored))
    assert not chain.updater.counts['critic']
    for a,b in zip(chain.updater.policy.parameters(),restored.updater.policy.parameters()):
        assert a.data_ptr()!=b.data_ptr() and torch.equal(a,b)


@pytest.mark.parametrize('field',('budget','sampler','history','boundary_rng','binding'))
def test_mutated_initial_checkpoint_is_rejected_before_destination_creation(tmp_path,field):
    permit=SyntheticPermit();chain=BoundedCollection(admission=permit,output=tmp_path/'original')
    cp=api();state=cp.capture(chain)
    if field=='budget':state['budget']['completed']=1
    elif field=='sampler':state['sampler_count']=1
    elif field=='history':state['history']=[dict(critic_batches=1)]
    elif field=='boundary_rng':state['rng']['boundary']['state']['state']+=1
    else:state['binding']['qualification_sha256']='different'
    with pytest.raises(ValueError):cp.validate_state(state,permit)


def test_payload_corruption_is_detected_before_loading(tmp_path):
    permit=SyntheticPermit();chain=BoundedCollection(admission=permit,output=tmp_path/'original')
    cp=api();pin=cp.save_checkpoint(chain,tmp_path/'checkpoint')
    with (tmp_path/'checkpoint/state.pt').open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError):cp.load_checkpoint(tmp_path/'checkpoint',expected_digest=pin,admission=permit,output=tmp_path/'restored')
    assert not (tmp_path/'restored').exists()
