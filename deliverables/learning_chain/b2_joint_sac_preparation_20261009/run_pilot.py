"""Check-only by default. A new explicit grant is required for the supervised worker."""
from pathlib import Path
import argparse
import shutil
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from joint_contract import ROOT,LIMITS,read,write,sha,digest
from execution import verify_grant,verify_sources,Counter
REGISTERED=Path('D:/dsub9项目计划/first_stage_sim/.worktrees/dsub9-v1-contact-validation/deliverables/learning_chain/b2_joint_sac_preparation_20261009').resolve()


def main():
    p=argparse.ArgumentParser();p.add_argument('--grant');p.add_argument('--grant-sha');p.add_argument('--output');args=p.parse_args()
    if OUT!=REGISTERED:raise PermissionError('Relocated candidate cannot create another claim store')
    binding=read(OUT/'source_binding.json');candidate=read(OUT/'candidate.json')
    if not args.grant:
        verify_sources(binding);print('CHECK_ONLY; training_admitted=false; no runtime imports');return
    grant=read(args.grant);verify_grant(candidate,grant,args.grant_sha,sha(OUT/'source_binding.json'))
    if not args.output:raise ValueError('New output required')
    folder=Path(args.output).resolve()
    if not folder.is_relative_to(ROOT) or folder.is_relative_to(OUT) or folder==ROOT or folder.exists():raise ValueError('New execution directory under worktree required')
    verify_sources(binding)
    claim=OUT/'future_claims';claim.mkdir(exist_ok=False) # One scope; no retry, even after setup failure.
    write(claim/'consumed.json',dict(grant_sha256=args.grant_sha,output=str(folder),retry_allowed=False))
    folder.mkdir(parents=True);(folder/'run').mkdir()
    write(folder/'grant.json',grant);write(folder/'grant_pin.json',dict(sha256=args.grant_sha))
    for name in ('configuration.json','model.xml'):shutil.copyfile(OUT/name,folder/name)
    keys=('dynamic_episodes','environment_creations','resets','control_cycles','native_steps','observations','formal_updates','policy_calls','learner_constructions','tensor_loads','checkpoint_saves','replay_publications')
    counter=Counter.create(folder/'counter.json',{k:LIMITS[k] for k in keys})
    status='CLOSED_ERROR'
    try:
        from supervised import bounded_process
        bounded_process([binding['executable'],'-I','-X','utf8','-B',str(OUT/'pilot_worker.py'),'parent',str(folder),'main'],
            folder/'supervisor',LIMITS['whole_wall_s'],phase_file=folder/'phase_deadline.json')
        status=read(folder/'run/ledger.json')['status']
        if status!='CLOSED_COMPLETE':raise RuntimeError('Worker did not complete; no retry')
    finally:
        counter.close()
        ledger_path=folder/'run/ledger.json'
        if ledger_path.exists():
            ledger=read(ledger_path);ledger.update(status=status,training_admitted=False,unused_closed=True);write(ledger_path,ledger)
        supervisor=read(folder/'supervisor.supervisor.json') if (folder/'supervisor.supervisor.json').exists() else {}
        write(folder/'authorization_closure.json',dict(status=status,grant_sha256=args.grant_sha,
            no_retry=True,unused_closed=True,automatic_tracking='PAUSED',cumulative_before=237,
            process_exit_confirmed=supervisor.get('process_exit_confirmed',False),
            cumulative_upper_bound=237+read(folder/'counter.json')['attempted']['dynamic_episodes']))


if __name__=='__main__':main()
