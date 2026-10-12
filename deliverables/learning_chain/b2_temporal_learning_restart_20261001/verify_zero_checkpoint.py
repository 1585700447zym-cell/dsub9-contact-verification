"""Actual execution zero-boundary reader in a separate process, all compute blocked."""
import argparse,json,os,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];sys.path.insert(0,str(ROOT))
import validation_contract as C
p=argparse.ArgumentParser()
for name in ('path','sha256','binding-sha256','authorization-sha256'):p.add_argument('--'+name,required=True)
p.add_argument('--parent-pid',required=True,type=int);a=p.parse_args()
C.require_authorization(a.binding_sha256,a.authorization_sha256);C.verify_binding(a.binding_sha256)
from run_validation import select_runtime,reader_guard
ancestry=reader_guard(a.parent_pid);select_runtime();C.verify_binding(a.binding_sha256,with_runtime=True)
import torch,mujoco
calls=dict(model_forward=0,optimizer=0,physics=0)
def forbidden(kind):
    def fail(*args,**kw):calls[kind]+=1;raise AssertionError('Zero reader forbids '+kind)
    return fail
torch.nn.Module._call_impl=forbidden('model_forward');torch.optim.Adam.step=forbidden('optimizer')
for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):setattr(mujoco,name,forbidden('physics'))
import learning_runtime as R
from tools.learning.sac_checkpoint import _same
path=Path(a.path).resolve()
if path!=(HERE/'run/origin_checkpoint_C').resolve() or C.digest(path/'manifest.json')!=a.sha256:raise ValueError('Exact registered zero checkpoint required')
m=C.read(path/'manifest.json')
if m['batches']!=0 or m['arm']!='C' or C.digest(path/'state.pt')!=m['state_sha256']:raise ValueError('Zero payload pin changed')
s=torch.load(path/'state.pt',map_location='cpu',weights_only=True)
R.check_snapshot_identity(s,'C',a.binding_sha256,a.authorization_sha256)
if s['history'] or any(s['updater']['counts'].values()):raise ValueError('Only complete zero state admitted')
ledger=C.Ledger.load(HERE/'run/ledger.json',a.binding_sha256,a.authorization_sha256);ledger.healthy()
u=R.zero_updater('C')
if not _same(u._snapshot(),s['updater']):raise ValueError('Disk zero network/Adam/Torch RNG differs from pinned origin')
b=R.Branch('C',ledger,s['dataset'],s['dataset_sha256'],updater=u,dataset_bytes=s['dataset_bytes'])
equal=_same(b.capture(),s)
if not equal or any(calls.values()):raise ValueError('Complete data/index/network/random state differs or reader computed')
reader_guard(a.parent_pid)
print(json.dumps(dict(complete_state_equal=equal,checkpoint_sha256=a.sha256,batches=0,actual_calls=calls,
    process_id=os.getpid(),parent_id=os.getppid(),payload_sha256=m['state_sha256'],replay_rows=len(b.replay),qualified_episodes=len(b.refs),**ancestry)))
