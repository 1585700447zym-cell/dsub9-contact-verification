"""Entry/supervision state protocol only; subprocess workers are not launched."""
import importlib,importlib.util,json
import pytest

def api():
    assert importlib.util.find_spec('tools.validation.run_force_failure_cycle') is not None,'New runner is absent'
    return importlib.import_module('tools.validation.run_force_failure_cycle')

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value),encoding='utf-8')

def stop_fixture(folder):
    from tools.learning.force_failure_cycle import ForceLedger
    from tools.learning.bounded_contact import ForceFailureStop
    run=folder/'run';run.mkdir();ledger=ForceLedger(run/'ledger.json')
    for i in range(4):ledger.start('initial',str(i));ledger.finish({})
    for i in range(2):
        ledger.start('training',f'train_{i:02d}')
        ledger.finish(dict(task_outcome='CONTACT_GUARD',success=False))
    exc=ForceFailureStop('two_consecutive_force_failures','train_01');ledger.stop(exc)
    write(run/'controlled_stop.json',dict(**exc.record(),ledger=ledger.state))
    return run

def test_one_shot_claim_refuses_second_launch(tmp_path,monkeypatch):
    m=api();monkeypatch.setattr(m,'DELIVERY',tmp_path);m.claim('worker')
    with pytest.raises(FileExistsError):m.claim('worker')

def test_controlled_exit_preserves_finished_failure_ledger(tmp_path):
    m=api();run=stop_fixture(tmp_path)
    result=m.finalize_exit(20,tmp_path)
    assert result['kind']=='force_failure_frequency' and result['retry_allowed'] is False
    state=json.loads((run/'ledger.json').read_text())
    assert state['status']=='stopped' and state['active'] is None
    assert state['attempts'][-1]['status']=='finished'
    assert not (run/'failure.json').exists()

@pytest.mark.parametrize('code,kind',[(0,'incomplete_execution'),(20,'invalid_controlled_stop'),
    (-1073741819,'native_crash'),(1,'entry_rejection')])
def test_exit_code_alone_never_proves_completion_or_controlled_stop(tmp_path,code,kind):
    m=api();result=m.finalize_exit(code,tmp_path)
    assert result['kind']==kind and not result['execution_complete'] and result['retry_allowed'] is False

def test_crash_cannot_be_relabelled_using_stale_controlled_stop(tmp_path):
    m=api();run=stop_fixture(tmp_path)
    result=m.finalize_exit(-1073741819,tmp_path)
    assert result['kind']=='native_crash'
    assert json.loads((run/'ledger.json').read_text())['status']=='failed'

def test_missing_authorization_in_cli_never_calls_supervisor(tmp_path,monkeypatch):
    m=api();monkeypatch.setattr(m,'DELIVERY',tmp_path)
    with pytest.raises(ValueError,match='authorization'):
        m.main(['--candidate-sha256','a'*64])
    assert not list(tmp_path.iterdir())

def test_child_commands_preserve_both_external_pins():
    m=api();cmd=m.child_command('a'*64,'b'*64,restore=True)
    assert cmd[cmd.index('--candidate-sha256')+1]=='a'*64
    assert cmd[cmd.index('--authorization-sha256')+1]=='b'*64
    assert '--restore' in cmd and '--worker' not in cmd

def test_worker_retains_controlled_stop_without_starting_final_evaluation(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from tools.learning.bounded_contact import ForceFailureStop
    from tools.learning import bounded_checkpoint as cp,bounded_cycle,bounded_contact
    m=api();monkeypatch.setattr(m,'DELIVERY',tmp_path)
    monkeypatch.setattr(m,'require_parent',lambda restore:None)
    monkeypatch.setattr(m,'verify_initial_chain',lambda chain:dict(synthetic_only=True))
    monkeypatch.setattr(m,'reuse_baseline',lambda run:None)
    def forbidden(*a,**kw):raise AssertionError('No optimization, subprocess or generic failure handler allowed')
    chain=SimpleNamespace(fail=forbidden)
    monkeypatch.setattr(bounded_contact,'BoundedCollection',lambda **kw:chain)
    monkeypatch.setattr(cp,'save_checkpoint',lambda *a:'synthetic')
    def initial_only(chain,stage,*,ledger,output,checkpoint_sha256):
        assert stage=='initial','No evaluation after frequency stop'
        for i in range(4):ledger.start('initial',str(i));ledger.finish({})
    def stopped_train(chain,*,ledger,output):
        for i in range(2):
            ledger.start('training',f'train_{i:02d}')
            ledger.finish(dict(success=False,task_outcome='CONTACT_GUARD'))
        exc=ForceFailureStop('two_consecutive_force_failures','train_01');ledger.stop(exc);raise exc
    monkeypatch.setattr(bounded_cycle,'evaluate',initial_only)
    monkeypatch.setattr(bounded_cycle,'train',stopped_train)
    monkeypatch.setattr(m.subprocess,'run',forbidden)
    with pytest.raises(ForceFailureStop):m.worker(SimpleNamespace())
    assert m.finalize_exit(20,tmp_path)['kind']=='force_failure_frequency'
    assert not (tmp_path/'run/frozen.json').exists()

def test_zero_exit_requires_every_registered_stage_and_recovery_evidence(tmp_path):
    from tools.learning.force_failure_cycle import ForceLedger
    m=api();run=tmp_path/'run';run.mkdir();ledger=ForceLedger(run/'ledger.json')
    for stage,cap in ledger.CAPS.items():
        for i in range(cap):ledger.start(stage,str(i));ledger.finish({})
    write(run/'frozen.json',dict(episodes=12,updates=4500))
    write(run/'training_episodes/update_budget.json',dict(attempted=4500,completed=4500))
    for stage in ('initial','final','restored','holdout_b2','holdout_sac'):
        write(run/stage/'verification.json',dict(training_state_unchanged=True))
    write(run/'restoration.json',dict(exact_physical_replay=True))
    write(run/'holdout_scope_gate.json',dict(passed=True))
    write(run/'completed.json',dict(status='execution_complete'))
    assert m.finalize_exit(0,tmp_path)['kind']=='incomplete_execution'


def integrity_fixture(folder,monkeypatch):
    """Synthetic file-integrity evidence, never a physical acceptance fixture."""
    import gzip
    from tools.learning.force_failure_cycle import ForceLedger
    from tools.learning.admission import digest
    from tools.learning.bounded_cycle import cases
    from tools.learning.bounded_contact import case_at,POINTS,SEED
    m=api();monkeypatch.setattr(m,'ROOT',folder)
    write(folder/'candidate.json',dict(synthetic_integrity_fixture=True))
    pin=digest(folder/'candidate.json');run=folder/'run';run.mkdir()
    def checkpoint(path):
        path.mkdir(parents=True);(path/'state.pt').write_bytes(b'synthetic payload: not loadable')
        write(path/'manifest.json',dict(version='bounded_checkpoint_manifest_v2',state_sha256=digest(path/'state.pt')))
        return digest(path/'manifest.json')
    initial=checkpoint(run/'initial_checkpoint');checkpoints=[]
    for i in range(12):
        path=f'training/checkpoints/train_{i:02d}'
        checkpoints.append(dict(path=path,sha256=checkpoint(run/path),episodes=i+1,updates=max(0,i-2)*500))
    frozen=checkpoints[-1];write(run/'training/checkpoints.json',checkpoints);write(run/'frozen.json',frozen)
    write(run/'training_episodes/update_budget.json',dict(attempted=4500,completed=4500))
    ledger=ForceLedger(run/'ledger.json');holdout_archives={}
    for stage in ledger.CAPS:
        training=stage=='training';attempts=[];results=[]
        points=[case_at(f'train_{i:02d}',*POINTS[i%4]) for i in range(12)] if training else cases(stage.startswith('holdout'))
        for case in points:
            name=case['name'];folder_run=run/'training_episodes'/name if training else run/stage/'episodes'/name
            folder_run.mkdir(parents=True)
            outcome=dict(task_outcome='FULL_SUCCESS',simulation_valid=True,physical_stopped=True,valid_for_learning=True)
            row=dict(success=True,cycles=1,**{k:v for k,v in outcome.items() if k!='valid_for_learning'})
            if not training:row['case']=name
            raw=dict(episode_id=name,case=case,seed=SEED,qualification_sha256=pin,
                outcome=outcome,transitions=[{}],fault=None,guard_clear=True,
                learning_eligibility=dict(version='force_only_v1',kind='guard_clear'))
            receipt=dict(episode_id=name,case=case,seed=SEED,qualification_sha256=pin,
                steps=1,committed=1 if training else 0,discarded=0 if training else 1,
                status='published' if training else 'evaluation_archived',guard_clear=True,
                learning_eligibility=raw['learning_eligibility'],**outcome)
            if not training:
                extra=dict(training_admitted=False,evaluation_method='zero_b2' if stage=='holdout_b2' else 'sac',
                    checkpoint_sha256=initial if stage=='initial' else frozen['sha256'])
                raw.update(extra);receipt.update(extra)
            archive=folder_run/'episode.json.gz';archive.write_bytes(gzip.compress(json.dumps(raw).encode()))
            receipt['archive_sha256']=digest(archive);write(folder_run/'status.json',receipt)
            attempts.append(receipt);results.append(row);ledger.start(stage,name);ledger.finish(row)
            if stage=='holdout_b2':holdout_archives[archive.relative_to(folder).as_posix()]=digest(archive)
        write(run/stage/'attempts.json',attempts)
        if not training:
            write(run/stage/'results.json',results);write(run/stage/'verification.json',dict(training_state_unchanged=True))
    write(run/'restoration.json',dict(exact_physical_replay=True,independent_performance_samples_added=0))
    write(run/'restore_process_exit.json',dict(role='restore',returncode=0,returncode_hex='0x0'))
    write(run/'holdout_scope_gate.json',dict(passed=True,qualification_sha256=pin,
        frozen_checkpoint_sha256=digest(run/'frozen.json'),archives=holdout_archives,
        evidence=[dict(case=c['name'],contact_cycles=1,guard_clear=True,physical_stopped=True,simulation_valid=True) for c in cases(True)]))
    write(run/'completed.json',dict(status='execution_complete'))
    return run


def test_complete_integrity_bundle_still_requires_later_physical_audit(tmp_path,monkeypatch):
    run=integrity_fixture(tmp_path,monkeypatch);result=api().finalize_exit(0,tmp_path)
    assert result['execution_complete'] and result['b2_complete'] is False


@pytest.mark.parametrize('damage',['archive_missing','archive_changed','checkpoint_missing','payload_changed',
    'wrong_frozen_path','case_missing','wrong_ledger_point','receipt_changed','scope_binding_changed'])
def test_completion_rejects_missing_or_mismatched_original_evidence(tmp_path,monkeypatch,damage):
    run=integrity_fixture(tmp_path,monkeypatch)
    archive=run/'final/episodes/x_pos_100/episode.json.gz'
    if damage=='archive_missing':archive.unlink()
    elif damage=='archive_changed':archive.write_bytes(b'changed')
    elif damage=='checkpoint_missing':(run/'training/checkpoints/train_11/manifest.json').unlink()
    elif damage=='payload_changed':(run/'training/checkpoints/train_11/state.pt').write_bytes(b'changed')
    elif damage=='wrong_frozen_path':
        r=api().read(run/'frozen.json');r['path']='../outside';write(run/'frozen.json',r)
    elif damage=='case_missing':write(run/'final/results.json',api().read(run/'final/results.json')[:-1])
    elif damage=='wrong_ledger_point':
        r=api().read(run/'ledger.json');r['attempts'][0]['id']='unregistered';write(run/'ledger.json',r)
    elif damage=='receipt_changed':
        r=api().read(run/'final/episodes/x_pos_100/status.json');r['committed']=1
        write(run/'final/episodes/x_pos_100/status.json',r)
    else:
        r=api().read(run/'holdout_scope_gate.json');r['archives']={};write(run/'holdout_scope_gate.json',r)
    assert api().finalize_exit(0,tmp_path)['kind']=='incomplete_execution'


def test_restore_native_crash_keeps_child_code_and_stops_before_holdout(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from tools.learning import bounded_checkpoint as cp,bounded_cycle,bounded_contact,repaired_cycle
    m=api();monkeypatch.setattr(m,'DELIVERY',tmp_path);monkeypatch.setattr(m,'require_parent',lambda restore:None)
    monkeypatch.setattr(m,'verify_initial_chain',lambda chain:{});monkeypatch.setattr(m,'reuse_baseline',lambda run:None)
    monkeypatch.setattr(bounded_contact,'BoundedCollection',lambda **kw:SimpleNamespace(fail=lambda exc:None))
    monkeypatch.setattr(cp,'save_checkpoint',lambda *a:'synthetic')
    seen=[]
    def evaluate(chain,stage,**kw):
        assert stage in ('initial','final');seen.append(stage)
    monkeypatch.setattr(bounded_cycle,'evaluate',evaluate)
    monkeypatch.setattr(bounded_cycle,'train',lambda *a,**kw:dict(sha256='synthetic'))
    monkeypatch.setattr(repaired_cycle,'development_decision',lambda run:{})
    monkeypatch.setattr(m.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=-1073741819))
    with pytest.raises(RuntimeError):m.worker(SimpleNamespace(expected_digest='a'*64,authorization_digest='b'*64))
    result=m.finalize_exit(1,tmp_path)
    assert seen==['initial','final'] and result['kind']=='native_crash'
    assert result['child_process']['role']=='restore'
    assert result['child_process']['returncode']==-1073741819
    assert result['child_process']['returncode_hex']=='0xc0000005'
    assert 'Separate restoration process failed' in result['underlying_failure']['error']


@pytest.mark.parametrize('cleaned',[True,False])
def test_supervisor_exception_seals_ledger_and_retains_cleanup_uncertainty(tmp_path,monkeypatch,cleaned):
    from types import SimpleNamespace
    from tools.learning.force_failure_cycle import ForceLedger
    m=api();monkeypatch.setattr(m,'DELIVERY',tmp_path)
    run=tmp_path/'run';run.mkdir();ledger=ForceLedger(run/'ledger.json');ledger.start('initial','x_pos_100')
    monkeypatch.setattr(m,'ForceAdmission',lambda *a,**kw:None)
    def supervise(*a):
        write(tmp_path/'process_exit.json',dict(status='supervisor_error',error='KeyboardInterrupt()',
            worker_stopped=cleaned,cleanup_error=None if cleaned else 'cleanup uncertain'))
        raise KeyboardInterrupt()
    spec=SimpleNamespace(loader=SimpleNamespace(exec_module=lambda module:setattr(module,'supervise',supervise)))
    monkeypatch.setattr(m.importlib.util,'spec_from_file_location',lambda *a:spec)
    monkeypatch.setattr(m.importlib.util,'module_from_spec',lambda spec:SimpleNamespace())
    with pytest.raises(KeyboardInterrupt):m.main(['--candidate-sha256','a'*64,'--authorization-sha256','b'*64])
    state=m.read(run/'ledger.json');report=m.read(tmp_path/'exit_classification.json')
    assert state['status']=='failed' and state['dynamic_starts']==1 and state['active'] is None
    assert state['attempts'][0]['status']=='interrupted_by_supervisor_error'
    assert report['kind']=='supervisor_error' and report['worker_stopped'] is cleaned
    assert report['cleanup_error']==(None if cleaned else 'cleanup uncertain') and not report['retry_allowed']


def test_technical_candidate_uses_immutable_document_snapshots(tmp_path):
    from tools.learning.force_failure_cycle import DELIVERY
    spec=importlib.util.spec_from_file_location('force_qualify_test',DELIVERY/'qualify.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    (tmp_path/'README.md').write_bytes(b'approved proposed plan')
    (tmp_path/'实施记录.md').write_bytes(b'preparation record')
    names=m.freeze_docs(tmp_path);assert len(names)==2
    snapshots={name:(tmp_path/name).read_bytes() for name in names}
    assert m.freeze_docs(tmp_path)==names
    (tmp_path/'README.md').write_bytes(b'live progress changed')
    assert {name:(tmp_path/name).read_bytes() for name in names}==snapshots
    with pytest.raises(ValueError,match='snapshot'):m.freeze_docs(tmp_path)
