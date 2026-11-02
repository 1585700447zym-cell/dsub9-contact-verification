"""Protocol/accounting checks; fixtures cannot certify physical-domain coverage."""
from copy import deepcopy
import json

import numpy as np
import pytest


def test_protocol_covers_registered_initial_domain_without_test_set():
    from tools.validation.verify_engineering_domain import build_protocol
    protocol = build_protocol()
    rows = protocol['attempts']
    initial = [r for r in rows if r['kind'] == 'initialization']
    dynamic = [r for r in rows if r['kind'] == 'dynamic']
    assert len(initial) == 9 and len(dynamic) == 17 and len({r['id'] for r in rows}) == 26
    coordinates = {(r['case']['x_offset_m'], r['case']['y_offset_m']) for r in initial}
    assert {(0., 0.), (-50e-6, -50e-6), (-50e-6, 50e-6),
            (50e-6, -50e-6), (50e-6, 50e-6)} <= coordinates
    for row in rows:
        case = row['case']
        assert abs(case['x_offset_m']) <= 50e-6 and abs(case['y_offset_m']) <= 50e-6
        assert case['roll_rad'] == case['pitch_rad'] == 0
        assert case['start_origin_z_m'] == -.004 and case['target_depth_m'] == .004
        assert len(row['action']) == 4 and max(map(abs, row['action'])) <= 1
    axes = [r['action'] for r in dynamic if r['family'] == 'single_axis']
    assert sorted(axes) == sorted([[sign if i == axis else 0. for i in range(4)]
                                    for axis in range(4) for sign in (-1., 1.)])
    assert build_protocol() == protocol
    assert protocol['training_admitted'] is False and protocol['domain_qualified'] is False
    assert protocol['data_use'] == 'development_only'


def fixture_reports(protocol):
    return [dict(id=r['id'], kind=r['kind'], case=deepcopy(r['case']), action=list(r['action']),
                 error=None, initialization_valid=True,
                 simulation_valid=True, physical_stopped=r['kind'] == 'dynamic',
                 observation_valid=True, masking_valid=True, completed=True,
                 command_effect_cycles=1 if any(r['action']) else 0,
                 task_outcome='CONTACT_GUARD', training_admitted=False,
                 model_scope_qualified=False, valid_for_learning=False)
            for r in protocol['attempts']]


def test_valid_failures_pass_only_sample_check_not_training_or_domain_admission():
    from tools.validation.verify_engineering_domain import build_protocol, summarize
    protocol = build_protocol()
    result = summarize(protocol, fixture_reports(protocol), source_unchanged=True)
    assert result['sample_checks_passed']
    assert result['attempts_planned'] == result['attempts_recorded'] == 26
    assert result['dynamic_valid_stopped'] == 17
    assert result['dynamic_task_successes'] == 0
    assert result['training_admitted'] is result['domain_qualified'] is False


@pytest.mark.parametrize('problem', ['missing', 'duplicate', 'unexpected', 'wrong_kind',
    'initialization', 'late_invalid', 'not_stopped', 'masked_action', 'no_effect',
    'watchdog', 'malformed_flag', 'source_change', 'promoted'])
def test_any_missing_invalid_or_unreviewed_attempt_keeps_suite_failed(problem):
    from tools.validation.verify_engineering_domain import build_protocol, summarize
    p = build_protocol()
    rows = fixture_reports(p)
    d = next(r for r in rows if r['kind'] == 'dynamic' and r['command_effect_cycles'])
    if problem == 'missing': rows.pop()
    if problem == 'duplicate': rows[-1] = deepcopy(rows[0])
    if problem == 'unexpected': rows[-1]['id'] = 'not-registered'
    if problem == 'wrong_kind': d['kind'] = 'initialization'
    if problem == 'initialization': rows[0]['initialization_valid'] = False
    if problem == 'late_invalid': d['simulation_valid'] = False
    if problem == 'not_stopped': d['physical_stopped'] = False
    if problem == 'masked_action': d['masking_valid'] = False
    if problem == 'no_effect': d['command_effect_cycles'] = 0
    if problem == 'watchdog': d['error'] = 'watchdog'
    if problem == 'malformed_flag': d['simulation_valid'] = 'false'
    if problem == 'promoted': d['training_admitted'] = True
    result = summarize(p, rows, source_unchanged=problem != 'source_change')
    assert not result['sample_checks_passed'] and not result['training_admitted']


@pytest.mark.parametrize('tag', ['../escape', '.', '', 'a/b', 'a\\b', 'a:', 'name.'])
def test_output_never_escapes_or_overwrites(tmp_path, tag):
    from tools.validation.verify_engineering_domain import fresh_output
    with pytest.raises(ValueError): fresh_output(tmp_path, tag)
    assert not list(tmp_path.iterdir())


def test_existing_attempt_is_not_overwritten(tmp_path):
    from tools.validation.verify_engineering_domain import fresh_output
    target = fresh_output(tmp_path, 'new-attempt')
    marker = target / 'marker'
    marker.write_text('keep')
    with pytest.raises(FileExistsError): fresh_output(tmp_path, 'new-attempt')
    assert marker.read_text() == 'keep'


def test_native_watchdog_is_failed_probe_but_attempts_real_stop(runtime):
    from tools.validation.verify_engineering_domain import build_protocol, run_attempt
    spec = next(r for r in build_protocol()['attempts'] if r['family'] == 'single_axis')
    report = run_attempt(spec, watchdog_cycles=2)
    assert report['error'] == 'WATCHDOG_EXCEEDED'
    assert report['initialization_valid'] and report['simulation_valid']
    assert report['physical_stopped'] and not report['completed']
    assert report['command_effect_cycles'] > 0 and report['masking_valid']
    assert report['physical_steps'] > 20
    assert report['training_admitted'] is report['valid_for_learning'] is False
    assert report['events'] and report['physical_stop_samples'] and len(report['trace']) > 2
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('field', ['case', 'action', 'missing_case', 'missing_action'])
def test_same_id_with_mismatched_or_missing_execution_inputs_cannot_pass(field):
    from tools.validation.verify_engineering_domain import build_protocol, summarize
    p = build_protocol()
    rows = fixture_reports(p)
    row = next(r for r in rows if r['command_effect_cycles'])
    if field == 'case': row['case']['x_offset_m'] = 40e-6
    if field == 'action': row['action'] = [0.] * 4
    if field.startswith('missing_'): del row[field.removeprefix('missing_')]
    assert not summarize(p, rows, source_unchanged=True)['sample_checks_passed']


@pytest.mark.parametrize('fault', ['initial_observation', 'cycle_observation', 'cycle_mask'])
def test_diagnostic_fault_remains_failed_while_healthy_tail_can_finish(runtime, monkeypatch, fault):
    from tools.learning.residual_session import ResidualSession
    from tools.validation.verify_engineering_domain import build_protocol, run_attempt
    if fault == 'initial_observation':
        original = ResidualSession.reset
        def reset(self, *args, **kwargs):
            snapshot = original(self, *args, **kwargs)
            snapshot.policy_observation[0] = float('nan')  # Returned diagnostic only, not physics.
            return snapshot
        monkeypatch.setattr(ResidualSession, 'reset', reset)
    else:
        original = ResidualSession.advance_cycle
        injected = False
        def advance(self, action):
            nonlocal injected
            result = original(self, action)
            if not injected:
                injected = True
                if fault == 'cycle_observation': result.next_snapshot.policy_observation[0] = float('nan')
                else: result.action_log['enabled'] = False
            return result
        monkeypatch.setattr(ResidualSession, 'advance_cycle', advance)
    spec = next(r for r in build_protocol()['attempts'] if r['family'] == 'single_axis')
    report = run_attempt(spec)
    assert report['error'] is not None and not report['completed']
    assert report['simulation_valid'] and report['physical_stopped']
    assert report['observation_valid'] is False or report['masking_valid'] is False
    assert report['physical_steps'] >= 10000
    assert not report['valid_for_learning']
