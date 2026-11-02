"""Cycle-wise extraction of the frozen B2 runner, initially zero-residual only.

The compatibility session is a regression instrument, NOT a training admission.
Task-window completion is locked separately from the final two-second stop tail.
"""
from copy import deepcopy
import json
import numpy as np

from .runtime import ROOT, verify_runtime, active_package
from .types import CycleSnapshot, CycleResult


class EpisodeSession:
    def __init__(self, *, environment=None, controller_factory=None, finish_criteria=None, geometry_checker=None):
        verify_runtime(active_package())
        from tools.validation.run_b1_baseline import FINISH
        self.finish_criteria = deepcopy(FINISH if finish_criteria is None else finish_criteria)
        if (set(self.finish_criteria) != set(FINISH) or
                any(isinstance(v, bool) or not np.isfinite(v) or v <= 0 for v in self.finish_criteria.values())):
            raise ValueError('Complete finite positive finish criteria required')
        if geometry_checker is not None and not callable(geometry_checker):
            raise TypeError('geometry_checker must be callable')
        self.geometry_checker = geometry_checker
        from .environment import SampledCompatibilityEnvironment
        from tools.control.search_recovery import SearchRecovery, SearchConfig
        self.env = environment if environment is not None else SampledCompatibilityEnvironment()
        frozen = json.loads((ROOT / 'deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json').read_text(encoding='utf-8'))
        self.controller_factory = controller_factory or (lambda: SearchRecovery(SearchConfig(**frozen['config'])))
        self._cache = None
        self._ready = False
        self.done = True

    def reset(self, case, seed=None):
        self._ready = False
        self._cache = None
        self.done = self.task_finished = True
        try:
            return self._reset(case, seed)
        except Exception:
            self._ready = False
            self._cache = None
            self.done = self.task_finished = True
            raise

    def _reset(self, case, seed):
        self.env.reset(case)
        self.case, self.seed = case, seed
        self.controller = self.controller_factory()
        self.initial = np.array(self.env.observe()['position_m'])
        self.reason = self.stop_time = self.hold_start = None
        self.recovery_state = self.wait_start = None
        self.guard_latched = False
        self.task_finished = self.done = False
        self.task_end_time = None
        self.cycle_id = 0
        self._cache = None
        self.initial_trace_row = self._trace_row(self.env.observe())
        self._ready = True
        return self.prepare_cycle()

    def _finish(self, reason):
        self.reason = reason
        self.stop_time = float(self.env.data.time)
        self.recovery_state = None
        if self.env.phase not in ('TERMINAL', 'STOPPING'):
            self.env.stop(reason)

    def _trace_row(self, row):
        c = self.controller
        return deepcopy(dict(row, policy_phase=c.phase, search_count=c.search_count,
                             spiral_theta_rad=c.theta,
                             admittance_velocity=c.admittance.velocity.tolist(),
                             commanded_correction=c.admittance.offset.tolist(),
                             recovery_state=self.recovery_state))

    def controller_state_snapshot(self):
        c = self.controller
        return deepcopy(dict(phase=c.phase, reason=c.reason, history=list(c.history),
                             phase_start=c.phase_start, theta=c.theta, search_count=c.search_count,
                             search_origin=None if c.search_origin is None else c.search_origin.tolist(),
                             admittance_velocity=c.admittance.velocity.tolist(),
                             admittance_offset=c.admittance.offset.tolist(), events=c.events))

    def policy_observation(self, row):
        from tools.validation.run_b2_search import policy_observation
        return policy_observation(row, self.initial)

    def completion_ready(self, row):
        from tools.validation.run_b1_baseline import geometric_finish
        return geometric_finish(row, criteria=self.finish_criteria)

    def prepare_cycle(self):
        if not self._ready:
            raise RuntimeError('A successful reset is required')
        if self._cache is not None:
            return deepcopy(self._cache)
        from tools.validation.run_b2_search import stable_for_recovery
        from tools.control.search_recovery import resume_after_recovery
        e, c = self.env, self.controller.config
        row = e.observe()
        obs = self.policy_observation(row)
        command = np.zeros(6)
        if not self.task_finished and not self.done:
            if e.phase == 'TERMINAL':
                self.reason = e.events[-1]['reason']
                self.task_finished = self.done = True
            if self.reason is None and row['time_s'] >= c.total_action_time_s - 1e-10:
                self._finish('TIME_LIMIT')
            if self.reason is None:
                if self.recovery_state == 'WAIT_STOP':
                    if stable_for_recovery(e):
                        try:
                            e.request_recovery()
                            self.recovery_state = 'RETRACT'
                        except RuntimeError:
                            self._finish('RECOVERY_REJECTED')
                    elif row['time_s'] - self.wait_start >= c.wait_stable_s:
                        self._finish('RECOVERY_NOT_STABLE')
                elif self.recovery_state == 'WAIT_RESUME':
                    if stable_for_recovery(e):
                        try:
                            resume_after_recovery(e, c.recovery_min_actual_m)
                            # Recovery resets actuator reference/command; adapters
                            # that expose that state need a fresh observation.
                            obs = self.policy_observation(e.observe())
                            self.controller.start_recovered_search(obs)
                            self.recovery_state = None
                        except RuntimeError:
                            self._finish('RECOVERY_RESUME_REJECTED')
                    elif row['time_s'] - self.wait_start >= c.wait_stable_s:
                        self._finish('RECOVERY_NOT_STABLE')
                if self.recovery_state is None and self.reason is None:
                    command = self.controller.command(obs, e.config.control_period)
                    if self.controller.phase == 'FAILED':
                        self._finish(self.controller.reason)
                    elif self.controller.phase == 'WAIT_RECOVERY':
                        e.stop('B2_SEARCH_EXHAUSTED')
                        self.recovery_state, self.wait_start = 'WAIT_STOP', row['time_s']
        # A rejected recovery can itself terminate the live engine. Preserve that
        # invalid reason instead of exposing a still-active RECOVERY_REJECTED cache.
        if e.phase == 'TERMINAL':
            self.reason = e.events[-1]['reason']
            self.task_finished = self.done = True
            self.task_end_time = float(e.data.time)
            self.recovery_state = None
        active = (self.controller.phase in ('INSERT', 'SEARCH') and e.phase == 'RUNNING'
                  and self.reason is None and not self.guard_latched and not self.done)
        self._cache = CycleSnapshot(self.cycle_id, float(e.data.time), command.tolist(), active,
                                    deepcopy(e.observe()), self.controller_state_snapshot())
        return deepcopy(self._cache)

    def observe(self):
        if not self._ready or self._cache is None:
            raise RuntimeError('Reset and prepare before observing')
        return deepcopy(self._cache)

    def _post_task_cycle(self, row):
        from tools.control.search_recovery import latched_contact_guard
        FINISH = self.finish_criteria
        e, c = self.env, self.controller.config
        if e.phase == 'TERMINAL':
            self.reason = e.events[-1]['reason']
            self.task_finished = True
            return
        guard_reason = latched_contact_guard(e)
        if guard_reason and not self.guard_latched:
            self.guard_latched = True
            e.events.append(dict(time_s=row['time_s'], reason='B2_LATCHED_' + guard_reason, phase=e.phase))
            self._finish(guard_reason)
        if self.reason is None and e.phase == 'STOPPING':
            why = e.events[-1]['reason']
            if self.recovery_state == 'RETRACT' and why == 'RECOVERY_DISTANCE_REACHED':
                self.recovery_state, self.wait_start = 'WAIT_RESUME', row['time_s']
            elif self.recovery_state in ('WAIT_STOP', 'WAIT_RESUME') and why in ('B2_SEARCH_EXHAUSTED', 'RECOVERY_DISTANCE_REACHED'):
                pass
            else:
                self._finish(why)
        if self.reason is None and e.phase == 'RUNNING' and row['position_m'][2] >= -10e-6:
            self._finish('TARGET_PLANE_REACHED')
        if self.reason is not None:
            peaks_ok = (e.peaks['force_N'] < FINISH['force_N'] and e.peaks['torque_G_Nm'] < FINISH['torque_Nm']
                        and e.peaks['penetration_m'] < FINISH['penetration_m'])
            if (self.reason == 'TARGET_PLANE_REACHED' and self.completion_ready(row) and peaks_ok
                    and (self.geometry_checker is None or self.geometry_checker(row))):
                if self.hold_start is None:
                    self.hold_start = row['time_s']
                if row['time_s'] - self.hold_start >= FINISH['hold_s'] - 1e-12:
                    self.reason, self.task_finished = 'GEOMETRIC_SUCCESS', True
                    return
            else:
                self.hold_start = None
            if row['time_s'] - self.stop_time >= c.settle_time_s - 1e-10:
                if self.reason == 'TARGET_PLANE_REACHED':
                    self.reason = 'TARGET_POSE_NOT_SETTLED'
                self.task_finished = True

    def _validate_action(self, action4):
        action = np.asarray(action4, dtype=float)
        if action.shape != (4,) or not np.isfinite(action).all() or np.any(action != 0):
            raise ValueError('Compatibility session accepts finite shape4 zero residual only')
        return action

    def _command_for_action(self, snapshot, action):
        return snapshot.base_command

    def advance_cycle(self, action4):
        if not self._ready:
            raise RuntimeError('A successful reset is required')
        if self.done:
            raise RuntimeError('Episode already ended')
        action = self._validate_action(action4)
        snapshot = self.prepare_cycle()
        if self.done:
            raise RuntimeError('Episode already ended')
        command = self._command_for_action(snapshot, action)
        event_start = len(self.env.events)
        if hasattr(self.env, 'begin_cycle'):
            self.env.begin_cycle()
        row = self.env.step(command)
        # Frozen runner records BEFORE post-step decisions and next preparation.
        trace_row = self._trace_row(row)
        if not self.task_finished:
            self._post_task_cycle(row)
            if self.task_finished:
                self.task_end_time = float(self.env.data.time)
        from tools.validation.native313_matrix_audit import actual_stop_start
        start = actual_stop_start(self.env.events, self.stop_time)
        self.done = (self.env.phase == 'TERMINAL' or
                     (self.task_finished and start is not None and self.env.data.time >= start + 2. - 1e-10))
        self.cycle_id += 1
        self._cache = None
        next_snapshot = self.prepare_cycle()
        return CycleResult(next_snapshot, trace_row, float(self.env.data.time) - snapshot.time_s,
                           deepcopy(self.env.events[event_start:]), self.task_finished, self.done,
                           list(row['limited_command_world']),
                           deepcopy(getattr(self.env, 'cycle_peaks', {})))
