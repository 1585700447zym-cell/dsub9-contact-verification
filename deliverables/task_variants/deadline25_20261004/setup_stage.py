from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
old=ROOT/'tests/task_variants/test_reference_search_preflight.py'
text=old.read_text(encoding='utf-8').replace('run_reference_search_preflight','run_deadline25_preflight')
text=text.replace("==123 and ledger['cumulative_limit']==128", "==124 and ledger['cumulative_limit']==129")
text=text.replace('asdict(SearchConfig())','asdict(SearchConfig(total_action_time_s=25.))')
text += '''

def test_new_task_changes_only_total_time_and_preserves_old_default():
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation import run_deadline25_preflight as new
    from tools.validation import run_reference_search_preflight as old
    from types import SimpleNamespace
    from dataclasses import asdict
    from tools.learning.guarded_environment import LearningEnvironment
    env=object.__new__(LearningEnvironment)
    env.config=SimpleNamespace(linear_speed=.001,linear_acceleration=.005)
    a=old.make_session(env).controller_factory()
    b=new.make_session(env).controller_factory()
    ac=asdict(a.config);bc=asdict(b.config)
    assert ac.pop('total_action_time_s')==20.
    assert bc.pop('total_action_time_s')==25.
    assert ac==bc and type(a) is type(b)
    assert new.TASK_ID=='dsub9_clearance120_functional_25s_v3'


@pytest.mark.parametrize('deadline',[20.,30.,float('nan'),True])
def test_rejects_config_from_other_task_version(deadline):
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    from tools.validation.run_deadline25_preflight import make_session
    from types import SimpleNamespace
    env=SimpleNamespace(config=SimpleNamespace(linear_speed=.001,linear_acceleration=.005))
    config=dict(drive_limits=dict(linear_speed_m_s=.001,linear_acceleration_m_s2=.005),
                b2_config=dict(total_action_time_s=deadline))
    with pytest.raises(ValueError,match='25 seconds'):make_session(env,config)
'''
(ROOT/'tests/task_variants/test_deadline25_preflight.py').write_text(text,encoding='utf-8')
