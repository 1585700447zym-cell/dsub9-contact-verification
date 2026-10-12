"""One explicitly authorized fresh cycle following the atomic-writer repair."""
from copy import deepcopy
from pathlib import Path
from . import resumed_force_cycle as prior
from .force_failure_cycle import (ROOT,IMPLEMENTATION,IMPLEMENTATION_PIN,PREVIOUS,REPAIRED,OLD,
    cycle_config,validate_config,verify_initial_chain,read,validate_case,RunLedger,write)
from .admission import digest,canonical,verify_files
from .repaired_cycle import pinned_manifest
from .runtime import select_runtime,active_package

DELIVERY=ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
CONFIG=DELIVERY/'config.json'
PREVIOUS_ATTEMPT=prior.DELIVERY
PREVIOUS_PIN='78c7f13fe1426fe18f29ceeeceaf71babfb70ebb9bf9a8ba42601cffcaa1a42b'
PREVIOUS_AUTH_PIN='a4be2e34446d55d84b8b87f7883f30c9ff5d60bcdb7f36936cec376f7b2d7b6d'
REPAIR=ROOT/'deliverables/learning_chain/b2_atomic_write_fix_20260929'
REPAIR_PIN='b6ba291df43df24cc1bc6f3c84118fa19d36d89b6a03ee5adc4c68b8e0eaf3f2'

def proposed_budget():
    r=prior.proposed_budget()
    r.update(previous_dynamic_starts=44,cumulative_dynamic_cap=76)
    return r

def validate_budget(budget):
    if canonical(budget)!=canonical(proposed_budget()):raise ValueError('Unapproved fresh cycle budget')

def validate_authorization(record,candidate_pin):
    if (not isinstance(record,dict) or record.get('version')!='force_cycle_user_authorization_v1'
            or record.get('approved') is not True or record.get('candidate_sha256')!=candidate_pin
            or not isinstance(record.get('user_confirmation'),str) or not record['user_confirmation'].strip()
            or record.get('prior_authorization_sha256')!=PREVIOUS_AUTH_PIN
            or record.get('manual_fresh_restart_after_repair') is not True):
        raise ValueError('Explicit fresh restart authorization required')
    validate_budget(record.get('budget'))

def verify_parent():
    repair=pinned_manifest(REPAIR/'assessment.json',REPAIR_PIN)
    if repair['status']!='windows_json_replacement_fix_verified':raise ValueError('Repair not verified')
    verify_files(ROOT,repair['files_sha256']);verify_files(ROOT,repair['source_sha256'])
    verify_files(ROOT,read(REPAIR/'previous_files.json'))
    old=pinned_manifest(PREVIOUS_ATTEMPT/'candidate.json',PREVIOUS_PIN)
    pinned_manifest(PREVIOUS_ATTEMPT/'authorization.json',PREVIOUS_AUTH_PIN)
    snapshots=read(REPAIR/'parent_source_snapshots.json')
    for name,pin in old['source_sha256'].items():
        if digest(ROOT/snapshots.get(name,name))!=pin:raise ValueError('Historical source changed: '+name)
    verify_files(ROOT,old['evidence_sha256'])
    totals=read(PREVIOUS_ATTEMPT/'run/cumulative_budget.json')
    updates=read(PREVIOUS_ATTEMPT/'run/training_episodes/update_budget.json')
    if (totals['cumulative_dynamic_starts']!=44 or totals['new_dynamic_starts']!=8
            or updates['completed']!=144 or read(PREVIOUS_ATTEMPT/'process_exit.json')['returncode']==0):
        raise ValueError('Prior failed cycle accounting changed')
    return repair

def cycle_sources():
    r=prior.cycle_sources();r[CONFIG.relative_to(ROOT).as_posix()]=digest(CONFIG)
    for name in ('run_tests.py','prepare_evidence.py','process_probe.py','qualify.py','dashboard.html'):
        r[(DELIVERY/name).relative_to(ROOT).as_posix()]=digest(DELIVERY/name)
    return r

def reuse_baseline(run):
    receipt=read(DELIVERY/'baseline_reuse.json')
    if receipt.get('passed') is not True:raise ValueError('Baseline reuse not verified')
    verify_files(ROOT,receipt['input_sha256'])
    folder=Path(run)/'baseline';folder.mkdir(exist_ok=False)
    write(folder/'results.json',receipt['results']);write(folder/'reuse.json',receipt)

def verify_candidate(path,expected_digest):
    path=Path(path)
    if path.resolve()!=(DELIVERY/'candidate.json').resolve() or digest(path)!=expected_digest:
        raise ValueError('Candidate path or pin changed')
    r=read(path)
    if (r.get('capability')!='force_only_cycle_v1' or r.get('synthetic_only') is not False
            or r.get('technical_ready') is not True or r.get('requires_user_authorization') is not True
            or r.get('repair_assessment_sha256')!=REPAIR_PIN
            or r.get('implementation_manifest_sha256')!=IMPLEMENTATION_PIN):raise ValueError('Invalid repaired qualification')
    validate_config(r['config']);validate_budget(r['budget']);verify_parent()
    if r['source_sha256']!=cycle_sources():raise ValueError('Current source changed')
    verify_files(ROOT,r['evidence_sha256'])
    repaired=read(REPAIRED/'admission.json')
    select_runtime(REPAIRED/'runtime.json',expected_digest=repaired['runtime_record_sha256'])
    from tools.validation.verify_residual_interface import qualified_runtime
    if canonical(qualified_runtime(active_package()))!=canonical(r['runtime']):raise ValueError('Qualified runtime changed')
    return deepcopy(r)

class ForceAdmission(prior.ForceAdmission):
    def verify(self,case=None):
        path=DELIVERY/'authorization.json'
        if not self.authorization_digest or not path.exists():raise ValueError('Missing explicit user authorization')
        if digest(path)!=self.authorization_digest:raise ValueError('User authorization pin changed')
        validate_authorization(read(path),self.expected_digest)
        r=verify_candidate(self.path,self.expected_digest)
        if case is not None:validate_case(case)
        r.update(collection_admitted=True,update_admitted=True,restore_admitted=True,authorization_sha256=self.authorization_digest)
        self._record=r;return deepcopy(r)

def accounting(state):
    n=state['dynamic_starts']
    if type(n) is not int or not 0<=n<=32 or len(state['attempts'])!=n:raise ValueError('Invalid fresh cycle accounting')
    return dict(previous_dynamic_starts=44,new_dynamic_starts=n,cumulative_dynamic_starts=44+n,
        new_dynamic_cap=32,cumulative_cap=76,formal_update_cap=4500,automatic_retry=False,
        old_remaining_budget_retired=True)

class ForceLedger(RunLedger):
    def start(self,stage,identity):
        accounting(self.state)
        if stage not in self.CAPS:raise RuntimeError('Unknown stage')
        for earlier in list(self.CAPS)[:list(self.CAPS).index(stage)]:
            rows=[r for r in self.state['attempts'] if r['stage']==earlier]
            if len(rows)!=self.CAPS[earlier] or any(r['status']!='finished' for r in rows):
                raise RuntimeError('Prior stage incomplete: '+earlier)
        super().start(stage,identity)
        write(self.path.parent/'cumulative_budget.json',accounting(self.state))
