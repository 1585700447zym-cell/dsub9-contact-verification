"""Independent contact execution admission; historical qualifications stay immutable."""
from copy import deepcopy
import json
from pathlib import Path
from .admission import canonical,digest,verify_files
from .contact_contract import PREPARATION,PREPARATION_SHA,validate_config,validate_case,contact_config
from .runtime import ROOT
from tools.validation.verify_residual_interface import all_sources,qualified_runtime

DELIVERY=ROOT/'deliverables/learning_chain/b2_contact_execution_20260927'
MODIFICATIONS=frozenset('tools/learning/'+n+'.py' for n in ('admitted_collection','sac_update','sac_collection','sac_checkpoint'))
ADDITIONS=frozenset(['tools/learning/'+n+'.py' for n in ('contact_contract','contact_admission','contact_execution','contact_evaluation','contact_training')]+
                   ['tools/validation/run_contact_training.py','tests/learning/test_contact_execution.py'])
HISTORY={
 'b2_engineering_short_train_20260926':'7441f3efec534b57abab0610a1e6b09db86c03b6f32633cb27c2cd48ef287449',
 'b2_observability_diagnosis_20260927':'33ec26063890cba8e1005756aa80debd144003d5a24eea8587e83cc40d911470',
 'b2_contact_preflight_20260927':'54752d35050b010770abc7467a55a1a13ae25f02e0c828add1c8b03603dd4912',
 'b2_search_action_probe_20260927':'5bfef85024449d9240c450cf36042cb2074c7a0fdfcdd113baa7a349aa0c6b57',
 'b2_action_chain_diagnosis_20260927':'d170602c74f6e61bfca70aad348abcbfdeff9506c3d6c9a1810cb523456576d4',
 'b2_motion_state_probe_20260927':'15e3412604ce6e8fbe396ea399c3c4f6f660459d5a874bb708e17d27a5ec2381',
 'b2_warmup_preflight_20260927':'363e76bab8c4b1f042a20a875b6654093bd23c543e0a82c6d1d420706aa30c44',
 'b2_contact_preparation_20260927':PREPARATION_SHA}


def lineage():
    for folder,sha in HISTORY.items():
        path=PREPARATION.parent/folder/'manifest.json'
        if digest(path)!=sha: raise ValueError('Historical manifest changed')
        verify_files(ROOT,json.loads(path.read_text(encoding='utf-8'))['files'])
    prep=json.loads((PREPARATION/'preparation.json').read_text(encoding='utf-8'))
    old=prep['binding']['legacy_source_sha256']; current=all_sources()
    modified={p for p in old.keys()&current.keys() if old[p]!=current[p]}
    if old.keys()-current.keys() or current.keys()-old.keys()!=ADDITIONS or modified!=MODIFICATIONS:
        raise ValueError('Unreviewed contact source delta')
    for path in MODIFICATIONS:
        if digest(DELIVERY/'source_snapshot'/path)!=old[path]: raise ValueError('Legacy source snapshot changed')
    verify_files(ROOT,prep['binding']['new_source_sha256'])
    verify_files(ROOT,prep['binding']['evidence_sha256'])
    return current


class ContactAdmission:
    def __init__(self,path,*,expected_digest):
        self.path=Path(path).resolve(); self.expected_digest=expected_digest; self.verify()
    @property
    def config(self): return deepcopy(self._record['config'])
    def verify(self,case=None):
        if not self.expected_digest or digest(self.path)!=self.expected_digest: raise ValueError('Contact qualification pin differs')
        r=json.loads(self.path.read_text(encoding='utf-8'))
        flags=('collection_admitted','update_admitted','restore_admitted','runnable_trainer')
        if (r.get('version')!='contact_execution_admission_v1' or r.get('capability')!='contact_four_point_execution' or
            any(r.get(k) is not True for k in flags) or r.get('parent_sha256')!=PREPARATION_SHA):
            raise ValueError('Formal contact execution qualification required')
        validate_config(r['config'])
        if r['source_sha256']!=lineage(): raise ValueError('Execution inputs changed')
        runtime=qualified_runtime(ROOT/'tmp/mujoco_3_13_probe')
        if canonical(runtime)!=canonical(r['runtime']): raise ValueError('Runtime changed')
        verify_files(ROOT,r['evidence_sha256'])
        from .contact_training import verify_validation_evidence
        verify_validation_evidence(r['validation'])
        if case is not None: validate_case(case)
        self._record=r
        return deepcopy(r)
