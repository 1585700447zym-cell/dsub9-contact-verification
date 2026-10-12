"""Revised read-only auditor, loaded separately from the sealed physical runner."""
import argparse
from copy import deepcopy
from fractions import Fraction
import gzip
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from scope_contract import ROOT,proposal,read,sha,canonical,case_kwargs,attempt_specs,script_action
from execution_contract import check_initial_pose


def read_archive(path):
    return json.loads(gzip.decompress(Path(path).read_bytes()).decode('utf-8'),
        parse_constant=lambda x:(_ for _ in ()).throw(ValueError('Nonfinite JSON: '+x)))


def python_scalar(value,label):
    """Match live NumPy scalars to their JSON types without coercing schemas."""
    if type(value) in (int,float,bool,str,type(None)):
        return value
    import numpy as np
    if isinstance(value,(np.integer,np.floating,np.bool_)):
        converted=value.item()
        if type(converted) in (int,float,bool):
            return converted
    raise ValueError(label+' unsupported scalar type: '+type(value).__name__)


def same(left,right,label,tolerance=1e-12):
    if not isinstance(left,(dict,list,tuple)):left=python_scalar(left,label)
    if not isinstance(right,(dict,list,tuple)):right=python_scalar(right,label)
    if isinstance(left,dict):
        if not isinstance(right,dict) or left.keys()!=right.keys():raise ValueError(label+' keys differ')
        for k in left:same(left[k],right[k],label+'.'+k,tolerance)
    elif isinstance(left,(list,tuple)):
        if not isinstance(right,(list,tuple)) or len(left)!=len(right):raise ValueError(label+' shape differs')
        for a,b in zip(left,right):same(a,b,label,tolerance)
    elif type(left) in (int,float):
        if type(right) not in (int,float) or not math.isfinite(left) or not math.isfinite(right):
            raise ValueError(label+' differs/nonfinite')
        # Subtracting int/float directly can discard integer low bits before
        # the tolerance check. Keep their exact represented difference.
        difference=abs(Fraction(left)-Fraction(right)) if type(left)!=type(right) else abs(left-right)
        if difference>tolerance:
            raise ValueError(label+' differs/nonfinite')
    elif left!=right or type(left)!=type(right):raise ValueError(label+' differs')


def assess_raw(raw,spec,binding):
    c=proposal();common=read(ROOT/c['parent']['configuration'])['common']
    if raw['version']!='b2_pose_scope_raw_v1' or canonical(raw['spec'])!=canonical(spec):raise ValueError('Archive spec differs')
    if raw['binding_sha256']!=binding['binding_sha256']:raise ValueError('Archive belongs to another implementation')
    if raw['fault'] is not None:raise ValueError('Incomplete or faulted attempt')
    same(case_kwargs(spec['case']),raw['simulation_case'],'ContactCase')
    check_initial_pose(spec['case'],raw['initial'])
    same(dict(dynamic_config=common['dynamic_config'],guard_config=common['guard_config']),raw['parameters'],'parameters')
    cost=raw['costs']
    for key in ('case_environment_instances_attempted','case_environment_instances_completed','reset_attempts','resets_completed'):
        if type(cost[key]) is not int or cost[key]!=1:raise ValueError('Exactly one construct/reset required')
    for key in ('learner_constructions','tensor_reads','network_forwards','optimizer_updates','replay_publications'):
        if type(cost[key]) is not int or cost[key]!=0:raise ValueError('Unexpected learning cost')
    steps=raw['physical_substeps'];cycles=raw['control_cycles']
    if (type(steps) is not int or type(cycles) is not int or not 0<=steps<=145000 or not 0<=cycles<=14500
            or cost['native_step_calls']!=steps):raise ValueError('Physical count mismatch')
    if not 0<=raw['wall_seconds']<(60 if spec['kind']=='static' else 1200):raise ValueError('Attempt wall ceiling')
    facts=raw['guard_facts']
    if spec['kind']=='static':
        if steps or cycles or raw['initial']['contact_count'] or raw['initial']['penetration_m']>1e-9:
            raise ValueError('Static integration/contact')
        if facts['simulation_valid'] is not True or facts['invalid_reasons']:raise ValueError('Static invalidity')
        return dict(audit_passed=True,initial_pose=raw['initial'],physical_substeps=0,initialization_valid=True)
    from offline_math import numerics
    n=numerics();np=n['np'];rows=raw['cycles'];trace=raw['trace']
    if not rows or len(rows)!=cycles or len(trace)!=cycles+1:raise ValueError('Missing cycle/trace contexts')
    if steps!=cycles*10:raise ValueError('Partial native cycle is not a qualified completed episode')
    from evidence_checks import guard_evidence,observation_evidence
    guard_evidence(raw,common,n)
    observation=observation_evidence(raw,common,n,same)
    end=raw['audit_end_time_s'];task_end=raw['task_end_time_s'];dt=common['dynamic_config']['timestep']
    if not 0<=task_end<=common['failure_penalty_s']+1e-8 or not task_end<=end:raise ValueError('Task clock invalid')
    stopped=bool(n['actual_stop_pass'](raw['stop_samples'],raw['events'],raw['stop_time'],end,dt)
                 and n['physical_tail_pass'](raw['stop_samples'],end,dt))
    if not stopped:raise ValueError('Missing/invalid physical STOP tail')
    # Preserve guards as independent raw facts; sampled checks cannot prove no
    # substep violation. The inherited engine records substep facts and peaks.
    valid=facts['simulation_valid'] is True and not facts['invalid_reasons']
    success=raw['final_session']['task_finished'] is True and raw['final_session']['reason']=='GEOMETRIC_SUCCESS'
    out=n['classify_outcome'](simulation_valid=valid,physical_stopped=stopped,
        contact_guard=bool(facts['contact_reasons']),motion_violation=bool(facts['motion_reasons']),full_success=success)
    out.update(valid_for_learning=False,model_scope_qualified=False,training_admitted=False)
    for key in ('simulation_valid','physical_stopped','task_outcome','guard_violations'):same(out[key],raw['outcome'][key],'outcome.'+key)
    if raw['final_session']['phase']!='STOPPING':raise ValueError('Final session not physically stopped')
    if not valid:raise ValueError('Invalid simulation cannot qualify scope')
    reward=n['EpisodeReward'](.004);effect=np.zeros(4);motion=np.zeros(4);contact_effect=0;contact_rows=0;requests=0
    last_after=None;last_time=0.;geometry_cache={};last_task_row=None
    for i,cycle in enumerate(rows):
        before=cycle['before'];after=cycle['after'];result=cycle['result'];row=result['trace_row']
        if before['cycle_id']!=i or after['cycle_id']!=i+1:raise ValueError('Cycle order differs')
        if last_after is not None:same(before,last_after,'continuous snapshot')
        same(before['time_s'],last_time,'cycle start')
        same(after,result['next_snapshot'],'next snapshot');same(row,trace[i+1],'trace row')
        same(after['time_s'],row['time_s'],'cycle end');same(result['dt'],after['time_s']-before['time_s'],'dt')
        if not 0<result['dt']<=.002+1e-10:raise ValueError('Control period differs')
        if result['done'] is not (i==len(rows)-1):raise ValueError('Terminal boundary differs')
        phase=before['controller_state']['phase'];elapsed=before['time_s']-before['controller_state']['phase_start']
        action=script_action(phase,elapsed,before['residual_enabled'],spec['case']['script_sign']) if spec['arm']=='script' else [0.]*4
        same(action,cycle['requested'],'script request')
        if len(cycle['composition'])!=1:raise ValueError('Missing/exceptional composition context')
        context=deepcopy(cycle['composition'][0]);same(context.pop('action'),action,'composition request')
        same(context['phase'],phase,'composition phase')
        same(context['enabled'],before['residual_enabled'],'composition permission')
        same(context['dt'],common['dynamic_config']['control_period'],'composition period')
        base=context.pop('base')
        if context.get('search_config') is not None:
            same(context['search_config'],common['b2_config'],'controller config')
            context['search_config']=SimpleNamespace(**context['search_config'])
        command,log=n['compose_continuation_command'](base,action,**context)
        for key,value in log.items():same(value,result['action_log'][key],'action log.'+key)
        same(result['executed_command'],row['limited_command_world'],'actual command')
        same(result['action_log']['actual_end_limited_command'],result['executed_command'],'logged actual command')
        # Drive acceleration advances in physical substeps and can change on a
        # latched guard within a control cycle. Compare to predictor only when
        # the physical cycle remains RUNNING; retain all STOP contexts anyway.
        if row['phase']=='RUNNING' and before['state']['phase']=='RUNNING':
            same(log['predicted_limited_command'],result['executed_command'],'drive prediction',1e-10)
        if phase=='SEARCH' and before['residual_enabled'] and row['phase']=='RUNNING':
            origin=np.array(raw['initial']['position_m'])[:2]+np.array(before['controller_state']['search_origin'])[:2]
            if np.linalg.norm(np.array(row['reference_qpos'])[:2]-origin)>.00012+1e-12:
                raise ValueError('Actual SEARCH reference outside frozen disk')
        peaks=result['cycle_peaks'];parts=reward.advance(advance_m=row['position_m'][2]-raw['initial']['position_m'][2],
            dt=result['dt'],force_N=peaks['force_N'],torque_G_Nm=peaks['torque_G_Nm'])
        parts['terminal']=reward.finalize(out['task_outcome']) if i==len(rows)-1 else 0.
        parts['total']+=parts['terminal'];same(parts,result['reward_terms'],'reward')
        if row['time_s']<=task_end+1e-9:last_task_row=row
        requests+=int(any(action));effect+=np.abs(np.array(log['effective_command_delta'])[[0,1,3,4]])*result['dt']
        delta=np.array(after['state']['position_m'])-np.array(before['state']['position_m'])
        # Physical angular velocity integral is descriptive, never attributed
        # causally to a scripted residual without the matched zero arm.
        motion+=np.abs(np.r_[delta[:2],np.array(row['velocity_world'])[3:5]*result['dt']])
        contact=bool(row['contact_count']>0);contact_rows+=int(contact)
        contact_effect+=int(contact and np.any(np.abs(log['effective_command_delta'])>1e-15))
        last_after=after;last_time=after['time_s']
    same(last_time,end,'archive end');same(steps*dt,end,'native clock',1e-8)
    if last_task_row is None:raise ValueError('No task endpoint')
    criteria=common['finish_criteria']
    if success:
        hold=[r for r in trace if task_end-criteria['hold_s']-1e-9<=r['time_s']<=task_end+1e-9]
        if not hold or hold[0]['time_s']>task_end-criteria['hold_s']+.0021 or hold[-1]['time_s']<task_end-1e-9:
            raise ValueError('Missing functional hold evidence')
        for row in hold:
            key=canonical({k:row[k] for k in ('position_m','quaternion_wxyz','velocity_world','contact_wrench_G','penetration_m')})
            if key not in geometry_cache:geometry_cache[key]=n['functional_finish'](row,criteria)
            if not geometry_cache[key]:raise ValueError('Functional success geometry/hold failed')
        if any(raw['peaks'][k]>=criteria[cname] for k,cname in [('force_N','force_N'),('torque_G_Nm','torque_Nm'),('penetration_m','penetration_m')]):
            raise ValueError('Success contradicts peak loads')
    p=last_task_row['position_m'];q=np.array(last_task_row['quaternion_wxyz']);q=q/np.linalg.norm(q)
    angle=2*math.atan2(float(np.linalg.norm(q[1:])),abs(float(q[0])))
    precision=bool(out['task_outcome']=='FULL_SUCCESS' and math.hypot(*p[:2])<=80e-6 and angle<=math.radians(.5))
    recovered=any(e.get('phase')=='RECOVERING' or 'RECOVERY' in e.get('reason','') for e in raw['events'])
    return dict(audit_passed=True,outcome=out,initial_pose=raw['initial'],functional_success=out['task_outcome']=='FULL_SUCCESS',
        strict_precision_success=precision,failure_penalized_task_time_s=task_end if out['task_outcome']=='FULL_SUCCESS' else common['failure_penalty_s'],
        guard_reasons=facts['contact_reasons']+facts['motion_reasons'],script_nonzero_cycles=requests,
        axis_command_effect_integral=effect.tolist(),axis_observed_motion=motion.tolist(),contact_cycles=contact_rows,
        contact_effect_cycles=contact_effect,effect_coverage='OBSERVED' if requests and np.all(effect>1e-15) else 'INSUFFICIENT_COVERAGE',
        contact_coverage='OBSERVED' if contact_effect else 'INSUFFICIENT_COVERAGE',
        recovery_coverage='EVENTS_OBSERVED_REQUIRES_REVIEW' if recovered else 'INSUFFICIENT_COVERAGE',
        observation=observation,training_admitted=False,full_B2_accepted=False,
        task_endpoint=last_task_row,peak_loads=raw['peaks'])


def information_comparison(rows):
    by_id={r['id']:r for r in rows};pairs=[];arms=[]
    for point in ('P01','P02','P03','P04','J01','J02','J03','J04'):
        zero=by_id.get(point+'_zero',{});script=by_id.get(point+'_script',{})
        motion=None
        if 'axis_observed_motion' in zero and 'axis_observed_motion' in script:
            motion=[b-a for a,b in zip(zero['axis_observed_motion'],script['axis_observed_motion'])]
        arms.append(dict(case_id=point,zero_status=zero.get('status'),script_status=script.get('status'),
            observed_motion_difference=motion,causal_residual_effect_claim=False))
    for a,b in (('P01','P02'),('P03','P04'),('J01','J03'),('J02','J04')):
        for arm in ('zero','script'):
            left=by_id.get(a+'_'+arm,{}).get('observation',{});right=by_id.get(b+'_'+arm,{}).get('observation',{})
            initial=None;contact=None
            if left.get('initial_vector') is not None and right.get('initial_vector') is not None:
                initial=[x-y for x,y in zip(left['initial_vector'],right['initial_vector'])]
            if left.get('first_contact') and right.get('first_contact'):
                contact=[x-y for x,y in zip(left['first_contact']['features'],right['first_contact']['features'])]
            covered=(left.get('contact_information')==right.get('contact_information')=='OBSERVED_DIFFERENCE'
                and contact is not None and any(v!=0 for v in contact))
            pairs.append(dict(left=a+'_'+arm,right=b+'_'+arm,initial_observation_delta=initial,
                first_contact_feature_delta=contact,status='RECORDED_DIFFERENCE_REQUIRES_REVIEW' if covered else 'INSUFFICIENT_COVERAGE',
                left_clipped=None if not left.get('first_contact') else left['first_contact']['clipped_components'],
                right_clipped=None if not right.get('first_contact') else right['first_contact']['clipped_components']))
    return dict(status='INFORMATION_REVIEW_REQUIRED' if all(p['status']=='RECORDED_DIFFERENCE_REQUIRES_REVIEW' for p in pairs)
        else 'INSUFFICIENT_COVERAGE',symmetric_pairs=pairs,paired_arms=arms,
        limitation='No registered quantitative distinguishability threshold; even nonzero differences require interpretation, not automatic training admission')


def choose_route(full,closed,rows,info):
    if not full or closed:return 'NO_SCOPE_QUALIFICATION'
    scripts=[r for r in rows if r['id'].endswith('_script')]
    if any(r.get('effect_coverage')!='OBSERVED' or r.get('contact_coverage')!='OBSERVED' for r in scripts):
        return 'INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS'
    if info['status']=='INSUFFICIENT_COVERAGE':return 'INSUFFICIENT_INFORMATION_NO_EXTRA_ATTEMPTS'
    return 'INFORMATION_REVIEW_REQUIRED_BEFORE_TRAINING_REGISTRATION'


def assess(folder,*,verify_binding=True):
    folder=Path(folder);c=proposal();binding={'binding_sha256':None}
    if verify_binding:
        from run_preflight import check_binding,BINDING
        _,binding=check_binding();binding=dict(binding,binding_sha256=sha(BINDING))
    ledger=read(folder/'ledger.json');entries=ledger['attempts'];specs=attempt_specs(c)
    if len(entries)>25 or any(e['id']!=specs[i]['id'] or e['kind']!=specs[i]['kind'] for i,e in enumerate(entries)):
        raise ValueError('Attempt ledger skipped/reordered/exceeded')
    rows=[];closed=False
    for i,spec in enumerate(specs):
        row=dict(id=spec['id'],kind=spec['kind'],status='NOT_ATTEMPTED',functional_success=None,
                 audit_passed=False,failure_penalized_task_time_s=None)
        if i<len(entries):
            if closed:raise ValueError('Attempt occurred after closure condition')
            entry=entries[i];row['status']=entry['status']
            if entry['status']=='finished':
                path=folder/(spec['id']+'.json.gz')
                if sha(path)!=entry['archive_sha256']:raise ValueError('Raw archive SHA differs')
                row.update(assess_raw(read_archive(path),spec,binding))
                out=row.get('outcome',{})
                closed=not row['audit_passed'] or (spec['kind']=='dynamic' and out['task_outcome'] not in ('FULL_SUCCESS','TASK_FAILURE'))
            else:
                closed=True
                if spec['kind']=='dynamic':row['failure_penalized_task_time_s']=26.
        rows.append(row)
    full=len(entries)==25 and all(r['audit_passed'] for r in rows)
    info=information_comparison(rows[9:]);route=choose_route(full,closed,rows[9:],info)
    return dict(static=rows[:9],dynamic=rows[9:],route=route,information=info,planned_static=9,planned_dynamic=16,
        new_training_authorized=False,full_B2_accepted=False,independent_tests=0,retry_allowed=False,
        limitation='Development scope evidence only; script is not SAC and observed motion is not causal residual benefit')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('folder',type=Path)
    print(json.dumps(assess(parser.parse_args().folder),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
