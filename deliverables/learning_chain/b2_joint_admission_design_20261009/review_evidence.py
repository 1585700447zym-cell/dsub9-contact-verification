"""B2-SCOPE-08 offline source/record review. No physics/learner construction."""
import ast
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import shutil
import xml.etree.ElementTree as ET

ROOT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation')
OUT=ROOT/'deliverables/learning_chain/b2_joint_admission_design_20261009'
PARENT=OUT.parent/'b2_joint_learning_review_20261009'
RAW=OUT.parent/'b2_rebound_execution_20261008'
PC06=ROOT/'deliverables/paper_comparison/v4_learning_requalification_20261006'
PC09=ROOT/'deliverables/paper_comparison/contact_gate_probe_20261007'
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md','AGENTS.md']

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def read(p):return json.loads(p.read_text(encoding='utf-8'))
def save(name,obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def main():
    assert not (OUT/'delivery_manifest.json').exists()
    assert sha(PARENT/'delivery_manifest.json')=='ef538c8951829a6a1d07cf005134b8ee26788f3a0e40a688dbdfd2c08c83af54'
    if not (OUT/'registration.json').exists():
        snapshots={}
        for name in DOCS:
            p=OUT/'before_documents'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p);snapshots[name]=sha(p)
        git=lambda *a:subprocess.check_output(['git',*a],cwd=ROOT)
        (OUT/'git_status_before.txt').write_bytes(git('-c','core.quotepath=false','status','--porcelain=v1'))
        save('registration.json',dict(stage_id='B2-SCOPE-08',user_date='2026-10-09',user_message='继续',
             scope='offline evidence review and admission design only',branch=git('branch','--show-current').decode().strip(),
             head=git('rev-parse','HEAD').decode().strip(),before_documents=snapshots,new_physics_authorized=False,new_training_authorized=False))
    source_names=['tools/control/search_recovery.py','tools/control/risk_search.py','tools/control/load_search.py',
                  'tools/control/axis_search.py','tools/control/reference_search.py','tools/learning/session.py',
                  'tools/learning/observation.py','tools/learning/v4_observation.py','tools/learning/v4_continuation.py',
                  'tools/learning/v4_session.py','tools/validation/run_v4_adapter_preflight.py',
                  'tests/learning/test_recovery.py','tests/learning/test_residual_recovery.py',
                  'docs/stage_b/训练合同_v3.md']
    source_pins={name:sha(ROOT/name) for name in source_names}
    config=read(PC06/'configuration.json')
    for name in source_names:
        if name in config['input_sha256']:assert source_pins[name]==config['input_sha256'][name],name
    # Inspect all controller inheritance layers without importing/executing them.
    history_references={}
    for name in source_names[:5]:
        tree=ast.parse((ROOT/name).read_text(encoding='utf-8'))
        history_references[name]=sorted({n.lineno for n in ast.walk(tree) if isinstance(n,ast.Attribute) and n.attr=='history'})
    assert all(not history_references[n] for n in source_names[1:5])
    base=(ROOT/source_names[0]).read_text(encoding='utf-8')
    assert "self.history.clear();self._transition('INSERT',obs,'SEARCH_ADVANCED')" in base
    assert "if self.phase=='INSERT':\n            self.history.append" in base
    parent=read(PARENT/'analysis.json');results=[]
    for ep in parent['episodes']:
        p=RAW/'run'/(ep['id']+'.json.gz');assert sha(p)==ep['source_archive_sha256']
        with gzip.open(p,'rt',encoding='utf-8') as f:raw=json.load(f)
        clipped=[];search_vectors=0;frozen_head=None;max_insert=0.;cleared=[];phase=''
        for i,c in enumerate(raw['cycles']):
            b=c['before'];ctrl=b['controller_state'];ph=ctrl['phase'];history=ctrl['history'];pr=b['policy_raw']
            if ph=='SEARCH':
                search_vectors+=1
                if phase!='SEARCH':frozen_head=history
                assert history==frozen_head,'SEARCH must retain, not update INSERT history'
                assert math.isclose(pr['phase_elapsed_s'][0],b['time_s']-ctrl['phase_start'],abs_tol=1e-12)
                assert math.isclose(pr['search_budget_remaining_s'][0],max(0.,8.-pr['phase_elapsed_s'][0]),abs_tol=1e-12)
                if pr['stall_span_s'][0]>.4*10:
                    assert b['policy_observation'][105]==10. and b['residual_enabled']
                    assert abs(pr['phase_elapsed_s'][0]/25.)<10 and abs(pr['search_budget_remaining_s'][0]/8.)<10
                    clipped.append(i)
            if ph=='INSERT' and b['state']['phase']=='RUNNING':max_insert=max(max_insert,pr['stall_span_s'][0])
            if phase=='SEARCH' and ph=='INSERT':
                assert history==[] and pr['stall_span_s']==[0.] and pr['stall_valid']==[0.]
                cleared.append(dict(cycle=i,time_s=b['time_s'],history_empty=True,stall_span_s=pr['stall_span_s'][0]))
            phase=ph
        assert len(clipped)==read(PARENT/'information_refinement.json')['episodes'][len(results)]['clipped_fields'].get('stall_span_s[0]',{}).get('occurrences',0)
        assert max_insert<.403 and len(cleared)==1
        results.append(dict(id=ep['id'],archive_sha256=sha(p),cycles=len(raw['cycles']),search_vectors=search_vectors,
             clipped_search_vectors=len(clipped),search_history_frozen=True,return_insert=cleared,
             max_active_insert_stall_span_s=max_insert,search_timing_fields_unsaturated=True,
             existing_wall_seconds=raw['wall_seconds']))
        print(ep['id'],'clipped',len(clipped),'INSERT maximum',max_insert,'cleared',len(cleared),flush=True)
        del raw
    # Same-current-source natural recovery at zero initial tilt, not joint-pose coverage.
    p=PC09/'run/probe_G50_y_neg_150.json.gz';gpin='a8d47576247bfc635dce783413e641aca00e6bc4f1758b9547791ccf27bb3563'
    assert sha(p)==gpin
    with gzip.open(p,'rt',encoding='utf-8') as f:g=json.load(f)
    assert g['comparison_key']==config['common_key'] and g['simulation_case']['roll_rad']==g['simulation_case']['pitch_rad']==0
    events={e['reason']:e for e in g['events']};start=events['RECOVERY_ACCEPTED']['time_s'];end=events['B2_RECOVERY_RESUMED']['time_s']
    trace=g['trace'];actions=g['actions'];assert len(trace)==len(actions)+1
    nearest=lambda t:min(trace,key=lambda r:abs(r['time_s']-t))
    start_row=nearest(start);end_row=nearest(end)
    distance=start_row['position_m'][2]-end_row['position_m'][2]
    assert distance>=.0002
    masked=[(t,action) for t,action in zip(trace,actions) if events['B2_SEARCH_EXHAUSTED']['time_s']<=t['time_s']<end-1e-9]
    assert masked and all(not action['enabled'] and not any(action['applied_residual']) and not any(action['experience_action']) for t,action in masked)
    recovery=dict(source=p.relative_to(ROOT).as_posix(),sha256=gpin,common_key=g['comparison_key'],initial_pose=g['simulation_case'],
                  events=g['events'],observed_retraction_control_boundary_m=distance,
                  start_sample_time_s=start_row['time_s'],end_sample_time_s=end_row['time_s'],
                  all_masked_recovery_cycles=len(masked),nonzero_requests_during_recovery=sum(any(action['raw_action']) for t,action in masked),
                  outcome=g['outcome'],joint_initial_pose_covered=False,
                  limitation='G50 and zero initial tilt; observed masking of zero requests does not stress nonzero F50 requests; task still failed after the second search.')
    tests=[]
    for folder,filename in [(PC06,'verification.xml'),(ROOT/'deliverables/residual_interface/b1_closeout_20260926','learning_tests.xml')]:
        root=ET.parse(folder/filename).getroot()
        for t in root.iter('testcase'):
            name=t.attrib.get('name','');cls=t.attrib.get('classname','')
            if ('recover' in name.lower() or cls.endswith('.test_recovery') or cls.endswith('.test_residual_recovery')):
                tests.append(dict(source=(folder/filename).relative_to(ROOT).as_posix(),classname=cls,name=name,
                                  passed=not any(c.tag in ['failure','error','skipped'] for c in t),
                                  current_source_qualification=folder==PC06))
    assert tests and all(t['passed'] for t in tests)
    save('evidence_review.json',dict(stage_id='B2-SCOPE-08',status='OFFLINE_EVIDENCE_REVIEW_COMPLETE',
       source_sha256=source_pins,history_reference_lines=history_references,episodes=results,
       total_cycles=sum(e['cycles'] for e in results),clipped_search_vectors=sum(e['clipped_search_vectors'] for e in results),
       semantic_decision='NO_OBSERVATION_CHANGE_REQUIRED_BY_THIS_CLIPPING_FINDING',
       semantic_limits='No proof of complete Markov state or preservation of every predictor useful to a learned policy; controller ignores this historical field in SEARCH and clears it before INSERT.',
       natural_recovery=recovery,historical_test_evidence=tests,new_physics=0,new_policy_forwards=0,new_updates=0,cumulative_dynamic=225))
    print('evidence complete',sum(e['clipped_search_vectors'] for e in results),'recovery',distance,'tests',len(tests),flush=True)

if __name__=='__main__':main()
