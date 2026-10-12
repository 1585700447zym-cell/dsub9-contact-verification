"""Freeze this cycle's evidence without launching dynamics or optimization."""
from pathlib import Path
import json,os,sys,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
from tools.learning.atomic_repaired_cycle import (DELIVERY,IMPLEMENTATION_PIN,PREVIOUS,REPAIRED,OLD,REPAIR,
    PREVIOUS_ATTEMPT,REPAIR_PIN,cycle_config,cycle_sources,proposed_budget,verify_parent,verify_candidate)
from tools.learning.admission import digest,verify_files
from tools.learning.repaired_cycle import read,require_complete_tests
from tools.learning.admitted_collection import _write_json as write

def main():
    if any((DELIVERY/n).exists() for n in ('candidate.json','authorization.json','started.json')):
        raise FileExistsError('Never overwrite a qualification or execution')
    repair=verify_parent();sources=cycle_sources()
    tests=read(DELIVERY/'final_binding.json');required=read(DELIVERY/'required_tests.json')
    require_complete_tests(tests['test_ids'],required)
    if (tests['source_unchanged'] is not True or tests['exit_code']!=0 or tests['tests_with_failure_or_error']!=0
            or tests['source_sha256']!=sources or any(tests['forbidden_call_counts'].values())
            or tests['runner_sha256']!=digest(DELIVERY/'run_tests.py') or tests['report_sha256']!=digest(DELIVERY/'final.xml')):
        raise ValueError('Fresh test binding failed')
    rows=list(ET.parse(DELIVERY/'final.xml').getroot().iter('testcase'))
    require_complete_tests([r.attrib['classname']+'::'+r.attrib['name'] for r in rows],required)
    if any(r.find(k) is not None for r in rows for k in ('failure','error','skipped')):raise ValueError('Failed or skipped checks')
    historical=read(REPAIR/'final_related_binding.json');oldtests=read(PREVIOUS_ATTEMPT/'test_binding.json')
    if (historical['tests']!=112 or oldtests['tests']!=212
            or any(historical['forbidden_call_counts'].values()) or any(oldtests['forbidden_call_counts'].values())
            or historical['exit_code'] or oldtests['exit_code']):raise ValueError('Inherited checks invalid')
    review=read(DELIVERY/'review.json')
    if review['unresolved_critical'] or review['unresolved_important'] or review['source_sha256']!=sources:
        raise ValueError('Review unresolved or source changed')
    identity=read(DELIVERY/'initial_identity_preflight.json');baseline=read(DELIVERY/'baseline_reuse.json')
    if (identity['initial_state_exact_except_binding_and_version'] is not True or any(identity['forbidden_call_counts'].values())
            or identity['source_sha256']!=sources or not identity['independent_points_still_unused'] or not baseline['passed']):
        raise ValueError('Initial identity or baseline incomplete')
    verify_files(ROOT,baseline['input_sha256'])
    for old in (OLD,REPAIRED,PREVIOUS,PREVIOUS_ATTEMPT,DELIVERY):
        if (old/'run/holdout_b2').exists() or (old/'run/holdout_sac').exists():raise ValueError('Independent points already used')
    for source,target in (('README.md','执行方案_冻结.md'),('实施记录.md','实施记录_冻结.md')):
        with (DELIVERY/target).open('xb') as f:f.write((DELIVERY/source).read_bytes())
    names=('config.json','执行方案_冻结.md','实施记录_冻结.md','baseline_reuse.json','initial_identity_preflight.json',
        'final_binding.json','final.xml','required_tests.json','review.json','独立审查.md','run_tests.py',
        'prepare_evidence.py','qualify.py','process_probe.py','dashboard.html')
    evidence={(DELIVERY/n).relative_to(ROOT).as_posix():digest(DELIVERY/n) for n in names}
    r=dict(capability='force_only_cycle_v1',synthetic_only=False,technical_ready=True,requires_user_authorization=True,
        implementation_manifest_sha256=IMPLEMENTATION_PIN,repair_assessment_sha256=REPAIR_PIN,
        config=cycle_config(),budget=proposed_budget(),source_sha256=sources,evidence_sha256=evidence,
        runtime=read(REPAIRED/'admission.json')['runtime'],baseline_reused=True,
        validation=dict(fresh_checks=len(rows),inherited_repair_checks=112,inherited_cycle_checks=212),
        independent_permission='Fixed episode 12; independent B2 scope gate then SAC, without tuning.')
    write(DELIVERY/'candidate.json',r);pin=digest(DELIVERY/'candidate.json');verify_candidate(DELIVERY/'candidate.json',pin)
    write(DELIVERY/'candidate_pin.json',dict(sha256=pin,technical_ready=True,execution_authorized=False))
    print(json.dumps(dict(technical_ready=True,sha256=pin,tests=len(rows),sources=len(sources))))

if __name__=='__main__':main()
