"""One-off schema inspection, reads only pre-existing sealed archives."""
from pathlib import Path
import sys,gzip,json
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from small_bound_profile import ROOT
p=OUT.parent/'contact_gate_probe_20261007/run/probe_F12p5_y_neg_150.json.gz'
r=json.loads(gzip.decompress(p.read_bytes()))
print('raw keys',sorted(r));print('log keys',sorted(r['actions'][0]))
print('transition keys',sorted(r['transitions'][0]));print('trace keys',sorted(r['trace'][0]))
print('active log',next(l for l in r['actions'] if l['enabled']))
common=json.loads((OUT.parent/'v4_learning_requalification_20261006/configuration.json').read_text(encoding='utf8'))
print('configuration keys',sorted(common));print('common keys',sorted(common['common']))
