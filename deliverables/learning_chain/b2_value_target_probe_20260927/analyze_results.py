"""Read-only interpretation and exact checks for the completed v2 diagnostic."""
import importlib.util
import json
import hashlib
from pathlib import Path
import numpy as np
import torch

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('probe_v2',HERE/'probe_v2.py')
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
protocol,state,flat,sets,bindings=m.load_inputs()
result=json.loads((HERE/'run_v2/results.json').read_text(encoding='utf-8'))
from tools.learning.observation import VECTOR_WIDTHS, DECISIONS
decision_start=1+sum(VECTOR_WIDTHS[k] for k in (
    'wrench_history_M','relative_position_m','relative_rotation_world_rad','velocity_world',
    'base_command','previous_limited_command','previous_residual','policy_phase','physical_phase','recovery_phase'))
assert decision_start==66
summaries={}
for arm in protocol['arms']:
    summaries[arm]={}
    for split in ('train','development'):
        initial=result['curves'][arm]['0'][split]['summary']
        final=result['curves'][arm]['1000'][split]['summary']
        summaries[arm][split]={}
        for group in protocol['primary_groups']:
            improvement=1-final[group]['mae']/initial[group]['mae']
            summaries[arm][split][group]=dict(initial_mae=initial[group]['mae'],
                final_mae=final[group]['mae'],final_maximum=final[group]['maximum'],
                relative_mae_reduction=improvement,
                passed=final[group]['maximum']<=1. and improvement>=.8)

ends=np.cumsum([len(ep['observations']) for ep in sets['train']])
starts=np.r_[0,ends[:-1]]
boundary=starts+np.array([ep['last'] for ep in sets['train']])
draws=np.zeros(4,dtype=int); term_draws=np.zeros(4,dtype=int)
rng=np.random.Generator(np.random.PCG64()); rng.bit_generator.state=state['rng']['replay']
h=hashlib.sha256()
for row in result['history']:
    ix=rng.integers(0,22722,size=256); h.update(ix.tobytes())
    draws+=np.array([(ix==v).sum() for v in boundary])
    term_draws+=np.array([(ix==v).sum() for v in ends-1])
    assert int(flat['suffix'][ix].sum())==row['suffix_rows']
    assert int(flat['terminated'][ix].sum())==row['terminal_rows']
assert h.hexdigest()==result['batch_indices_sha256']

diagnostics={}
for arm in protocol['arms']:
    p=m.make_policy(state)
    saved=torch.load(HERE/'run_v2'/f'{arm}.pt',weights_only=True,map_location='cpu')
    p.critic.load_state_dict(saved['critic'])
    diagnostics[arm]={}
    for split,episodes in sets.items():
        details=[]
        for ep in episodes:
            last=ep['last']; obs=ep['observations'][last:]; act=ep['actions'][last:]
            decisions=obs[:,decision_start:decision_start+len(DECISIONS)]
            assert torch.equal(decisions.sum(1),torch.ones(len(obs)))
            labels=decisions.argmax(1)
            known=(labels==DECISIONS.index('GEOMETRIC_SUCCESS'))|(labels==DECISIONS.index('TARGET_POSE_NOT_SETTLED'))
            with torch.no_grad():
                q=torch.cat(p.critic(obs,act),1).min(1).values
                error=(q-ep['returns'][last:]).abs()
            info=dict(id=ep['id'],outcome=ep['outcome'],decision_changes=[],error_by_decision={})
            for index in range(len(labels)):
                if index==0 or labels[index]!=labels[index-1]:
                    info['decision_changes'].append(dict(offset_control_cycles=index,label=DECISIONS[int(labels[index])]))
            for label in torch.unique(labels):
                part=error[labels==label]
                info['error_by_decision'][str(DECISIONS[int(label)])]=dict(n=len(part),mae=float(part.mean()),maximum=float(part.max()))
            details.append(info)
        diagnostics[arm][split]=details

out=dict(version='b2_fixed_actor_value_probe_assessment_v2',valid_comparison=True,
    corrected_critic_updates=2000,invalid_first_attempt_critic_updates=2000,cumulative_critic_updates=4000,
    physical_episodes=0,actor_updates=0,temperature_updates=0,summary=summaries,
    every_primary_group_passed=all(g['passed'] for s in summaries['exact_inactive_suffix'].values() for g in s.values()),
    sampling=dict(batch_indices_reconstructed_exactly=True,last_active_row_draws=draws.tolist(),terminal_row_draws=term_draws.tolist()),
    decision_conditioned=diagnostics,
    conclusion='Exact inactive-tail targets improve terminal fit and mean inactive-tail error, but suffix-start and last-active groups fail preregistered thresholds. No policy-performance claim.',
    limitations=['One checkpoint, four training episodes, one diagnostic batch sequence; archived development data are not independent final tests.',
        'Outcome decision appears only after action disablement; terminal accuracy does not establish useful pre-decision value or action ranking.',
        'Direct exact targets change information delivery but keep the uniform sampler; this does not isolate all causes of boundary underfitting.'],
    result_sha256=m.digest(HERE/'run_v2/results.json'),protocol_sha256=m.digest(HERE/'protocol_v2.json'))
m.dump(HERE/'assessment.json',out)
print(json.dumps(dict(summary=summaries,sampling=out['sampling'],all_passed=out['every_primary_group_passed']),ensure_ascii=False,indent=2))
