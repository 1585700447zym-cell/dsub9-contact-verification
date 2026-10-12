"""Synthetic command data + orchestration protocol, never a neural test."""
from copy import deepcopy
import numpy as np
import pytest,sys
from numeric_contract import profile_contract,profile_pin
from synthetic_data import synthetic_episode,test_states as fixed_states
from numeric_worker import NumericAdmission,normalized_state,execute_numeric
from small_bound_profile import audit_small_bound_episode


class Dummy:
    def __init__(self):
        self.inner=self;self.contract=profile_contract();self.mode='F50';self.warm_draws=0;self.held=[0.]*4
        self.binding=dict(mode='F50',purpose='synthetic_qualification',qualification_sha256='a'*64,
                          config_sha256=self.contract['engine_config_sha256'])
        self.rng=np.random.default_rng(np.random.SeedSequence([2026092716,1]))
        self.updater=type('Meta',(),{'counts':{'critic':0},'fingerprints':lambda _:self.contract['zero_origin']})()
    def warm_action(self,cycle):
        if cycle%50==0:self.held=self.rng.uniform(-1,1,4).tolist();self.warm_draws+=1
        return self.held.copy()


def test_synthetic_a_replay_and_physical_scale_are_distinct():
    c=Dummy();raw=synthetic_episode(c,'warmup',0)
    assert raw['scope']=='synthetic_qualification' and raw['dynamics_executed'] is False and raw['synthetic'] is True
    assert len(raw['transitions'])==80 and raw['warmup_draws']==2
    assert raw['transitions'][0]['action']==raw['transitions'][0]['sampling_request']
    assert max(abs(x) for x in raw['transitions'][0]['action'])>.25
    assert raw['transitions'][0]['action_log']['compositor_action']==(np.array(raw['transitions'][0]['action'])*.25).tolist()
    assert audit_small_bound_episode(raw,c.contract)['cycles']==80
    assert 'torch' not in sys.modules


def test_inactive_tail_reward_and_complete_mask():
    c=Dummy();raw=synthetic_episode(c,'online',0)
    assert [r['action_active'] for r in raw['transitions'][-3:]]==[True,False,False]
    assert raw['transitions'][-1]['action']==[0.]*4 and raw['transitions'][-1]['terminated'] is True
    assert sum(r['reward_terms']['terminal']!=0 for r in raw['transitions'])==1
    assert raw['transitions'][-1]['reward_terms']['terminal']==-2.
    bad=deepcopy(raw);bad['transitions'][0]['action']=(np.asarray(bad['transitions'][0]['action'])*.25).tolist()
    with pytest.raises(ValueError):audit_small_bound_episode(bad,c.contract)


def test_observation_test_states_are_fixed_16_and_permission_valid():
    from tools.learning.v4_pilot_contract import permission
    states=fixed_states();assert len(states)==16 and all(len(o)==137 and permission(o,'F50') for o in states)
    assert states==fixed_states()


def test_missing_grant_rejected_before_model_or_output(tmp_path):
    with pytest.raises(PermissionError):execute_numeric({},None,None,tmp_path/'must_not_exist')
    assert not (tmp_path/'must_not_exist').exists() and 'torch' not in sys.modules


def test_snapshot_comparison_ignores_only_measured_wall_time():
    a=dict(history=[dict(wall_s=1.,indices=[['warm',3]],loss=.2)],
        journal='{"event":"complete","stats":{"wall_s":1.0,"loss":0.2}}\n',rng={'warm':3},archives={'a':b'raw'})
    b=deepcopy(a);b['history'][0]['wall_s']=9.;b['journal']='{"event":"complete","stats":{"wall_s":9.0,"loss":0.2}}\n'
    assert normalized_state(a)==normalized_state(b)
    b['rng']['warm']=4;assert normalized_state(a)!=normalized_state(b)


def test_numeric_admission_requires_pending_charge_and_never_physics(tmp_path,monkeypatch):
    import numeric_contract as module
    from test_numeric_contract import candidate,grant
    monkeypatch.setattr(module,'CLAIMS',tmp_path/'claims')
    c=candidate();c['hot_source_sha256']={};g=grant(c)
    l=module.NumericLedger.create(tmp_path/'run',c,g,module.digest(g))
    a=NumericAdmission(c,g,module.digest(g),l,'parent')
    with pytest.raises(PermissionError):a.verify('forward',profile_pin())
    with pytest.raises(PermissionError):a.verify('update',profile_pin())
    with pytest.raises(PermissionError):a.verify('physical',profile_pin())
    t=l.reserve('parent','update');assert a.verify('update',profile_pin())['purpose']=='synthetic_qualification'
    l.complete(t)


def test_all_execution_cli_modes_reject_absent_grant_before_runtime(tmp_path):
    import subprocess
    from numeric_contract import OUT,ROOT
    for mode in ('--execute','--worker','--reader'):
        output=tmp_path/mode.removeprefix('--')
        r=subprocess.run([sys.executable,'-I',str(OUT/'numeric_worker.py'),mode,'--folder',str(output)],cwd=ROOT,capture_output=True,text=True)
        assert r.returncode!=0 and 'PermissionError' in r.stderr
        assert not output.exists() and not output.with_name(output.name+'.supervision').exists()
    r=subprocess.run([sys.executable,'-I',str(OUT/'numeric_worker.py'),'--inspect'],cwd=ROOT,capture_output=True,text=True)
    assert r.returncode==0 and 'PREPARED_NOT_AUTHORIZED' in r.stdout


def charged_fixture(tmp_path,monkeypatch):
    from test_numeric_contract import candidate,grant
    import numeric_contract as module
    monkeypatch.setattr(module,'CLAIMS',tmp_path/'claims')
    c=candidate();g=grant(c);return module.NumericLedger.create(tmp_path/'run',c,g,module.digest(g))


def test_returned_forward_is_counted_before_output_audit_failure(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from numeric_worker import predict_states
    l=charged_fixture(tmp_path,monkeypatch)
    fake=SimpleNamespace(predict=lambda *args,**kw:([2.,0,0,0],None))
    with pytest.raises(ValueError):predict_states(fake,l,'parent')
    assert l.data['forwards_attempted']==l.data['forwards_completed']==1


def test_committed_update_is_counted_before_critic_audit_failure(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from numeric_worker import one_update
    l=charged_fixture(tmp_path,monkeypatch)
    q=SimpleNamespace(register_forward_pre_hook=lambda fn:SimpleNamespace(remove=lambda:None))
    updater=SimpleNamespace(counts={'critic':0},policy=SimpleNamespace(critic=q,critic_target=q))
    def update(n):updater.counts['critic']+=1;return [{'indices':[]}]
    c=SimpleNamespace(inner=SimpleNamespace(updater=updater,replay=SimpleNamespace(_state=SimpleNamespace(episodes=[]))),update=update)
    with pytest.raises(ValueError):one_update(c,l,'parent')
    assert l.data['updates_attempted']==l.data['updates_completed']==1


def test_runtime_resolution_rejects_same_version_external_package_without_import():
    import numeric_worker as m
    from types import SimpleNamespace
    with pytest.raises(ValueError):m.check_module_origins({'torch':'D:/qualified/torch/__init__.py'},
        finder=lambda name:SimpleNamespace(origin='D:/external/torch/__init__.py'))
    assert 'torch' not in sys.modules


def test_reader_timeout_terminates_live_tree_and_records_confirmation(tmp_path,monkeypatch):
    import numeric_worker as m,subprocess
    from types import SimpleNamespace
    events=[]
    class Process:
        pid=123
        def __init__(self):self.stopped=False
        def wait(self,timeout):
            if not self.stopped:raise subprocess.TimeoutExpired('pure fixture',timeout)
            return -1
        def poll(self):return -1 if self.stopped else None
    process=Process()
    monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**k:process)
    def stop(p):events.append(p.poll());p.stopped=True;return True
    monkeypatch.setattr(m,'stop_owned_tree',stop,raising=False)
    with pytest.raises(subprocess.TimeoutExpired):m.managed_child(['never_launched'],tmp_path/'reader.log',timeout=1,receipt=tmp_path/'exit.json')
    import json
    assert events==[None] and json.loads((tmp_path/'exit.json').read_text())['worker_stopped'] is True


def test_numeric_costs_are_measured_separately_with_pure_fakes():
    import numeric_worker as m
    from types import SimpleNamespace
    class FakeUpdater:
        def __init__(self):self.protocol_fixture=True
    torch_fixture=SimpleNamespace(load=lambda *a,**k:dict(protocol_fixture=True))
    with m.capture_costs(torch_fixture,FakeUpdater) as metrics:
        FakeUpdater();torch_fixture.load('not_a_real_checkpoint')
    assert metrics['model_constructions_attempted']==metrics['model_constructions_completed']==1
    assert metrics['tensor_reads_attempted']==metrics['tensor_reads_completed']==1
    assert 'torch' not in sys.modules


def test_zero_origin_rejects_used_optimizer_replay_or_rng_with_pure_state():
    from numeric_worker import verify_zero_state
    rng=dict(warm={'state':1},replay={'state':2},boundary={'state':3})
    state=dict(origin={'actor':'fixture'},updater=dict(counts={'critic':0},actor={'state':{}},critic={'state':{}},temperature={'state':{}}),
        replay=dict(size=0,seen=[],episodes=[]),rng=rng,archives={},attempts=[],history=[],journal='',update_attempts=0,
        warm=dict(draws=0,held=[0.]*4),stop_reason=None)
    assert verify_zero_state(state,state['origin'],rng)
    optimizer=deepcopy(state);optimizer['updater']['actor']['state']={'used':1}
    replay=deepcopy(state);replay['replay']['size']=1
    changed_rng=deepcopy(state);changed_rng['rng']['replay']['state']=4
    for bad in (optimizer,replay,changed_rng):
        with pytest.raises(ValueError):verify_zero_state(bad,state['origin'],rng)
    assert 'torch' not in sys.modules


def test_cleanup_failure_retains_uncertain_receipt(tmp_path,monkeypatch):
    import numeric_worker as m,subprocess
    from types import SimpleNamespace
    process=SimpleNamespace(pid=123,wait=lambda **k:(_ for _ in ()).throw(subprocess.TimeoutExpired('fixture',1)))
    monkeypatch.setattr(m.subprocess,'Popen',lambda *a,**k:process)
    monkeypatch.setattr(m,'stop_owned_tree',lambda *a:(_ for _ in ()).throw(OSError('stop denied')))
    with pytest.raises(m.UnconfirmedStop):m.managed_child(['never_launched'],None,1,tmp_path/'exit.json')
    from numeric_contract import read
    receipt=read(tmp_path/'exit.json')
    assert receipt['worker_stopped'] is False and 'stop denied' in receipt['cleanup_error']


def test_failed_constructor_and_read_keep_attempts_and_restore_wrappers():
    import numeric_worker as m
    from types import SimpleNamespace
    class Failed:
        def __init__(self):raise ValueError('fixture constructor')
    def failed_load(*a,**k):raise ValueError('fixture read')
    t=SimpleNamespace(load=failed_load);original=Failed.__init__
    with m.capture_costs(t,Failed) as costs:
        with pytest.raises(ValueError):Failed()
        with pytest.raises(ValueError):t.load('fixture')
    assert costs['model_constructions_attempted']==costs['tensor_reads_attempted']==1
    assert costs['model_constructions_completed']==costs['tensor_reads_completed']==0
    assert Failed.__init__ is original and t.load is failed_load
