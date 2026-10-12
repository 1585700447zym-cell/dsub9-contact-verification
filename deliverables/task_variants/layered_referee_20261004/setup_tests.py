from pathlib import Path
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
s=(ROOT/'tests/task_variants/test_deadline25_preflight.py').read_text(encoding='utf-8').split('\ndef test_new_task_changes_only_total_time_and_preserves_old_default')[0]
s=s.replace('run_deadline25_preflight','run_layered_referee_preflight').replace('==124 and ledger[\'cumulative_limit\']==129','==125 and ledger[\'cumulative_limit\']==130')
s=s.replace('from tools.learning.reference_session import ReferenceSearchSession','from tools.learning.layered_session import LayeredReferenceSession\n    from tools.model.layered_task import referee_metadata')
s=s.replace('s=make_session(env,config)',"config['geometry_referee']=referee_metadata()\n    s=make_session(env,config)").replace('isinstance(s,ReferenceSearchSession)','isinstance(s,LayeredReferenceSession)')
s+='''

def test_default_session_changes_only_referee_and_not_controller():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation import run_layered_referee_preflight as new
    from tools.validation import run_deadline25_preflight as old
    from tools.learning.guarded_environment import LearningEnvironment
    from tools.model.layered_task import layered_pin_fit
    from types import SimpleNamespace
    env=object.__new__(LearningEnvironment);env.config=SimpleNamespace(linear_speed=.001,linear_acceleration=.005)
    a=old.make_session(env);b=new.make_session(env)
    assert a.controller_factory().metadata()==b.controller_factory().metadata()
    assert a.finish_criteria==b.finish_criteria
    assert b.geometry_checker is layered_pin_fit and a.geometry_checker is not layered_pin_fit
    assert new.TASK_ID=='dsub9_clearance120_layered_25s_v4'


@pytest.mark.parametrize('mode',['missing','wrong_tolerance','old_version'])
def test_rejects_unbound_or_wrong_referee(mode):
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation.run_layered_referee_preflight import make_session
    from tools.model.layered_task import referee_metadata
    from types import SimpleNamespace
    config=dict(b2_config=dict(total_action_time_s=25.),drive_limits=dict(linear_speed_m_s=.001,linear_acceleration_m_s2=.005),geometry_referee=referee_metadata())
    if mode=='missing':del config['geometry_referee']
    elif mode=='wrong_tolerance':config['geometry_referee']['tolerance_m']=1e-6
    else:config['geometry_referee']['id']='old_whole_shaft'
    env=SimpleNamespace(config=SimpleNamespace(linear_speed=.001,linear_acceleration=.005))
    with pytest.raises(ValueError,match='Geometry referee'):make_session(env,config)
'''
(ROOT/'tests/task_variants/test_layered_referee_preflight.py').write_text(s,encoding='utf-8')
