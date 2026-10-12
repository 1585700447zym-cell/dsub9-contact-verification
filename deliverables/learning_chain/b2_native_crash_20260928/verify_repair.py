"""Offline evidence recheck: no simulation steps, model creation or optimization."""
import gzip
import json
import math
from pathlib import Path
import sys
from probe import HERE, ROOT, write
from validate_candidate import sha, candidate_runtime


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_files(base, files):
    for name, expected in files.items():
        assert sha(base/name) == expected, name
    return len(files)


def finite(value):
    if isinstance(value, dict):
        return not {'nonfinite','unserializable_type','unarchivable_record_type'}.intersection(value) and all(map(finite,value.values()))
    if isinstance(value, list):
        return all(map(finite,value))
    return not isinstance(value,float) or math.isfinite(value)


def main():
    old = ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927'
    admission = read(old/'admission.json')
    assert sha(old/'admission.json') == '1df0c0919e998e281dc910d314c54114efe521b7248922fc2733290c242994a9'
    preserved = dict(source_inputs=verify_files(ROOT, admission['source_sha256']),
        historical_files=verify_files(ROOT, read(old/'historical_files.json')),
        retry_binding_files=verify_files(ROOT, read(old/'retry_01/binding.json')['files']))
    original_dll = ROOT/'tmp/mujoco_3_13_probe/mujoco/mujoco.dll'
    assert sha(original_dll) == '5a4bcda24e9ada75e6f787e810e163fb25739ec1c5e62083af96286d26cfcb48'
    assert sha(old/'run/initial_checkpoint/manifest.json') == 'e5a7524a128124cd33b414dbfd0ae62a5d8e5a7947ed5bde18dfd07f261605d7'
    runtimes = {label:read(HERE/(label+'_runtime.json')) for label in (
        'horizon_fixed','horizon_control','horizon_control02')}
    for record in runtimes.values():
        verify_files(Path(record['package']), record['files'])
        assert record['training_admitted'] is False
        for name, expected in record['files'].items():
            if name != 'mujoco/mujoco.dll':
                assert sha(ROOT/'tmp/mujoco_3_13_probe'/name) == expected, name
    dll = {k:v['files']['mujoco/mujoco.dll'] for k,v in runtimes.items()}
    assert dll['horizon_fixed'] == dll['horizon_control']  # retained invalid control
    assert dll['horizon_fixed'] != dll['horizon_control02']
    assert read(HERE/'canary_original/result.json')['overflow_bytes'] == 4
    assert read(HERE/'canary_fixed/result.json')['overflow_bytes'] == 0
    assert read(HERE/'canary_guard_exit.json')['returncode'] == 86
    assert read(HERE/'control_forward_02_exit.json')['returncode'] == 0xc0000005
    assert read(HERE/'fixed_forward_01_exit.json')['returncode'] == 0
    forward = read(HERE/'fixed_forward_01/completed.json')
    assert forward['finite'] and not any(forward['warnings']) and forward['physical_steps'] == 0
    assert read(HERE/'fixed_episode_01_exit.json')['returncode'] == 0
    complete = read(HERE/'fixed_episode_01/completed.json')
    path = HERE/'fixed_episode_01/episode.json.gz'
    assert sha(path) == complete['archive_sha256']
    raw = json.loads(gzip.decompress(path.read_bytes()))
    assert finite(raw) and raw['done'] and raw['cycle_count'] == len(raw['results'])
    assert 1894 < raw['cycle_count'] <= 13000
    assert raw['optimizer_calls'] == raw['replay_published'] == 0
    assert raw['training_admitted'] is False
    import numpy as np
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([2026092716,1])))
    times = []
    for i, result in enumerate(raw['results']):
        expected = rng.uniform(-1.,1.,4).astype(np.float32).astype(float).tolist()
        assert result['action_log']['raw_action'] == expected
        assert result['done'] == (i == len(raw['results'])-1)
        times.append(result['next_snapshot']['time_s'])
    assert all(b > a for a,b in zip(times,times[1:]))
    candidate_runtime('horizon_fixed')  # import-only dependency for the pure audit helpers
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    from tools.learning.outcome import classify_outcome
    stopped = bool(actual_stop_pass(raw['stop_samples'],raw['events'],raw['stop_time'],
                   raw['audit_end_time_s'],.0002) and physical_tail_pass(raw['stop_samples'],raw['audit_end_time_s'],.0002))
    facts = raw['guard_facts']; final = raw['final_session']
    outcome = classify_outcome(simulation_valid=facts['simulation_valid'],
        contact_guard=bool(facts['contact_reasons']),motion_violation=bool(facts['motion_reasons']),
        full_success=final['task_finished'] and final['reason']=='GEOMETRIC_SUCCESS',physical_stopped=stopped)
    assert outcome == raw['outcome'] == complete['outcome']
    assert stopped and facts['simulation_valid'] and not any(facts[k] for k in ('invalid_reasons','contact_reasons','motion_reasons'))
    report = dict(status='captured_native_crash_repaired_and_episode_audited',
        root_cause='EPA horizon arrays of 24 integers overflow at entry 25',
        scope='captured state and original-seed failure-case regression; not universal engine or training qualification',
        patch='two allocations and one layout offset increased to 18 * iterations',
        independent_capacity_review=dict(critical=0,important=0),
        original_dll_sha256=sha(original_dll),candidate_dll_sha256=dll['horizon_fixed'],
        matched_compiler_unpatched_dll_sha256=dll['horizon_control02'],
        matched_compiler_control_access_violation=True,patched_forward=forward,
        canary_overflow_bytes=dict(original=4,fixed=0),
        invalid_control_01='Same DLL as fixed: old copied source timestamp caused incremental build to skip; not counted as unpatched evidence',
        preserved=preserved,diagnostic_setup_failures=1,diagnostic_dynamic_starts=2,
        original_training_and_retry_starts=6,total_dynamic_starts_including_diagnostics=8,
        diagnostic_episode=dict(cycles=raw['cycle_count'],outcome=outcome,
            guard_facts=facts,elapsed_s=complete['elapsed_s'],archive_sha256=sha(path)),
        diagnostic_only=True,formal_optimizer_updates=0,replay_published=0,
        training_runtime_admitted=False,policy_benefit_verified=False,b2_complete=False,
        static_subprocess_attempts={p.stem:read(p) for p in sorted(HERE.glob('*_exit.json'))
            if not p.stem.startswith(('capture_', 'fixed_episode_'))},
        validation_script_sha256=sha(HERE/'validate_candidate.py'),
        original_admission_preserved=True,original_checkpoint_preserved=True,
        other_candidate_package_files_identical_to_original=len(runtimes['horizon_fixed']['files'])-1)
    write(HERE/'assessment.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='static_subprocess_attempts'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
