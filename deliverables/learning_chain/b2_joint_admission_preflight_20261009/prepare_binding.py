"""Bind new implementation plus all inherited production/runtime inputs; no grant."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from scope_contract import ROOT,read,sha,proposal,PROPOSAL_PIN
from execution_contract import write,verify_files
def main():
    if (OUT/'delivery_manifest.json').exists() or (OUT/'claims').exists():raise PermissionError('Cannot refresh sealed/consumed candidate')
    parent=OUT.parent/'b2_preflight_rebound_20261008/candidate_binding.json'
    if sha(parent)!='b7746e0cfaf29317c1ae692f6ed03c685d0d1a3398965c3fa36fc012b8ed3952':raise ValueError('Prior binding differs')
    old=read(parent);files=dict(old['files']);files[str(parent)]=sha(parent)
    for name in ('b2_rebound_execution_20261008','b2_joint_learning_review_20261009','b2_joint_admission_design_20261009'):
        folder=OUT.parent/name
        manifest=folder/'delivery_manifest.json';files[str(manifest)]=sha(manifest)
        for rel,meta in read(manifest)['files'].items():files[str(folder/rel)]=meta['sha256']
    for path in OUT.glob('*.py'):files[str(path)]=sha(path)
    for path in (OUT/'candidate.json',OUT/'offline_seed.json',ROOT/'docs/superpowers/plans/2026-10-09-b2-joint-preflight.md'):
        files[str(path)]=sha(path)
    verify_files(files);c=proposal()
    binding=dict(version='b2_joint_preflight_binding_v1',status='PREPARED_NOT_AUTHORIZED',implementation_directory=str(OUT),
        proposal_sha256=PROPOSAL_PIN,scope_key=c['draft_scope_key'],parent_common_key=c['parent']['common_key'],
        executable=old['executable'],files=files,inventories=old['inventories'],
        training_admitted=False,static_authorized=False,dynamic_authorized=False)
    write(OUT/'candidate_binding.json',binding)
    request=dict(version='b2_joint_preflight_authorization_request_v1',status='REQUESTED_NOT_AUTHORIZED',explicit_user_approval=False,
        authorization_text=None,binding_sha256=sha(OUT/'candidate_binding.json'),proposal_sha256=PROPOSAL_PIN,
        scope_key=c['draft_scope_key'],limits=c['proposed_limits'],cumulative_before=225,cumulative_ceiling_if_fully_executed=237,
        automatic_tracking='PAUSED',training_admitted=False,retry_allowed=False,
        purpose='B.2 four J poses: fixed 8 action stress episodes plus 4 engineered recovery episodes; no separate static or learning',
        grant_instructions='Only after separate explicit human approval of this bound candidate, create a new b2_joint_preflight_grant_v1 OPEN record with exact pins/limits and approval text. This request itself is not a grant.')
    write(OUT/'authorization_request.json',request)
    print(dict(bound_inputs=len(files),binding_sha256=sha(OUT/'candidate_binding.json'),new_physics=0))
if __name__=='__main__':main()
