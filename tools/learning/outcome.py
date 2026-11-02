"""Independent facts and v3 adjudication; never infer validity from one reason."""


def classify_outcome(*, simulation_valid: bool, contact_guard: bool,
                     motion_violation: bool, full_success: bool,
                     physical_stopped: bool) -> dict:
    if not simulation_valid:
        category = 'INVALID_SIMULATION'
    elif contact_guard:
        category = 'CONTACT_GUARD'
    elif motion_violation:
        category = 'MOTION_VIOLATION'
    elif not physical_stopped:
        category = 'STOP_NOT_QUALIFIED'
    elif full_success:
        category = 'FULL_SUCCESS'
    else:
        category = 'TASK_FAILURE'
    return dict(simulation_valid=bool(simulation_valid), task_outcome=category,
                guard_violations={'contact': bool(contact_guard), 'motion': bool(motion_violation)},
                physical_stopped=bool(physical_stopped),
                valid_for_learning=bool(simulation_valid and physical_stopped))
