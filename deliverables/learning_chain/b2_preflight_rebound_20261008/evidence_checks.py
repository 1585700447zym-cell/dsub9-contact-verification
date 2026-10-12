"""Pure reconciliation of frozen guards and observed information; no inference."""
import math
from types import SimpleNamespace
from scope_contract import canonical


def guard_evidence(raw,common,n):
    np=n['np'];facts=raw['guard_facts'];steps=raw['physical_substeps'];peaks=raw['peaks'];config=common['dynamic_config']
    if type(facts.get('checked_substeps')) is not int or facts['checked_substeps']!=steps:
        raise ValueError('Missing/contradictory substep guard sampling')
    categories={**{k:'contact_reasons' for k in ('FORCE_LIMIT','TORQUE_LIMIT','PENETRATION_LIMIT')},
                **{k:'motion_reasons' for k in ('SPEED_LIMIT','ANGULAR_SPEED_LIMIT','TRAVEL_LIMIT','ROTATION_LIMIT')}}
    reasons=facts['contact_reasons']+facts['motion_reasons'];events=set()
    for key in ('contact_reasons','motion_reasons','invalid_reasons'):
        if not isinstance(facts[key],list) or len(facts[key])!=len(set(facts[key])):raise ValueError('Malformed guard reasons')
    for reason in reasons:
        if reason not in categories or reason not in facts[categories[reason]]:raise ValueError('Guard in wrong category')
    for event in raw['events']:
        for token in event['reason'].split('+'):
            token=token.removeprefix('B2_LATCHED_')
            if token in categories:events.add(token)
            if token=='CONTACT_GUARD' and not facts['contact_reasons']:raise ValueError('Unlatched contact event')
            if token=='MOTION_VIOLATION' and not facts['motion_reasons']:raise ValueError('Unlatched motion event')
    if events!=set(reasons):raise ValueError('Guard events and reasons disagree')
    def finite(value):
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:raise ValueError('Invalid guard measurement')
        return value
    checks=[('force_N','stop_force_N','FORCE_LIMIT'),('torque_G_Nm','stop_torque_Nm','TORQUE_LIMIT'),
            ('penetration_m','stop_penetration_m','PENETRATION_LIMIT'),('speed_m_s','actual_speed_limit','SPEED_LIMIT')]
    for key,limit,reason in checks:
        if (finite(peaks[key])>config[limit])!=(reason in reasons):raise ValueError('Peak threshold and guard contradict: '+reason)
    angle=finite(facts['max_rotation_from_start_rad'])
    if angle>math.pi or (angle>common['guard_config']['max_rotation_from_start_rad'])!=('ROTATION_LIMIT' in reasons):
        raise ValueError('Rotation maximum and guard contradict')
    initial=raw['initial']
    for cycle in raw['cycles']:
        row=cycle['result']['trace_row'];p=cycle['result']['cycle_peaks']
        if type(p.get('samples')) is not int or p['samples']!=10:raise ValueError('Incomplete cycle peak samples')
        for key in ('force_N','torque_G_Nm','penetration_m'):
            if finite(p[key])>peaks[key]+1e-12:raise ValueError('Cycle peak exceeds episode peak')
        measured=dict(force_N=float(np.linalg.norm(row['contact_wrench_M'][:3])),
            torque_G_Nm=float(np.linalg.norm(row['contact_wrench_G'][3:])),penetration_m=row['penetration_m'],
            speed_m_s=float(np.linalg.norm(row['velocity_world'][:3])))
        for key,limit,reason in checks:
            if finite(measured[key])>peaks[key]+1e-12:raise ValueError('Sample exceeds reported peak')
            if measured[key]>config[limit] and reason not in reasons:raise ValueError('Unlatched sampled guard')
        angular=finite(float(np.linalg.norm(row['velocity_world'][3:])))
        travel=finite(float(np.linalg.norm(np.array(row['position_m'])-initial['position_m'])))
        rotation=finite(float(np.linalg.norm(n['rotation_vector_world'](initial['quaternion_wxyz'],row['quaternion_wxyz']))))
        if rotation>angle+1e-10:raise ValueError('Sample rotation exceeds recorded substep maximum')
        if angular>config['actual_angular_speed_limit'] and 'ANGULAR_SPEED_LIMIT' not in reasons:raise ValueError('Unlatched angular guard')
        if travel>config['travel_limit_m'] and 'TRAVEL_LIMIT' not in reasons:raise ValueError('Unlatched travel guard')


def observation_evidence(raw,common,n,same):
    records=raw.get('observations');rows=raw['cycles'];np=n['np']
    if not isinstance(records,list) or len(records)!=len(rows)+1:raise ValueError('Missing observation provenance')
    builder=n['V4ObservationBuilder'](raw['initial'],SimpleNamespace(**common['b2_config']))
    signatures=[];initial_vector=None
    for i,record in enumerate(records):
        snapshot=rows[i]['before'] if i<len(rows) else rows[-1]['after']
        if 'policy_observation' not in snapshot or 'policy_raw' not in snapshot:raise ValueError('Missing policy observation evidence')
        source=record['snapshot']
        for key in ('cycle_id','time_s','controller_state','base_command','residual_enabled'):
            same(source[key],snapshot[key],'observation source.'+key)
        # STOP/recovery can rebase the live drive after the physical sensor row.
        # Those two fields are recorded in the actual capture source, not guessed.
        for key in source['state']:
            if key not in ('reference_qpos','limited_command_world'):
                same(source['state'][key],snapshot['state'][key],'observation sensor.'+key)
        vector,policy_raw=builder.capture(SimpleNamespace(**source),record['context'],refresh=True)
        if vector.shape!=(137,) or not np.isfinite(vector).all():raise ValueError('Wrong observation schema/vector')
        same(builder.schema,raw.get('observation_schema'),'frozen observation schema')
        same(vector.tolist(),snapshot['policy_observation'],'recomputed policy vector',1e-7)
        same(policy_raw,snapshot['policy_raw'],'recomputed policy raw',1e-12)
        if initial_vector is None:initial_vector=vector.tolist()
        sensor=source['state'];context=record['context'];facts=context['guard_facts']
        expected_active=bool(source['controller_state']['phase'] in ('INSERT','SEARCH') and sensor['phase']=='RUNNING'
            and context['reason'] is None and not facts['contact_reasons'] and not facts['motion_reasons'])
        if source['residual_enabled']!=expected_active:raise ValueError('Observation permission contradicts context')
        clipping=sum(int(abs(v/s)>10.) for item in builder.schema for v,s in zip(policy_raw[item['name']],item['scale']))
        signatures.append(dict(time_s=source['time_s'],contact_count=sensor['contact_count'],
            features=policy_raw['wrench_history_M'][:6]+policy_raw['relative_position_m']+policy_raw['relative_rotation_world_rad'],
            clipped_components=clipping))
    first=next((i for i,row in enumerate(signatures) if row['contact_count']>0),None)
    prior=signatures[first-1] if first is not None and first>0 else None
    contact=signatures[first] if first is not None else None
    delta=None if prior is None else [a-b for a,b in zip(contact['features'],prior['features'])]
    informative=delta is not None and any(value!=0 for value in delta)
    return dict(schema_version='residual_reference_whitelist_v4',vectors_verified=len(records),width=137,
        initial_vector=initial_vector,precontact=prior,first_contact=contact,contact_feature_delta=delta,
        contact_information='OBSERVED_DIFFERENCE' if informative else 'INSUFFICIENT_COVERAGE',
        limitation='Exact recorded feature differences only; significance/observability and causal benefit are not established')
