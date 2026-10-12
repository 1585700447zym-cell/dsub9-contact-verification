"""Four-attempt entry; authorization and owned GO precede scientific imports."""
import argparse
import importlib.abc
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(OUT))
from contract import ROOT, LIMITS, read, write, sha, now, helper, require_grant, verify_binding, next_case


def supervise(command, base, timeout, *, job_factory=None, popen=None):
    """Reuse the qualified launcher/native ownership and externally timed GO gate."""
    module = helper('supervised')
    original = module.subprocess.Popen
    if popen is not None: module.subprocess.Popen = popen
    try:
        options = {} if job_factory is None else dict(job_factory=job_factory)
        return module.bounded_process(command, base, timeout, **options)
    finally: module.subprocess.Popen = original


def collect_receipt(ledger, run):
    path = run / 'receipt.json'
    if path.exists():
        receipt = read(path)
        if receipt['case_id'] != ledger['episodes'][-1]['case_id']:
            raise ValueError('Final receipt does not belong to the claimed attempt')
        ledger['episodes'][-1] = dict(receipt, receipt_path=str(path), receipt_sha256=sha(path))
    supervisor = run / 'gate.supervisor.json'
    if supervisor.exists():
        ledger['episodes'][-1]['supervisor'] = read(supervisor)


class NoLearning(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if (fullname.split('.')[0] in ('torch', 'stable_baselines3') or
                fullname in ('tools.learning.v4_sac', 'tools.learning.sac_update',
                             'tools.learning.v4_checkpoint', 'tools.learning.sac_checkpoint')):
            raise PermissionError('Learned runtime is forbidden in the pure B2 worker: ' + fullname)


def checked_grant(args):
    if not args.grant or not args.grant_pin or not args.run_id:
        raise PermissionError('A separately bound explicit four-B2 grant is required before scientific imports')
    if sha(args.grant) != args.grant_pin: raise PermissionError('New grant pin differs')
    grant = read(args.grant)
    require_grant(grant, sha(OUT / 'source_binding.json'), args.run_id)
    binding, config = verify_binding()
    return grant, binding, config


def worker(args):
    grant, binding, config = checked_grant(args)
    execution = OUT / 'execution'; run = execution / ('case_' + str(args.case_index))
    launch = read(run / 'launch.json')
    if (launch['run_id'] != args.run_id or launch['nonce'] != args.nonce or
            launch['case_index'] != args.case_index or not 0 <= args.case_index < 4):
        raise PermissionError('Worker launch identity differs')
    if not args.gate or Path(args.gate).resolve() != (run / 'gate').resolve():
        raise PermissionError('Registered gate does not belong to this claimed attempt')
    helper('supervised').enter_gate(args.gate, args.parent_pid, args.registered_at)
    ledger = read(execution / 'ledger.json')
    if ledger['status'] != 'RUNNING' or len(ledger['episodes']) != args.case_index + 1:
        raise PermissionError('Physical attempt is not exclusively claimed')
    verify_binding(); sys.meta_path.insert(0, NoLearning()); sys.path.insert(0, str(ROOT))
    from baseline_rollout import physical_case
    receipt = dict(case_id=config['cases'][args.case_index]['id'], status='running', healthy=False,
                   environment_creation_attempted=0, environment_created=0,
                   reset_attempted=0, reset_completed=0, policy_calls=0, formal_updates=0)
    physical_case(config, config['cases'][args.case_index], args.case_index, run, receipt, binding)


def execute(args):
    grant, binding, config = checked_grant(args)
    if os.name != 'nt': raise OSError('Existing Windows job supervision is required')
    execution = OUT / 'execution'; execution.mkdir(exist_ok=False)
    ledger = dict(version='pure_b2_ledger_v1', run_id=args.run_id, grant_sha256=args.grant_pin,
                  status='RUNNING', episodes=[], limits=LIMITS, policy_calls=0, formal_updates=0,
                  cumulative_before=254, independent_tests=0, started_at=now())
    write(execution / 'ledger.json', ledger); started = time.monotonic()
    try:
        for index, point in enumerate(config['cases']):
            verify_binding()
            if next_case(ledger['episodes'], config['cases']) != point: break
            if time.monotonic() - started >= LIMITS['whole_wall_s']: raise TimeoutError('Whole-package deadline')
            run = execution / ('case_' + str(index)); run.mkdir(exist_ok=False)
            nonce = uuid.uuid4().hex
            ledger['episodes'].append(dict(case_id=point['id'], status='claimed', healthy=False))
            write(execution / 'ledger.json', ledger)
            write(run / 'launch.json', dict(run_id=args.run_id, nonce=nonce, case_index=index))
            command = [binding['executable'], '-I', '-X', 'utf8', '-X', 'faulthandler', '-B',
                       str(OUT / 'baseline_entry.py'), '--worker', '--case-index', str(index),
                       '--grant', str(Path(args.grant).resolve()), '--grant-pin', args.grant_pin,
                       '--run-id', args.run_id, '--nonce', nonce]
            timeout = min(LIMITS['per_episode_wall_s'], started + LIMITS['whole_wall_s'] - time.monotonic())
            if timeout <= 0: raise TimeoutError('Whole-package deadline before supervised launch')
            try: supervise(command, run / 'gate', timeout)
            finally:
                collect_receipt(ledger, run)
                write(execution / 'ledger.json', ledger)
            if ledger['episodes'][-1]['status'] != 'finished':
                raise RuntimeError('Worker lacks a completed physical receipt; no retry')
            if not ledger['episodes'][-1]['healthy']: break
        verify_binding()
        ledger['status'] = 'CLOSED_COMPLETE' if len(ledger['episodes']) == 4 and all(
            row.get('healthy') is True for row in ledger['episodes']) else 'CLOSED_EARLY'
    except BaseException as exc:
        ledger.update(status='CLOSED_ERROR', error=repr(exc))
        raise
    finally:
        ledger.update(ended_at=now(), unused_closed=4-len(ledger['episodes']),
                      claimed_attempts=len(ledger['episodes']), new_budget_reusable=False)
        write(execution / 'ledger.json', ledger)
        write(execution / 'authorization_closure.json', dict(status=ledger['status'],
              grant_sha256=args.grant_pin, claimed_attempts=len(ledger['episodes']),
              unused_closed=ledger['unused_closed'], no_retry=True, automatic_tracking='PAUSED'))


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check', action='store_true'); mode.add_argument('--execute', action='store_true')
    mode.add_argument('--worker', action='store_true')
    parser.add_argument('--grant'); parser.add_argument('--grant-pin'); parser.add_argument('--run-id')
    parser.add_argument('--case-index', type=int); parser.add_argument('--nonce')
    parser.add_argument('gate', nargs='?'); parser.add_argument('parent_pid', nargs='?', type=int)
    parser.add_argument('registered_at', nargs='?', type=float)
    args = parser.parse_args()
    if args.check:
        _, config = verify_binding()
        print(json.dumps(dict(source_binding_verified=True, case_ids=[p['id'] for p in config['cases']],
                              scientific_execution_admitted=False, training_admitted=False)))
    elif args.worker: worker(args)
    else: execute(args)


if __name__ == '__main__':
    main()
