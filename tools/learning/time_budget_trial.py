"""Opt-in 450/900 comparison on the SAME warning-only, time-only protocol.

No environment, policy or rollout is constructed by importing/configuring here.
F4000 remains frozen and dimension-compatible, with a new observation meaning
for the two retry entitlement slots. No old learning contract is relabelled.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from tools.control.yaw_admittance import YawSearchRecovery
from tools.learning.five_axis_observation import FiveAxisObservation

VERSION = 'noise50_yaw_on_time_budget_search_v1'
OBSERVATION_VERSION = 'five_axis_N2_30s_time_only_retry_permission_v1'
SPEEDS = {450: .00045, 900: .0009}


def _speed(search_speed_um_s):
    if type(search_speed_um_s) is not int or search_speed_um_s not in SPEEDS:
        raise ValueError('Registered 450 or 900 um/s search speed required')
    return SPEEDS[search_speed_um_s]


class TimeBudgetSearchRecovery(YawSearchRecovery):
    warning_only = True

    def search_count_exhausted(self):
        return False

    def metadata(self):
        return {**super().metadata(), 'retry_policy': 'time_only',
                'rotation_risk_policy': 'warning_only', 'effective_search_count_limit': None}


def make_controller(profile=None, *, search_speed_um_s=450):
    from .global_residual_session import make_controller as original
    speed = _speed(search_speed_um_s)
    old = original(profile)
    cfg = replace(old.config, spiral_speed_m_s=speed, search_xy_component_speed_m_s=speed)
    c = TimeBudgetSearchRecovery(cfg, old.risk_config, old.load_config, old.drive_config)
    c.admittance = old.admittance
    return c


def protocol_config(search_speed_um_s=450):
    from tools.model.layered_task import TASK_ID
    c = make_controller(search_speed_um_s=search_speed_um_s)
    return dict(version=VERSION, group=f'search_{search_speed_um_s}',
        observation_version=OBSERVATION_VERSION, observation_width=140,
        retry_policy='time_only', effective_max_searches=None, effective_max_recoveries=None,
        rotation_risk_policy='warning_only', passive_yaw_enabled=True,
        task_deadline_s=30., max_cycles=16000, control_period_s=.002, noise_hold_cycles=25,
        optimizer_updates=0, replay_publication=False,
        search_xy_limit_m_s=_speed(search_speed_um_s), controller_config=asdict(c.config),
        rotation_risk_config=asdict(c.risk_config), search_load_config=asdict(c.load_config),
        search_drive_config=asdict(c.drive_config), action_scale=[.0005]*4+[.005],
        retry_observation_semantics='slots searches_remaining/recoveries_remaining are 0/1 time-only permission; real counts retained in controller/environment evidence',
        task_referee=TASK_ID, source_policy='frozen_F4000',
        frozen_policy_compatibility='140D structure only; new budget-feature distribution unvalidated')


class TimeBudgetObservation(FiveAxisObservation):
    version = OBSERVATION_VERSION

    def capture(self, snapshot, context, *, refresh=False):
        vector, raw = super().capture(snapshot, context, refresh=refresh)
        allowed = float(snapshot.time_s < self.config.total_action_time_s - 1e-10)
        for name in ('searches_remaining', 'recoveries_remaining'):
            vector[self.slices[name]] = allowed
            raw[name] = [allowed]
            field = next(f for f in self.schema if f['name'] == name)
            field.update(scale=[1.], source='time_only_retry_permission')
        return vector, raw


def environment_class():
    from .consistent_sac_trial import environment_class as original
    Base = original()

    class TimeBudgetEnvironment(Base):
        retry_policy = 'time_only'

        def recovery_count_exhausted(self):
            return False

        def metadata(self):
            return {**super().metadata(), 'retry_policy': 'time_only',
                    'effective_recovery_count_limit': None}
    return TimeBudgetEnvironment


def session_class(search_speed_um_s=450):
    from .consistent_sac_trial import session_class as original
    speed = _speed(search_speed_um_s)
    Base = original(search_xy_limit_m_s=speed)

    class TimeBudgetSession(Base):
        def __init__(self, environment):
            if getattr(environment, 'retry_policy', None) != 'time_only':
                raise TypeError('The time-only recovery environment is required')
            super().__init__(environment)
            self.controller_factory = lambda: make_controller(environment.profile, search_speed_um_s=search_speed_um_s)
            self.contract = protocol_config(search_speed_um_s)

        def _reset_residual(self, case, seed):
            initial = super()._reset_residual(case, seed)
            self.observations = TimeBudgetObservation(initial.state, self.controller.config, self.env.profile)
            self._decorated_cache = None
            return self.prepare_cycle()

        def _resume_after_recovery(self):
            from tools.control.search_recovery import resume_after_recovery
            resume_after_recovery(self.env, self.controller.config.recovery_min_actual_m,
                                  unlimited_recoveries=True)

        def _rebase_permitted(self, count):
            return self.controller.search_count > 0

    return TimeBudgetSession


def verify_group_composition(log, observation, contract):
    """Audit composition using the registered group limit, never implicit 450."""
    from .global_residual_action import recompose_logged_command
    from tools.validation.run_global_residual_authority import verify_composition_log
    if (contract not in [protocol_config(v) for v in SPEEDS] or
            log.get('contract_version') != VERSION or log.get('profile') != 'G1'):
        raise ValueError('New time-budget composition contract required')
    _, expected = recompose_logged_command(log, search_xy_limit_m_s=contract['search_xy_limit_m_s'])
    verify_composition_log(log, expected, observation, contract['controller_config'])
    return True


def audit_archive(folder, reg, job, *, search_speed_um_s=450, source_trainer=None):
    """Use the full existing domain/source/stop auditor with explicit new rules."""
    from tools.validation.consistent_sac_audit import audit_archive as audit
    _speed(search_speed_um_s)
    return audit(folder, reg, job, source_trainer=source_trainer,
                 time_budget_group=search_speed_um_s)


def collect_episode(session, case, *, policy, seed=None, max_cycles=16000):
    """Quarantined zero-update capture; callers supply frozen held-noise policy.

    Uses the numerical capture kernel directly, never the old domain-admitting
    collector or trainer.collect(). Starting a run remains a separate action.
    """
    from .five_axis_collection import collect_episode as kernel, CollectionError
    contract = deepcopy(getattr(session, 'contract', None))
    groups = [protocol_config(v) for v in SPEEDS]
    if contract not in groups:
        raise ValueError('Collector requires the new time-budget session contract')
    if type(max_cycles) is not int or not 0 < max_cycles <= contract['max_cycles']:
        raise ValueError('Collection ceiling must be between 1 and 16000 cycles')

    def bind(raw):
        raw.update(version=VERSION, execution_contract=deepcopy(contract),
                   time_budget_protocol=deepcopy(contract), training_admitted=False,
                   valid_for_learning=False)
        raw.setdefault('observation_version', OBSERVATION_VERSION)
        return raw

    try:
        raw = kernel(session, case, policy=policy, seed=seed, max_cycles=max_cycles)
    except CollectionError as exc:
        bind(exc.archive)
        raise
    bind(raw)
    if session.contract != contract or raw['observation_version'] != OBSERVATION_VERSION:
        raw['error'] = 'Time-budget execution/observation contract changed'
        raise CollectionError(raw['error'], raw)
    return raw


if __name__ == '__main__':
    import json
    print(json.dumps(dict(configuration_only=True,
        groups=[protocol_config(v) for v in SPEEDS]), indent=2, allow_nan=False))
