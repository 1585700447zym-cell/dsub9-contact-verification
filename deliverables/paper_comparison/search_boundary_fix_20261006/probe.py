"""Three development regressions only; no neural policy, training or publication."""
from pathlib import Path
import argparse, gzip, hashlib, json, math, os, sys, time
from copy import deepcopy

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault('MPLCONFIGDIR', str(ROOT/'tmp/matplotlib_search_boundary_fix'))
from tools.validation.run_clearance_preflight import write, now, archive_episode, record_error
from tools.validation import run_v4_adapter_preflight as old

SEED = 2026092716
SPECS = [dict(id=mode+'_y_neg_150', mode=mode, profile=profile)
         for mode, profile in [('B2', 'zero'), ('S50', 'uniform_hold50'), ('F50', 'uniform_hold50')]]


def read(path): return json.loads(Path(path).read_text(encoding='utf8'))
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs():
    pins = old.input_hashes()
    for path in [OUT/'probe.py', OUT/'scope.json',
                 ROOT/'deliverables/paper_comparison/v4_learning_pilot_20261006/delivery_manifest_v2.json']:
        pins[path.relative_to(ROOT).as_posix()] = sha(path)
    return pins


def make_session(env, mode, common):
    from tools.learning.v4_continuation import ContinuationResidualSession
    from tools.learning.layered_session import LayeredReferenceSession
    base = old.make_session(env, 'F50' if mode == 'B2' else mode, common)
    cls = LayeredReferenceSession if mode == 'B2' else ContinuationResidualSession
    extra = {} if mode == 'B2' else dict(mode=mode)
    return cls(environment=env, controller_factory=base.controller_factory,
               finish_criteria=common['finish_criteria'], geometry_checker=base.geometry_checker, **extra)


def prepare():
    from tools.learning.guarded_environment import LearningEnvironment, GuardCandidateConfig
    from tools.learning.runtime import verify_runtime, active_package
    from tools.evaluation.paper_comparison import comparison_key
    if (OUT/'configuration.json').exists(): raise FileExistsError('Already prepared')
    prior = ROOT/'deliverables/paper_comparison/v4_learning_pilot_20261006'
    common = deepcopy(read(prior/'configuration.json')['common'])
    xml = (prior/'model.xml').read_text(encoding='utf8')
    assert hashlib.sha256(xml.encode()).hexdigest() == common['canonical_model_sha256']
    runtime = verify_runtime(active_package())
    assert comparison_key(runtime) == common['runtime_proof_sha256']
    env = LearningEnvironment(guard_config=GuardCandidateConfig(**common['guard_config']), model_xml=xml)
    session = make_session(env, 'S50', common)  # construction only; no reset/step
    common['search_composition'] = session.controller_factory().metadata()
    common['control_revision'] = 'prospective_search_boundary_exhaustion_v1'
    common['frozen_common_source_sha256'] = {n: sha(ROOT/n) for n in common['frozen_common_source_sha256']}
    config = dict(scope='boundary_development_no_learning', common=common, common_key=comparison_key(common),
                  specs=SPECS, seed=SEED, input_sha256=inputs(), prior_cumulative=142, max_new_episodes=3,
                  max_cycles=14500, per_episode_wall_s=1200, training_admitted=False,
                  formal_updates=0, policy_calls=0, replay_published=0, independent_tests=0)
    (OUT/'model.xml').write_text(xml, encoding='utf8', newline='\n')
    write(OUT/'configuration.json', config)
    write(OUT/'preparation_binding.json', {n: sha(OUT/n) for n in ('configuration.json', 'model.xml')})


def verify():
    from tools.learning.runtime import verify_runtime, active_package
    from tools.evaluation.paper_comparison import comparison_key
    c = read(OUT/'configuration.json')
    if any(sha(OUT/n) != h for n, h in read(OUT/'preparation_binding.json').items()):
        raise ValueError('Prepared file changed')
    if c['input_sha256'] != inputs(): raise ValueError('Execution source changed')
    if comparison_key(verify_runtime(active_package())) != c['common']['runtime_proof_sha256']:
        raise ValueError('Runtime changed')
    a = read(OUT/'preflight_admission.json')
    if (a['configuration_sha256'] != sha(OUT/'configuration.json') or a['max_new_episodes'] != 3
            or a['training_admitted'] is not False or a['tests_passed'] is not True
            or a['review_critical'] != 0 or a['review_important'] != 0):
        raise ValueError('No matching bounded preflight qualification')
    return c


def run_episode(config, ledger, spec):
    import numpy as np
    from tools.learning.guarded_environment import LearningEnvironment, GuardCandidateConfig
    from tools.validation.run_contact_cases import ContactCase
    from tools.learning.reward import EpisodeReward
    entry = dict(id=spec['id'], spec=spec, status='running', started_at=now(), control_cycles=0, physical_substeps=0)
    ledger['episodes'].append(entry); write(OUT/'run/ledger.json', ledger)
    env = session = None; trace = []; actions = []; rows = []; started = time.monotonic()
    case = ContactCase('y_neg_150', 0., -.00015, 0., 0., -.004, .004)
    try:
        env = LearningEnvironment(guard_config=GuardCandidateConfig(**config['common']['guard_config']),
                                 model_xml=(OUT/'model.xml').read_text(encoding='utf8'))
        session = make_session(env, spec['mode'], config['common'])
        snap = session.reset(case, seed=SEED); trace.append(session.initial_trace_row)
        rng = np.random.default_rng(np.random.SeedSequence([SEED, 1])); held = [0.]*4
        reward = EpisodeReward(.004); draws = checks = 0; maxradius = 0.
        while not session.done:
            if session.cycle_id >= config['max_cycles'] or time.monotonic()-started > config['per_episode_wall_s'] or (OUT/'STOP').exists():
                raise RuntimeError('Bounded development interrupted; no retry')
            sampled = None
            if spec['profile'] != 'zero':
                if session.cycle_id % 50 == 0: held = rng.uniform(-1., 1., 4).tolist(); draws += 1
                sampled = held.copy()
            request = held.copy() if sampled is not None and snap.residual_enabled else [0.]*4
            result = session.advance_cycle(request); trace.append(result.trace_row)
            radius = old.actual_reference_radius(snap, result.trace_row, session.initial)
            if radius is not None:
                checks += 1; maxradius = max(maxradius, radius)
                if radius > .00012+1e-12: raise RuntimeError('Actual SEARCH reference exceeded disk')
            if spec['mode'] == 'B2':
                terms = reward.advance(advance_m=result.trace_row['position_m'][2]-session.initial[2], dt=result.dt,
                    force_N=result.cycle_peaks['force_N'], torque_G_Nm=result.cycle_peaks['torque_G_Nm'])
                terms['terminal'] = reward.finalize(session.adjudicate()['task_outcome']) if result.done else 0.
                terms['total'] += terms['terminal']; log = dict(raw_action=request, experience_action=request, enabled=snap.residual_enabled)
            else: terms = result.reward_terms; log = result.action_log
            actions.append(log)
            rows.append(dict(observation=snap.policy_observation, next_observation=result.next_snapshot.policy_observation,
                action=log['experience_action'], action_active=snap.residual_enabled,
                next_action_active=result.next_snapshot.residual_enabled, action_log=log, sampling_request=sampled,
                reward=terms['total'], reward_terms=terms, dt=result.dt, discount=math.exp(-result.dt/10),
                terminated=bool(result.done), truncated=False, cycle_force_N=result.cycle_peaks['force_N'],
                cycle_torque_G_Nm=result.cycle_peaks['torque_G_Nm'],
                advance_m=result.trace_row['position_m'][2]-session.initial[2], trace_row=result.trace_row))
            snap = result.next_snapshot
            if session.cycle_id % 500 == 0:
                entry.update(control_cycles=session.cycle_id, physical_substeps=env.physical_steps, time_s=float(env.data.time))
                write(OUT/'run/ledger.json', ledger)
                archive_episode(OUT/'run'/(spec['id']+'.partial.json.gz'), dict(trace=trace, actions=actions, transitions=rows,
                    controller_events=session.controller.events, events=env.events, stop_samples=env.stop_samples, guard_facts=env.guard_facts))
                print(json.dumps(dict(id=spec['id'], cycles=session.cycle_id, time_s=float(env.data.time))), flush=True)
        source = session.adjudicate()
        from tools.learning.outcome import classify_outcome
        outcome = classify_outcome(simulation_valid=source['simulation_valid'], physical_stopped=source['physical_stopped'],
            contact_guard=bool(env.guard_facts['contact_reasons']), motion_violation=bool(env.guard_facts['motion_reasons']),
            full_success=session.task_finished and session.reason=='GEOMETRIC_SUCCESS')
        problems = [e for e in session.controller.events if e['reason'] in
                    ('SEARCH_REFERENCE_LIMIT', 'RESIDUAL_REFERENCE_INFEASIBLE', 'REFERENCE_ACTUAL_LIMIT')]
        good = bool(outcome['simulation_valid'] and outcome['physical_stopped'] and not problems and
                    not any(outcome['guard_violations'].values()))
        entry.update(status='finished', ended_at=now(), outcome=outcome, reason=session.reason, verification_passed=good,
                     control_cycles=session.cycle_id, physical_substeps=env.physical_steps, wall_s=time.monotonic()-started)
        raw = dict(scope=config['scope'], spec=spec, seed=SEED, common_key=config['common_key'], trace=trace,
            actions=actions, transitions=rows, observation_schema=getattr(getattr(session, 'observations', None), 'schema', None),
            outcome=outcome, source_session_outcome=source, summary=deepcopy(entry), controller_events=session.controller.events, events=env.events,
            stop_samples=env.stop_samples, guard_facts=env.guard_facts, stop_time=session.stop_time,
            audit_end_time_s=float(env.data.time), task_end_time_s=session.task_end_time, peaks=env.peaks,
            final_session=dict(task_finished=session.task_finished, reason=session.reason, phase=env.phase),
            reference_problems=problems, actual_reference_failed=False, max_actual_reference_radius_m=maxradius,
            actual_reference_checks=checks, warmup_draws=draws, optimizer_steps=0, policy_calls=0, fault=None)
        entry['archive_sha256'] = archive_episode(OUT/'run'/(spec['id']+'.json.gz'), raw)
        write(OUT/'run/ledger.json', ledger); print(json.dumps(entry, ensure_ascii=False), flush=True)
        return good
    except BaseException as exc:
        record_error(OUT/'run', ledger, entry, exc, case, trace, env, session)
        archive_episode(OUT/'run'/(spec['id']+'.actions_error.json.gz'), dict(actions=actions, transitions=rows))
        raise


def execute():
    config = verify(); (OUT/'run').mkdir(exist_ok=False)
    ledger = dict(status='running', started_at=now(), episodes=[], prior_cumulative=142, max_new_episodes=3,
                  training_updates=0, policy_calls=0, replay_published=0, independent_tests=0, retry_allowed=False)
    write(OUT/'run/ledger.json', ledger)
    try:
        for spec in SPECS:
            verify()
            if (OUT/'STOP').exists() or not run_episode(config, ledger, spec): break
        verify(); ledger['status'] = 'complete' if len(ledger['episodes']) == 3 and ledger['episodes'][-1]['verification_passed'] else 'controlled_stop'
    except BaseException as exc:
        ledger.update(status='error', error=repr(exc)); raise
    finally:
        ledger.update(ended_at=now(), unused_closed=3-len(ledger['episodes']))
        write(OUT/'run/ledger.json', ledger)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('operation', choices=['prepare', 'execute'])
    args = parser.parse_args()
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    prepare() if args.operation == 'prepare' else execute()
