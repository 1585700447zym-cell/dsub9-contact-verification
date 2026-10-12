"""Once-only standalone restore verification; never a physical/training runner."""
from pathlib import Path
import argparse,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
from gate_contract import Counter,verify_grant,WHOLE_WALL_S,LIMITS
from joint_contract import read,write,sha,canonical
from supervised import bounded_process

def finalize_execution(folder,counter,status):
    receipt={};receipt_error=None;counter_error=None;counter_closed=False
    try:
        if (folder/'supervisor.supervisor.json').exists():receipt=read(folder/'supervisor.supervisor.json')
    except BaseException as exc:receipt_error=repr(exc)
    exited=receipt.get('process_exit_confirmed') is True and receipt.get('owned_launcher_exit_confirmed') is True
    if not exited:status='CLOSED_ERROR'
    try:
        if counter is not None:counter.close(owned_exit_confirmed=exited);counter_closed=True
    except BaseException as exc:counter_error=repr(exc);status='CLOSED_ERROR'
    # This receipt independently revokes the grant even if the counter cannot be closed.
    write(folder/'authorization_closure.json',dict(status=status,unused_closed=True,no_retry=True,
        process_exit_confirmed=exited,counter_closed=counter_closed,counter_error=counter_error,receipt_error=receipt_error,
        training_admitted=False,cumulative_dynamic=245,automatic_tracking='PAUSED'))
    return status

def main():
    p=argparse.ArgumentParser();p.add_argument('--grant',required=True);p.add_argument('--grant-sha',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    candidate=read(OUT/'candidate.json');grant=read(a.grant);binding_pin=sha(OUT/'source_binding.json')
    verify_grant(candidate,grant,a.grant_sha,binding_pin)
    for name,pin in candidate['code_sha256'].items():
        if sha(OUT/name)!=pin:raise ValueError('Runner code changed '+name)
    folder=Path(a.output).resolve()
    if folder.parent!=(ROOT/'deliverables/learning_chain').resolve() or folder.exists():raise ValueError('Fresh direct stage output required')
    claim=OUT/'future_claims/consumed.json';claim.parent.mkdir(exist_ok=True)
    with claim.open('x',encoding='utf8') as f:f.write(canonical(dict(grant_sha256=a.grant_sha,output=str(folder))))
    status='CLOSED_ERROR';counter=None
    try:
        folder.mkdir();write(folder/'grant.json',grant);write(folder/'grant_pin.json',dict(sha256=a.grant_sha));counter=Counter.create(folder/'counter.json')
        binding=read(OUT/'source_binding.json')
        bounded_process([binding['executable'],'-I','-X','utf8','-B',str(OUT/'gate_worker.py'),'parent',str(folder)],folder/'supervisor',WHOLE_WALL_S)
        if read(folder/'assessment.json').get('verified') is not True:raise ValueError('Incomplete numeric assessment')
        counter.require_complete()
        status='CLOSED_COMPLETE'
    finally:
        status=finalize_execution(folder,counter,status)
    print(canonical(dict(status=status,output=str(folder),training_admitted=False)))

if __name__=='__main__':main()
