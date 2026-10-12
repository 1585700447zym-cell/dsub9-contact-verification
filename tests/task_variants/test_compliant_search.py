import copy,math
from dataclasses import replace
import numpy as np
import pytest


def obs(t=0.,p=(0.,0.,0.),w=(0.,0.,0.,0.,0.,0.)):
    from tools.control.risk_search import PoseObservation
    return PoseObservation(t,p,w,0.)


def controller():
    from tools.control.compliant_search import CompliantSearchRecovery
    c=CompliantSearchRecovery();c._start_search(obs());return c


def test_accumulated_compliance_is_retained_in_search_target():
    from tools.control.load_search import LoadSearchRecovery
    old=LoadSearchRecovery();old._start_search(obs());old.admittance.offset[1]=80e-6
    new=controller();new.admittance.offset[1]=80e-6
    sample=obs(.1,(0.,40e-6,0.))
    assert old.command(sample,.002)[1]<0
    assert new.command(sample,.002)[1]>0
    assert new.search_composition['target_xy_m']==[0.,80e-6]


def test_no_feedback_and_no_integral_change_matches_old_search_formula():
    from tools.control.load_search import LoadSearchRecovery
    old=LoadSearchRecovery();old._start_search(obs());new=controller()
    for t in [.02,.04,.06,.08]:
        sample=obs(t,(1e-6,-2e-6,0.))
        assert np.array_equal(new.command(sample,.002),old.command(sample,.002))
        assert new.theta==old.theta


def test_admittance_integrates_once_and_target_uses_preintegration_offset():
    c=controller();c.admittance.offset[:2]=[10e-6,20e-6]
    previous=c.admittance.offset.copy();expected=copy.deepcopy(c.admittance)
    w=(.002,.005,0.,0.,0.,0.);expected.command(w,.002)
    c.command(obs(.1,w=w),.002)
    assert np.array_equal(c.admittance.offset,expected.offset)
    assert np.array_equal(c.admittance.velocity,expected.velocity)
    assert c.search_composition['correction_xy_m']==previous[:2].tolist()


def test_each_search_anchors_integral_to_current_state_including_recovery():
    c=controller();c.admittance.offset[:2]=[.0003,-.0002];c.phase='WAIT_RECOVERY'
    c.start_recovered_search(obs(.2,(20e-6,30e-6,0.)))
    assert c.search_admittance_origin.tolist()==[.0003,-.0002]
    assert c.search_origin.tolist()==[20e-6,30e-6,0.]
    command=c.command(obs(.202,(20e-6,30e-6,0.)),.002)
    assert c.search_composition['correction_xy_m']==[0.,0.]
    assert np.linalg.norm(command[:2])>0


@pytest.mark.parametrize('point,velocity,expected_point,expected_velocity',[
    ([20e-6,0.],[.0001,.0002],[20e-6,0.],[.0001,.0002]),
    ([240e-6,0.],[.0001,.0002],[120e-6,0.],[0.,.0001]),
    ([120e-6,0.],[.0001,.0002],[120e-6,0.],[0.,.0002]),
    ([120e-6,0.],[-.0001,.0002],[120e-6,0.],[-.0001,.0002]),
    ([0.,0.],[.0001,.0002],[0.,0.],[.0001,.0002])])
def test_bounded_target_and_consistent_feedforward(point,velocity,expected_point,expected_velocity):
    from tools.control.compliant_search import bounded_target
    q,v=bounded_target(point,velocity,120e-6)
    assert np.allclose(q,expected_point,rtol=0,atol=1e-14)
    assert np.allclose(v,expected_velocity,rtol=0,atol=1e-14)


@pytest.mark.parametrize('boundary,phase,reason',[
    ('excursion','FAILED','SEARCH_EXCURSION_LIMIT'),('advance','INSERT','SEARCH_ADVANCED'),
    ('timeout','WAIT_RECOVERY','SEARCH_EXHAUSTED'),('radius','WAIT_RECOVERY','SEARCH_EXHAUSTED')])
def test_original_boundaries_win_before_composition_and_load_relief(boundary,phase,reason):
    c=controller();c.load_since=.1;sample=obs(.12,w=(.022,0.,-.008,0.,0.,0.))
    if boundary=='excursion':sample=replace(sample,displacement_m=(201e-6,0.,0.))
    if boundary=='advance':sample=replace(sample,displacement_m=(0.,0.,100e-6))
    if boundary=='timeout':c.config=replace(c.config,search_time_s=.12)
    if boundary=='radius':c.theta=6*math.pi
    c.command(sample,.002)
    assert c.phase==phase and c.events[-1]['reason']==reason
    assert c.search_composition is None and not c.reference_release_requested


def test_load_relief_and_nonsearch_behavior_preserved():
    c=controller();c.load_since=.1;before=c.admittance.offset.copy()
    command=c.command(obs(.12,w=(.022,0.,-.008,0.,0.,0.)),.002)
    assert c.phase=='UNLOAD' and c.reference_release_requested
    assert c.search_composition is None and list(command[:2])==[0.,0.]
    assert np.array_equal(c.admittance.offset[:2],before[:2])
    from tools.control.load_search import LoadSearchRecovery
    from tools.control.compliant_search import CompliantSearchRecovery
    old=LoadSearchRecovery();new=CompliantSearchRecovery()
    assert np.array_equal(old.command(obs(),.002),new.command(obs(),.002))


def test_invalid_observation_does_not_integrate_or_change_target():
    c=controller();before=c.admittance.offset.copy()
    with pytest.raises(ValueError):c.command(obs(w=(float('nan'),0.,0.,0.,0.,0.)),.002)
    assert np.array_equal(c.admittance.offset,before) and c.search_composition is None


def test_trace_logs_only_active_composition_and_copies_arrays():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.learning.compliant_session import CompliantSearchSession
    s=object.__new__(CompliantSearchSession);s.controller=controller();s.recovery_state=None
    s.controller.command(obs(.1),.002)
    row=s._trace_row({'phase':'RUNNING'})
    assert row['search_composition']['time_s']==.1
    row['search_composition']['target_xy_m'][0]=99
    assert s.controller.search_composition['target_xy_m'][0]!=99
    assert s._trace_row({'phase':'STOPPING'})['search_composition'] is None
