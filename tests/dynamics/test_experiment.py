from tools.dynamics.cartesian import CartesianEnvironment
from tools.validation.validate_dynamic_actuator import run_episode
from tools.validation.run_contact_cases import ContactCase


def test_recovery_keeps_first_stop_distinct_from_final_stop():
    result=run_episode(CartesianEnvironment(),'snapshot_check',ContactCase.separated(),.02,True)
    assert result['recovery']=='ACCEPTED'
    first=result['first_stop_snapshot']['time_s']
    assert abs(first-.02)<1e-10
    assert result['final_stop_snapshot']['time_s']>first+.5
    elapsed=result['stop_check_0p2']['time_s']-first
    assert .198-1e-10<=elapsed<=.2+1e-10
