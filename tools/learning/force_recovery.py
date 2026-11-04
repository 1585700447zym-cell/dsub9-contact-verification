"""Opt-in native force recovery, preserving cumulative physical evidence.

Six newtons is an uncalibrated 20% simulation overshoot ceiling, not a
replacement for the five-newton stop trigger or a hardware safety rating.
"""
from copy import deepcopy
import math
import numpy as np

VERSION = 'native_force_recovery_v1'
CONFIG = dict(trigger_force_N=5., fatal_force_N=6., max_over_force_s=.020,
              unload_force_N=.5, stable_hold_s=.1, min_actual_retraction_m=.00025,
              retract_speed_m_s=.0005, task_deadline_s=30., hardware_calibrated=False)
ACTIVE = ('UNLOADING', 'RETRACT', 'WAIT_RESUME')


class ForceRecoveryMixin:
    force_recovery_version = VERSION

    def _clear_facts(self):
        super()._clear_facts()
        self.force_recovery_events = []
        self.force_recovery_samples = []
        self.force_recovery_fatal_reasons = []
        self._force_stable_since = None
        self.force_deadline_reached = False

    @property
    def active_force_recovery(self):
        event = self.force_recovery_events[-1] if self.force_recovery_events else None
        return event if event and event['status'] in ACTIVE else None

    def force_recovery_evidence(self):
        return deepcopy(dict(version=VERSION, events=self.force_recovery_events,
            samples=self.force_recovery_samples, fatal_reasons=self.force_recovery_fatal_reasons,
            had_force_recovery=bool(self.force_recovery_events),
            force_recovery_count=len(self.force_recovery_events),
            completed_force_recovery_count=sum(e['status']=='COMPLETED' for e in self.force_recovery_events),
            peak_force_N=self.peaks.get('force_N', 0.)))

    def recovery_guard_clear(self):
        facts = self.guard_facts
        return (facts['simulation_valid'] and not facts['invalid_reasons'] and
                not facts['motion_reasons'] and not self.force_recovery_fatal_reasons and
                set(facts['contact_reasons']) <= {'FORCE_LIMIT'} and
                (('FORCE_LIMIT' not in facts['contact_reasons'] and self.peaks['force_N'] <= CONFIG['trigger_force_N'])
                 or bool(self.force_recovery_events)) and
                self.peaks['force_N'] <= CONFIG['fatal_force_N'])

    def active_guard_facts(self):
        """Return response/permission facts; never edit the historical facts."""
        facts = self.guard_facts
        if self.recovery_guard_clear():
            facts['contact_reasons'] = [r for r in facts['contact_reasons'] if r != 'FORCE_LIMIT']
        return facts

    def force_history_completed(self):
        return (self.recovery_guard_clear() and
                all(e['status']=='COMPLETED' for e in self.force_recovery_events))

    def _force_fatal(self, reasons):
        new = [r for r in reasons if r not in self.force_recovery_fatal_reasons]
        self.force_recovery_fatal_reasons.extend(new)
        event = self.active_force_recovery
        if event:
            event.update(status='FATAL', end_time_s=float(self.data.time), status_reason='+'.join(reasons))
        if self.phase not in ('STOPPING', 'TERMINAL'):
            self.stop('+'.join(reasons))
        elif new and self.phase != 'TERMINAL':
            self.events.append(dict(time_s=float(self.data.time), phase='STOPPING', reason='+'.join(new)))

    def abort_force_recovery(self, reason):
        event = self.active_force_recovery
        if event:
            event.update(status='ABORTED', end_time_s=float(self.data.time), status_reason=reason)
        self._force_stable_since = None

    def _terminate(self, reason):
        self._force_fatal([reason])
        return super()._terminate(reason)

    def _low_and_stable(self, row):
        c = self.config
        return (np.linalg.norm(row['contact_wrench_M'][:3]) <= CONFIG['unload_force_N'] and
                np.linalg.norm(row['contact_wrench_G'][3:]) <= c.stop_torque_Nm and
                row['penetration_m'] < c.stop_penetration_m and
                np.linalg.norm(row['velocity_world'][:3]) <= c.stopped_speed and
                np.linalg.norm(row['velocity_world'][3:]) <= c.stopped_angular_speed)

    def force_recovery_stable(self):
        if (not self.recovery_guard_clear() or not self._state_valid() or
                self.data.time >= CONFIG['task_deadline_s']-1e-10 or
                not self._low_and_stable(self.observe())):
            return False
        if self.active_force_recovery:
            return (self._force_stable_since is not None and
                    self.data.time-self._force_stable_since >= CONFIG['stable_hold_s']-1e-10)
        return self.force_history_completed()

    def _guard(self, row):
        self._facts['checked_substeps'] += 1
        found, new = self._collect(row, engine_valid=self._state_valid())
        force = float(np.linalg.norm(row['contact_wrench_M'][:3]))
        now = float(self.data.time)
        other = found['invalid_reasons'] + found['motion_reasons'] + [
            r for r in found['contact_reasons'] if r != 'FORCE_LIMIT']
        event = self.active_force_recovery
        if (force > CONFIG['trigger_force_N'] and event is None and
                (not self.force_recovery_events or not self.force_recovery_fatal_reasons)):
            eligible = (self.phase == 'RUNNING' and not other and not self.force_recovery_fatal_reasons
                        and now < CONFIG['task_deadline_s']-1e-10)
            event = dict(id=len(self.force_recovery_events)+1, trigger_time_s=now,
                peak_force_N=force, last_over_force_time_s=now, continuous_over_force_s=0.,
                first_under_force_time_s=None, unloaded_time_s=None, retract_start_time_s=None,
                retract_start_z_m=None, retracted_time_s=None, actual_retraction_m=None,
                resume_time_s=None, end_time_s=None, status='UNLOADING', status_reason=None,
                eligible=eligible, trigger_position_m=list(row['position_m']))
            self.force_recovery_events.append(event)
            self._force_stable_since = None
            if self.phase != 'STOPPING':
                self.stop('FORCE_LIMIT' if not other else '+'.join(['FORCE_LIMIT']+other))
            else:
                # Record a newly observed force fact during an existing stop,
                # without restarting that physical stop or dropping its cause.
                self.events.append(dict(time_s=now,phase='STOPPING',reason='FORCE_LIMIT'))
            self.raw_command[:] = 0.
            event['frozen_reference_qpos'] = self.reference.tolist()
            event['stopped_command_world'] = self.command.tolist()
            if not eligible:
                self._force_fatal(['FORCE_RECOVERY_NOT_ELIGIBLE']+other)
        if event and event['status'] in ACTIVE:
            event['peak_force_N'] = max(event['peak_force_N'], force)
            if force > CONFIG['fatal_force_N']:
                self._force_fatal(['FORCE_FATAL_CEILING'])
            elif force > CONFIG['trigger_force_N']:
                event['last_over_force_time_s'] = now
                if event['first_under_force_time_s'] is not None or event['status'] != 'UNLOADING':
                    self._force_fatal(['FORCE_RECURRENCE'])
                else:
                    event['continuous_over_force_s'] = now-event['trigger_time_s']
                    if event['continuous_over_force_s'] > CONFIG['max_over_force_s']+1e-10:
                        self._force_fatal(['FORCE_PERSISTENT'])
            elif event['first_under_force_time_s'] is None:
                event['first_under_force_time_s'] = now
        if other:
            self._force_fatal(other)
        if found['invalid_reasons']:
            self._terminate('+'.join(found['invalid_reasons']))
        elif self.phase != 'TERMINAL':
            if now >= CONFIG['task_deadline_s']-1e-10 and (self.phase in ('RUNNING','RETRACT') or self.active_force_recovery):
                self.force_deadline_reached = True
                self.abort_force_recovery('TIME_LIMIT')
                self.stop('TIME_LIMIT')
            event = self.active_force_recovery
            if event and event['status']=='RETRACT':
                actual = float(self.recovery_start[2]-self.data.qpos[2])
                event['actual_retraction_m'] = actual
                if actual >= CONFIG['min_actual_retraction_m']-1e-12:
                    self.stop('RECOVERY_DISTANCE_REACHED')
            event = self.active_force_recovery
            if event and event['status'] in ('UNLOADING','WAIT_RESUME') and self._low_and_stable(row):
                if self._force_stable_since is None:
                    self._force_stable_since = now
            else:
                self._force_stable_since = None
        if self.force_recovery_events:
            latest = self.force_recovery_events[-1]
            self.force_recovery_samples.append(dict(time_s=now, event_id=latest['id'], phase=self.phase,
                status=latest['status'], force_N=force,
                torque_G_Nm=float(np.linalg.norm(row['contact_wrench_G'][3:])),
                penetration_m=float(row['penetration_m']),
                linear_m_s=float(np.linalg.norm(row['velocity_world'][:3])),
                angular_rad_s=float(np.linalg.norm(row['velocity_world'][3:])),
                position_z_m=float(self.data.qpos[2]), reference_z_m=float(self.reference[2]),
                command_world=self.command.tolist()))

    def stop(self, reason='REQUESTED_STOP'):
        # The inherited integrator uses reference distance. Only this new
        # protocol requires physical displacement before accepting that event.
        if (reason == 'RECOVERY_DISTANCE_REACHED' and self.phase == 'RETRACT'
                and self.active_force_recovery is not None):
            if self.recovery_start[2]-self.data.qpos[2] < CONFIG['min_actual_retraction_m']-1e-12:
                return
            event = self.active_force_recovery
            if event:
                event.update(status='WAIT_RESUME', retracted_time_s=float(self.data.time),
                    actual_retraction_m=float(self.recovery_start[2]-self.data.qpos[2]))
            self._force_stable_since = None
        return super().stop(reason)

    def request_recovery(self):
        if not self.force_recovery_stable():
            raise RuntimeError('Force recovery requires valid low load and completed stable hold before deadline')
        from tools.dynamics.cartesian import CartesianEnvironment
        # Reuse all live velocity/load/travel/count checks. Only the historical
        # guard veto is replaced, after the explicit checks immediately above.
        CartesianEnvironment.request_recovery(self)
        event = self.active_force_recovery
        if event:
            event.update(status='RETRACT', unloaded_time_s=float(self.data.time),
                retract_start_time_s=float(self.data.time), retract_start_z_m=float(self.data.qpos[2]))
        self.raw_command[:] = 0.
        self._force_stable_since = None

    def resume_force_recovery(self, normal_min_actual_m=.0002):
        """Resume a verified mixed normal/force history, keeping every fact."""
        if not self.force_recovery_stable() or self.phase != 'STOPPING':
            raise RuntimeError('Recovery resume requires stable low load before deadline')
        events = self.events
        if type(self.recovery_count) is not int or self.recovery_count < 1 or len(events) != 4*self.recovery_count-1:
            raise RuntimeError('Recovery event history is incomplete')
        previous = -math.inf
        for i, e in enumerate(events):
            expected = (('B2_SEARCH_EXHAUSTED','FORCE_LIMIT'), ('RECOVERY_ACCEPTED',),
                        ('RECOVERY_DISTANCE_REACHED',), ('B2_RECOVERY_RESUMED',))[i%4]
            phase = ('STOPPING','RETRACT','STOPPING','RUNNING')[i%4]
            if (e.get('reason') not in expected or e.get('phase') != phase or
                    not isinstance(e.get('time_s'),(int,float)) or not math.isfinite(e['time_s']) or
                    not previous <= e['time_s'] <= self.data.time):
                raise RuntimeError('Recovery event history contains an unverified stop')
            previous = e['time_s']
            if e['reason']=='FORCE_LIMIT' and not any(
                    f['trigger_time_s']==e['time_s'] and f['eligible'] and f['status'] in ('COMPLETED','WAIT_RESUME')
                    for f in self.force_recovery_events):
                raise RuntimeError('Unverified historical force event')
        minimum = CONFIG['min_actual_retraction_m'] if self.active_force_recovery else normal_min_actual_m
        if (isinstance(minimum,bool) or not isinstance(minimum,(int,float)) or
                not math.isfinite(minimum) or minimum<=0 or self.recovery_start is None or
                self.recovery_start[2]-self.data.qpos[2] < minimum-1e-12 or
                not math.isclose(events[-2]['time_s'],self.recovery_start_time,abs_tol=1e-10,rel_tol=0)):
            raise RuntimeError('Actual recovery distance or native start is invalid')
        event = self.active_force_recovery
        if event:
            event.update(status='COMPLETED', resume_time_s=float(self.data.time), end_time_s=float(self.data.time))
        self.reference = self.data.qpos.copy(); self.command[:] = 0.; self.raw_command[:] = 0.
        self.phase = 'RUNNING'
        self.events.append(dict(time_s=float(self.data.time), phase='RUNNING', reason='B2_RECOVERY_RESUMED'))
        self._force_stable_since = None
