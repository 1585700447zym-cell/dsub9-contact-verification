import importlib
import pytest


def module():
    spec=importlib.util.find_spec('tools.validation.run_readiness_candidate')
    assert spec is not None, 'Frozen seven-case candidate entry is missing'
    return importlib.import_module(spec.name)


def test_failed_or_incomplete_gate_prevents_candidate():
    m=module()
    for gate in ({'status':'RUNNING'}, {'status':'COMPLETE','verdict':'BLOCKED_REQUIRES_REVIEW'}):
        with pytest.raises(ValueError,match='numerical'):m.require_gate(gate)


def test_candidate_keeps_original_budgets_and_same_config_for_all_cases():
    m=module(); c=m.controller()
    assert c.probe.pause_s==2 and c.probe.resume_s==.1
    assert c.config.total_action_time_s==20 and c.config.settle_time_s==1
    assert c.config.search_time_s==8 and c.config.max_searches==2
    assert c.config.spiral_radius_m==120e-6
    assert c.exit_gate.hold_s==.05
