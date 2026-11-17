"""Whole-cycle policy-source tests using a controller session double."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from tools.learning.five_axis_contract import field_slices, permission
from tools.learning.observation import POLICY_PHASES, PHYSICAL_PHASES, RECOVERY_PHASES
from tools.learning.recurrent_collection import CyclePolicy, collect_episode
from tools.validation.recurrent_source_audit import audit_source


def obs(phase, physical="RUNNING", recovery=None, *, signal=0.):
    data = np.zeros(140)
    fields = field_slices()
    for value, name, values in [(phase, "policy_phase", POLICY_PHASES),
                                (physical, "physical_phase", PHYSICAL_PHASES),
                                (recovery, "recovery_phase", RECOVERY_PHASES)]:
        data[fields[name].start + values.index(value)] = 1.
    data[fields["decision"].start] = 1.
    data[fields["simulation_valid"]] = 1.
    data[fields["action_active"]] = phase in ("INSERT", "SEARCH") and physical == "RUNNING"
    data[0] = signal
    return data


class HistoryActor(torch.nn.Module):
    """Scalar sum makes the contribution of each inactive observation measurable."""
    def __init__(self):
        super().__init__()
        self.scale = torch.nn.Parameter(torch.ones(1))

    def encode_step(self, x, hidden=None):
        h = x[:, :1] * self.scale if hidden is None else hidden[0] + x[:, :1] * self.scale
        return h, h[None]

    def distribution(self, encoded):
        return encoded.expand(-1, 5), torch.zeros_like(encoded.expand(-1, 5))


class MemorylessActor(torch.nn.Module):
    def get_action_dist_params(self, x):
        return x[:, :1].expand(-1, 5), torch.zeros(x.shape[0], 5), {}


def provider(mode="gru", deterministic=True):
    actor = HistoryActor() if mode == "gru" else MemorylessActor()
    return actor, CyclePolicy(mode, actor, checkpoint_id="fixture-7", exploration_seed=14,
                              deterministic=deterministic)


def test_gru_encodes_unload_retract_once_and_resets_at_episode_boundary():
    actor, policy = provider()
    policy.begin_episode("experiment-1")
    search = obs("SEARCH", signal=.1)
    first = policy.select_cycle(0, search, True)
    assert first == policy.select_cycle(0, search.copy(), True)
    with pytest.raises(ValueError):
        policy.select_cycle(0, obs("SEARCH", signal=.2), True)
    with pytest.raises(ValueError):
        policy.select_cycle(2, search, True)
    assert policy.select_cycle(1, obs("UNLOAD", signal=.2), False) == [0.] * 5
    assert policy.select_cycle(2, obs("WAIT_RECOVERY", "RETRACT", "RETRACT", signal=.4), False) == [0.] * 5
    resumed = policy.select_cycle(3, search, True)
    assert resumed == pytest.approx([np.tanh(.8)] * 5, abs=1e-7)
    with pytest.raises(RuntimeError):
        policy.begin_episode("unexpected-reset")
    policy.end_episode()
    policy.begin_episode("experiment-2")
    assert first == policy.select_cycle(0, search, True)


class Session:
    def __init__(self):
        from tools.validation.run_actor_lr_comparison import select_qualified_runtime
        select_qualified_runtime()
        from tools.learning.force_recovery_trial import protocol_config
        self.contract = protocol_config(900)
        self.env = SimpleNamespace(force_recovery_evidence=lambda: {}, peaks={})
        self.observations = SimpleNamespace(version=self.contract["observation_version"], schema=[])
        self.frames = [obs("SEARCH", signal=.1), obs("UNLOAD", signal=.2),
                       obs("WAIT_RECOVERY", "RETRACT", "RETRACT", signal=.4),
                       obs("SEARCH", signal=.1), obs("FAILED", "STOPPING"), obs("FAILED","TERMINAL")]

    def reset(self, case, seed=None):
        self.cycle_id = 0

    def prepare_cycle(self):
        vector = self.frames[self.cycle_id]
        return SimpleNamespace(state={}, policy_observation=vector, residual_enabled=permission(vector))

    def advance_cycle(self, action):
        self.cycle_id += 1
        return SimpleNamespace(
            next_snapshot=self.prepare_cycle(), dt=.002, done=self.cycle_id == len(self.frames)-1,
            action_log=dict(raw_action=action, experience_action=action, enabled=permission(self.frames[self.cycle_id-1])),
            reward_terms={"total": 0.}, trace_row={}, cycle_peaks={}, events=[])

    def adjudicate(self):
        return dict(simulation_valid=True, physical_stopped=True, task_outcome="TASK_FAILURE")


@pytest.mark.parametrize("mode", ["mlp", "gru"])
def test_source_replay_matches_real_collector_path_including_stop_tail(mode):
    actor, policy = provider(mode, deterministic=False)
    raw = collect_episode(Session(), None, provider=policy, episode_id="e45", seed=11)
    audit = dict(actor=actor, policy_mode=mode, checkpoint_id="fixture-7", exploration_seed=14, deterministic=False)
    result = audit_source(raw, **audit)
    assert result["verified"]
    assert raw["training_admitted"] is False and raw["valid_for_learning"] is False
    assert raw["source_counts"]["encoded_cycles"] == (5 if mode == "gru" else 0)
    assert raw["source_counts"]["actor_head_calls"] == 2
    assert raw["action_provider_calls"] == raw["action_provider_successes"] == 2
    for label in ("inactive_observation", "request", "checkpoint", "counts", "mode", "terminal"):
        changed = deepcopy(raw)
        if label == "inactive_observation":
            changed["transitions"][2]["observation"][0] += .25
        elif label == "request":
            changed["transitions"][3]["action_log"]["raw_action"][2] += .01
        elif label == "checkpoint":
            changed["policy_source"]["checkpoint_id"] = "another-id"
        elif label == "counts":
            changed["source_counts"]["actor_head_calls"] += 1
        elif label == "mode":
            changed["policy_mode"] = "mlp" if mode == "gru" else "gru"
        else:
            changed["transitions"][-1]["terminated"] = False
        with pytest.raises(ValueError):
            audit_source(changed, **audit)


def test_noise_clock_changes_epsilon_at_cycle_25_and_mu_every_cycle():
    _, policy = provider(deterministic=False)
    policy.begin_episode("noise")
    for cycle in range(26):
        policy.select_cycle(cycle, obs("SEARCH", signal=.01), True)
    rows = policy.records
    assert rows[0]["noise"]["noise"] == rows[24]["noise"]["noise"] != rows[25]["noise"]["noise"]
    assert rows[0]["mean"] != rows[1]["mean"]


def test_mlp_mode_matches_existing_held_policy_exactly():
    from tools.learning.five_axis_contract import learning_config
    from tools.learning.five_axis_sac import FiveAxisUpdater
    from tools.learning.noise50_trial import FrozenHeldPolicy

    updater = FiveAxisUpdater(learning_config())
    old = FrozenHeldPolicy(SimpleNamespace(updater=updater), seed=18)
    new = CyclePolicy("mlp", updater.policy.actor, checkpoint_id="mlp-fixture", exploration_seed=18)
    new.begin_episode("paired")
    for i, phase in enumerate(["SEARCH", "UNLOAD", "SEARCH", "INSERT"]):
        frame = obs(phase, signal=i/10)
        enabled = permission(frame)
        expected = old.select(frame if enabled else None, cycle=i, phase=phase, enabled=enabled)
        assert new.select_cycle(i, frame, enabled) == expected
        assert new.records[-1]["noise"] == old.last_log["noise"]


def test_real_gru_actor_checkpoint_binding_and_frozen_episode_weights():
    from tools.learning.recurrent_sac import RecurrentActor

    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(73)
        actor = RecurrentActor()
    new = CyclePolicy("gru", actor, checkpoint_id="gru-fixture", exploration_seed=73)
    retained = deepcopy(actor)
    with torch.no_grad():
        next(actor.parameters()).add_(1)
    raw = collect_episode(Session(), None, provider=new, episode_id="gru-fixture-ep")
    settings = dict(policy_mode="gru", checkpoint_id="gru-fixture", exploration_seed=73)
    assert audit_source(raw, actor=retained, **settings)["audit_encoded_cycles"] == 5
    with pytest.raises(ValueError, match="digest"):
        audit_source(raw, actor=actor, **settings)


def test_interrupted_forward_preserves_cost_and_closes_episode():
    from tools.learning.five_axis_collection import CollectionError

    class BrokenActor(HistoryActor):
        def distribution(self, encoded):
            raise RuntimeError("injected head failure")

    new = CyclePolicy("gru", BrokenActor(), checkpoint_id="fault", exploration_seed=0)
    with pytest.raises(CollectionError, match="injected head failure") as caught:
        collect_episode(Session(), None, provider=new, episode_id="fault")
    raw = caught.value.archive
    assert raw["source_counts"]["encoded_cycles"] == raw["source_counts"]["actor_head_calls"] == 1
    assert raw["source_counts"]["completed_cycle_inputs"] == 0
    assert raw["action_provider_successes"] == 0 and raw["training_admitted"] is False
    new.begin_episode("next")  # the wrapper closes the interrupted lifecycle
