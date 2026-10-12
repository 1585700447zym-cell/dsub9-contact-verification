"""Read sealed development data and evaluate command algebra. Never step physics."""
from pathlib import Path
import gzip, hashlib, json, math, sys
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parents[3]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'deliverables/task_variants/layered_referee_20261004'
sys.path.insert(0,str(ROOT))
from tools.evaluation.paper_comparison import comparison_key, summarize, build_common_contract

EXPECTED_SEALS={
 'clearance120_20261003':'9a30d508298a81384e1d7a96f779e1ef9fc8856c6b37d98e908f744cf33b42b3',
 'functional_b2_20261003':'bce6ff81e3a68681e0c15d6f7a2d1470fe89a6adc29adf06a66cbe2fbce689a0',
 'search_load_20261004':'8b91de9dc101aa2af2d2f35277d44c6fe0f32894e4cb64086bfb0c32735cf90f',
 'admittance_rebase_20261004':'cb010377707ba49a60405f067faeee1e238cdc460d09d55deffa7551a0fef57e',
 'compliant_search_20261004':'0a32a668f220a8b19a52766a823614e8552448a347e9d66bb66081d4a9afe36b',
 'axis_search_20261004':'e23b4e3ce25a316e98124e137f7bfd3725c697be033d131b596b04670f574551',
 'reference_search_20261004':'be7c6d63b424ffaefa1cb4d70d7d0ff56cb45deb02b08218cb22e9a3d063f716',
 'deadline25_20261004':'5888d9f304c14999fe4d074739b2b0c92e52e28a628192e8f222e695a53aba0c',
 'layered_referee_20261004':'25ac263620570cf068f0f36a1d702a68223f1a6d237d1dcf8b5604fbe3425e6a'}

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')

def verify_prior():
    verified={}
    for name,digest in EXPECTED_SEALS.items():
        folder=ROOT/'deliverables/task_variants'/name
        manifest=folder/'delivery_manifest.json'
        assert sha(manifest)==digest, name
        files=read(manifest)['files']
        for rel,record in files.items():
            p=folder/rel
            assert p.stat().st_size==record['bytes'] and sha(p)==record['sha256'],str(p)
        verified[name]=dict(manifest_sha256=digest,files_verified=len(files))
    return verified

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed; read results only')
    verified=verify_prior();write('prior_seals_verified.json',verified)
    cfg=read(BASE/'configuration.json');ledger=read(BASE/'run/ledger.json');assessment=read(BASE/'assessment.json')
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    import numpy as np
    from tools.model.clearance_task import build_task_xml
    from tools.learning.action import compose_command
    common=build_common_contract(cfg,canonical_model_sha256=hashlib.sha256(build_task_xml().encode()).hexdigest(),
                                 evaluator_sha256=sha(ROOT/'tools/evaluation/paper_comparison.py'))
    code=common['frozen_common_source_sha256']
    assert all(sha(ROOT/n)==h for n,h in code.items())
    key=comparison_key(common)
    protocol=dict(version='paper_comparison_v4_prepare1',created_at=datetime.now(timezone(timedelta(hours=8))).isoformat(),
        common=common,comparison_key=key,baseline_seal_sha256=EXPECTED_SEALS[BASE.name],
        methods={'B1':dict(search=False,residual=False,status='adapter_pending'),
                 'B2':dict(search=True,residual=False,status='five_development_cases_verified'),
                 'F50':dict(action_scale=[.00005,.00005,.0005,.0005],phases=['INSERT','SEARCH'],status='adapter_not_admitted'),
                 'S50':dict(action_scale=[.00005,.00005,.0005,.0005],phases=['SEARCH'],status='adapter_not_admitted')},
        current_budget=dict(dynamic_episodes=0,physical_substeps=0,network_calls=0,training_updates=0,cumulative_episodes=130),
        proposed_next_budgets=dict(status='proposal_not_admission',adapter=dict(episodes=9,updates=0),pilot=dict(episodes=28,updates=4000)),
        training_admitted=False,automatic_tracking='PAUSED',stage_B2_complete=False,
        pilot_gate=dict(comparators=['B2','F50'],successes_no_fewer=True,minimum_successes=1,
                        penalized_time_reduction_fraction=.10,max_mean_peak_force_ratio=1.05,guards_no_more=True),
        scope='development_protocol_not_independent_evaluation')
    write('protocol.json',protocol)
    records=[];audits={};examples=[]
    actions=[(x,y,0.,0.) for x in (-1.,0.,1.) for y in (-1.,0.,1.) if x or y]
    dt=cfg['dynamic_config']['control_period'];limit=cfg['b2_config']['spiral_radius_m']
    for e,a in zip(ledger['episodes'],assessment['rows'],strict=True):
        assert e['id']==a['id']
        path=BASE/'run'/(e['id']+'.json.gz');assert sha(path)==e['archive_sha256']
        d=json.loads(gzip.decompress(path.read_bytes()));trace=d['trace'];facts=d['guard_facts']
        # The archive cannot contain its own digest; the ledger adds it afterward.
        assert d['status']=='finished' and d['summary']=={k:v for k,v in e.items() if k!='archive_sha256'}
        assert facts['simulation_valid'] is a['simulation_valid'] is True
        assert a['physical_stopped'] is e['outcome']['physical_stopped'] is True
        assert a['functional_success']==(e['outcome']['task_outcome']=='FULL_SUCCESS')
        times=np.array([r['time_s'] for r in trace]);force=np.linalg.norm([r['contact_wrench_M'][:3] for r in trace],axis=1)
        assert np.all(np.diff(times)>0) and np.max(np.abs(np.diff(times)-dt))<1e-8
        assert abs(times[-1]-e['end_time'])<1e-9
        integral=float(np.sum((force[1:]+force[:-1])*.5*np.diff(times)))
        records.append(dict(case_id=e['id'],comparison_key=key,status='finished',outcome=e['outcome']['task_outcome'],
            simulation_valid=facts['simulation_valid'],physical_stopped=a['physical_stopped'],
            contact_guard=bool(facts['contact_reasons']),motion_violation=bool(facts['motion_reasons']),
            guard_reasons=facts['contact_reasons']+facts['motion_reasons'],
            task_end_time_s=e['task_end_time'],physical_end_time_s=e['end_time'],
            peak_force_N=e['peaks']['force_N'],peak_torque_Nm=e['peaks']['torque_G_Nm'],
            strict_precision_success=a['strict_precision_success'],sampled_force_integral_N_s=integral,
            archive_sha256=sha(path),archive_path=path.relative_to(ROOT).as_posix()))
        count=violations=0;zero_error=0.;max_excess=0.
        for prev,r in zip(trace,trace[1:]):
            comp=r['search_composition']
            if comp is None:continue
            assert r['phase']=='RUNNING' and r['policy_phase']=='SEARCH'
            assert abs(comp['time_s']-prev['time_s'])<1e-9
            kwargs=dict(phase='SEARCH',enabled=True,previous_limited=prev['limited_command_world'],dt=dt,
                        action_scale=(.00005,.00005,.0005,.0005))
            _,zero=compose_command(r['raw_command_world'],[0.]*4,**kwargs)
            ref=np.array(comp['reference_xy_m'])
            prediction=ref+np.array(zero['predicted_limited_command'][:2])*dt
            zero_error=max(zero_error,float(np.max(np.abs(prediction-comp['predicted_reference_xy_m']))))
            assert np.linalg.norm(prediction)<=limit+1e-12
            count+=1
            for action in actions:
                _,log=compose_command(r['raw_command_world'],action,**kwargs)
                xy=np.array(log['predicted_limited_command'][:2]);new_ref=ref+xy*dt
                excess=float(np.linalg.norm(new_ref)-limit)
                if excess>1e-12:
                    violations+=1;max_excess=max(max_excess,excess)
                    if len(examples)<12:
                        examples.append(dict(case=e['id'],command_time_s=comp['time_s'],normalized_action=action,
                            reference_xy_m=ref.tolist(),base_command=r['raw_command_world'],
                            previous_limited_command=prev['limited_command_world'],dt_s=dt,
                            zero_reference_radius_um=float(np.linalg.norm(prediction))*1e6,
                            composed_reference_radius_um=float(np.linalg.norm(new_ref))*1e6,
                            excess_um=excess*1e6,composed_limited_xy_m_s=xy.tolist()))
        assert zero_error<1e-12
        audits[e['id']]=dict(search_commands=count,zero_prediction_error_m=zero_error,
                            counterfactual_actions=count*8,envelope_violations=violations,max_excess_um=max_excess*1e6)
    assert len(records)==5
    write('baseline_records.json',records)
    summary=summarize(records,[c['id'] for c in cfg['cases']]);assert summary['successes']==5
    write('baseline_metrics.json',summary)
    audit=dict(cases=audits,examples=examples,scope='one_step_command_counterfactual_not_physics_or_policy_success',
        baseline_common_task_unchanged=True,zero_prediction_equivalent=True,
        search_commands=sum(a['search_commands'] for a in audits.values()),
        counterfactual_actions=sum(a['counterfactual_actions'] for a in audits.values()),
        envelope_violations=sum(a['envelope_violations'] for a in audits.values()),
        new_dynamic_episodes=0,new_physical_steps=0,network_calls=0,training_updates=0,
        residual_v4_integration_ready=False)
    assert audit['search_commands']==16563 and audit['envelope_violations']>0
    write('residual_integration_audit.json',audit)
    print(json.dumps(dict(metrics=summary,audit={k:v for k,v in audit.items() if k not in ('cases','examples')},
                         first_counterexample=examples[0]),ensure_ascii=False))

if __name__=='__main__':main()
