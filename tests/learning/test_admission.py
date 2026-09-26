"""Admission counterexamples use synthetic files, never physical qualification."""
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import pytest


def api():
    assert importlib.util.find_spec('tools.learning.admission') is not None, 'Admission implementation missing'
    return importlib.import_module('tools.learning.admission')


def test_explicit_config_and_case_scope():
    a = api()
    config = a.short_training_config()
    a.validate_config(config)
    a.validate_case(dict(x_offset_m=-50e-6, y_offset_m=50e-6,
        roll_rad=0., pitch_rad=0., start_origin_z_m=-.004, target_depth_m=.004))
    assert config['sampling']['target_cycles'] == 20000
    assert config['learning']['gamma_nominal'] == pytest.approx(.9998000199986667)


def test_delivered_json_configuration_is_usable():
    root = Path(__file__).resolve().parents[2]
    config = json.loads((root / 'docs/stage_b/工程短训配置_v1.json').read_text(encoding='utf-8'))
    api().validate_config(config)


@pytest.mark.parametrize('mutation', ['missing', 'period', 'guard', 'domain', 'nan', 'bool', 'extra'])
def test_changed_or_incomplete_config_rejected(mutation):
    a = api()
    c = a.short_training_config()
    if mutation == 'missing': del c['learning']['learning_rate']
    if mutation == 'period': c['physics']['policy_period_s'] = .02
    if mutation == 'guard': c['guard']['max_rotation_from_start_rad'] = .08
    if mutation == 'domain': c['domain']['roll_rad'] = .01
    if mutation == 'nan': c['learning']['learning_rate'] = float('nan')
    if mutation == 'bool': c['sampling']['workers'] = True
    if mutation == 'extra': c['bypass'] = True
    with pytest.raises(ValueError): a.validate_config(c)


@pytest.mark.parametrize('field,value', [('x_offset_m', .000050001), ('roll_rad', 1e-12),
    ('start_origin_z_m', -.005), ('pitch_rad', float('nan')), ('target_depth_m', True)])
def test_out_of_scope_cases_rejected(field, value):
    a = api()
    case = dict(x_offset_m=0., y_offset_m=0., roll_rad=0., pitch_rad=0.,
                start_origin_z_m=-.004, target_depth_m=.004)
    case[field] = value
    with pytest.raises(ValueError): a.validate_case(case)


def test_manifest_detects_changed_file_and_path_escape(tmp_path):
    a = api()
    (tmp_path / 'evidence.txt').write_text('evidence', encoding='utf-8')
    manifest = {'evidence.txt': hashlib.sha256(b'evidence').hexdigest()}
    assert a.verify_files(tmp_path, manifest) == 1
    (tmp_path / 'evidence.txt').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError): a.verify_files(tmp_path, manifest)
    with pytest.raises(ValueError): a.verify_files(tmp_path, {'../outside': '0'*64})
    with pytest.raises(ValueError): a.verify_files(tmp_path, {})


@pytest.mark.parametrize('kind', ['failure', 'error', 'skipped', 'empty', 'duplicate', 'missing_module'])
def test_false_green_xml_rejected(tmp_path, kind):
    a = api()
    cases = '<testcase classname="tests.learning.test_alpha" name="one" />'
    if kind in ('failure', 'error', 'skipped'):
        cases = f'<testcase classname="tests.learning.test_alpha" name="one"><{kind}/></testcase>'
    if kind == 'empty': cases = ''
    if kind == 'duplicate': cases *= 2
    path = tmp_path / 'suite.xml'
    path.write_text(f'<testsuites><testsuite>{cases}</testsuite></testsuites>', encoding='utf-8')
    required = {'test_missing'} if kind == 'missing_module' else {'test_alpha'}
    with pytest.raises(ValueError): a.verify_test_report(path, required_modules=required, minimum=1)


def test_real_xml_and_bound_record_revalidation(tmp_path):
    a = api()
    xml = tmp_path / 'suite.xml'
    xml.write_text('<testsuites><testsuite><testcase classname="tests.learning.test_alpha" name="one"/></testsuite></testsuites>')
    assert a.verify_test_report(xml, required_modules={'test_alpha'}, minimum=1)['passed'] == 1
    config = a.short_training_config()
    record = dict(version='b1_admission_v1', training_admitted=True,
        scope='engineering_chain_only', config=config, runtime={'test': 'fixture'},
        source_sha256={'suite.xml': hashlib.sha256(xml.read_bytes()).hexdigest()},
        evidence_sha256={'suite.xml': hashlib.sha256(xml.read_bytes()).hexdigest()},
        gates={name: True for name in a.REQUIRED_GATES})
    path = tmp_path / 'admission.json'
    path.write_text(json.dumps(record), encoding='utf-8')
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    kwargs = dict(root=tmp_path, expected_digest=digest, config=config,
                  runtime={'test': 'fixture'}, current_sources=record['source_sha256'])
    assert a.verify_admission(path, **kwargs)['scope'] == 'engineering_chain_only'
    bad = deepcopy(kwargs)
    bad['runtime'] = {'test': 'wrong'}
    with pytest.raises(ValueError): a.verify_admission(path, **bad)
    bad = deepcopy(kwargs)
    bad['current_sources']['new.py'] = 'a'*64
    with pytest.raises(ValueError): a.verify_admission(path, **bad)
    record['gates']['scope'] = False
    path.write_text(json.dumps(record), encoding='utf-8')
    with pytest.raises(ValueError): a.verify_admission(path, **kwargs)
    kwargs['expected_digest'] = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError): a.verify_admission(path, **kwargs)


def test_cost_projection_includes_full_episode_overshoot():
    a = api()
    result = a.project_budget(cycle_s=.01, network_batch_s=.1, init_s=1., audit_s=2.)
    # 20000 requested + at most 13000 watchdog cycles; 1 update per 4 audited cycles.
    assert result['projected_cycles_cap'] == 33000
    assert result['gradient_batches_cap'] == 8250
    assert result['sampling_seconds'] == 330.
    assert result['network_proxy_seconds'] == 825.
    assert result['actual_training_measured'] is False
    with pytest.raises(ValueError): a.project_budget(cycle_s=float('nan'), network_batch_s=.1, init_s=1., audit_s=2.)


def test_cost_network_proxy_does_not_update_weights():
    assert importlib.util.find_spec('tools.validation.measure_residual_cost') is not None, 'Cost implementation missing'
    m = importlib.import_module('tools.validation.measure_residual_cost')
    result = m.network_proxy(repetitions=2, warmup=1)
    assert result['parameters_unchanged'] is True
    assert result['optimizer_steps'] == 0
    assert result['measured_batches'] == 2
    assert len(result['batch_seconds']) == 2
    assert all(x > 0 for x in result['batch_seconds'])


def test_validation_cli_records_missing_inputs_without_admitting(tmp_path):
    import subprocess
    import sys
    assert importlib.util.find_spec('tools.validation.verify_residual_interface') is not None, 'Formal validator missing'
    result = subprocess.run([sys.executable, '-X', 'utf8', '-B', '-m',
        'tools.validation.verify_residual_interface', '--output', str(tmp_path / 'attempt'),
        '--config', str(tmp_path / 'missing.json'), '--cost', str(tmp_path / 'cost.json'),
        '--package', str(tmp_path / 'missing_package'), '--seed', '2026092609'],
        capture_output=True, text=True, encoding='utf-8')
    assert result.returncode != 0
    record = json.loads((tmp_path / 'attempt/admission.json').read_text(encoding='utf-8'))
    assert record['training_admitted'] is False
    assert record['gates']['config'] is False
    assert record['errors']


def test_effective_physics_not_just_config_file(runtime):
    assert importlib.util.find_spec('tools.validation.verify_residual_interface') is not None, 'Formal validator missing'
    validator = importlib.import_module('tools.validation.verify_residual_interface')
    result = validator.effective_parameters(api().short_training_config())
    assert result['timestep_s'] == .0002
    assert result['control_period_s'] == .002
    assert result['force_stop_N'] == .025
    assert result['penetration_invalid_m'] == 80e-6


def test_native_archive_child_selects_runtime(tmp_path):
    validator = importlib.import_module('tools.validation.verify_residual_interface')
    assert hasattr(validator, 'check_native_archive'), 'Native child bootstrap missing'
    validator.check_native_archive(tmp_path / 'native.log')
    assert '14 raw archives' in (tmp_path / 'native.log').read_text(encoding='utf-8')


def test_cost_watchdog_retains_trace_and_stop(tmp_path, runtime, monkeypatch):
    import gzip
    m = importlib.import_module('tools.validation.measure_residual_cost')
    original = m.short_training_config
    def bounded():
        result = original()
        result['sampling']['watchdog_cycles'] = 1
        return result
    monkeypatch.setattr(m, 'short_training_config', bounded)
    with pytest.raises(RuntimeError): m.measure(tmp_path)
    assert (tmp_path / 'timing_episode.json.gz').is_file(), 'Failed attempt raw trace was lost'
    with gzip.open(tmp_path / 'timing_episode.json.gz', 'rt', encoding='utf-8') as stream:
        raw = json.load(stream)
    assert raw['error']
    assert len(raw['trace']) > 1
    assert raw['outcome']['physical_stopped'] is True
    assert raw['outcome']['valid_for_learning'] is False


def test_cost_nonfinite_logging_retains_failed_row(tmp_path, runtime, monkeypatch):
    import gzip
    from tools.learning.residual_session import ResidualSession
    m = importlib.import_module('tools.validation.measure_residual_cost')
    original = ResidualSession.advance_cycle
    calls = 0
    def inject(self, action):
        nonlocal calls
        result = original(self, action)
        calls += 1
        if calls == 1: result.reward_terms['diagnostic_nan'] = float('nan')
        return result
    monkeypatch.setattr(ResidualSession, 'advance_cycle', inject)
    with pytest.raises(RuntimeError): m.measure(tmp_path)
    assert (tmp_path / 'timing_episode.json.gz').is_file(), 'Failed logging erased the attempt'
    with gzip.open(tmp_path / 'timing_episode.json.gz', 'rt', encoding='utf-8') as stream:
        raw = json.load(stream)
    assert raw['trace'][0]['reward_terms']['diagnostic_nan'] == {'nonfinite': 'nan'}
    assert raw['error']
    assert raw['outcome']['physical_stopped'] is True


@pytest.mark.parametrize('mutation', ['empty', 'negative', 'length', 'bool', 'nan'])
def test_invalid_cost_samples_rejected(mutation):
    a = api()
    assert hasattr(a, 'validate_timings'), 'Timing sample validation missing'
    values = [.1, .2]
    if mutation == 'empty': values = []
    if mutation == 'negative': values[0] = -.1
    if mutation == 'length': values = [.1]
    if mutation == 'bool': values[0] = True
    if mutation == 'nan': values[0] = float('nan')
    with pytest.raises(ValueError): a.validate_timings(values, expected_count=2)


def test_cost_runtime_must_match_current():
    validator = importlib.import_module('tools.validation.verify_residual_interface')
    assert hasattr(validator, 'verify_cost_runtime'), 'Cost runtime binding missing'
    validator.verify_cost_runtime({'python': 'fixture'}, {'python': 'fixture'})
    with pytest.raises(ValueError): validator.verify_cost_runtime({'python': 'old'}, {'python': 'new'})
    with pytest.raises(ValueError): validator.verify_cost_runtime({}, {'python': 'new'})


def test_inputs_changed_after_check_are_rejected(tmp_path):
    a = api()
    assert hasattr(a, 'InputBinding'), 'Input snapshot binding missing'
    path = tmp_path / 'config.json'
    path.write_text('{"seed":1}')
    binding = a.InputBinding([path])
    assert binding.json(path) == {'seed': 1}
    path.write_text('{"seed":2}')
    assert binding.json(path) == {'seed': 1}
    with pytest.raises(ValueError): binding.verify_unchanged()
    binding.copy_to(path, tmp_path / 'snapshot.json')
    assert json.loads((tmp_path / 'snapshot.json').read_text()) == {'seed': 1}
