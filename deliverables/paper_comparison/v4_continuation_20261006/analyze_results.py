"""Read-only physical, command, reward and transition validation; no learning."""
import sys,json,gzip,hashlib,math,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT));os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_v4_continuation'))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
import numpy as np
from tools.validation.native313_matrix_audit import actual_stop_pass
from tools.validation.run_contact_candidate_stop import physical_tail_pass
from tools.learning.reward import EpisodeReward

def read(p):return json.loads(p.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def emit(result):
    (OUT/'assessment.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
    print(json.dumps(result,ensure_ascii=False))

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    ledger=read(OUT/'run/ledger.json');assert ledger['status']!='running'
    result=dict(status=ledger['status'],attempts=len(ledger['episodes']),cumulative=139+len(ledger['episodes']),
        unused_closed=ledger['unused_closed'],training_updates=0,policy_calls=0,replay_published=0,independent_tests=0,
        training_admitted=False,stage_B2_complete=False,automatic_tracking='PAUSED',bounded_preflight_passed=False)
    if ledger['episodes'] and ledger['episodes'][0]['status']=='finished':
        e=ledger['episodes'][0];p=OUT/'run'/(e['id']+'.json.gz');assert sha(p)==e['archive_sha256']
        d=json.loads(gzip.decompress(p.read_bytes()));assert d['summary']=={k:v for k,v in e.items() if k!='archive_sha256'}
        stopped=bool(actual_stop_pass(d['stop_samples'],d['events'],e['stop_time'],e['end_time'],.0002)
            and physical_tail_pass(d['stop_samples'],e['end_time'],.0002));assert stopped==e['outcome']['physical_stopped']
        if not e['verification_passed']:
            result.update(completed=1,outcome=e['outcome'],reason=e['reason'],pulse_pass=e['pulse_pass'],pulse=e['pulse'],
                followup=e['followup'],reference_problems=e['reference_problems'],actual_reference_failed=e['actual_reference_failed'],
                control_cycles=e['control_cycles'],physical_substeps=e['physical_substeps'],wall_seconds=e['wall_seconds'])
            emit(result);return
        old=json.loads(gzip.decompress((ROOT/'deliverables/task_variants/layered_referee_20261004/run/y_neg_150.json.gz').read_bytes()))
        pulse=e['pulse'];n=pulse['prefix_samples'];assert d['trace'][:n]==old['trace'][:n]
        assert abs(pulse['command_time_s']-9.146)<1e-9
        # The logged total fraction multiplies two layers. Recompute the first
        # independently from the frozen base and the exact actual pre-pulse input.
        from tools.learning.v4_action import compose_reference_command
        _,first=compose_reference_command(old['trace'][pulse['cycle']]['raw_command_world'],pulse['log']['raw_action'],
            phase='SEARCH',enabled=True,previous_limited=d['trace'][n-1]['limited_command_world'],dt=.002,
            reference_xy=pulse['log']['reference_xy_m'])
        assert first['unfiltered_stage_limited_total']==pulse['log']['unfiltered_stage_limited_total']
        assert first['reference_filter_fraction']<1
        assert abs(first['reference_filter_fraction']*pulse['log']['continuation_filter_fraction']-pulse['log']['reference_filter_fraction'])<1e-15
        assert sum(any(a['raw_action']) for a in d['actions'])==1
        assert e['followup']['policy_phase']=='SEARCH' and e['followup']['log']['raw_action']==[0]*4
        assert not e['reference_problems']
        actual_checks=actual_failed=0;maxradius=0.;command_error=0.
        starts=[x for x in d['controller_events'] if x['reason']=='LOW_LOAD_SEARCH']
        by_time={round(r['time_s'],8):r for r in d['trace']}
        for a in d['actions']:
            r=d['trace'][a['cycle']]
            if r['phase']!='RUNNING':continue
            command_error=max(command_error,float(np.max(np.abs(np.array(r['limited_command_world'])-a['predicted_limited_command']))))
            if not a['reference_checked']:continue
            event=max((x for x in starts if x['time_s']<=a['command_time_s']+1e-9),key=lambda x:x['time_s'])
            origin=by_time[round(event['time_s'],8)]['position_m'][:2]
            radius=float(np.linalg.norm(np.array(r['reference_qpos'][:2])-origin));actual_checks+=1
            actual_failed+=radius>.00012+1e-12;maxradius=max(maxradius,radius)
        assert actual_checks==e['actual_reference_checks'] and actual_failed==0 and command_error<1e-12
        assert abs(maxradius-e['max_actual_reference_radius_m'])<1e-12
        fields={s['name']:slice(s['start'],s['start']+s['width']) for s in d['observation_schema']}
        assert sum(s['width'] for s in d['observation_schema'])==137
        reward=EpisodeReward(.004);previous=None;totals={};transition_checks=0
        assert len(d['transitions'])==e['control_cycles']==len(d['actions'])
        for i,t in enumerate(d['transitions']):
            obs=np.asarray(t['observation']);nxt=np.asarray(t['next_observation'])
            assert obs.shape==nxt.shape==(137,) and np.isfinite(np.r_[obs,nxt]).all()
            assert max(np.max(np.abs(obs)),np.max(np.abs(nxt)))<=10
            assert bool(obs[fields['action_active']][0])==t['action_active']
            assert bool(nxt[fields['action_active']][0])==t['next_action_active']
            if previous is not None:assert np.array_equal(previous,obs)
            previous=nxt
            assert t['dt']>0 and math.isclose(t['discount'],math.exp(-t['dt']/10),rel_tol=0,abs_tol=1e-12)
            assert t['terminated']==(i==len(d['transitions'])-1) and not t['truncated']
            assert t['action']==d['actions'][i]['experience_action']
            if not t['action_active']:assert t['action']==[0]*4
            parts=reward.advance(advance_m=t['advance_m'],dt=t['dt'],force_N=t['cycle_force_N'],torque_G_Nm=t['cycle_torque_G_Nm'])
            parts['terminal']=reward.finalize(e['outcome']['task_outcome']) if t['terminated'] else 0.
            parts['total']+=parts['terminal']
            assert parts.keys()==t['reward_terms'].keys()
            assert all(abs(parts[k]-t['reward_terms'][k])<1e-12 for k in parts)
            assert abs(parts['total']-t['reward'])<1e-12
            for k,v in parts.items():totals[k]=totals.get(k,0.)+v
            transition_checks+=1
        assert all(abs(v-e['reward_totals'][k])<1e-10 for k,v in totals.items())
        result.update(completed=1,bounded_preflight_passed=bool(e['verification_passed'] and stopped and ledger['status']=='complete'),
            outcome=e['outcome'],reason=e['reason'],prefix_equal_samples=n,pulse_cycle=pulse['cycle'],pulse_time_s=pulse['command_time_s'],
            filter_cycles=e['filter_cycles'],continuation_filter_cycles=e['continuation_filter_cycles'],
            continuation_fraction=pulse['log']['continuation_filter_fraction'],combined_fraction=pulse['log']['reference_filter_fraction'],
            first_step_fraction=first['reference_filter_fraction'],
            actual_reference_checks=actual_checks,actual_reference_failures=actual_failed,max_actual_reference_radius_um=maxradius*1e6,
            max_command_error=command_error,transition_reward_permission_checks=transition_checks,observation_width=137,
            control_cycles=e['control_cycles'],physical_substeps=e['physical_substeps'],wall_seconds=e['wall_seconds'],
            task_end_time_s=e['task_end_time'],peak_force_mN=e['peaks']['force_N']*1000,xy_um=e['xy_um'],z_um=e['z_um'],
            pin_clearance_um=e['pin_clearance_um'],stop_time_s=e['stop_time'],physical_end_time_s=e['end_time'])
    else:
        result.update(completed=0,errors=[e.get('error') for e in ledger['episodes']],
            control_cycles=sum(e.get('control_cycles',0) for e in ledger['episodes']),
            physical_substeps=sum(e.get('physical_substeps',0) for e in ledger['episodes']))
    emit(result)

if __name__=='__main__':main()
