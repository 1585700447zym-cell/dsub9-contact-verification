"""Plan and interruption-safe accounting for the bounded A0/A2 comparison."""
from copy import deepcopy
from pathlib import Path
from .five_axis_contract import validate_config
from .five_axis_preparation import cases,read

ARMS=('A0','A2')


def arm_configs(base):
    configs={}
    for arm,alpha in [('A0',.01),('A2',.001)]:
        config=deepcopy(base)
        config['learning'].update(entropy_initial=alpha,replay_capacity=172000)
        configs[arm]=validate_config(config)
    return configs


def schedule():
    return [dict(id=f'{i+1:02d}_{"online" if i<8 else "development"}_{point["name"]}',
                 case=point,stage='online' if i<8 else 'development',
                 publish=i<8,updates_after=500 if i<8 else 0)
            for i,point in enumerate(cases()*3)]


def summarize_run(run):
    episodes=[]
    for arm in ARMS:
        for index,job in enumerate(schedule()):
            folder=Path(run)/arm/job['id']
            if not folder.exists():continue
            def optional(name):return read(folder/name) if (folder/name).exists() else {}
            receipt=optional('receipt.json');progress=optional('progress.json')
            result=optional('job_result.json');updates=optional('update_progress.json')
            supervisor=optional('supervisor.json')
            final=result.get('status') in ('FINISHED','ERROR') and supervisor.get('process_exit_confirmed',False)
            episodes.append(dict(arm=arm,index=index,job=job['id'],stage=job['stage'],
                status=result.get('status',receipt.get('status','STARTING')),
                initialization_attempts=max(receipt.get('reset_attempted',0),progress.get('reset_attempted',0)),
                physical_substeps=max(receipt.get('physical_substeps',0),progress.get('physical_substeps',0)),
                control_cycles=max(receipt.get('control_cycles',0),progress.get('cycles',0)),
                policy_calls=max(receipt.get('policy_calls',0),progress.get('policy_calls',0)),
                training_updates=max(result.get('actual_updates_for_job',0),updates.get('actual_updates_for_job',0)),
                attempted_updates=max(result.get('attempted_updates_for_job',0),updates.get('attempted_updates_for_job',0)),
                completed=result.get('status')=='FINISHED',counts_exact=bool(final),
                valid=receipt.get('valid'),stopped=receipt.get('stopped'),outcome=receipt.get('outcome'),
                final_reason=receipt.get('final_reason'),error=result.get('error'),
                process_exit_code=supervisor.get('returncode')))
    return dict(episodes=episodes,initialization_attempts=sum(e['initialization_attempts'] for e in episodes),
        cumulative_initializations=391+sum(e['initialization_attempts'] for e in episodes),
        physical_substeps=sum(e['physical_substeps'] for e in episodes),
        policy_calls=sum(e['policy_calls'] for e in episodes),
        training_updates=sum(e['training_updates'] for e in episodes),
        attempted_updates=sum(e['attempted_updates'] for e in episodes),
        updates_by_arm={a:sum(e['training_updates'] for e in episodes if e['arm']==a) for a in ARMS},
        completed_jobs=sum(e['completed'] for e in episodes),counts_exact=all(e['counts_exact'] for e in episodes),
        new_warmup_draws=0,shared_old_warmup_episodes=4)
