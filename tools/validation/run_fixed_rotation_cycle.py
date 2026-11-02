"""One authorized fixed-rotation cycle, supervised, no automatic restart."""
import argparse
import ctypes
import gzip
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from tools.learning.fixed_rotation_cycle import (DELIVERY,OLD,ROOT,FixedAdmission,FixedLedger,
    accounting,read,reuse_baseline)
from tools.learning.repaired_cycle import verify_initial_chain,development_decision
from tools.learning.admitted_collection import _write_json as write

RUN=DELIVERY/'run'


def claim(name):
    with (DELIVERY/(name+'_claim.json')).open('x',encoding='utf-8') as stream:
        json.dump(dict(pid=os.getpid(),parent_pid=os.getppid(),wall_timestamp=time.time()),stream)


def worker(permit,restore=False):
    ctypes.windll.kernel32.SetErrorMode(0x0002)  # fatal native error exits instead of waiting on a dialog
    claim('restore' if restore else 'worker')
    from tools.learning import bounded_checkpoint as cp
    from tools.learning.bounded_contact import BoundedCollection
    from tools.learning.bounded_cycle import train,evaluate,cases,same_physical_result,holdout_scope_gate,compare_success,progress
    ledger=None;chain=None
    try:
        if restore:
            frozen=read(RUN/'frozen.json')
            chain=cp.load_checkpoint(RUN/frozen['path'],expected_digest=frozen['sha256'],
                admission=permit,output=RUN/'restored_training_state')
            ledger=FixedLedger(RUN/'ledger.json')
            evaluate(chain,'restored',ledger=ledger,output=RUN/'restored',checkpoint_sha256=frozen['sha256'])
            for case in cases():
                a=json.loads(gzip.decompress((RUN/'final/episodes'/case['name']/'episode.json.gz').read_bytes()))
                b=json.loads(gzip.decompress((RUN/'restored/episodes'/case['name']/'episode.json.gz').read_bytes()))
                if not same_physical_result(a,b):raise RuntimeError('Restored physical trajectory differs')
            write(RUN/'restoration.json',dict(exact_physical_replay=True,independent_performance_samples_added=0))
            return
        RUN.mkdir(exist_ok=False);ledger=FixedLedger(RUN/'ledger.json')
        chain=BoundedCollection(admission=permit,output=RUN/'training_episodes')
        write(RUN/'initial_state_identity.json',verify_initial_chain(chain))
        initial_pin=cp.save_checkpoint(chain,RUN/'initial_checkpoint')
        reuse_baseline(RUN)
        evaluate(chain,'initial',ledger=ledger,output=RUN/'initial',checkpoint_sha256=initial_pin)
        final=train(chain,ledger=ledger,output=RUN/'training');write(RUN/'frozen.json',final)
        evaluate(chain,'final',ledger=ledger,output=RUN/'final',checkpoint_sha256=final['sha256'])
        print(json.dumps(dict(stage='development_decision',**development_decision(RUN))),flush=True)
        command=[sys.executable,'-X','utf8','-X','faulthandler','-B','-m',
            'tools.validation.run_fixed_rotation_cycle','--admission-sha256',permit.expected_digest,'--restore']
        with (RUN/'restore_process.log').open('x',encoding='utf-8') as log:
            result=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        ledger=FixedLedger(RUN/'ledger.json')
        if result.returncode:raise RuntimeError('Separate restoration failed: '+str(result.returncode))
        evaluate(chain,'holdout_b2',ledger=ledger,output=RUN/'holdout_b2',checkpoint_sha256=final['sha256'])
        holdout_scope_gate(RUN,permit)
        evaluate(chain,'holdout_sac',ledger=ledger,output=RUN/'holdout_sac',checkpoint_sha256=final['sha256'])
        independent=compare_success(read(RUN/'holdout_b2/results.json'),read(RUN/'holdout_sac/results.json'))
        permit.verify()
        write(RUN/'completed.json',dict(status='execution_complete',**accounting(ledger.state),
            formal_updates=chain.updater.counts,independent=independent,checkpoint=final,
            action_scale=permit.config['action']['scale'],baseline_reused=True))
        progress(RUN/'progress.json',stage='completed',independent=independent)
    except BaseException as exc:
        if chain is not None:chain.fail(exc)
        if ledger is not None:ledger.fail(repr(exc))
        write(RUN/'failure.json',dict(error=repr(exc)))
        progress(RUN/'progress.json',stage='failed',error=repr(exc));raise
    finally:
        if ledger is not None:write(RUN/'cumulative_budget.json',accounting(ledger.state))


def main():
    p=argparse.ArgumentParser();p.add_argument('--admission-sha256',required=True)
    modes=p.add_mutually_exclusive_group()
    for name in ('worker','restore','verify-only'):modes.add_argument('--'+name,action='store_true')
    args=p.parse_args()
    permit=FixedAdmission(DELIVERY/'admission.json',expected_digest=args.admission_sha256)
    if args.verify_only:
        print('Fixed rotation qualification verified; no physics or optimization.');return 0
    if args.worker or args.restore:
        worker(permit,restore=args.restore);return 0
    # Reuse the already tested, hash-bound supervisor; no changes to its cleanup semantics.
    source=OLD/'retry_01/driver.py'
    spec=importlib.util.spec_from_file_location('frozen_retry_supervisor',source)
    supervisor=importlib.util.module_from_spec(spec);spec.loader.exec_module(supervisor)
    command=[sys.executable,'-X','utf8','-X','faulthandler','-B','-m',
        'tools.validation.run_fixed_rotation_cycle','--admission-sha256',args.admission_sha256,'--worker']
    try:
        code=supervisor.supervise(command,DELIVERY,ROOT)
    except FileExistsError:
        raise
    except BaseException:
        code=1
    if code and (RUN/'ledger.json').exists():
        state=read(RUN/'ledger.json');state.update(status='failed',error='Worker exit '+hex(code & 0xffffffff))
        if state['active'] is not None:
            state['attempts'][state['active']].update(status='interrupted_by_process_exit',valid_for_learning=False)
        write(RUN/'ledger.json',state);write(RUN/'cumulative_budget.json',accounting(state))
        write(RUN/'progress.json',dict(stage='failed',error=state['error'],wall_timestamp=time.time()))
        write(RUN/'failure.json',dict(error=state['error'],process_exit=read(DELIVERY/'process_exit.json')))
    return 1 if code else 0


if __name__=='__main__':raise SystemExit(main())
