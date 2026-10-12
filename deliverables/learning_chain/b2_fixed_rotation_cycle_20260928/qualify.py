"""Issue an immutable qualification only after approved budget and related checks."""
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.learning.fixed_rotation_cycle import (DELIVERY,PREVIOUS,OLD,CONFIG,PARENT_PIN,FixedAdmission,
    FixedLedger,fixed_config,fixed_sources,verify_previous,validate_fixed_config)
from tools.learning.runtime import select_runtime,active_package
from tools.learning.admission import digest,canonical,verify_files
from tools.learning.repaired_cycle import read,pinned_manifest,require_complete_tests
from tools.learning.admitted_collection import _write_json as write
REQUIRED_TESTS_PIN='b3e1865417186c76408fabf9add7cb20e66a432dee40f379f73d58aaa6dde1e5'


def main():
    if (DELIVERY/'admission.json').exists():raise FileExistsError('Never overwrite an admission')
    parent=verify_previous();auth=read(DELIVERY/'authorization.json')
    if (auth['previous_dynamic_starts']!=27 or auth['new_dynamic_cap']!=32 or
        auth['cumulative_dynamic_cap']!=59 or auth['formal_optimizer_batches']!=4500 or
        auth['new_synthetic_updates']!=0 or auth['new_separate_static_initializations']!=0 or
        auth['action_scale']!=fixed_config()['action']['scale'] or auth['stages']!=FixedLedger.CAPS or
        auth['automatic_retry'] is not False or auth['old_remaining_budget_retired'] is not True or
        digest(ROOT/auth['approved_plan'])!=auth['plan_sha256']):raise ValueError('Approval differs from executed plan')
    validate_fixed_config(read(CONFIG))
    tests=read(DELIVERY/'test_binding.json')
    if (tests['exit_code']!=0 or tests['source_sha256']!=fixed_sources() or any(tests['forbidden_call_counts'].values()) or
        tests['report_sha256']!=digest(DELIVERY/'tests.xml') or tests['runner_sha256']!=digest(DELIVERY/'run_tests.py')):
        raise ValueError('Unbound or failed tests')
    required=pinned_manifest(DELIVERY/'required_tests.json',REQUIRED_TESTS_PIN)
    require_complete_tests(tests['test_ids'],required)
    cases=list(ET.parse(DELIVERY/'tests.xml').getroot().iter('testcase'))
    if (len(cases)!=tests['tests'] or any(list(c) for c in cases) or
        sorted(c.attrib['classname']+'::'+c.attrib['name'] for c in cases)!=tests['test_ids']):raise ValueError('Incomplete test report')
    review=read(DELIVERY/'review.json')
    if review['unresolved_critical'] or review['unresolved_important']:raise ValueError('Unresolved review')
    if review['source_sha256']!=fixed_sources():raise ValueError('Review resolution sources changed')
    reuse=read(DELIVERY/'baseline_reuse.json');identity=read(DELIVERY/'initial_identity_preflight.json')
    verify_files(ROOT,reuse['input_sha256'])
    if (reuse['passed'] is not True or reuse['zero_command_comparisons']!=24429 or
        identity['initial_state_exact_except_binding'] is not True or any(identity['forbidden_call_counts'].values())):
        raise ValueError('Baseline reuse or initial state is not qualified')
    static=read(OLD/'checks/preflight.json');synthetic=read(OLD/'checks/synthetic_probe.json')
    parent_old=read(OLD/'admission.json');verify_files(ROOT,parent_old['evidence_sha256'])
    if (not static['all_passed'] or not static['holdout_not_previously_used'] or
        synthetic['optimizer_batches']!=3 or not synthetic['all_state_equal']):raise ValueError('Inherited checks incomplete')
    if (PREVIOUS/'run/holdout_b2').exists() or (OLD/'run/holdout_b2').exists():raise ValueError('Holdout already used')
    select_runtime(PREVIOUS/'runtime.json',expected_digest=parent['runtime_record_sha256'])
    from tools.validation.verify_residual_interface import qualified_runtime
    if canonical(qualified_runtime(active_package()))!=canonical(parent['runtime']):raise ValueError('Runtime changed')
    names=('authorization.json','parent_source_snapshots.json','previous_files.json','baseline_reuse.json',
        'initial_identity_preflight.json','test_binding.json','tests.xml','required_tests.json','review.json',
        'run_tests.py','prepare_evidence.py','qualify.py')
    evidence={str((DELIVERY/n).relative_to(ROOT).as_posix()):digest(DELIVERY/n) for n in names}
    evidence[auth['approved_plan']]=auth['plan_sha256']
    evidence.update({str((OLD/n).relative_to(ROOT).as_posix()):digest(OLD/n) for n in ('checks/preflight.json','checks/synthetic_probe.json')})
    record=dict(capability='fixed_rotation_cycle_v1',parent_admission_sha256=PARENT_PIN,synthetic_only=False,
        collection_admitted=True,update_admitted=True,restore_admitted=True,config=fixed_config(),
        source_sha256=fixed_sources(),evidence_sha256=evidence,runtime=parent['runtime'],budget=auth,
        inherited_static=static,baseline_reused=True,holdout_permission='Frozen checkpoint, B2 dynamic gate, then SAC; never tune from holdout')
    write(DELIVERY/'admission.json',record)
    pin=digest(DELIVERY/'admission.json');FixedAdmission(DELIVERY/'admission.json',expected_digest=pin)
    write(DELIVERY/'admission_pin.json',dict(sha256=pin))
    print('Fixed rotation admitted:',pin,'tests:',len(cases),'new physical/optimizer calls: 0')


if __name__=='__main__':main()
