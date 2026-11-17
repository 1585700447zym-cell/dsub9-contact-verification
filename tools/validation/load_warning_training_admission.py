"""Promote frozen dynamic evidence to a versioned G2 prerequisite, never to replay.

No simulator or policy is created. Original compressed archives are hashed in
bounded chunks; receipts are read one at a time. The independently frozen review
locates the actual enabled control cycle following a warning.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from tools.learning.recovery_learning_contract import digest, protocol_name, validate_config

VERSION = 'load_warning_training_qualification_v1'
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BATCH = ROOT/'deliverables/learning_chain/load_warning_retest_s2_20261108'
REGISTRATION_SHA256 = '04629576a70b2b85c19df065b2dc9c4d5f5f2ee591944fb12375eed61b64c8d8'
VERIFICATION_SHA256 = '10a2a49142217137cfd63d434de444aa3c07b978b8b948730c93ec1d782160e5'
EPISODES = ('GRU_M15_S2', 'GRU_P15_S2', 'MLP_M15_S2', 'MLP_P15_S2')
PHYSICAL_LEARNING_FILES = tuple('tools/learning/'+name+'.py' for name in (
    'load_warning_trial', 'time_budget_trial', 'consistent_sac_trial', 'consistent_reference',
    'global_residual_session', 'global_residual_action', 'guarded_environment', 'guarded_session',
    'session', 'environment', 'runtime', 'newton_damping', 'newton_profile', 'five_axis_session',
    'five_axis_action', 'five_axis_observation', 'observation', 'layered_session',
    'reference_session', 'rebase_session', 'residual_session', 'reward',
    'axis_session', 'load_session', 'functional_session', 'five_axis_contract'))
PHYSICAL_VALIDATION_FILES = tuple('tools/validation/'+name+'.py' for name in (
    'yaw_pilot', 'run_b1_baseline', 'run_b2_search', 'run_contact_cases'))


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def _read(path, expected):
    _require(_sha(path) == expected, 'Frozen qualification evidence digest differs: '+str(path))
    return json.loads(Path(path).read_bytes())


def _number(value):
    _require(type(value) in (int, float) and math.isfinite(value), 'Finite qualification measurement required')
    return value


def _same(a, b):
    _require(math.isclose(_number(a), _number(b), rel_tol=1e-11, abs_tol=1e-8),
             'Qualification measurement binding differs')


def _build(batch):
    batch = Path(batch)
    registration = _read(batch/'registration.json', REGISTRATION_SHA256)
    verification = _read(batch/'verification.json', VERIFICATION_SHA256)
    _require(registration['version'] == 'load_warning_s2_retest_v1'
        and verification['registration_sha256'] == REGISTRATION_SHA256
        and verification['delivery_verified'] is True
        and verification['attempts'] == verification['independent_audits_passed'] == 4
        and registration['training_updates'] == registration['replay_publications'] == 0
        and verification['optimizer_updates'] == 0
        and registration['task_deadline_s'] == 30 and registration['passive_yaw_enabled'] is True,
        'Frozen four-episode qualification batch required')
    schedule = registration['schedule']
    _require(tuple(j['episode_id'] for j in schedule) == EPISODES, 'Qualification schedule differs')
    # Training admission code may change; the simulator, controller, geometry,
    # reward and observation path that produced this qualification may not.
    pins = registration['source_and_model_pins']
    required_sources = PHYSICAL_LEARNING_FILES + PHYSICAL_VALIDATION_FILES
    _require(all(name in pins for name in required_sources), 'Missing qualified physical source pins')
    physical_sources = {name:value for name,value in pins.items()
        if name.startswith(('models/','tools/model/','tools/control/','tools/dynamics/'))
        or name in required_sources}
    for name, expected in physical_sources.items():
        _require(_sha(ROOT/name) == expected, 'Qualified physical source digest differs: '+name)
    evidence_hashes = dict(registration_json=REGISTRATION_SHA256, verification_json=VERIFICATION_SHA256)

    def bound(name, *, parse=True):
        expected = verification['files'][name]
        path = batch/name
        _require(_sha(path) == expected, 'Frozen qualification evidence digest differs: '+name)
        evidence_hashes[name] = expected
        return json.loads(path.read_bytes()) if parse else expected

    ledger, result = bound('ledger.json'), bound('batch_result.json')
    _require(ledger['status'] == 'COMPLETED' and result['verified'] is True
        and ledger['registration_sha256'] == result['registration_sha256'] == REGISTRATION_SHA256
        and result['optimizer_updates'] == result['replay_publications'] == 0
        and result['policy_training_approved'] is False, 'Qualification batch is not closed and quarantined')
    _require(tuple(a['episode_id'] for a in ledger['attempts']) == EPISODES
        and all(a['status'] == 'AUDITED' for a in ledger['attempts']), 'Four completed independent audits required')
    common = physical = None
    episodes, continued, recoveries = [], {}, []
    for job in schedule:
        identity, mode = job['episode_id'], job['policy_mode']
        request_name = 'requests/'+identity+'.json'
        request = bound(request_name)
        _require(evidence_hashes[request_name] == registration['requests'][identity]
            and request['job'] == job and job['split'] == 'qualification', 'Qualification request binding differs')
        config = validate_config(request['config'])
        _require(protocol_name(config) == 'load_warning' and config['policy_mode'] == mode,
                 'Load-warning policy binding required')
        binding = registration['modes'][mode]['binding']
        if common is None:
            common, physical = deepcopy(request['reg']['common']), deepcopy(config['physical_protocol'])
        _require(common == request['reg']['common'] and physical == config['physical_protocol']
            and request['reg']['experiment'] == binding and binding['config_sha256'] == digest(config)
            and binding['physical_protocol'] == physical and binding['optimizer_updates'] == 0,
            'Qualification physical domain or behavior binding differs')
        folder = 'run/'+identity+'/'
        audit, receipt, review = bound(folder+'audit.json'), bound(folder+'receipt.json'), bound('review/'+identity+'.json')
        archive_sha = bound(folder+'episode.json.gz', parse=False)
        model_sha = bound(folder+'model_used.xml', parse=False)
        _require(all(audit[k] is True for k in ('verified','source_replay_verified','native_reference_verified'))
            and audit['physical_protocol_sha256'] == digest(physical)
            and audit['policy_mode'] == mode and audit['episode_id'] == identity
            and audit['config_sha256'] == digest(config)
            and audit['source_checkpoint_sha256'] == binding['source_checkpoint']
            and audit['archive_sha256'] == receipt['archive_sha256'] == review['archive_sha256'] == archive_sha
            and model_sha == common['model_xml_sha256'] == receipt['model_xml_sha256'],
            'Independent native/source audit binding differs')
        _require(receipt['status'] == 'finished' and receipt['valid'] is True and receipt['stopped'] is True
            and receipt['experiment'] == binding and not receipt.get('error') and not receipt['nonfinite_fields']
            and all(receipt[k] == v for k,v in common.items())
            and all(receipt[k] == job[k] for k in ('case','seed','episode_id','exploration_seed','deterministic'))
            and receipt['reset_attempted'] == receipt['reset_completed'] == 1,
            'Completed matching physical receipt required')
        _require(audit['optimizer_updates'] == receipt['training_updates'] == 0
            and all(obj[k] is False for obj in (audit,receipt) for k in ('training_admitted','valid_for_learning')),
            'Qualification evidence cannot already be training data')
        yaw = audit['passive_channel']
        _require(yaw['verified'] is True and yaw['passive_yaw_enabled'] is True
            and type(yaw['recurrence_updates_checked']) is int and yaw['recurrence_updates_checked'] > 0,
            'Measured passive-yaw feedback required')
        load, facts = audit['load_warnings'], receipt['guard_facts']
        _require(load['verified'] is True and review['audit_verified'] is True
            and load == review['native_load'] and facts == review['guard_facts']
            and facts['simulation_valid'] is True and not facts['invalid_reasons']
            and set(facts['contact_reasons']) <= {'FORCE_LIMIT'}
            and set(facts['motion_reasons']) <= {'ROTATION_LIMIT'}
            and load['native_samples'] == receipt['physical_substeps'] == facts['checked_substeps']
            and receipt['control_cycles']*10 == load['native_samples'] <= 160000,
            'Complete qualified native warning evidence required')
        for key in ('events','metrics','peak_force_N','peak_rotation_rad'):
            _require(load[key] == receipt['load_warnings'][key], 'Native warning receipt differs')
        stop = audit['stop']
        decision, task_end, audit_end = [receipt[k] for k in ('stop_time_s','task_end_time_s','audit_end_time_s')]
        _same(decision, stop['decision_time_s']); _same(audit_end, stop['end_time_s'])
        _same(task_end, review['task_end_time_s']); _same(audit_end, review['audit_end_time_s'])
        _require(stop['clock_version'] == 'native_event_stop_clock_v1'
            and 0 <= _number(decision) <= 30.+1e-8
            and decision <= task_end+1e-8 <= audit_end+1e-8
            and audit_end >= stop['physical_start_time_s']+2.-1e-8
            and stop['final_native_samples'] >= 10000,
            'Native 30-second action and final-stop clocks required')
        # All four frozen cases succeeded; this does not turn a future valid
        # task failure into a disqualified training episode.
        _require(audit['task_outcome'] == receipt['outcome'] == review['outcome'] == 'FULL_SUCCESS'
            and review['frames']['task']['all_nine_fit'] is True
            and review['frames']['audit']['all_nine_fit'] is True,
            'Frozen success/100nm evidence differs')
        recovered = load['recoveries']
        _require(len(recovered) == load['actual_search_resumptions'] == len(review['recoveries']),
                 'Qualified normal recovery count differs')
        for native, detailed in zip(recovered, review['recoveries'], strict=True):
            _require(all(detailed[k] == v for k,v in native.items()) and native['search_executed'] is True
                and native['reference_distance_m'] >= .0003-1e-12
                and native['actual_at_release_m'] >= .000249-1e-15
                and native['start_tick'] < native['reached_tick'] <= native['release_tick'],
                'Actual recovery release and resumed SEARCH required')
            cycle, release = detailed['executed_search_cycle'], detailed['release_native']
            _same(cycle['start_s'], native['release_tick']*.0002)
            _same(cycle['end_s']-cycle['start_s'], .002)
            _require(cycle['physical_phase_after'] == 'RUNNING' and release['force_N'] <= .5
                and release['linear_m_s'] <= common['dynamic_config']['stopped_speed']
                and release['angular_rad_s'] <= common['dynamic_config']['stopped_angular_speed'],
                'Recovery SEARCH must follow a real low-load release')
            recoveries.append(dict(episode_id=identity, **native))
        for reason in ('FORCE_GT5_N','ROTATION_GT2P5_DEG'):
            if not load['metrics'][reason]['samples']:
                continue
            activity = review['warning_activity'][reason]
            first, cycle = activity['first_native'], activity['first_later_enabled_cycle']
            _require(activity['first_event'] in load['events'] and first['phase'] == 'RUNNING'
                and first['time_s'] < cycle['start_s'] < cycle['end_s'] <= decision
                and cycle['policy_phase'] in ('SEARCH','INSERT') and cycle['physical_phase_after'] == 'RUNNING'
                and activity['enabled_cycles_before_decision'] > 0,
                'Warning lacks a later real enabled control cycle')
            _same(cycle['end_s']-cycle['start_s'], .002)
            continued.setdefault(reason, []).append(dict(episode_id=identity, first_time_s=first['time_s'],
                                                       first_later_enabled_cycle=cycle))
        _require(load['metrics']['FORCE_GT6_N']['samples'] == 0, 'Frozen 6N coverage differs')
        episodes.append(dict(episode_id=identity, policy_mode=mode, case=job['case'],
            archive_sha256=archive_sha, audit_sha256=evidence_hashes[folder+'audit.json'],
            receipt_sha256=evidence_hashes[folder+'receipt.json'],
            task_end_time_s=task_end, stop=stop, native_samples=load['native_samples'],
            passive_yaw_updates=yaw['recurrence_updates_checked']))
        del receipt
    _require(all(continued.get(r) for r in ('FORCE_GT5_N','ROTATION_GT2P5_DEG'))
        and len(recoveries) == verification['actual_search_resumptions'] == 6,
        'Real warning continuation and normal recovery coverage required')
    proof = dict(version=VERSION, verified=True, physical_protocol_sha256=digest(physical), common=common,
        physical_source_sha256=physical_sources,
        source_registration_sha256=REGISTRATION_SHA256, source_verification_sha256=VERIFICATION_SHA256,
        evidence_sha256=evidence_hashes, qualified_episodes=4, qualified_episode_ids=list(EPISODES),
        episodes=episodes, continued_warnings=continued, recoveries=recoveries,
        actual_search_resumptions=len(recoveries), optimizer_updates=0, replay_publications=0,
        data_role='development_qualification_only',
        coverage=dict(force_gt5_continued=True, rotation_gt2p5_continued=True,
            force_gt6_dynamic=False, normal_recovery_and_search=True,
            legacy_forced_force_recovery_100ms=False, passive_yaw=True,
            action_deadline_30s=True, native_final_stop=True),
        limitations=['Force above 6 N was not dynamically observed.',
            'Normal recovery uses instantaneous low-load release, not the legacy forced 100 ms recovery chain.',
            'Four known development cases do not establish generalization or an algorithm advantage.'])
    return dict(proof, proof_sha256=digest(proof))


def build_load_warning_qualification(batch):
    """Read the approved frozen batch; returned proof does not publish its data."""
    try:
        return _build(batch)
    except (KeyError, TypeError, IndexError, OSError) as exc:
        raise ValueError('Incomplete frozen load-warning qualification evidence') from exc


def verify_load_warning_qualification(proof, *, config):
    """Check content against fixed external anchors, not a self-signed boolean."""
    config = validate_config(config)
    _require(protocol_name(config) == 'load_warning', 'Load-warning qualification requires its own protocol')
    _require(isinstance(proof, dict) and proof.get('version') == VERSION, 'Qualification version differs')
    _require(proof.get('proof_sha256') == digest({k:v for k,v in proof.items() if k != 'proof_sha256'}),
             'Qualification proof digest differs')
    _require(proof.get('physical_protocol_sha256') == digest(config['physical_protocol']),
             'Qualification physical protocol differs')
    expected = build_load_warning_qualification(DEFAULT_BATCH)
    _require(digest(proof) == digest(expected), 'Qualification differs from independently frozen evidence')
