"""Only the four pinned archived warmups may retain historical provenance."""
from copy import deepcopy
from pathlib import Path
import gzip, json
from bootstrap import sha, read

OUT = Path(__file__).resolve().parent

def original_spec_digest(spec):
    import hashlib
    original = read(OUT.parent / 'b2_warm_import_repair_20261009/input_spec.json')
    return hashlib.sha256(json.dumps(original, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def restoration_binding_pin(spec):
    return sha(OUT.parent / 'b2_warm_import_repair_20261009/source_binding.json')

def require_new_binding(binding, spec):
    if (set(binding) != {'mode', 'purpose', 'qualification_sha256', 'config_sha256'} or
        binding['mode'] != 'F50' or binding['purpose'] != 'bounded_physical_pilot' or
        binding['config_sha256'] != spec['legacy_config_sha256'] or
        binding['qualification_sha256'] == spec['source_grant_sha256']):
        raise ValueError('A distinct current continuation admission is required')
    import re
    if not re.fullmatch('[0-9a-f]{64}', binding['qualification_sha256']): raise ValueError('Invalid admission digest')

def archive_binding(raw, binding, spec=None, archive_sha256=None):
    spec = read(OUT / 'input_spec.json') if spec is None else spec
    require_new_binding(binding, spec)
    index = raw.get('case_index')
    if type(index) is not int or not 0 <= index < 4: raise ValueError('Invalid inherited case')
    if raw.get('stage') == 'warmup':
        source = spec['warmup'][index]
        if raw.get('episode_id') != source['id'] or archive_sha256 != source['archive_sha256']:
            raise ValueError('Only byte-pinned historical warm archives are admissible')
        return dict(binding, qualification_sha256=spec['source_grant_sha256'])
    if raw.get('stage') != 'online' or raw.get('episode_id') != 'online_F50_J0' + str(index + 1):
        raise ValueError('Only new registered online archives are publishable')
    return dict(binding)

def migrate_warm_state(envelope, binding, spec=None):
    spec = read(OUT / 'input_spec.json') if spec is None else spec
    require_new_binding(binding, spec)
    expected = dict(input_spec_sha256=original_spec_digest(spec), binding_sha256=restoration_binding_pin(spec),
                    source_grant_sha256=spec['source_grant_sha256'], source_zero_sha256=spec['zero_state_sha256'],
                    boundary=spec['source_boundary'], old_run_remains_closed=True)
    if (envelope.get('version') != 'b2_archived_warm_checkpoint_v1' or envelope.get('training_admitted') is not False or
        envelope.get('provenance') != expected): raise ValueError('Wrong restored warm envelope provenance')
    state = envelope['state']
    if (state.get('version') != 'v4_pilot_checkpoint_v1' or state.get('binding') != dict(binding, qualification_sha256=spec['source_grant_sha256']) or
        state.get('history') != [] or state.get('update_attempts') != 0 or state.get('journal') != '' or state.get('stop_reason') is not None or
        state['updater']['counts'] != dict(critic=0, actor=0, temperature=0, target=0) or
        state['replay']['size'] != 19300 or state['warm']['draws'] != 388 or
        set(state['archives']) != {x['id'] for x in spec['warmup']} or
        [(r['episode_id'], r['stage'], r['case_index']) for r in state['attempts']] != [(x['id'], 'warmup', i) for i, x in enumerate(spec['warmup'])]):
        raise ValueError('Not the exact healthy zero-update four-warmup boundary')
    migrated = deepcopy(state)
    migrated['binding'] = deepcopy(binding)
    return migrated

def remaining_schedule():
    from joint_contract import schedule
    return schedule()

def baseline_rows():
    from joint_contract import SEED, validate_raw_identity
    spec = read(OUT / 'input_spec.json'); result = []
    for i, source in enumerate(spec['baseline']):
        if sha(source['archive']) != source['archive_sha256']: raise ValueError('Inherited baseline bytes changed')
        raw = json.loads(gzip.decompress(Path(source['archive']).read_bytes()))
        validate_raw_identity(raw)
        if (raw['episode_id'] != source['id'] or raw['stage'] != 'zero' or raw['case_index'] != i or raw['mode'] != 'F50' or
            raw['seed'] != SEED or raw['qualification_sha256'] != spec['source_grant_sha256'] or
            raw['config_sha256'] != spec['legacy_config_sha256'] or raw['policy_sha256'] != spec['actor_sha256'] or
            raw['optimizer_steps'] != 0 or raw['optimizer_steps_start'] != 0): raise ValueError('Inherited baseline identity differs')
        out = raw['outcome']
        result.append(dict(case_id=raw['case_id'], simulation_valid=out['simulation_valid'], physical_stopped=out['physical_stopped'],
                           task_outcome=out['task_outcome'], task_time_s=raw['task_end_time_s'], guard=any(out['guard_violations'].values()), peaks=raw['peaks']))
    return result
