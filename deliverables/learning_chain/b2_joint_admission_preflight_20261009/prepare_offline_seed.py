"""Extract one existing SEARCH sensor state as an offline test fixture; no replay."""
import gzip
import json
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from scope_contract import ROOT,sha,read
from execution_contract import write

def main():
    p=ROOT/'deliverables/learning_chain/b2_rebound_execution_20261008/run/J01_script.json.gz'
    raw=json.loads(gzip.decompress(p.read_bytes()))
    row=next(r for r in raw['cycles'] if r['before']['controller_state']['phase']=='SEARCH'
        and r['before']['time_s']-r['before']['controller_state']['phase_start']>=.02
        and r['before']['state']['contact_count']>0 and r['before']['residual_enabled'])
    seed=dict(source=str(p),source_sha256=sha(p),source_cycle_id=row['before']['cycle_id'],
        initial=raw['initial'],snapshot=row['before'],context=raw['observations'][row['before']['cycle_id']]['context'],
        purpose='Pure injected-state fixture; no native reset/integration and not new physical evidence')
    write(OUT/'offline_seed.json',seed);print({'seed_cycle':seed['source_cycle_id'],'new_physics':0})
if __name__=='__main__':main()
