"""Freeze technical readiness only. A separate user approval is still mandatory."""
from pathlib import Path
import json,os,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.learning.resumed_force_cycle import (DELIVERY,IMPLEMENTATION,IMPLEMENTATION_PIN,PREVIOUS,
    REPAIRED,OLD,REPAIR,PREVIOUS_ATTEMPT,REPAIR_PIN,cycle_config,cycle_sources,proposed_budget,verify_parent,verify_candidate)
from tools.learning.admission import digest,canonical,verify_files
from tools.learning.repaired_cycle import read,require_complete_tests
from tools.learning.admitted_collection import _write_json as write

def freeze_docs(delivery):
    pairs=(('README.md','执行方案_冻结.md'),('实施记录.md','实施记录_冻结.md'))
    # Check the whole set before creating anything, and never rewrite snapshots.
    for source,target in pairs:
        if (delivery/target).exists() and (delivery/target).read_bytes()!=(delivery/source).read_bytes():
            raise ValueError('Document snapshot differs: '+target)
    for source,target in pairs:
        if not (delivery/target).exists():
            with (delivery/target).open('xb') as stream:stream.write((delivery/source).read_bytes())
    return tuple(target for source,target in pairs)

def main():
    if (DELIVERY/'candidate.json').exists():raise FileExistsError('Never overwrite a technical candidate')
    if (DELIVERY/'authorization.json').exists() or (DELIVERY/'started.json').exists():
        raise ValueError('This is preparation only; authorization/launch must not exist')
    verify_parent();sources=cycle_sources()
    tests=read(DELIVERY/'test_binding.json');required=read(DELIVERY/'required_tests.json')
    require_complete_tests(tests['test_ids'],required)
    inherited=set(read(IMPLEMENTATION/'required_tests.json')['tests'])
    inherited.update(read(PREVIOUS_ATTEMPT/'required_tests.json'))
    inherited.update(read(REPAIR/'final_related_binding.json')['test_ids'])
    new_names=('test_repair_and_failed_attempt_remain_verifiable',
        'test_child_routes_to_new_qualified_entry[False]','test_child_routes_to_new_qualified_entry[True]',
        'test_bound_runner_restored_even_on_error','test_missing_authorization_rejected_before_candidate',
        'test_old_authorization_cannot_authorize_new_candidate','test_candidate_wrong_path_rejected',
        'test_repair_pin_tampering_rejected','test_real_resumed_wrapper_parent_chain')
    inherited.update('tests.learning.test_resumed_force_cycle::'+name for name in new_names)
    if set(required)!=inherited:raise ValueError('Required test closure differs')
    if (tests['source_unchanged'] is not True or tests['exit_code']!=0 or tests['tests_with_failure_or_error']!=0 or tests['source_sha256']!=sources
            or any(tests['forbidden_call_counts'].values()) or tests['runner_sha256']!=digest(DELIVERY/'run_tests.py')
            or tests['report_sha256']!=digest(DELIVERY/'tests.xml')):raise ValueError('Test binding failed')
    rows=list(ET.parse(DELIVERY/'tests.xml').getroot().iter('testcase'))
    require_complete_tests([r.attrib['classname']+'::'+r.attrib['name'] for r in rows],required)
    if any(r.find(k) is not None for r in rows for k in ('failure','error','skipped')):raise ValueError('Failed or skipped checks')
    review=read(DELIVERY/'review.json')
    if review['unresolved_critical'] or review['unresolved_important'] or review['source_sha256']!=sources:
        raise ValueError('Review unresolved or source changed')
    identity=read(DELIVERY/'initial_identity_preflight.json');baseline=read(DELIVERY/'baseline_reuse.json')
    if (identity['initial_state_exact_except_binding_and_version'] is not True or any(identity['forbidden_call_counts'].values())
            or identity['source_sha256']!=sources or not identity['independent_points_still_unused'] or not baseline['passed']):
        raise ValueError('Initial identity/baseline preflight incomplete')
    verify_files(ROOT,baseline['input_sha256'])
    for old in (OLD,REPAIRED,PREVIOUS,DELIVERY):
        if (old/'run/holdout_b2').exists() or (old/'run/holdout_sac').exists():raise ValueError('Independent points already used')
    snapshots=freeze_docs(DELIVERY)
    names=('config.json',*snapshots,'baseline_reuse.json','initial_identity_preflight.json',
        'test_binding.json','tests.xml','required_tests.json','review.json','独立审查.md','run_tests.py',
        'prepare_evidence.py','qualify.py','process_probe.py')
    evidence={(DELIVERY/n).relative_to(ROOT).as_posix():digest(DELIVERY/n) for n in names}
    candidate=dict(capability='force_only_cycle_v1',synthetic_only=False,technical_ready=True,
        requires_user_authorization=True,implementation_manifest_sha256=IMPLEMENTATION_PIN,repair_assessment_sha256=REPAIR_PIN,
        config=cycle_config(),budget=proposed_budget(),source_sha256=sources,evidence_sha256=evidence,
        runtime=read(REPAIRED/'admission.json')['runtime'],baseline_reused=True,
        independent_permission='Frozen episode 12; strict zero B2 dynamic gate; then SAC. Never tune from independent results.')
    write(DELIVERY/'candidate.json',candidate);pin=digest(DELIVERY/'candidate.json')
    verify_candidate(DELIVERY/'candidate.json',pin)
    write(DELIVERY/'candidate_pin.json',dict(sha256=pin,technical_ready=True,execution_authorized=False))
    print(json.dumps(dict(technical_ready=True,execution_authorized=False,sha256=pin,tests=len(rows),sources=len(sources))))

if __name__=='__main__':main()
