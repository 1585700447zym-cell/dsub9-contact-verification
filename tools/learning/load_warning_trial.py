"""900 µm/s, 30 s protocol with native force and SO(3) warnings."""
from copy import deepcopy
from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from . import time_budget_trial as previous


VERSION = 'nano100_yaw_on_load_warning_900_v1'
OBSERVATION_VERSION = 'five_axis_N2_30s_load_warning_permission_v1'
WARNING_VERSION = 'native_load_warnings_v1'
GUARD_SOURCE = 'active_hard_guards_excluding_native_force_and_rotation_warnings'
TASK_REFEREE = 'dsub9_clearance120_layered_nano100_v6'
REFERENCE_TARGET_M = .000300
NOMINAL_ACTUAL_M = .000250
DISTANCE_TOLERANCE_M = .000001
MIN_ACTUAL_M = .000249
DEADLINE_S = 30.
WARNINGS = {
    'FORCE_GT5_N': ('force_N', 5.),
    'FORCE_GT6_N': ('force_N', 6.),
    'ROTATION_GT2P5_DEG': ('rotation_rad', math.radians(2.5)),
}


def _speed(value):
    if type(value) is not int or value != 900:
        raise ValueError('Only the registered 900 µm/s group is available')


def make_controller(profile=None, *, search_speed_um_s=900):
    _speed(search_speed_um_s)
    controller = previous.make_controller(profile, search_speed_um_s=900)
    controller.config = replace(controller.config, recovery_min_actual_m=MIN_ACTUAL_M)
    return controller


def protocol_config(search_speed_um_s=900):
    """Read the registered settings without loading MuJoCo, a policy or an env."""
    _speed(search_speed_um_s)
    root = Path(__file__).resolve().parents[2]
    source = root/'deliverables/learning_chain/time_budget_search_20261103/search_900.json'
    raw = source.read_bytes()
    if hashlib.sha256(raw).hexdigest() != '15c0f0f8399092ffb4e6ced5bbc32450ac00390d799e8b3fb4cf91e270c7b84f':
        raise ValueError('Registered base 900 settings changed')
    contract = json.loads(raw)
    contract['controller_config']['recovery_min_actual_m'] = MIN_ACTUAL_M
    contract.update(version=VERSION, observation_version=OBSERVATION_VERSION, task_referee=TASK_REFEREE,
        guard_observation_semantics=GUARD_SOURCE,
        load_warning=dict(version=WARNING_VERSION, force_warning_N=[5.,6.],
            rotation_warning_rad=math.radians(2.5), force_success_gate=False,
            recovery_reference_target_m=REFERENCE_TARGET_M,
            recovery_min_actual_m=NOMINAL_ACTUAL_M, recovery_distance_tolerance_m=DISTANCE_TOLERANCE_M,
            recovery_effective_min_actual_m=MIN_ACTUAL_M,
            duration_method='native samples times timestep', angular_reference='rotation from episode start'))
    return contract


def blocking_facts(facts):
    """Preserve historical observations; return just the blockers for this protocol."""
    result = deepcopy(facts)
    result['contact_reasons'] = [r for r in facts['contact_reasons'] if r != 'FORCE_LIMIT']
    result['motion_reasons'] = [r for r in facts['motion_reasons'] if r != 'ROTATION_LIMIT']
    return result


def _exposure():
    return dict(samples=0, duration_s=0., integral_force_Ns=0., square_integral_force_N2s=0.)


def summarize_warnings(samples, *, timestep_s=.0002, task_end_time_s=None, checked_substeps=None):
    """Integrate all native loads and count contiguous threshold crossings."""
    exposure = {key: _exposure() for key in ('all', 'task', 'audit_tail')}
    metrics = {key: dict(samples=0, episodes=0, duration_s=0., peak=0., excess_integral=0.)
               for key in WARNINGS}
    events, active = [], {}
    peak_force = peak_rotation = 0.
    for row in samples:
        now, force = row['time_s'], row['force_N']
        peak_force = max(peak_force, force)
        peak_rotation = max(peak_rotation, row['rotation_rad'])
        stage = 'task' if task_end_time_s is None or now <= task_end_time_s+1e-10 else 'audit_tail'
        for key in ('all',stage):
            bucket = exposure[key]
            bucket['samples'] += 1
            bucket['integral_force_Ns'] += force*timestep_s
            bucket['square_integral_force_N2s'] += force*force*timestep_s
        for reason, (field, threshold) in WARNINGS.items():
            value = row[field]
            if not value > threshold:
                active.pop(reason, None)
                continue
            metric = metrics[reason]
            if reason not in active:
                active[reason] = dict(reason=reason, start_time_s=now, samples=0, peak=0., excess_integral=0.)
                events.append(active[reason])
                metric['episodes'] += 1
            event = active[reason]
            event['last_time_s'] = now
            for bucket in (event,metric):
                bucket['samples'] += 1
                bucket['duration_s'] = bucket['samples']*timestep_s
                bucket['peak'] = max(bucket['peak'],value)
                bucket['excess_integral'] += (value-threshold)*timestep_s
    for bucket in exposure.values():
        bucket['duration_s'] = bucket['samples']*timestep_s
    return dict(version=WARNING_VERSION, checked_substeps=len(samples) if checked_substeps is None else checked_substeps,
        timestep_s=timestep_s, task_end_time_s=task_end_time_s,
        peak_force_N=peak_force, peak_rotation_rad=peak_rotation,
        samples=samples, events=events, metrics=metrics, exposure=exposure)


def environment_class():
    from tools.control.search_recovery import _completed_recovery_segments
    from tools.dynamics.cartesian import CartesianEnvironment
    from .guarded_environment import relative_rotation_rad

    class LoadWarningEnvironment(previous.environment_class()):
        load_warning_version = WARNING_VERSION

        def __init__(self, profile=None):
            super().__init__(profile)
            self.config = replace(self.config, recovery_distance_m=REFERENCE_TARGET_M)

        def _clear_facts(self):
            super()._clear_facts()
            self.warning_samples = []

        def active_guard_facts(self):
            return blocking_facts(self.guard_facts)

        def _collect(self, row, *, engine_valid):
            # The parent first records every fact in its historical guard ledger.
            found, new = super()._collect(row, engine_valid=engine_valid)
            return blocking_facts(found), [r for r in new if r not in ('FORCE_LIMIT','ROTATION_LIMIT')]

        def _guard(self, row):
            try:
                angle = relative_rotation_rad(self.initial[3:], row['quaternion_wxyz'])
            except ValueError:
                angle = math.nan  # Parent retains INVALID_QUATERNION / NONFINITE_OBSERVATION.
            sample = dict(time_s=float(self.data.time), phase=self.phase,
                force_N=float(np.linalg.norm(row['contact_wrench_M'][:3])), rotation_rad=angle,
                torque_G_Nm=float(np.linalg.norm(row['contact_wrench_G'][3:])),
                penetration_m=float(row['penetration_m']), position_z_m=float(self.data.qpos[2]),
                reference_z_m=float(self.reference[2]),
                linear_m_s=float(np.linalg.norm(row['velocity_world'][:3])),
                angular_rad_s=float(np.linalg.norm(row['velocity_world'][3:])))
            self.warning_samples.append(sample)
            super()._guard(row)
            if self.phase != 'TERMINAL' and not all(math.isfinite(v) for k,v in sample.items() if k != 'phase'):
                self._terminate('NONFINITE_NATIVE_MEASUREMENT')
            if self.phase in ('RUNNING','RETRACT') and self.data.time >= DEADLINE_S-1e-10:
                self.stop('TIME_LIMIT')

        def latched_hard_contact(self):
            c = self.config
            reasons = [reason for key, limit, reason in (
                ('torque_G_Nm',c.stop_torque_Nm,'TORQUE_LIMIT'),
                ('penetration_m',c.stop_penetration_m,'PENETRATION_LIMIT'))
                if self.peaks[key] > limit]
            return '+'.join(reasons) if reasons else None

        def ready_for_normal_recovery(self):
            facts, c, row = self.active_guard_facts(), self.config, self.observe()
            return (self._state_valid() and self.phase == 'STOPPING' and self.data.time < DEADLINE_S-1e-10
                and facts['simulation_valid'] and not any(facts[k] for k in ('invalid_reasons','motion_reasons','contact_reasons'))
                and not self.latched_hard_contact()
                and np.linalg.norm(row['velocity_world'][:3]) <= c.stopped_speed
                and np.linalg.norm(row['velocity_world'][3:]) <= c.stopped_angular_speed
                and np.linalg.norm(row['contact_wrench_M'][:3]) <= c.recovery_force_N
                and np.linalg.norm(row['contact_wrench_G'][3:]) <= c.stop_torque_Nm
                and row['penetration_m'] < c.stop_penetration_m)

        def request_recovery(self):
            if not self.ready_for_normal_recovery():
                raise RuntimeError('Normal recovery requires the existing low-load, speed and safety conditions')
            # This retains the native travel/count checks, along with the original stop and retract events.
            CartesianEnvironment.request_recovery(self)

        def resume_normal_recovery(self):
            # The normal-segment auditor reads only these fields. Give it the
            # effective blockers; facts, events, peaks, pose and clock stay live.
            view = SimpleNamespace(events=self.events,recovery_count=self.recovery_count,
                guard_facts=self.active_guard_facts(),data=self.data,
                recovery_start_time=getattr(self,'recovery_start_time',None))
            if (not self.ready_for_normal_recovery() or not _completed_recovery_segments(view)
                    or self.recovery_start is None
                    or self.recovery_start[2]-self.data.qpos[2] < MIN_ACTUAL_M-1e-15):
                raise RuntimeError('Normal recovery distance, stability or event history is insufficient')
            self.reference = self.data.qpos.copy()
            self.command[:] = 0.; self.raw_command[:] = 0.
            self.phase = 'RUNNING'
            self.events.append(dict(time_s=float(self.data.time),phase='RUNNING',reason='B2_RECOVERY_RESUMED'))

        def metadata(self):
            return {**super().metadata(),'load_warning':protocol_config()['load_warning']}

    return LoadWarningEnvironment


class LoadWarningObservation(previous.TimeBudgetObservation):
    version = OBSERVATION_VERSION

    def __init__(self, initial, config, profile, environment):
        super().__init__(initial,config,profile)
        self.environment = environment

    def capture(self, snapshot, context, *, refresh=False):
        context = dict(context,guard_facts=self.environment.active_guard_facts())
        vector, raw = super().capture(snapshot,context,refresh=refresh)
        next(field for field in self.schema if field['name']=='latched_guards')['source'] = GUARD_SOURCE
        return vector, raw


def session_class(search_speed_um_s=900):
    _speed(search_speed_um_s)
    from tools.model.layered_task import TASK_ID, functional_finish

    class LoadWarningSession(previous.session_class(900)):
        def __init__(self, environment):
            if getattr(environment,'load_warning_version',None) != WARNING_VERSION:
                raise TypeError('Registered native load warning environment required')
            settings = dict(control_period=.002,timestep=.0002,stop_force_N=5.,
                stop_torque_Nm=.1,stop_penetration_m=.00003,recovery_force_N=.5,
                recovery_distance_m=REFERENCE_TARGET_M,recovery_speed=.0005)
            if (TASK_ID != TASK_REFEREE or
                    environment.guard_config.max_rotation_from_start_rad != math.radians(2.5) or
                    any(getattr(environment.config,k) != v for k,v in settings.items())):
                raise ValueError('Registered 900 warning, recovery and referee settings required')
            super().__init__(environment)
            self.contract = protocol_config(900)
            self.controller_factory = lambda: make_controller(environment.profile)

        def _reset_residual(self, case, seed):
            initial = super()._reset_residual(case,seed)
            self.observations = LoadWarningObservation(initial.state,self.controller.config,self.env.profile,self.env)
            self._decorated_cache = None
            return self.prepare_cycle()

        def _guard_failure_facts(self):
            return self.env.active_guard_facts()

        def _latched_guard_reason(self):
            return self.env.latched_hard_contact()

        def _finish_peaks_ok(self, row):
            e, f = self.env, self.finish_criteria
            return e.peaks['torque_G_Nm'] < f['torque_Nm'] and e.peaks['penetration_m'] < f['penetration_m']

        def completion_ready(self, row):
            return functional_finish(row,self.finish_criteria,force_warning_only=True)

        def _stable_for_recovery(self):
            return self.env.ready_for_normal_recovery()

        def _resume_after_recovery(self):
            self.env.resume_normal_recovery()

        def _finish(self, reason):
            e = self.env
            if self.stop_time is None and self.recovery_state and e.phase=='STOPPING':
                # Use the first event of the current continuous physical stop,
                # even when more guard facts were recorded while already stopped.
                origin = None
                for event in reversed(e.events):
                    if event.get('phase') is None:
                        continue
                    if event['phase'] != 'STOPPING':
                        break
                    origin = event
                if (origin and origin['reason'] in ('B2_SEARCH_EXHAUSTED','RECOVERY_DISTANCE_REACHED')
                        and e.data.time-origin['time_s'] > 1e-8):
                    e.events.append(dict(time_s=float(e.data.time),phase='STOPPING',
                        reason='RECOVERY_FINAL_AUDIT_START',physical_stop_preserved=True,
                        recovery_kind='normal',physical_stop_time_s=origin['time_s'],recovery_count=e.recovery_count,
                        force_recovery_id=None,decision_reason=reason))
            return super()._finish(reason)

    return LoadWarningSession


def receipt_fields(session):
    from .episode_buffer import _safe_error_archive
    e = session.env
    record = summarize_warnings(e.warning_samples,timestep_s=e.config.timestep,
        task_end_time_s=getattr(session,'task_end_time',None),checked_substeps=e.guard_facts['checked_substeps'])
    return _safe_error_archive(dict(load_warnings=record,cumulative_peaks=e.peaks))


if __name__ == '__main__':
    print(json.dumps(dict(configuration_only=True,groups=[protocol_config()]),indent=2,allow_nan=False))
