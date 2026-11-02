"""Versioned 140-observation/5-action Stage A interface; no execution grant."""
from copy import deepcopy
import math
import numpy as np

VERSION = 'five_axis_sac_N2_450_v1'
OBSERVATION_VERSION = 'five_axis_short_history_N2_v1'
WIDTH = 140
ACTION_DIM = 5
SCALE = (.00005, .00005, .0005, .0005, .0005)
# The legacy 137 fields retain their order. Only necessary yaw state is added.
_LAYOUT = '''wrench_history_M:24 relative_position_m:3 relative_rotation_world_rad:3
velocity_world:6 maximum_advance_m:1 base_command:6 previous_limited_command:6
previous_residual:4 policy_phase:5 physical_phase:4 recovery_phase:4 decision:9
pending:1 action_active:1 simulation_valid:1 latched_guards:7 invalid_latched:1
total_budget_remaining_s:1 search_budget_remaining_s:1 search_budget_valid:1
searches_remaining:1 recoveries_remaining:1 admittance_velocity:4 admittance_offset:4
spiral_theta_rad:1 search_origin_m:3 search_origin_valid:1 stall_progress_m:1
stall_span_s:1 stall_valid:1 phase_elapsed_s:1 hold_elapsed_s:1 hold_valid:1
stop_elapsed_s:1 stop_valid:1 wait_elapsed_s:1 wait_valid:1 reference_position_error_m:3
reference_rotation_error_world_rad:3 relative_drive_reference_m:3 search_reference_xy_m:2
search_reference_valid:1 episode_peak_z_m:1 episode_peak_valid:1 net_search_remaining_m:1
net_search_valid:1 rotation_risk_elapsed_s:1 rotation_risk_valid:1 search_load_elapsed_s:1
search_load_valid:1 admittance_xy_rebase_count:1 reference_release_pending:1
previous_reference_filter_fraction:1 previous_yaw_residual:1 yaw_admittance_velocity:1
yaw_admittance_offset:1'''


def field_slices():
    result = {}; offset = 0
    for token in _LAYOUT.split():
        name, width = token.split(':'); width = int(width)
        result[name] = slice(offset, offset + width); offset += width
    assert offset == WIDTH
    return result


def permissions(observations):
    values = np.asarray(observations)
    if (values.ndim != 2 or values.shape[1] != WIDTH or not len(values) or
            values.dtype.kind not in 'iuf' or not np.isfinite(values).all() or (abs(values) > 10).any()):
        raise ValueError('Finite bounded 140D observations required')
    fields = field_slices()
    for name in ('policy_phase', 'physical_phase', 'recovery_phase', 'decision'):
        block = values[:, fields[name]]
        if not np.isin(block, (0., 1.)).all() or not (block.sum(axis=1) == 1).all():
            raise ValueError('Invalid one-hot: ' + name)
    for name, span in fields.items():
        if name.endswith('_valid') or name in ('pending', 'action_active', 'simulation_valid',
                'invalid_latched', 'latched_guards', 'reference_release_pending'):
            if not np.isin(values[:, span], (0., 1.)).all():
                raise ValueError('Invalid boolean: ' + name)
    pending = values[:, fields['pending']][:, 0].astype(bool)
    if np.any(pending != (values[:, fields['decision']][:, 0] == 0)):
        raise ValueError('Decision/pending mismatch')
    phase = values[:, fields['policy_phase']].argmax(axis=1)
    expected = np.isin(phase, (0, 2)) & (values[:, fields['physical_phase']][:, 0] == 1) & ~pending
    expected &= values[:, fields['simulation_valid']][:, 0] == 1
    expected &= ~values[:, fields['latched_guards']].any(axis=1)
    expected &= ~values[:, fields['invalid_latched']].any(axis=1)
    if np.any(values[:, fields['action_active']][:, 0] != expected):
        raise ValueError('Same-cycle residual permission mismatch')
    return expected


def permission(observation):
    values = np.asarray(observation)
    if values.shape != (WIDTH,):
        raise ValueError('140D single observation required')
    return bool(permissions(values[None])[0])


def learning_config():
    return dict(version=VERSION, observation_version=OBSERVATION_VERSION, width=WIDTH,
        action_dim=ACTION_DIM, action_scale=list(SCALE), mode='F5', control_period_s=.002,
        policy_period_s=.002, learning=dict(learning_rate=.0003, actor_learning_rate=.0003,
            batch_size=256, replay_capacity=116000, network=[256, 256], seed=2026092716,
            torch_threads=1, device='cpu', entropy_initial=.01, target_entropy=-5., tau=.005,
            exact_terminal_tail=False, critic_boundary_rows=0), discount_time_constant_s=10.)


def validate_config(config):
    expected = learning_config()
    if not isinstance(config, dict) or config.keys() != expected.keys():
        raise ValueError('Complete five-axis configuration required')
    for key in expected.keys() - {'learning'}:
        if config[key] != expected[key]:
            raise ValueError('Five-axis interface mismatch: ' + key)
    settings = config['learning']
    if not isinstance(settings, dict) or settings.keys() != expected['learning'].keys():
        raise ValueError('Complete learning settings required')
    for key in ('target_entropy', 'exact_terminal_tail', 'critic_boundary_rows', 'device'):
        if settings[key] != expected['learning'][key]:
            raise ValueError('Ordinary five-axis SAC required: ' + key)
    for key in ('learning_rate', 'actor_learning_rate', 'entropy_initial', 'tau'):
        value = settings[key]
        if type(value) not in (float, int) or not math.isfinite(value) or value <= 0:
            raise ValueError('Positive finite setting: ' + key)
    if settings['tau'] > 1:
        raise ValueError('Target interpolation must be <=1')
    for key in ('batch_size', 'replay_capacity', 'torch_threads', 'seed'):
        if type(settings[key]) is not int or settings[key] < (0 if key == 'seed' else 1):
            raise ValueError('Invalid integer setting: ' + key)
    if (not isinstance(settings['network'], list) or not settings['network'] or
            any(type(width) is not int or width <= 0 for width in settings['network'])):
        raise ValueError('Positive network widths required')
    return deepcopy(config)
