"""Read-only source/profile/test-report/document/seal verification. No runtime."""
from pathlib import Path
import json,re,sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from small_bound_profile import ROOT,read,sha,digest,canonical,validate_outer_contract
from prepare_candidate import source_proof
from update_documents import DOCS


def main():
    checks=0
    def check(condition,message):
        nonlocal checks
        if not condition:raise AssertionError(message)
        checks+=1
    c=read(OUT/'qualification_candidate.json');t=read(OUT/'offline_tests.json');e=read(OUT/'command_equivalence.json')
    proof=source_proof()
    check(c['status']=='OFFLINE_CANDIDATE_NOT_ADMITTED','candidate status')
    for flag in ['training_admitted','execution_authorized','numeric_verified','physical_preflight_verified','runtime_backend_implemented','runtime_backend_verified']:
        check(c[flag] is False,'unearned '+flag)
    check(c['automatic_tracking']=='PAUSED','tracking')
    check(c['profile_sha256']==validate_outer_contract(c['outer_contract']),'physical contract')
    check(proof==read(OUT/'source_bindings.json') and digest(proof)==c['source_bindings_sha256'],'source proof')
    check(proof['old_sealed_file_count']==730 and proof['production_input_count']==1057,'source counts')
    check(c['actual']['cumulative_dynamic']==208,'cumulative')
    for name,value in c['actual'].items():
        if name!='cumulative_dynamic':check(value==0,'unearned compute '+name)
    for rel,pin in c['execution_code_sha256'].items():check(sha(ROOT/rel)==pin,'candidate code '+rel)
    check(t['passed'] is True and t['pytest_exit']==0,'offline tests')
    for name,pin in t['test_source_sha256'].items():check(sha(OUT/name)==pin,'test changed '+name)
    check(t['inspect_exit']==0 and t['unadmitted_execute_exit']!=0 and 'PermissionError' in t['unadmitted_execute_output'],'CLI guard')
    check(e['passed'] and e['matched_command_states']==9750 and e['active_command_states']==7362 and e['zero_residual_command_checks']==9750,'command arithmetic')
    check(sum(s['stored_cycles'] for s in e['sources'])==9752 and sum(len(s['skipped_states']) for s in e['sources'])==2,'retained command gaps')
    for s in e['sources']:check(sha(ROOT/s['path'])==s['sha256'],'historical command source')
    check(c['limits']['physical_attempts']==21 and c['limits']['formal_batches']==2000 and c['limits']['cumulative_dynamic_limit']==229,'unopened proposal')
    check(c['limits']['numeric_qualification']==dict(max_synthetic_update_batches=4,max_test_state_forward_evaluations=32),'unopened numeric proposal')
    for name in DOCS:
        current=(ROOT/name).read_bytes();snapshot=(OUT/'document_snapshots'/name).read_bytes()
        check(current==snapshot,'current document snapshot '+name)
        check(b'pc12-current' in current,'current document entry '+name)
    report=(OUT/'结果说明.md').read_text(encoding='utf8')
    for text in ['9750','9752','208','PAUSED','物理backend','数值','1057','730']:
        check(text in report,'report limit '+text)
    plan=ROOT/'docs/superpowers/plans/2026-10-07-small-boundary-fair-comparison.md'
    check(sha(plan)==read(OUT.parent/'small_boundary_registration_20261007/delivery_manifest.json')['files']['implementation_plan_snapshot.md']['sha256'],'PC11 frozen plan unchanged')
    review=read(OUT/'review.json')
    check(review['critical_open']==review['important_open']==0,'review issues still open')
    if (OUT/'delivery_manifest.json').exists():
        for name,item in read(OUT/'delivery_manifest.json')['files'].items():
            check(sha(OUT/name)==item['sha256'] and (OUT/name).stat().st_size==item['bytes'],'new seal '+name)
    print(json.dumps(dict(passed=True,checks=checks,pure_tests=t['tests_passed'],old_files=730,shared_inputs=1057,
        actual_new_compute=0,cumulative_dynamic=208,status=c['status']),ensure_ascii=False))


if __name__=='__main__':main()
