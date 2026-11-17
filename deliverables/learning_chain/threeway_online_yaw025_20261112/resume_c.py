"""User-authorized single replacement attempt; C only, original physics/training."""
import argparse
import importlib.util
from pathlib import Path
import shutil
import sys

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('frozen_online_runner',BASE/'run_experiment.py')
run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
OUT=BASE/'resume_C'
AMENDMENT=BASE/'resume_authorization.json'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','launch','capture','audit','admit','optimize'])
    parser.add_argument('--pin');parser.add_argument('--request',type=Path);parser.add_argument('--request-pin')
    args=parser.parse_args()
    if args.action=='prepare':
        if AMENDMENT.exists() or OUT.exists(): raise FileExistsError('Resume already prepared')
        ledger=run.read(BASE/'ledger.json');reg=run.verify(ledger['registration_sha256'])
        assert ledger['status']=='INTERRUPTED_INCOMPLETE' and len(ledger['attempts'])==13
        assert ledger['updates']==dict(A=303,B=303)
        assert not (BASE/'run/C_T03/episode.json.gz').exists()
        OUT.mkdir()
        for name in ('run','requests','monitor','rewards','qualifications'): (OUT/name).mkdir()
        initial=reg['groups']['C']['initial']['path']
        shutil.copytree(BASE/initial,OUT/initial)
        run.write(AMENDMENT,dict(version='authorized_C_replacement_v1',approved_user_text='允许补采并完成 C 组',
            original_registration_sha256=ledger['registration_sha256'],resume_script_sha256=run.sha(Path(__file__)),
            prior_ledger_sha256=run.sha(BASE/'ledger.json'),interrupted_receipt_sha256=run.sha(BASE/'run/C_T03/receipt.json'),
            maximum_total_attempts=19,additional_replacement_attempts=1,remaining_C_attempts=6,
            retained_unknown_cost_attempts=1,created_utc=run.now()))
        print('RESUME PREPARED',ledger['registration_sha256']);return
    amendment=run.read(AMENDMENT)
    if (run.sha(Path(__file__))!=amendment['resume_script_sha256']
            or args.pin!=amendment['original_registration_sha256']
            or run.sha(BASE/'run/C_T03/receipt.json')!=amendment['interrupted_receipt_sha256']):
        raise ValueError('Resume authorization/evidence changed')
    reg=run.verify(args.pin)
    run.OUT=OUT
    run.__file__=str(Path(__file__).resolve())
    if args.action=='launch':
        if run.sha(BASE/'ledger.json')!=amendment['prior_ledger_sha256']: raise ValueError('Prior ledger changed')
        return run.launch(dict(reg,groups={'C':reg['groups']['C']}),args.pin)
    if run.sha(args.request)!=args.request_pin: raise ValueError('Resume request changed')
    request=run.read(args.request)
    if request['group']!='C': raise ValueError('Only C is authorized for resume')
    run.worker(reg,args.action,request)


if __name__=='__main__': main()
