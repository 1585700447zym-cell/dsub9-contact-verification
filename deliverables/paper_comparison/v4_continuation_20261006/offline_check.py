"""Frozen command replay and actual next-controller oracle; no reset/step."""
import sys,json,gzip,math
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import numpy as np
from tools.control.reference_search import ReferenceSearchRecovery,DriveSearchConfig,DriveObservation
from tools.control.search_recovery import SearchConfig
from tools.control.risk_search import RotationRiskConfig
from tools.control.load_search import SearchLoadConfig
from tools.learning.v4_continuation import compose_continuation_command
from tools.learning.v4_action import compose_reference_command
from tools.dynamics.safety import limit_command

if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
base=ROOT/'deliverables/task_variants/layered_referee_20261004'
common=json.loads((ROOT/'deliverables/paper_comparison/protocol_v4_20261004/protocol.json').read_text(encoding='utf8'))['common']
cfg=SearchConfig(**common['b2_config']);b=cfg.spiral_pitch_m/(2*math.pi)
examples=json.loads((ROOT/'deliverables/paper_comparison/protocol_v4_20261004/residual_integration_audit.json').read_text(encoding='utf8'))['examples']
count=0;error=0.;records=[];unproven_zero=0
ledger=json.loads((base/'run/ledger.json').read_text(encoding='utf8'))
for entry in ledger['episodes']:
    d=json.loads(gzip.decompress((base/'run'/(entry['id']+'.json.gz')).read_bytes()))
    for previous,row in zip(d['trace'],d['trace'][1:]):
        c=row['search_composition']
        if c is None:continue
        theta=c['theta_rad'];advanced=min(cfg.spiral_radius_m/b,theta+cfg.spiral_speed_m_s/math.hypot(b*theta,b)*.002)
        args=dict(phase='SEARCH',enabled=True,previous_limited=previous['limited_command_world'],dt=.002,
            reference_xy=c['reference_xy_m'],next_theta=advanced,search_config=cfg)
        cmd,log=compose_continuation_command(row['raw_command_world'],[0]*4,**args)
        expected=np.array(row['limited_command_world']);actual=limit_command(cmd,args['previous_limited'],.002,[.001]*3+[.03]*3,[.005]*3+[.3]*3)
        np.testing.assert_array_equal(actual,expected);count+=1;error=max(error,float(np.max(np.abs(actual-expected))))
        unproven_zero+=not log['next_zero_reference_feasible']
        for e in examples:
            if entry['id']!=e['case'] or abs(e['command_time_s']-previous['time_s'])>1e-8:continue
            _,old=compose_reference_command(e['base_command'],e['normalized_action'],**{k:v for k,v in args.items() if k not in ('next_theta','search_config')})
            cmd,new=compose_continuation_command(e['base_command'],e['normalized_action'],**args)
            def oracle(a):
                controller=ReferenceSearchRecovery(cfg,RotationRiskConfig(**common['rotation_risk']),
                    SearchLoadConfig(**common['search_load']),DriveSearchConfig(**common['drive_limits']))
                controller.phase='SEARCH';controller.search_count=1;controller.search_origin=np.zeros(3);controller.theta=advanced
                obs=DriveObservation(row['time_s'],(0,0,.0002),(0,0,-.008,0,0,0),(0,0,0),
                    tuple(a['predicted_reference_xy_m']+[0]),tuple(a['predicted_limited_command'][:2]))
                controller._search_command(obs,.002)
                return controller.phase,controller.events
            old_phase,old_events=oracle(old);new_phase,new_events=oracle(new)
            assert not any(x['reason']=='SEARCH_REFERENCE_LIMIT' for x in new_events)
            assert new['next_zero_reference_feasible']
            records.append(dict(command_time_s=previous['time_s'],action=e['normalized_action'],old_next_phase=old_phase,
                old_next_events=old_events,new_next_phase=new_phase,new_next_events=new_events,
                one_step_fraction=old['reference_filter_fraction'],continuation_fraction=new['continuation_filter_fraction'],
                combined_fraction=new['reference_filter_fraction'],predicted_radius_um=np.linalg.norm(new['predicted_reference_xy_m'])*1e6,
                next_predicted_radius_um=np.linalg.norm(new['next_zero_predicted_reference_xy_m'])*1e6,
                controlled_end=new['next_zero_controlled_search_end']))
assert count==16563 and len(records)==6
result=dict(search_zero_rows=count,max_zero_command_error=error,unproven_zero_predictions=unproven_zero,
    old_next_reference_failures=sum(any(x['reason']=='SEARCH_REFERENCE_LIMIT' for x in r['old_next_events']) for r in records),
    continuation_filtered_examples=sum(r['continuation_fraction']<1 for r in records),new_next_reference_failures=0,
    examples=records,new_dynamic_episodes=0,new_physical_steps=0,formal_updates=0,policy_calls=0)
(OUT/'offline_check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps({k:v for k,v in result.items() if k!='examples'}))
