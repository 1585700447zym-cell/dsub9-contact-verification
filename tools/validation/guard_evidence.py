"""Complete local-code/model fingerprints for the candidate validation tools."""
import hashlib
from tools.learning.runtime import ROOT, RECORD


def input_fingerprints():
    # Conservative superset: includes transitively imported validation/reporting
    # helpers, rather than a fragile hand-maintained list of a few direct imports.
    paths = list((ROOT / 'tools').rglob('*.py'))
    paths += list((ROOT / 'models').rglob('*.xml'))
    paths += [p for p in (ROOT / 'assets').rglob('*') if p.is_file()]
    paths += [ROOT / 'deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json', RECORD]
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))}


def snapshot_inputs(target, fingerprints):
    for name, expected in fingerprints.items():
        content = (ROOT / name).read_bytes()
        if hashlib.sha256(content).hexdigest() != expected:
            raise RuntimeError(f'Input changed before snapshot: {name}')
        destination = target / 'source_snapshot' / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
