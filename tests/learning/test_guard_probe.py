"""A real integrated boundary trial, separate from synthetic guard logic."""
def test_rotation_probe_crosses_boundary_and_audits_actual_stop(runtime):
    from tools.validation.verify_guard_candidate import run_probe
    report = run_probe('free_roll_pos')
    assert report['simulation_valid'] is True
    assert report['physical_stopped'] is True
    assert report['expected_event_observed'] is True
    assert report['guard_facts']['motion_reasons'] == ['ROTATION_LIMIT']
    assert report['guard_facts']['contact_reasons'] == []
    assert 2.5 < report['max_rotation_deg'] < 2.6
    assert report['guard_facts']['checked_substeps'] == report['physical_steps']
    assert report['end_time_s'] >= report['actual_stop_start_s'] + 2 - 1e-9
    assert report['training_admitted'] is False
    assert report['trace'] and report['physical_stop_samples']
