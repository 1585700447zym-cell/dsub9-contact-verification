"""Pin permitted one-rollout inputs after offline/review gates; no reset/step."""
import sys,json,shutil,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from tools.validation.run_actor_lr_comparison import select_qualified_runtime
select_qualified_runtime()
from tools.validation.run_v4_continuation_preflight import verify_inputs,PLAN

if (OUT/'run').exists() or (OUT/'preflight_admission.json').exists():raise RuntimeError('Bound once only')
config=verify_inputs(OUT)
assert '310 passed' in (OUT/'tests_final.txt').read_text(encoding='utf8')
offline=json.loads((OUT/'offline_check.json').read_text(encoding='utf8'))
assert offline['search_zero_rows']==16563 and offline['max_zero_command_error']==0 and offline['new_next_reference_failures']==0
assert 'Critical0 / Important0 / Minor2' in (OUT/'review.md').read_text(encoding='utf8')
for name,digest in config['input_sha256'].items():
    if name.endswith('.py') or name==PLAN:
        target=OUT/'source_snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,target)
        assert hashlib.sha256(target.read_bytes()).hexdigest()==digest
record=dict(allowed_scope='one_continuation_boundary_development_episode_only',max_new_episodes=1,
    prior_cumulative=139,cumulative_limit=140,training_admitted=False,formal_updates=0,policy_calls=0,replay_published=0,
    tests_passed=310,review_critical=0,review_important=0,review_minor_deferred=2,
    configuration_sha256=hashlib.sha256((OUT/'configuration.json').read_bytes()).hexdigest())
(OUT/'preflight_admission.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
with (OUT/'progress.md').open('a',encoding='utf8') as f:
    f.write('\nTask 2: complete — 310相关检查，独立审查0 Critical/0 Important/2暂缓Minor；输入与源码快照绑定，静态模型编译无reset/step。仅1动态获准，训练未准入。\n')
print(json.dumps(record))
