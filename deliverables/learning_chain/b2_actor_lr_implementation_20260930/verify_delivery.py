"""Final byte/record verification using the standard library only."""
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OLD = ROOT / 'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def canonical(obj):
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(',', ':'))


def write(name, obj):
    p = HERE / name
    data = (json.dumps(obj, ensure_ascii=False, allow_nan=False, indent=2) + '\n').encode('utf-8')
    if p.exists() and p.read_bytes() != data:
        raise ValueError('Final evidence already exists with different bytes: ' + name)
    if not p.exists():
        p.write_bytes(data)


branch = subprocess.check_output(['git', 'branch', '--show-current'], cwd=ROOT, text=True).strip()
assert branch == 'feature/dsub9-dynamic-actuator-v1'
assert ROOT.resolve() == Path('D:/dsub9项目计划/first_stage_sim/.worktrees/dsub9-v1-contact-validation').resolve()
before = read(HERE / 'protected_before.json')
snapshots = read(HERE / 'parent_source_snapshots.json')
changes = [rel for rel, pin in before.items() if sha(ROOT / rel) != pin]
assert changes == ['tools/learning/sac_update.py']
for rel, pin in before.items():
    assert sha(ROOT / snapshots.get(rel, rel)) == pin, rel
candidate = read(OLD / 'candidate.json')
for rel, pin in candidate['source_sha256'].items():
    assert sha(ROOT / snapshots.get(rel, rel)) == pin, rel
sealed = read(OLD / 'sealed_files.json')
for rel, pin in sealed.items():
    assert sha(ROOT / rel) == pin, rel
sources = read(HERE / 'source_sha256.json')
assert len(sources) == 283
for rel, pin in sources.items():
    assert sha(ROOT / rel) == pin, rel
actual = {p.relative_to(ROOT).as_posix() for folder in ('tools', 'tests', 'docs/stage_b')
          for p in (ROOT / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert actual == set(sources), 'Source set differs'
source_pin = sha(HERE / 'source_sha256.json')
configs = {name: read(HERE / ('config_' + name + '.json')) for name in ('A', 'B')}
for name, config in configs.items():
    binding = read(HERE / ('binding_' + name + '.json'))
    assert binding['source_manifest_sha256'] == source_pin
    assert binding['config_sha256'] == hashlib.sha256(canonical(config).encode('utf-8')).hexdigest()
    assert binding['parent_config_sha256'] == sha(OLD / 'config.json')
    assert binding['branch'] == config['comparison']['branch'] == name
    assert config['comparison']['runnable'] is False and config['execution']['preparation_only'] is True
    assert all(config['execution'][field] == 0 for field in ('authorized_dynamic_starts', 'authorized_optimizer_calls', 'authorized_model_forwards'))
    assert config['learning']['learning_rate'] == 3e-4
    assert config['learning']['actor_learning_rate'] == (3e-4 if name == 'A' else 3e-5)
    normalized = json.loads(canonical(config))
    normalized['comparison']['branch'] = 'SAME'
    normalized['learning']['actor_learning_rate'] = 'SAME'
    if name == 'A':
        reference = normalized
    else:
        assert normalized == reference, 'Unregistered A/B difference'
state_record = read(HERE / 'diagnostic_states.json')
assert len(state_record['states']) == 256
assert len({(r['episode'], r['index']) for r in state_record['states']}) == 256
for archive in state_record['archives']:
    path = ROOT / archive['path']
    assert sha(path) == archive['sha256'] == sealed[archive['path']]
    raw = json.loads(gzip.decompress(path.read_bytes()))
    assert raw['sampling_mode'] == 'uniform_warmup' and raw['optimizer_steps'] == raw['optimizer_steps_start'] == 0
    selected = [r for r in state_record['states'] if r['episode'] == raw['episode_id']]
    assert len(selected) == 64
    for row in selected:
        archived = raw['transitions'][row['index']]
        assert archived['action_active'] is True and row['observation'] == archived['observation']
rebuild = read(HERE / 'rebuild_requirements.json')
assert rebuild['pool_rows'] == 22766 and rebuild['reconstructed'] is rebuild['a_reproduced'] is False
assert sha(ROOT / rebuild['initial_checkpoint_path'] / 'state.pt') == rebuild['state_sha256']
result = read(HERE / 'final_protocol_results.json')
assert result['tests'] == 101 and result['exit_code'] == result['failures'] == result['errors'] == 0
assert not any(result['forbidden_call_counts'].values())
assert sha(HERE / 'final_protocol.xml') == result['report_sha256']
cases = list(ET.parse(HERE / 'final_protocol.xml').getroot().iter('testcase'))
assert len(cases) == 101 and all(not list(c) for c in cases)
receipt = read(HERE / 'preparation_receipt.json')
assert not any(receipt['forbidden_call_counts'].values())
assert receipt['qualification_issued'] is receipt['training_launched'] is False
assert receipt['source_manifest_sha256'] == source_pin
budget = read(HERE / 'proposed_compute.json')
assert budget['approved'] is budget['runnable'] is budget['automatic_tracking'] is False
assert budget['formal_batches'] == dict(A=500, B=500, total=1000)
assert budget['physical_starts'] == dict(A=4, B=4, total=8)
assert budget['synthetic_transaction_attempts'] == 16 and budget['extra_test_state_forwards'] == 128
assert budget['diagnostic_actor_state_forwards'] == 768 and budget['diagnostic_critic_state_forwards'] == 0
assert budget['old_unused_budget_consumed'] == 0
stopped = read(OLD / 'stop_assessment.json')
assert (stopped['new_dynamic_starts'], stopped['completed_formal_batches'], stopped['unused_dynamic_starts'], stopped['unused_formal_batches']) == (13, 2500, 19, 2000)
automation = Path('C:/Users/ok everything/.codex/automations/b-2/automation.toml')
assert 'status = "PAUSED"' in automation.read_text(encoding='utf-8')
docs = [ROOT / '项目进度跟踪.md', ROOT / '项目交付总览.md', ROOT / 'deliverables/monthly_progress/2026-09/月报素材_2026-09.md']
doc_pins = {}
for p in docs:
    assert '独立actor学习率实现与协议准备（2026-09-30）' in p.read_text(encoding='utf-8')
    relative = p.relative_to(ROOT)
    snapshot = HERE / 'document_snapshot' / relative
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if snapshot.exists():
        assert snapshot.read_bytes() == p.read_bytes()
    else:
        snapshot.write_bytes(p.read_bytes())
    doc_pins[relative.as_posix()] = sha(snapshot)
assessment = dict(status='implementation_and_protocol_preparation_accepted', date='2026-09-30',
    branch=branch, source_manifest_sha256=source_pin, tests=101, failures=0, errors=0,
    actual_forbidden_calls=result['forbidden_call_counts'], protected_original_files=len(before),
    inherited_source_files=len(candidate['source_sha256']), old_sealed_files=len(sealed),
    changed_inherited_sources=changes, current_source_files=len(sources),
    review='review.md; internal target guard and coverage findings corrected; no remaining important findings',
    full_learning_state_reconstructed=False, a_reproduced=False, real_update_validated=False,
    qualification_issued=False, training_launched=False, policy_effect_validated=False, b2_complete=False,
    old_unused_dynamic=19, old_unused_batches=2000, automatic_tracking='PAUSED',
    document_snapshots_sha256=doc_pins, next='Versioned execution integration and separately authorized real validation/A-B stage')
write('assessment.json', assessment)
# Create the verification file before checking references; its final body follows.
files = [HERE / 'README.md', *docs]
links = []
for p in files:
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)', p.read_text(encoding='utf-8')):
        target = target.strip('<>')
        if target.startswith(('http:', 'https:', '#', 'app:', 'codex:')):
            continue
        local = target.split('#', 1)[0]
        if not local:
            continue
        resolved = (p.parent / local).resolve()
        if resolved == (HERE / 'verification.json').resolve():
            links.append(str(resolved))
            continue
        assert resolved.exists(), (p, local)
        links.append(str(resolved))
evidence_pins = {p.name: sha(p) for p in HERE.iterdir() if p.is_file() and p.name != 'verification.json'}
write('verification.json', dict(status='passed', date='2026-09-30', standard_library_only=True,
    checks=dict(branch=True, protected_original_bytes=len(before), inherited_source_bytes=len(candidate['source_sha256']),
        old_sealed_bytes=len(sealed), current_sources=len(sources), prepared_configs=2, fixed_archive_states=256,
        final_protocol_tests=101, local_links=len(links), rolling_document_snapshots=3, automation_paused=True),
    evidence_sha256=evidence_pins, document_snapshots_sha256=doc_pins,
    qualification_issued=False, training_launched=False, policy_effect_validated=False, b2_complete=False))
print(json.dumps({'status': 'passed', 'tests': 101, 'old_sealed_files': len(sealed), 'local_links': len(links),
                  'source_manifest_sha256': source_pin, 'tracking': 'PAUSED'}, ensure_ascii=True))
