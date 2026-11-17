"""Bounded fresh-GRU qualification from frozen mesh-contact repair evidence.

Only hashes and JSON are read. No simulator, policy or optimizer is initialized.
The caller still binds the new registration, job digest, budget and fresh state.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from tools.learning.recovery_learning_contract import digest, protocol_name, validate_config
from tools.validation.load_warning_training_admission import PHYSICAL_LEARNING_FILES, PHYSICAL_VALIDATION_FILES

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BATCH = ROOT/'deliverables/contact_invalid_t04_20261110'
PRIOR_BATCH = ROOT/'deliverables/learning_chain/load_warning_7pct_gru_short_20261109'
VERSION = 'load_warning_mesh_contact_gru_qualification_v1'
VERIFICATION_SHA256 = '48afac3cdb8d7ccddf663b25225133b62a508b07f9110e954372e4d85dd80e6c'
STATIC_VERIFICATION_SHA256 = 'a0ce9916ed3638e4ddebf6acd7f9fab135d19693231438b05f04035432e65101'
PRIOR_REGISTRATION_SHA256 = 'ae63638a5c060ef8807afbe901b306c240f97bce6bbe6c330c7d51bf46157152'
RUNTIME_SHA256 = 'd586be6e14e338089937c13b8f2db67fbeff48121b320856c68e7b9e7b601102'
ORIGINAL_ARCHIVES = {
    'T04_GRU': '239b19f01317d8d6a47ee003397a0dcfe9485c8d8fccfde2be790c1e2f9d02ed',
    'T04_GRU_RETRY': '4a7cee2f6eb1d75e82432bf482adb19e70371a1a1e0c08a4e4d7fd5f081d6413',
    'T04_GRU_YM200': '827a300d96ba0ad7c2ec93463bad8c2faae719cc644606324657b88ff9a93212',
}
ORIGINAL_RECEIPTS = {
    'T04_GRU': 'e123102b09fb318ce51ad745065698f7d3516273271d2d39ef5d47aff742ec26',
    'T04_GRU_RETRY': '91430c19fcad2aed8b3b62991379cb1731f64ac24657d9bc11359e898b979853',
    'T04_GRU_YM200': '93fbeaa876c688a313222edbf7a7a0a0c63d9bea137e79124e6f9bc17fc31912',
}
SOURCE_OVERRIDES = {
    'tools/learning/load_warning_mesh_contact_trial.py': '83eaf4ef8cd49e8a6483545cc715d91a2d6e91a60b57b9f3fc83b0c64b2bbd45',
    'tools/validation/consistent_sac_audit.py': 'bfaed04d59f01b4b4aedfaadde0dd5019b5e3e1da746c8225f16def201961fdb',
    'tools/validation/recovery_learning_audit.py': '85473bfb3a9007052c000e6fdbe9084b8dc5187246a08f77246c4c16775bd08e',
}
REQUIRED_SOURCES = PHYSICAL_LEARNING_FILES + PHYSICAL_VALIDATION_FILES + (
    'tools/learning/load_warning_search_authority.py', 'tools/validation/load_warning_audit.py',
    'tools/validation/consistent_sac_audit.py', 'tools/validation/recovery_learning_audit.py',
    'tools/validation/native_stop_clock.py', 'tools/validation/recurrent_source_audit.py')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _bound(path, expected, *, parse=True):
    _require(_sha(path) == expected, 'Frozen evidence digest differs: '+str(path))
    return json.loads(Path(path).read_bytes()) if parse else expected


def training_cases():
    return [dict(x_offset_m=.0003, y_offset_m=y, roll_rad=math.radians(-1),
                 pitch_rad=math.radians(1), yaw_rad=math.radians(yaw),
                 start_origin_z_m=-.005, target_depth_m=.005)
            for y in (-.0003, .0003) for yaw in (-1.5, 1.5)]


def _runtime(record, common):
    package = Path(record['module_file']).resolve().parent.parent
    files = record['files']
    _require(record['version']=='native313_repair_runtime_v1' and record['training_admitted'] is False
        and record['candidate_dll_sha256']==files['mujoco/mujoco.dll']
        and common['runtime']['module_file']==record['module_file']
        and common['runtime']['compatibility_record_sha256']==RUNTIME_SHA256,
        'Repaired runtime binding differs')
    for name, pin in files.items():
        path = (package/name).resolve()
        _require(not Path(name).is_absolute() and path.is_relative_to(package/'mujoco'),
                 'Runtime file escapes package')
        _bound(path, pin, parse=False)
    inventory = {p.relative_to(package).as_posix() for p in (package/'mujoco').rglob('*')
                 if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc'}
    _require(inventory==set(files) and common['runtime']['dll_verified'] is True
        and common['runtime']['package_files_verified']==len(files)
        and common['runtime']['dll_sha256']=={str(package/name): pin for name,pin in files.items()
            if Path(name).suffix.lower() in ('.dll','.pyd')}, 'Runtime inventory or DLL proof differs')


def _build(batch):
    batch = Path(batch)
    closeout = _bound(batch/'verification.json', VERIFICATION_SHA256)
    evidence = dict(closeout['evidence_sha256'])
    evidence['verification.json'] = VERIFICATION_SHA256
    for name,pin in evidence.items():
        path = (batch/name).resolve()
        _require(path.is_relative_to(batch.resolve()), 'Evidence path escapes batch')
        _bound(path,pin,parse=False)
    def read(name):
        return json.loads((batch/name).read_bytes())
    _require(closeout['status']=='VERIFIED_T04_CONTACT_FIX' and closeout['dynamic_initializations']==1
        and closeout['native_steps']==160000 and closeout['optimizer_updates']==0
        and closeout['training_admitted'] is False and closeout['prior_evidence_unchanged'] is True,
        'Single zero-update repaired dynamic closeout required')
    static = _bound(batch/'static_recompute/verification.json',STATIC_VERIFICATION_SHA256)
    evidence['static_recompute/verification.json'] = STATIC_VERIFICATION_SHA256
    _require(static['passed'] is True and static['source_inputs_unchanged'] is True
        and static['physics_steps']==static['reset_calls']==static['policy_calls']==0
        and all(row['passed'] is True for row in static['checks']), 'Static root-cause evidence differs')
    for name,pin in static['diagnostic_file_sha256'].items():
        _bound(batch/'static_recompute'/name,pin,parse=False)
        evidence['static_recompute/'+name] = pin
    assets = {}
    inputs = read('static_recompute/input_manifest.json')
    for pins in inputs['inputs'].values():
        for name,pin in pins.items():
            _bound(ROOT/name,pin,parse=False)
            assets[name]=pin
    prior = _bound(PRIOR_BATCH/'registration.json',PRIOR_REGISTRATION_SHA256)
    source = prior['source_sha256']
    _require(all(name in source for name in REQUIRED_SOURCES), 'Missing registered physical source pins')
    sources = {name: pin for name,pin in source.items()
        if name.startswith(('models/','tools/model/','tools/control/','tools/dynamics/')) or name in REQUIRED_SOURCES}
    sources.update(SOURCE_OVERRIDES)
    for name,pin in sources.items():
        _require(_sha(ROOT/name)==pin, 'Qualified physical source digest differs: '+name)
    request, receipt, audit = read('t04_repair_request.json'),read('T04_contact_fixed/receipt.json'),read('T04_contact_fixed/audit.json')
    config, common, job = request['config'], request['reg']['common'], request['job']
    validate_config(config)
    physical = config['physical_protocol']
    _require(protocol_name(config)=='load_warning_7pct_mesh_contact' and config['policy_mode']=='gru'
        and config['learning']['seed']==2026110801 and physical['collision_runtime_sha256']==RUNTIME_SHA256
        and physical['search_authority']==dict(search_xy_residual_m_s=.00075,search_xy_acceleration_m_s2=.020)
        and physical['passive_yaw_enabled'] is True and physical['task_deadline_s']==30.
        and physical['search_xy_limit_m_s']==.0009, 'Repaired 900/yaw/30-second domain required')
    runtime=read('runtime.json')
    _require(evidence['runtime.json']==RUNTIME_SHA256
        and runtime['patch_sha256']==evidence['mesh_multicontact_normal.patch'], 'Repair patch/runtime differs')
    _runtime(runtime,common)
    _bound(batch/'T04_contact_fixed/model_used.xml',common['model_xml_sha256'],parse=False)
    evidence['T04_contact_fixed/model_used.xml']=common['model_xml_sha256']
    binding=request['reg']['experiment']
    manifest=_bound(batch/request['checkpoint']/'manifest.json',binding['source_checkpoint'])
    _bound(batch/request['checkpoint']/'state.pt',manifest['state_sha256'],parse=False)
    evidence[request['checkpoint']+'/manifest.json']=binding['source_checkpoint']
    evidence[request['checkpoint']+'/state.pt']=manifest['state_sha256']
    original_request=_bound(PRIOR_BATCH/'requests/T04_GRU.capture.json',request['original_request_sha256'])
    _require(request['source_checkpoint_sha256']==original_request['source']['checkpoint_sha256']
        and request['static_candidate_sha256']==evidence['frozen_after.json']
        and request['max_attempts']==1 and request['training_admitted'] is False
        and job==dict(original_request['job'],episode_id='T04_contact_fixed',split='diagnostic'),
        'Original actor/pose/seed diagnostic registration differs')
    _require(receipt['experiment']==binding and binding['config_sha256']==digest(config)
        and binding['physical_protocol']==physical and binding['optimizer_updates']==0
        and all(receipt[k]==v for k,v in common.items())
        and all(receipt[k]==job[k] for k in ('episode_id','case','seed','exploration_seed','deterministic'))
        and receipt['archive_sha256']==audit['archive_sha256']==evidence['T04_contact_fixed/episode.json.gz']
        and receipt['reset_attempted']==receipt['reset_completed']==1
        and receipt['physical_substeps']==160000 and receipt['control_cycles']==16000
        and receipt['valid'] is True and receipt['stopped'] is True and receipt['status']=='finished'
        and receipt['training_updates']==0 and receipt['training_admitted'] is False
        and receipt['valid_for_learning'] is False and receipt['error'] is None and not receipt['nonfinite_fields'],
        'Audited diagnostic receipt must remain valid, stopped and quarantined')
    _require(all(audit[k] is True for k in ('verified','source_replay_verified','native_reference_verified'))
        and audit['config_sha256']==digest(config) and audit['physical_protocol_sha256']==digest(physical)
        and audit['source_checkpoint_sha256']==binding['source_checkpoint'] and audit['episode_id']==job['episode_id']
        and audit['policy_mode']=='gru' and audit['optimizer_updates']==0
        and audit['audit_physical_initializations']==audit['audit_optimizer_updates']==0
        and audit['training_admitted'] is False and audit['valid_for_learning'] is False
        and audit['task_outcome']==receipt['outcome']==closeout['dynamic_outcome']=='TASK_FAILURE'
        and receipt['final_reason']==closeout['reason']=='TIME_LIMIT', 'Full native/source audit binding differs')
    facts, dynamic = receipt['guard_facts'], common['dynamic_config']
    _require(facts['simulation_valid'] is True and facts['checked_substeps']==160000
        and all(not facts[k] for k in ('invalid_reasons','contact_reasons','motion_reasons'))
        and dynamic['stop_penetration_m']==30e-6 and dynamic['invalid_penetration_m']==80e-6
        and dynamic['stop_torque_Nm']==.1 and dynamic['actual_speed_limit']==.02
        and dynamic['actual_angular_speed_limit']==.5, 'Original hard protections must remain intact')
    stop=audit['stop']
    _require(stop['clock_version']=='native_event_stop_clock_v1' and stop['decision_time_s']<=30.+1e-8
        and abs(stop['decision_time_s']-receipt['stop_time_s'])<1e-8
        and receipt['task_end_time_s']<=stop['decision_time_s']+1.+1e-8
        and receipt['audit_end_time_s']<=32.+1e-8
        and abs(stop['end_time_s']-receipt['audit_end_time_s'])<1e-8
        and stop['final_native_samples']==10000, 'Native stop/deadline evidence differs')
    loads=audit['load_warnings']
    _require(loads['verified'] is True and loads['native_samples']==160000
        and loads['actual_search_resumptions']==closeout['actual_search_resumptions']==len(loads['recoveries'])==4
        and all(r['search_executed'] is True and r['actual_at_release_m']>=249e-6
                and abs(r['reference_distance_m']-300e-6)<1e-9 for r in loads['recoveries'])
        and audit['passive_channel']['verified'] is True and audit['passive_channel']['passive_yaw_enabled'] is True,
        'Real retract/research and passive yaw evidence required')
    _require(all(m['samples']==m['episodes']==0 for m in loads['metrics'].values()) and not loads['events'],
             'Frozen diagnostic has no warning-threshold dynamic coverage')
    before,after=read('frozen_before_with_control.json'),read('frozen_after.json')
    _require(before['passed'] is False and after['passed'] is True
        and after['runtime_sha256']==RUNTIME_SHA256
        and before['model_sha256']==after['model_sha256']==common['model_xml_sha256']
        and after['native_and_multiccd_enabled'] is True and after['physical_steps']==0
        and after['static_queries']==10, 'Same-geometry static repair evidence required')
    witnesses={}
    for identity in ORIGINAL_ARCHIVES:
        original=_bound(PRIOR_BATCH/'run'/identity/'receipt.json',ORIGINAL_RECEIPTS[identity])
        _bound(PRIOR_BATCH/'run'/identity/'episode.json.gz',ORIGINAL_ARCHIVES[identity],parse=False)
        _require(original['archive_sha256']==ORIGINAL_ARCHIVES[identity] and original['valid'] is False
            and original['final_reason']=='INVALID_PENETRATION' and original['training_admitted'] is False,
            'Original invalid evidence must remain quarantined')
        old,new=before['results'][identity],after['results'][identity]
        shallow, separated,deep=new['shallow'],new['separated'],new['true_deep']
        _require(old['passes'] is False and old['shallow']['full_penetration_m']>80e-6
            and new['passes'] is True and shallow['finite'] is True and shallow['pair_contacts']>0
            and 0.<shallow['pair_penetration_m']<1e-6 and shallow['full_penetration_m']<1e-6
            and abs(shallow['pair_normal_z'])>.999 and separated['finite'] is True
            and separated['pair_contacts']==separated['all_contacts']==0
            and deep['finite'] is True and deep['pair_contacts']>0 and deep['pair_penetration_m']>80e-6,
            'Repair must retain shallow contact, separation and real deep penetration')
        witnesses[identity]=deepcopy(new)
    aligned=after['aligned_mesh_faces']
    _require(aligned['passes'] is True and aligned['finite'] is True and aligned['pair_contacts']>=2
        and abs(aligned['pair_penetration_m']-100e-6)<1e-9, 'Aligned-face multicontact must remain enabled')
    return dict(version=VERSION, purpose='Bounded fresh GRU development short training only',
        policy_modes=['gru'], learning_seed=2026110801, replay_focus='search_entry_event_half_v1',
        training_initialization='fresh_actor_critics_targets_optimizers_replay',
        physical_protocol=deepcopy(physical), physical_protocol_sha256=digest(physical), common=deepcopy(common),
        qualified_episodes=1, qualified_episode_ids=['T04_contact_fixed'], dynamic_successes=0,
        actual_search_resumptions=4, training_cases=training_cases(),
        development_cases=[deepcopy(j['case']) for j in prior['evaluate']],
        replay_import_allowed=False, excluded_archive_sha256=list(ORIGINAL_ARCHIVES.values())+[audit['archive_sha256']],
        development_replay_allowed=False, allowed_training_episode_ids=['T01_GRU','T02_GRU','T03_GRU','T04_GRU'],
        coverage=dict(force_gt5_dynamic=False,force_gt6_dynamic=False,rotation_gt2p5_dynamic=False,
                      successful_insertion_new_runtime=False, two_timestep_dynamic_comparison=False,
                      forced_overload_100ms_recovery=False, static_true_deep_contact=True),
        static_witnesses=witnesses, evidence_sha256=evidence, source_sha256=sources, asset_sha256=assets,
        original_archive_sha256=deepcopy(ORIGINAL_ARCHIVES), original_receipt_sha256=deepcopy(ORIGINAL_RECEIPTS),
        prior_registration_sha256=PRIOR_REGISTRATION_SHA256,
        original_request_sha256=request['original_request_sha256'], runtime_record_sha256=RUNTIME_SHA256)


def build_mesh_contact_qualification(batch=DEFAULT_BATCH):
    try:
        proof=_build(batch)
        return dict(proof,proof_sha256=digest(proof))
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError('Complete frozen mesh contact qualification evidence required') from exc


def verify_mesh_contact_qualification(proof, *, config):
    validate_config(config)
    _require(protocol_name(config)=='load_warning_7pct_mesh_contact' and config['policy_mode']=='gru'
        and config['learning']['seed']==2026110801 and config.get('replay_focus')=='search_entry_event_half_v1',
        'Only fresh GRU mesh contact development training with registered event replay is permitted')
    _require(isinstance(proof,dict) and proof.get('version')==VERSION
        and proof.get('physical_protocol_sha256')==digest(config['physical_protocol'])
        and proof.get('proof_sha256')==digest({k:v for k,v in proof.items() if k!='proof_sha256'}),
        'Mesh contact qualification protocol or digest differs')
    _require(digest(proof)==digest(build_mesh_contact_qualification()), 'Qualification differs from frozen evidence')


def verify_mesh_contact_training_job(job, *, proof=None):
    """Domain only; caller verifies fresh checkpoint, registration and unique job digest."""
    try:
        _require(job['episode_id'] in ('T01_GRU','T02_GRU','T03_GRU','T04_GRU')
            and job['policy_mode']=='gru' and job['split']=='train' and job['deterministic'] is False
            and all(type(job[k]) is int and 0<=job[k]<2**32 for k in ('seed','exploration_seed'))
            and isinstance(job['case']['name'],str) and bool(job['case']['name'].strip())
            and digest({k:v for k,v in job['case'].items() if k!='name'}) in map(digest,training_cases()),
            'Only newly registered T01-T04 GRU jobs in the four training poses are permitted')
        if proof is not None:
            _require(digest(proof)==digest(build_mesh_contact_qualification()),
                     'Training proof differs from frozen mesh repair evidence')
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError('Complete new registered training job required') from exc
