from pathlib import Path
import hashlib,json
D=Path(__file__).resolve().parent
ROOT=D.parents[2]
OLD=ROOT/'deliverables/learning_chain/b2_fixed_rotation_cycle_20260928'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
assert not (D/'parent_source_snapshots.json').exists()
q=json.loads((OLD/'admission.json').read_bytes())
for name,pin in q['source_sha256'].items():assert sha(ROOT/name)==pin,name
mapping={}
for name in ('contact_execution','bounded_contact','boundary_targets','bounded_checkpoint','bounded_cycle'):
    rel=f'tools/learning/{name}.py'
    target=D/'source_snapshot'/rel
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_bytes((ROOT/rel).read_bytes())
    mapping[rel]=target.relative_to(ROOT).as_posix()
(D/'parent_source_snapshots.json').write_text(json.dumps(mapping,indent=2)+'\n',encoding='utf-8')
files={p.relative_to(ROOT).as_posix():sha(p) for p in OLD.rglob('*') if p.is_file()}
(D/'previous_files.json').write_text(json.dumps(files,indent=2)+'\n',encoding='utf-8')
print('Saved source snapshots:',len(mapping),'Preserved current execution package files:',len(files))
