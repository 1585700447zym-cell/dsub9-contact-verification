"""Read archived bytes/JSON only; never import learning or simulation code."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / 'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
REVIEW = ROOT / 'deliverables/learning_chain/b2_force_mechanism_review_20260929'

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def verify(base, entries):
    for relative, expected in entries.items():
        assert digest(base / relative) == expected, relative
    return len(entries)

sealed = read(OLD / 'sealed_files.json')
sealed_count = verify(ROOT, sealed)
review_count = verify(REVIEW, read(REVIEW / 'verification.json')['artifacts_sha256'])
stop = read(OLD / 'stop_assessment.json')
assert (stop['new_dynamic_starts'], stop['completed_formal_batches'], stop['returncode']) == (13, 2500, 20)
assert (stop['unused_dynamic_starts'], stop['unused_formal_batches']) == (19, 2000)
assert stop['reason'] == 'three_total_force_failures'
assert all(row['simulation_valid'] and row['physical_stopped'] for row in stop['physical_audits'])
assert not any(stop[k] for k in ('native_crash', 'write_failure', 'entry_rejection', 'b2_complete'))
archive_count = verify(ROOT, stop['archives_sha256'])
probe = read(REVIEW / 'critic_probe/results.json')
assert (probe['states'], probe['state_action_pairs']) == (1747, 20968)
assert (probe['physics'], probe['actor_forwards'], probe['optimizer_updates']) == (0, 0, 0)
assert len(probe['checkpoints']) == 4
last = probe['checkpoints'][-1]
boundary = next(r for r in last['scores'] if r['episode'] == 'train_08' and r['boundary'])
assert last['checkpoint']['updates'] == 2500 and not boundary['in_checkpoint_replay']
checkpoint_count = 0
for result in probe['checkpoints']:
    assert result['complete_state_unchanged'] and result['process_rng_unchanged']
    path = OLD / 'run' / result['checkpoint']['path']
    assert digest(path / 'manifest.json') == result['checkpoint']['sha256']
    assert digest(path / 'state.pt') == read(path / 'manifest.json')['state_sha256'] == result['state_file_sha256']
    checkpoint_count += 1
mechanism = read(REVIEW / 'assessment.json')
failures = [r for r in mechanism['episodes'] if r['id'] in ('train_04', 'train_06', 'train_08')]
assert [r['boundary_draws'] for r in failures] == [5116, 2134, 0]
automation_path = Path('C:/Users/ok everything/.codex/automations/b-2/automation.toml')
automation = automation_path.read_text(encoding='utf-8')
assert 'status = "PAUSED"' in automation
protected = {p.relative_to(ROOT).as_posix(): digest(p)
             for folder in ('tools', 'tests', 'docs/stage_b')
             for p in (ROOT / folder).rglob('*')
             if p.is_file() and '__pycache__' not in p.parts}
before_file = HERE / 'protected_before.json'
if before_file.exists():
    assert read(before_file) == protected, 'Source, test or frozen contract changed during design'
else:
    before_file.write_text(json.dumps(protected, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
assert branch == 'feature/dsub9-dynamic-actuator-v1'
result = dict(status='archive_recheck_passed', worktree=str(ROOT), branch=branch,
    sealed_files_verified=sealed_count, review_artifacts_verified=review_count,
    physical_archives_verified=archive_count, checkpoint_files_verified=checkpoint_count,
    protected_source_test_contract_files=len(protected),
    stop=dict(dynamic=13, batches=2500, unused_dynamic=19, unused_batches=2000, code=20),
    prior_probe=dict(states=1747, state_action_pairs=20968,
        dangerous_min_q=boundary['scores']['recorded']['min_q'],
        exact_tail_label=boundary['exact_tail_label'],
        gap=boundary['scores']['recorded']['min_q']-boundary['exact_tail_label'],
        in_checkpoint_replay=boundary['in_checkpoint_replay']),
    failure_boundary_draws=[r['boundary_draws'] for r in failures],
    automation_status='PAUSED', automation_sha256=digest(automation_path),
    current_work=dict(physics=0, actor_forwards=0, critic_forwards=0, optimizer_updates=0,
                      training_launched=False, qualification_issued=False),
    limitation='Archived results and byte hashes rechecked; no new model/physics computation or software test execution.')
plan = HERE / 'README.md'
if plan.exists():
    links = re.findall(r'\]\(([^)]+)\)', plan.read_text(encoding='utf-8'))
    for target in links:
        assert (HERE / target).resolve().exists(), target
    rolling = [ROOT / '项目进度跟踪.md', ROOT / '项目交付总览.md',
               ROOT / 'deliverables/monthly_progress/2026-09/月报素材_2026-09.md']
    for document in rolling:
        content = document.read_text(encoding='utf-8')
        assert 'b2_actor_lr_design_20260929/README.md' in content
        assert 'b2_actor_lr_design_20260929/evidence_recheck.json' in content
    result['document_checks'] = dict(plan_links_existing=len(links), rolling_originals_linked=3,
                                     plan_sha256=digest(plan))
assert not any(n.split('.')[0] in ('torch', 'mujoco', 'stable_baselines3') for n in sys.modules)
(HERE / 'evidence_recheck.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
