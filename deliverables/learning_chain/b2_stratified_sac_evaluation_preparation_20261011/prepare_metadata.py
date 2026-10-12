"""Read-only source extraction; no tensor loads or scientific imports."""
from pathlib import Path
import importlib.util
import csv,gzip,hashlib,json,math

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2];BASE=ROOT/'deliverables/learning_chain'
ENTRY=BASE/'b2_stratified_zero_baseline_entry_20261011'
spec=importlib.util.spec_from_file_location('frozen_scope',ENTRY/'scope_contract.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)

def build():
    inherited=c.read(ENTRY/'source_binding.json');pins=dict(inherited['files']);seals=[]
    def add(p):
        p=Path(p);v=c.sha(p)
        if str(p) in pins and pins[str(p)]!=v:raise ValueError('Inherited pin changed: '+str(p))
        pins[str(p)]=v;return v
    for name,count in [('b2_stratified_zero_baseline_execution_20261011',229),
        ('b2_stratified_zero_baseline_entry_20261011',55),('b2_pure_baseline_execution_20261011',77),
        ('b2_stratified_scope_preparation_20261011',29),('b2_joint_sac_continuation_execution_20261009',139)]:
        d=BASE/name;m=c.read(d/'delivery_manifest.json');assert len(m['files'])==count
        for rel,v in m['files'].items():
            p=d/rel;pin=v['sha256'] if isinstance(v,dict) else v
            if c.sha(p)!=pin or isinstance(v,dict) and p.stat().st_size!=v['bytes']:raise ValueError('Seal drift: '+str(p))
            add(p)
        seals.append(dict(path=str(d/'delivery_manifest.json'),sha256=add(d/'delivery_manifest.json'),members=count))
    actual=c.read(BASE/'b2_stratified_zero_baseline_execution_20261011/assessment.json')
    assert actual['cumulative_dynamic']==279 and len(actual['records'])==25
    old=c.read(BASE/'b2_pure_baseline_execution_20261011/assessment.json')
    S20=BASE/'b2_joint_sac_continuation_execution_20261009'
    cfg=c.read(S20/'configuration.json');scores=c.read(S20/'assessment.json')['scores']
    schema=cfg['methods']['F50']['schema'];learn=dict(cfg['methods']['F50'],version='b2_joint_sac_config_v1')
    actors=[];states=[];reused=[]
    for role,stage,checkpoint,expected in [('F0','zero','warm','6cebe494e472f88c725beb6e19b3f1b2e0883be8b8f81487eef0c27d131e6d31'),
        ('F2000','final','final','609a41d4538b75e847cc35866da204107fb3807efe1493a04636a8319256657c')]:
        records=[r for r in old['records'] if r['role']==role];assert len(records)==4
        for record in records:
            p=Path(record['archive_path']);assert c.sha(p)==record['sha256'];raw=json.loads(gzip.decompress(p.read_bytes()))
            point=next(p for p in cfg['cases'] if p['id']==raw['case_id'])
            score=next(r for r in scores[stage]['rows'] if r['case_id']==point['id'])
            audit=c.frozen_module('contract').check_archive(raw,point,role,cfg['common_key'],score,schema)
            assert raw['policy_sha256']==expected
            n=raw['control_cycles'];assert len(raw['transitions'])==len(raw['actions'])==n and len(raw['trace'])==n+1
            active=[i for i,t in enumerate(raw['transitions']) if t['action_active'] is True];assert len(active)>=4
            chosen=[active[(len(active)-1)*k//3] for k in range(4)];assert len(set(chosen))==4
            for i in chosen:
                obs=c.finite_vector(raw['transitions'][i]['observation'],137)
                action=c.finite_vector(raw['actions'][i]['raw_action'],4)
                assert max(abs(x) for x in obs)<=10 and max(abs(x) for x in action)<=1
                assert action==raw['transitions'][i]['action']
                states.append(dict(role=role,source_archive=str(p),source_sha256=add(p),
                    original_case_id=point['id'],input_index=i,time_s=raw['trace'][i]['time_s'],
                    observation=obs,raw_action=action,policy_sha256=expected,optimizer_steps=raw['optimizer_steps']))
            alias='J'+point['id'][-1]*2
            reused.append(dict(record,case_id=alias,original_case_id=point['id'],archive_audit=audit))
        cp=S20/'run/checkpoints'/checkpoint;manifest=c.read(cp/'manifest.json')
        statepin=add(cp/'state.pt');assert statepin==manifest['state_sha256']
        actors.append(dict(role=role,stage=stage,updates=0 if role=='F0' else 2000,
            checkpoint=str(cp),state_sha256=statepin,state_bytes=(cp/'state.pt').stat().st_size,
            manifest_sha256=add(cp/'manifest.json'),actor_sha256=expected,
            source_status='metadata_candidate_only_pending_tensor_equivalence'))
    assert len(states)==32
    priority=['D00','P4','A1','J12','J23','J14'];cases=c.new_cases()
    ordered=[next(p for p in cases if p['id']==key) for key in priority]+[p for p in cases if p['id'] not in priority]
    schedule=[dict(index=2*i+j,case_id=p['id'],role=role,phase='dynamic_precheck' if i<6 else 'remaining_evaluation',
        case=p,data_use='development',counts_in_42=True) for i,p in enumerate(ordered) for j,role in enumerate(['F0','F2000'])]
    for rel in ['sac/policies.py','common/policies.py','common/distributions.py','common/preprocessing.py','common/torch_layers.py']:
        add(ROOT/'tmp/learning_cpu_20260924/Lib/site-packages/stable_baselines3'/rel)
    for p,pin in pins.items():assert c.sha(p)==pin,p
    binding=dict(inherited,files=pins,inherited_input_count=len(inherited['files']),prior_seals=seals,
        version='b2_stratified_frozen_sac_sources_v1',scientific_execution_admitted=False,training_admitted=False)
    c.write(OUT/'configuration.json',dict(c.read(ENTRY/'configuration.json'),learning_config=learn,
        schema=schema,actor_specs=actors,roles=['F0','F2000'],cumulative_before=279))
    c.write(OUT/'source_binding.json',binding)
    c.write(OUT/'actors.json',dict(actors=actors,schema_sha256=c.digest(schema),observation_width=137,action_width=4,
        physical_scales=learn['action_scale'],weight_tensor_read=False,numeric_actor_equivalence_passed=False))
    c.write(OUT/'numeric_reference_states.json',dict(states=states,source_states_only=True,new_policy_calls=0,new_tensors=0,
        selection='four_equally_spaced_active_inputs_per_old_archive',schema_sha256=c.digest(schema)))
    c.write(OUT/'evaluation_schedule.json',dict(schedule=schedule,prechecks=12,remaining=30,total=42,data_use='development'))
    c.write(OUT/'reuse_catalog.json',dict(pure_B2=actual['records'],learned_old=reused,reused=33,pending=42,total=75))
    c.write(OUT/'seal_format_audit.json',dict(passed=True,seals=seals,old_files_changed=False,
        resolved_false_alarm='Old SCOPE20 entries are objects containing bytes and sha256, not direct hashes.'))
    with (OUT/'evaluation_schedule.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['index','case_id','role','phase','data_use']);w.writeheader()
        w.writerows({k:r[k] for k in w.fieldnames} for r in schedule)
    print(json.dumps(dict(bound_sources=len(pins),old_seal_members=sum(s['members'] for s in seals),states=32,schedule=42,reused=33)))

if __name__=='__main__':build()
