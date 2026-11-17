"""Frozen 7pct dynamic evidence for a bounded GRU development pilot only.

Archives/checkpoints are hashed in chunks; receipts are read one at a time.
No environment, neural network, replay publication or optimizer is constructed.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from tools.learning.recovery_learning_contract import digest, protocol_name, validate_config
from tools.validation.load_warning_training_admission import PHYSICAL_LEARNING_FILES, PHYSICAL_VALIDATION_FILES

VERSION = 'search_authority_gru_training_qualification_v1'
ADJUSTED_VERSION = 'search_authority_gru_single_y_adjustment_qualification_v1'
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BATCH = ROOT/'deliverables/learning_chain/load_warning_7pct_threeway_20261109'
ADJUSTMENT_BATCH = ROOT/'deliverables/learning_chain/load_warning_7pct_gru_short_20261109'
ADJUSTMENT_JOB_ID = 'T04_GRU_YM200'
ADJUSTMENT_PINS = {
    'registration.json':'ae63638a5c060ef8807afbe901b306c240f97bce6bbe6c330c7d51bf46157152',
    'continuation_registration.json':'7ca1f0be478f033b5b5eeda0543546ef76b85e7bf59dfea63437edda2a3b0882',
    'qualification.json':'fd0defe5d180929d15c229549a9403242758508e62f2c5e58d26ef212288c1a1',
    'run/T04_GRU/receipt.json':'e123102b09fb318ce51ad745065698f7d3516273271d2d39ef5d47aff742ec26',
    'run/T04_GRU/episode.json.gz':'239b19f01317d8d6a47ee003397a0dcfe9485c8d8fccfde2be790c1e2f9d02ed',
    'run/T04_GRU_RETRY/receipt.json':'91430c19fcad2aed8b3b62991379cb1731f64ac24657d9bc11359e898b979853',
    'run/T04_GRU_RETRY/episode.json.gz':'4a7cee2f6eb1d75e82432bf482adb19e70371a1a1e0c08a4e4d7fd5f081d6413',
}
VERIFICATION_SHA256 = 'c8ff516380bc205d08baa9fe4b468bfccb8862519a8708499e124b4a19b2e3e8'
REGISTRATION_SHA256 = '381aac93ab4e75058aa2758476d27e24d97f75701b7c671990b88b57bb69ebe3'
EPISODES = ('E01_ADMITTANCE','E01_MLP','E01_GRU','E02_ADMITTANCE','E02_MLP','E02_GRU')
# The original closeout anchors archives and audit hashes via its continuation
# ledger, but omits receipt hashes. Pin those original reviewed bytes explicitly.
RECEIPT_SHA256 = {
    'E01_ADMITTANCE':'dc41b1bf4c8ec742fb4912a6bccaedd2cf703ea6fc6162cb1cbdcd992d23d432',
    'E01_MLP':'387fb6558a19e6eab45ad0a8664db96723c4b74a774fdfb21d6f41b0d80ca9d2',
    'E01_GRU':'22dc4d9cacaf0aac5eb5bd3f13d2d3c9b4dec1f0cab0e3936fc250e8180368e5',
    'E02_ADMITTANCE':'515ff689e14a4ffdbfe36a0989f9dea2eef798321e8cba131a81a308e220be13',
    'E02_MLP':'97c501003681b138e8261d45042726b9f426824f2c985a811d76e9c3919e3909',
    'E02_GRU':'146849649f41f40bff142c790836d49a50ed09170a057bcd98d152fcee1fe794',
}
REQUIRED_SOURCES = PHYSICAL_LEARNING_FILES + PHYSICAL_VALIDATION_FILES + (
    'tools/learning/load_warning_search_authority.py', 'tools/validation/load_warning_audit.py',
    'tools/validation/recovery_learning_audit.py', 'tools/validation/consistent_sac_audit.py',
    'tools/validation/native_stop_clock.py', 'tools/validation/recurrent_source_audit.py')


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _close(a, b):
    return (type(a) in (int,float) and type(b) in (int,float) and math.isfinite(a)
            and math.isfinite(b) and math.isclose(a,b,rel_tol=0.,abs_tol=1e-8))


def training_cases():
    return [dict(x_offset_m=.0003,y_offset_m=y,roll_rad=math.radians(-1),
                 pitch_rad=math.radians(1),yaw_rad=math.radians(yaw),
                 start_origin_z_m=-.005,target_depth_m=.005)
            for y in (-.0003,.0003) for yaw in (-1.5,1.5)]


def verify_search_authority_training_job(job, *, proof=None):
    """Additional domain check; the caller must still verify the trusted job digest."""
    try:
        if isinstance(proof,dict) and proof.get('version')==ADJUSTED_VERSION:
            expected=build_adjusted_search_authority_qualification()
            _require(digest(proof)==digest(expected), 'Adjusted qualification differs from frozen evidence')
            _require(job['episode_id'] not in proof['excluded_training_episode_ids'],
                     'Invalid original and retry episodes remain excluded')
            if job['episode_id']==ADJUSTMENT_JOB_ID:
                _require(digest(job)==digest(proof['adjustment']['job']),
                         'Only the exact single adjusted job is permitted')
                return
        _require(job.get('episode_id')!=ADJUSTMENT_JOB_ID,
                 'The adjusted job requires its independently verified qualification')
        case = job['case']
        _require(job['policy_mode']=='gru' and job['split']=='train' and job['deterministic'] is False
            and isinstance(job['episode_id'],str) and bool(job['episode_id'].strip())
            and job['episode_id'] not in EPISODES
            and all(type(job[k]) is int and 0 <= job[k] < 2**32 for k in ('seed','exploration_seed'))
            and isinstance(case.get('name'),str) and bool(case['name'].strip())
            and digest({k:v for k,v in case.items() if k!='name'}) in map(digest,training_cases()),
            'Only fresh GRU jobs in the four registered training pose combinations are permitted')
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError('Complete registered GRU training job required') from exc


def _build(batch):
    batch = Path(batch)
    evidence = {}

    def bound(name, expected, *, parse=True):
        path = batch/name
        _require(_sha(path)==expected, 'Frozen qualification evidence digest differs: '+name)
        evidence[name] = expected
        return json.loads(path.read_bytes()) if parse else expected

    closeout = bound('verification.json', VERIFICATION_SHA256)
    reg = bound('registration.json', REGISTRATION_SHA256)
    _require(closeout['status']=='COMPLETED' and closeout['attempts']==6 and closeout['audited']==5
        and closeout['unqualified_stop']==1 and closeout['updates']==closeout['publications']==0
        and closeout['stage_initializations']==6 and closeout['cumulative_initializations']==481
        and closeout['native_steps']==890720
        and reg['version']=='load_warning_7pct_threeway_development_v1'
        and reg['training_updates']==reg['replay_publications']==0 and reg['deterministic'] is True,
        'Frozen six-attempt, five-audit development closeout required')
    for name, expected in closeout['evidence_sha256'].items():
        bound(name,expected,parse=False)
    ledger = json.loads((batch/'continuation_ledger.json').read_bytes())
    _require(ledger['status']=='COMPLETED' and ledger['registration_sha256']==REGISTRATION_SHA256
        and ledger['original_ledger_sha256']==evidence['ledger.json']
        and ledger['optimizer_updates']==ledger['replay_publications']==0
        and ledger['stage_initializations']==6 and ledger['native_steps']==890720
        and tuple(a['episode_id'] for a in ledger['attempts'])==EPISODES
        and tuple(j['episode_id'] for j in reg['jobs'])==EPISODES,
        'Original and continuation accounting must remain bound')
    pins = reg['source_sha256']
    _require(all(name in pins for name in REQUIRED_SOURCES), 'Missing physical source pins')
    physical_sources = {k:v for k,v in pins.items()
        if k.startswith(('models/','tools/model/','tools/control/','tools/dynamics/')) or k in REQUIRED_SOURCES}
    for name, expected in physical_sources.items():
        _require(_sha(ROOT/name)==expected, 'Qualified physical source digest differs: '+name)
    prep = json.loads((batch/'checkpoints/source_preparation.json').read_bytes())
    _require(evidence['checkpoints/source_preparation.json']==reg['source_preparation_sha256']
        and prep['physical_protocol']=='load_warning_7pct' and prep['new_optimizer_updates']==0
        and prep['replay_publications']==0, 'Frozen zero-update source preparation required')
    common, physical = reg['common'],reg['physical_protocol']
    _require(physical['search_authority']==dict(search_xy_residual_m_s=.00075,search_xy_acceleration_m_s2=.020)
        and physical['passive_yaw_enabled'] is True and physical['task_deadline_s']==30.
        and physical['search_xy_limit_m_s']==.0009, 'Registered 900/yaw/30-second SEARCH authority required')
    for group in prep['groups'].values():
        cfg,binding=group['config'],group['archive_binding']
        _require(protocol_name(cfg)=='load_warning_7pct' and cfg['physical_protocol']==physical
            and binding['physical_protocol']==physical and binding['optimizer_updates']==0
            and binding['config_sha256']==digest(cfg), 'Qualified behavior configuration differs')
        prefix=group['checkpoint_path']+'/'
        manifest=bound(prefix+'manifest.json',group['checkpoint_sha256'])
        _require(manifest['config_sha256']==digest(cfg), 'Qualified checkpoint config differs')
        bound(prefix+'state.pt',manifest['state_sha256'],parse=False)
    qualified=[]; successes=[]; recoveries=[]; gru_recoveries=0
    for job, attempt in zip(reg['jobs'],ledger['attempts']):
        identity=job['episode_id']; prefix='run/'+identity+'/'
        receipt=bound(prefix+'receipt.json',RECEIPT_SHA256[identity])
        archive=bound(prefix+'episode.json.gz',closeout['archive_sha256'][identity],parse=False)
        bound(prefix+'model_used.xml',common['model_xml_sha256'],parse=False)
        group=prep['groups'][job['method']]; binding=group['archive_binding']
        _require(receipt['archive_sha256']==attempt['archive_sha256']==archive
            and receipt['experiment']==binding and receipt['reset_attempted']==receipt['reset_completed']==1
            and receipt['physical_substeps']==attempt['native_steps']
            and all(receipt[k]==v for k,v in common.items())
            and all(receipt[k]==job[k] for k in ('case','seed','episode_id','exploration_seed','deterministic'))
            and receipt['training_updates']==0 and receipt['training_admitted'] is False
            and receipt['valid_for_learning'] is False and not receipt['error'],
            'Original quarantined receipt binding differs')
        if identity=='E01_ADMITTANCE':
            _require(attempt['status']==receipt['outcome']=='STOP_NOT_QUALIFIED'
                and receipt['valid'] is True and receipt['stopped'] is False,
                'The unqualified stop must remain excluded')
            del receipt
            continue
        audit=bound(prefix+'audit.json',attempt['evidence_sha256'])
        _require(attempt['status']=='AUDITED' and receipt['status']=='finished'
            and receipt['valid'] is True and receipt['stopped'] is True
            and not receipt['nonfinite_fields']
            and all(audit[k] is True for k in ('verified','source_replay_verified','native_reference_verified'))
            and audit['episode_id']==identity and audit['archive_sha256']==archive
            and audit['config_sha256']==binding['config_sha256']
            and audit['physical_protocol_sha256']==digest(physical)
            and audit['source_checkpoint_sha256']==binding['source_checkpoint']
            and audit['policy_mode']==job['policy_mode'] and audit['optimizer_updates']==0
            and audit['task_outcome']==receipt['outcome']==attempt['outcome']
            and audit['training_admitted'] is False and audit['valid_for_learning'] is False,
            'Complete independent native/source audit required')
        stop,load,yaw=audit['stop'],audit['load_warnings'],audit['passive_channel']
        _require(stop['decision_time_s']<=30.+1e-8 and stop['end_time_s']<=32.+1e-8
            and _close(stop['decision_time_s'],receipt['stop_time_s'])
            and _close(stop['end_time_s'],receipt['audit_end_time_s'])
            and _close(load['exposure']['task']['duration_s'],receipt['task_end_time_s'])
            and receipt['task_end_time_s']<=stop['decision_time_s']+1.+1e-8
            and load['verified'] is True and load['native_samples']==receipt['physical_substeps']
            and yaw['verified'] is True and yaw['passive_yaw_enabled'] is True
            and yaw['recurrence_updates_checked']>0, 'Native clocks, warning audit and passive yaw required')
        _require(all(m['samples']==0 for m in load['metrics'].values()),
                 'Frozen batch did not dynamically cover warning threshold crossings')
        for item in load['recoveries']:
            _require(item['search_executed'] is True and item['actual_at_release_m']>=.000249-1e-12
                and _close(item['reference_distance_m'],.0003), 'Actual retraction and resumed SEARCH required')
            recoveries.append(dict(episode_id=identity,**item))
        _require(load['actual_search_resumptions']==len(load['recoveries']), 'Recovery count differs')
        if job['policy_mode']=='gru':
            _require(len(load['recoveries'])>0, 'Both GRU yaw cases need measured recovery and SEARCH')
            gru_recoveries+=len(load['recoveries'])
        if audit['task_outcome']=='FULL_SUCCESS': successes.append(identity)
        qualified.append(identity)
        del receipt
    _require(len(qualified)==5 and len(recoveries)==16 and gru_recoveries==8
        and successes==['E02_ADMITTANCE','E02_MLP'], 'Frozen shared geometry/recovery coverage differs')
    dev={job['pair_id']:{k:v for k,v in job['case'].items() if k!='name'} for job in reg['jobs']}
    proof=dict(version=VERSION,verified=True,physical_protocol_sha256=digest(physical),common=deepcopy(common),
        source_registration_sha256=REGISTRATION_SHA256,source_verification_sha256=VERIFICATION_SHA256,
        physical_source_sha256=physical_sources,evidence_sha256=evidence,
        qualified_episodes=5,qualified_episode_ids=qualified,excluded_episode_ids=['E01_ADMITTANCE'],
        development_episode_ids=list(EPISODES),development_cases=list(dev.values()),training_cases=training_cases(),
        policy_modes=['gru'],training_seed=2026110801,data_role='development_qualification_only',
        permitted_use='bounded_gru_search_authority_development_training',replay_import_allowed=False,
        optimizer_updates=0,replay_publications=0,actual_search_resumptions=16,gru_search_resumptions=8,
        recoveries=recoveries,shared_geometry_successes=successes,
        coverage=dict(native_stop=True,passive_yaw=True,normal_recovery_and_search=True,
            shared_geometry_success=True,force_gt5_dynamic=False,force_gt6_dynamic=False,
            rotation_gt2p5_dynamic=False,legacy_forced_force_recovery_100ms=False),
        limitations=['One unqualified stop remains excluded; no qualification data may enter training replay.',
            'No native force/rotation warning threshold crossing occurred in this batch.',
            'E01/E02 remain development retests, not training cases or independent generalization evidence.'])
    return dict(proof,proof_sha256=digest(proof))


def build_search_authority_qualification(batch=DEFAULT_BATCH):
    try:
        return _build(batch)
    except (KeyError,TypeError,IndexError,OSError) as exc:
        raise ValueError('Incomplete frozen SEARCH authority qualification evidence') from exc


def build_adjusted_search_authority_qualification():
    """One explicitly authorized same-sign Y adjustment; original proof stays intact."""
    try:
        for name, expected in ADJUSTMENT_PINS.items():
            _require(_sha(ADJUSTMENT_BATCH/name)==expected,
                     'Frozen adjustment evidence digest differs: '+name)
        read=lambda name: json.loads((ADJUSTMENT_BATCH/name).read_bytes())
        original,continuation,base=map(read,('registration.json','continuation_registration.json','qualification.json'))
        _require(base['proof_sha256']=='1635e4cbfc441667a21701e4bc4baeee1e123f4016e12560e9252655df014d3e'
            and digest(base)==digest(build_search_authority_qualification())
            and original['g1_sha256']==ADJUSTMENT_PINS['qualification.json']
            and continuation['registration_sha256']==ADJUSTMENT_PINS['registration.json']
            and continuation['previous_attempt_sha256']==ADJUSTMENT_PINS['run/T04_GRU/episode.json.gz']
            and continuation['previous_receipt_sha256']==ADJUSTMENT_PINS['run/T04_GRU/receipt.json']
            and continuation['optimizer_updates']==0 and continuation['max_additional_attempts']==1,
            'Original qualification and bounded continuation must remain bound')
        original_job=next(j for j in original['train'] if j['episode_id']=='T04_GRU')
        invalid=[]
        for job in (original_job,continuation['job']):
            identity=job['episode_id']; receipt=read('run/'+identity+'/receipt.json')
            _require(identity in ('T04_GRU','T04_GRU_RETRY')
                and receipt['archive_sha256']==ADJUSTMENT_PINS['run/'+identity+'/episode.json.gz']
                and all(receipt[k]==job[k] for k in ('episode_id','case','seed','exploration_seed','deterministic'))
                and receipt['status']=='finished' and not receipt['error']
                and receipt['outcome']=='INVALID_SIMULATION' and receipt['final_reason']=='INVALID_PENETRATION'
                and receipt['valid'] is False and receipt['stopped'] is False
                and receipt['training_admitted'] is False and receipt['valid_for_learning'] is False
                and receipt['training_updates']==0 and receipt['experiment']['optimizer_updates']==0
                and receipt['source_checkpoint_sha256']==continuation['source_checkpoint_sha256']
                and all(receipt[k]==v for k,v in base['common'].items())
                and digest(receipt['experiment']['physical_protocol'])==base['physical_protocol_sha256']
                and 'INVALID_PENETRATION' in receipt['guard_facts']['invalid_reasons']
                and receipt['cumulative_peaks']['penetration_m']>receipt['dynamic_config']['invalid_penetration_m'],
                'Both invalid trajectories must remain quarantined under the same physical protocol')
            invalid.append(dict(episode_id=identity,outcome=receipt['outcome'],reason=receipt['final_reason'],
                time_s=receipt['audit_end_time_s'],native_steps=receipt['physical_substeps'],
                penetration_m=receipt['cumulative_peaks']['penetration_m']))
            del receipt
        job=deepcopy(original_job)
        job.update(episode_id=ADJUSTMENT_JOB_ID,seed=2026110824,exploration_seed=2026110844)
        job['case'].update(name='TRAIN_T04_YM200',y_offset_m=-.0002)
        proof={k:deepcopy(v) for k,v in base.items() if k!='proof_sha256'}
        proof.update(version=ADJUSTED_VERSION,base_proof_sha256=base['proof_sha256'],
            base_qualification_file_sha256=ADJUSTMENT_PINS['qualification.json'],
            adjustment_evidence_sha256=deepcopy(ADJUSTMENT_PINS),
            excluded_training_episode_ids=['T04_GRU','T04_GRU_RETRY'],
            adjustment=dict(job=job,max_additional_attempts=1,invalid_attempts=invalid,
                scope='One exact same-sign Y=-200um job only; all other qualification scopes unchanged',
                physical_rules_changed=False,invalid_replay_import_allowed=False))
        return dict(proof,proof_sha256=digest(proof))
    except (KeyError,TypeError,IndexError,OSError,StopIteration) as exc:
        raise ValueError('Incomplete frozen single-adjustment qualification evidence') from exc


def verify_search_authority_qualification(proof, *, config):
    config=validate_config(config)
    _require(protocol_name(config)=='load_warning_7pct' and config['policy_mode']=='gru'
        and config['learning']['seed']==2026110801, 'Qualification is restricted to this new GRU development pilot')
    _require(isinstance(proof,dict) and proof.get('version') in (VERSION,ADJUSTED_VERSION)
        and proof.get('proof_sha256')==digest({k:v for k,v in proof.items() if k!='proof_sha256'})
        and proof.get('physical_protocol_sha256')==digest(config['physical_protocol']),
        'Qualification version, digest or physical domain differs')
    expected=(build_adjusted_search_authority_qualification() if proof['version']==ADJUSTED_VERSION
              else build_search_authority_qualification())
    _require(digest(proof)==digest(expected), 'Qualification differs from independently frozen evidence')
