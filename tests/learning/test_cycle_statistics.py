import numpy as np


def test_cycle_peak_is_not_the_cumulative_peak(runtime):
    from tools.learning.environment import SampledCompatibilityEnvironment
    from tools.validation.run_b1_baseline import cases
    env = SampledCompatibilityEnvironment()
    env.reset(cases()[0])
    env.begin_cycle()
    row = env.observe()
    row['contact_wrench_M'] = [.020, 0, 0, 0, 0, 0]
    env._record_peaks(row)
    assert env.cycle_peaks['force_N'] == .020
    env.begin_cycle()
    row['contact_wrench_M'][0] = .005
    env._record_peaks(row)
    assert env.cycle_peaks['force_N'] == .005
    assert env.peaks['force_N'] == .020
    env.reset(cases()[0])
    assert env.cycle_peaks['force_N'] == 0
    assert env.stop_samples == []


def test_substep_sampler_does_not_replace_global_mujoco_function(runtime):
    import mujoco
    from tools.learning.environment import SampledCompatibilityEnvironment
    from tools.validation.run_b1_baseline import cases
    original = mujoco.mj_step
    env = SampledCompatibilityEnvironment()
    env.reset(cases()[0])
    env.stop('REQUESTED_STOP')
    env.begin_cycle()
    env.step(np.zeros(6))
    assert mujoco.mj_step is original
    assert len(env.stop_samples) == 10
    assert env.cycle_peaks['samples'] == 10
    np.testing.assert_allclose([x['time_s'] for x in env.stop_samples],
                               [.0002, .0004, .0006, .0008, .001, .0012, .0014, .0016, .0018, .002], atol=1e-15)
