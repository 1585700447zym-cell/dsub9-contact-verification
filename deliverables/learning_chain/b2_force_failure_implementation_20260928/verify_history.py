"""Hash-only historical checks; never execute an old qualification on new code."""
from pathlib import Path
import hashlib,json
D=Path(__file__).resolve().parent;ROOT=D.parents[2]
OLD=ROOT/'deliverables/learning_chain/b2_fixed_rotation_cycle_20260928'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_bytes())
mapping=read(D/'parent_source_snapshots.json')
for name,pin in read(OLD/'admission.json')['source_sha256'].items():
    assert sha(ROOT/mapping.get(name,name))==pin,name
history=read(D/'previous_files.json')
for name,pin in history.items():assert sha(ROOT/name)==pin,name
prior=read(OLD/'previous_files.json')
for name,pin in prior.items():assert sha(ROOT/name)==pin,name
print(json.dumps(dict(parent_sources_verified=len(read(OLD/'admission.json')['source_sha256']),
    changed_sources_preserved=len(mapping),closed_fixed_cycle_files_unchanged=len(history),
    prior_repaired_cycle_files_unchanged=len(prior),physical_calls=0,optimizer_calls=0)))
