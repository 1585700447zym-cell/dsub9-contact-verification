"""Read-only check by default; standalone once-only continuation after a new grant."""
import argparse, shutil, sys
from pathlib import Path
OUT = Path(__file__).resolve().parent; ROOT = OUT.parents[2]; sys.path.insert(0, str(OUT))
from joint_contract import LIMITS, read, write, sha, canonical
from execution import verify_grant, verify_sources, verify_code, Counter, COST_KEYS
REGISTERED = ROOT / 'deliverables/learning_chain/b2_joint_sac_continuation_preparation_20261009'

def finalize(folder, counter, status):
    receipt = {}; receipt_error = None; counter_error = None; closed = False
    try:
        if (folder / 'supervisor.supervisor.json').exists(): receipt = read(folder / 'supervisor.supervisor.json')
    except BaseException as exc: receipt_error = repr(exc)
    exited = receipt.get('process_exit_confirmed') is True and receipt.get('owned_launcher_exit_confirmed') is True
    if not exited: status = 'CLOSED_ERROR'
    try:
        if counter is not None: counter.close(owned_exit_confirmed=exited); closed = True
    except BaseException as exc: counter_error = repr(exc); status = 'CLOSED_ERROR'
    write(folder / 'authorization_closure.json', dict(status=status, no_retry=True, unused_closed=True, counter_closed=closed,
          counter_error=counter_error, receipt_error=receipt_error, process_exit_confirmed=exited, training_admitted=False,
          automatic_tracking='PAUSED', cumulative_before=245,
          cumulative_upper_bound=245 + (read(folder / 'counter.json')['attempted']['dynamic_episodes'] if closed else 9)))
    return status

def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--grant'); parser.add_argument('--grant-sha'); parser.add_argument('--output'); args = parser.parse_args()
    if OUT != REGISTERED.resolve(): raise PermissionError('Relocated candidate refused')
    binding = read(OUT / 'source_binding.json'); candidate = read(OUT / 'candidate.json')
    if args.grant is None:
        verify_code(candidate); verify_sources(binding); print('CHECK_ONLY; training_admitted=false; no numeric imports'); return
    grant = read(args.grant); verify_grant(candidate, grant, args.grant_sha, sha(OUT / 'source_binding.json')); verify_code(candidate); verify_sources(binding)
    if not args.output: raise ValueError('Fresh output required')
    folder = Path(args.output).resolve()
    if folder.parent != (ROOT / 'deliverables/learning_chain').resolve() or folder.exists(): raise ValueError('Fresh direct stage output required')
    claim = OUT / 'future_claims/consumed.json'; claim.parent.mkdir(exist_ok=True)
    with claim.open('x', encoding='utf8') as f: f.write(canonical(dict(grant_sha256=args.grant_sha, output=str(folder))))
    status = 'CLOSED_ERROR'; counter = None
    try:
        folder.mkdir(); (folder / 'run').mkdir(); write(folder / 'grant.json', grant); write(folder / 'grant_pin.json', dict(sha256=args.grant_sha))
        for name in ('configuration.json', 'model.xml'): shutil.copyfile(OUT / name, folder / name)
        counter = Counter.create(folder / 'counter.json', {k: LIMITS[k] for k in COST_KEYS})
        from supervised import bounded_process
        bounded_process([binding['executable'], '-I', '-X', 'utf8', '-B', str(OUT / 'pilot_worker.py'), 'parent', str(folder), 'main'],
                        folder / 'supervisor', LIMITS['whole_wall_s'], phase_file=folder / 'phase_deadline.json')
        ledger = read(folder / 'run/ledger.json')
        if (ledger['status'] != 'CLOSED_COMPLETE' or not ledger.get('warm_state_restore_verified') or
            ledger['formal_updates']['critic'] != 2000 or len(ledger['episodes']) != 9): raise ValueError('Incomplete continuation')
        costs=counter.checked()
        if costs['attempted']!=costs['limits']:raise ValueError('Incomplete registered operation ledger')
        verify_sources(binding); status = 'CLOSED_COMPLETE'
    finally: status = finalize(folder, counter, status)
    if status != 'CLOSED_COMPLETE': raise RuntimeError('Continuation failed and closed; no retry')
    print(canonical(dict(status=status, training_admitted=False, output=str(folder))))

if __name__ == '__main__': main()
