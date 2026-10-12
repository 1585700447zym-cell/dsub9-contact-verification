"""Verify saved evidence and plot hashes; no simulation or learning imports."""
import gzip
import hashlib
import json
import math
from pathlib import Path

D = Path(__file__).resolve().parent
ROOT = D.parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def verify(base, pins):
    for name, pin in pins.items():
        assert digest(base / name) == pin, name
    return len(pins)


def main():
    output = D / 'integrity_verification.json'
    assert not output.exists(), 'Do not replace a completed evidence receipt.'
    assessment = read(D / 'assessment.json')
    input_count = verify(ROOT, assessment['inputs_sha256'])
    qualification = read(D / 'admission.json')
    source_count = verify(ROOT, qualification['source_sha256'])
    evidence_count = verify(ROOT, qualification['evidence_sha256'])
    old_count = verify(ROOT, read(D / 'previous_files.json'))
    figures = read(D / 'figures/manifest.json')
    verify(D, figures['inputs_sha256'])
    figure_count = verify(D, figures['outputs_sha256'])
    assert digest(D / 'plot_stopped_run.py') == figures['renderer_sha256']
    sample_counts = {}
    for name in assessment['inputs_sha256']:
        if not name.endswith('/episode.json.gz'):
            continue
        raw = json.loads(gzip.decompress((ROOT / name).read_bytes()))
        samples = raw['stop_samples']
        assert samples and all(
            math.isfinite(row[key])
            for row in samples
            for key in ('time_s', 'linear_m_s', 'angular_rad_s')
        ), name
        sample_counts[name] = len(samples)
    assert len(sample_counts) == 13
    assert all(not (D / 'run' / name).exists() for name in assessment['missing'])
    reports = ['README.md', '实施记录.md', '停止结果说明.md',
               'audit_stopped_run.py', 'verify_stopped_result.py',
               'assessment.json', 'figures/manifest.json', 'plot_stopped_run.py']
    result = dict(
        status='verified_stopped_evidence_not_B2_acceptance',
        audit_inputs_verified=input_count, source_files_verified=source_count,
        qualification_evidence_verified=evidence_count, old_files_verified=old_count,
        figure_outputs_verified=figure_count,
        all_stop_samples_finite=True, stop_sample_counts=sample_counts,
        missing_final_stages_still_absent=True,
        additional_physical_starts=0, additional_policy_inferences=0,
        additional_state_restorations=0, additional_optimizer_calls=0,
        saved_report_sha256={name: digest(D / name) for name in reports},
    )
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2,
                                 allow_nan=False) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ('stop_sample_counts', 'saved_report_sha256')},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
