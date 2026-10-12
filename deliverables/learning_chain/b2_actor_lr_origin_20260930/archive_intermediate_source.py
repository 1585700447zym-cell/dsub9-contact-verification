"""Retain the exact pre-strict module bytes, verified against the old manifest."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
relative = 'tools/learning/actor_lr_origin.py'
data = (ROOT/relative).read_bytes()
start = data.index(b'def verify_warmup_requests(')
end = data.index(b'def rebuild_origin(',start)
prior = data[:start]+data[end:]
needle = b"        verify_warmup_requests(requests, [r['action_log']['raw_action'] for r in raw['transitions']])"
replacement = b"        if not np.array_equal(requests, np.asarray([r['action_log']['raw_action'] for r in raw['transitions']], dtype=np.float32)):\n            raise ValueError('Warmup random requests differ from locked stream')"
assert prior.count(needle) == 1
prior = prior.replace(needle,replacement)
pin = json.loads((HERE/'origin/source_sha256.json').read_text(encoding='utf-8'))[relative]
assert hashlib.sha256(prior).hexdigest() == pin
path = HERE/'pre_strict_source_snapshots'/relative
path.parent.mkdir(parents=True,exist_ok=True)
if path.exists():
    assert path.read_bytes() == prior
else:
    with path.open('xb') as stream:
        stream.write(prior)
print(json.dumps(dict(status='exact_pre_strict_source_retained',sha256=pin)))
