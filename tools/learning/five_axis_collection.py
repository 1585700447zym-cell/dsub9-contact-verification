"""Full-cycle data capture; output remains quarantined until independent audit."""
from copy import deepcopy
from dataclasses import asdict, is_dataclass
import math
from time import perf_counter
from .five_axis_action import normalized_action
from .five_axis_contract import VERSION, permission
from .episode_buffer import _safe_error_archive


class CollectionError(RuntimeError):
    def __init__(self, message, archive):
        super().__init__(message)
        self.archive = archive


def _freeze_evidence(session, raw, started):
    """Copy independent evidence, including steps with no completed CycleResult.

    Missing counters remain unknown. Historical last_finite is never substituted
    for the current observation, which may itself contain invalid diagnostic data.
    """
    evidence = {}; errors = {}
    env = getattr(session, 'env', None)
    controller = getattr(session, 'controller', None)
    readers = dict(
        environment_events=lambda: getattr(env, 'events', None),
        controller_events=lambda: getattr(controller, 'events', None),
        stop_samples=lambda: getattr(env, 'stop_samples', None),
        guard_facts=lambda: getattr(env, 'guard_facts', None),
        interface_fault=lambda: getattr(session, 'interface_fault', None),
        current_state=lambda: env.observe() if env is not None else None,
        historical_last_finite=lambda: getattr(env, 'last_finite', None),
        stop_time_s=lambda: getattr(session, 'stop_time', None),
        task_end_time_s=lambda: getattr(session, 'task_end_time', None),
        audit_end_time_s=lambda: getattr(getattr(env, 'data', None), 'time', None),
        physical_steps_observed=lambda: getattr(env, 'physical_steps', None),
        control_cycles_completed=lambda: getattr(session, 'cycle_id', None))
    for name, read in readers.items():
        try:
            evidence[name] = _safe_error_archive(read())
        except Exception as exc:
            evidence[name] = None; errors[name] = repr(exc)
    evidence['diagnostic_errors'] = errors
    raw['evidence'] = evidence
    # A failed reset may leave counters from a preceding episode: do not claim
    # them as this attempt's cost. The observed value remains diagnostic only.
    raw['cost'].update(physical_substeps=(evidence['physical_steps_observed']
        if raw['cost']['initializations_completed'] else None),
        wall_time_s=perf_counter() - started)


def collect_episode(session, case, *, policy, seed=None, max_cycles=13500):
    if type(max_cycles) is not int or max_cycles <= 0:
        raise ValueError('Positive control-cycle ceiling required')
    started = perf_counter()
    raw = dict(version=VERSION, transitions=[], trace=[], cycle_peaks=[], events=[],
               action_provider_calls=0, action_provider_successes=0, training_admitted=False,
               cost=dict(initialization_attempts=0, initializations_completed=0),
               case=asdict(case) if is_dataclass(case) else None, seed=seed)
    try:
        raw['cost']['initialization_attempts'] += 1
        session.reset(case, seed=seed)
        raw['cost']['initializations_completed'] += 1
        raw['trace'].append(deepcopy(session.prepare_cycle().state))
        if hasattr(session, 'observations'):
            raw['observation_version'] = session.observations.version
            raw['observation_schema'] = deepcopy(session.observations.schema)
        for _ in range(max_cycles):
            before = session.prepare_cycle()
            if permission(before.policy_observation) != before.residual_enabled:
                raise ValueError('Collector permission mismatch')
            if before.residual_enabled:
                raw['action_provider_calls'] += 1
                action = normalized_action(policy(before.policy_observation)).tolist()
                raw['action_provider_successes'] += 1
            else:
                action = [0.] * 5
            result = session.advance_cycle(action)
            next_snapshot = result.next_snapshot
            raw['transitions'].append(dict(observation=list(before.policy_observation),
                next_observation=list(next_snapshot.policy_observation),
                action=list(result.action_log['experience_action']), action_active=bool(before.residual_enabled),
                next_action_active=bool(next_snapshot.residual_enabled), reward=result.reward_terms['total'],
                reward_terms=deepcopy(result.reward_terms), action_log=deepcopy(result.action_log),
                dt=result.dt, discount=math.exp(-result.dt / 10.), terminated=bool(result.done), truncated=False))
            raw['trace'].append(deepcopy(result.trace_row)); raw['cycle_peaks'].append(deepcopy(result.cycle_peaks))
            raw['events'].extend(deepcopy(result.events))
            if result.done:
                raw['outcome'] = dict(session.adjudicate(), training_admitted=False, valid_for_learning=False)
                _freeze_evidence(session, raw, started)
                return raw
        raise RuntimeError('Collection ceiling reached before completed stop audit')
    except Exception as exc:
        _freeze_evidence(session, raw, started)
        raw['evidence_before_abort'] = deepcopy(raw['evidence'])
        if hasattr(session, '_abort_interface'):
            try:
                session._abort_interface(exc)
            except Exception as abort_exc:
                raw['abort_error'] = repr(abort_exc)
        _freeze_evidence(session, raw, started)
        raw['error'] = repr(exc)
        raw['outcome'] = dict(simulation_valid=False, physical_stopped=False,
            valid_for_learning=False, training_admitted=False, task_outcome='INVALID_SIMULATION')
        raise CollectionError(str(exc), raw) from exc
