"""Pure archived-data verification and empty learning-state identity; no rollouts."""
from pathlib import Path
import sys
import gzip
import importlib.util
import json
import numpy as np
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.learning.fixed_rotation_cycle import DELIVERY,PREVIOUS,OLD,verify_previous,fixed_config
from tools.learning.runtime import select_runtime,active_package,verify_runtime
from tools.learning.admission import digest,canonical
from tools.learning.admitted_collection import _write_json as write
parent=verify_previous()
select_runtime(PREVIOUS/'runtime.json',expected_digest=parent['runtime_record_sha256'])
verify_runtime(active_package())
import mujoco
import torch
counts=dict(physics=0,optimizer=0)
def deny(kind):
    def fail(*args,**kwargs):counts[kind]+=1;raise AssertionError('Forbidden '+kind)
    return fail
torch.optim.Adam.step=deny('optimizer')
for name in ('mj_forward','mj_step','mj_step1','mj_step2','mj_resetData','mj_resetDataKeyframe'):
    setattr(mujoco,name,deny('physics'))
from tools.learning.action import compose_command
from tools.learning.bounded_cycle import cases
from tools.learning.engineering_evaluation import episode_metrics
from tools.learning.sac_checkpoint import _audit_physics
from tools.learning.repaired_cycle import verify_initial_chain
from tools.learning.bounded_contact import BoundedCollection
from tools.learning.fixed_rotation_cycle import FixedAdmission
spec=importlib.util.spec_from_file_location('old_action_mapping',DELIVERY/'source_snapshot/tools/learning/action.py')
old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
results=json.loads((PREVIOUS/'run/baseline/results.json').read_text(encoding='utf-8'))
inputs={};rows=[];total=0
for case in cases():
    path=PREVIOUS/'run/baseline/episodes'/case['name']/'episode.json.gz'
    inputs[path.relative_to(ROOT).as_posix()]=digest(path)
    raw=json.loads(gzip.decompress(path.read_bytes()))
    assert raw['case']==case and raw['evaluation_method']=='zero_b2'
    _audit_physics(raw)
    metric=dict(case=case['name'],**episode_metrics(raw))
    assert canonical(metric)==canonical(next(r for r in results if r['case']==case['name']))
    previous=np.zeros(6)
    for row in raw['transitions']:
        log=row['action_log'];assert row['action']==[0.]*4 and log['raw_action']==[0.]*4
        args=dict(phase=row['trace_row']['policy_phase'],enabled=log['enabled'],previous_limited=previous,dt=.002)
        base=log['stage_limited_total']
        a=old.compose_command(base,[0.]*4,**args)
        b=compose_command(base,[0.]*4,action_scale=fixed_config()['action']['scale'],**args)
        assert np.array_equal(a[0],b[0]) and a[1]==b[1]
        previous=np.array(log['actual_end_limited_command']);total+=1
    rows.append(metric)
for name in ('run/baseline/results.json','baseline_audit.json','runtime.json'):
    path=PREVIOUS/name;inputs[path.relative_to(ROOT).as_posix()]=digest(path)
write(DELIVERY/'baseline_reuse.json',dict(passed=True,input_sha256=inputs,results=rows,
    zero_command_comparisons=total,all_four_physical_audits=True,physical_starts=0,optimizer_calls=0,
    qualification_runtime_unchanged=True,limitation='Same supplied-state zero-command equivalence, not a new physical rollout.'))
class PreparationPermit(FixedAdmission):
    def __init__(self):
        self.expected_digest='PREPARATION-NOT-EXECUTION'
        self._record=dict(config=fixed_config(),synthetic_only=True)
    def verify(self,case=None):return self._record
chain=BoundedCollection(admission=PreparationPermit(),output=DELIVERY/'empty_state_check')
receipt=verify_initial_chain(chain)
assert not any(counts.values())
receipt['forbidden_call_counts']=counts
write(DELIVERY/'initial_identity_preflight.json',receipt)
print(json.dumps(dict(zero_command_comparisons=total,initial_identity=receipt,forbidden_call_counts=counts)))
