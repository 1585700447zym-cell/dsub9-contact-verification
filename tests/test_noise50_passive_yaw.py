import numpy as np
from tools.learning.noise50_trial import YawOnlyOff, behavior_contract
from tools.control.yaw_admittance import YawFixedAdmittance


def test_yaw_off_preserves_all_original_four_axis_feedback():
    on, off = YawFixedAdmittance(), YawOnlyOff()
    for w in ([1., -.7, -2., .01, -.03, .05], [-.4, .8, -1., -.02, .02, -.06])*5:
        a, b = on.command(w, .002), off.command(w, .002)
        np.testing.assert_array_equal(a[:5], b[:5])
        np.testing.assert_array_equal(on.velocity, off.velocity)
        np.testing.assert_array_equal(on.offset, off.offset)
        assert b[5] == 0 and off.feedback_enabled
        assert off.yaw_velocity == off.yaw_offset == 0
    assert on.yaw_updates == 10 and off.yaw_updates == 0


def test_diagnostic_behavior_is_frozen_50ms_and_zero_update():
    on, off = behavior_contract(True), behavior_contract(False)
    assert on['noise_hold_cycles'] == off['noise_hold_cycles'] == 25
    assert on['control_period_s'] == off['control_period_s'] == .002
    assert on['optimizer_updates'] == off['optimizer_updates'] == 0
    assert on['passive_yaw_enabled'] is True and off['passive_yaw_enabled'] is False
    assert {k:v for k,v in on.items() if k!='passive_yaw_enabled'} == {k:v for k,v in off.items() if k!='passive_yaw_enabled'}


def test_source_adapter_replays_inactive_gaps_and_tail():
    from copy import deepcopy
    from tools.learning.persistent_exploration import HeldExploration
    from tools.learning.noise50_trial import HeldSourceReplay, FrozenHeldPolicy
    class Fake:
        def __init__(self):
            self.sampler=HeldExploration(31); self.policy_calls=0; self.last_log={}
        def select(self, observation, *, cycle, phase, enabled):
            noise=self.sampler.noise_at(cycle,phase=phase,enabled=enabled)
            if enabled: self.policy_calls+=1
            self.last_log=dict(noise=deepcopy(self.sampler.last_log),calls=self.policy_calls)
            return (np.tanh(noise+cycle*.001) if enabled else np.zeros(5)).tolist()
        finish_cycle=FrozenHeldPolicy.finish_cycle
    phases=['INSERT']*7+['UNLOAD']*4+['SEARCH']*20+['WAIT_RECOVERY']*4+['SEARCH']*13+['FAILED']*8
    actual=Fake(); contexts=[]; actions=[]
    for cycle,phase in enumerate(phases):
        enabled=phase in ('INSERT','SEARCH')
        next_enabled=cycle+1<len(phases) and phases[cycle+1] in ('INSERT','SEARCH')
        actions.append(actual.select(None,cycle=cycle,phase=phase,enabled=enabled))
        contexts.append(dict(cycle=cycle,phase=phase,enabled=enabled,next_enabled=next_enabled,source_log=deepcopy(actual.last_log)))
        actual.finish_cycle(next_enabled)
    replay=HeldSourceReplay(Fake(),contexts)
    for context,action in zip(contexts,actions):
        if context['enabled']: assert replay.action([0.]*140)==action
    assert replay.finish()==actual.sampler.state_dict()
    assert replay.policy_calls==actual.policy_calls
