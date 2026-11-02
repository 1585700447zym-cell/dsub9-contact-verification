"""B2-01: qualify additive collection code, then audit three fresh attempts.

No SAC updates, no final test-set use, no claim of learning effectiveness.
The complete native episodes check real publication and unchanged physics.
"""
import argparse
from dataclasses import asdict
import gzip
import json
from pathlib import Path
import sys
import time

from tools.learning.runtime import ROOT
from tools.learning.admission import digest, verify_files, validate_case, canonical
from tools.learning.b2_admission import CollectionAdmission, create_collection_admission
from tools.validation.verify_residual_interface import all_sources, qualified_runtime, run_logged


def save(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')


def verification_attempts():
    from tools.learning.admission import short_training_config
    from tools.learning.admitted_collection import EngineeringSampler
    center = dict(name='aligned', x_offset_m=0., y_offset_m=0., roll_rad=0., pitch_rad=0.,
                  start_origin_z_m=-.004, target_depth_m=.004)
    return [dict(id='sampled_zero', case=EngineeringSampler(short_training_config()).next_case(),
                 action=[0.] * 4, cut_steps=None),
            dict(id='center_plus_x', case=center.copy(), action=[1., 0., 0., 0.], cut_steps=None),
            dict(id='untrained_cut', case=center.copy(), action=None, cut_steps=8)]


def validate_attempt(raw, item, *, seed, qualification_sha256):
    validate_case(raw.get('case', {}))
    validate_case(item.get('case', {}))
    if (raw.get('episode_id') != item['id'] or raw['case'] != item['case'] or
            type(raw.get('seed')) is not int or raw['seed'] != seed or
            raw.get('qualification_sha256') != qualification_sha256):
        raise ValueError('Attempt identity, scope or qualification differs from protocol')


def validate_outcome(raw, *, stopped):
    from tools.learning.outcome import classify_outcome
    facts, final = raw['guard_facts'], raw['final_session']
    if type(facts['simulation_valid']) is not bool or type(final['task_finished']) is not bool:
        raise ValueError('Raw validity/completion facts must be boolean')
    actual = classify_outcome(simulation_valid=facts['simulation_valid'],
        contact_guard=bool(facts['contact_reasons']), motion_violation=bool(facts['motion_reasons']),
        full_success=final['task_finished'] and final['reason'] == 'GEOMETRIC_SUCCESS',
        physical_stopped=bool(stopped and final['phase'] == 'STOPPING'))
    if canonical(actual) != canonical(raw['outcome']):
        raise ValueError('Claimed outcome differs from original physical facts')
    return actual


def audit_archives(target):
    """Recompute stopping and replay eligibility from durable original data."""
    protocol = json.loads((target / 'protocol.json').read_text(encoding='utf-8'))
    if (protocol.get('version') != 'b2_collection_check_v1' or
            type(protocol.get('seed')) is not int or protocol['seed'] != 2026092609 or
            canonical(protocol.get('attempts')) != canonical(verification_attempts())):
        raise ValueError('Missing, duplicated or changed preregistered acceptance attempts')
    qualification_sha256 = digest(target / 'admission.json')
    from tools.learning.audited_replay import AuditedReplay
    from tools.validation.native313_matrix_audit import actual_stop_pass
    from tools.validation.run_contact_candidate_stop import physical_tail_pass
    import numpy as np
    pool = AuditedReplay(capacity=100000)
    summaries = []
    regression_passed = False
    for item in protocol['attempts']:
        folder = target / 'episodes' / item['id']
        raw = json.loads(gzip.decompress((folder / 'episode.json.gz').read_bytes()))
        status = json.loads((folder / 'status.json').read_text(encoding='utf-8'))
        validate_attempt(raw, item, seed=protocol['seed'], qualification_sha256=qualification_sha256)
        if raw['fault'] is not None:
            raise ValueError('Attempt differs from preregistered case/seed or has a fault')
        stopped = actual_stop_pass(raw['stop_samples'], raw['events'], raw['stop_time'], raw['audit_end_time_s'], .0002)
        stopped = stopped and physical_tail_pass(raw['stop_samples'], raw['audit_end_time_s'], .0002)
        validate_outcome(raw, stopped=stopped)
        if (not stopped or raw['guard_facts']['simulation_valid'] is not True or
                raw['outcome']['valid_for_learning'] is not True or
                raw['optimizer_steps'] != 0 or status['archive_sha256'] != digest(folder / 'episode.json.gz')):
            raise ValueError('Raw validity, stop audit or archive binding failed')
        rows = raw['transitions']
        if item['cut_steps'] is not None:
            if (len(rows) != item['cut_steps'] or not rows[-1]['truncated'] or rows[-1]['terminated'] or
                    rows[-1]['reward_terms']['terminal'] != 0 or
                    rows[-1]['trace_row']['time_s'] >= raw['audit_end_time_s']):
                raise ValueError('Truncation/bootstrap boundary differs from real cutoff')
        elif not rows[-1]['terminated']:
            raise ValueError('Complete native episode missing terminal boundary')
        publication = pool.publish(item['id'], rows, outcome=raw['outcome'], training_admitted=True)
        if publication['committed'] != status['committed'] or status['status'] != 'published':
            raise ValueError('Durable archive differs from published count')
        summaries.append(dict(id=item['id'], transitions=len(rows), outcome=raw['outcome'],
            contact_cycles=sum(r['trace_row']['contact_count'] > 0 for r in rows),
            action_active_cycles=sum(r['action_active'] for r in rows),
            truncated=rows[-1]['truncated'], end_time_s=raw['audit_end_time_s']))
        if item['id'] == 'center_plus_x':
            old = json.loads(gzip.decompress((ROOT / 'deliverables/residual_interface/b1_cost_20260926/timing_episode.json.gz').read_bytes()))
            if [r['trace_row'] for r in rows] != [r['trace_row'] for r in old['trace']]:
                raise ValueError('New collection changed the inherited full physical trajectory')
            regression_passed = True
    pool.sample(256, rng=np.random.default_rng(2026092609))
    return dict(attempts=summaries, published_transitions=len(pool), replay_tensor_sampled=256,
                center_plus_x_exact_physical_regression=regression_passed, optimizer_steps=0)


def run(output):
    target = Path(output).resolve()
    if not target.is_relative_to(ROOT): raise ValueError('Output must stay within worktree')
    target.mkdir(parents=True, exist_ok=False)
    save(target / 'assessment.json', dict(collection_verified=False, optimizer_steps=0, status='started'))
    try:
        runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
        from tools.learning.admission import short_training_config
        from tools.learning.admitted_collection import AdmittedCollector, EngineeringSampler
        from tools.learning.audited_replay import AuditedReplay
        from tools.validation.run_contact_cases import ContactCase
        import numpy as np
        import torch
        from gymnasium import spaces
        from stable_baselines3.sac.policies import SACPolicy
        config = short_training_config()
        seed = config['sampling']['seed']
        attempts = verification_attempts()
        protocol = dict(version='b2_collection_check_v1', seed=seed, attempts=attempts,
            purpose='Fresh collection acceptance, not policy training or evaluation', runtime=runtime,
            optimizer_steps=0, baseline_git='d2e7e4f', source_sha256=all_sources())
        save(target / 'protocol.json', protocol)
        run_logged([sys.executable, '-X', 'utf8', '-B', '-m', 'pytest', '-p', 'no:cacheprovider',
            '-q', 'tests/learning', '-o', 'junit_family=xunit1', '--tb=short',
            f'--junitxml={target / "learning_tests.xml"}'], target / 'learning_tests.log')
        create_collection_admission(target / 'admission.json', test_report=target / 'learning_tests.xml',
                                    checked_sources=protocol['source_sha256'])
        permit = CollectionAdmission(target / 'admission.json', expected_digest=digest(target / 'admission.json'))
        torch.set_num_threads(1); torch.manual_seed(seed)
        policy = SACPolicy(spaces.Box(-10., 10., shape=(120,), dtype=np.float32),
            spaces.Box(-1., 1., shape=(4,), dtype=np.float32), lambda _: .0003,
            net_arch=[256, 256], activation_fn=torch.nn.ReLU)
        before = {k: v.detach().clone() for k, v in policy.state_dict().items()}
        class Fixed:
            def __init__(self, action): self.action = np.asarray(action, dtype=np.float32)
            def predict(self, observation, deterministic=False): return self.action.copy(), None
        replay = AuditedReplay(capacity=config['learning']['replay_capacity'])
        collector = AdmittedCollector(admission=permit, replay=replay, output=target / 'episodes')
        start = time.perf_counter()
        for item in attempts:
            collector.start(item['id'], case=item['case'], seed=seed)
            active_policy = policy if item['action'] is None else Fixed(item['action'])
            if item['cut_steps']:
                collector.collect(active_policy, item['cut_steps'], cut_at_end=True)
            else:
                while collector.active:
                    result = collector.collect(active_policy, 500)
                    print(json.dumps(dict(attempt=item['id'], **result)), flush=True)
            if collector.attempts[-1]['status'] != 'published':
                raise ValueError('Native acceptance attempt was not published')
            save(target / 'attempts.json', collector.attempts)
        elapsed = time.perf_counter() - start
        if any(not torch.equal(before[k], v) for k, v in policy.state_dict().items()):
            raise ValueError('Untrained policy parameters changed')
        if policy.actor.optimizer.state or policy.critic.optimizer.state:
            raise ValueError('Unexpected optimizer state')
        permit.verify()
        report = audit_archives(target)
        report.update(collection_verified=True, runnable_trainer=False,
            policy_parameters_unchanged=True, collection_wall_s=elapsed,
            tests=json.loads((target / 'admission.json').read_text(encoding='utf-8'))['tests'])
        save(target / 'assessment.json', report)
        save(target / 'manifest.json', dict(version='b2_collection_delivery_v1', files={
            p.relative_to(ROOT).as_posix(): digest(p) for p in target.rglob('*')
            if p.is_file() and p.name != 'manifest.json'}))
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return report
    except Exception as exc:
        save(target / 'assessment.json', dict(collection_verified=False, runnable_trainer=False,
            optimizer_steps=0, error=repr(exc)))
        raise


def recheck(target):
    target = Path(target).resolve()
    manifest = json.loads((target / 'manifest.json').read_text(encoding='utf-8'))
    verify_files(ROOT, manifest['files'])
    admission = target / 'admission.json'
    CollectionAdmission(admission, expected_digest=manifest['files'][admission.relative_to(ROOT).as_posix()])
    result = audit_archives(target)
    report = json.loads((target / 'assessment.json').read_text(encoding='utf-8'))
    if report['collection_verified'] is not True or any(report[k] != v for k, v in result.items()):
        raise ValueError('Assessment differs from raw audit')
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--recheck', action='store_true')
    args = parser.parse_args()
    if args.recheck: recheck(args.output)
    else: run(args.output)
