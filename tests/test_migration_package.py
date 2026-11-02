"""Small archive/CLI checks only: no numerical model or environment imports."""
import hashlib
import importlib
import json
from pathlib import Path
import zipfile

import pytest


def module():
    try:
        return importlib.import_module('tools.migration.package')
    except ModuleNotFoundError:
        pytest.fail('Migration restore module is not implemented')


def bundle(root, entries=None):
    entries = entries or {'checkpoint/state.pt': b'saved-state', 'engine/tools/example.py': b'x=1\n'}
    root.mkdir(parents=True, exist_ok=True)
    archive = root/'fixture.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        for name, value in entries.items(): z.writestr(name, value)
    sha = lambda b: hashlib.sha256(b).hexdigest()
    manifest = dict(version='f4000_migration_v1', archives=[dict(
        path='fixture.zip', bytes=archive.stat().st_size, sha256=sha(archive.read_bytes()),
        files={name: dict(bytes=len(value), sha256=sha(value)) for name,value in entries.items()})],
        layout=dict(checkpoint='checkpoint', engine='engine', runtime='runtime'),
        source=dict(updates=4000))
    p=root/'package.json'; p.write_text(json.dumps(manifest),encoding='utf-8')
    return p


def test_restore_is_relocatable_and_preserves_existing_files(tmp_path):
    m=module(); src=bundle(tmp_path/'source')
    target=tmp_path/'new machine with spaces'/'state'
    result=m.restore(src,target)
    assert (target/'checkpoint/state.pt').read_bytes()==b'saved-state'
    assert result['checkpoint']==str((target/'checkpoint').resolve())
    assert m.restore(src,target)==result


def test_restore_rejects_archive_escape_before_writing(tmp_path):
    m=module(); src=bundle(tmp_path/'source',{'../outside.txt':b'bad'})
    with pytest.raises(ValueError,match='[Pp]ath|[Ee]scape|[Uu]nsafe'):
        m.restore(src,tmp_path/'destination')
    assert not (tmp_path/'outside.txt').exists()


def test_restore_rejects_tampered_archive(tmp_path):
    m=module(); src=bundle(tmp_path/'source')
    (src.parent/'fixture.zip').write_bytes(b'not the registered archive')
    with pytest.raises(ValueError,match='digest|Digest|SHA'):
        m.restore(src,tmp_path/'destination')


def test_restore_never_overwrites_modified_payload(tmp_path):
    m=module(); src=bundle(tmp_path/'source'); target=tmp_path/'destination'
    m.restore(src,target)
    (target/'checkpoint/state.pt').write_bytes(b'user changed it')
    with pytest.raises(ValueError,match='digest|Digest|SHA|modified'):
        m.restore(src,target)
    assert (target/'checkpoint/state.pt').read_bytes()==b'user changed it'


def test_run_default_checks_and_requires_an_explicit_prepared_batch():
    try:
        m=importlib.import_module('tools.migration.run_f4000')
    except ModuleNotFoundError:
        pytest.fail('Migration execution entry is not implemented')
    args=m.parser().parse_args([])
    assert args.action=='check'
    with pytest.raises(ValueError,match='output|batch|directory'):
        m.validate_request(m.parser().parse_args(['--run']))


def test_continuation_registration_rejects_zero_or_excess_budget():
    try:
        m=importlib.import_module('tools.migration.run_f4000')
    except ModuleNotFoundError:
        pytest.fail('Migration execution entry is not implemented')
    for value in ['0','9']:
        args=m.parser().parse_args(['--prepare','--purpose','continuation','--output','experiments/test',
                                   '--episodes',value,'--updates-per-episode','500'])
        with pytest.raises(ValueError,match='episode|budget|1.*8'):
            m.validate_request(args)


def test_changed_prepared_registration_is_rejected_before_running(tmp_path):
    m=importlib.import_module('tools.migration.run_f4000')
    paths={'package_sha256':'package','root':str(tmp_path/'restored')}
    reg=dict(version='f4000_original_protocol_continuation_v1',package_sha256='package',
        paths=paths,launcher_sha256=m.digest(Path(m.__file__)),updates_budget=500)
    p=tmp_path/'registration.json';p.write_text(json.dumps(reg),encoding='utf-8')
    (tmp_path/'prepared.json').write_text(json.dumps({'registration_sha256':m.digest(p)}),encoding='utf-8')
    reg['updates_budget']=1000;p.write_text(json.dumps(reg),encoding='utf-8')
    args=m.parser().parse_args(['--run','--output',str(tmp_path)])
    with pytest.raises(ValueError,match='registration|Registration|digest'):
        m.verified_registration(args,paths)


def test_run_costs_merge_progress_instead_of_reporting_temporary_zero(tmp_path):
    m=importlib.import_module('tools.migration.run_f4000')
    folder=tmp_path/'run/job';folder.mkdir(parents=True)
    for name,value in {'receipt.json':{'physical_substeps':0,'reset_attempted':0},
        'progress.json':{'physical_substeps':100,'reset_attempted':1},
        'job_result.json':{'actual_updates_for_job':0,'status':'UPDATING'},
        'update_progress.json':{'actual_updates_for_job':25}}.items():
        (folder/name).write_text(json.dumps(value),encoding='utf-8')
    function=getattr(m,'recorded_costs',None)
    assert callable(function),'Progress cost merger is not implemented'
    value=function(tmp_path)
    assert value['new_physical_substeps']==100
    assert value['new_optimizer_updates']==25
    assert value['new_initializations']==1
    assert value['counts_are_recorded_lower_bounds'] is True


def test_reset_failure_receipt_survives_missing_session_fields():
    from types import SimpleNamespace
    m=importlib.import_module('tools.migration.run_f4000')
    function=getattr(m,'collection_receipt',None)
    assert callable(function),'Early-reset failure receipt handler is not implemented'
    receipt={};env=SimpleNamespace(physical_steps=0,guard_facts={},reference_checks={},
        reference_envelope_corrections=0,data=SimpleNamespace(time=0))
    trainer=SimpleNamespace(policy_calls=4,warmup_draws=0)
    raw=dict(error='reset failed',cost={'initializations_completed':0},
        outcome=dict(simulation_valid=False,physical_stopped=False,task_outcome='INVALID_SIMULATION'))
    function(receipt,env,SimpleNamespace(),trainer,raw,4,0)
    assert receipt['status']=='error'
    assert receipt['control_cycles']==0 and receipt['reset_completed']==0
    assert receipt['valid'] is False and receipt['stopped'] is False


def test_partial_audit_and_attempted_update_costs_are_retained():
    from types import SimpleNamespace
    m=importlib.import_module('tools.migration.run_f4000')
    function=getattr(m,'final_costs',None)
    assert callable(function),'Failure cost recorder is not implemented'
    trainer=SimpleNamespace(policy_calls=7,warmup_draws=0,update_attempts=4001,
        updater=SimpleNamespace(counts={'critic':4000}))
    source=SimpleNamespace(policy_calls=3,warmup_draws=0)
    result={};receipt={}
    function(result,receipt,trainer,source,4000,4000,1,0)
    assert result['audit_neural_policy_calls']==2
    assert result['attempted_updates_for_job']==1 and result['actual_updates_for_job']==0
    assert receipt['policy_calls']==6
