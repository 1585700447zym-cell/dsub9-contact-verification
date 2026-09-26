"""Read-only integrity check before replaying the stopping diagnosis."""
import json
from tools.validation.validate_training_readiness import ROOT, verify_hashes


def main():
    folder = ROOT/'deliverables/stop_reliability'
    manifest = json.loads((folder/'delivery_manifest.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT, manifest)
    index = json.loads((folder/'diagnosis_v1/results_index.json').read_text(encoding='utf-8'))
    verify_hashes(ROOT, index['historical_source_sha256'])
    verify_hashes(ROOT, index['protected_inputs'])
    verify_hashes(folder/'diagnosis_v1', index['files'])
    print(f"PASS: {len(manifest)} delivery files; {len(index['historical_source_sha256'])} historical model/assets; protected source and raw outputs")


if __name__ == '__main__':
    main()
