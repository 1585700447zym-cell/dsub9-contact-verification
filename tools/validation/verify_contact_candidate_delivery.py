"""Verify preserved candidate evidence and dependencies before reproduction."""
import json
from tools.validation.validate_training_readiness import ROOT,verify_hashes


def main():
    out=ROOT/'deliverables/contact_consistency_repair'
    manifest=json.loads((out/'delivery_manifest.json').read_text(encoding='utf-8'));verify_hashes(ROOT,manifest)
    static=json.loads((out/'static_gate_v1/results.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT,static['input_sha256']);verify_hashes(ROOT,static['historical_source_sha256'])
    core=json.loads((out/'核心依赖追溯核查.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT,core['verified_dependencies']);verify_hashes(ROOT,core['evidence_sha256'])
    for name in ('stop_dt0p2_v1','stop_dt0p1_v1'):
        idx=json.loads((out/name/'results_index.json').read_text(encoding='utf-8'))
        verify_hashes(ROOT,idx['protected_inputs']);verify_hashes(out/name,idx['files'])
    print(f'PASS: {len(manifest)} delivery files, 715 historical inputs and protected dependencies; physical verdict remains CANDIDATE_NOT_ADMITTED')


if __name__=='__main__':main()
