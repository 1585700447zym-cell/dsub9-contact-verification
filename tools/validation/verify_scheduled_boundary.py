"""Eight preregistered time-varying development probes. NEVER grants admission."""
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from copy import deepcopy
import gzip
import json
import math
import time
import numpy as np

from tools.learning.runtime import ROOT, verify_runtime
verify_runtime(ROOT / 'tmp/mujoco_3_13_probe')
from tools.learning.action import normalized_action
from tools.learning.episode_buffer import _safe_error_archive
from tools.learning.guarded_environment import GuardCandidateConfig, LearningEnvironment, relative_rotation_rad
from tools.learning.residual_session import ResidualSession
from tools.validation.run_contact_cases import ContactCase
from tools.validation.guard_evidence import input_fingerprints, snapshot_inputs
from tools.validation.verify_engineering_domain import fresh_output, WATCHDOG_CYCLES

SEED = 2026092608


def build_protocol():
    attempts = []
    def add(name, x, y, rotation, translations, family):
        schedule = [dict(start_cycle=c, action=list(xy) + list(rotation))
                    for c, xy in zip((0,250,500,1000), translations)]
        attempts.append(dict(id=name, family=family,
            case=dict(name=name, x_offset_m=x, y_offset_m=y, roll_rad=0., pitch_rad=0.,
                      start_origin_z_m=-.004, target_depth_m=.004), schedule=schedule))
    for axis, name in enumerate(('roll','pitch')):
        for sign, label in ((-1,'neg'),(1,'pos')):
            rotation=[0,0]; rotation[axis]=sign
            xy=[0,0]; xy[1-axis]=sign
            add(f'center_{name}_{label}',0.,0.,rotation,
                ([0,0],xy,[-v for v in xy],[0,0]),'center_signed_rotation')
    for i,(x,y) in enumerate(((-1,-1),(-1,1),(1,-1),(1,1))):
        add(f'corner_{i}',x*50e-6,y*50e-6,[x,y],
            ([x,y],[-x,-y],[x,y],[0,0]),'corner_coupled_rotation')
    return dict(version='scheduled_boundary_v1', seed=SEED, data_use='development_only',
        guard_config=dict(max_rotation_from_start_rad=math.radians(2.5),
                          initial_roll_pitch_limit_rad=math.radians(1.5)),
        timestep_s=.0002, control_period_s=.002, watchdog_cycles=WATCHDOG_CYCLES,
        attempts=attempts, training_admitted=False, parameter_frozen=False,
        model_scope_qualified=False, maximum_complete_attempts=8,
        termination='original lifecycle and actual stop; no resampling or forced boundary coverage')


def validate_schedule(schedule):
    if not isinstance(schedule,list) or not schedule:
        raise ValueError('Nonempty schedule required')
    previous=-1
    for segment in schedule:
        cycle=segment['start_cycle']
        if type(cycle) is not int or cycle<=previous or cycle>=WATCHDOG_CYCLES:
            raise ValueError('Strictly increasing integer cycle schedule required')
        normalized_action(segment['action'])
        previous=cycle
    if schedule[0]['start_cycle']!=0:
        raise ValueError('Schedule must begin at cycle zero')


def action_for_cycle(schedule, cycle):
    if type(cycle) is not int or cycle<0:
        raise ValueError('Nonnegative integer cycle required')
    # The runner validates the immutable schedule once, before interaction.
    for segment in reversed(schedule):
        if cycle>=segment['start_cycle']:
            return list(segment['action'])
    raise ValueError('No schedule segment')


class BoundaryEnvironment(LearningEnvironment):
    """Post-guard observer only; never mutates a sample or physical command."""
    def reset(self, case, *, allow_initial_contact=False):
        self.boundary_observations=[]
        return super().reset(case,allow_initial_contact=allow_initial_contact)

    def _guard(self,row):
        before=tuple(tuple(self._facts[k]) for k in ('invalid_reasons','contact_reasons','motion_reasons'))
        super()._guard(row)
        after=tuple(tuple(self._facts[k]) for k in ('invalid_reasons','contact_reasons','motion_reasons'))
        if before!=after:
            rotation_new='ROTATION_LIMIT' in after[2] and 'ROTATION_LIMIT' not in before[2]
            self.boundary_observations.append(dict(time_s=float(self.data.time),
                rotation_trigger=rotation_new, contact_at_trigger=bool(row['contact_count']>0),
                rotation_deg=math.degrees(relative_rotation_rad(self.initial[3:],row['quaternion_wxyz'])),
                physical=deepcopy(row), guard_facts=self.guard_facts))


def write_json_new(path,value):
    text=json.dumps(_safe_error_archive(value),ensure_ascii=False,allow_nan=False,indent=2)+'\n'
    with path.open('x',encoding='utf-8') as handle:
        handle.write(text)


def run_attempt(spec, *, watchdog_cycles=WATCHDOG_CYCLES):
    started=time.perf_counter()
    report=dict(id=spec['id'],spec=deepcopy(spec),runtime=verify_runtime(ROOT/'tmp/mujoco_3_13_probe'),
        initialization_valid=False,simulation_valid=False,physical_stopped=False,completed=False,
        observation_valid=True,masking_valid=True,schedule_valid=True,error=None,trace=[],
        active_cycles=0,masked_cycles=0,contact_cycles=0,command_effect_cycles=0,
        rotation_guard_observations=[],diagnostic_failures=[],adjudication_status='unavailable',
        training_admitted=False,model_scope_qualified=False,valid_for_learning=False)
    session=None
    def valid_observation(snapshot):
        obs=np.asarray(snapshot.policy_observation)
        return bool(obs.shape==(120,) and np.isfinite(obs).all() and np.all(obs>=-10) and np.all(obs<=10))
    def advance(action,source,index):
        result=session.advance_cycle(action)
        log=result.action_log
        mask_good=bool(log['enabled'] or not(any(log['experience_action']) or any(log['applied_residual'])))
        obs_good=valid_observation(result.next_snapshot)
        request_good=log['raw_action']==action
        report['active_cycles' if log['enabled'] else 'masked_cycles']+=1
        report['contact_cycles']+=int(result.trace_row['contact_count']>0)
        report['command_effect_cycles']+=int(any(abs(v)>1e-15 for v in log['effective_command_delta']))
        report['masking_valid'] &= mask_good
        report['observation_valid'] &= obs_good
        report['schedule_valid'] &= request_good
        report['trace'].append(dict(cycle_index=index,source=source,request=list(action),
            physical=result.trace_row,action_log=log,cycle_peaks=result.cycle_peaks,
            reward=result.reward_terms,dt=result.dt,task_finished=result.task_finished,done=result.done))
        if not(mask_good and obs_good and request_good):
            report['diagnostic_failures'].append(_safe_error_archive(dict(cycle_index=index,
                next_snapshot=vars(result.next_snapshot),action_log=log,
                observation_valid=obs_good,masking_valid=mask_good,request_valid=request_good)))
            raise ValueError('Invalid current observation, permission or request diagnostic')
    def emergency_stop():
        if session is not None and session._ready and not session.done:
            session.start_external_tail()
            for _ in range(1500):
                if session.done: break
                advance([0.]*4,'diagnostic_stop',len(report['trace']))
        if session is not None and session._ready:
            report['physical_stopped']=session.adjudicate()['physical_stopped']
    try:
        validate_schedule(spec['schedule'])
        session=ResidualSession(environment=BoundaryEnvironment(
            guard_config=GuardCandidateConfig(**build_protocol()['guard_config'])))
        initial=session.reset(ContactCase(**spec['case']),seed=SEED)
        report.update(initialization_valid=True,initial_state=initial.state,
            environment=session.env.metadata(),initial_policy_observation=initial.policy_observation)
        report['observation_valid']=valid_observation(initial)
        if not report['observation_valid']: raise ValueError('Invalid initial observation')
        for index in range(watchdog_cycles):
            if session.done: break
            advance(action_for_cycle(spec['schedule'],index),'schedule',index)
        if not session.done:
            report['error']='WATCHDOG_EXCEEDED'
            emergency_stop()
            if not session.done: report['stop_error']='WATCHDOG_STOP_INCOMPLETE'
        outcome=session.adjudicate()
        report.update(outcome=outcome,task_outcome=outcome['task_outcome'],
            physical_stopped=outcome['physical_stopped'],completed=bool(session.done and report['error'] is None))
    except Exception as exc:
        report['error']=report['error'] or repr(exc)
        report['exception']=repr(exc)
        try: emergency_stop()
        except Exception as stop_exc: report['stop_error']=repr(stop_exc)
    if session is not None:
        e=session.env
        report['interface_fault']=_safe_error_archive(getattr(session,'interface_fault',None))
        try:
            outcome=session.adjudicate()
            report.update(outcome=outcome,task_outcome=outcome['task_outcome'],
                physical_stopped=outcome['physical_stopped'],adjudication_status='available')
        except Exception as exc:
            report['adjudication_error']=repr(exc)
            report['adjudication_status']='unavailable'
            report['physical_stopped']=False
            report['completed']=False
            report['error']=report['error'] or 'ADJUDICATION_UNAVAILABLE'
        observations=deepcopy(getattr(e,'boundary_observations',[]))
        report.update(simulation_valid=e.guard_facts['simulation_valid'],guard_facts=e.guard_facts,
            events=e.events,physical_stop_samples=e.stop_samples,physical_steps=e.physical_steps,
            peaks=e.peaks,end_time_s=float(e.data.time),final_phase=e.phase,
            max_rotation_deg=math.degrees(e.guard_facts['max_rotation_from_start_rad']),
            boundary_observations=observations,
            rotation_guard_observations=[o for o in observations if o['rotation_trigger']])
    segments=[]
    for i,seg in enumerate(spec['schedule']):
        upper=spec['schedule'][i+1]['start_cycle'] if i+1<len(spec['schedule']) else WATCHDOG_CYCLES
        rows=[t for t in report['trace'] if t['source']=='schedule' and seg['start_cycle']<=t['cycle_index']<upper]
        segments.append(dict(start_cycle=seg['start_cycle'],requested_cycles=len(rows),
            enabled_cycles=sum(t['action_log']['enabled'] for t in rows),
            effect_cycles=sum(any(abs(v)>1e-15 for v in t['action_log']['effective_command_delta']) for t in rows)))
    report['segments']=segments
    report['wall_seconds']=time.perf_counter()-started
    return _safe_error_archive(report)


def summarize(protocol,reports,*,source_unchanged):
    planned={s['id']:s for s in protocol['attempts']}
    ids=[r.get('id') for r in reports]
    accounting=len(ids)==len(set(ids))==len(planned) and set(ids)==set(planned)
    checks=[]
    for r in reports:
        good=r.get('spec')==planned.get(r.get('id')) and r.get('id') in planned and r.get('error') is None
        good &= all(r.get(k) is True for k in ('completed','initialization_valid','simulation_valid',
            'physical_stopped','observation_valid','masking_valid','schedule_valid'))
        good &= all(r.get(k) is False for k in ('training_admitted','model_scope_qualified','valid_for_learning'))
        good &= type(r.get('command_effect_cycles')) is int and r['command_effect_cycles']>0
        checks.append(dict(id=r.get('id'),passed=bool(good)))
    return dict(sample_checks_passed=bool(source_unchanged is True and accounting and all(c['passed'] for c in checks)),
        source_unchanged=source_unchanged,accounting_complete=accounting,checks=checks,
        attempts_recorded=len(reports),dynamic_valid_stopped=sum(r.get('simulation_valid') is True and r.get('physical_stopped') is True for r in reports),
        contact_rotation_boundary_cases=sum(any(o['contact_at_trigger'] for o in r.get('rotation_guard_observations',[])) for r in reports),
        rotation_boundary_cases=sum(bool(r.get('rotation_guard_observations')) for r in reports),
        training_admitted=False,parameter_frozen=False,model_scope_qualified=False,
        limitation='Eight finite development probes, no continuous-domain or policy qualification; no automatic freeze.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',required=True)
    parser.add_argument('--workers',type=int,choices=(1,2,3),default=2)
    args=parser.parse_args()
    target=fresh_output(ROOT/'deliverables/residual_interface',args.tag)
    protocol=build_protocol(); hashes=input_fingerprints()
    snapshot_inputs(target,hashes)
    protocol['source_sha256']=hashes
    write_json_new(target/'protocol.json',protocol)  # BEFORE any of the eight runs.
    started=time.perf_counter(); reports=[]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        jobs={pool.submit(run_attempt,s):s for s in protocol['attempts']}
        for future in as_completed(jobs):
            spec=jobs[future]
            try: report=future.result()
            except Exception as exc:
                report=dict(id=spec['id'],spec=spec,error=repr(exc),training_admitted=False,
                    model_scope_qualified=False,valid_for_learning=False)
            raw=json.dumps(_safe_error_archive(report),ensure_ascii=False,allow_nan=False).encode('utf-8')
            with (target/(spec['id']+'.json.gz')).open('xb') as handle:
                handle.write(gzip.compress(raw,mtime=0))
            compact={k:v for k,v in report.items() if k not in ('trace','physical_stop_samples','runtime','environment','initial_policy_observation')}
            reports.append(compact)
            write_json_new(target/(spec['id']+'.summary.json'),compact)
            print(spec['id'],report.get('task_outcome'),'valid=',report.get('simulation_valid'),
                'stopped=',report.get('physical_stopped'),'angle=',report.get('max_rotation_deg'),
                'error=',report.get('error'),flush=True)
    assessment=summarize(protocol,reports,source_unchanged=hashes==input_fingerprints())
    assessment.update(runs=sorted(reports,key=lambda r:r['id']),wall_seconds=time.perf_counter()-started,
                      workers=args.workers,not_a_cost_benchmark=True)
    write_json_new(target/'assessment.json',assessment)
    raise SystemExit(0 if assessment['sample_checks_passed'] else 1)


if __name__=='__main__':
    main()
