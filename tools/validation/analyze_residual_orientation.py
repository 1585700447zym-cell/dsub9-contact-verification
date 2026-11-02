"""Read-only historical orientation envelope; NOT a guard qualification."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from tools.learning.runtime import ROOT


def relative_angles(quaternions, initial):
    q = np.asarray(quaternions, dtype=float)
    q0 = np.asarray(initial, dtype=float)
    if q.ndim != 2 or q.shape[1] != 4 or q0.shape != (4,):
        raise ValueError('Quaternion shape must be (n,4), initial (4,)')
    if not np.isfinite(q).all() or not np.isfinite(q0).all():
        raise ValueError('Finite quaternion required')
    norms, norm0 = np.linalg.norm(q, axis=1), np.linalg.norm(q0)
    if np.any(norms == 0) or norm0 == 0:
        raise ValueError('Nonzero quaternion required')
    dots = np.clip(np.abs((q / norms[:, None]) @ (q0 / norm0)), 0, 1)
    return 2*np.arccos(dots)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = ROOT / 'deliverables/native313_baseline_matrix'
    rows = []
    for original in sorted(root.glob('b?_v1/*/original.json.gz')):
        paths = [original, original.parent / 'stop_extension.json.gz']
        run, tail = [json.loads(gzip.decompress(p.read_bytes())) for p in paths]
        samples = run['trace'] + tail['trace'][1:]
        initial = samples[0]['quaternion_wxyz']
        relative = relative_angles([r['quaternion_wxyz'] for r in samples], initial)
        absolute = relative_angles([r['quaternion_wxyz'] for r in samples], [1, 0, 0, 0])
        index = int(np.argmax(relative))
        rows.append(dict(policy=original.parent.parent.name, case=original.parent.name,
                         max_relative_deg=float(np.rad2deg(relative[index])),
                         max_relative_time_s=samples[index]['time_s'],
                         max_absolute_deg=float(np.rad2deg(max(absolute))), control_samples=len(samples),
                         archive_sha256={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}))
    if len(rows) != 14:
        raise RuntimeError('Expected all 14 frozen development episodes')
    result = dict(status='CANDIDATE_DISCUSSION_ONLY', training_admitted=False,
                  candidate_not_approved_deg=2.5, guard_enabled=False, rows=rows,
                  overall_max_relative_deg=max(r['max_relative_deg'] for r in rows),
                  geometric_scale_example=dict(axial_span_m=.0045, angle_deg=2.5,
                                               lateral_shift_m=.0045*math.tan(math.radians(2.5)),
                                               nominal_radial_gap_m=.000075),
                  limitations=['2ms control samples, not a full physical-substep orientation envelope',
                               'Historical baseline does not qualify nonzero residual exploration',
                               'Simple axial-span geometry is a scale illustration, not a connector collision bound',
                               'Candidate requires approval, geometry review and dynamic boundary/stop tests',
                               'No independent test cases were read'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(dict(max_relative_deg=result['overall_max_relative_deg'], cases=len(rows),
                          training_admitted=False)))


if __name__ == '__main__':
    main()
