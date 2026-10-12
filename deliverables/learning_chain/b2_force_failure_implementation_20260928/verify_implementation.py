"""Read evidence and hashes only. Never grants admission or executes learning."""
from pathlib import Path
import gzip,hashlib,json,os,runpy,sys,xml.etree.ElementTree as ET

D=Path(__file__).resolve().parent;ROOT=D.parents[2]
sys.path.insert(0,str(ROOT))
os.environ['MPLCONFIGDIR']=str(ROOT/'tmp/learning_mpl_cache')
read=lambda p:json.loads(p.read_bytes())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
write=lambda p,v:p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

runpy.run_path(str(D/'verify_history.py'))
binding=read(D/'suite_after_review_binding.json')
required=read(D/'required_tests.json')
cases=list(ET.parse(D/'suite_after_review.xml').getroot().iter('testcase'))
ids=sorted(c.attrib['classname']+'::'+c.attrib['name'] for c in cases)
assert len(ids)==len(set(ids))==required['count']==149
assert ids==required['tests']==binding['test_ids']
assert all(c.find(k) is None for c in cases for k in ('failure','error','skipped'))
assert binding['exit_code']==binding['tests_with_failure_or_error']==0
assert binding['tests']==149
assert binding['forbidden_call_counts']==dict(optimizer=0,physics=0,prediction=0)
assert binding['report_sha256']==sha(D/'suite_after_review.xml')
assert binding['runner_sha256']==sha(D/'run_tests.py')
from tools.learning.fixed_rotation_cycle import fixed_sources
from tools.learning.force_failure_preparation import force_config
assert binding['source_sha256']==fixed_sources()
assert read(D/'preparation_config.json')==force_config()
assert force_config()['execution']['authorized_dynamic_starts']==0
assert force_config()['execution']['authorized_optimizer_calls']==0
from tools.learning.runtime import verify_runtime
verify_runtime(ROOT/'tmp/mujoco_3_13_probe')  # Import-path setup only; no model or dynamics.
from tools.learning.episode_rules import FORCE_ONLY
clear_compatibility=[]
for name in ('train_00','train_01'):
    path=ROOT/'deliverables/learning_chain/b2_fixed_rotation_cycle_20260928/run/training_episodes'/name/'episode.json.gz'
    raw=json.loads(gzip.decompress(path.read_bytes()))
    assert FORCE_ONLY.classify(raw)==dict(version='force_only_v1',kind='guard_clear')
    clear_compatibility.append(dict(episode=name,task_outcome=raw['outcome']['task_outcome'],archive_sha256=sha(path)))
assert {r['task_outcome'] for r in clear_compatibility}=={'FULL_SUCCESS','TASK_FAILURE'}

assessment=dict(status='implementation_protocol_verification_passed',tests_passed=149,
    source_count=len(binding['source_sha256']),forbidden_call_counts=binding['forbidden_call_counts'],
    review=dict(reviewer='GPT-6 Astra',reviews=1,critical=0,important=3,important_resolved=3,minor=0,
        declined_to_judge=[],fixes=[
            dict(issue='per_cycle_event_consistency',verification='test_review_event_and_frozen_clock_counterexamples'),
            dict(issue='frozen_physical_clock',verification='test_review_event_and_frozen_clock_counterexamples'),
            dict(issue='administrative_frequency_stop',verification=[
                'test_review_frequency_stop_finishes_run_ledger_without_runtime_fault',
                'test_controlled_stop_propagates_through_outer_runner'])]),
    review_red=dict(tests=10,failed=9,already_passed=1),
    archived_guard_clear_compatibility=clear_compatibility,
    history=dict(parent_sources=901,shared_source_snapshots=5,closed_fixed_cycle_files=100,
        prior_repaired_cycle_files=126,unchanged=True),
    synthetic_checkpoint=dict(independent_process=True,optimizer_updates=0,
        recorded_transition_fixture=True,actual_trained_state_restore=False,physical_replay=False),
    execution_admitted=False,training_budget_granted=False,b2_complete=False,
    performance_improvement_demonstrated=False,
    restrictions=['Preparation admission refuses execution.',
        'Archived failure data is not imported into an actual training replay.',
        'Old unused 23 starts and 4000 updates remain closed.',
        'Future execution entry/supervisor must preserve the typed controlled-stop result and receive new qualification.',
        'All historic entry points remain bound to their original strict rule.'])
if '--check' in sys.argv:
    assert read(D/'assessment.json')==assessment
    for path,pin in read(D/'verification.json')['files'].items():assert sha(ROOT/path)==pin,path
    print('Final implementation evidence, required tests and historical hashes verified.')
else:
    assert not (D/'assessment.json').exists(),'Use --check for sealed evidence.'
    write(D/'assessment.json',assessment)
    paths=[p for p in D.rglob('*') if p.is_file() and p.name!='verification.json']
    write(D/'verification.json',dict(files={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(paths)},
        source_sha256=binding['source_sha256'],execution_admitted=False))
    print(json.dumps({k:assessment[k] for k in ('status','tests_passed','source_count','execution_admitted')},ensure_ascii=False))
