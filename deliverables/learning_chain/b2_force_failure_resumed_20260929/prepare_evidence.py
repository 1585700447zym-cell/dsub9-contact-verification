"""Read archived B2 evidence and compare a fresh empty learning state. No rollouts."""
from pathlib import Path
import gzip,json,os,sys,uuid
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.learning.resumed_force_cycle import (DELIVERY,IMPLEMENTATION,PREVIOUS,REPAIRED,OLD,
    ForceAdmission,cycle_config,cycle_sources,verify_parent,verify_initial_chain)
from tools.learning.runtime import select_runtime,active_package,verify_runtime
from tools.learning.admission import digest,canonical,verify_files
from tools.learning.repaired_cycle import read
from tools.learning.admitted_collection import _write_json as write
verify_parent()
parent=read(REPAIRED/'admission.json')
select_runtime(REPAIRED/'runtime.json',expected_digest=parent['runtime_record_sha256'])
verify_runtime(active_package())
import mujoco,torch
from tools.learning.sac_update import SACUpdater
counts=dict(physics=0,optimizer=0,prediction=0)
def deny(kind):
    def fail(*a,**kw):counts[kind]+=1;raise AssertionError('Forbidden preflight call: '+kind)
    return fail
torch.optim.Adam.step=deny('optimizer');SACUpdater.predict=deny('prediction')
for name in ('mj_forward','mj_step','mj_step1','mj_step2','mj_resetData','mj_resetDataKeyframe'):
    setattr(mujoco,name,deny('physics'))
from tools.learning.bounded_contact import BoundedCollection,guard_clear
from tools.learning.bounded_cycle import cases
from tools.learning.engineering_evaluation import episode_metrics
from tools.learning.sac_checkpoint import _audit_physics

prior=read(PREVIOUS/'baseline_reuse.json');verify_files(ROOT,prior['input_sha256'])
assert prior['passed'] and prior['zero_command_comparisons']==24429
inputs=dict(prior['input_sha256']);rows=[]
for case in cases():
    path=REPAIRED/'run/baseline/episodes'/case['name']/'episode.json.gz'
    raw=json.loads(gzip.decompress(path.read_bytes()))
    assert raw['case']==case and raw['evaluation_method']=='zero_b2' and guard_clear(raw)
    _audit_physics(raw)
    row=dict(case=case['name'],**episode_metrics(raw));rows.append(row)
    assert canonical(row)==canonical(next(r for r in prior['results'] if r['case']==case['name']))
    assert all(t['action']==[0.]*4 and t['action_log']['raw_action']==[0.]*4 for t in raw['transitions'])
inputs[(PREVIOUS/'baseline_reuse.json').relative_to(ROOT).as_posix()]=digest(PREVIOUS/'baseline_reuse.json')
write(DELIVERY/'baseline_reuse.json',dict(passed=True,results=rows,input_sha256=inputs,
    inherited_zero_command_comparisons=24429,new_physical_starts=0,new_policy_predictions=0,
    reason='Physics/controller/action sources unchanged from the hash-bound parent; all four raw B2 audits and metrics rechecked.'))

class ProtocolPermit(ForceAdmission):
    def __init__(self):
        self.expected_digest='PREPARATION-NOT-EXECUTION'
        self._record=dict(config=cycle_config(),synthetic_only=True)
    def verify(self,case=None):return self._record

empty_output=DELIVERY/('empty_state_check_'+uuid.uuid4().hex)
chain=BoundedCollection(admission=ProtocolPermit(),output=empty_output)
identity=verify_initial_chain(chain)
static=read(OLD/'checks/preflight.json');synthetic=read(OLD/'checks/synthetic_probe.json')
assert static['all_passed'] and static['holdout_not_previously_used']
assert synthetic['optimizer_batches']==3 and synthetic['all_state_equal']
for package in (OLD,REPAIRED,PREVIOUS,DELIVERY):
    assert not (package/'run/holdout_b2').exists() and not (package/'run/holdout_sac').exists()
assert not any(counts.values())
identity.update(forbidden_call_counts=counts,source_sha256=cycle_sources(),
    independent_points_still_unused=True,inherited_static_reexecuted=False,inherited_three_synthetic_updates_reexecuted=False)
write(DELIVERY/'initial_identity_preflight.json',identity)
print(json.dumps(dict(initial_identity=True,baseline_successes=sum(r['success'] for r in rows),
    source_count=len(identity['source_sha256']),forbidden_call_counts=counts)))
