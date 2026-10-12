"""Load the pinned complete source without executing a model or optimizer."""
from copy import deepcopy
import night_contract as N

def load():
    import torch
    import learning_runtime as R
    from tools.learning.sac_checkpoint import _same,_tensor,_optimizer
    m=N.verify_parent();s=torch.load(N.CHECKPOINT/'state.pt',map_location='cpu',weights_only=True)
    pins=N.read(N.PARENT/'execution_pins.json')
    R.check_snapshot_identity(s,'C',pins['binding_sha256'],pins['authorization_sha256'])
    if len(s['history'])!=2000 or len(s['references'])!=7 or s['updater']['counts']!={k:2000 for k in ('critic','target','actor','temperature')}:
        raise ValueError('Expected exact complete C2000 source')
    R.verify_dataset_bytes(s['dataset'],s['dataset_bytes'],s['dataset_sha256'])
    u=R.Updater(N.P.config('C'));reference=u._snapshot();saved=s['updater']
    if saved.keys()!=reference.keys() or saved['policy'].keys()!=reference['policy'].keys():raise ValueError('Incomplete updater')
    for k in reference['policy']:_tensor(saved['policy'][k],reference['policy'][k])
    _tensor(saved['alpha'],reference['alpha']);_tensor(saved['rng'],reference['rng']);torch.Generator().set_state(saved['rng'])
    for k,opt in zip(('critic','actor','temperature'),u._optimizers()):_optimizer(saved[k],opt,2000)
    u._restore(deepcopy(saved));u._finite_state()
    if not _same(u._snapshot(),saved) or u.fingerprints()['actor']!=N.ACTOR_PIN:raise ValueError('Full saved updater restore differs')
    return u,s,dict(source_manifest_sha256=N.CHECKPOINT_PIN,state_sha256=m['state_sha256'],actor_sha256=N.ACTOR_PIN,
        updater_complete_equal=True,source_complete_data_audit_sha256=N.digest(N.PARENT/'result_analysis/assessment.json'),
        batches=2000,replay_source_episodes=7,new_training=0)
