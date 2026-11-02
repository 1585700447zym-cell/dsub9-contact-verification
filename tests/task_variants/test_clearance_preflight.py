import pytest


@pytest.fixture(scope='module',autouse=True)
def qualified_runtime():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()


def test_cases_are_fixed_and_cover_both_difficulty_levels():
    from tools.validation.run_clearance_preflight import case_specs
    specs = case_specs()
    assert [(r['x_um'], r['y_um']) for r in specs] == [(0,0),(100,0),(-100,0),(0,100),(0,-100),(150,0),(-150,0),(0,150),(0,-150)]
    assert len({r['id'] for r in specs}) == 9


@pytest.mark.parametrize('category,stop', [('FULL_SUCCESS',False),('TASK_FAILURE',False),('CONTACT_GUARD',True),('MOTION_VIOLATION',True),('INVALID_SIMULATION',True),('STOP_NOT_QUALIFIED',True)])
def test_next_case_preserves_ordinary_failure_but_stops_protection(category,stop):
    from tools.validation.run_clearance_preflight import case_specs, next_case
    entries = [dict(id=case_specs()[0]['id'], status='finished', outcome=dict(task_outcome=category, simulation_valid=category!='INVALID_SIMULATION', physical_stopped=category!='STOP_NOT_QUALIFIED'))]
    assert (next_case(entries) is None) == stop


def test_interrupted_started_episode_is_never_implicitly_retried():
    from tools.validation.run_clearance_preflight import case_specs, next_case
    with pytest.raises(RuntimeError, match='Unfinished'):
        next_case([dict(id=case_specs()[0]['id'],status='running')])


def test_output_claim_does_not_overwrite_existing_results(tmp_path):
    from tools.validation.run_clearance_preflight import claim_run
    claim_run(tmp_path/'run')
    marker=tmp_path/'run'/'ledger.json'
    before=marker.read_bytes()
    with pytest.raises(FileExistsError):
        claim_run(tmp_path/'run')
    assert marker.read_bytes()==before


@pytest.mark.parametrize('archive_fails',[False,True])
def test_error_record_preserves_previous_archive_and_facts_even_if_archive_fails(tmp_path,monkeypatch,archive_fails):
    import json,gzip
    from types import SimpleNamespace
    from tools.validation import run_clearance_preflight as runner
    from tools.validation.run_contact_cases import ContactCase
    ledger=runner.claim_run(tmp_path/'run');run=tmp_path/'run'
    entry=dict(id='aligned',status='running');ledger['episodes'].append(entry)
    previous=run/'aligned.json.gz';previous.write_bytes(b'previous-valid-partial')
    env=SimpleNamespace(physical_steps=10,guard_facts={'simulation_valid':False,'invalid_reasons':['INVALID_INITIAL_STATE']},
        peaks={'force_N':.03},events=[{'reason':'FORCE_LIMIT'}],stop_samples=[],
        data=SimpleNamespace(qpos=[0,0,-.004,1,0,0,0],qvel=[0]*6,time=.002))
    if archive_fails:
        monkeypatch.setattr(runner,'archive_episode',lambda *args:(_ for _ in ()).throw(OSError('disk failure')))
    runner.record_error(run,ledger,entry,ValueError('reset failed'),ContactCase.aligned(),[],env,None)
    saved=json.loads((run/'ledger.json').read_text())
    assert saved['status']=='error' and saved['episodes'][0]['status']=='error'
    assert saved['episodes'][0]['error_facts']['guard_facts']['simulation_valid'] is False
    assert saved['episodes'][0]['error_facts']['case']['name']=='aligned'
    assert previous.read_bytes()==b'previous-valid-partial'
    if archive_fails:
        assert 'disk failure' in saved['episodes'][0]['archive_error']
    else:
        archived=json.loads(gzip.decompress((run/'aligned.error.json.gz').read_bytes()))
        assert archived['peaks']['force_N']==.03
        assert archived['initial_or_current_state']['qpos'][2]==-.004


def test_prepared_configuration_records_verified_runtime(tmp_path):
    from tempfile import TemporaryDirectory
    from pathlib import Path
    from tools.validation.run_clearance_preflight import prepare,ROOT
    with TemporaryDirectory(dir=ROOT/'tmp') as folder:
        configuration=prepare(Path(folder))
    proof=configuration['runtime_proof']
    assert proof['version']=='3.13.0' and proof['dll_verified']
    assert proof['dll_sha256'] and proof['compatibility_record_sha256']


@pytest.mark.parametrize('failure_phase',['reset','advance'])
def test_execute_error_preserves_actual_attempt_and_stops_schedule(tmp_path,monkeypatch,failure_phase):
    import json
    from types import SimpleNamespace
    from tools.validation import run_clearance_preflight as runner
    from tools.learning import guarded_environment,guarded_session
    class Environment:
        def __init__(self,**kwargs):
            self.physical_steps=0;self.config=SimpleNamespace(control_period=.002)
            self.guard_facts={'simulation_valid':True,'contact_reasons':[]};self.peaks={};self.events=[];self.stop_samples=[]
            self.data=SimpleNamespace(qpos=[0,0,-.004,1,0,0,0],qvel=[0]*6,time=0.)
    def reset(self,case):
        self.cycle_id=0;self.done=False;self.initial_trace_row={'time_s':0.}
        self.controller=self.controller_factory()
        if failure_phase=='reset':raise ValueError('reset injection')
    def advance(self,action):
        (tmp_path/'run/aligned.json.gz').write_bytes(b'previous partial')
        raise ValueError('advance injection')
    monkeypatch.setattr(guarded_environment,'LearningEnvironment',Environment)
    monkeypatch.setattr(guarded_session.CandidateEpisodeSession,'reset',reset)
    monkeypatch.setattr(guarded_session.CandidateEpisodeSession,'advance_cycle',advance)
    monkeypatch.setattr(runner,'input_hashes',lambda:{})
    runner.write(tmp_path/'configuration.json',dict(input_sha256={},guard_config={'max_rotation_from_start_rad':.04,'initial_roll_pitch_limit_rad':.01},b2_config={}))
    with pytest.raises(ValueError,match=failure_phase+' injection'):
        runner.execute(tmp_path)
    ledger=json.loads((tmp_path/'run/ledger.json').read_text())
    assert ledger['status']=='error' and len(ledger['episodes'])==1
    assert ledger['unused_closed']==8 and ledger['episodes'][0]['error_facts']['case']['name']=='aligned'
    assert ledger['episodes'][0]['physical_substeps']==0
    if failure_phase=='advance':assert (tmp_path/'run/aligned.json.gz').read_bytes()==b'previous partial'


def test_ledger_write_failure_does_not_prevent_error_archive(tmp_path,monkeypatch):
    import json
    from tools.validation import run_clearance_preflight as runner
    from tools.validation.run_contact_cases import ContactCase
    ledger=runner.claim_run(tmp_path/'run');entry={'id':'aligned','status':'running'};ledger['episodes'].append(entry)
    original=runner.write
    calls=[]
    def fail_once(path,value):
        calls.append(path)
        if len(calls)==1:raise OSError('ledger unavailable once')
        original(path,value)
    monkeypatch.setattr(runner,'write',fail_once)
    runner.record_error(tmp_path/'run',ledger,entry,ValueError('constructor'),ContactCase.aligned(),[],None,None)
    saved=json.loads((tmp_path/'run/ledger.json').read_text())
    assert saved['status']=='error' and 'unavailable once' in saved['episodes'][0]['ledger_write_error']
    assert (tmp_path/'run/aligned.error.json.gz').exists()
