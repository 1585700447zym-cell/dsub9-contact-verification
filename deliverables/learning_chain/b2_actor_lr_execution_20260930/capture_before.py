"""Read-only stage boundary; preserve all inherited source and archive bytes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
PARENT = ROOT/'deliverables/learning_chain/b2_actor_lr_origin_20260930'


def sha(p):
    with p.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


sources = json.loads((PARENT/'origin_v2/source_sha256.json').read_text(encoding='utf-8'))
for rel,pin in sources.items():
    assert sha(ROOT/rel) == pin,rel
files = {p.relative_to(ROOT).as_posix():sha(p) for p in PARENT.rglob('*')
    if p.is_file() and not any(part.endswith('_work') for part in p.parts)}
for name,record in (('protected_before.json',sources),('parent_files.json',files)):
    with (HERE/name).open('x',encoding='utf-8') as stream:
        json.dump(record,stream,ensure_ascii=False,indent=2)
        stream.write('\n')
print(json.dumps(dict(protected_sources=len(sources),parent_artifacts=len(files))))
