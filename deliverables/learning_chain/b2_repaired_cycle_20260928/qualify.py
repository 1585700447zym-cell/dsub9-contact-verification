"""Bind repaired runtime, unchanged learning contract and explicit revised budget."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.learning.repaired_cycle import (DELIVERY,OLD,REPAIR,PARENT_PIN,verify_parent,RepairedAdmission,RepairedLedger,
    read,require_learning_runtime_unchanged,require_complete_tests,pinned_manifest)
from tools.learning.bounded_contact import bounded_config,current_sources
from tools.learning.runtime import select_runtime,active_package
from tools.learning.admission import digest,verify_files
from tools.learning.admitted_collection import _write_json as write
REQUIRED_TESTS_PIN='d9c25de0c0f500662b243f24cc1629c0d1169afdacd8b82ad0f8a88baa4f5045'


def main():
    if (DELIVERY/'admission.json').exists():raise FileExistsError('Never overwrite qualification')
    parent=verify_parent()
    auth=read(DELIVERY/'authorization.json')
    if (auth['new_dynamic_cap']!=36 or auth['cumulative_dynamic_cap']!=44 or
        auth['previous_dynamic_starts']!=8 or auth['formal_optimizer_batches']!=4500 or
        auth['new_synthetic_updates']!=0 or auth['new_separate_static_initializations']!=0 or
        auth['stages']!=RepairedLedger.CAPS):raise ValueError('Budget approval mismatch')
    repair=read(REPAIR/'assessment.json')
    if (repair['canary_overflow_bytes']!={'original':4,'fixed':0} or
        not repair['matched_compiler_control_access_violation'] or
        repair['diagnostic_episode']['outcome']['task_outcome']!='FULL_SUCCESS' or
        repair['diagnostic_episode']['guard_facts']['invalid_reasons'] or
        repair['diagnostic_episode']['guard_facts']['contact_reasons'] or
        repair['diagnostic_episode']['guard_facts']['motion_reasons']):raise ValueError('Repair evidence insufficient')
    package=read(REPAIR/'horizon_fixed_runtime.json')
    if package['files']['mujoco/mujoco.dll']!='4007b6b0956eabc1a3892ac3c3f0947d0e98b90a0604cd8ffcbb795227274047':
        raise ValueError('Wrong repaired binary')
    runtime_record=dict(version='native313_repair_runtime_v1',
        module_file=str(Path(package['package'])/'mujoco/__init__.py'),files=package['files'],
        repair_manifest_sha256=digest(REPAIR/'manifest.json'),scope='bounded 100um development and frozen 95um evaluation')
    tests=read(DELIVERY/'test_binding.json');review=read(DELIVERY/'review.json')
    if (tests['exit_code']!=0 or tests['source_sha256']!=current_sources() or
        any(tests['forbidden_call_counts'].values()) or digest(DELIVERY/'tests.xml')!=tests['report_sha256'] or
        digest(DELIVERY/'run_tests.py')!=tests['runner_sha256']):
        raise ValueError('Tests failed, unbound, or executed forbidden calls')
    cases=list(ET.parse(DELIVERY/'tests.xml').getroot().iter('testcase'))
    require_complete_tests(tests['test_ids'],pinned_manifest(DELIVERY/'required_tests.json',REQUIRED_TESTS_PIN))
    if (len(cases)!=tests['tests'] or any(list(case) for case in cases) or
        sorted(c.attrib['classname']+'::'+c.attrib['name'] for c in cases)!=tests['test_ids']):
        raise ValueError('Test receipt differs')
    if review['unresolved_critical'] or review['unresolved_important']:raise ValueError('Unresolved review')
    static=read(OLD/'checks/preflight.json');synthetic=read(OLD/'checks/synthetic_probe.json')
    if not static['all_passed'] or not static['holdout_not_previously_used'] or synthetic['optimizer_batches']!=3 or not synthetic['all_state_equal']:
        raise ValueError('Missing inherited static/restoration evidence')
    verify_files(ROOT,read(OLD/'admission.json')['evidence_sha256'])
    write(DELIVERY/'runtime.json',runtime_record)
    runtime_pin=digest(DELIVERY/'runtime.json');select_runtime(DELIVERY/'runtime.json',expected_digest=runtime_pin)
    from tools.validation.verify_residual_interface import qualified_runtime
    runtime=qualified_runtime(active_package())
    require_learning_runtime_unchanged(parent['runtime'],runtime)
    names=('authorization.json','runtime.json','test_binding.json','tests.xml','required_tests.json','review.json','qualify.py','run_tests.py',
           'source_snapshot/runtime.py','source_snapshot/environment.py')
    evidence={str((DELIVERY/name).relative_to(ROOT).as_posix()):digest(DELIVERY/name) for name in names}
    for name in ('environment.json','requirements.lock.txt'):
        path=ROOT/'deliverables/residual_interface/learning_tensor_20260924'/name
        evidence[path.relative_to(ROOT).as_posix()]=digest(path)
    record=dict(capability='repaired_bounded_contact_cycle_v1',parent_admission_sha256=PARENT_PIN,
        synthetic_only=False,collection_admitted=True,update_admitted=True,restore_admitted=True,
        config=bounded_config(),source_sha256=current_sources(),runtime_record_sha256=runtime_pin,
        runtime=runtime,evidence_sha256=evidence,budget=auth,
        inherited_static=static,baseline_reassessment_required=True,
        holdout_permission='Freeze final checkpoint first, then B2 dynamic gate before SAC; no tuning')
    write(DELIVERY/'admission.json',record)
    pin=digest(DELIVERY/'admission.json');RepairedAdmission(DELIVERY/'admission.json',expected_digest=pin)
    write(DELIVERY/'admission_pin.json',dict(sha256=pin))
    print(json.dumps(dict(admitted=True,sources=len(record['source_sha256']),tests=len(cases),sha256=pin)))


if __name__=='__main__':main()
