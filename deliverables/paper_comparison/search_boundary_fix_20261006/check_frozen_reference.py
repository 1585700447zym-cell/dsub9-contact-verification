"""Compare old/new commands at recorded states; no simulator or neural calls."""
from pathlib import Path
import gzip, hashlib, importlib.util, json, sys
import numpy as np

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
from tools.control.reference_search import ReferenceSearchRecovery,DriveObservation,DriveSearchConfig
from tools.control.search_recovery import SearchConfig
from tools.control.risk_search import RotationRiskConfig
from tools.control.load_search import SearchLoadConfig

source=OUT/'before_source/tools/control/reference_search.py'
spec=importlib.util.spec_from_file_location('frozen_reference_search_before',source)
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
config=json.loads((OUT/'configuration.json').read_text(encoding='utf8'))['common']
records=[]
for case in config['cases']:
    p=ROOT/'deliverables/task_variants/layered_referee_20261004/run'/(case['id']+'.json.gz')
    raw=json.loads(gzip.decompress(p.read_bytes()));old=module.ReferenceSearchRecovery(SearchConfig(**config['b2_config']),
        RotationRiskConfig(**config['rotation_risk']),SearchLoadConfig(**config['search_load']),module.DriveSearchConfig(**config['drive_limits']))
    new=ReferenceSearchRecovery(SearchConfig(**config['b2_config']),RotationRiskConfig(**config['rotation_risk']),
        SearchLoadConfig(**config['search_load']),DriveSearchConfig(**config['drive_limits']))
    count=changes=0;error=0.
    for i,row in enumerate(raw['trace'][1:],1):
        comp=row.get('search_composition')
        if comp is None:continue
        previous=raw['trace'][i-1]
        obs=DriveObservation(comp['time_s'],(0.,0.,0.),tuple(previous['contact_wrench_M']),0.,
            (*comp['reference_xy_m'],0.),tuple(previous['limited_command_world'][:2]))
        for c in (old,new):
            c.phase='SEARCH';c.search_origin=np.zeros(3);c.theta=comp['theta_rad'];c.search_count=row['search_count']
            c.admittance.offset=np.array(previous['commanded_correction']);c.admittance.velocity=np.array(previous['admittance_velocity'])
        before=old._search_command(obs,.002);after=new._search_command(obs,.002);count+=1
        if not np.array_equal(before,after) or old.phase!=new.phase:changes+=1
        if new.search_composition is not None:
            error=max(error,float(np.max(np.abs(np.array(new.search_composition['predicted_reference_xy_m'])-comp['predicted_reference_xy_m']))))
    assert changes==0 and error<1e-15,(p,changes,error)
    records.append(dict(case=case['id'],archive=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        checked_search_commands=count,changed_commands=changes,max_reference_prediction_error_m=error))
result=dict(scope='recorded B2 SEARCH state command regression only; no new physics',cases=records,
    total_commands=sum(r['checked_search_commands'] for r in records),new_physics=0,
    production_sha256={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
        ('tools/control/reference_search.py','tools/learning/v4_continuation.py')})
(OUT/'frozen_reference_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(dict(cases=len(records),checked_commands=result['total_commands'],changes=0,new_physics=0)))
