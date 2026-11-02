"""Breaks caught: wrong switch timing, mismatched attempt, false admission,
missing stop on watchdog, nonfinite archive loss, and observer physics drift."""
from copy import deepcopy
import importlib
import json
import math
import pytest


def module():
    return importlib.import_module('tools.validation.verify_scheduled_boundary')


def test_protocol_is_eight_fixed_engineering_attempts():
    p = module().build_protocol()
    assert len(p['attempts']) == 8
    assert [s['id'] for s in p['attempts']] == [
        'center_roll_neg', 'center_roll_pos', 'center_pitch_neg', 'center_pitch_pos',
        'corner_0', 'corner_1', 'corner_2', 'corner_3']
    assert [(s['case']['x_offset_m'], s['case']['y_offset_m']) for s in p['attempts']] == [
        (0,0),(0,0),(0,0),(0,0),(-50e-6,-50e-6),(-50e-6,50e-6),(50e-6,-50e-6),(50e-6,50e-6)]
    for s in p['attempts']:
        assert s['case']['roll_rad'] == s['case']['pitch_rad'] == 0
        assert s['case']['start_origin_z_m'] == -.004
        assert s['case']['target_depth_m'] == .004
        assert [x['start_cycle'] for x in s['schedule']] == [0,250,500,1000]
    assert p['attempts'][1]['schedule'] == [
        {'start_cycle':0,'action':[0,0,1,0]},
        {'start_cycle':250,'action':[0,1,1,0]},
        {'start_cycle':500,'action':[0,-1,1,0]},
        {'start_cycle':1000,'action':[0,0,1,0]}]
    assert p['attempts'][4]['schedule'] == [
        {'start_cycle':0,'action':[-1,-1,-1,-1]},
        {'start_cycle':250,'action':[1,1,-1,-1]},
        {'start_cycle':500,'action':[-1,-1,-1,-1]},
        {'start_cycle':1000,'action':[0,0,-1,-1]}]
    assert p['guard_config']['max_rotation_from_start_rad'] == math.radians(2.5)
    assert p['training_admitted'] is p['parameter_frozen'] is False


@pytest.mark.parametrize('cycle,want', [(0,[0,0,1,0]),(249,[0,0,1,0]),
    (250,[0,1,1,0]),(499,[0,1,1,0]),(500,[0,-1,1,0]),
    (999,[0,-1,1,0]),(1000,[0,0,1,0]),(12999,[0,0,1,0])])
def test_exact_cycle_switch(cycle, want):
    m=module(); s=m.build_protocol()['attempts'][1]
    assert m.action_for_cycle(s['schedule'], cycle) == want


@pytest.mark.parametrize('bad', [[], [{'start_cycle':1,'action':[0]*4}],
    [{'start_cycle':0,'action':[float('nan'),0,0,0]}],
    [{'start_cycle':0,'action':[2,0,0,0]}],
    [{'start_cycle':0,'action':[0]*4},{'start_cycle':0,'action':[1]*4}],
    [{'start_cycle':False,'action':[0]*4}]])
def test_bad_schedule_rejected_before_interaction(bad):
    with pytest.raises(ValueError):
        module().validate_schedule(bad)


def test_summary_never_promotes_guarded_failure_to_training():
    m=module(); p=m.build_protocol(); reports=[]
    for s in p['attempts']:
        reports.append(dict(spec=deepcopy(s), id=s['id'], error=None, completed=True,
            simulation_valid=True, physical_stopped=True, observation_valid=True,
            masking_valid=True, initialization_valid=True, schedule_valid=True,
            command_effect_cycles=1, contact_cycles=1, task_outcome='CONTACT_GUARD',
            rotation_guard_observations=[], training_admitted=False,
            model_scope_qualified=False, valid_for_learning=False))
    r=m.summarize(p,reports,source_unchanged=True)
    assert r['sample_checks_passed'] is True
    assert r['contact_rotation_boundary_cases'] == 0
    assert r['training_admitted'] is r['parameter_frozen'] is False
    reports[0]['spec']['schedule'][1]['action'][0]=.1
    assert m.summarize(p,reports,source_unchanged=True)['sample_checks_passed'] is False
    reports[0]['spec']=deepcopy(p['attempts'][0])
    reports[0]['simulation_valid']=False
    assert m.summarize(p,reports,source_unchanged=True)['sample_checks_passed'] is False
    assert m.summarize(p,reports[:-1],source_unchanged=True)['sample_checks_passed'] is False


def test_archive_nonfinite_is_explicit_and_no_overwrite(tmp_path):
    m=module(); path=tmp_path/'attempt.json'
    m.write_json_new(path, {'diagnostic':float('nan'),'training_admitted':False})
    saved=json.loads(path.read_text(encoding='utf-8'))
    assert saved['diagnostic'] != 0 and saved['diagnostic'] is not None
    assert 'nan' in str(saved['diagnostic']).lower()
    original=path.read_bytes()
    with pytest.raises(FileExistsError):
        m.write_json_new(path, {'replacement':True})
    assert path.read_bytes()==original


def test_native_watchdog_fails_but_retains_actual_stop():
    m=module(); s=m.build_protocol()['attempts'][1]
    r=m.run_attempt(s,watchdog_cycles=8)
    assert r['error']=='WATCHDOG_EXCEEDED'
    assert r['completed'] is False and r['physical_stopped'] is True
    assert r['simulation_valid'] is True and len(r['trace'])>8
    assert all(t['source']=='diagnostic_stop' for t in r['trace'][8:])
    assert r['training_admitted'] is r['valid_for_learning'] is False


def test_observer_does_not_change_native_cycles():
    m=module()
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.learning.residual_session import ResidualSession
    from tools.validation.run_contact_cases import ContactCase
    cfg=GuardCandidateConfig(**m.build_protocol()['guard_config'])
    a=ResidualSession(environment=LearningEnvironment(guard_config=cfg))
    b=ResidualSession(environment=m.BoundaryEnvironment(guard_config=cfg))
    case=ContactCase(**m.build_protocol()['attempts'][1]['case'])
    a.reset(case); b.reset(case)
    for _ in range(8):
        x=a.advance_cycle([0,0,1,0]); y=b.advance_cycle([0,0,1,0])
        assert x.trace_row==y.trace_row and x.action_log==y.action_log
    assert b.env.boundary_observations==[]


def test_substep_rotation_observer_retains_contact_at_trigger():
    m=module()
    from tools.learning.guarded_environment import GuardCandidateConfig
    from tools.validation.run_contact_cases import ContactCase
    env=m.BoundaryEnvironment(guard_config=GuardCandidateConfig(**m.build_protocol()['guard_config']))
    env.reset(ContactCase(**m.build_protocol()['attempts'][0]['case']))
    row=deepcopy(env.observe()); a=math.radians(2.51)
    row['quaternion_wxyz']=[math.cos(a/2),math.sin(a/2),0,0]
    row['contact_count']=1; row['penetration_m']=1e-6
    env._guard(row)
    assert len(env.boundary_observations)==1
    ob=env.boundary_observations[0]
    assert ob['rotation_trigger'] is True and ob['contact_at_trigger'] is True
    assert ob['rotation_deg']==pytest.approx(2.51)
    assert env.guard_facts['motion_reasons']==['ROTATION_LIMIT']


def test_failed_cycle_observation_archives_nan_and_final_adjudication(monkeypatch):
    m=module(); original=m.ResidualSession.advance_cycle; injected=False
    def bad_once(self,action):
        nonlocal injected
        result=original(self,action)
        if not injected:
            injected=True
            result.next_snapshot.policy_observation[0]=float('nan')
        return result
    monkeypatch.setattr(m.ResidualSession,'advance_cycle',bad_once)
    r=m.run_attempt(m.build_protocol()['attempts'][1])
    assert r['error'] is not None and not r['completed']
    assert r['simulation_valid'] and r['physical_stopped']
    assert r['diagnostic_failures'][0]['next_snapshot']['policy_observation'][0]=={'nonfinite':'nan'}
    assert r['adjudication_status']=='available'
    assert r['outcome']['physical_stopped'] is True
    assert r['task_outcome']==r['outcome']['task_outcome']
    assert r['valid_for_learning'] is False
    json.dumps(r,allow_nan=False)


def test_internal_interface_fault_archived_without_inventing_stop(monkeypatch):
    m=module()
    from tools.learning.observation import ObservationBuilder
    original=ObservationBuilder.capture; calls=0
    def fail_next_capture(self,*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==2: raise ValueError('injected capture failure')
        return original(self,*args,**kwargs)
    monkeypatch.setattr(ObservationBuilder,'capture',fail_next_capture)
    r=m.run_attempt(m.build_protocol()['attempts'][1])
    assert r['error'] is not None and not r['completed']
    assert r['simulation_valid'] is r['physical_stopped'] is False
    assert 'injected capture failure' in r['interface_fault']['error']
    assert r['adjudication_status']=='available'
    assert r['outcome']['simulation_valid'] is False
    assert r['task_outcome']==r['outcome']['task_outcome']
    assert r['valid_for_learning'] is False
