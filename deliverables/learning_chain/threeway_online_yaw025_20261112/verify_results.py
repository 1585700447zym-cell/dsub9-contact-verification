"""Verify online provenance, complete budget and final artifact bindings; no physics."""
import importlib.util
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))


def main():
    spec=importlib.util.spec_from_file_location('online_runner',OUT/'run_experiment.py')
    run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
    run.helper.select()
    from tools.learning.threeway_online import load
    from tools.learning.switchable_sac import tensor_digest
    ledger=run.read(OUT/'ledger.json');reg=run.verify(ledger['registration_sha256'])
    assert ledger['status']=='COMPLETED' and len(ledger['attempts'])==18
    assert len({r['id'] for r in ledger['attempts']})==18
    assert ledger['stage_initializations']==18 and ledger['unknown_cost_attempts']==0
    assert ledger['cumulative_initializations']==reg['previous_initializations']+18
    assert ledger['updates']==dict(A=303,B=303,C=303)
    assert ledger['update_costs']==dict(known_completed=dict(A=303,B=303,C=303),failed_attempts=0,unknown_in_progress=0)
    for attempt in ledger['attempts']:
        folder=OUT/'run'/attempt['id'];proof=run.read(folder/'audit.json');receipt=run.read(folder/'receipt.json')
        group=attempt['group'];settings=reg['groups'][group]
        job=next(j for j in settings['train']+settings['evaluate'] if j['episode_id']==attempt['id'])
        assert attempt['status']=='AUDITED' and proof['verified'] and proof['source_replay_verified']
        assert receipt['valid'] and receipt['stopped'] and receipt['reset_attempted']==1
        assert proof['archive_sha256']==receipt['archive_sha256']==run.sha(folder/'episode.json.gz')
        assert proof['registration_sha256']==ledger['registration_sha256']
        assert proof['experiment_intervention']['yaw']['verified']
        assert proof['policy_mode']==settings['config']['policy_mode']==job['policy_mode']
        assert proof['optimizer_updates']==job['required_updates']==attempt['source']['optimizer_updates']
        assert proof['source_checkpoint_sha256']==attempt['source']['checkpoint_sha256']
        if job['split']=='train':
            admitted=run.read(folder/'admission.json');reward=run.read(OUT/'rewards'/(attempt['id']+'.json'))
            assert admitted['optimizer_updates']==job['required_updates']
            assert admitted['proof']['archive_sha256']==proof['archive_sha256']
            assert admitted['proof']['qualification_sha256']==run.sha(OUT/'qualifications'/(group+'.json'))
            assert reward['archive_sha256']==proof['archive_sha256']
            assert reward['overlay_sha256']==run.sha(OUT/'rewards'/(attempt['id']+'.npz'))
            assert abs(reward['telescoping_residual'])<1e-10
    first_batches={};costs={}
    for group,settings in reg['groups'].items():
        for round_ in (1,2,3):
            result=run.read(OUT/(group+'_optimization_'+str(round_)+'.json'))
            assert result['optimizer_updates']==round_*101 and result['admitted_episodes']==round_+1
            assert len(result['batches'])==len(result['updates'])==101
            assert all(r['learning_rows']==256 for r in result['batches'])
            assert all(r['batch_rows']==256 for r in result['updates'])
            assert all(r['reward_scheme']==('original' if group=='A' else 'potential') for r in result['batches'])
            if group=='A': assert all(r['changed_learning_rewards']==0 for r in result['batches'])
            else: assert sum(r['changed_learning_rewards'] for r in result['batches'])>0
            restored=load(OUT/result['path'],config=settings['config'],expected_digest=result['checkpoint_sha256'],group=group)
            assert restored.optimizer_updates==round_*101
            assert tensor_digest(restored.actor.state_dict())==result['actor_sha256']
            assert [r['optimizer_updates'] for r in restored._training['episodes']]==[0,0,101,202][:round_+1]
            assert restored.online['registration_sha256']==ledger['registration_sha256']
            if round_==1: first_batches[group]=result['batches']
        costs[group]=dict(learning_rows=303*256,admitted_transitions=result['admitted_transitions'],
            actor_parameters=settings['actor_parameters'],optimizer_updates=303,
            capture_wall_s=sum(run.read(OUT/'run'/a['id']/'receipt.json')['elapsed_wall_s']
                               for a in ledger['attempts'] if a['group']==group))
    pairing=dict(same_initial_actor=reg['groups']['A']['initial']['actor_sha256']==reg['groups']['B']['initial']['actor_sha256'],
        initial_round_matching_learning_batches=sum(x['learning_inputs_sha256']==y['learning_inputs_sha256']
            for x,y in zip(first_batches['A'],first_batches['B'])),
        note='Only initial zero-update collections can be identical; subsequent own-policy trajectories should be allowed to differ.')
    assert pairing['same_initial_actor']
    comparison=run.read(OUT/'review/comparison.json');assert len(comparison['results'])==6
    run.write(OUT/'cost_comparison.json',dict(groups=costs,pairing=pairing))
    pins={p.relative_to(OUT).as_posix():run.sha(p) for p in OUT.rglob('*')
          if p.is_file() and p.name!='verification.json' and '__pycache__' not in p.parts and p.suffix not in ('.log','.pending')}
    run.write(OUT/'verification.json',dict(verified=True,status='VERIFIED',development_only=True,
        registration_sha256=ledger['registration_sha256'],stage_initializations=18,cumulative_initializations=ledger['cumulative_initializations'],
        native_steps=ledger['native_steps'],critic_updates=ledger['updates'],replay_publications=12,
        learning_rows_per_group=77568,pairing=pairing,successes=comparison['successes'],evidence_sha256=pins))
    print('VERIFIED',comparison['successes'],ledger['native_steps'],pairing)


if __name__=='__main__': main()
