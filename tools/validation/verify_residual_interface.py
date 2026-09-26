"""B.1 admission: replay immutable evidence, run tests, bind all current inputs.

This does not run SAC, authorize candidate replay, or build the B.2 adapter.
Use a fresh output directory. A failed check always retains a false record.
"""
import argparse
import gzip
import hashlib
from dataclasses import asdict
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess
import sys

from tools.learning.admission import (REQUIRED_GATES, InputBinding, canonical, digest,
    short_training_config, validate_config, validate_timings, verify_files, verify_test_report)
from tools.learning.runtime import ROOT, verify_runtime
from tools.validation.guard_evidence import input_fingerprints, snapshot_inputs

BASE = 'deliverables/residual_interface/'
MANIFESTS = [BASE + name + '/manifest.json' for name in (
    'observation_integration_20260924', 'learning_tensor_20260924',
    'collection_replay_20260924', 'engineering_preflight_20260924',
    'pose_scope_review_20260924', 'scheduled_boundary_20260926')]
SCOPE = 'docs/stage_b/工程范围与姿态参数冻结记录_v1.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def all_sources():
    result = input_fingerprints()
    paths = list((ROOT / 'tests/learning').glob('*.py'))
    paths += [ROOT / SCOPE, ROOT / 'docs/stage_b/工程范围与姿态参数冻结记录_v1.md',
              ROOT / 'docs/stage_b/工程短训配置_v1.json', ROOT / 'docs/stage_b/训练合同_v3.md']
    result.update({p.relative_to(ROOT).as_posix(): digest(p) for p in paths})
    return result


def qualified_runtime(package):
    runtime = verify_runtime(package)
    env = read(ROOT / BASE / 'learning_tensor_20260924/environment.json')
    if Path(sys.executable).resolve() != Path(env['executable']).resolve():
        raise ValueError('Qualified CPU interpreter required')
    if platform.python_version() != short_training_config()['versions']['python']:
        raise ValueError('Python version changed')
    lock = ROOT / BASE / 'learning_tensor_20260924/requirements.lock.txt'
    versions = {}
    for line in lock.read_text(encoding='utf-8').splitlines():
        if not line or line.startswith('#'): continue
        name, expected = line.split('==')
        versions[name] = importlib.metadata.version(name)
        if versions[name] != expected: raise ValueError(f'Dependency changed: {name}')
    torch_root = Path(env['package_paths']['torch']).parent
    for name, expected in env['torch_dll_sha256'].items():
        if digest(torch_root / 'lib' / name) != expected: raise ValueError(f'Torch DLL changed: {name}')
    return dict(native=runtime, executable=str(Path(sys.executable).resolve()),
        python=platform.python_version(), versions=versions,
        torch_dll_sha256=env['torch_dll_sha256'], lock_sha256=digest(lock))


def effective_parameters(config):
    validate_config(config)
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    e = LearningEnvironment(guard_config=GuardCandidateConfig(**config['guard']))
    actual = dict(timestep_s=float(e.model.opt.timestep), control_period_s=e.config.control_period,
        segments=e.segments, ccd_tolerance=float(e.model.opt.ccd_tolerance),
        backend=e.config.collision_backend, force_stop_N=e.config.stop_force_N,
        torque_stop_Nm=e.config.stop_torque_Nm, penetration_stop_m=e.config.stop_penetration_m,
        penetration_invalid_m=e.config.invalid_penetration_m, guard=asdict(e.guard_config))
    expected = dict(timestep_s=.0002, control_period_s=.002, segments=256,
        ccd_tolerance=1e-12, backend='native', force_stop_N=.025, torque_stop_Nm=.0005,
        penetration_stop_m=30e-6, penetration_invalid_m=80e-6, guard=config['guard'])
    if actual != expected: raise ValueError('Actual environment parameters differ from reviewed configuration')
    return actual


def check_scope():
    scope = read(ROOT / SCOPE)
    if (scope.get('version') != 'engineering_scope_v1' or
            scope.get('parameter_frozen') is not True or
            scope.get('scope') != 'engineering_chain_only' or
            scope.get('angle_is_model_trust_bound') is not False or
            scope.get('continuous_domain_certified') is not False or
            scope.get('guard') != short_training_config()['guard'] or
            scope.get('domain') != short_training_config()['domain'] or
            not set(MANIFESTS) <= set(scope.get('evidence_sha256', {}))):
        raise ValueError('Missing explicit limited-scope parameter decision')
    verify_files(ROOT, scope['evidence_sha256'])
    return scope


def run_logged(command, path):
    with Path(path).open('w', encoding='utf-8') as stream:
        result = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT)
    if result.returncode: raise ValueError(f'Check exited {result.returncode}; see {path}')


def check_native_archive(path):
    bootstrap = (
        "from tools.learning.runtime import ROOT,verify_runtime; "
        "verify_runtime(ROOT/'tmp/mujoco_3_13_probe'); "
        "from tools.validation.verify_native313_matrix_delivery import main; main()")
    run_logged([sys.executable, '-X', 'utf8', '-B', '-c', bootstrap], path)


def check_historical(target):
    files = {}
    for name in MANIFESTS:
        manifest = read(ROOT / name)
        maps = [manifest['files']]
        maps += [manifest[key] for key in ('evidence_sha256', 'references') if isinstance(manifest.get(key), dict)]
        for mapping in maps:
            verify_files(ROOT, mapping)
            files.update(mapping)
        files[name] = digest(ROOT / name)
    protocol = read(ROOT / BASE / 'scheduled_boundary_20260926/protocol.json')
    verify_files(ROOT, protocol['source_sha256'])
    for relative in (
        BASE + 'engineering_preflight_20260924/checks/recheck_archives.py',
        BASE + 'scheduled_boundary_20260926/checks/recheck_scheduled.py'):
        run_logged([sys.executable, '-X', 'utf8', '-B', str(ROOT / relative)],
                   target / (Path(relative).stem + '.log'))
    check_native_archive(target / 'native_archive.log')
    return files


def verify_cost_runtime(measured, current):
    if not measured or canonical(measured) != canonical(current):
        raise ValueError('Cost measured under a different or unrecorded runtime')


def check_cost(path, *, expected_runtime, binding=None):
    archive = Path(path).parent / 'timing_episode.json.gz'
    binding = binding or InputBinding([path, archive])
    cost = binding.json(path)
    verify_cost_runtime(cost.get('runtime'), expected_runtime)
    validate_config(cost['config'])
    if (cost.get('version') != 'b1_cost_v1' or cost.get('source_sha256') != input_fingerprints() or
            cost.get('source_unchanged') is not True or cost.get('independent_single_worker') is not True or
            cost.get('concurrent_regression') is not False or cost.get('optimizer_steps') != 0 or
            cost['network'].get('parameters_unchanged') is not True or
            cost['network'].get('optimizer_steps') != 0 or
            cost['outcome'].get('simulation_valid') is not True or
            cost['outcome'].get('physical_stopped') is not True or cost.get('contact_cycles', 0) < 1 or
            cost.get('cycles', 0) < 1):
        raise ValueError('Missing, stale or unsuccessful independent no-learning cost measurement')
    count = cost['cycles']
    validate_timings(cost['control_seconds'], expected_count=count)
    validate_timings(cost['logging_seconds'], expected_count=count)
    validate_timings(cost['initialization_seconds'], expected_count=3)
    validate_timings(cost['network']['batch_seconds'], expected_count=20)
    validate_timings([cost['final_audit_s'], cost['archive_s']], expected_count=2)
    if (cost['network']['measured_batches'] != 20 or cost['network']['warmup'] != 3 or
            cost['mean_control_cycle_s'] != sum(cost['control_seconds'])/count or
            cost['mean_logging_cycle_s'] != sum(cost['logging_seconds'])/count):
        raise ValueError('Cost summary/sample count mismatch')
    raw_bytes = binding.contents[archive.resolve()]
    if hashlib.sha256(raw_bytes).hexdigest() != cost['archive_sha256']: raise ValueError('Cost raw archive changed')
    raw = json.loads(gzip.decompress(raw_bytes))
    canonical(raw)  # Reject untagged NaN/Inf before stop-window reconstruction.
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    stopped = actual_stop_pass(raw['stop_samples'], raw['events'], raw['stop_time'], raw['end_time_s'], .0002)
    stopped = stopped and physical_tail_pass(raw['stop_samples'], raw['end_time_s'], .0002)
    if (raw['error'] is not None or raw['stop_error'] is not None or raw['interface_fault'] is not None or
            raw['outcome'] != cost['outcome'] or raw['runtime'] != expected_runtime or
            raw['guard_facts']['simulation_valid'] is not True or not stopped or
            len(raw['trace']) != count or raw['trace'][-1]['done'] is not True or
            sum(r['trace_row']['contact_count'] > 0 for r in raw['trace']) != cost['contact_cycles'] or
            raw['trace'][-1]['trace_row']['phase'] != 'STOPPING'):
        raise ValueError('Cost raw episode/counts/outcome/actual-stop mismatch')
    from tools.learning.admission import project_budget
    budget = project_budget(cycle_s=(sum(cost['control_seconds'])+sum(cost['logging_seconds']))/cost['cycles'],
        network_batch_s=max(cost['network']['batch_seconds']), init_s=max(cost['initialization_seconds']),
        audit_s=cost['final_audit_s']+cost['archive_s'])
    if budget != cost['budget']: raise ValueError('Cost projection mismatch')
    binding.verify_unchanged()
    return cost


def validate_run(*, output, config_path, cost_path, package, seed):
    target = Path(output).resolve()
    target.mkdir(parents=True, exist_ok=False)
    report = dict(version='b1_admission_v1', scope='engineering_chain_only', training_admitted=False,
        runnable_trainer=False, gates={name: False for name in REQUIRED_GATES}, errors=[],
        limitation='B.1 qualification only; B.2 must implement and verify admitted collection/update/restore. Candidate sessions stay quarantined. No continuous-domain or real-hardware certification.')
    def save():
        (target / 'admission.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    save()
    gate = 'config'
    try:
        config_binding = InputBinding([config_path])
        config = config_binding.json(config_path)
        validate_config(config)
        if type(seed) is not int or seed != config['sampling']['seed']: raise ValueError('Seed differs from explicit configuration')
        report['config'] = config
        report['gates'][gate] = True
        gate = 'runtime'
        report['runtime'] = qualified_runtime(package)
        report['effective_parameters'] = effective_parameters(config)
        report['gates'][gate] = True
        gate = 'scope'
        sources = all_sources()
        report['scope_record'] = check_scope()
        report['gates'][gate] = True
        report['source_sha256'] = sources
        snapshot_inputs(target, sources)
        gate = 'cost'
        cost_binding = InputBinding([cost_path, Path(cost_path).parent / 'timing_episode.json.gz'])
        gate = 'historical_evidence'
        evidence = check_historical(target)
        report['gates'][gate] = True
        gate = 'cost'
        report['cost_budget'] = check_cost(cost_path, expected_runtime=report['runtime'], binding=cost_binding)['budget']
        report['gates'][gate] = True
        gate = 'tests'
        report_path = target / 'learning_tests.xml'
        run_logged([sys.executable, '-X', 'utf8', '-B', '-m', 'pytest', '-p', 'no:cacheprovider',
            '-q', 'tests/learning', '-o', 'junit_family=xunit1', '--tb=short', f'--junitxml={report_path}'], target / 'learning_tests.log')
        required = {p.stem for p in (ROOT / 'tests/learning').glob('test_*.py')}
        report['tests'] = verify_test_report(report_path, required_modules=required, minimum=258)
        report['gates'][gate] = True
        gate = 'source_unchanged'
        if all_sources() != sources: raise ValueError('Inputs changed during admission checks')
        config_binding.verify_unchanged()
        cost_binding.verify_unchanged()
        verify_files(ROOT, evidence)
        verify_files(ROOT, report['scope_record']['evidence_sha256'])
        if qualified_runtime(package) != report['runtime']: raise ValueError('Runtime changed during admission')
        report['gates'][gate] = True
        # Copy user-supplied configuration/cost to bind even if located outside root.
        config_binding.copy_to(config_path, target / 'config.json')
        cost_binding.copy_to(cost_path, target / 'cost.json')
        cost_binding.copy_to(Path(cost_path).parent / 'timing_episode.json.gz', target / 'timing_episode.json.gz')
        if not target.is_relative_to(ROOT):
            raise ValueError('Successful delivery must reside within the worktree')
        evidence.update({p.relative_to(ROOT).as_posix(): digest(p) for p in target.iterdir()
                         if p.is_file() and p.name != 'admission.json'})
        evidence.update(report['scope_record']['evidence_sha256'])
        report['evidence_sha256'] = evidence
        report['training_admitted'] = all(report['gates'].values())
    except Exception as exc:
        report['gates'][gate] = False
        report['errors'].append(dict(gate=gate, error=repr(exc)))
    save()
    print(json.dumps(dict(training_admitted=report['training_admitted'], gates=report['gates'], errors=report['errors']), ensure_ascii=False))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--cost', required=True, type=Path)
    parser.add_argument('--package', required=True, type=Path)
    parser.add_argument('--seed', required=True, type=int)
    args = parser.parse_args()
    report = validate_run(output=args.output, config_path=args.config, cost_path=args.cost,
                          package=args.package, seed=args.seed)
    raise SystemExit(0 if report['training_admitted'] else 1)


if __name__ == '__main__': main()
