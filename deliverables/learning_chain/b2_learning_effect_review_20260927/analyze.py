"""Read-only analysis of sealed B2-13 data. No physics or optimizer updates."""
from pathlib import Path
import gzip
import hashlib
import json
import math
import os
import sys
from copy import deepcopy

ROOT = Path(__file__).resolve().parents[3]
os.environ.setdefault('MPLCONFIGDIR', str(ROOT / 'tmp/learning_mpl_cache'))
sys.path.insert(0, str(ROOT))
import numpy as np
import torch
from gymnasium import spaces
from stable_baselines3.sac.policies import SACPolicy

SRC = ROOT / 'deliverables/learning_chain/b2_contact_short_train_20260927'
OUT = Path(__file__).resolve().parent
INPUTS = {}

def read(path):
    data = path.read_bytes()
    INPUTS[path.relative_to(ROOT).as_posix()] = hashlib.sha256(data).hexdigest()
    return data

def archive(path):
    return json.loads(gzip.decompress(read(path)))

def stats(values):
    a = np.asarray(values, dtype=float)
    return dict(n=int(a.size), mean=float(a.mean()), median=float(np.median(a)),
                minimum=float(a.min()), maximum=float(a.max())) if a.size else None

torch.set_num_threads(1)
torch.manual_seed(1401)
sealed = json.loads(read(SRC/'manifest.json'))
assert INPUTS[(SRC/'manifest.json').relative_to(ROOT).as_posix()] == 'e643d9b88c8a37cedcb0137575581ecc6133346f1062c77482f5db59237d159e'
for path,expected in sealed['files'].items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected, path
cp = SRC / 'run/training/checkpoints/contact_000003'
manifest = json.loads(read(cp / 'manifest.json'))
assert INPUTS[(cp/'manifest.json').relative_to(ROOT).as_posix()] == 'c29d7837a12a842a0fe8281f47e42d4b22195fc091125e60eff5a60295d01ca1'
assert hashlib.sha256(read(cp / 'state.pt')).hexdigest() == manifest['state_sha256']
state = torch.load(cp / 'state.pt', weights_only=True, map_location='cpu')
policy = SACPolicy(spaces.Box(-10., 10., shape=(120,), dtype=np.float32),
    spaces.Box(-1., 1., shape=(4,), dtype=np.float32), lambda _: .0003,
    net_arch=[256, 256], activation_fn=torch.nn.ReLU)
policy.load_state_dict(state['updater']['policy'])
policy.set_training_mode(False)
initial_parameters = deepcopy(policy.state_dict())
alpha = float(state['updater']['alpha'].exp())

def episode(raw, kind):
    if kind == 'baseline':
        rows = [dict(observation=t['observation'], action=[0.]*4,
            action_active=t['action_active'], reward=t['reward']['total'],
            reward_terms=t['reward'], discount=math.exp(-t['dt']/10), dt=t['dt'],
            terminated=i==len(raw['trace'])-1, trace_row=t['physical'],
            action_log=t['action_log']) for i,t in enumerate(raw['trace'])]
        outcome = raw['task_outcome']
    else:
        rows = raw['transitions']; outcome = raw['outcome']['task_outcome']
    n = len(rows)
    obs = torch.tensor([r['observation'] for r in rows], dtype=torch.float32)
    active = np.asarray([r['action_active'] for r in rows], dtype=bool)
    contact = np.asarray([r['trace_row']['contact_count'] > 0 for r in rows])
    actual = torch.tensor([r['action'] for r in rows], dtype=torch.float32)
    with torch.no_grad():
        mean = policy.actor(obs, deterministic=True)
        q_both = torch.cat(policy.critic(obs, actual), 1).numpy()
        qa = q_both.min(1)
        qz = torch.cat(policy.critic(obs, torch.zeros_like(actual)), 1).min(1).values.numpy()
        qm = torch.cat(policy.critic(obs, mean), 1).min(1).values.numpy()
        _, logp = policy.actor.action_log_prob(obs)
        ent = -alpha*logp.numpy()
    rewards = np.asarray([r['reward'] for r in rows])
    returns = np.zeros(n)
    for i in range(n-1, -1, -1):
        returns[i] = rewards[i] + (rows[i]['discount']*returns[i+1] if i+1<n else 0.)
    first_contact = int(np.flatnonzero(contact)[0]) if contact.any() else n
    last_active = int(np.flatnonzero(active)[-1])
    assert not active[last_active+1:].any()
    terminal = [i for i,r in enumerate(rows) if r['reward_terms'].get('terminal',0) != 0]
    terms = {key:sum(r['reward_terms'].get(key,0.) for r in rows)
             for key in ('progress','time','force','torque','terminal')}
    deterministic_actions = mean.numpy()
    actions = actual.numpy()
    def region(mask):
        return dict(n=int(mask.sum()), actual_action_mean=actions[mask].mean(0).tolist(),
            final_policy_mean=deterministic_actions[mask].mean(0).tolist(),
            q_actual=stats(qa[mask]), q_policy_minus_zero=stats((qm-qz)[mask]),
            reward_abs=stats(np.abs(rewards[mask])), sampled_entropy_bonus=stats(ent[mask])) if mask.any() else None
    tail_points = sorted(set([last_active+1, n-1001, n-501, n-101, n-11, n-1]))
    tail = []
    for i in tail_points:
        if i < last_active+1 or i < 0: continue
        tail.append(dict(index=i, remaining_steps=n-i,
            inactive=True, q_zero=float(qz[i]), observed_discounted_return=float(returns[i]),
            q_each=q_both[i].tolist(),
            physical_phase=rows[i]['trace_row']['phase']))
    return dict(id=raw.get('episode_id',raw.get('id')), kind=kind, outcome=outcome,
        cycles=n, duration_s=sum(r['dt'] for r in rows), first_contact_s=rows[first_contact]['trace_row']['time_s'] if first_contact<n else None,
        active_cycles=int(active.sum()), contact_cycles=int(contact.sum()),
        final_xy_um=float(np.linalg.norm(rows[-1]['trace_row']['position_m'][:2])*1e6),
        return_sum=float(rewards.sum()), discounted_return=float(returns[0]), reward_terms=terms,
        terminal_indices=terminal, terminal_count=len(terminal), last_active_index=last_active,
        terminal_delay_from_last_active_s=sum(r['dt'] for r in rows[last_active+1:]),
        inactive_suffix_cycles=n-last_active-1, tail_q_vs_realized_return=tail,
        regions=dict(active=region(active), precontact_active=region(active & (np.arange(n)<first_contact)),
            contact_active=region(active & contact)),
        initial_observation=obs[0].tolist(), initial_policy_action=deterministic_actions[0].tolist())

training=[]; evaluation=[]; baselines=[]
for path in sorted((SRC/'run/episodes').glob('*/episode.json.gz')):
    training.append(episode(archive(path),'training'))
for path in sorted((SRC/'evaluation_run/evaluation/episodes').glob('*/episode.json.gz')):
    evaluation.append(episode(archive(path),'evaluation'))
base = ROOT/'deliverables/learning_chain/b2_contact_preflight_20260927/runs'
for point in ('x_neg_100','x_pos_100','y_neg_100','y_pos_100'):
    baselines.append(episode(archive(base/f'zero_{point}.json.gz'),'baseline'))

updates = json.loads(read(SRC/'run/training/updates.json'))
# Reconstruct batch indices only, never re-run updates. Check against archived
# active counts, reward means and final PCG64 state to establish exact history.
replay_episodes=state['replay']['episodes']
flat_rewards=torch.cat([v['rewards'] for _,v in replay_episodes])
flat_active=torch.cat([v['action_active'] for _,v in replay_episodes])
lengths=[len(v['rewards']) for _,v in replay_episodes]
end_indices=np.cumsum(lengths)-1
draw_rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([2026092711,2])))
terminal_hits=np.zeros(4,dtype=np.int64)
terminal_batches=0
for update in updates:
    indices=draw_rng.integers(0,update['audited_total'],size=256)
    hit=np.asarray([(indices==end).sum() for end in end_indices])
    terminal_hits+=hit
    terminal_batches+=int(hit.sum()>0)
    assert int(flat_active[indices].sum())==update['active_rows']
    assert abs(float(flat_rewards[indices].abs().mean())-update['reward_abs_mean'])<1e-8
assert draw_rng.bit_generator.state==state['rng']['replay']
replay_reconstruction=dict(terminal_row_draws_by_episode=terminal_hits.tolist(),
    batches_with_terminal=terminal_batches,batches_without_terminal=len(updates)-terminal_batches,
    total_batch_rows=len(updates)*256,terminal_row_draws=int(terminal_hits.sum()),
    final_rng_exact_match=True,all_logged_batch_active_counts_and_reward_means_match=True)
history = []
for total in sorted(set(u['audited_total'] for u in updates)):
    group = [u for u in updates if u['audited_total']==total]
    history.append(dict(audited_total=total, updates=len(group),
        alpha_start=group[0]['alpha_before'], alpha_end=group[-1]['alpha_after'],
        critic_loss=stats([u['critic_loss'] for u in group]),
        logged_entropy_abs_mean=stats([u['entropy_abs_mean'] for u in group]),
        logged_reward_abs_mean=stats([u['reward_abs_mean'] for u in group]),
        target_abs_max=stats([u['target_abs_max'] for u in group])))

assert len(training)==4 and len(evaluation)==4 and len(baselines)==4
assert sum(r['cycles'] for r in training)==22722
assert sum(r['terminal_count'] for r in training)==4
assert state['updater']['counts']['critic']==4430
assert all(e['initial_observation']==evaluation[0]['initial_observation'] for e in evaluation)
for key in ('reward.py','observation.py','sac_update.py','tensor_masks.py','sac_collection.py','audited_replay.py'):
    read(ROOT/'tools/learning'/key)

result = dict(version='b2_learning_effect_offline_review_v1', new_physical_episodes=0,
    optimizer_updates=0, final_alpha=alpha,
    limitations=['Tail returns are exact realized rewards on archived zero-action suffixes; comparisons measure fitted critic error on these observed states, not a causal policy counterfactual.',
        'Active-state critic scores are soft, approximate, and off-policy; they are not comparable to ordinary realized returns as a policy ranking test.',
        'Entropy/reward magnitude is a scale clue, not proof that entropy gradients dominate.',
        'Four-point deterministic development set and single training seed do not estimate generalization.'],
    training=training,evaluation=evaluation,baselines=baselines,update_groups=history,
    terminal_fraction=4/22722, physical_time_discount_last_2s=math.exp(-.2),
    exact_initial_eval_observations_identical=True, source_sha256=INPUTS)
result['reconstructed_replay']=replay_reconstruction
result['sealed_b213_file_checks']=len(sealed['files'])
assert all(torch.equal(v,initial_parameters[k]) for k,v in policy.state_dict().items())
result['inference_parameters_unchanged']=True
for path,expected in INPUTS.items():
    assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==expected
if '--check' in sys.argv:
    assert json.loads((OUT/'assessment.json').read_text(encoding='utf-8'))==result
    print('Read-only independent recheck: exact match.')
else:
    (OUT/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('REPLAY',replay_reconstruction)
for e in training:
    print(e['id'],e['outcome'],'tail_start',e['tail_q_vs_realized_return'][0],
          'terminal',e['tail_q_vs_realized_return'][-1])
print('Source unchanged; no optimizer updates or physics; sealed B2-13 files verified:',len(sealed['files']))
