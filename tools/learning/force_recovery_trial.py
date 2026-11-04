"""Explicit zero-update force recovery on the existing 30-second protocol."""
from copy import deepcopy
import numpy as np
from . import time_budget_trial as previous
from .force_recovery import CONFIG, ForceRecoveryMixin, VERSION as RECOVERY_VERSION

VERSION = 'nano100_yaw_on_force_recovery_time_budget_v1'
OBSERVATION_VERSION = 'five_axis_N2_30s_force_recovery_permission_v1'
SPEEDS = previous.SPEEDS
make_controller = previous.make_controller


def protocol_config(search_speed_um_s=450):
    from tools.model.layered_task import TASK_ID
    result = previous.protocol_config(search_speed_um_s)
    result.update(version=VERSION, observation_version=OBSERVATION_VERSION, task_referee=TASK_ID,
        force_recovery=dict(CONFIG, version=RECOVERY_VERSION,
            wait_stable_s=result['controller_config']['wait_stable_s'],
            overshoot_basis='uncalibrated simulation convention: 20 percent above unchanged 5N trigger'),
        guard_observation_semantics='active blockers; historical force facts retained in independent recovery evidence')
    return result


class ForceRecoveryObservation(previous.TimeBudgetObservation):
    version = OBSERVATION_VERSION

    def __init__(self, initial, config, profile, environment):
        super().__init__(initial, config, profile)
        self.environment = environment

    def capture(self, snapshot, context, *, refresh=False):
        context = dict(context, guard_facts=self.environment.active_guard_facts())
        vector, raw = super().capture(snapshot, context, refresh=refresh)
        next(field for field in self.schema if field['name']=='latched_guards')['source'] = 'active_guard_blockers_after_verified_force_recovery'
        return vector, raw


def environment_class():
    class ForceRecoveryEnvironment(ForceRecoveryMixin, previous.environment_class()):
        def metadata(self):
            return {**super().metadata(), 'force_recovery_protocol':dict(CONFIG, version=RECOVERY_VERSION)}
    return ForceRecoveryEnvironment


def session_class(search_speed_um_s=450):
    class ForceRecoverySession(previous.session_class(search_speed_um_s)):
        def __init__(self, environment):
            if getattr(environment, 'force_recovery_version',None) != RECOVERY_VERSION:
                raise TypeError('Explicit native force recovery environment required')
            settings = dict(stop_force_N=5.,stop_torque_Nm=.1,stop_penetration_m=30e-6,
                recovery_force_N=.5,recovery_distance_m=.00025,recovery_speed=.0005,
                timestep=.0002,control_period=.002)
            if any(getattr(environment.config,key)!=value for key,value in settings.items()):
                raise ValueError('Registered native force recovery settings required')
            super().__init__(environment)
            self.contract = protocol_config(search_speed_um_s)

        def _reset_residual(self, case, seed):
            initial = super()._reset_residual(case, seed)
            self.observations = ForceRecoveryObservation(initial.state, self.controller.config,self.env.profile,self.env)
            self._decorated_cache = None
            return self.prepare_cycle()

        def _guard_failure_facts(self):
            return self.env.active_guard_facts()

        def _adjudication_facts(self):
            return (self.env.active_guard_facts() if self.env.force_history_completed()
                    else self.env.guard_facts)

        def _latched_guard_reason(self):
            if self.env.recovery_guard_clear():
                return None
            return super()._latched_guard_reason()

        def _stable_for_recovery(self):
            return self.env.force_recovery_stable()

        def _expected_recovery_stop_reasons(self):
            return super()._expected_recovery_stop_reasons()+('FORCE_LIMIT',)

        def _resume_after_recovery(self):
            self.env.resume_force_recovery(self.controller.config.recovery_min_actual_m)

        def _finish_peaks_ok(self, row):
            e, f = self.env, self.finish_criteria
            return (e.force_history_completed() and
                (bool(e.force_recovery_events) or e.peaks['force_N'] < f['force_N']) and
                np.linalg.norm(row['contact_wrench_M'][:3]) < f['force_N']
                and e.cycle_peaks['force_N'] < f['force_N'] and e.peaks['torque_G_Nm'] < f['torque_Nm']
                and e.peaks['penetration_m'] < f['penetration_m'])

        def _post_task_cycle(self, row):
            e = self.env; event = e.active_force_recovery
            if event and event['status']=='UNLOADING' and self.reason is None and e.recovery_guard_clear():
                if self.recovery_state is None:
                    self.controller._transition('WAIT_RECOVERY', self.policy_observation(row), 'FORCE_LIMIT_RECOVERY_REQUESTED')
                    self.controller.reference_release_requested = False
                    self.recovery_state = 'WAIT_STOP'
                    self.wait_start = event['trigger_time_s']
            super()._post_task_cycle(row)
            event = e.active_force_recovery
            if event and event['status']=='WAIT_RESUME' and self.recovery_state=='WAIT_RESUME':
                self.wait_start = event['retracted_time_s']

        def _finish(self, reason):
            e = self.env
            if self.stop_time is None and e.phase=='STOPPING' and (e.force_recovery_events or self.recovery_state):
                from tools.validation.native313_matrix_audit import actual_stop_start
                start = actual_stop_start(e.events, None)
                if start is not None and e.data.time-start > e.config.control_period+1e-10:
                    latest = e.force_recovery_events[-1] if e.force_recovery_events else None
                    force = latest is not None and latest['status']!='COMPLETED'
                    e.events.append(dict(time_s=float(e.data.time),phase='STOPPING',
                        reason='RECOVERY_FINAL_AUDIT_START',physical_stop_preserved=True,
                        recovery_kind='force' if force else 'normal', physical_stop_time_s=start,
                        recovery_count=e.recovery_count,
                        force_recovery_id=None if latest is None else latest['id'],decision_reason=reason))
            e.abort_force_recovery(reason)
            return super()._finish(reason)

        def adjudicate(self):
            result = super().adjudicate()
            events = self.env.force_recovery_events
            result.update(had_force_recovery=bool(events),force_recovery_count=len(events),
                completed_force_recovery_count=sum(e['status']=='COMPLETED' for e in events),
                peak_force_N=self.env.peaks.get('force_N',0.),
                force_recovery_fatal_reasons=list(self.env.force_recovery_fatal_reasons))
            return result

        def _trace_row(self, row):
            result = super()._trace_row(row)
            event = self.env.active_force_recovery
            result['force_recovery_state'] = None if event is None else event['status']
            result['force_recovery_count'] = len(self.env.force_recovery_events)
            return result

    return ForceRecoverySession


def receipt_fields(session):
    from .episode_buffer import _safe_error_archive
    return _safe_error_archive(dict(force_recovery=session.env.force_recovery_evidence(),
                cumulative_peaks=deepcopy(session.env.peaks)))


def collect_episode(session, case, *, policy, seed=None, max_cycles=16000):
    from .five_axis_collection import collect_episode as kernel, CollectionError
    contract = deepcopy(getattr(session, 'contract',None))
    if contract not in [protocol_config(v) for v in SPEEDS]:
        raise ValueError('Collector requires the explicit force recovery contract')
    if type(max_cycles) is not int or not 0 < max_cycles <= contract['max_cycles']:
        raise ValueError('Collection ceiling must be between 1 and 16000 cycles')

    def bind(raw):
        fields = receipt_fields(session)
        raw.update(version=VERSION, execution_contract=deepcopy(contract),
            time_budget_protocol=previous.protocol_config(round(contract['search_xy_limit_m_s']*1e6)),
            force_recovery_protocol=deepcopy(contract), training_admitted=False, valid_for_learning=False, **fields)
        raw.setdefault('evidence',{}).update(deepcopy(fields))
        raw.setdefault('observation_version',OBSERVATION_VERSION)
        return raw
    try:
        raw = kernel(session,case,policy=policy,seed=seed,max_cycles=max_cycles)
    except CollectionError as exc:
        bind(exc.archive)
        raise
    bind(raw)
    if session.contract != contract or raw['observation_version'] != OBSERVATION_VERSION:
        raw['error'] = 'Force recovery execution/observation contract changed'
        raise CollectionError(raw['error'],raw)
    return raw


def verify_group_composition(log, observation, contract):
    from .global_residual_action import recompose_logged_command
    from tools.validation.run_global_residual_authority import verify_composition_log
    if (contract not in [protocol_config(v) for v in SPEEDS] or
            log.get('contract_version') != VERSION or log.get('profile') != 'G1'):
        raise ValueError('Explicit force recovery composition contract required')
    _, command = recompose_logged_command(log, search_xy_limit_m_s=contract['search_xy_limit_m_s'])
    verify_composition_log(log,command,observation,contract['controller_config'])
    return True


def audit_archive(folder,reg,job,*,search_speed_um_s=450,source_trainer=None):
    from tools.validation.consistent_sac_audit import audit_archive as audit
    previous._speed(search_speed_um_s)
    return audit(folder,reg,job,source_trainer=source_trainer,force_recovery_group=search_speed_um_s)


if __name__ == '__main__':
    import json
    print(json.dumps(dict(configuration_only=True,
        groups=[protocol_config(v) for v in SPEEDS]),indent=2,allow_nan=False))
