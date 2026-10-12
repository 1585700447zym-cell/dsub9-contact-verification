"""Read existing bytes/JSON only. Never import project, MuJoCo, NumPy or Torch."""
import ast
import gzip
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PAPER = ROOT / 'deliverables/paper_comparison'
PC06 = PAPER / 'v4_learning_requalification_20261006'
PC07 = PAPER / 'frozen_comparison_20261007'
PC14 = PAPER / 'small_boundary_numeric_execution_20261008'
DOCS = ['项目当前入口.md', '项目进度跟踪.md', '项目交付总览.md',
        '研究推进计划_当前版.md', 'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def audit():
    cfg = read(PC06 / 'configuration.json')
    old = read(PC14 / 'prior_source_bindings.json')
    pins = dict(old['seal_pins'])
    pins.update(
        small_boundary_numeric_gate_20261007='51eef860885bcea78c4324149060014d8faac5ce1d8e760c0abc4a9ea68eb6e9',
        small_boundary_numeric_execution_20261008='810c95ad9eb1c393a603c7e13549d1325ac0d45914d82798e6d85e8d3f4c8312')
    seals = {}
    for folder, pin in pins.items():
        base = PAPER / folder
        assert sha(base / 'delivery_manifest.json') == pin, folder
        members = read(base / 'delivery_manifest.json')['files']
        for name, item in members.items():
            assert sha(base / name) == item['sha256'], (folder, name)
            assert (base / name).stat().st_size == item['bytes'], (folder, name)
        seals[folder] = dict(manifest_sha256=pin, verified_members=len(members))
    for name, pin in old['production_inputs'].items():
        assert sha(ROOT / name) == pin, name
    assert len(old['production_inputs']) == 1057
    common = cfg['common']
    assert cfg['common_key'] == old['common_key']
    assert math.isclose(math.degrees(common['guard_config']['initial_roll_pitch_limit_rad']), .5)
    assert common['initial_pose']['roll_rad'] == common['initial_pose']['pitch_rad'] == 0
    assert sha(PC06 / 'model.xml') == common['canonical_model_sha256']
    pose_rows = []
    for folder in ['v4_learning_requalification_20261006', 'frozen_comparison_20261007',
                   'contact_gate_probe_20261007']:
        base = PAPER / folder
        ledger = read(base / 'run/ledger.json')
        for entry in ledger['episodes']:
            path = base / 'run' / (entry['id'] + '.json.gz')
            assert sha(path) == entry['archive_sha256'], str(path)
            raw = json.loads(gzip.decompress(path.read_bytes()))
            case = raw['simulation_case']
            assert raw['comparison_key'] == cfg['common_key']
            assert case['roll_rad'] == case['pitch_rad'] == 0
            pose_rows.append(dict(package=folder, episode_id=entry['id'],
                                 archive_sha256=entry['archive_sha256'], simulation_case=case))
    assert len(pose_rows) == 63
    source = ROOT / 'tools/validation/run_v4_learning_pilot.py'
    constructors = [n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                    if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                    and n.func.id == 'ContactCase']
    assert len(constructors) == 1
    call = constructors[0]
    assert all(isinstance(call.args[i], ast.Constant) and call.args[i].value == 0 for i in (3, 4))
    result = read(PC07 / 'assessment.json')
    rows = result['records']['development']
    b2 = {r['case_id']: r['task_end_time_s'] for r in rows['B2']}
    s = {r['case_id']: r['task_end_time_s'] for r in rows['S2000']}
    savings = {k: b2[k] - s[k] for k in b2}
    b2cost = [r['wall_seconds'] for r in result['costs'] if r['provider'] == 'B2']
    assert len(b2cost) == 9
    pc09 = read(PAPER / 'contact_gate_probe_20261007/assessment.json')
    assert pc09['new_attempts'] == pc09['finished'] == 8 and pc09['cumulative_dynamic'] == 208
    assert read(PC14 / 'authorization_closure.json')['status'] == 'CLOSED_EXHAUSTED'
    q = read(PC14 / 'numeric_qualification.json')
    assert q['numeric_verified'] and not q['training_admitted'] and not q['dynamic_authorized']
    git = lambda *args: subprocess.check_output(['git', *args], cwd=ROOT, text=True, encoding='utf-8').strip()
    return dict(
        version='b2_scope_existing_evidence_v1', user_date='2026-10-08', timezone='Asia/Shanghai',
        branch=git('branch', '--show-current'), head=git('rev-parse', 'HEAD'),
        parent_common_key=cfg['common_key'], common_config_sha256=sha(PC06 / 'configuration.json'),
        model_sha256=common['canonical_model_sha256'], guard_config=common['guard_config'],
        inherited_scope=common['initial_pose'], sealed_packages=seals,
        sealed_members_verified=sum(x['verified_members'] for x in seals.values()),
        production_inputs_verified=1057, raw_pose_records=pose_rows,
        raw_records_verified=63, nonzero_initial_tilt_records=0,
        raw_scope_note='PC06/07/09 new attempts only; no duplicate inherited evaluations or partial archives; not entire historical corpus',
        pilot_hardcoded_zero_pose=dict(path=source.relative_to(ROOT).as_posix(), line=call.lineno, sha256=sha(source)),
        position_metrics=result['metrics'],
        development_s_time_savings=savings,
        negative_y_share_of_development_s_savings=savings['y_neg_150'] / sum(savings.values()),
        budget_reference=dict(source='PC07/assessment.json costs: provider B2', samples=9,
            mean_wall_s=sum(b2cost) / 9, minimum_wall_s=min(b2cost), maximum_wall_s=max(b2cost),
            sixteen_episode_mean_extrapolation_h=(sum(b2cost) / 9) * 16 / 3600,
            limitation='zero initial tilt historical costs; not measured pose cost or performance samples'),
        actual_new=dict(physical_episodes=0, physics_substeps=0, engine_loads=0,
            static_initializations=0, network_forwards=0, tensor_reads=0, optimizer_updates=0, replay_publications=0),
        cumulative_dynamic=208, automatic_tracking='PAUSED', training_admitted=False,
        dynamic_authorized=False, pc14_authorization_closed=True)


if __name__ == '__main__':
    result = audit()
    if '--write' in sys.argv:
        with (OUT / 'existing_evidence.json').open('x', encoding='utf-8', newline='\n') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write('\n')
        for name in DOCS:
            target = OUT / 'before_documents' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as f:
                f.write((ROOT / name).read_bytes())
    print(json.dumps({k: result[k] for k in ['branch', 'head', 'raw_records_verified',
        'nonzero_initial_tilt_records', 'sealed_members_verified', 'production_inputs_verified',
        'pilot_hardcoded_zero_pose', 'budget_reference', 'actual_new']}, ensure_ascii=False))
