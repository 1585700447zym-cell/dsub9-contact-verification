"""Exact comparison configuration and separately pinned human authorization."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
DELIVERY=ROOT/'deliverables/learning_chain/b2_actor_lr_execution_20260930'
OLD=ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
ORIGIN=ROOT/'deliverables/learning_chain/b2_actor_lr_origin_20260930/origin_v2'
ORIGIN_PIN='d31f696ae82c7e3f992afa27bcd68ab222a4ea8dbc965f29cbd26c5f1f0cde5f'
PARENT_CONFIG_PIN='18b43f1c27e7a5c33a26ae2127efbf4a48dd5da18cf4bbb3b7fa6d0e60a2b85b'
PARENT_CANDIDATE_PIN='ab2fefe0ae4eb6850d5aae768dff7a7c952302e3893f68721fb41a4adf3de379'
CASE_NAMES=('x_pos_100','x_neg_100','y_pos_100','y_neg_100')


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))


def valid_pin(pin):
    if not isinstance(pin,str) or re.fullmatch('[0-9a-f]{64}',pin) is None:
        raise ValueError('External SHA256 pin required')
    return pin


def execution_config(branch):
    if branch not in ('A','B'):raise ValueError('Registered execution branch required')
    if digest(OLD/'config.json')!=PARENT_CONFIG_PIN:raise ValueError('Parent config changed')
    c=deepcopy(read(OLD/'config.json'));c['version']='actor_lr_comparison_execution_v1'
    c['learning'].update(actor_learning_rate=3e-4 if branch=='A' else 3e-5,max_gradient_batches=500)
    c['sampling'].update(max_attempts=0,stop_at='no_new_training_collection')
    c['execution'].update(preparation_only=False,new_training_collection=0,
        evaluate='fixed_four_development_points_once_per_branch',baseline='historical_context_only',
        authorized_dynamic_starts=4,authorized_optimizer_calls=500,
        stop_on_any_evaluation_guard=True,requires_separate_user_authorization=True)
    c['comparison']=dict(branch=branch,parent_config_sha256=PARENT_CONFIG_PIN,
        origin_manifest_sha256=ORIGIN_PIN,data_source='train_00_through_train_03_only',
        a_reproduction_required=True,condition='validation_then_exact_A_then_B',automatic_retry=False)
    return c


def validate_execution_config(config):
    if not isinstance(config,dict) or not isinstance(config.get('comparison'),dict):
        raise ValueError('Execution comparison config required')
    if canonical(config)!=canonical(execution_config(config['comparison'].get('branch'))):
        raise ValueError('Unregistered comparison execution configuration')


def compute_budget():
    return dict(formal=dict(A=500,B=500),physical=dict(A=4,B=4),synthetic=16,test_forward=128,
        diagnostic=dict(initial=256,A=256,B=256),extra_critic_diagnostic=0,new_warmup=0,
        new_training_collection=0,independent_test=0,previous_dynamic=57,new_dynamic_cap=8,
        cumulative_dynamic_cap=65,watchdog_cycles_per_start=13000,old_unused_dynamic=19,
        old_unused_batches=2000,old_unused_consumed=0,automatic_tracking=False,automatic_retry=False,
        stop_on_any_evaluation_guard=True,stop_on_a_reproduction_mismatch=True)


def validate_authorization(record,candidate_pin):
    valid_pin(candidate_pin)
    if (not isinstance(record,dict) or record.get('version')!='actor_lr_user_authorization_v1' or
        record.get('approved') is not True or record.get('candidate_sha256')!=candidate_pin or
        record.get('scope')!='validation_and_conditional_ab' or
        not isinstance(record.get('user_confirmation'),str) or not record['user_confirmation'].strip() or
        canonical(record.get('budget'))!=canonical(compute_budget())):
        raise ValueError('Explicit authorization of the exact new comparison budget required')


def verify_files(files):
    if not isinstance(files,dict) or not files:raise ValueError('Pinned input inventory required')
    for rel,pin in files.items():
        valid_pin(pin)
        path=(ROOT/rel).resolve()
        if not path.is_relative_to(ROOT.resolve()) or digest(path)!=pin:
            raise ValueError('Input bytes changed: '+rel)


def source_inventory():
    if digest(OLD/'candidate.json')!=PARENT_CANDIDATE_PIN:raise ValueError('Parent candidate changed')
    paths={p.relative_to(ROOT).as_posix() for folder in ('tools','tests','docs/stage_b')
        for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    paths.update(read(OLD/'candidate.json')['source_sha256'])
    paths.update((DELIVERY/f'config_{branch}.json').relative_to(ROOT).as_posix() for branch in ('A','B'))
    return {rel:digest(ROOT/rel) for rel in sorted(paths)}


def verify_candidate(candidate_pin,*,check_runtime=True):
    valid_pin(candidate_pin)
    path=DELIVERY/'candidate.json'
    if digest(path)!=candidate_pin:raise ValueError('Comparison candidate pin changed')
    r=read(path)
    if (r.get('version')!='actor_lr_comparison_candidate_v1' or r.get('synthetic_only') is not False or
        r.get('protocol_preparation_passed') is not True or r.get('real_validation_required') is not True or
        r.get('user_authorization_required') is not True or r.get('origin_manifest_sha256')!=ORIGIN_PIN or
        canonical(r.get('budget'))!=canonical(compute_budget())):
        raise ValueError('Comparison preparation qualification required')
    if digest(ORIGIN/'manifest.json')!=ORIGIN_PIN:raise ValueError('Common origin manifest changed')
    for branch in ('A','B'):
        validate_execution_config(r['configs'][branch])
        if canonical(r['configs'][branch])!=canonical(execution_config(branch)):
            raise ValueError('Candidate A/B key and internal branch differ')
        if canonical(read(DELIVERY/f'config_{branch}.json'))!=canonical(r['configs'][branch]):
            raise ValueError('Branch config bytes differ from candidate')
    if r['source_sha256']!=source_inventory():raise ValueError('Execution source inventory changed')
    verify_files(r['evidence_sha256'])
    if check_runtime:
        from tools.validation.verify_residual_interface import qualified_runtime
        from .runtime import active_package
        if canonical(qualified_runtime(active_package()))!=canonical(r['runtime']):
            raise ValueError('Exact comparison runtime changed')
    return deepcopy(r)


def require_authorization(candidate_pin,authorization_pin):
    valid_pin(authorization_pin)
    path=DELIVERY/'authorization.json'
    if not path.exists() or digest(path)!=authorization_pin:
        raise ValueError('Missing or changed explicit comparison authorization')
    r=read(path);validate_authorization(r,candidate_pin)
    return deepcopy(r)


def branch_binding(config,candidate_pin,authorization_pin):
    validate_execution_config(config);valid_pin(candidate_pin);valid_pin(authorization_pin)
    return dict(version='actor_lr_execution_binding_v1',branch=config['comparison']['branch'],
        candidate_sha256=candidate_pin,authorization_sha256=authorization_pin,
        config_sha256=hashlib.sha256(canonical(config).encode('utf-8')).hexdigest(),origin_manifest_sha256=ORIGIN_PIN)
