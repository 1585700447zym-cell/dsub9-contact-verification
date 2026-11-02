"""Zero-update request-hold experiment and open-loop command diagnostics.

These are command contrasts under the recorded baseline, not counterfactual
physical trajectories. No data from this module is published to learning.
"""
import numpy as np
from .five_axis_action import _stage_limit, normalized_action
from .five_axis_contract import SCALE
from tools.dynamics.safety import limit_command

AXES = [0, 1, 3, 4, 5]
VELOCITY = np.array([.001]*3 + [.03]*3)
ACCELERATION = np.array([.005]*3 + [.3]*3)


class HeldRequests:
    def __init__(self, requests, *, hold_cycles):
        self.requests = np.asarray(requests, dtype=float).copy()
        if (self.requests.ndim != 2 or self.requests.shape[1] != 5
                or not np.isfinite(self.requests).all() or (abs(self.requests) > 1).any()
                or type(hold_cycles) is not int or hold_cycles not in (1, 10)):
            raise ValueError('Finite normalized stream and 1/10-cycle hold required')
        self.hold_cycles = hold_cycles
        self.reset()

    def reset(self):
        self.draws = 0; self.last_cycle = None; self.phase = None; self.remaining = 0
        self.value = np.zeros(5)

    def select(self, cycle, phase):
        # The collector invokes this only when enabled. Any skipped cycle is a
        # permission break, so an old request can never survive that break.
        if type(cycle) is not int or cycle < 0 or phase not in ('SEARCH', 'INSERT'):
            raise ValueError('Enabled SEARCH/INSERT cycle required')
        if (self.last_cycle is None or cycle != self.last_cycle + 1
                or phase != self.phase or self.remaining == 0):
            if self.draws >= len(self.requests):
                raise ValueError('Registered request stream exhausted')
            self.value = normalized_action(self.requests[self.draws])
            self.draws += 1; self.remaining = self.hold_cycles
        self.last_cycle = cycle; self.phase = phase; self.remaining -= 1
        return self.value.copy()


def command_metrics(rows):
    """Common ten-cycle windows, cut at permission/stage boundaries.

    The shadow uses its own previous zero-residual command. Actual and shadow
    references are checked; filtering makes the gain inadmissible for gating,
    rather than pretending the reference filter did not exist.
    """
    groups = {}
    def bucket(name):
        if name not in groups:
            groups[name] = dict(rows=0, requested=np.zeros(5), contrast=np.zeros(5),
                error=np.zeros(5), local=np.zeros(5), static_clip=np.zeros(5),
                near_cap=np.zeros(5))
        return groups[name]
    shadow = None; shadow_ref = None; phase = None; ticks = 0
    invalid_windows = set(); window = -1; active = 0
    for row in rows:
        if not row['action_active']:
            shadow = None; ticks = 0; phase = None
            continue
        log = row['action_log']; inputs = log['composition_inputs']
        stage = inputs['phase']; dt = row['dt']
        if abs(dt - .002) > 1e-12:
            raise ValueError('Registered 2 ms control required')
        if shadow is None or ticks == 10 or phase != stage:
            window += 1; ticks = 0; phase = stage
            shadow = np.asarray(inputs['previous_limited_command'], dtype=float)
            shadow_ref = (np.asarray(log['reference_xy_m'], dtype=float).copy()
                          if 'reference_xy_m' in log else None)
        base = np.asarray(inputs['base_command'], dtype=float)
        request = np.asarray(log['applied_residual'], dtype=float)
        actual = np.asarray(log['actual_end_limited_command'], dtype=float)
        target = np.clip(_stage_limit(base + request, stage), -VELOCITY, VELOCITY)
        shadow = limit_command(_stage_limit(base, stage), shadow, dt, VELOCITY, ACCELERATION)
        if log['reference_filter_fraction'] < 1.:
            invalid_windows.add(window)
        if shadow_ref is not None:
            shadow_ref += shadow[:2] * dt
            if np.linalg.norm(shadow_ref) > log['reference_radius_limit_m'] + 1e-12:
                invalid_windows.add(window)
        residual = request[AXES]
        local = np.asarray(log['effective_command_delta'])[AXES]
        caps = np.array(([.0005]*2 if stage == 'INSERT' else [.00045]*2) + [.02]*3)
        for name in ('all', stage):
            b = bucket(name); b['rows'] += 1
            b['requested'] += abs(residual) * dt
            b['contrast'] += abs((actual - shadow)[AXES]) * dt
            b['error'] += abs((actual - target)[AXES]) * dt
            b['local'] += abs(local) * dt
            b['static_clip'] += (abs((target - base - request)[AXES]) > 1e-15)
            b['near_cap'] += (caps - abs(base[AXES]) < np.asarray(SCALE))
        ticks += 1; active += 1
    def divide(numerator, denominator):
        # Below 1 pm or 1 prad of integrated request is uninformative.
        return [float(a / b) if b > 1e-12 else None for a, b in zip(numerator, denominator)]
    result = dict(gain_admissible=not invalid_windows,
                  inadmissible_reference_windows=len(invalid_windows),
                  windows=window + 1, active_cycles=active, window_s=.020)
    for name, b in groups.items():
        result[name] = dict(rows=b['rows'], gain=divide(b['contrast'], b['requested']),
            tracking_error=divide(b['error'], b['requested']),
            local_gain_auxiliary=divide(b['local'], b['requested']),
            requested_absolute_integral=b['requested'].tolist(),
            static_clip_fraction=(b['static_clip'] / b['rows']).tolist(),
            baseline_near_cap_fraction=(b['near_cap'] / b['rows']).tolist())
    return result
