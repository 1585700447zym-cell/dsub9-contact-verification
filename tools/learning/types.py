"""Detached, serializable snapshots; privileged state is explicitly separate."""
from dataclasses import dataclass, field


@dataclass
class CycleSnapshot:
    cycle_id: int
    time_s: float
    base_command: list
    residual_enabled: bool
    state: dict
    controller_state: dict
    policy_observation: list = field(default_factory=list)
    privileged_evaluation: dict = field(default_factory=dict)
    policy_raw: dict = field(default_factory=dict)


@dataclass
class CycleResult:
    next_snapshot: CycleSnapshot
    trace_row: dict
    dt: float
    events: list
    task_finished: bool
    done: bool
    executed_command: list
    cycle_peaks: dict = field(default_factory=dict)
    reward_terms: dict = field(default_factory=dict)
    outcome: dict = field(default_factory=dict)
    action_log: dict = field(default_factory=dict)
