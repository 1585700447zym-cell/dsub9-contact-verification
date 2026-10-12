"""Read-only verification of a crashed run; no physical or optimizer calls."""
import gzip
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from tools.learning.bounded_contact import DELIVERY,BoundedAdmission,current_sources
from tools.learning import bounded_checkpoint as cp
from tools.learning.admission import digest,verify_files
from tools.learning.admitted_collection import _write_json
from tools.learning.engineering_evaluation import episode_metrics
from tools.learning.bounded_cycle import cases


def main():
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    pin=read(DELIVERY/'admission_pin.json')['sha256']
    permit=BoundedAdmission(DELIVERY/'admission.json',expected_digest=pin)
    run=DELIVERY/'run';source_before=current_sources()
    checkpoint_pin=digest(run/'initial_checkpoint/manifest.json')
    state,components=cp.read_checkpoint(run/'initial_checkpoint',expected_digest=checkpoint_pin,admission=permit)
    assert all(v==0 for v in state['updater']['counts'].values()) and not state['archives']
    policy=components[0].fingerprints()['actor'];recomputed=[]
    archived=read(run/'initial/results.json')
    for case,row in zip(cases(),archived,strict=True):
        p=run/'initial/episodes'/case['name']/'episode.json.gz'
        raw=json.loads(gzip.decompress(p.read_bytes()));status=read(p.parent/'status.json')
        assert digest(p)==status['archive_sha256'] and raw['case']==case
        assert raw['policy_sha256']==policy and raw['optimizer_steps']==raw['optimizer_steps_start']==0
        cp._audit_physics(raw)
        actual=dict(case=case['name'],**episode_metrics(raw))
        assert actual==row;recomputed.append(actual)
    assert len(recomputed)==4 and all(r['success'] for r in recomputed)
    assert read(run/'initial/verification.json')['training_state_unchanged'] is True
    assert not (run/'training/checkpoints').exists() and not list((run/'training_episodes').glob('*/episode.json.gz'))
    assert not (run/'training_episodes/update_budget.json').exists()
    journal=read(run/'ledger.json');exit_report=read(run/'process_exit.json')
    assert journal['dynamic_starts']==5 and journal['status']=='failed'
    assert len(journal['attempts'])==5 and sum(r['status']=='finished' for r in journal['attempts'])==4
    assert exit_report['exit_code_signed']&0xffffffff==0xc0000005
    history=read(DELIVERY/'historical_files.json');verify_files(ROOT,history)
    assert source_before==current_sources()
    result=dict(version='bounded_cycle_interrupted_v1',stage_complete=False,policy_benefit_verified=False,
        execution_status='hard_stopped_process_crash',root_cause='not_determined',
        physical_starts=5,completed_initial_evaluations=4,initial_untrained_successes=4,
        initial_evaluation_wall_s=read(run/'initial/verification.json')['wall_s'],
        initial_evaluations=recomputed,training_starts=1,completed_training_episodes=0,
        formal_update_attempts=0,formal_updates=0,synthetic_update_batches=3,static_initializations=4,
        last_durable_training_cycles=1500,exact_crash_cycle_unknown=True,partial_trajectory_lost=True,
        remaining_planned_physical_starts_not_executed=27,independent_evaluation_started=False,
        same_initial_checkpoint_verified=True,initial_policy_state_unchanged=True,
        historical_files_unchanged=len(history),current_sources_unchanged=len(source_before),
        verification_physical_steps=0,verification_optimizer_batches=0,automatic_retry=False)
    _write_json(DELIVERY/'assessment.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='initial_evaluations'},ensure_ascii=False))


if __name__=='__main__':main()
