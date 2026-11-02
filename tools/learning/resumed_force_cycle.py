"""Manually authorized resumption after a zero-physics Windows entry rejection."""
from copy import deepcopy
from pathlib import Path
from . import force_failure_cycle as prior
from .force_failure_cycle import (ROOT,IMPLEMENTATION,IMPLEMENTATION_PIN,PREVIOUS,REPAIRED,OLD,
    cycle_config,validate_config,proposed_budget,validate_budget,validate_authorization,
    verify_initial_chain,read,validate_case)
from .admission import digest,canonical,verify_files
from .repaired_cycle import pinned_manifest
from .runtime import select_runtime,active_package

DELIVERY=ROOT/'deliverables/learning_chain/b2_force_failure_resumed_20260929'
CONFIG=DELIVERY/'config.json'
PREVIOUS_ATTEMPT=prior.DELIVERY
REPAIR=ROOT/'deliverables/learning_chain/b2_windows_parent_fix_20260929'
REPAIR_PIN='5cea89c66e25eed5fdc993b186d43e517b2a5cd4cc9ef868ffe5ed60cf6c90b0'


def verify_parent():
    repair=pinned_manifest(REPAIR/'assessment.json',REPAIR_PIN)
    if repair['status']!='windows_parent_identity_fix_verified':raise ValueError('Repair not verified')
    verify_files(ROOT,repair['files_sha256']);verify_files(ROOT,repair['source_sha256'])
    verify_files(ROOT,read(REPAIR/'previous_files.json'))
    snapshots=read(REPAIR/'parent_source_snapshots.json')
    old=read(PREVIOUS_ATTEMPT/'candidate.json')
    for name,pin in old['source_sha256'].items():
        if digest(ROOT/snapshots.get(name,name))!=pin:raise ValueError('Historical source changed: '+name)
    verify_files(ROOT,old['evidence_sha256'])
    failed=read(PREVIOUS_ATTEMPT/'launch_failure_assessment.json')
    if (failed['kind']!='entry_rejection' or failed['new_dynamic_ledger_starts']!=0
            or failed['new_physical_starts']!=0 or failed['new_formal_optimizer_batches']!=0
            or (PREVIOUS_ATTEMPT/'run/ledger.json').exists()):
        raise ValueError('Prior attempt consumed execution budget')
    prior.verify_parent()
    return repair


def cycle_sources():
    sources=prior.cycle_sources();sources[CONFIG.relative_to(ROOT).as_posix()]=digest(CONFIG)
    return sources


def verify_candidate(path,expected_digest):
    path=Path(path)
    if path.resolve()!=(DELIVERY/'candidate.json').resolve() or digest(path)!=expected_digest:
        raise ValueError('Candidate path or pin changed')
    r=read(path)
    if (r.get('capability')!='force_only_cycle_v1' or r.get('synthetic_only') is not False
            or r.get('technical_ready') is not True or r.get('requires_user_authorization') is not True
            or r.get('repair_assessment_sha256')!=REPAIR_PIN
            or r.get('implementation_manifest_sha256')!=IMPLEMENTATION_PIN):
        raise ValueError('Invalid resumed qualification')
    validate_config(r['config']);validate_budget(r['budget']);verify_parent()
    if r['source_sha256']!=cycle_sources():raise ValueError('Current resumed source changed')
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
        auth=read(path);validate_authorization(auth,self.expected_digest)
        if (auth.get('prior_authorization_sha256')!=digest(PREVIOUS_ATTEMPT/'authorization.json')
                or auth.get('manual_resumption_after_repair') is not True):
            raise ValueError('Manual resumption authorization required')
        r=verify_candidate(self.path,self.expected_digest)
        if case is not None:validate_case(case)
        r.update(collection_admitted=True,update_admitted=True,restore_admitted=True,
            authorization_sha256=self.authorization_digest)
        self._record=r;return deepcopy(r)
