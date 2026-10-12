"""Numerical and isolation tests; these do not execute optimizer updates."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest

def module():
    path=Path(__file__).with_name('probe.py')
    spec=importlib.util.spec_from_file_location('value_probe',path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m

def test_actual_dt_discounted_suffix_and_last_action():
    m=module()
    r=np.array([1.,2.,3.,10.]); d=np.array([.9,.8,.7,.6])
    mask,g,last=m.suffix_labels(r,d,[True,True,False,False],[False,False,False,True])
    assert last==1 and mask.tolist()==[False,True,True,True]
    assert g[3]==10 and g[2]==10 and g[1]==10

def test_inactive_gap_before_resumed_action_not_relabelled():
    m=module()
    mask,g,last=m.suffix_labels([1]*6,[.5]*6,[True,False,False,True,False,False],[False]*5+[True])
    assert last==3 and mask.tolist()==[False,False,False,True,True,True]
    assert g[3]==1.75

@pytest.mark.parametrize('active,terminated',[
    ([True,False],[False,False]),([True,False],[True,True]),([True,True],[False,True])])
def test_refuse_incomplete_or_no_inactive_suffix(active,terminated):
    with pytest.raises(ValueError): module().suffix_labels([1.,2.],[.9,.9],active,terminated)

def test_discount_must_be_finite_and_valid():
    with pytest.raises(ValueError): module().suffix_labels([1.,2.],[float('nan'),.9],[True,False],[False,True])

def test_control_targets_unchanged_and_only_suffix_replaced():
    m=module()
    import torch
    original=torch.tensor([[2.],[3.],[4.]])
    mask=torch.tensor([[False],[True],[True]])
    exact=torch.tensor([[20.],[30.],[40.]])
    assert torch.equal(m.select_targets(original,mask,exact,'one_step'),original)
    result=m.select_targets(original,mask,exact,'exact_inactive_suffix')
    assert torch.equal(result,torch.tensor([[2.],[30.],[40.]]))
    assert torch.equal(original,torch.tensor([[2.],[3.],[4.]]))
    with pytest.raises(ValueError): m.select_targets(original,mask,exact,'unknown')
