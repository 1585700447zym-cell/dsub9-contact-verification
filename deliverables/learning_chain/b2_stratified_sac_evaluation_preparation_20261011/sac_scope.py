"""Frozen actor evaluation contract. All functions here use the standard library."""
from pathlib import Path
import importlib.util,math,re
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
ENTRY=ROOT/'deliverables/learning_chain/b2_stratified_zero_baseline_entry_20261011'
spec=importlib.util.spec_from_file_location('sac_frozen_scope',ENTRY/'scope_contract.py')
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
read,write,sha,digest,canonical,now,helper=c.read,c.write,c.sha,c.digest,c.canonical,c.now,c.helper
finite_vector,case_kwargs,check_initial_state=c.finite_vector,c.case_kwargs,c.check_initial_state
SEED=c.SEED
PHYSICAL_LIMITS=dict(dynamic_episodes=42,environment_creations=42,resets=42,control_cycles=609000,native_steps=6090000,
    per_episode_cycles=14500,per_episode_native_steps=145000,per_episode_wall_s=1200,whole_wall_s=21600,
    policy_calls=609000,policy_call_attempts=609000,actor_constructions=42,actor_construction_attempts=42,
    tensor_loads=42,tensor_load_attempts=42,learner_constructions=0,formal_updates=0,replay_publications=0,independent_tests=0)
NUMERIC_LIMITS=dict(dynamic_episodes=0,environment_creations=0,resets=0,native_steps=0,whole_wall_s=600,
    distinct_states=32,policy_calls=64,policy_call_attempts=64,actor_constructions=2,actor_construction_attempts=2,
    reference_learner_constructions=2,reference_learner_construction_attempts=2,tensor_loads=2,tensor_load_attempts=2,
    critic_forward_calls=0,formal_updates=0,optimizer_steps=0,replay_publications=0,independent_tests=0)

def actor_spec(role):
    if role not in ('F0','F2000'):raise ValueError('Frozen registered actor role required')
    return next(a for a in read(OUT/'actors.json')['actors'] if a['role']==role)

def schedule():
    raw=read(OUT/'evaluation_schedule.json')['schedule'];cases=c.new_cases()
    priority=['D00','P4','A1','J12','J23','J14']
    points=[next(p for p in cases if p['id']==s) for s in priority]+[p for p in cases if p['id'] not in priority]
    expected=[dict(index=2*i+j,case_id=p['id'],role=r,phase='dynamic_precheck' if i<6 else 'remaining_evaluation',
        case=p,data_use='development',counts_in_42=True) for i,p in enumerate(points) for j,r in enumerate(['F0','F2000'])]
    if canonical(raw)!=canonical(expected):raise ValueError('Frozen ordered 12+30 development schedule differs')
    return raw

def verify_binding():
    binding=read(OUT/'source_binding.json')
    for path,pin in binding['files'].items():
        if sha(path)!=pin:raise ValueError('Bound source changed: '+path)
    c.frozen_module('contract').check_runtime(binding['numerical_runtime'])
    cfg=read(OUT/'configuration.json');original=read(ENTRY/'configuration.json')
    if any(canonical(cfg[k])!=canonical(v) for k,v in original.items()):raise ValueError('Shared matrix/common/method identity changed')
    if cfg['cumulative_before']!=279 or cfg['data_use']!='development':raise ValueError('Development scope/cumulative differs')
    schema=read(OUT/'actors.json');states=read(OUT/'numeric_reference_states.json')
    if (schema['schema_sha256']!=digest(cfg['schema']) or states['schema_sha256']!=schema['schema_sha256'] or
        len(states['states'])!=32 or schema['physical_scales']!=[5e-5,5e-5,.0005,.0005] or
        cfg['actor_specs']!=schema['actors']):raise ValueError('Actor/schema/action/reference identity differs')
    schedule();return binding,cfg

def grant_template(kind,binding_pin,run_id):
    if kind not in ('numeric','physical'):raise ValueError('Separate grant kind required')
    return dict(version='b2_stratified_frozen_sac_grant_v1',kind=kind,binding_sha256=binding_pin,run_id=run_id,
        status='DRAFT',explicit_user_authorized=False,human_evidence='',purpose='frozen_sac_'+kind+'_development',
        matrix_scope_key=read(OUT/'configuration.json')['common_key'],cumulative_before=279,
        old_budget_closed=True,retries=0,limits=dict(NUMERIC_LIMITS if kind=='numeric' else PHYSICAL_LIMITS),
        numeric_result_sha256=None)

def require_grant(g,kind,binding_pin,run_id):
    expected=grant_template(kind,binding_pin,run_id)
    if (not isinstance(g,dict) or set(g)!=set(expected) or g.get('status')!='OPEN' or
        g.get('explicit_user_authorized') is not True or not isinstance(g.get('human_evidence'),str) or not g['human_evidence'].strip() or
        re.fullmatch('[0-9a-f]{64}',binding_pin or '') is None or not isinstance(run_id,str) or
        re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{1,90}',run_id) is None or run_id=='pending-new-run-id' or
        any(canonical(g[k])!=canonical(expected[k]) for k in expected if k not in
            ('status','explicit_user_authorized','human_evidence','numeric_result_sha256')) or
        kind=='numeric' and g['numeric_result_sha256'] is not None):
        raise PermissionError('Separately bound explicit '+kind+' grant required')

def check_receipt_costs(row):
    caps=dict(environment_creation_attempted=1,environment_created=1,reset_attempted=1,reset_completed=1,
        control_cycles=14500,physical_substeps=145000,policy_calls=14500,policy_call_attempts=14500,
        actor_construction_attempts=1,actor_constructions=1,tensor_load_attempts=1,tensor_loads=1,
        learner_constructions=0,formal_updates=0,replay_publications=0)
    for k,cap in caps.items():
        v=row.get(k,0)
        if type(v) is not int or not 0<=v<=cap:raise ValueError('Operation ceiling or integer violated: '+k)
    for completed,attempt in [('environment_created','environment_creation_attempted'),('reset_completed','reset_attempted'),
        ('policy_calls','policy_call_attempts'),('actor_constructions','actor_construction_attempts'),('tensor_loads','tensor_load_attempts')]:
        if row.get(completed,0)>row.get(attempt,0):raise ValueError('Uncharged completed operation: '+completed)

def receipt_healthy(row):
    check_receipt_costs(row);out=row.get('outcome',{});sup=row.get('supervisor',{})
    try:
        expected=actor_spec(row['role'])['actor_sha256'];error=row['max_command_error']
        return bool(row['status']=='finished' and row['healthy'] is True and row['initial_audit']['passed'] is True and
            re.fullmatch('[0-9a-f]{64}',row.get('archive_sha256') or '') and
            row['actor_before']==row['actor_after']==expected and type(error) in (int,float) and math.isfinite(error) and 0<=error<=1e-12 and
            all(row.get(k)==1 for k in ('environment_creation_attempted','environment_created','reset_attempted','reset_completed',
                'actor_construction_attempts','actor_constructions','tensor_load_attempts','tensor_loads')) and
            row['physical_substeps']==10*row['control_cycles'] and 0<row['control_cycles']<=14500 and
            row['policy_calls']==row['policy_call_attempts'] and row['policy_calls']<=row['control_cycles'] and
            out['simulation_valid'] is True and out['physical_stopped'] is True and out['guard_violations']==dict(contact=False,motion=False) and
            out['task_outcome'] in ('FULL_SUCCESS','TASK_FAILURE') and sup.get('go_issued') is True and
            sup.get('process_exit_confirmed') is True and sup.get('owned_launcher_exit_confirmed') is True and
            type(sup.get('returncode')) is int and sup['returncode']==0)
    except (KeyError,TypeError,ValueError):return False

def dynamic_precheck(rows):
    passed=len(rows)>=12
    evidence=[]
    for i,row in enumerate(rows[:12]):
        spec=schedule()[i]
        n=row.get('nonzero_applied_command_cycles')
        good=row.get('index')==i and row.get('case_id')==spec['case_id'] and row.get('role')==spec['role'] and receipt_healthy(row)
        good=good and type(n) is int and 0<n<=row.get('policy_calls',0)
        evidence.append(dict(index=i,passed=bool(good)));passed=passed and bool(good)
    return dict(passed=passed,required_attempts=12,evidence=evidence,fixed_actors_discrete_development_only=True,
        training_admitted=False,continuous_scope_qualified=False)

def next_unit(rows):
    units=schedule()
    if not isinstance(rows,list) or len(rows)>42:raise ValueError('42 attempt ceiling')
    for i,row in enumerate(rows):
        unit=units[i]
        if any(row.get(k)!=unit[k] for k in ('index','case_id','role')):raise ValueError('Duplicate, omitted or reordered attempt')
        if not receipt_healthy(row):return None
    if len(rows)>=12 and not dynamic_precheck(rows)['passed']:return None
    return units[len(rows)] if len(rows)<42 else None

def check_numeric_result(result,ledger,proof):
    if (ledger.get('status')!='CLOSED_COMPLETE' or result.get('passed') is not True or
        result.get('binding_sha256')!=ledger.get('binding_sha256') or
        result.get('states_sha256')!=sha(OUT/'numeric_reference_states.json') or
        result.get('actor_specs_sha256')!=sha(OUT/'actors.json') or
        result.get('equivalent_states')!=32 or result.get('policy_calls')!=64 or
        any(result.get(k)!=ledger.get(k) or proof.get(k)!=ledger.get(k) or not isinstance(ledger.get(k),str) or not ledger[k]
            for k in ('run_id','grant_sha256','nonce','binding_sha256')) or
        type(result.get('worker_pid')) is not int or result['worker_pid']<=0 or proof.get('worker_pid')!=result['worker_pid'] or
        proof.get('identity_verified') is not True or proof.get('result_digest')!=digest(result) or proof.get('go_issued') is not True or
        proof.get('process_exit_confirmed') is not True or proof.get('owned_launcher_exit_confirmed') is not True or
        type(proof.get('returncode')) is not int or proof['returncode']!=0):
        raise PermissionError('Closed, bound 32-state / 64-call numeric proof and owned exit required')

def require_numeric(pin):
    d=OUT/'numeric_execution';result=read(d/'result.json');ledger=read(d/'ledger.json');proof=read(d/'numeric_exit_proof.json')
    if sha(d/'result.json')!=pin or ledger['binding_sha256']!=sha(OUT/'source_binding.json'):
        raise PermissionError('Numeric proof binding differs')
    check_numeric_result(result,ledger,proof)
    if ledger.get('numeric_exit_proof_sha256')!=sha(d/'numeric_exit_proof.json'):
        raise PermissionError('Numeric final exit proof pin differs')
    for name,p in [('raw_supervisor_sha256',d/'gate.supervisor.json'),('worker_claim_sha256',d/'worker.claim'),
        ('ready_sha256',d/'gate.ready.json'),('go_sha256',d/'gate.go.json'),('result_sha256',d/'result.json'),('receipt_sha256',d/'receipt.json')]:
        if proof.get(name)!=sha(p):raise PermissionError('Numeric evidence member changed: '+name)
    from sac_entry import numeric_exit_proof
    if canonical(proof)!=canonical(numeric_exit_proof(d,ledger,read(d/'gate.supervisor.json'))):
        raise PermissionError('Numeric process evidence context differs')
    grant=read(ledger['grant_path'])
    if sha(ledger['grant_path'])!=ledger['grant_sha256']:raise PermissionError('Numeric grant pin differs')
    require_grant(grant,'numeric',ledger['binding_sha256'],ledger['run_id'])
    return result
