"""Explicit authorization first, then qualified runtime and exclusive supervised execution."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
from tools.learning.actor_lr_contract import (ROOT,DELIVERY,verify_candidate,require_authorization,read,digest)


class UnconfirmedWorkerStop(RuntimeError):pass


def ensure_live_ancestor(record):
    from tools.validation.process_parent import windows_process,same_image
    with windows_process(record['supervisor_pid']) as process:
        if (process['alive'] is not True or process['created_at']>record['wall_timestamp'] or
            not same_image(process['image'],sys._base_executable)):
            raise RuntimeError('Registered ancestor supervisor is stale or stopped')


def execution_guard(folder):
    from tools.validation.process_parent import require_registered_parent
    folder=Path(folder);record=read(folder/'started.json')
    ancestor=None if folder==DELIVERY else read(DELIVERY/'started.json')
    def check():
        if any(path.exists() for path in (folder/'stop_requested.json',DELIVERY/'stop_requested.json',
            DELIVERY/'run/supervision_uncertain.json')):raise RuntimeError('Supervisor requested stop; no further computation')
        require_registered_parent(record['supervisor_pid'],record['wall_timestamp'])
        if ancestor is not None:ensure_live_ancestor(ancestor)
    return check


def select_qualified_runtime():
    from tools.learning.runtime import select_runtime,active_package,verify_runtime
    repaired=ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928'
    select_runtime(repaired/'runtime.json',expected_digest=read(repaired/'admission.json')['runtime_record_sha256'])
    verify_runtime(active_package())


def child_command(candidate_pin,authorization_pin,branch=None):
    result=[sys.executable,'-X','utf8','-X','faulthandler','-B','-m','tools.validation.run_actor_lr_comparison',
        '--candidate-sha256',candidate_pin,'--authorization-sha256',authorization_pin]
    return result+(['--worker'] if branch is None else ['--evaluate',branch])


def claim(folder):
    from tools.learning.sac_checkpoint import _flush_write
    _flush_write(Path(folder)/'claim.json',json.dumps(dict(pid=os.getpid(),parent_pid=os.getppid(),wall_timestamp=time.time())))


def require_parent(folder):
    from tools.validation.process_parent import require_registered_parent
    record=read(Path(folder)/'started.json')
    require_registered_parent(record['supervisor_pid'],record['wall_timestamp'])


def supervise(command,folder):
    # Reuse only the frozen process-lifetime helper, never its experiment entry.
    source=ROOT/'deliverables/learning_chain/b2_bounded_cycle_20260927/retry_01/driver.py'
    spec=importlib.util.spec_from_file_location('actor_lr_frozen_supervisor',source)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    from tools.learning.admitted_collection import _write_json
    helper.write=_write_json
    try:return helper.supervise(command,folder,ROOT)
    except FileExistsError:raise
    except BaseException as exc:
        folder=Path(folder);path=folder/'process_exit.json'
        receipt=read(path) if path.exists() else {}
        if receipt.get('status')!='supervisor_error' or receipt.get('worker_stopped') is not True or receipt.get('cleanup_error') is not None:
            _write_json(folder/'stop_requested.json',dict(error=repr(exc),worker_stop_confirmed=False,process_exit=receipt))
            raise UnconfirmedWorkerStop('Worker tree stop was not confirmed: '+repr(exc)) from exc
        raise


def finalize_failure(candidate_pin,authorization_pin,error):
    from tools.learning.actor_lr_budget import ComparisonLedger
    from tools.learning.admitted_collection import _write_json as write
    run=DELIVERY/'run'
    process=read(DELIVERY/'process_exit.json') if (DELIVERY/'process_exit.json').exists() else {}
    uncertain=(DELIVERY/'stop_requested.json').exists() or (run/'supervision_uncertain.json').exists() or (
        process.get('status')=='supervisor_error' and (process.get('worker_stopped') is not True or process.get('cleanup_error') is not None))
    if uncertain:
        write(DELIVERY/'stop_requested.json',dict(error=str(error),worker_stop_confirmed=False))
        write(DELIVERY/'exit_classification.json',dict(execution_complete=False,error=str(error),retry_allowed=False,
            worker_stop_confirmed=False,ledger_preserved_pending_process_confirmation=True,b2_complete=False))
        return
    if (run/'ledger.json').exists():
        ledger=ComparisonLedger.load(run/'ledger.json',candidate_pin,authorization_pin)
        ledger.fail(error);write(run/'accounting.json',ledger.accounting())
    write(DELIVERY/'exit_classification.json',dict(execution_complete=False,error=str(error),retry_allowed=False,
        worker_stop_confirmed=True,b2_complete=False))


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--candidate-sha256',required=True)
    parser.add_argument('--authorization-sha256')
    modes=parser.add_mutually_exclusive_group();modes.add_argument('--verify-only',action='store_true')
    modes.add_argument('--worker',action='store_true');modes.add_argument('--evaluate',choices=('A','B'))
    args=parser.parse_args(argv)
    if args.verify_only:
        verify_candidate(args.candidate_sha256,check_runtime=False)
        print('Protocol preparation verified; real computation is not authorized.');return 0
    # This gate precedes runtime imports, constructors, claims and reservations.
    require_authorization(args.candidate_sha256,args.authorization_sha256)
    select_qualified_runtime();verify_candidate(args.candidate_sha256)
    if args.worker or args.evaluate:
        folder=DELIVERY if args.worker else DELIVERY/'run'/('eval_process_'+args.evaluate)
        require_parent(folder);claim(folder)
        if os.name=='nt':
            import ctypes
            ctypes.windll.kernel32.SetErrorMode(0x0002)
        from tools.learning.actor_lr_execution import execute_worker,evaluate_worker
        if args.worker:return execute_worker(args.candidate_sha256,args.authorization_sha256)
        return evaluate_worker(args.candidate_sha256,args.authorization_sha256,args.evaluate)
    try:
        code=supervise(child_command(args.candidate_sha256,args.authorization_sha256),DELIVERY)
        from tools.learning.actor_lr_budget import ComparisonLedger
        ledger=ComparisonLedger.load(DELIVERY/'run/ledger.json',args.candidate_sha256,args.authorization_sha256)
        from tools.learning.admitted_collection import _write_json as write
        complete=code==0 and ledger.state['status']=='complete' and (DELIVERY/'run/completed.json').exists()
        controlled=code==20 and ledger.state['status']=='stopped'
        if not complete and not controlled:raise RuntimeError('Supervised comparison failed or incomplete: '+str(code))
        write(DELIVERY/'exit_classification.json',dict(execution_complete=complete,controlled_stop=controlled,
            returncode=code,retry_allowed=False,b2_complete=False,accounting=ledger.accounting()))
        return code
    except FileExistsError:raise
    except BaseException as exc:
        finalize_failure(args.candidate_sha256,args.authorization_sha256,repr(exc));raise


if __name__=='__main__':raise SystemExit(main())
