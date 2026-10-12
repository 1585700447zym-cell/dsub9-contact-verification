"""Verify prior seals and freeze exact execution sources; no simulation steps."""
from pathlib import Path
import hashlib,json,shutil
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
previous=['clearance120_20261003','functional_b2_20261003','search_load_20261004','admittance_rebase_20261004','compliant_search_20261004']
results={}
for name in previous:
    folder=OUT.parent/name;manifest=folder/'delivery_manifest.json';data=json.loads(manifest.read_text(encoding='utf-8'))
    for relative,item in data['files'].items():
        b=(folder/relative).read_bytes();assert hashlib.sha256(b).hexdigest()==item['sha256'] and len(b)==item['bytes'],str(folder/relative)
    results[name]=dict(files=len(data['files']),manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())
(OUT/'prior_seals_verified.json').write_text(json.dumps(results,indent=2)+'\n',encoding='utf-8')
config=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'));n=0
for name,digest in config['input_sha256'].items():
    source=ROOT/name;assert hashlib.sha256(source.read_bytes()).hexdigest()==digest,name
    if source.suffix.lower()!='.stl':
        dest=OUT/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest);n+=1
for source in (ROOT/'tests/task_variants').glob('test_axis*.py'):
    dest=OUT/'source_snapshot'/source.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
record=dict(execution_inputs=len(config['input_sha256']),input_source_snapshots=n,prior_sealed_files=sum(v['files'] for v in results.values()),
    assets='STL bound by input hashes in place',dynamic_episodes_before_execute=0)
(OUT/'snapshot_record.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8');print(json.dumps(record))
