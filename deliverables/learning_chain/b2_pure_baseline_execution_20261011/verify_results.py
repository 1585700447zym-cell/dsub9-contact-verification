"""Independent stdlib recalculation, source preservation, document snapshots and seal."""
import gzip
import importlib.abc
import json
import math
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PREP = ROOT / 'deliverables/learning_chain/b2_pure_baseline_preparation_20261011'


class NoScience(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('numpy', 'mujoco', 'torch', 'stable_baselines3'):
            raise AssertionError('Final archive verification cannot run science')


sys.meta_path.insert(0, NoScience()); sys.path.insert(0, str(PREP))
import contract as c
if (OUT / 'delivery_manifest.json').exists(): raise FileExistsError('Preserve the first sealed verification')
before = c.read(OUT / 'before_state.json'); d = c.read(OUT / 'assessment.json')
g = c.read(OUT / 'geometry_assessment.json'); ledger = c.read(OUT / 'run/ledger.json')
registration = c.read(OUT / 'registration.json'); closure = c.read(OUT / 'authorization_closure.json')
binding, config = c.verify_binding()
checks = {}


def check(name, value):
    assert value, name
    checks[name] = True


def close(a, b, tol=1e-9):
    return math.isfinite(a) and math.isfinite(b) and abs(a - b) <= tol


check('source_binding_and_registration_unchanged', c.sha(PREP / 'source_binding.json') == before['source_binding_sha256'] == registration['source_binding_sha256'])
check('all_2254_inputs_verified', len(binding['files']) == 2254)
check('same_branch_head', subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT).decode().strip() == before['branch'] and
      subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip() == before['head'])
check('200_common_tool_sources_unchanged', len(before['runtime_sources']) == 200 and all(c.sha(ROOT / p) == pin for p, pin in before['runtime_sources'].items()))
check('AGENTS_unchanged', c.sha(ROOT / 'AGENTS.md') == before['documents']['AGENTS.md'])
prior = {x for x in (OUT / 'git_status_before.bin').read_bytes().split(b'\0') if x}
current = {x for x in subprocess.check_output(['git', 'status', '--porcelain=v1', '-z'], cwd=ROOT).split(b'\0') if x}
check('all_prior_dirty_entries_retained', prior <= current)
check('new_grant_pinned_and_closed', c.sha(OUT / 'grant.json') == registration['grant_sha256'] == closure['grant_sha256'] == ledger['grant_sha256'] and
      closure['status'] == ledger['status'] == d['status'] == 'CLOSED_COMPLETE' and closure['claimed_attempts'] == 4 and closure['unused_closed'] == 0 and closure['no_retry'] is True)
source_run = {str(p.relative_to(PREP / 'execution')): c.sha(p) for p in (PREP / 'execution').rglob('*') if p.is_file()}
copy_run = {str(p.relative_to(OUT / 'run')): c.sha(p) for p in (OUT / 'run').rglob('*') if p.is_file()}
check('complete_run_copy_matches_original', source_run == copy_run)
check('four_worker_trees_exited', len(ledger['episodes']) == 4 and all(e['status'] == 'finished' and e['healthy'] is True and
      e['supervisor']['go_issued'] is True and e['supervisor']['process_exit_confirmed'] is True and
      e['supervisor']['owned_launcher_exit_confirmed'] is True and e['supervisor']['returncode'] == 0 and e['supervisor']['deadline_hit'] is False for e in ledger['episodes']))
check('three_exact_four_case_sets', len(d['records']) == 12 and all({r['case_id'] for r in d['records'] if r['role'] == role} == {'J01', 'J02', 'J03', 'J04'} for role in ('pure_B2', 'F0', 'F2000')))
times = {}; new_cycles = 0; new_steps = 0
for r in d['records']:
    path = Path(r['archive_path']); check('archive_hash_' + r['role'] + r['case_id'], c.sha(path) == r['sha256'])
    raw = json.loads(gzip.decompress(path.read_bytes()))
    point = next(p for p in config['cases'] if p['id'] == r['case_id'])
    c.check_pose(point, raw['trace'][0])
    assert raw['comparison_key'] == config['common_key'] and raw['case'] == point
    assert raw['outcome']['task_outcome'] == 'FULL_SUCCESS' and raw['outcome']['simulation_valid'] is True and raw['outcome']['physical_stopped'] is True and not any(raw['outcome']['guard_violations'].values())
    assert close(raw['task_end_time_s'], r['task_time_s']) and close(r['penalized_time_s'], r['task_time_s'])
    times.setdefault(r['role'], []).append(raw['task_end_time_s'])
    xyz = raw['trace'][-1]['position_m']; q = raw['trace'][-1]['quaternion_wxyz']; norm = math.sqrt(sum(v*v for v in q))
    xy = math.sqrt(xyz[0]**2 + xyz[1]**2) * 1e6
    angle = math.degrees(2 * math.atan2(math.sqrt(sum(v*v for v in q[1:])) / norm, abs(q[0]) / norm))
    assert close(xy, r['final_xy_um']) and close(angle, r['final_angle_deg'], 1e-7)
    assert r['additional_precision'] == r['functional_plus_precision'] == (xy <= 80. and angle <= .5)
    schema = {f['name']: f for f in raw['observation_schema']}; phase_s = {}
    for i, t in enumerate(raw['transitions']):
        start = raw['trace'][i]['time_s']; end = raw['trace'][i+1]['time_s']; assert close(end-start, t['dt'], 2e-12)
        pf = schema['policy_phase']; ph = schema['physical_phase']; ob = t['observation']
        po = ob[pf['start']:pf['start']+pf['width']]; phy = ob[ph['start']:ph['start']+ph['width']]
        assert sum(po) == sum(phy) == 1. and all(x in (0., 1.) for x in po + phy)
        label = ('INSERT', 'UNLOAD', 'SEARCH', 'WAIT_RECOVERY', 'FAILED')[po.index(1.)] if phy[0] else ('RUNNING', 'STOPPING', 'RETRACT', 'TERMINAL')[phy.index(1.)]
        dt = max(0., min(end, raw['task_end_time_s']) - start)
        if dt > 0: phase_s[label] = phase_s.get(label, 0.) + dt
    assert set(phase_s) == set(r['phase_times_s']) and all(close(v, r['phase_times_s'][k]) for k, v in phase_s.items())
    assert close(sum(phase_s.values()), raw['task_end_time_s'])
    if r['role'] == 'pure_B2':
        assert raw['policy_calls'] == raw['optimizer_steps'] == 0 and raw['policy_sha256'] is None
        assert raw['physical_substeps'] == 10 * raw['control_cycles']
        assert len(raw['actions']) == len(raw['transitions']) == raw['control_cycles']
        for a in raw['actions']:
            for field, width in [('raw_action', 4), ('experience_action', 4), ('requested_residual', 6), ('applied_residual', 6), ('effective_command_delta', 6)]:
                assert len(a[field]) == width and all(v == 0. and math.isfinite(v) for v in a[field])
        new_cycles += raw['control_cycles']; new_steps += raw['physical_substeps']
    geom = next(x for x in g['rows'] if x['role'] == r['role'] and x['case_id'] == r['case_id'])
    assert geom['archive_sha256'] == r['sha256'] and math.isfinite(geom['audit_end_clearance_um'])
    assert geom['audit_end_geometry_fit'] == (geom['audit_end_clearance_um'] >= -.001)
check('saved_pose_precision_phase_and_zero_residual_checks', True)
for role, values in times.items():
    s = d['summaries'][role]
    assert close(statistics.mean(values), s['mean_penalized_time_s']) and close(statistics.mean(values), s['success_conditioned_mean_s'])
    for q, value in zip(('0.25', '0.5', '0.75'), statistics.quantiles(values, n=4, method='inclusive')):
        assert close(value, s['success_time_quantiles_s'][q])
    assert s['functional_successes'] == s['valid_stopped'] == 4 and s['guard_failures'] == 0
check('means_quantiles_counts_recalculated', True)
check('actual_costs_within_grant', new_cycles == d['costs']['control_cycles'] == 21324 and new_steps == d['costs']['native_steps'] == 213240 and
      new_cycles <= registration['limits']['control_cycles'] and new_steps <= registration['limits']['native_steps'] and
      all(e['control_cycles'] <= 14500 and e['physical_substeps'] <= 145000 and e['supervisor']['wall_seconds'] <= 1200 for e in ledger['episodes']) and
      d['costs']['package_wall_s'] <= 7200 and all(d['costs'][k] == 0 for k in ('policy_calls', 'learner_constructions', 'tensor_loads', 'formal_updates', 'replay_publications')))
check('relative_improvement_and_old_gate_preserved', close(d['relative_time_improvement_over_pure_B2']['F2000'], 1 - statistics.mean(times['F2000']) / statistics.mean(times['pure_B2'])) and
      close(d['original_F2000_over_F0_improvement'], 1 - statistics.mean(times['F2000']) / statistics.mean(times['F0'])) and d['original_10percent_gate_passed'] is False)
check('geometry_function_and_metadata_pinned', g['source_binding_sha256'] == registration['source_binding_sha256'] and g['referee'] == config['common']['geometry_referee'] and g['code_sha256'] == c.sha(OUT / 'geometry_assessment.py') and
      len(g['rows']) == 12 and all(g[k] == 0 for k in ('new_physical_models', 'new_physical_steps', 'new_policy_calls', 'new_tensor_loads', 'new_training_updates')))
check('limited_acceptance_labels_and_cumulative', d['cumulative_dynamic'] == 258 and d['new_independent_tests'] == 0 and d['full_B2_accepted'] is False and d['C_accepted'] is False and d['training_admitted'] is False and d['automatic_tracking'] == 'PAUSED')
after = {}
for name, pin in before['documents'].items():
    assert c.sha(OUT / 'before_documents' / name) == pin
    dst = OUT / 'after_documents' / name; dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / name, dst); after[name] = c.sha(dst)
check('six_before_after_document_snapshots', len(after) == 6 and all(c.sha(ROOT / name) == pin for name, pin in after.items()))
rolling = [name for name in before['documents'] if name != 'AGENTS.md']; blocks = []
for name in rolling:
    text = (ROOT / name).read_text('utf8'); assert text.count('<!-- b2-scope-current -->') == text.count('<!-- /b2-scope-current -->') == 1
    block = text.split('<!-- b2-scope-current -->')[1].split('<!-- /b2-scope-current -->')[0]
    assert all(x in block for x in ('8.9020/8.9060/8.6595', '累计动态258', '21个新增组合', 'PAUSED', '完整B.2/C未验收', '准备进入C之前'))
    blocks.append(re.sub(r'\[结果与路线\]\([^)]*\)', 'LINK', block))
check('five_current_documents_consistent', len(set(blocks)) == 1)
monthly = (ROOT / 'deliverables/monthly_progress/2026-10/月报素材_2026-10.md').read_text('utf8')
check('monthly_five_sections_integrated', all('四点' in monthly[monthly.index(h):monthly.find('\n## ', monthly.index(h)+4)] for h in
      ('## 一、本月综合摘要', '## 二、关键数字与证据', '## 三、负结果与限制', '## 四、图表与讲稿', '## 五、下一项')))
missing = []
for path in [OUT / '结果说明.md', *(ROOT / name for name in rolling)]:
    for target in re.findall(r'\]\(([^)]+)\)', path.read_text('utf8')):
        target = target.strip().split('#', 1)[0]
        if not target or '://' in target or target.startswith('mailto:'): continue
        if path.parent != OUT and 'b2_pure_baseline_execution_20261011' not in target: continue
        resolved = (path.parent / target).resolve()
        if resolved == (OUT / 'verification.json').resolve(): continue
        if not resolved.is_file(): missing.append((str(path), target))
check('new_delivery_links_resolve', not missing)
check('independent_review_clean', 'Clean，无未解决' in (OUT / 'review.md').read_text('utf8'))
c.write(OUT / 'qualification.json', dict(scope='four_registered_joint_development_cases_zero_residual', pure_B2_evaluation_verified=True,
    matched_comparison_complete=True, scientific_execution_admitted=False, training_admitted=False,
    full_B2_accepted=False, C_accepted=False, cumulative_dynamic=258, independent_tests=0,
    automatic_tracking='PAUSED', all_current_budget_closed=True, source_binding_sha256=registration['source_binding_sha256']))
c.write(OUT / 'verification.json', dict(status='PASS', verified_at=c.now(), checks=checks, stdlib_only=True,
    archives_checked=12, new_physical_episodes=4, reused_evaluations=8, new_policy_calls=0, new_updates=0,
    cycles=new_cycles, native_steps=new_steps, cumulative_dynamic=258, source_input_count=len(binding['files']),
    common_tool_sources_unchanged=200, prior_dirty_entries=before['dirty_entries'], current_dirty_entries=len(current),
    before_documents=before['documents'], after_documents=after,
    independent_review_geometry_limit='Reviewer did not reexecute NumPy geometry; frozen function/source/metadata and saved-pose result identity checked.',
    failure_test_limit='No new physical failure or injected fault trial; observed four episodes all succeeded.'))
progress = OUT / 'progress.md'
progress.write_text(progress.read_text('utf8') + '\nTask 4: complete — final independent stdlib verification PASS; all prior dirty entries retained, 200 tool sources and 2254 input bindings unchanged, six before/after snapshots and new links checked. Budget closed, cumulative258, no new admission. Preparation/entry archives unchanged; no commits/worktree changes. Delivery sealed and stop/report under AGENTS.md.\n', encoding='utf8')
manifest = {str(p.relative_to(OUT)): c.sha(p) for p in OUT.rglob('*') if p.is_file() and p.name not in ('delivery_manifest.json', 'verification.log')}
c.write(OUT / 'delivery_manifest.json', dict(version='pure_b2_delivery_manifest_v1', sealed_at=c.now(), files=manifest,
    source_binding_sha256=registration['source_binding_sha256'], stage='B.2 item 3', independent_tests=0, full_B2_accepted=False, C_accepted=False))
print(json.dumps(dict(status='PASS', checks=len(checks), archives=12, cycles=new_cycles, native_steps=new_steps,
    cumulative=258, retained_dirty_entries=before['dirty_entries'], snapshots=6, sealed_files=len(manifest))))
