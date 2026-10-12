"""B2-SCOPE-11: read existing archives and compare coverage definitions only."""
from pathlib import Path
import gzip
import json
import shutil
import subprocess
import sys

OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
OLD=OUT.parent/'b2_joint_preflight_execution_20261009'
CORR=OUT.parent/'b2_joint_coverage_clarification_20261009'
RUNNER=OUT.parent/'b2_joint_admission_preflight_20261009'
sys.path.insert(0,str(RUNNER))
from scope_contract import read,sha,schedule_position,healthy
from coverage_checks import action_coverage,matrix_route

def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
def nz(v):return any(abs(x)>1e-15 for x in v)

def main():
    if (OUT/'registration.json').exists():raise PermissionError('Review already registered; no blind rerun')
    git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT).decode('utf-8')
    before=read(CORR/'document_update.json')['after_documents']
    for name,pin in before.items():
        assert sha(ROOT/name)==pin,'Concurrent document change: '+name
        p=OUT/'before_documents'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    (OUT/'git_status_before.txt').write_text(git('status','--porcelain=v1'),encoding='utf-8')
    source_paths=[ROOT/'tools/learning/v4_session.py',ROOT/'tools/learning/v4_action.py',ROOT/'tools/learning/observation.py',
        ROOT/'tools/learning/v4_observation.py',RUNNER/'physical_worker.py',RUNNER/'scope_contract.py',RUNNER/'coverage_checks.py']
    registration=dict(stage_id='B2-SCOPE-11',human_request='继续',purpose='离线复核并形成最小覆盖条件修改方案，不启动物理或训练',
        branch=git('branch','--show-current').strip(),head=git('rev-parse','HEAD').strip(),before_documents=before,
        source_pins={str(p.relative_to(ROOT)).replace('\\','/'):sha(p) for p in source_paths},
        parent_manifests={OLD.name:sha(OLD/'delivery_manifest.json'),CORR.name:sha(CORR/'delivery_manifest.json')},
        new_physical_attempts=0,new_training=0,cumulative_dynamic=237)
    write(OUT/'registration.json',registration)
    (OUT/'progress.md').write_text('# B2-SCOPE-11 offline review\n\nTask1: registration, current sources, branch and six before snapshots recorded.\nTask2: compare all eight A/B archives with inherited 12/12 audits and four recovery results.\nTask3: recommend justified gate and minimum remaining pilot preparation; update five rolling documents, verify and seal.\nNo physical backend, policy inference, learner or new data generation.\n',encoding='utf-8')
    summary=read(OLD/'execution_summary.json');matrix=read(OLD/'run/assessment.json')
    assert matrix_route(matrix['dynamic'])==matrix['route']=='INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS'
    assert all(healthy(r) and r['functional_success'] for r in matrix['dynamic'])
    rows=[];cases={};old_gaps=[];interval_gaps=[]
    for entry in summary['rows']:
        if entry['id'].endswith('R_RECOVERY'):continue
        name=entry['id'];p=OLD/'run'/entry['raw_source'];assert sha(p)==entry['raw_sha256']
        raw=json.loads(gzip.decompress(p.read_bytes()));cycles=raw['cycles'];profile=raw['spec']['profile'];case_id=raw['spec']['case']['id']
        assert len(cycles)==raw['control_cycles'] and len(raw['observations'])==len(cycles)+1
        recomputed=action_coverage(raw,raw['spec']);assert recomputed==entry['assessment']['joint_coverage']
        holds={str(h):dict(total_cycles=0,permission_cycles=0,endpoint_contact_cycles=0,endpoint_effect_cycles=0,
            internal_peak_cycles=0,peak_effect_cycles=0,endpoint_or_peak_effect_cycles=0,
            next_observation_nonzero_wrench_cycles=0,endpoint_effect_ids=[],peak_only_effect_ids=[],signs=[set() for _ in range(4)]) for h in (50,1)}
        for i,c in enumerate(cycles):
            result=c['result'];log=result['action_log'];row=result['trace_row'];cp=result['cycle_peaks']
            enabled=c['before']['residual_enabled'];effective=nz(log['effective_command_delta']);endpoint=row['contact_count']>0
            assert cp['samples']==10
            internal=cp['force_N']>0 or cp['penetration_m']>0
            h=holds[str(schedule_position(profile,i)[1])]
            h['total_cycles']+=1;h['permission_cycles']+=int(enabled)
            h['endpoint_contact_cycles']+=int(endpoint);h['internal_peak_cycles']+=int(internal)
            h['peak_effect_cycles']+=int(enabled and effective and internal)
            h['endpoint_or_peak_effect_cycles']+=int(enabled and effective and (endpoint or internal))
            if enabled and effective and internal and not endpoint:h['peak_only_effect_ids'].append(i)
            if enabled and effective and endpoint:
                h['endpoint_effect_cycles']+=1;h['endpoint_effect_ids'].append(i)
                newest=c['after']['policy_raw']['wrench_history_M'][:6]
                assert newest==c['after']['state']['contact_wrench_M']
                h['next_observation_nonzero_wrench_cycles']+=int(nz(newest))
                for axis,j in enumerate((0,1,3,4)):
                    value=log['effective_command_delta'][j]
                    if abs(value)>1e-15:h['signs'][axis].add(1 if value>0 else -1)
        for hold,h in holds.items():
            assert h['endpoint_effect_cycles']==recomputed['hold_contact_effect_cycles'][hold]
            if h['endpoint_effect_cycles']==0:old_gaps.append(dict(id=name,hold_cycles=int(hold)))
            if h['endpoint_or_peak_effect_cycles']==0:interval_gaps.append(dict(id=name,hold_cycles=int(hold)))
            h['signs']=[sorted(x) for x in h['signs']]
        row=dict(id=name,case_id=case_id,profile=profile,archive_sha256=entry['raw_sha256'],control_cycles=len(cycles),
            holds=holds,joint_coverage=recomputed,observation_summary=entry['assessment']['observation'],
            initial_pose=raw['simulation_case'],binding_sha256=raw['binding_sha256'])
        rows.append(row)
        case=cases.setdefault(case_id,dict(episode_ids=[],holds={str(h):dict(endpoint_effect_cycles=0,interval_effect_cycles=0,
            next_observation_nonzero_wrench_cycles=0) for h in (50,1)},signs=[set() for _ in range(4)],
            all_peaks_covered=True,observation_difference_recorded=True))
        case['episode_ids'].append(name)
        for hold,h in holds.items():
            case['holds'][hold]['endpoint_effect_cycles']+=h['endpoint_effect_cycles']
            case['holds'][hold]['interval_effect_cycles']+=h['endpoint_or_peak_effect_cycles']
            case['holds'][hold]['next_observation_nonzero_wrench_cycles']+=h['next_observation_nonzero_wrench_cycles']
        for i,signs in enumerate(recomputed['signs']):case['signs'][i].update(signs)
        case['all_peaks_covered'] &= all(v['covered'] for v in recomputed['peaks'].values())
        case['observation_difference_recorded'] &= entry['assessment']['observation']['contact_information']=='OBSERVED_DIFFERENCE'
        print(json.dumps(dict(id=name,endpoint=[holds[str(h)]['endpoint_effect_cycles'] for h in (50,1)],
            interval=[holds[str(h)]['endpoint_or_peak_effect_cycles'] for h in (50,1)])),flush=True)
        del raw,cycles
    for c in cases.values():
        c['signs']=[sorted(x) for x in c['signs']]
        c['representative_coverage_observed']=all(h['endpoint_effect_cycles']>0 and h['next_observation_nonzero_wrench_cycles']>0 for h in c['holds'].values()) and all(x==[-1,1] for x in c['signs']) and c['all_peaks_covered'] and c['observation_difference_recorded']
    recoveries=[dict(id=r['id'],**r['assessment']['recovery']) for r in summary['rows'] if r['id'].endswith('R_RECOVERY')]
    assert len(rows)==8 and len(cases)==4 and len(recoveries)==4 and all(r['covered'] for r in recoveries)
    result=dict(stage_id='B2-SCOPE-11',kind='POST_HOC_DEVELOPMENT_CRITERIA_REVIEW',rows=rows,cases=cases,recoveries=recoveries,
        old_per_profile_endpoint_gaps=old_gaps,per_profile_endpoint_or_peak_gaps=interval_gaps,
        recommended_per_case_endpoint_gaps=[k for k,v in cases.items() if not v['representative_coverage_observed']],
        old_route_preserved=matrix['route'],counts=dict(archives_read=8,recorded_control_cycles=sum(r['control_cycles'] for r in rows),
            new_physical_attempts=0,new_training=0,cumulative_dynamic=237),
        limits=['Post-hoc development evidence, not independent confirmation or old-gate acceptance',
            'Cycle co-occurrence does not establish substep causal load benefit',
            'Observed wrench differences do not prove statistical observability or learned benefit',
            'Four discrete joint cases only; no continuous-domain or original 1.5deg qualification'])
    write(OUT/'coverage_comparison.json',result)
    print(json.dumps(dict(old_gaps=old_gaps,interval_gaps=interval_gaps,case_gaps=result['recommended_per_case_endpoint_gaps'],
        per_case={k:v['holds'] for k,v in cases.items()}),ensure_ascii=False))

if __name__=='__main__':main()
