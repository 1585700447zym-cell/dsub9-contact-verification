"""Synthetic reporting tests: never load a checkpoint or initialize physics."""
from copy import deepcopy
import json
import math

import pytest

from tools.validation.analyze_load_warning_pilot import (
    analyze_batch, normalize_episode as _normalize_episode, read_receipt, summarize_records, write_reports,
)


def expected(spec):
    return dict(checkpoint_sha256=('a' if spec['policy_mode']=='mlp' else 'b')*64, optimizer_updates=128)


def normalize_episode(spec,*args,**kwargs):
    kwargs.setdefault('expected_checkpoint',expected(spec))
    return _normalize_episode(spec,*args,**kwargs)


def job(mode, pair):
    return dict(episode_id=mode+'_'+pair, policy_mode=mode, pair_id=pair,
                case=dict(name=pair, yaw_rad=-.02 if pair=='negative' else .02),
                seed=100 if pair=='negative' else 101, exploration_seed=222,
                deterministic=True, split='dev_eval')


def evidence(spec, *, success=True, seconds=12., force=2.):
    digest=('a' if spec['policy_mode']=='mlp' else 'b')*64
    outcome='FULL_SUCCESS' if success else 'CONTACT_GUARD'
    receipt=dict(spec, status='finished', valid=True, stopped=True, outcome=outcome,
                 final_reason='GEOMETRIC_SUCCESS' if success else 'TORQUE_LIMIT',
                 archive_sha256='c'*64, source_checkpoint_sha256=digest,
                 experiment=dict(policy_mode=spec['policy_mode'], optimizer_updates=128), training_updates=0,
                 task_end_time_s=seconds, stop_time_s=seconds-.1)
    warning=dict(over_duration_s=.002, longest_continuous_s=.001, peak=force)
    task=dict(duration_s=seconds, integral_force_Ns=force*seconds,
              square_integral_force_N2s=force*force*seconds,
              mean_force_N=force, rms_force_N=force,
              warnings=dict(FORCE_GT5_N=warning, FORCE_GT6_N=dict(warning,over_duration_s=0.,longest_continuous_s=0.),
                            ROTATION_GT2P5_DEG=dict(warning,peak=.05)))
    audit=dict(verified=True, task_outcome=outcome, episode_id=spec['episode_id'],
               policy_mode=spec['policy_mode'], archive_sha256='c'*64,
               source_checkpoint_sha256=digest, optimizer_updates=128,
               stop=dict(decision_time_s=seconds-.1,end_time_s=seconds+1.9),
               load_warnings=dict(verified=True, peak_force_N=99.,
                                  exposure=dict(task=task,audit_tail=dict(peak_force_N=99.))))
    attempt=dict(episode_id=spec['episode_id'],policy_mode=spec['policy_mode'],
                 pair_id=spec['pair_id'],status='AUDITED')
    return receipt,audit,attempt


def record(mode, pair, **kwargs):
    spec=job(mode,pair)
    return normalize_episode(spec,*evidence(spec,**kwargs))


def test_failure_time_is_30_not_an_early_stop_advantage_and_pairs_are_matched():
    rows=[record('mlp','negative',seconds=10),record('gru','negative',seconds=8),
          record('mlp','positive',seconds=2,success=False),record('gru','positive',seconds=12)]
    result=summarize_records(rows)
    mlp=result['groups']['mlp']; gru=result['groups']['gru']
    assert mlp['success_rate_registered']==.5 and mlp['success_rate_valid']==.5
    assert mlp['mean_penalized_time_valid_s']==20.
    assert gru['mean_penalized_time_valid_s']==10.
    assert result['common_success']['pair_ids']==['negative']
    assert result['common_success']['mean_gru_minus_mlp_time_s']==-2.
    positive=next(p for p in result['pairs'] if p['pair_id']=='positive')
    assert positive['penalized_gru_minus_mlp_time_s']==-18.
    assert positive['common_success_gru_minus_mlp_time_s'] is None
    assert result['selection_performed'] is False


def test_invalid_and_missing_are_not_hidden_or_normal_failure():
    spec=job('gru','negative');receipt,audit,attempt=evidence(spec)
    audit['verified']=False
    invalid=normalize_episode(spec,receipt,audit,attempt)
    missing=normalize_episode(job('gru','positive'),None,None,None)
    summary=summarize_records([record('mlp','negative'),record('mlp','positive'),invalid,missing])
    gru=summary['groups']['gru']
    assert gru['registered_count']==2 and gru['valid_count']==0
    assert gru['invalid_count']==1 and gru['missing_count']==1 and gru['failure_count']==0
    assert gru['success_rate_registered']==0 and gru['success_rate_valid'] is None
    assert gru['mean_penalized_time_registered_s'] is None
    assert invalid['task_load'] is None and invalid['penalized_time_s'] is None


def test_task_load_uses_task_segment_and_correct_duration_weighting():
    summary=summarize_records([record('mlp','negative',seconds=10,force=1),
                               record('mlp','positive',seconds=20,force=3),
                               record('gru','negative'),record('gru','positive')])
    load=summary['groups']['mlp']['task_load']
    assert load['max_task_peak_force_N']==3 and load['mean_episode_peak_force_N']==2
    assert load['sum_integral_force_Ns']==70
    assert load['time_weighted_mean_force_N']==pytest.approx(70/30)
    assert load['time_weighted_rms_force_N']==pytest.approx(math.sqrt(190/30))
    assert load['over_duration_sum_s']['FORCE_GT5_N']==.004


@pytest.mark.parametrize('field,value',[('case',{}),('seed',999),('deterministic',False),
                                       ('archive_sha256','d'*64),('source_checkpoint_sha256','e'*64),
                                       ('training_updates',1)])
def test_receipt_binding_mismatch_is_invalid(field,value):
    spec=job('mlp','negative');receipt,audit,attempt=evidence(spec)
    receipt[field]=value
    result=normalize_episode(spec,receipt,audit,attempt)
    assert result['status']=='INVALID' and result['issues']


def test_late_or_nonfinite_success_and_bad_metrics_are_invalid():
    spec=job('mlp','negative')
    for seconds in (31.01,float('nan')):
        assert normalize_episode(spec,*evidence(spec,seconds=seconds))['status']=='INVALID'
    receipt,audit,attempt=evidence(spec)
    audit['load_warnings']['exposure']['task']['integral_force_Ns']=-1
    assert normalize_episode(spec,receipt,audit,attempt)['status']=='INVALID'


def test_missing_pair_or_duplicate_records_rejected():
    rows=[record('mlp','negative'),record('gru','negative')]
    with pytest.raises(ValueError,match='Duplicate'):
        summarize_records(rows+rows[:1])
    with pytest.raises(ValueError,match='paired'):
        summarize_records(rows+[record('mlp','positive')])


def make_batch(tmp_path):
    schedule=[job(mode,pair) for pair in ('negative','positive') for mode in ('mlp','gru')]
    (tmp_path/'registration.json').write_text(json.dumps(dict(evaluation_schedule=schedule)),encoding='utf-8')
    attempts=[]
    for spec in schedule:
        receipt,audit,attempt=evidence(spec)
        attempts.append(attempt)
        folder=tmp_path/'evaluation'/spec['episode_id'];folder.mkdir(parents=True)
        (folder/'receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
        (folder/'audit.json').write_text(json.dumps(audit),encoding='utf-8')
    (tmp_path/'ledger.json').write_text(json.dumps(dict(status='COMPLETED',training_attempts=[],
        final_checkpoints={mode:expected(job(mode,'negative')) for mode in ('mlp','gru')},
        evaluation_attempts=attempts)),encoding='utf-8')
    return schedule


def test_closed_batch_cli_artifacts_do_not_change_inputs(tmp_path):
    make_batch(tmp_path)
    before={p.relative_to(tmp_path):p.read_bytes() for p in tmp_path.rglob('*.json')}
    result=analyze_batch(tmp_path)
    assert result['groups']['mlp']['registered_count']==2
    write_reports(result,tmp_path/'review')
    assert (tmp_path/'review'/'pilot_evaluation_summary.json').is_file()
    assert (tmp_path/'review'/'配对短训独立评估.md').is_file()
    assert all((tmp_path/p).read_bytes()==data for p,data in before.items())
    assert '单训练种子' in (tmp_path/'review'/'配对短训独立评估.md').read_text(encoding='utf-8')


def test_pair_registration_checks_shared_case_and_seed(tmp_path):
    schedule=make_batch(tmp_path)
    schedule[1]['seed']+=1
    (tmp_path/'registration.json').write_text(json.dumps(dict(evaluation_schedule=schedule)),encoding='utf-8')
    with pytest.raises(ValueError,match='paired'):
        analyze_batch(tmp_path)


def test_receipt_reader_skips_duplicate_native_sample_arrays(tmp_path):
    spec=job('mlp','negative');receipt,_,_=evidence(spec)
    receipt['load_warnings']={'samples':[dict(time_s=i*.0002,force_N=2) for i in range(200)]}
    receipt['evidence']={'load_warnings':deepcopy(receipt['load_warnings'])}
    path=tmp_path/'receipt.json';path.write_text(json.dumps(receipt),encoding='utf-8')
    compact=read_receipt(path)
    assert compact['episode_id']==spec['episode_id'] and 'load_warnings' not in compact
    assert 'evidence' not in compact


def test_corrupt_saved_evidence_remains_in_registered_denominator(tmp_path):
    schedule=make_batch(tmp_path)
    (tmp_path/'evaluation'/schedule[0]['episode_id']/'receipt.json').write_text('{broken',encoding='utf-8')
    result=analyze_batch(tmp_path)
    assert result['groups']['mlp']['registered_count']==2
    assert result['groups']['mlp']['invalid_count']==1
    assert result['groups']['mlp']['success_rate_registered']==.5
    assert result['groups']['mlp']['success_rate_valid']==1.


def test_malformed_load_or_checkpoint_metadata_is_invalid_not_a_crash():
    spec=job('mlp','negative')
    receipt,audit,attempt=evidence(spec)
    receipt['experiment']=None
    audit['load_warnings']=None
    assert normalize_episode(spec,receipt,audit,attempt)['status']=='INVALID'


def test_receipt_exponent_split_at_buffer_boundary(tmp_path):
    before='{"padding":"'+'x'*100+'","task_end_time_s":'
    padding=(1 << 16)-len(before)-2
    text=before.replace('x'*100,'x'*(100+padding))+'1e1,"episode_id":"boundary"}'
    assert text[(1 << 16)-2:(1 << 16)]=='1e'
    path=tmp_path/'receipt.json';path.write_text(text,encoding='utf-8')
    assert read_receipt(path)['task_end_time_s']==10.


def test_success_in_legal_hold_tail_keeps_actual_time_but_caps_time_score():
    spec=job('mlp','negative')
    row=normalize_episode(spec,*evidence(spec,seconds=30.05))
    assert row['status']=='SUCCESS'
    assert row['decision_time_s']==pytest.approx(29.95)
    assert row['task_time_s']==30.05 and row['penalized_time_s']==30.
    receipt,audit,attempt=evidence(spec,seconds=30.95)
    receipt['stop_time_s']=29.8
    audit['stop'].update(decision_time_s=29.8,end_time_s=31.8)
    assert normalize_episode(spec,receipt,audit,attempt)['status']=='INVALID'


@pytest.mark.parametrize('key,value',[('checkpoint_sha256','e'*64),('optimizer_updates',129)])
def test_same_old_frozen_weights_do_not_replace_ledger_final_checkpoint(tmp_path,key,value):
    make_batch(tmp_path)
    path=tmp_path/'ledger.json';ledger=json.loads(path.read_bytes())
    ledger['final_checkpoints']['mlp'][key]=value
    path.write_text(json.dumps(ledger),encoding='utf-8')
    result=analyze_batch(tmp_path)
    assert result['groups']['mlp']['invalid_count']==2
    assert result['groups']['mlp']['success_count']==0


def test_attempted_evaluation_without_final_checkpoint_binding_is_invalid():
    spec=job('mlp','negative')
    assert normalize_episode(spec,*evidence(spec),expected_checkpoint=None)['status']=='INVALID'
