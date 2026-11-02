"""One bounded XY-search ablation on top of the unchanged V2 controller."""
from dataclasses import asdict, dataclass
import math
import numpy as np
from tools.control.search_exit_v2 import SearchRecoveryV2


@dataclass(frozen=True)
class ProbeConfig:
    pause_s: float = 1.
    resume_s: float = .1

    def __post_init__(self):
        if any(not math.isfinite(v) or v <= 0 for v in asdict(self).values()):
            raise ValueError('Probe durations must be positive and finite')


class SearchPauseProbe(SearchRecoveryV2):
    def __init__(self, config=None, exit_gate=None, probe=None):
        super().__init__(config, exit_gate)
        self.probe = probe or ProbeConfig()
        self.probe_start = None
        self.probe_closed = False
        self.probe_events = []
        self.probe_trace = []

    def command(self, obs, dt):
        theta_before = self.theta
        # Parent owns all guards, exit qualification, admittance and budgets.
        result = super().command(obs, dt)
        if self.phase != 'SEARCH' or not self.recovered_search:
            if self.probe_start is not None and not self.probe_closed:
                self.probe_events.append({'time_s': obs.time_s, 'event': 'XY_PROBE_ENDED_BY_PARENT',
                                          'phase': self.phase})
                self.probe_closed = True
            return result
        c = self.config
        delta = np.asarray(obs.displacement_m)-self.search_origin
        if self.probe_start is None:
            if delta[2] < c.search_exit_advance_m:
                return result
            self.probe_start = obs.time_s
            self.probe_events.append({'time_s': obs.time_s, 'event': 'XY_PROBE_START',
                                      'relative_search_advance_m': float(delta[2]),
                                      'episode_advance_m': float(obs.displacement_m[2])})
        elapsed = obs.time_s-self.probe_start
        if elapsed <= self.probe.pause_s+1e-10:
            gain = 0.
        elif elapsed >= self.probe.pause_s+self.probe.resume_s-1e-10:
            gain = 1.
        else:
            fraction = (elapsed-self.probe.pause_s)/self.probe.resume_s
            gain = fraction*fraction*(3-2*fraction)
        b = c.spiral_pitch_m/(2*math.pi)
        radius = b*theta_before
        rate = c.spiral_speed_m_s/math.hypot(radius, b)
        tangent = np.array([b*math.cos(theta_before)-radius*math.sin(theta_before),
                            b*math.sin(theta_before)+radius*math.cos(theta_before)])*rate
        target = radius*np.array([math.cos(theta_before), math.sin(theta_before)])
        extra = tangent+c.search_tracking_gain_s*(target-delta[:2])
        base = self.admittance.velocity[:2].copy()
        if gain < 1.:
            result[:2] = np.clip(base+gain*extra, -c.search_xy_component_speed_m_s,
                                 c.search_xy_component_speed_m_s)
        elif not self.probe_closed:
            self.probe_events.append({'time_s': obs.time_s, 'event': 'XY_SEARCH_FULLY_RESTORED'})
            self.probe_closed = True
        self.probe_trace.append({'input_time_s': obs.time_s, 'extra_xy_gain': gain,
                                 'theta_before_rad': theta_before, 'base_xy_m_s': base.tolist(),
                                 'extra_xy_m_s': extra.tolist(), 'command_world': result.tolist()})
        return result

    def metadata(self):
        result = super().metadata()
        result.update(name='B2_v2_bounded_xy_pause', probe=asdict(self.probe),
                      probe_trigger='recovered_search_advance_reaches_original_100um',
                      budget_rule='parent_time_theta_origin_and_exit_gate_unchanged',
                      xy_rule='clip(admittance_xy + gain * (spiral_tangent + tracking), original_cap)')
        return result
