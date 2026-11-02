"""Read-only integrity and physical-stop recheck for this version validation delivery."""
import json
from tools.validation.run_native313_validation import ROOT, OUT
from tools.validation.run_native313_stop import verify_static_dependencies
from tools.validation.validate_training_readiness import verify_hashes
from tools.validation.run_b2_search import read_run
from tools.validation.run_contact_candidate_stop import physical_tail_pass
from tools.validation.measure_readiness_stop import stop_qualified


def main():
    manifest=json.loads((OUT/'delivery_manifest.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT,manifest);verify_static_dependencies()
    for tag in ('stop_dt0p2_v1','stop_dt0p1_v1'):
        folder=OUT/tag
        audit=json.loads((folder/'audited_results.json').read_text(encoding='utf-8'))
        verify_hashes(ROOT,audit['source_sha256']);verify_hashes(ROOT,audit['corrected_protected_inputs'])
        tail=read_run(folder/'stop_extension.json.gz');final=tail['trace'][-1]
        stable=physical_tail_pass(tail['physical_stop_samples'],final['time_s'],audit['timestep'])
        passed=stop_qualified(phase=final['phase'],events=tail['events'],recorded_time_s=final['time_s'],
                             deadline_s=audit['stop_time_s']+2.,confirmed=stable,final_stable=stable,peaks=tail['peaks'])
        assert bool(passed)==audit['passed'] and bool(stable)==audit['physical_tail_pass']
    result=json.loads((OUT/'report_v1/assessment.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT,result['source_sha256'])
    print(f"PASS: {len(manifest)} delivery entries, protected static inputs and DLL, two physical-stop recomputations; {result['status']}; training remains blocked")


if __name__=='__main__':main()
