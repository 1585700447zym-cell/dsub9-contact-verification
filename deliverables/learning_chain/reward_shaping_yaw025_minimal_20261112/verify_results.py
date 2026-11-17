"""Verify bounded experiment evidence without additional physics or optimization."""
import importlib.util
from pathlib import Path
import sys

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path.insert(0,str(ROOT))


def main():
    spec=importlib.util.spec_from_file_location('reward_runner',OUT/'run_experiment.py')
    run=importlib.util.module_from_spec(spec);spec.loader.exec_module(run)
    ledger=run.read(OUT/'ledger.json');reg=run.verify(ledger['registration_sha256'])
    assert ledger['status']=='COMPLETED'
    assert len(ledger['attempts'])==8 and ledger['stage_initializations']==8
    assert ledger['unknown_cost_attempts']==0 and ledger['updates']==dict(A=101,B=101)
    assert ledger['cumulative_initializations']==reg['previous_initializations']+8
    for attempt in ledger['attempts']:
        assert attempt['status']=='AUDITED'
        folder=OUT/'run'/attempt['id']; proof=run.read(folder/'audit.json'); receipt=run.read(folder/'receipt.json')
        assert proof['verified'] and proof['source_replay_verified'] and receipt['valid'] and receipt['stopped']
        assert proof['archive_sha256']==receipt['archive_sha256']==run.sha(folder/'episode.json.gz')
        assert proof['experiment_registration_sha256']==ledger['registration_sha256']
        assert proof['experiment_intervention']['yaw']['verified']
        if attempt['split']=='train':
            admission=run.read(folder/'admission.json')
            assert admission['optimizer_updates']==0
            reward=run.read(OUT/'rewards'/(attempt['id']+'.json'))
            assert reward['archive_sha256']==proof['archive_sha256']
            assert reward['overlay_sha256']==run.sha(OUT/'rewards'/(attempt['id']+'.npz'))
            assert abs(reward['telescoping_residual'])<1e-10
    a,b=[run.read(OUT/f'optimization_{k}.json') for k in ('A','B')]
    assert a['initial_actor_sha256']==b['initial_actor_sha256']==reg['initial']['actor_sha256']
    assert a['source_checkpoint_sha256']==b['source_checkpoint_sha256']
    assert a['overlay_sha256']==b['overlay_sha256'] and a['replay_unchanged'] and b['replay_unchanged']
    assert len(a['batches'])==len(b['batches'])==len(a['updates'])==len(b['updates'])==101
    assert all(x['input_except_reward_sha256']==y['input_except_reward_sha256'] for x,y in zip(a['batches'],b['batches']))
    assert all(x['nonzero_reward_changes']==0 for x in a['batches'])
    assert sum(x['nonzero_reward_changes'] for x in b['batches'])>0
    for result in (a,b):
        path=OUT/result['path'];manifest=run.read(path/'manifest.json')
        assert run.sha(path/'manifest.json')==result['checkpoint_sha256']
        assert run.sha(path/'state.pt')==manifest['state_sha256']
    comparison=run.read(OUT/'review/comparison.json')
    assert len(comparison['results'])==4
    pins={p.relative_to(OUT).as_posix():run.sha(p) for p in OUT.rglob('*')
          if p.is_file() and p.name!='verification.json' and '__pycache__' not in p.parts and p.suffix not in ('.log','.pending')}
    run.write(OUT/'verification.json',dict(status='VERIFIED',verified=True,stage='B.2',development_only=True,
        stage_initializations=8,cumulative_initializations=ledger['cumulative_initializations'],native_steps=ledger['native_steps'],
        critic_updates=dict(A=101,B=101),replay_publications=4,paired_batches=101,
        original_replay_unchanged=True,successes=comparison['successes'],evidence_sha256=pins))
    print('VERIFIED',comparison['successes'],ledger['native_steps'])


if __name__=='__main__': main()
