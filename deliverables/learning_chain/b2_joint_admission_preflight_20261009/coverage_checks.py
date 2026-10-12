"""Joint protocol and coverage, from recorded requests/effects/sensors only."""
from copy import deepcopy
from types import SimpleNamespace
from scope_contract import profile_action,schedule_position,healthy
from recovery_fixture import eligible

def nonzero(values):return any(abs(v)>1e-15 for v in values)

def action_coverage(raw,spec):
    if spec['profile']=='R_RECOVERY':return {'applicable':False}
    signs=[set() for _ in range(4)];holds={'50':0,'1':0};peaks={}
    for i,c in enumerate(raw['cycles']):
        effect=c['result']['action_log']['effective_command_delta']
        if c['before']['residual_enabled'] and c['result']['trace_row']['contact_count']>0 and nonzero(effect):
            _,hold,_=schedule_position(spec['profile'],i);holds[str(hold)]+=1
            for axis,index in enumerate((0,1,3,4)):
                if abs(effect[index])>1e-15:signs[axis].add(1 if effect[index]>0 else -1)
    for key in ('force_N','torque_G_Nm','penetration_m'):
        maximum=raw['peaks'][key]
        indices=[i for i,c in enumerate(raw['cycles']) if c['result']['cycle_peaks'][key]==maximum]
        overlap=[i for i in indices if raw['cycles'][i]['before']['residual_enabled'] is True
            and nonzero(raw['cycles'][i]['result']['action_log']['effective_command_delta'])]
        peaks[key]=dict(value=maximum,cycle_ids=indices,overlap_cycle_ids=overlap,
            covered=bool(maximum>0 and indices and len(indices)==len(overlap)))
    return dict(applicable=True,signs=[sorted(s) for s in signs],hold_contact_effect_cycles=holds,peaks=peaks)

def audit_protocol(raw,spec,same):
    rows=raw['cycles'];events=raw.get('fixture_events')
    if not isinstance(events,list):raise ValueError('Missing fixture provenance')
    if spec['profile']!='R_RECOVERY':
        if events:raise ValueError('Recovery injection in A/B')
        actions=[profile_action(spec['profile'],i,c['before']['residual_enabled']) for i,c in enumerate(rows)]
        for action,c in zip(actions,rows):same(action,c['requested'],'fixed A/B schedule')
        return dict(expected_actions=actions,recovery=dict(applicable=False,covered=False))
    if len(events)>1:raise ValueError('Repeated recovery injection')
    records=raw['observations'];trigger=None
    if events:
        event=events[0];trigger=event['cycle_id']
        if type(trigger) is not int or not 0<=trigger<len(rows):raise ValueError('Bad fixture cycle')
        pre=event['prepared'];post=event['after'];context=records[trigger]['context']
        if not eligible(SimpleNamespace(**pre),reason=event['reason_before'],guard_latched=event['guard_latched_before'],
            done=event['done_before'],task_finished=event['task_finished_before'],recovery_state=event['recovery_state_before'],
            facts=event['guard_facts_before'],recovery_count=event['recovery_count_before']):raise ValueError('Ineligible injection')
        same(post,rows[trigger]['before'],'fixture final snapshot')
        same(pre['cycle_id'],trigger,'fixture cycle');same(pre['time_s'],post['time_s'],'fixture time')
        same(post['base_command'],[0.]*6,'discarded prepared command')
        if post['residual_enabled'] is not False or context['recovery_state']!='WAIT_STOP':raise ValueError('Injection not masked WAIT_STOP')
        for key,value in event['sensor_before'].items():
            if key!='phase':same(value,event['sensor_after'][key],'unchanged fixture sensor.'+key)
        if event['sensor_after']['phase']!='STOPPING':raise ValueError('Fixture did not use stop')
        old,new=event['live_before'],event['live_after']
        if old is None or new is None:raise ValueError('Missing live physical fixture evidence')
        for key in ('qpos','qvel','time_s','physical_steps','recovery_count','recovery_start','guard_facts','raw_command'):
            same(old[key],new[key],'unchanged live state.'+key)
        same(new['reference'],old['qpos'],'original stop reanchor');same(new['command'],[0.]*6,'original stop command')
        expected=deepcopy(pre['controller_state']);expected.update(phase='WAIT_RECOVERY',phase_start=pre['time_s'],search_composition=None)
        expected['events'].append(dict(time_s=pre['time_s'],phase='WAIT_RECOVERY',reason='SEARCH_EXHAUSTED'))
        same(expected,post['controller_state'],'one transition and no duplicate baseline update')
        matching=[e for e in raw['events'] if e['reason']=='B2_SEARCH_EXHAUSTED' and abs(e['time_s']-pre['time_s'])<1e-12]
        if len(matching)!=1:raise ValueError('Missing exact physical stop event')
    actions=[];pulse=None;masked=[]
    for i,c in enumerate(rows):
        snap=c['before'];ctx=records[i]['context'];state=ctx['recovery_state']
        # There may not be an earlier eligible prepared state that was skipped.
        if trigger is None or i<trigger:
            if eligible(SimpleNamespace(**snap),reason=ctx['reason'],guard_latched=bool(ctx['guard_facts']['contact_reasons'] or ctx['guard_facts']['motion_reasons']),
                done=False,task_finished=False,recovery_state=state,facts=ctx['guard_facts'],recovery_count=ctx['recovery_count']):
                raise ValueError('Skipped first eligible recovery trigger')
        action=[0.]*4
        if trigger is not None and i>=trigger:
            if state in ('WAIT_STOP','RETRACT','WAIT_RESUME'):
                action=[1.,-1.,1.,-1.];masked.append(i)
                if snap['residual_enabled']:raise ValueError('Recovery permission open')
                log=c['result']['action_log']
                for key,width in (('applied_residual',6),('experience_action',4),('effective_command_delta',6)):
                    same(log[key],[0.]*width,'recovery mask.'+key)
            elif pulse is None and snap['residual_enabled'] and snap['state']['phase']=='RUNNING' and snap['controller_state']['phase']=='SEARCH' and snap['controller_state']['search_count']==2:
                pulse=i;action=[.1,-.1,.1,-.1]
        same(action,c['requested'],'recovery request sequence');actions.append(action)
    recovery=audit_recovery_transitions(raw,trigger,pulse,masked,same)
    return dict(expected_actions=actions,recovery=recovery)

def audit_recovery_transitions(raw,trigger,pulse,masked,same):
    transitions=raw.get('recovery_transitions')
    if not isinstance(transitions,list):raise ValueError('Missing recovery transitions')
    rows=raw['cycles'];records=raw['observations']
    accepted=[];resumed=[];last=-1
    for item in transitions:
        i=item['cycle_id'];snap=item['snapshot'];live=item['live']
        if type(i) is not int or not last<=i<=len(rows) or live is None:raise ValueError('Invalid recovery transition')
        expected=rows[i]['before'] if i<len(rows) else rows[-1]['after']
        same(snap,expected,'recovery transition snapshot');same(live['time_s'],snap['time_s'],'transition live time')
        state,count,search=item['signature'];ctx=records[i]['context']
        same([state,count,search],[ctx['recovery_state'],ctx['recovery_count'],snap['controller_state']['search_count']],'transition signature')
        if count not in (0,1) or search>2:raise ValueError('Recovery count exceeded')
        if state=='RETRACT':accepted.append(item)
        if state is None and count==1 and search==2 and snap['state']['phase']=='RUNNING':resumed.append(item)
        last=i
    retraction=None;reference_ok=False;net_ok=False
    if resumed:
        if len(resumed)!=1 or len(accepted)!=1:raise ValueError('Repeated or missing real recovery')
        start=accepted[0];end=resumed[0]
        if not start['cycle_id']<end['cycle_id']:raise ValueError('Resume without measured interval')
        live=end['live'];ss=end['snapshot'];ctrl=ss['controller_state']
        same(start['live']['recovery_start'],live['recovery_start'],'fixed actual retraction origin')
        retraction=live['recovery_start'][2]-live['qpos'][2]
        if retraction<.0002:raise ValueError('Insufficient actual retraction')
        same(live['reference'],live['qpos'],'resumed reference reanchor');same(live['command'],[0.]*6,'resumed zero command')
        source=records[end['cycle_id']]['snapshot']
        same(source['state']['reference_qpos'],live['reference'],'fresh resumed observation reference')
        same(source['state']['limited_command_world'],live['command'],'fresh resumed observation command')
        same(ctrl['search_origin'],[v-o for v,o in zip(ss['state']['position_m'],raw['initial']['position_m'])],'second SEARCH sensed origin')
        z=ss['state']['position_m'][2]-raw['initial']['position_m'][2]
        same(ctrl['search_progress_origin_z_m'],max(ctrl['episode_peak_z_m'],z),'net advance origin')
        reference_ok=True;net_ok=True
        if trigger is not None:
            if pulse!=end['cycle_id']:raise ValueError('Missing first enabled resumed pulse')
            pulse_effect=rows[pulse]['result']['action_log']['effective_command_delta']
            if not nonzero(pulse_effect):return dict(applicable=True,covered=False,reason='NO_EFFECT_AFTER_RESUME',actual_retraction_m=retraction)
    return dict(applicable=True,covered=bool(trigger is not None and masked and resumed and reference_ok and net_ok),
        trigger_cycle=trigger,masked_cycles=len(masked),resumed_pulse_cycle=pulse,actual_retraction_m=retraction,
        reference_reanchored=reference_ok,net_advance_origin_verified=net_ok,
        natural_recovery_probability_claim=False,learning_data_eligible=False)

def matrix_route(rows):
    if len(rows)!=12 or any(not healthy(r) for r in rows):return 'NO_SCOPE_QUALIFICATION'
    if any(r['outcome']['task_outcome']=='TASK_FAILURE' for r in rows):return 'REVIEW_TASK_FAILURE_NO_TRAINING'
    for r in rows:
        if r['profile']=='R_RECOVERY':
            if not r['recovery']['covered']:return 'INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS'
        else:
            c=r['joint_coverage']
            if not all(c['hold_contact_effect_cycles'].values()) or not c['peaks']['force_N']['covered']:
                return 'INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS'
    for case in ('J01','J02','J03','J04'):
        arms=[r for r in rows if r['case_id']==case and r['profile']!='R_RECOVERY']
        for axis in range(4):
            if set().union(*(set(r['joint_coverage']['signs'][axis]) for r in arms))!={-1,1}:
                return 'INSUFFICIENT_COVERAGE_NO_EXTRA_ATTEMPTS'
    return 'READY_FOR_SEPARATE_SAC_REGISTRATION'
