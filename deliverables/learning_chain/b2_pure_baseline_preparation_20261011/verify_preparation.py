"""Final stdlib verification and rolling-document snapshot; no physics execution."""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
import contract as c
ROOT = c.ROOT
before = c.read(OUT / 'before_state.json')
checks = {}
branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT).decode().strip()
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
checks['same_branch_and_head'] = branch == before['branch'] and head == before['head']
prior = {item for item in (OUT / 'git_status_before.bin').read_bytes().split(b'\0') if item}
current_raw = subprocess.check_output(['git', 'status', '--porcelain=v1', '-z'], cwd=ROOT)
current = {item for item in current_raw.split(b'\0') if item}
checks['all_prior_dirty_entries_retained'] = prior <= current
checks['all_200_common_tool_sources_unchanged'] = len(before['runtime_sources']) == 200 and all(
    c.sha(ROOT / p) == pin for p, pin in before['runtime_sources'].items())
checks['AGENTS_unchanged'] = c.sha(ROOT / 'AGENTS.md') == before['documents']['AGENTS.md']
checks['six_before_snapshots_unchanged'] = len(before['documents']) == 6 and all(
    c.sha(OUT / 'before_documents' / p) == pin for p, pin in before['documents'].items())
binding, config = c.verify_binding()
checks['all_bound_inputs_and_runtime_verified'] = True
checks['source_binding_count_correct'] = len(binding['files']) == 2254
request = c.read(OUT / 'authorization_request.json')
qualification = c.read(OUT / 'qualification_candidate.json')
candidate = c.read(OUT / 'candidate.json')
checks['unapproved_candidate_and_grant_preserved'] = (
    request['status'] == 'DRAFT' and request['explicit_user_authorized'] is False and
    request['binding_sha256'] == c.sha(OUT / 'source_binding.json') and
    candidate['scientific_execution_admitted'] is False and candidate['training_admitted'] is False and
    qualification['physical_execution_verified'] is False and qualification['training_admitted'] is False and
    qualification['scientific_execution_admitted'] is False)
checks['no_execution_and_closed_old_budget'] = (
    not (OUT / 'execution').exists() and request['old_budget_closed'] is True and
    request['retries'] == 0 and request['limits']['dynamic_episodes'] == 4 and
    request['limits']['formal_updates'] == 0)
reuse = c.read(OUT / 'reuse_assessment.json')
checks['eight_development_archives_labels_preserved'] = (
    reuse['verified'] is True and len(reuse['rows']) == 8 and all(
    row['historical_model_scope_qualified'] is False and row['historical_training_admitted'] is False and
    row['reused_as'] == 'development_comparison_only' for row in reuse['rows']))
checklog = (OUT / 'source_check_no_science.log').read_text('utf-8-sig')
testlog = (OUT / 'tests_final.log').read_text('utf-8-sig')
checks['fresh_27_tests_passed'] = 'Ran 27 tests' in testlog and testlog.strip().endswith('OK')
checks['fresh_check_without_scientific_imports'] = (
    '"source_binding_verified": true' in checklog and
    'loaded_scientific_packages= [] execution_folder_exists= False' in checklog)
checks['review_repairs_confirmed'] = 'all three original findings are resolved' in (
    OUT / 'review.md').read_text('utf8')
after = {}
for name in before['documents']:
    src = ROOT / name; dst = OUT / 'after_documents' / name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst); after[name] = c.sha(dst)
checks['six_after_snapshots_match'] = len(after) == 6 and all(
    c.sha(ROOT / p) == pin for p, pin in after.items())
rolling = [p for p in before['documents'] if p != 'AGENTS.md']
blocks = []
for name in rolling:
    s = (ROOT / name).read_text('utf8')
    assert s.count('<!-- b2-scope-current -->') == 1 and s.count('<!-- /b2-scope-current -->') == 1, name
    block = s.split('<!-- b2-scope-current -->')[1].split('<!-- /b2-scope-current -->')[0]
    blocks.append(re.sub(r'\[准备结果与执行边界\]\([^)]*\)', 'LINK', block))
    assert all(x in block for x in ['27项标准库测试通过', '8/8', '累计动态254', 'PAUSED', 'DRAFT', '准备进入C之前']), name
checks['five_current_blocks_consistent'] = len(set(blocks)) == 1
monthly = (ROOT / 'deliverables/monthly_progress/2026-10/月报素材_2026-10.md').read_text('utf8')
checks['monthly_five_sections_integrated'] = all('纯B2' in monthly[
    monthly.index(h):monthly.find('\n## ', monthly.index(h) + 4)] for h in [
    '## 一、本月综合摘要', '## 二、关键数字与证据', '## 三、负结果与限制', '## 四、图表与讲稿', '## 五、下一项'])
missing = []
for path in [OUT / '结果说明.md', *(ROOT / p for p in rolling)]:
    for target in re.findall(r'\]\(([^)]+)\)', path.read_text('utf8')):
        target = target.strip().split('#', 1)[0]
        if not target or '://' in target or target.startswith('mailto:'): continue
        if path.parent != OUT and 'b2_pure_baseline_preparation_20261011' not in target: continue
        resolved = path.parent / target
        if resolved.resolve() == (OUT / 'verification.json').resolve(): continue  # Written immediately below.
        if not resolved.is_file(): missing.append((str(path), target))
checks['new_delivery_relative_links_resolve'] = not missing
assert all(checks.values()), json.dumps({k: v for k, v in checks.items() if not v}, ensure_ascii=False) + str(missing)
verification = dict(version='pure_b2_preparation_verification_v1', verified_at=c.now(), status='PASS',
    checks=checks, branch=branch, head=head, prior_dirty_entries=before['dirty_entries'],
    current_dirty_entries=len(current), common_tool_sources_unchanged=200, reused_archives=8,
    stdlib_tests=27, bound_input_files=len(binding['files']), binding_sha256=c.sha(OUT / 'source_binding.json'),
    after_documents=after, before_documents=before['documents'],
    logs={name: c.sha(OUT / name) for name in ['tests_final.log', 'source_check_no_science.log', 'prepare.log',
          'tests_review_red.log', 'tests_review_green.log', 'review.md']},
    new_physics=0, new_physical_model_loads=0, new_policy_calls=0, new_updates=0,
    new_tensor_loads=0, new_replay_publications=0, cumulative_dynamic=254, independent_tests=0,
    automatic_tracking='PAUSED', full_B2_accepted=False, C_accepted=False, physical_execution_verified=False,
    scientific_execution_admitted=False, training_admitted=False,
    limit='Preparation and stdlib verification only; actual Windows owned worker and four physical results remain unexecuted.')
c.write(OUT / 'verification.json', verification)
print(json.dumps(dict(status='PASS', checks=len(checks), tests=27, reused_archives=8,
    bound_input_files=len(binding['files']), prior_dirty_entries=before['dirty_entries'],
    current_dirty_entries=len(current), snapshots_after=len(after), new_physics=0)))
