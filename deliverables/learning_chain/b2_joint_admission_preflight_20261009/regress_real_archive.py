"""Read-only inherited full audit of J01_script; never run a simulator."""
import importlib.abc
import json
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
OLD=OUT.parent/'b2_preflight_rebound_20261008'
sys.path.insert(0,str(OLD))
class NoEngine(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'mujoco','torch','stable_baselines3','gymnasium','tensorflow','jax'}:
            raise ImportError('Offline regression forbids '+fullname)
def main():
    sys.meta_path.insert(0,NoEngine())
    from scope_contract import sha,read
    from assess import read_archive,assess_raw
    binding=OLD/'candidate_binding.json'
    if sha(binding)!='b7746e0cfaf29317c1ae692f6ed03c685d0d1a3398965c3fa36fc012b8ed3952':raise ValueError('Historical binding differs')
    for name in ('offline_math.py','evidence_checks.py'):
        if sha(OUT/name)!=sha(OLD/name):raise ValueError('Inherited numerical/guard audit changed')
    source=OUT.parent/'b2_rebound_execution_20261008/run/J01_script.json.gz'
    manifest=read(source.parents[1]/'delivery_manifest.json')
    if sha(source)!=manifest['files']['run/J01_script.json.gz']['sha256']:raise ValueError('Archive changed')
    raw=read_archive(source)
    result=assess_raw(raw,raw['spec'],dict(binding_sha256=sha(binding)))
    expected=next(r for r in read(source.parent/'assessment.json')['dynamic'] if r['id']=='J01_script')
    for key in ('outcome','functional_success','strict_precision_success','script_nonzero_cycles','contact_effect_cycles'):
        if result[key]!=expected[key]:raise ValueError('Regression differs: '+key)
    report=dict(status='PASS_INHERITED_REAL_ARCHIVE_REGRESSION',source=str(source),sha256=sha(source),
        cycles=raw['control_cycles'],observation_vectors=result['observation']['vectors_verified'],
        outcome=result['outcome'],contact_effect_cycles=result['contact_effect_cycles'],new_physics=0,
        limitation='Existing J01 script audit only; not new A/B/R qualification or recovery coverage')
    print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
