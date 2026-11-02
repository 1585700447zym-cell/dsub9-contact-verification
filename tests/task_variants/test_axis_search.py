import copy,math
from dataclasses import replace
import numpy as np
import pytest


def obs(t=0.,p=(0.,0.,0.),w=(0.,0.,0.,0.,0.,0.)):
    from tools.control.risk_search import PoseObservation
    return PoseObservation(t,p,w,0.)


def controller():
    from tools.control.axis_search import AxisSearchRecovery
    c=AxisSearchRecovery();c._start_search(obs());return c


def test_xy_force_cannot_cancel_spiral_or_accumulate_hidden_offsets():
    a=controller();a.theta=8.;a.admittance.offset[:2]=[.0002,-.0003]
    a.admittance.velocity[:2]=[.0004,-.0004];b=copy.deepcopy(a)
    state=(a.admittance.offset.copy(),a.admittance.velocity.copy())
    ua=a.command(obs(.2,w=(.006,-.006,-.008,0.,0.,0.)),.002)
    ub=b.command(obs(.2,w=(0.,0.,-.008,0.,0.,0.)),.002)
    assert np.array_equal(ua,ub)
    assert np.array_equal(a.admittance.offset[:2],state[0][:2])
    assert np.array_equal(a.admittance.velocity[:2],state[1][:2])
    assert np.linalg.norm(a.search_composition['target_xy_m'])==pytest.approx(8.*40e-6/(2*math.pi))


def test_angles_integrate_once_and_axial_force_control_unchanged():
    c=controller();expected=copy.deepcopy(c.admittance)
    w=(.003,.002,-.006,.0001,-.0002,0.)
    old=expected.command(w,.002);u=c.command(obs(.1,w=w),.002)
    assert np.array_equal(c.admittance.offset[2:],expected.offset[2:])
    assert np.array_equal(c.admittance.velocity[2:],expected.velocity[2:])
    assert np.array_equal(u[3:],old[3:])
    assert u[2]==pytest.approx(.0001)


def test_recovery_return_is_not_new_progress_and_baseline_stays_frozen():
    c=controller();c.command(obs(.1,(0.,0.,250e-6)),.002)
    assert c.phase=='INSERT' and c.episode_peak_z_m==250e-6
    c.phase='WAIT_RECOVERY';c.start_recovered_search(obs(.2,(0.,0.,-5e-6)))
    assert c.search_progress_origin_z_m==250e-6
    c.command(obs(.3,(0.,0.,96e-6)),.002)
    assert c.phase=='SEARCH'
    c.command(obs(.4,(0.,0.,349e-6)),.002)
    assert c.phase=='SEARCH' and c.search_progress_origin_z_m==250e-6
    c.command(obs(.5,(0.,0.,351e-6)),.002)
    assert c.phase=='INSERT' and c.events[-1]['reason']=='SEARCH_ADVANCED'


def test_initial_unload_uses_previous_peak_not_retracted_start():
    from tools.control.axis_search import AxisSearchRecovery
    c=AxisSearchRecovery();c.command(obs(.1,(0.,0.,260e-6)),.002)
    c.phase='UNLOAD';c.phase_start=.1
    c.command(obs(.2,(0.,0.,240e-6)),.002)
    assert c.search_progress_origin_z_m==260e-6
    c.command(obs(.3,(0.,0.,341e-6)),.002)
    assert c.phase=='SEARCH'


def test_return_progress_cannot_bypass_sustained_load_relief():
    c=controller();c.episode_peak_z_m=250e-6;c.phase='WAIT_RECOVERY'
    c.start_recovered_search(obs(.1,(0.,0.,-5e-6)));c.load_since=.1
    c.command(obs(.12,(0.,0.,96e-6),(.022,0.,-.008,0.,0.,0.)),.002)
    assert c.phase=='FAILED' and c.reason=='SEARCH_BUDGET_EXHAUSTED'


@pytest.mark.parametrize('boundary,phase,reason',[
    ('excursion','FAILED','SEARCH_EXCURSION_LIMIT'),('advance','INSERT','SEARCH_ADVANCED'),
    ('timeout','WAIT_RECOVERY','SEARCH_EXHAUSTED'),('radius','WAIT_RECOVERY','SEARCH_EXHAUSTED')])
def test_gates_still_precede_search_and_load(boundary,phase,reason):
    c=controller();c.load_since=.1;sample=obs(.12,w=(.022,0.,-.008,0.,0.,0.))
    if boundary=='excursion':sample=replace(sample,displacement_m=(201e-6,0.,0.))
    if boundary=='advance':sample=replace(sample,displacement_m=(0.,0.,101e-6))
    if boundary=='timeout':c.config=replace(c.config,search_time_s=.12)
    if boundary=='radius':c.theta=6*math.pi
    c.command(sample,.002)
    assert c.phase==phase and c.events[-1]['reason']==reason
    assert c.search_composition is None and not c.reference_release_requested


@pytest.mark.parametrize('failure',['invalid','pending_release'])
def test_rejected_command_cannot_update_highwater_or_search_state(failure):
    c=controller();c.episode_peak_z_m=10e-6;sample=obs(.2,(0.,0.,.001))
    error=RuntimeError
    if failure=='invalid':sample=replace(sample,wrench_M=(float('nan'),0.,0.,0.,0.,0.));error=ValueError
    else:c.reference_release_requested=True
    before=copy.deepcopy(c.__dict__)
    with pytest.raises(error):c.command(sample,.002)
    assert c.episode_peak_z_m==10e-6 and c.search_progress_origin_z_m==before['search_progress_origin_z_m']
    assert c.phase=='SEARCH' and c.search_composition is None


def test_insert_and_unload_match_previous_controller():
    from tools.control.axis_search import AxisSearchRecovery
    from tools.control.load_search import LoadSearchRecovery
    a=AxisSearchRecovery();b=LoadSearchRecovery()
    for phase,w in [('INSERT',(.002,.004,-.001,.0001,0.,0.)),('UNLOAD',(.002,.004,-.02,.0001,0.,0.))]:
        a.phase=b.phase=phase
        assert np.array_equal(a.command(obs(.1,w=w),.002),b.command(obs(.1,w=w),.002))
        assert np.array_equal(a.admittance.offset,b.admittance.offset)


def test_trace_copies_active_fields_and_stops_composition():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.learning.axis_session import AxisSearchSession
    s=object.__new__(AxisSearchSession);s.controller=controller();s.recovery_state=None
    s.controller.command(obs(.1),.002)
    row=s._trace_row({'phase':'RUNNING'})
    assert row['search_progress_origin_z_m']==0. and row['episode_peak_z_m']==0.
    row['search_composition']['target_xy_m'][0]=99
    assert s.controller.search_composition['target_xy_m'][0]!=99
    assert s._trace_row({'phase':'STOPPING'})['search_composition'] is None


@pytest.mark.parametrize('bad',['wrench','position','time','angle','type'])
def test_recovery_rejects_invalid_observation_before_consuming_retry(bad):
    c=controller();c.phase='WAIT_RECOVERY';sample=obs(.2,(0.,0.,-.0002))
    if bad=='wrench':sample=replace(sample,wrench_M=(float('nan'),0.,0.,0.,0.,0.))
    if bad=='position':sample=replace(sample,displacement_m=(0.,0.,float('nan')))
    if bad=='time':sample=replace(sample,time_s=float('inf'))
    if bad=='angle':sample=replace(sample,relative_rotation_rad=-.1)
    if bad=='type':sample=object()
    before=copy.deepcopy(c.__dict__)
    with pytest.raises(ValueError):c.start_recovered_search(sample)
    assert c.phase=='WAIT_RECOVERY' and c.search_count==1
    assert c.events==before['events'] and c.search_progress_origin_z_m==before['search_progress_origin_z_m']
    assert c.episode_peak_z_m==before['episode_peak_z_m']
