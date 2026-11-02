"""Versioned finite-cycle qualification; technical evidence is not user approval."""
from copy import deepcopy
import io
from pathlib import Path
import torch
from .runtime import ROOT,select_runtime,active_package
from .admission import canonical,digest,verify_files
from .admitted_collection import _write_json as write
from .bounded_contact import BoundedAdmission,BoundedUpdater,RunLedger,validate_case
from .force_failure_preparation import force_config
from .episode_rules import FORCE_ONLY
from .fixed_rotation_cycle import fixed_sources
from .repaired_cycle import read,pinned_manifest,compare_initial_states as compare_empty

DELIVERY=ROOT/'deliverables/learning_chain/b2_force_failure_cycle_20260929'
IMPLEMENTATION=ROOT/'deliverables/learning_chain/b2_force_failure_implementation_20260928'
PREVIOUS=ROOT/'deliverables/learning_chain/b2_fixed_rotation_cycle_20260928'
REPAIRED=ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928'
OLD=ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927'
CONFIG=DELIVERY/'config.json'
IMPLEMENTATION_PIN='9f4a277a8c0b83b9f4f6eae011ff03c8bcac78e5fe3c8986d5f4a86b3b40257b'

def cycle_config():
    c=force_config();c['version']='force_only_cycle_v1'
    c['execution'].pop('authorized_dynamic_starts');c['execution'].pop('authorized_optimizer_calls')
    c['execution'].update(preparation_only=False,requires_separate_user_authorization=True)
    return c

def validate_config(config):
    if canonical(config)!=canonical(cycle_config()):raise ValueError('Unregistered force cycle configuration')

def proposed_budget():
    return dict(previous_dynamic_starts=36,new_dynamic_cap=32,cumulative_dynamic_cap=68,
        formal_optimizer_batches=4500,new_synthetic_updates=0,new_separate_static_initializations=0,
        extra_diagnostic_physics=0,stages=dict(RunLedger.CAPS),force_failure_stop=dict(consecutive=2,total=3),
        automatic_retry=False,old_remaining_budget_retired=True,initial_state='same_empty_state',
        final_checkpoint='fixed_episode_12',baseline_reused=True)

def validate_budget(budget):
    if canonical(budget)!=canonical(proposed_budget()):raise ValueError('Unapproved force cycle budget')

def validate_authorization(record,candidate_pin):
    if (not isinstance(record,dict) or record.get('version')!='force_cycle_user_authorization_v1'
            or record.get('approved') is not True or record.get('candidate_sha256')!=candidate_pin
            or not isinstance(record.get('user_confirmation'),str) or not record['user_confirmation'].strip()):
        raise ValueError('Explicit user authorization required')
    validate_budget(record.get('budget'))

def verify_parent_files(root,manifest):
    # Additions belong to the child version; inherited bytes cannot be changed.
    verify_files(root,manifest)

def verify_parent():
    parent=pinned_manifest(IMPLEMENTATION/'verification.json',IMPLEMENTATION_PIN)
    verify_parent_files(ROOT,parent['files']);verify_parent_files(ROOT,parent['source_sha256'])
    for inventory in (IMPLEMENTATION/'previous_files.json',PREVIOUS/'previous_files.json'):
        verify_parent_files(ROOT,read(inventory))
    snapshots=read(IMPLEMENTATION/'parent_source_snapshots.json')
    fixed=read(PREVIOUS/'admission.json')
    for name,pin in fixed['source_sha256'].items():
        if digest(ROOT/snapshots.get(name,name))!=pin:raise ValueError('Historical source changed: '+name)
    verify_files(ROOT,fixed['evidence_sha256'])
    if (read(IMPLEMENTATION/'assessment.json')['status']!='implementation_protocol_verification_passed'
            or read(PREVIOUS/'run/cumulative_budget.json')['cumulative_dynamic_starts']!=36
            or read(PREVIOUS/'run/training_episodes/update_budget.json')['attempted']!=500):
        raise ValueError('Previous results or budget changed')
    return fixed

def cycle_sources():
    sources=fixed_sources();sources[CONFIG.relative_to(ROOT).as_posix()]=digest(CONFIG)
    return sources

def verify_candidate(path,expected_digest):
    path=Path(path)
    if path.resolve()!=(DELIVERY/'candidate.json').resolve() or digest(path)!=expected_digest:
        raise ValueError('Candidate path or pin changed')
    r=read(path)
    if (r.get('capability')!='force_only_cycle_v1' or r.get('synthetic_only') is not False
            or r.get('technical_ready') is not True or r.get('requires_user_authorization') is not True
            or r.get('implementation_manifest_sha256')!=IMPLEMENTATION_PIN):
        raise ValueError('Invalid technical qualification')
    validate_config(r['config']);validate_budget(r['budget']);verify_parent()
    if r['source_sha256']!=cycle_sources():raise ValueError('Current execution source changed')
    verify_files(ROOT,r['evidence_sha256'])
    repaired=read(REPAIRED/'admission.json')
    select_runtime(REPAIRED/'runtime.json',expected_digest=repaired['runtime_record_sha256'])
    from tools.validation.verify_residual_interface import qualified_runtime
    if canonical(qualified_runtime(active_package()))!=canonical(r['runtime']):raise ValueError('Qualified runtime changed')
    return deepcopy(r)

class ForceCycleUpdater(BoundedUpdater):
    config_validator=staticmethod(validate_config)

class ForceAdmission(BoundedAdmission):
    episode_rules=FORCE_ONLY
    updater_type=ForceCycleUpdater
    def __init__(self,path,*,expected_digest,authorization_digest):
        self.authorization_digest=authorization_digest
        super().__init__(path,expected_digest=expected_digest)
    def verify(self,case=None):
        authorization=DELIVERY/'authorization.json'
        if not self.authorization_digest or not authorization.exists():
            raise ValueError('Missing explicit user budget authorization')
        if digest(authorization)!=self.authorization_digest:raise ValueError('User authorization pin changed')
        auth=read(authorization);validate_authorization(auth,self.expected_digest)
        r=verify_candidate(self.path,self.expected_digest)
        if case is not None:validate_case(case)
        r.update(collection_admitted=True,update_admitted=True,restore_admitted=True,
            authorization_sha256=self.authorization_digest)
        self._record=r;return deepcopy(r)

def accounting(state):
    n=state['dynamic_starts']
    if type(n) is not int or not 0<=n<=32 or len(state['attempts'])!=n:raise ValueError('Invalid force cycle accounting')
    return dict(previous_dynamic_starts=36,new_dynamic_starts=n,cumulative_dynamic_starts=36+n,
        new_dynamic_cap=32,cumulative_cap=68,formal_update_cap=4500,automatic_retry=False,
        old_remaining_budget_retired=True)

class ForceLedger(RunLedger):
    def start(self,stage,identity):
        accounting(self.state)
        if stage not in self.CAPS:raise RuntimeError('Unknown stage')
        for earlier in list(self.CAPS)[:list(self.CAPS).index(stage)]:
            rows=[r for r in self.state['attempts'] if r['stage']==earlier]
            if len(rows)!=self.CAPS[earlier] or any(r['status']!='finished' for r in rows):
                raise RuntimeError('Prior force cycle stage incomplete: '+earlier)
        super().start(stage,identity)
        write(self.path.parent/'cumulative_budget.json',accounting(self.state))

def compare_initial_states(before,after):
    if before['version']!='bounded_checkpoint_v2' or after['version']!='force_only_checkpoint_v1':
        raise ValueError('Unregistered initial checkpoint versions')
    normalized=deepcopy(after);normalized['version']=before['version']
    compare_empty(before,normalized)

def verify_initial_chain(chain):
    from . import bounded_checkpoint as cp
    path=PREVIOUS/'run/initial_checkpoint'
    manifest=read(path/'manifest.json')
    if digest(path/'state.pt')!=manifest['state_sha256']:raise ValueError('Old empty state changed')
    before=torch.load(io.BytesIO((path/'state.pt').read_bytes()),map_location='cpu',weights_only=True)
    if before['binding']['qualification_sha256']!=digest(PREVIOUS/'admission.json'):
        raise ValueError('Initial qualification binding differs')
    compare_initial_states(before,cp.capture(chain))
    return dict(initial_state_exact_except_binding_and_version=True,
        initial_checkpoint_manifest_sha256=digest(path/'manifest.json'),physical_calls=0,optimizer_calls=0)

def reuse_baseline(run):
    receipt=read(DELIVERY/'baseline_reuse.json')
    if receipt.get('passed') is not True:raise ValueError('Baseline reuse not verified')
    verify_files(ROOT,receipt['input_sha256'])
    folder=Path(run)/'baseline';folder.mkdir(exist_ok=False)
    write(folder/'results.json',receipt['results']);write(folder/'reuse.json',receipt)
