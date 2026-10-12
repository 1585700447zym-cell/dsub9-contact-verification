"""Frozen SEARCH rows, zero equivalence and bounded counterfactuals; no physics."""
from pathlib import Path
import sys,gzip,json
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import numpy as np
from tools.learning.v4_action import compose_reference_command
from tools.dynamics.safety import limit_command

if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
base=ROOT/'deliverables/task_variants/layered_referee_20261004'
ledger=json.loads((base/'run/ledger.json').read_text(encoding='utf8'))
rows=counterfactuals=filtered=0;max_zero=0.;max_radius=0.
for e in ledger['episodes']:
    data=json.loads(gzip.decompress((base/'run'/(e['id']+'.json.gz')).read_bytes()))
    for previous,r in zip(data['trace'],data['trace'][1:]):
        c=r['search_composition']
        if c is None:continue
        args=dict(phase='SEARCH',enabled=True,previous_limited=previous['limited_command_world'],dt=.002,reference_xy=c['reference_xy_m'])
        _,log=compose_reference_command(r['raw_command_world'],[0.]*4,**args)
        error=np.max(np.abs(np.array(log['predicted_limited_command'])-r['limited_command_world']))
        max_zero=max(max_zero,float(error));assert error<1e-12;rows+=1
        for x in (-1.,0.,1.):
            for y in (-1.,0.,1.):
                if not(x or y):continue
                cmd,log=compose_reference_command(r['raw_command_world'],[x,y,0.,0.],**args)
                actual=limit_command(cmd,args['previous_limited'],.002,[.001]*3+[.03]*3,[.005]*3+[.3]*3)
                np.testing.assert_array_equal(actual,log['predicted_limited_command'])
                radius=float(np.linalg.norm(np.array(c['reference_xy_m'])+actual[:2]*.002))
                assert radius<=.00012+1e-12
                max_radius=max(max_radius,radius);counterfactuals+=1;filtered+=log['reference_filter_fraction']<1
result=dict(search_rows=rows,counterfactual_actions=counterfactuals,filtered_actions=filtered,
    max_zero_command_error=max_zero,max_predicted_radius_m=max_radius,new_physical_steps=0,
    scope='command_only_not_new_physics_or_learning',all_filtered_predictions_pass=True)
assert (rows,counterfactuals,filtered)==(16563,132504,6)
(OUT/'offline_replay.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
print(json.dumps(result))
