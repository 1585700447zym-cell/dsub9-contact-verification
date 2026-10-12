"""Deferred actor-only deployment; no replay or optimizers are constructed."""
from pathlib import Path
import hashlib,io
from sac_scope import canonical,read,sha,finite_vector

def permitted():
    from sac_entry import assert_owned
    assert_owned()

def actor_digest(actor):
    permitted();h=hashlib.sha256()
    for name,value in sorted(actor.state_dict().items()):
        h.update(name.encode());h.update(str(tuple(value.shape)).encode());h.update(value.detach().cpu().contiguous().numpy().tobytes())
    return h.hexdigest()

def load_state(spec,config,meter,save):
    permitted()
    p=Path(spec['checkpoint']);manifest=read(p/'manifest.json')
    if sha(p/'manifest.json')!=spec['manifest_sha256'] or manifest['version']!='v4_checkpoint_manifest_v1':raise ValueError('Weight manifest drift')
    payload=(p/'state.pt').read_bytes()
    if len(payload)!=spec['state_bytes'] or hashlib.sha256(payload).hexdigest()!=spec['state_sha256'] or manifest['state_sha256']!=spec['state_sha256']:
        raise ValueError('Checkpoint payload drift')
    meter['tensor_load_attempts']=meter.get('tensor_load_attempts',0)+1;save()
    if meter['tensor_load_attempts']> (2 if meter.get('numeric') else 1):raise PermissionError('Tensor read ceiling')
    import torch
    state=torch.load(io.BytesIO(payload),map_location='cpu',weights_only=True)
    meter['tensor_loads']=meter.get('tensor_loads',0)+1;save()
    if (state['version']!='v4_pilot_checkpoint_v1' or canonical(state['config'])!=canonical(config['learning_config']) or
        state['update_attempts']!=spec['updates'] or state['updater']['counts']['critic']!=spec['updates'] or
        state['updater']['counts']['target']!=spec['updates'] or len(state['history'])!=spec['updates']):
        raise ValueError('Checkpoint saved config/update identity differs')
    return state

def make_actor(state,spec,config,meter,save):
    permitted();meter['actor_construction_attempts']=meter.get('actor_construction_attempts',0)+1;save()
    if meter['actor_construction_attempts']>(2 if meter.get('numeric') else 1):raise PermissionError('Actor construction ceiling')
    import numpy as np
    import torch
    from gymnasium import spaces
    from stable_baselines3.sac.policies import Actor
    from stable_baselines3.common.torch_layers import FlattenExtractor
    settings=config['learning_config']['learning'];torch.set_num_threads(settings['torch_threads'])
    obs=spaces.Box(-10.,10.,shape=(137,),dtype=np.float32);action=spaces.Box(-1.,1.,shape=(4,),dtype=np.float32)
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(settings['seed'])
        actor=Actor(obs,action,net_arch=settings['network'],features_extractor=FlattenExtractor(obs),
            features_dim=137,activation_fn=torch.nn.ReLU,use_sde=False,log_std_init=-3.,full_std=True,
            use_expln=False,clip_mean=2.,normalize_images=True).to('cpu')
    saved={k[len('actor.'):]:v for k,v in state['updater']['policy'].items() if k.startswith('actor.')}
    if set(saved)!=set(actor.state_dict()):raise ValueError('Strict actor keys required')
    for k,v in saved.items():
        if not isinstance(v,torch.Tensor) or v.device.type!='cpu' or v.dtype!=torch.float32 or v.shape!=actor.state_dict()[k].shape or not torch.isfinite(v).all():
            raise ValueError('Actor tensor shape/dtype/finiteness differs')
    actor.load_state_dict(saved,strict=True);actor.set_training_mode(False)
    for p in actor.parameters():p.requires_grad_(False)
    if actor_digest(actor)!=spec['actor_sha256']:raise ValueError('Actor fingerprint differs from old evaluations')
    def predict_action(observation):
        permitted();finite_vector(observation,137)
        if max(abs(v) for v in observation)>10:raise ValueError('Observation outside shared schema bounds')
        value=actor.predict(np.asarray(observation,dtype=np.float32),deterministic=True)[0]
        if value.dtype!=np.float32 or value.shape!=(4,) or not np.isfinite(value).all() or np.max(np.abs(value))>1:
            raise ValueError('Actor output shape/dtype/bounds differs')
        return value.tolist()
    actor.predict_action=predict_action
    meter['actor_constructions']=meter.get('actor_constructions',0)+1;save();return actor

def numeric_worker(run,config,binding,meter):
    permitted()
    from sac_scope import OUT,write,actor_spec
    def save():write(run/'receipt.json',meter)
    import numpy as np
    import torch
    from gymnasium import spaces
    from stable_baselines3.sac.policies import SACPolicy
    settings=config['learning_config']['learning'];torch.set_num_threads(settings['torch_threads']);results=[]
    states=read(OUT/'numeric_reference_states.json')['states']
    for role in ['F0','F2000']:
        spec=actor_spec(role);state=load_state(spec,config,meter,save);actor=make_actor(state,spec,config,meter,save)
        meter['reference_learner_construction_attempts']=meter.get('reference_learner_construction_attempts',0)+1;save()
        if meter['reference_learner_construction_attempts']>2:raise PermissionError('Reference construction ceiling')
        # Exact original SACPolicy constructor/predict path from v4_sac.py. No updater, replay or optimizer restore.
        with torch.random.fork_rng(devices=[]):
            torch.manual_seed(settings['seed'])
            reference=SACPolicy(spaces.Box(-10.,10.,shape=(137,),dtype=np.float32),spaces.Box(-1.,1.,shape=(4,),dtype=np.float32),
                lambda _:settings['learning_rate'],net_arch=settings['network'],activation_fn=torch.nn.ReLU)
        reference.load_state_dict(state['updater']['policy'],strict=True);reference.set_training_mode(False)
        meter['reference_learner_constructions']=meter.get('reference_learner_constructions',0)+1;save()
        before=actor_digest(actor);reference_before=actor_digest(reference.actor)
        if before!=reference_before:raise ValueError('Reference/deployed actor tensors differ')
        for item in [s for s in states if s['role']==role]:
            if (OUT/'STOP').exists():raise RuntimeError('STOP; unused numeric allowance closed')
            actions=[]
            for policy in [reference,actor]:
                if meter.get('policy_call_attempts',0)>=64:raise PermissionError('Numeric call ceiling')
                meter['policy_call_attempts']=meter.get('policy_call_attempts',0)+1;save()
                value=policy.predict(np.asarray(item['observation'],dtype=np.float32),deterministic=True)[0]
                meter['policy_calls']=meter.get('policy_calls',0)+1;save();actions.append(value)
            original=np.asarray(item['raw_action'],dtype=np.float32)
            if any(a.shape!=(4,) or a.dtype!=np.float32 or not np.isfinite(a).all() for a in actions) or not (
                np.array_equal(actions[0],actions[1]) and np.array_equal(actions[0],original)):
                raise ValueError('Deterministic single-frame reference / deployed / original float32 action differs')
            results.append(dict(role=role,original_case_id=item['original_case_id'],input_index=item['input_index'],
                all_three_equal=True,action=actions[1].tolist()))
        if actor_digest(actor)!=before or actor_digest(reference.actor)!=before:raise ValueError('Actor mutated during equivalence')
        del state,actor,reference
    if len(results)!=32 or meter['policy_calls']!=64:raise ValueError('Numeric proof incomplete')
    return dict(passed=True,binding_sha256=sha(OUT/'source_binding.json'),states_sha256=sha(OUT/'numeric_reference_states.json'),
        actor_specs_sha256=sha(OUT/'actors.json'),equivalent_states=32,policy_calls=64,rows=results,
        critic_forward_calls=0,formal_updates=0,optimizer_steps=0,physics_steps=0,replay_publications=0,training_admitted=False)
