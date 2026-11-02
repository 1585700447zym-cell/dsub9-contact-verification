import importlib.util
import pytest


def gate():
    spec=importlib.util.find_spec('tools.validation.run_native313_validation')
    assert spec is not None, 'Isolated version regression gate is missing'
    from tools.validation.run_native313_validation import require_static_gate
    return require_static_gate


def test_rejects_wrong_engine_and_incomplete_static_evidence():
    check=gate()
    good={'passed':True,'mujoco_version':'3.13.0','strict_pairs_pass':True,'new_failure_pass':True}
    check(good,'3.13.0')
    with pytest.raises(ValueError):check(good,'3.9.0')
    for key in ('passed','strict_pairs_pass','new_failure_pass'):
        with pytest.raises(ValueError):check({**good,key:False},'3.13.0')
    with pytest.raises(ValueError):check({'passed':True},'3.13.0')
