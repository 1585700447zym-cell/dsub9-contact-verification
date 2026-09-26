"""Sequential headless timing, no replay publication and no optimizer step.

Repeat one existing center/+X development case for timing, not added boundary
coverage. Run separately from regression tests; archive the complete attempt.
"""
import argparse
from dataclasses import asdict
import gzip
import json
import math
from pathlib import Path
import statistics
import time

from tools.learning.admission import canonical, digest, project_budget, short_training_config
from tools.learning.runtime import ROOT, verify_runtime
from tools.validation.guard_evidence import input_fingerprints
from tools.validation.verify_engineering_domain import fresh_output


def network_proxy(*, repetitions=20, warmup=3):
    import numpy as np
    import torch
    from gymnasium.spaces import Box
    from stable_baselines3.sac.policies import SACPolicy
    from tools.learning.tensor_masks import canonical_actions, critic_target, actor_temperature_losses
    if type(repetitions) is not int or repetitions < 1 or type(warmup) is not int or warmup < 0:
        raise ValueError('Explicit positive repetitions and nonnegative warmup required')
    c = short_training_config()['learning']
    torch.set_num_threads(c['torch_threads'])
    torch.manual_seed(c['seed'])
    policy = SACPolicy(Box(-10., 10., (120,), dtype=np.float32),
                       Box(-1., 1., (4,), dtype=np.float32),
                       lambda _: c['learning_rate'], net_arch=c['network'])
    before = {k: v.detach().clone() for k, v in policy.state_dict().items()}
    n = c['batch_size']
    obs = torch.randn(n, 120)
    nxt = torch.randn(n, 120)
    active = torch.arange(n).reshape(-1, 1) % 2 == 0
    actions = canonical_actions(torch.zeros(n, 4), active)
    log_alpha = torch.tensor(math.log(c['entropy_initial']), requires_grad=True)
    times = []
    for iteration in range(warmup + repetitions):
        started = time.perf_counter()
        policy.zero_grad(set_to_none=True)
        log_alpha.grad = None
        with torch.no_grad():
            a_next, lp_next = policy.actor.action_log_prob(nxt)
            q_next = torch.min(torch.cat(policy.critic_target(nxt, canonical_actions(a_next, active)), dim=1), dim=1, keepdim=True).values
            target = critic_target(reward=torch.zeros(n, 1), discount=torch.full((n, 1), c['gamma_nominal']),
                terminated=torch.zeros(n, 1, dtype=torch.bool), q_next=q_next,
                log_probability=lp_next.reshape(-1, 1), alpha=log_alpha.detach().exp(), next_active=active)
        q_values = policy.critic(obs, actions)
        sum((q-target).square().mean() for q in q_values).backward()
        for p in policy.critic.parameters(): p.requires_grad_(False)
        action, lp = policy.actor.action_log_prob(obs)
        q = torch.min(torch.cat(policy.critic(obs, canonical_actions(action, active)), dim=1), dim=1, keepdim=True).values
        actor, temperature = actor_temperature_losses(q=q, log_probability=lp.reshape(-1, 1),
            log_alpha=log_alpha, target_entropy=c['target_entropy'], active=active)
        actor.backward()
        temperature.backward()
        for p in policy.critic.parameters(): p.requires_grad_(True)
        if iteration >= warmup: times.append(time.perf_counter()-started)
    unchanged = all(torch.equal(v, policy.state_dict()[k]) for k, v in before.items())
    if not unchanged: raise RuntimeError('Timing must never change network weights')
    return dict(batch_seconds=times, median_batch_s=statistics.median(times),
        max_batch_s=max(times), measured_batches=repetitions, warmup=warmup,
        parameters_unchanged=unchanged, optimizer_steps=0,
        data='synthetic finite tensors only; no episode experience used',
        limitation='Backward compute proxy: excludes optimizer step, replay sampling and checkpoint IO')


def measure(target):
    from tools.validation.verify_residual_interface import qualified_runtime
    from tools.learning.episode_buffer import _safe_error_archive
    runtime = qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe')
    from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment
    from tools.learning.residual_session import ResidualSession
    from tools.validation.run_contact_cases import ContactCase
    config = short_training_config()
    sources = input_fingerprints()
    case = ContactCase(name='cost_repeat_center_x_pos', x_offset_m=0., y_offset_m=0.,
                       roll_rad=0., pitch_rad=0., start_origin_z_m=-.004, target_depth_m=.004)
    init = []
    session = None
    trace, step_times, log_times = [], [], []
    error = stop_error = None
    outcome = dict(simulation_valid=False, physical_stopped=False, valid_for_learning=False)
    audit_s = 0.
    try:
        for _ in range(3):
            started = time.perf_counter()
            session = ResidualSession(environment=LearningEnvironment(guard_config=GuardCandidateConfig(**config['guard'])))
            session.reset(case, seed=config['sampling']['seed'])
            init.append(time.perf_counter()-started)
        for _ in range(config['sampling']['watchdog_cycles']):
            if session.done: break
            started = time.perf_counter()
            result = session.advance_cycle([1., 0., 0., 0.])
            step_times.append(time.perf_counter()-started)
            started = time.perf_counter()
            row = asdict(result)
            trace.append(row)  # Retain offending raw row BEFORE strict serialization.
            canonical(row)
            log_times.append(time.perf_counter()-started)
        if not session.done: raise RuntimeError('WATCHDOG_EXCEEDED')
        started = time.perf_counter()
        outcome = session.adjudicate()
        audit_s = time.perf_counter()-started
        if not outcome['simulation_valid'] or not outcome['physical_stopped']:
            raise RuntimeError('Cost repeat invalid or not stopped')
    except Exception as exc:
        error = repr(exc)
        try:
            if session is not None:
                if not session.done:
                    session.start_external_tail()
                    for _ in range(1500):
                        if session.done: break
                        trace.append(asdict(session.advance_cycle([0.]*4)))
                outcome = session.adjudicate()
        except Exception as tail_exc:
            stop_error = repr(tail_exc)
    archive = dict(case=asdict(case), trace=trace, outcome=outcome,
        error=error, stop_error=stop_error, runtime=runtime,
        events=session.env.events if session else [], stop_samples=session.env.stop_samples if session else [],
        stop_time=getattr(session, 'stop_time', None), end_time_s=float(session.env.data.time) if session else None,
        interface_fault=getattr(session, 'interface_fault', None),
        guard_facts=session.env.guard_facts if session else None,
        qpos=session.env.data.qpos.tolist() if session else None,
        qvel=session.env.data.qvel.tolist() if session else None,
        environment=session.env.metadata() if session else None, training_admitted=False)
    started = time.perf_counter()
    with gzip.open(target / 'timing_episode.json.gz', 'wt', encoding='utf-8') as stream:
        json.dump(_safe_error_archive(archive), stream, ensure_ascii=False, allow_nan=False)
    archive_s = time.perf_counter()-started
    if error:
        (target / 'failure.json').write_text(json.dumps(dict(training_admitted=False,
            error=error, stop_error=stop_error, outcome=outcome), allow_nan=False), encoding='utf-8')
        raise RuntimeError(f'Cost attempt failed; raw diagnostics retained: {error}')
    network = network_proxy()
    count = len(step_times)
    result = dict(version='b1_cost_v1', source_sha256=sources, runtime=runtime,
        source_unchanged=sources == input_fingerprints(), config=config,
        initialization_seconds=init, control_seconds=step_times, logging_seconds=log_times,
        cycles=count, contact_cycles=sum(row['trace_row']['contact_count'] > 0 for row in trace),
        mean_control_cycle_s=sum(step_times)/count, mean_logging_cycle_s=sum(log_times)/count,
        final_audit_s=audit_s, archive_s=archive_s, network=network,
        outcome=outcome, archive_sha256=digest(target / 'timing_episode.json.gz'),
        independent_single_worker=True, concurrent_regression=False,
        training_admitted=False, optimizer_steps=0,
        limitation='One repeated development trajectory, not worst-case throughput or new scope evidence')
    result['budget'] = project_budget(cycle_s=(sum(step_times)+sum(log_times))/count,
        network_batch_s=network['max_batch_s'], init_s=max(init), audit_s=audit_s+archive_s)
    if qualified_runtime(ROOT / 'tmp/mujoco_3_13_probe') != runtime:
        raise RuntimeError('Runtime changed during timing')
    (target / 'cost.json').write_text(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args = parser.parse_args()
    target = fresh_output(ROOT / 'deliverables/residual_interface', args.tag)
    # Record the protocol before any timing; exceptions retain a failed result.
    (target / 'protocol.json').write_text(json.dumps(dict(config=short_training_config(),
        purpose='isolated sequential timing only', case='repeat center +X',
        source_sha256=input_fingerprints()), indent=2), encoding='utf-8')
    try:
        result = measure(target)
        print(json.dumps({k: result[k] for k in ('cycles', 'contact_cycles', 'mean_control_cycle_s', 'budget')}))
    except Exception as exc:
        if not (target / 'failure.json').exists():
            (target / 'failure.json').write_text(json.dumps(dict(training_admitted=False, error=repr(exc))), encoding='utf-8')
        raise


if __name__ == '__main__': main()
