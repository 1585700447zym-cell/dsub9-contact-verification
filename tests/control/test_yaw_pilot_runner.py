"""No physics: bound and audit checks for the one-shot four-case runner."""
import importlib.util
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[2]


def api():
    path=ROOT/'tools/validation/run_yaw_pilot.py'
    spec=importlib.util.spec_from_file_location('yaw_runner_test',path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def test_claim_prevents_second_launch_and_keeps_original(tmp_path):
    m=api();m.claim_batch(tmp_path)
    (tmp_path/'run/retained.txt').write_text('evidence')
    with pytest.raises(FileExistsError):m.claim_batch(tmp_path)
    assert (tmp_path/'run/retained.txt').read_text()=='evidence'


def test_registration_exact_scope():
    s=api().scope()
    assert s['max_initializations']==4 and s['retries']==0
    assert s['cumulative_before']==368
    assert s['yaw_degrees']==[1.,-1.,1.5,-1.5]
    assert s['policy_calls']==s['training_updates']==0


def test_common_physics_mismatch_rejected():
    m=api();parent={k:{'value':1} for k in m.COMMON_KEYS}
    m.check_common(parent,parent)
    changed={**parent,'effective_kd':[0.]}
    with pytest.raises(ValueError):m.check_common(changed,parent)


def test_hash_drift_prevents_execution(tmp_path):
    m=api();(tmp_path/'a').write_text('first')
    pins={'a':m.sha(tmp_path/'a')}
    m.verify_inputs(pins,tmp_path)
    (tmp_path/'a').write_text('changed')
    with pytest.raises(ValueError):m.verify_inputs(pins,tmp_path)


def test_invalid_simulation_or_unqualified_stop_closes_batch():
    m=api();good={'status':'finished','valid':True,'stopped':True,'audit_passed':True}
    assert m.continue_batch(good)
    for key in good:
        changed={**good,key:False}
        assert not m.continue_batch(changed)


def test_nonfinite_raw_preserves_final_attempt_and_diagnostic(tmp_path):
    import gzip,json
    m=api();receipt={'reset_attempted':1,'physical_substeps':42,'status':'error'}
    m.publish_archive(tmp_path,{'trace':[{'force':float('nan')}]},receipt)
    saved=json.loads((tmp_path/'receipt.json').read_bytes())
    raw=json.loads(gzip.decompress((tmp_path/'episode.json.gz').read_bytes()))
    assert saved['reset_attempted']==1 and saved['physical_substeps']==42
    assert raw['trace'][0]['force']=={'nonfinite':'nan'}
    assert saved['nonfinite_fields']==['$.trace[0].force']


def test_archive_failure_still_saves_actual_costs(tmp_path):
    import json
    m=api();(tmp_path/'episode.json.gz').write_bytes(b'original')
    receipt={'reset_attempted':1,'physical_substeps':42,'status':'finished'}
    with pytest.raises(FileExistsError):m.publish_archive(tmp_path,{},receipt)
    saved=json.loads((tmp_path/'receipt.json').read_bytes())
    assert saved['status']=='error' and saved['physical_substeps']==42
    assert saved['archive_error']
    assert (tmp_path/'episode.json.gz').read_bytes()==b'original'


def test_timeout_reaps_worker_and_reconciles_known_attempt(tmp_path,monkeypatch):
    import json,subprocess
    m=api()
    class Process:
        def __init__(self,*args,**kwargs):self.waits=0;self.killed=False
        def wait(self,timeout=None):
            self.waits+=1
            if self.waits==1:raise subprocess.TimeoutExpired('worker',1)
            assert self.killed
            return -9
        def kill(self):self.killed=True
    monkeypatch.setattr(m.subprocess,'Popen',Process)
    (tmp_path/'receipt.json').write_text(json.dumps(dict(status='running',reset_attempted=1,
        physical_substeps=100,control_cycles=10)))
    (tmp_path/'progress.json').write_text(json.dumps(dict(reset_attempted=1,physical_substeps=200,cycles=20)))
    proof=m.supervise(['worker'],tmp_path,timeout=1)
    r=m.reconcile_receipt(tmp_path,proof)
    assert proof['process_exit_confirmed'] and proof['returncode']==-9
    assert r['reset_attempted']==1 and r['physical_substeps']==200
    assert r['count_precision']=='lower_bound' and not m.continue_batch(r)


def test_model_archive_uses_closed_windows_byte_format():
    assert api().model_archive_bytes('<mujoco>\n</mujoco>\n')==b'<mujoco>\r\n</mujoco>\r\n'


def test_before_reset_error_has_zero_cost_without_masking_original():
    from types import SimpleNamespace
    m=api();r={'error':'original','reset_attempted':0}
    m.snapshot_environment(r,SimpleNamespace(guard_facts={'simulation_valid':True}))
    assert r['physical_substeps']==0 and r['peaks']=={} and r['error']=='original'
