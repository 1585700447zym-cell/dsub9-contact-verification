"""Stdlib-only closure audit: never deserialize tensors or restart numeric work."""
import argparse, ast, json, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
KIT = HERE.parent / 'b2_warm_import_repair_20261009'
sys.path.insert(0, str(KIT))
from joint_contract import read, write, sha, digest
from gate_contract import verify_grant, LIMITS, ROLE_LIMITS, Gate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--seal', action='store_true')
    parser.add_argument('--current-docs', action='store_true')
    parser.add_argument('--runtime-only', action='store_true')
    args = parser.parse_args()
    if args.seal and (args.runtime_only or (HERE / 'delivery_manifest.json').exists()):
        raise FileExistsError('Never reseal or seal a partial audit')
    checks = 0

    def check(ok, label):
        nonlocal checks
        if not ok:
            raise AssertionError(label)
        checks += 1

    reg = read(HERE / 'launch_registration/registration.json')
    check(reg['stage_id'] == 'B2-SCOPE-18', 'execution identity')
    check(sha(KIT / 'delivery_manifest.json') == reg['preparation_manifest_sha256'], 'approved preparation seal')
    proc = subprocess.run([sys.executable, '-I', '-X', 'utf8', '-B', str(KIT / 'verify_delivery.py')],
                          cwd=ROOT, capture_output=True, text=True, encoding='utf8', check=True)
    prior = json.loads(proc.stdout.strip().splitlines()[-1])
    check(prior['old_sealed_members_preserved'] + prior['sealed_files'] == 3443, '3443 prior sealed members preserved')
    check(prior['bound_inputs'] == 2588, '2588 prepared source bindings preserved')
    grant = read(HERE / 'grant.json')
    pin = read(HERE / 'grant_pin.json')['sha256']
    candidate = read(KIT / 'candidate.json')
    check(digest(candidate) == reg['candidate_sha256'], 'registered frozen candidate')
    check(digest(grant) == pin == reg['grant_sha256'] == digest(read(HERE / 'launch_registration/grant.json')), 'one approved grant')
    verify_grant(candidate, grant, pin, sha(KIT / 'source_binding.json'))
    checks += 1
    check(read(KIT / 'future_claims/consumed.json') == dict(grant_sha256=pin, output=str(HERE.resolve())), 'unique consumed claim')
    counter = read(HERE / 'counter.json')
    closure = read(HERE / 'authorization_closure.json')
    check(counter['status'] == 'CLOSED' and closure['status'] == 'CLOSED_COMPLETE', 'successful durable closure')
    check(counter['limits'] == reg['limits'] == LIMITS, 'exact approved limits')
    check(counter['attempted'] == LIMITS and all(type(v) is int for v in counter['attempted'].values()), 'all registered operations consumed exactly')
    check(counter['unused_closed'] == {k: 0 for k in LIMITS}, 'no remaining balance')
    for role in ('parent', 'reader'):
        check(counter['roles'][role]['claimed'] is True, 'role claimed ' + role)
        check(counter['roles'][role]['attempted'] == ROLE_LIMITS[role], 'role operation counts ' + role)
    check(closure['counter_closed'] and closure['unused_closed'] and closure['no_retry'], 'one-shot grant closed')
    check(closure['counter_error'] is None and closure['receipt_error'] is None, 'closure without errors')
    check(closure['process_exit_confirmed'], 'owned processes exited')
    check(closure['automatic_tracking'] == 'PAUSED' and closure['cumulative_dynamic'] == 245 and closure['training_admitted'] is False, 'research scope unchanged')
    supervisors = {}
    for name, cap in (('supervisor', grant['whole_wall_s']), ('reader', grant['reader_wall_s'])):
        receipt = read(HERE / (name + '.supervisor.json'))
        supervisors[name] = receipt
        check(receipt['process_exit_confirmed'] and receipt['owned_launcher_exit_confirmed'], 'owned tree and launcher exited ' + name)
        check(receipt['go_issued'] and receipt['returncode'] == 0 and not receipt['deadline_hit'], 'successful owned process ' + name)
        check(0 < receipt['wall_seconds'] < cap, 'within deadline ' + name)
        check((HERE / (name + '.ready.json')).is_file() and (HERE / (name + '.go.json')).is_file(), 'readiness and GO evidence ' + name)
        log = (HERE / (name + '.log')).read_text(encoding='utf8')
        check('Traceback (most recent call last)' not in log, 'no runtime traceback ' + name)
    try:
        Gate(HERE, 'parent')
    except PermissionError as exc:
        check('closed authorization' in str(exc), 'closed entry refuses reuse before numeric imports')
    else:
        raise AssertionError('Closed authorization remains usable')
    check(not (HERE / 'counter.lock').exists(), 'no counter lock left behind')
    check(not list((HERE / 'checkpoint').glob('*.staging')), 'no partial checkpoint')
    manifest = read(HERE / 'checkpoint/manifest.json')
    request = read(HERE / 'reader_request.json')
    reply = read(HERE / 'reader_reply.json')
    assessment = read(HERE / 'assessment.json')
    check(manifest['version'] == 'b2_archived_warm_manifest_v1', 'warm checkpoint format')
    check(sha(HERE / 'checkpoint/state.pt') == manifest['state_sha256'], 'payload bytes match saved manifest, no deserialization')
    check(sha(HERE / 'checkpoint/manifest.json') == request['manifest_sha256'], 'independent reader received exact manifest')
    state_hash = manifest['state_digest']
    check(len(state_hash) == 64 and state_hash == request['state_digest'] == reply['state_digest'] == assessment['state_digest'], 'complete typed-state summaries agree')
    check(reply['verified'] is True and reply['live_restore_verified'] is True, 'independent rebuild and live component readback passed')
    check(assessment['verified'] is True and assessment['numeric_restore_verified'] is True, 'numeric restoration passed')
    check(assessment['replay_rows'] == 19300 and assessment['warm_draws'] == 388, 'complete registered warm boundary')
    check(assessment['physical_resume_verified'] is False and assessment['training_admitted'] is False and assessment['cumulative_dynamic'] == 245, 'no physical or training qualification')
    launch = read(HERE / 'launch_registration/launcher_result.json')
    check(launch['returncode'] == 0 and launch['no_retry'], 'outer launcher successful once')
    check(0 < launch['wall_s'] < grant['whole_wall_s'], 'outer elapsed within scope')
    note = read(HERE / 'launch_registration/preparation_note.json')
    check(note['numeric_operations'] == 0 and all(note[k] is False for k in ('registration_created', 'grant_created', 'candidate_claim_created')), 'prelaunch shell edit error separately preserved')
    for name, before_pin in reg['before_documents'].items():
        check(sha(HERE / 'launch_registration/before_documents' / name) == before_pin, 'before snapshot ' + name)
    git = lambda *x: subprocess.check_output(['git', *x], cwd=ROOT).decode('utf8')
    check(git('branch', '--show-current').strip() == reg['branch'] and git('rev-parse', 'HEAD').strip() == reg['head'], 'branch and HEAD preserved')
    before = set((HERE / 'launch_registration/git_status_before.txt').read_text(encoding='utf8').splitlines())
    after = set(git('status', '--porcelain=v1').splitlines())
    check(not before - after, 'all earlier dirty entries preserved')
    if not args.runtime_only:
        review = read(HERE / 'review_resolution.json')
        check(review['status'] == 'RESOLVED' and review['open_critical'] == review['open_important'] == 0, 'independent review resolved')
        docs = read(HERE / 'document_update.json')
        for name in reg['before_documents']:
            check(sha(HERE / 'document_snapshots' / name) == docs['after_documents'][name], 'after snapshot ' + name)
            if args.current_docs:
                check(sha(ROOT / name) == docs['after_documents'][name], 'current document ' + name)
        qualification = read(HERE / 'numeric_qualification.json')
        check(qualification['stage_id'] == 'B2-SCOPE-18' and qualification['numeric_restore_verified'] is True, 'new separate numeric qualification')
        check(qualification['state_digest'] == state_hash and qualification['checkpoint_manifest_sha256'] == request['manifest_sha256'], 'qualification binds restored state')
        check(qualification['physical_resume_verified'] is False and qualification['training_admitted'] is False and qualification['formal_updates'] == 0, 'qualification remains component-only')
    for path in HERE.glob('*.py'):
        ast.parse(path.read_text(encoding='utf8'))
        checks += 1
    check(not any(k.split('.')[0] in ('numpy', 'torch', 'mujoco', 'stable_baselines3') for k in sys.modules), 'stdlib-only closeout')
    result = dict(stage_id='B2-SCOPE-18', status='VERIFIED_NUMERIC_RESTORE' if args.runtime_only else 'VERIFIED_NUMERIC_RESTORE_CLOSEOUT',
                  checks=checks, execution_status=closure['status'], actual_operations=counter['attempted'],
                  numeric_restore_verified=True, live_component_restore_verified=True, state_digest=state_hash,
                  physical_resume_verified=False, training_admitted=False, process_exit_confirmed=True,
                  old_sealed_members_preserved=3443, bound_inputs_preserved=2588, prior_offline_tests=70,
                  cumulative_dynamic=245, automatic_tracking='PAUSED', full_B2_accepted=False, C_accepted=False,
                  independent_tests=0, supervisor_wall_s=supervisors['supervisor']['wall_seconds'],
                  reader_wall_s=supervisors['reader']['wall_seconds'], no_retry=True)
    if args.seal:
        write(HERE / 'prior_verification.json', prior)
        write(HERE / 'verification.json', result)
        (HERE / 'git_status_after.txt').write_text(git('status', '--porcelain=v1'), encoding='utf8')
        files = {p.relative_to(HERE).as_posix(): dict(sha256=sha(p), bytes=p.stat().st_size)
                 for p in sorted(HERE.rglob('*')) if p.is_file() and p.name != 'delivery_manifest.json' and '__pycache__' not in p.parts}
        write(HERE / 'delivery_manifest.json', dict(stage_id='B2-SCOPE-18', files=files, rolling_documents_may_advance=True))
    if (HERE / 'delivery_manifest.json').exists():
        members = read(HERE / 'delivery_manifest.json')['files']
        for name, record in members.items():
            check(sha(HERE / name) == record['sha256'] and (HERE / name).stat().st_size == record['bytes'], 'sealed ' + name)
        result.update(checks=checks, sealed_files=len(members), manifest_sha256=sha(HERE / 'delivery_manifest.json'))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
