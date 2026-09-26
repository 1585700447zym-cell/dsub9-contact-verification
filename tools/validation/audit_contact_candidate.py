"""Supplementary strict pairing audit; preserves the original static run unchanged."""
import json
from tools.validation.validate_training_readiness import ROOT,sha,verify_hashes


def wall_pairs_pass(row):
    detected=set()
    for c in row['contacts']:
        a,b=c['pair']
        for pin,hole in ((a,b),(b,a)):
            if pin.startswith('pin_') and hole.startswith(f'hole_convex256_{pin[-2:]}_main_'):
                detected.add(pin)
    return bool(row['passed'] and detected=={f'pin_{i:02}' for i in range(1,10)})


def main():
    base=ROOT/'deliverables/contact_consistency_repair';source=base/'static_gate_v1/results.json'
    target=base/'strict_static_audit.json'
    if target.exists():raise FileExistsError(target)
    data=json.loads(source.read_text(encoding='utf-8'));verify_hashes(ROOT,data['input_sha256'])
    verify_hashes(ROOT,data['historical_source_sha256'])
    wall=next(r for r in data['special'] if r['name']=='wall_x')
    result=dict(passed=bool(data['passed'] and wall_pairs_pass(wall)),wall_nine_corresponding_pairs=wall_pairs_pass(wall),
                trajectory_total=len(data['trajectory']),trajectory_contact_poses=sum(r['ncon']>0 for r in data['trajectory']),
                historical_poses=len(data['coverage']),historical_positive_witness_poses=sum(bool(r['expected_pins']) for r in data['coverage']),
                source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in (source,ROOT/'tools/validation/audit_contact_candidate.py')})
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
