"""Byte-pinned N2 session-archive integrity and sampled stop mathematics.

This auditor reads supplied bytes only. It does not reconstruct contacts or all
native substeps, certify geometric success, admit training, or import numerical
libraries. It supports the completed N2 diagnostic session archive layout,
not force-hold probes or a future training-episode format.
"""
from copy import deepcopy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re


class AuditError(ValueError):
    def __init__(self, code, message):
        self.code = code
        super().__init__(code+': '+message)


def _fail(code, message): raise AuditError(code, message)


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(value): return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def _finite(value):
    if isinstance(value,dict):
        if 'nonfinite' in value: _fail('NONFINITE_EVIDENCE','Archived nonfinite marker')
        for item in value.values(): _finite(item)
    elif isinstance(value,(list,tuple)):
        for item in value: _finite(item)
    elif isinstance(value,float) and not math.isfinite(value):
        _fail('NONFINITE_EVIDENCE','Nonfinite number')


def _number(value):
    if type(value) not in (int,float) or not math.isfinite(value):
        _fail('MALFORMED_EVIDENCE','Finite numeric scalar required')
    return value


def _vector(value,n):
    if not isinstance(value,list) or len(value)!=n:
        _fail('MALFORMED_EVIDENCE','Wrong vector width')
    for item in value: _number(item)
    return value


def _norm(values): return math.sqrt(sum(x*x for x in values))


def _close(a,b,absolute=1e-9,relative=1e-9):
    return math.isclose(_number(a),_number(b),abs_tol=absolute,rel_tol=relative)


def _check_pin(data,pin,name):
    if (not isinstance(pin,str) or re.fullmatch('[0-9a-f]{64}',pin) is None or
        hashlib.sha256(data).hexdigest()!=pin):
        _fail('BYTE_PIN_MISMATCH',name+' pin differs')


def _loads(data):
    def bad_constant(value): _fail('NONFINITE_EVIDENCE','JSON constant '+value)
    try: return json.loads(data,parse_constant=bad_constant)
    except (json.JSONDecodeError,UnicodeError) as exc:
        _fail('MALFORMED_EVIDENCE','Invalid JSON: '+str(exc))


def _domain(receipt):
    common={k:deepcopy(receipt[k]) for k in ('variant','profile','dynamic_config','effective_kd',
        'controller_config','admittance_config','model_xml_sha256','actual_model','runtime')}
    common['schema']=deepcopy(receipt['observation_schema'])
    return common


def _validate_domain(common):
    # The sibling contract has only standard-library imports and no I/O on
    # import. Reuse its schema/parameter checks, never its admission identity.
    path=Path(__file__).with_name('newton_contract.py')
    spec=importlib.util.spec_from_file_location('_n2_integrity_contract',path)
    contract=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    contract._validate_common(common)


def _stop_math(raw,receipt,dt,control_period):
    end=receipt['audit_end_time_s'];events=raw['events'];samples=raw['stop_samples']
    start=None;phase=None;previous=-math.inf
    for event in events:
        now=_number(event['time_s'])
        if now<previous or now<0 or now>end+dt/2:
            _fail('STOP_NOT_QUALIFIED','Invalid event time order')
        previous=now
        current=event.get('phase')
        if current is None: continue
        if current not in ('RUNNING','STOPPING','RETRACT','TERMINAL'):
            _fail('STOP_NOT_QUALIFIED','Unknown physical event phase')
        if current=='STOPPING':
            if phase!='STOPPING': start=now
        else: start=None
        phase=current
    if (start is None or phase!='STOPPING' or raw['trace'][-1]['phase']!='STOPPING' or
        not _close(start,receipt['stop_time_s']) or end<start+2.-1e-8):
        _fail('STOP_NOT_QUALIFIED','No final two-second physical stopping interval')
    previous=-math.inf;by_step={}
    for row in samples:
        now=_number(row['time_s']);linear=_number(row['linear_m_s']);angular=_number(row['angular_rad_s'])
        if now<=previous or linear<0 or angular<0 or now<0 or now>end+dt/2:
            _fail('STOP_NOT_QUALIFIED','Invalid raw stopping sample')
        previous=now;step=round(now/dt)
        if not _close(now,step*dt,absolute=1e-8,relative=0):
            _fail('STOP_NOT_QUALIFIED','Stopping sample is off the native clock')
        by_step[step]=row
    final=[r for r in samples if r['time_s']>start+dt/2]
    expected=round((end-start)/dt)
    if (not final or len(final)!=expected or not _close(final[0]['time_s'],start+dt) or
        not _close(final[-1]['time_s'],end)):
        _fail('STOP_NOT_QUALIFIED','Final native stop segment is incomplete')
    for a,b in zip(final,final[1:]):
        if not _close(b['time_s']-a['time_s'],dt,absolute=dt*.01,relative=0):
            _fail('STOP_NOT_QUALIFIED','Native stopping sample gap')
    def tail_pass(stop_end):
        bounded=[r for r in final if r['time_s']<=stop_end+dt/2]
        tail=[r for r in bounded if r['time_s']>=stop_end-.1-dt/2]
        if (not tail or tail[0]['time_s']>stop_end-.1+dt/2 or
            abs(tail[-1]['time_s']-stop_end)>dt/2): return False
        return all(r['linear_m_s']<=1e-5 and r['angular_rad_s']<=.001 for r in tail)
    if not tail_pass(start+2.) or not tail_pass(end):
        _fail('STOP_NOT_QUALIFIED','Raw samples fail the 100ms stable stop tail')
    # Control-rate qvel independently corroborates native stop speed samples.
    checked=0
    for row in raw['trace']:
        if row['phase']!='STOPPING': continue
        step=round(row['time_s']/dt)
        sample=by_step.get(step)
        if sample is None:
            # The phase-entry control row precedes the first stopped substep.
            if any(_close(row['time_s'],e['time_s']) and e.get('phase')=='STOPPING' for e in events):
                continue
            _fail('STOP_NOT_QUALIFIED','Missing control/native stopping cross-check')
        velocity=row['velocity_world']
        if (not _close(_norm(velocity[:3]),sample['linear_m_s'],absolute=1e-12) or
            not _close(_norm(velocity[3:]),sample['angular_rad_s'],absolute=1e-12)):
            _fail('STOP_NOT_QUALIFIED','Native stop speeds disagree with recorded qvel')
        checked+=1
    return dict(start_time_s=start,deadline_s=start+2.,end_time_s=end,
                final_native_samples=len(final),control_native_cross_checks=checked)


def _observation(vector,trace,index,slices):
    _vector(vector,137)
    if any(abs(x)>10 for x in vector): _fail('OBSERVATION_MISMATCH','Observation outside bounds')
    for name in ('policy_phase','physical_phase','recovery_phase','decision'):
        values=vector[slices[name]]
        if any(x not in (0,1) for x in values) or sum(values)!=1:
            _fail('OBSERVATION_MISMATCH','Invalid one-hot '+name)
    for name,span in slices.items():
        if name.endswith('_valid') or name in ('pending','action_active','simulation_valid','invalid_latched','latched_guards','reference_release_pending'):
            if any(x not in (0,1) for x in vector[span]):
                _fail('OBSERVATION_MISMATCH','Invalid boolean '+name)
    if bool(vector[slices['pending']][0])!=(vector[slices['decision']][0]==0):
        _fail('OBSERVATION_MISMATCH','Decision and pending disagree')
    active=(vector[slices['policy_phase']][0]==1 or vector[slices['policy_phase']][2]==1)
    active=bool(active and vector[slices['physical_phase']][0]==1 and
        not vector[slices['pending']][0] and vector[slices['simulation_valid']][0]==1 and
        not any(vector[slices['latched_guards']]) and not vector[slices['invalid_latched']][0])
    if bool(vector[slices['action_active']][0])!=active:
        _fail('OBSERVATION_MISMATCH','F50 same-cycle action permission differs')
    history=[]
    for lag in range(4): history.extend(trace[max(0,index-lag)]['contact_wrench_M'])
    expected=[max(-10.,min(10.,x/s)) for x,s in zip(history,([5.]*3+[.1]*3)*4)]
    actual=vector[slices['wrench_history_M']]
    if any(not _close(a,b,absolute=1e-6,relative=1e-7) for a,b in zip(actual,expected)):
        _fail('OBSERVATION_MISMATCH','Four-sample raw N/Nm history or normalization differs')
    expected=[(v-i)/.004 for v,i in zip(trace[index]['position_m'],trace[0]['position_m'])]
    expected=[max(-10.,min(10.,v)) for v in expected]
    if any(not _close(a,b,absolute=1e-6,relative=1e-7) for a,b in zip(vector[slices['relative_position_m']],expected)):
        _fail('OBSERVATION_MISMATCH','Relative position differs from physical trace')
    return active


def _audit(raw,receipt,common,expected_case):
    trace,actions,transitions=raw['trace'],raw['actions'],raw['transitions']
    d=common['dynamic_config'];dt=d['timestep'];period=d['control_period']
    cycles=len(transitions);steps=round(period/dt)
    if (not 0<cycles<=14500 or len(trace)!=cycles+1 or len(actions)!=cycles or
        receipt['physical_substeps']!=cycles*steps or type(receipt['physical_substeps']) is not int or
        receipt['guard_facts']['checked_substeps']!=cycles*steps):
        _fail('STEP_COUNT_MISMATCH','Control trace, native steps or checked steps differ')
    if receipt.get('status')!='finished' or receipt.get('kind') not in ('anchor','baseline'):
        _fail('UNSUPPORTED_ARCHIVE','Completed N2 session archive required')
    if any(type(receipt.get(k)) is not int or receipt[k]!=0 for k in ('policy_calls','training_updates')):
        _fail('BASELINE_POLICY_MISMATCH','This diagnostic format requires zero policy calls and training updates')
    for i,row in enumerate(trace):
        if not _close(row['time_s'],i*period,absolute=1e-8,relative=0):
            _fail('TRACE_CLOCK_MISMATCH','Missing/reordered control cycle')
        _vector(row['position_m'],3);_vector(row['velocity_world'],6)
        for key in ('contact_wrench_M','contact_wrench_G','limited_command_world'):_vector(row[key],6)
        if not _close(_norm(_vector(row['quaternion_wxyz'],4)),1.,absolute=1e-6):
            _fail('TRACE_POSE_MISMATCH','Quaternion is not normalized')
        if row['phase'] not in ('RUNNING','STOPPING','RETRACT','TERMINAL'):
            _fail('TRACE_PHASE_MISMATCH','Unknown physical trace phase')
    if (not _close(trace[-1]['time_s'],receipt['audit_end_time_s']) or
        not _close(trace[0]['position_m'][2],-.005) or trace[0]['phase']!='RUNNING'):
        _fail('TRACE_CLOCK_MISMATCH','Wrong initial Z or final audit time')
    pose_bound=False
    if expected_case is not None:
        p=expected_case
        if p['start_origin_z_m']!=-.005 or p['target_depth_m']!=.005:
            _fail('CASE_MISMATCH','N2 target travel and starting Z differ')
        wanted=[p['x_um']*1e-6,p['y_um']*1e-6,-.005]
        r=math.radians(p['roll_deg'])/2;pitch=math.radians(p['pitch_deg'])/2
        q=[math.cos(pitch)*math.cos(r),math.cos(pitch)*math.sin(r),
           math.sin(pitch)*math.cos(r),-math.sin(pitch)*math.sin(r)]
        actual=trace[0]['quaternion_wxyz']
        if (any(not _close(a,b,absolute=1e-12) for a,b in zip(wanted,trace[0]['position_m'])) or
            min(max(abs(a-b) for a,b in zip(actual,q)),max(abs(a+b) for a,b in zip(actual,q)))>1e-12):
            _fail('CASE_MISMATCH','Actual first trace pose differs from expected physical case')
        pose_bound=True
    stop=_stop_math(raw,receipt,dt,period)
    facts=receipt['guard_facts']
    if type(receipt.get('valid')) is not bool or type(facts.get('simulation_valid')) is not bool:
        _fail('OUTCOME_MISMATCH','Boolean validity facts required')
    if receipt['valid']!=facts['simulation_valid'] or not receipt['valid'] or facts['invalid_reasons']:
        _fail('INVALID_SIMULATION_RECORDED','Invalid simulation cannot be counted as ordinary failure')
    if receipt.get('stopped') is not True:
        _fail('STOP_NOT_QUALIFIED','Claimed stop contradicts recomputed raw stop')
    sampled_force=max(_norm(r['contact_wrench_M'][:3]) for r in trace)
    sampled_torque=max(_norm(r['contact_wrench_G'][3:]) for r in trace)
    penetration=max(r['penetration_m'] for r in trace)
    sampled_speed=max(_norm(r['velocity_world'][:3]) for r in trace)
    sampled_angular=max(_norm(r['velocity_world'][3:]) for r in trace)
    slices={f['name']:slice(f['start'],f['start']+f['width']) for f in common['schema']}
    maximum=0.;previous=None;cycle_force=cycle_torque=cycle_penetration=0.
    terminal_values=dict(FULL_SUCCESS=10.,TASK_FAILURE=-2.,CONTACT_GUARD=-10.,MOTION_VIOLATION=-10.)
    outcome=receipt['outcome']
    if outcome not in terminal_values:_fail('OUTCOME_MISMATCH','Unsupported completed-session outcome')
    for i,(row,log) in enumerate(zip(transitions,actions)):
        active=_observation(row['observation'],trace,i,slices)
        _observation(row['next_observation'],trace,i+1,slices)
        if previous is not None and row['observation']!=previous:
            _fail('OBSERVATION_MISMATCH','Observation chain is discontinuous')
        previous=row['next_observation']
        if not _close(row['dt'],trace[i+1]['time_s']-trace[i]['time_s'],absolute=1e-12):
            _fail('TRACE_CLOCK_MISMATCH','Transition dt differs from actual trace')
        request=_vector(log['raw_action'],4);experience=_vector(log['experience_action'],4)
        if any(value!=0. for value in request+experience):
            _fail('BASELINE_POLICY_MISMATCH','Pure traditional archives require explicit zero residual requests and experience')
        if (type(log['enabled']) is not bool or log['enabled']!=active or
            any(abs(x)>1 for x in request) or experience!=(request if active else [0.]*4)):
            _fail('ACTION_MISMATCH','Action permission or experience differs')
        if ('action' in row and _vector(row['action'],4)!=experience or
            'action_log' in row and canonical(row['action_log'])!=canonical(log) or
            'action_active' in row and (type(row['action_active']) is not bool or row['action_active']!=active)):
            _fail('ACTION_MISMATCH','Transition action copy differs from the zero residual log')
        if log['actual_end_limited_command']!=trace[i+1]['limited_command_world']:
            _fail('ACTION_MISMATCH','Action log differs from actual drive command')
        peaks=row['cycle_peaks']
        if peaks['samples']!=steps or min(peaks['force_N'],peaks['torque_G_Nm'],peaks['penetration_m'])<0:
            _fail('STEP_COUNT_MISMATCH','Cycle native samples or loads differ')
        # The endpoint is the final substep of THIS cycle. Its start belongs
        # to the preceding cycle and must not be imposed as a lower bound.
        endpoint=trace[i+1]
        endpoint_loads=dict(force_N=_norm(endpoint['contact_wrench_M'][:3]),
            torque_G_Nm=_norm(endpoint['contact_wrench_G'][3:]),penetration_m=endpoint['penetration_m'])
        for key,value in endpoint_loads.items():
            if peaks[key]<value-(1e-12+1e-9*abs(value)):
                _fail('CYCLE_PEAK_MISMATCH','Cycle load maximum omits its own endpoint: '+key)
        cycle_force=max(cycle_force,peaks['force_N']);cycle_torque=max(cycle_torque,peaks['torque_G_Nm'])
        cycle_penetration=max(cycle_penetration,peaks['penetration_m'])
        progress=trace[i+1]['position_m'][2]-trace[0]['position_m'][2]
        nextmax=max(maximum,min(.005,max(0.,progress)))
        terms=dict(progress=5*(nextmax-maximum)/.005,time=-.1*row['dt'],
            force=-.2*row['dt']*(peaks['force_N']/5.)**2,
            torque=-.2*row['dt']*(peaks['torque_G_Nm']/.1)**2,
            terminal=terminal_values[outcome] if i==cycles-1 else 0.)
        terms['total']=sum(terms.values());maximum=nextmax
        if set(terms)!=set(row['reward_terms']) or any(not _close(v,row['reward_terms'][k],absolute=1e-9) for k,v in terms.items()):
            _fail('REWARD_MISMATCH','Raw progress/load/terminal reward accounting differs')
    peaks=receipt['peaks']
    for key,value in (('force_N',max(sampled_force,cycle_force)),('torque_G_Nm',max(sampled_torque,cycle_torque)),
                      ('penetration_m',max(penetration,cycle_penetration)),('speed_m_s',sampled_speed)):
        if peaks[key]+1e-10<value:_fail('PEAK_MISMATCH','Receipt peak omits recorded evidence: '+key)
    for key,value in (('force_N',cycle_force),('torque_G_Nm',cycle_torque),('penetration_m',cycle_penetration)):
        if not _close(peaks[key],value,absolute=1e-12):
            _fail('PEAK_MISMATCH','Receipt load maximum differs from complete cycle aggregation: '+key)
    observed_contact=(max(sampled_force,cycle_force,peaks['force_N'])>d['stop_force_N']+1e-10 or
        max(sampled_torque,cycle_torque,peaks['torque_G_Nm'])>d['stop_torque_Nm']+1e-10 or
        max(penetration,cycle_penetration,peaks['penetration_m'])>d['stop_penetration_m']+1e-10)
    # The native speed maximum is not independently reconstructed here, but
    # it must not contradict an empty motion-guard summary between 2ms rows.
    observed_motion=(max(sampled_speed,peaks['speed_m_s'])>d['actual_speed_limit']+1e-10 or
                     sampled_angular>d['actual_angular_speed_limit']+1e-10)
    if (observed_contact and not facts['contact_reasons']) or (observed_motion and not facts['motion_reasons']):
        _fail('GUARD_EVIDENCE_MISMATCH','Recorded loads/velocity contradict empty guard facts')
    contact=bool(facts['contact_reasons']);motion=bool(facts['motion_reasons'])
    classified=('CONTACT_GUARD' if contact else 'MOTION_VIOLATION' if motion else
                'FULL_SUCCESS' if receipt.get('final_reason')=='GEOMETRIC_SUCCESS' else 'TASK_FAILURE')
    if classified!=outcome:_fail('OUTCOME_MISMATCH','Failure/guard/success category disagrees with recorded facts')
    task_time=_number(receipt['task_time_s'])
    if (task_time<receipt['stop_time_s']-1e-9 or task_time>receipt['audit_end_time_s']+1e-9 or
        task_time<0 or task_time>26.+1e-9):
        _fail('METRIC_MISMATCH','Task decision time is outside its recorded stopping interval')
    expected_score=task_time if outcome=='FULL_SUCCESS' else 26.
    if not _close(receipt['scored_time_s'],expected_score):
        _fail('METRIC_MISMATCH','Success time or 26s failure penalty is inconsistent')
    healthy=not contact and not motion
    if receipt.get('healthy') is not healthy or receipt.get('audit_passed') is not True:
        _fail('OUTCOME_MISMATCH','Summary health/audit flag contradicts recomputed checks')
    return dict(integrity_passed=True,recorded_outcome=outcome,control_cycles=cycles,
        physical_substeps=cycles*steps,stop_samples_recomputed=True,stop_audit=stop,
        initial_pose_recomputed=pose_bound,wrench_history_recomputed=True,
        reward_accounting_recomputed=True,full_observation_recomputed=False,
        full_physical_audit_complete=False,all_substep_guards_recomputed=False,
        geometric_success_recomputed=False,training_admitted=False,
        scope='archive_integrity_control_trace_and_sampled_stop_math_only')


def audit_bytes(receipt_data,episode_data,*,expected_receipt_sha256,expected_episode_sha256,
                expected_common,expected_common_sha256,expected_case=None):
    """Audit supplied pinned bytes; failures have explicit AuditError.code."""
    if not isinstance(receipt_data,bytes) or not isinstance(episode_data,bytes):
        _fail('MALFORMED_EVIDENCE','Exact receipt/archive bytes are required')
    _check_pin(receipt_data,expected_receipt_sha256,'receipt')
    _check_pin(episode_data,expected_episode_sha256,'episode')
    _check_pin(canonical(expected_common).encode('utf-8'),expected_common_sha256,'common domain')
    try:
        external=_loads(receipt_data);raw=_loads(gzip.decompress(episode_data))
        _finite(external);_finite(raw)
        receipt=raw['receipt']
        if (not isinstance(receipt,dict) or not isinstance(external,dict) or
            any(k not in external or canonical(v)!=canonical(external[k]) for k,v in receipt.items())):
            _fail('RECEIPT_MISMATCH','External and embedded receipt cores differ')
        extras=set(external)-set(receipt)
        if any(k not in ('archive','supervisor') and not k.startswith(('archive_','supervisor_')) for k in extras):
            _fail('RECEIPT_MISMATCH','Unknown external-only receipt fields')
        if 'archive_sha256' in external and external['archive_sha256']!=expected_episode_sha256:
            _fail('BYTE_PIN_MISMATCH','External archive hint differs')
        common=_domain(receipt);_validate_domain(common)
        if canonical(common)!=canonical(expected_common):
            _fail('DOMAIN_MISMATCH','Actual schema/model/controller/drive domain changed')
        result=_audit(raw,receipt,common,expected_case)
        result.update(receipt_sha256=expected_receipt_sha256,episode_sha256=expected_episode_sha256,
                      common_sha256=expected_common_sha256,external_only_fields=sorted(extras))
        return result
    except AuditError: raise
    except (KeyError,TypeError,IndexError,OverflowError,OSError,EOFError) as exc:
        _fail('INCOMPLETE_EVIDENCE',str(exc))
