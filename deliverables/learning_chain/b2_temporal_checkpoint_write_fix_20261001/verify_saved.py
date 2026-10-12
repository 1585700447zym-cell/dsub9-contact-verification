"""Independent process reads/restores zero-update complete file fixture only."""
import argparse,hashlib,io,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'deliverables/learning_chain/b2_temporal_learning_validation_20261001'))
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import torch,mujoco
calls=dict(model_forward=0,optimizer=0,physics=0)
def forbidden(kind):
    def fail(*a,**k):calls[kind]+=1;raise AssertionError('Read-only verifier forbids '+kind)
    return fail
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
import learning_runtime as R
from tools.learning.sac_checkpoint import _same,_tensor,_optimizer
p=argparse.ArgumentParser();p.add_argument('--path',required=True);p.add_argument('--sha256',required=True);a=p.parse_args();path=Path(a.path)
if R.C.digest(path/'manifest.json')!=a.sha256:raise ValueError('Manifest pin changed')
m=R.C.read(path/'manifest.json');data=(path/'state.pt').read_bytes()
if hashlib.sha256(data).hexdigest()!=m['state_sha256']:raise ValueError('Payload pin changed')
s=torch.load(io.BytesIO(data),map_location='cpu',weights_only=True)
R.check_snapshot_identity(s,m['arm'],m['binding_sha256'],m['authorization_sha256']);R.verify_dataset_bytes(s['dataset'],s['dataset_bytes'],s['dataset_sha256'])
if m['batches']!=0 or s['history'] or any(s['updater']['counts'].values()):raise ValueError('Only zero-update offline fixture admitted')
u=R.Updater(s['config']);reference=u._snapshot();saved=s['updater']
for k in reference['policy']:_tensor(saved['policy'][k],reference['policy'][k])
_tensor(saved['alpha'],reference['alpha']);_tensor(saved['rng'],reference['rng']);torch.Generator().set_state(saved['rng'])
for key,opt in zip(('critic','actor','temperature'),u._optimizers()):_optimizer(saved[key],opt,0)
u._restore(saved);u._finite_state();equal=_same(saved,u._snapshot())
if not equal or any(calls.values()):raise ValueError('Complete zero state differs or verifier computed')
print(json.dumps(dict(complete_updater_equal=equal,batches=0,actual_calls=calls,process_id=os.getpid())))
