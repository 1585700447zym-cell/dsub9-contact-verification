"""Recompute archived stop, rewards, permissions and reference facts offline."""
from pathlib import Path
import gzip, hashlib, json, math, os, sys
import numpy as np

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(ROOT))
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_search_boundary_fix'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.validation.native313_matrix_audit import actual_stop_pass
from tools.validation.run_contact_candidate_stop import physical_tail_pass
from tools.validation.verify_admitted_collection import validate_outcome
from tools.learning.reward import EpisodeReward
from tools.learning.v4_pilot_contract import permission,field_slices
from tools.learning.v4_replay import V4Replay
from tools.validation.run_clearance_preflight import write


def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def archive(p):return json.loads(gzip.decompress(Path(p).read_bytes()))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


ledger=read(OUT/'run/ledger.json')
partial='--partial' in sys.argv
assert ledger['status'] in ('complete','controlled_stop','error') or (partial and ledger['status']=='running')
config=read(OUT/'configuration.json');reports=[]
for entry in ledger['episodes']:
    if entry['status']!='finished':continue
    path=OUT/'run'/(entry['id']+'.json.gz');raw=archive(path)
    assert sha(path)==entry['archive_sha256'] and raw['common_key']==config['common_key']
    stopped=bool(actual_stop_pass(raw['stop_samples'],raw['events'],raw['stop_time'],raw['audit_end_time_s'],.0002)
        and physical_tail_pass(raw['stop_samples'],raw['audit_end_time_s'],.0002))
    validate_outcome(raw,stopped=stopped)
    reward=EpisodeReward(.004);rows=raw['transitions'];draws=0;held=[0.]*4
    rng=np.random.default_rng(np.random.SeedSequence([config['seed'],1]));checks=0;maxradius=0.
    slices=field_slices();reference_ends=[e for e in raw['controller_events'] if e.get('reference_boundary_end')]
    for i,row in enumerate(rows):
        assert row['trace_row']==raw['trace'][i+1] and row['action_log']==raw['actions'][i]
        assert abs(row['dt']-(raw['trace'][i+1]['time_s']-raw['trace'][i]['time_s']))<1e-12
        assert abs(row['discount']-math.exp(-row['dt']/10))<1e-12
        terms=reward.advance(advance_m=row['advance_m'],dt=row['dt'],force_N=row['cycle_force_N'],torque_G_Nm=row['cycle_torque_G_Nm'])
        terms['terminal']=reward.finalize(raw['outcome']['task_outcome']) if i==len(rows)-1 else 0.
        terms['total']+=terms['terminal']
        assert terms.keys()==row['reward_terms'].keys()
        assert all(math.isclose(v,row['reward_terms'][k],rel_tol=0,abs_tol=1e-12) for k,v in terms.items())
        assert math.isclose(terms['total'],row['reward'],rel_tol=0,abs_tol=1e-12)
        assert row['terminated']==(i==len(rows)-1) and row['truncated'] is False
        if raw['spec']['mode']!='B2':
            if i%50==0:held=rng.uniform(-1.,1.,4).tolist();draws+=1
            assert row['sampling_request']==held
            assert row['action_active']==permission(row['observation'],raw['spec']['mode'])
            assert row['next_action_active']==permission(row['next_observation'],raw['spec']['mode'])
            request=held if row['action_active'] else [0.]*4
            assert row['action_log']['raw_action']==request and row['action']==request
            x=np.array(row['observation']);phase=int(np.argmax(x[slices['policy_phase']]))
            if phase==2 and row['trace_row']['phase']=='RUNNING':
                origin=np.array(raw['trace'][0]['position_m'])[:2]+x[slices['search_origin_m']][:2]*.004
                radius=float(np.linalg.norm(np.array(row['trace_row']['reference_qpos'])[:2]-origin))
                # The observable origin is stored as float32: permit only its
                # reconstruction roundoff when auditing, not in the controller.
                assert radius<=.00012+1e-10
                checks+=1;maxradius=max(maxradius,radius)
    if raw['spec']['mode']!='B2':
        assert draws==raw['warmup_draws'];V4Replay(mode=raw['spec']['mode'],capacity=116000)._prepare(rows)
    final=raw['trace'][-1]
    report=dict(id=entry['id'],archive_sha256=sha(path),outcome=raw['outcome'],reason=entry['reason'],stopped_recomputed=stopped,
        control_cycles=len(rows),physical_substeps=entry['physical_substeps'],wall_s=entry['wall_s'],
        task_end_time_s=raw['task_end_time_s'],end_time_s=raw['audit_end_time_s'],reference_ends=reference_ends,
        reference_problems=raw['reference_problems'],max_actual_reference_radius_m=raw['max_actual_reference_radius_m'],
        independent_observed_reference_checks=checks,independent_reconstructed_radius_m=maxradius,
        terminal_reward=rows[-1]['reward_terms']['terminal'],reward_total=sum(r['reward'] for r in rows),
        peaks=raw['peaks'],final_xy_um=float(np.linalg.norm(final['position_m'][:2])*1e6),
        final_z_um=final['position_m'][2]*1e6,valid_training_format=raw['spec']['mode']!='B2',published=0)
    if raw['spec']['mode']=='B2':
        old=archive(ROOT/'deliverables/task_variants/layered_referee_20261004/run/y_neg_150.json.gz')
        report['zero_baseline_full_trace_exact']=raw['trace']==old['trace']
        assert report['zero_baseline_full_trace_exact']
    reports.append(report)
result=dict(scope='bounded development repair regression, no learned-policy benefit proof',status=ledger['status'],
    launched=len(ledger['episodes']),completed=len(reports),prior_cumulative=142,cumulative=142+len(ledger['episodes']),
    unused_closed=ledger.get('unused_closed'),reports=reports,control_cycles=sum(r['control_cycles'] for r in reports),
    physical_substeps=sum(r['physical_substeps'] for r in reports),formal_updates=0,policy_calls=0,replay_published=0,
    independent_tests=0,B2_complete=False,production_sha256={n:sha(ROOT/n) for n in ('tools/control/reference_search.py','tools/learning/v4_continuation.py')})
write(OUT/('assessment_partial.json' if partial else 'assessment.json'),result)
print(json.dumps({k:v for k,v in result.items() if k not in ('reports','production_sha256')},ensure_ascii=False))
