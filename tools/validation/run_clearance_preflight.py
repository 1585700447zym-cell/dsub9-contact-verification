"""Bounded development-only B2 preflight. No learned policy, replay or optimizer."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone, timedelta
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
DELIVERY = ROOT/'deliverables/task_variants/clearance120_20261003'


def write(path, value):
    from tools.learning.admitted_collection import _write_json
    _write_json(Path(path), value)


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def case_specs():
    return [dict(id=name, x_um=x, y_um=y) for name,x,y in [
        ('aligned',0,0),('x_pos_100',100,0),('x_neg_100',-100,0),('y_pos_100',0,100),('y_neg_100',0,-100),
        ('x_pos_150',150,0),('x_neg_150',-150,0),('y_pos_150',0,150),('y_neg_150',0,-150)]]


def next_case(entries):
    specs=case_specs()
    if len(entries)>len(specs) or any(e['id']!=specs[i]['id'] for i,e in enumerate(entries)):
        raise RuntimeError('Invalid case order or budget')
    for entry in entries:
        if entry['status']!='finished':
            raise RuntimeError('Unfinished attempt must not be retried')
        outcome=entry['outcome']
        if (outcome['task_outcome'] not in ('FULL_SUCCESS','TASK_FAILURE') or
                outcome['simulation_valid'] is not True or outcome['physical_stopped'] is not True):
            return None
    return specs[len(entries)] if len(entries)<len(specs) else None


def claim_run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    ledger=dict(status='prepared',started_at=now(),episodes=[],max_new_episodes=9,prior_cumulative=109,
                cumulative_limit=118,training_updates=0,policy_calls=0,independent_tests=0,retry_allowed=False)
    write(folder/'ledger.json',ledger)
    return ledger


def archive_episode(path, value):
    from tools.validation.native313_matrix_audit import archive_nonfinite
    data=gzip.compress(json.dumps(archive_nonfinite(value),ensure_ascii=False,allow_nan=False,separators=(',',':')).encode(),mtime=0)
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_bytes(data);os.replace(temporary,path)
    return hashlib.sha256(data).hexdigest()


def input_hashes():
    paths=list((ROOT/'tools').rglob('*.py'))+list((ROOT/'models').rglob('*.xml'))+list((ROOT/'assets').rglob('*.stl'))
    paths += [ROOT/'deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json',
              ROOT/'docs/superpowers/plans/2026-10-03-clearance-task-preflight.md',
              ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json',
              ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/admission.json']
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def prepare(folder):
    from tools.model.clearance_task import TASK_ID,build_task_xml,finish_criteria
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    from tools.learning.guarded_session import CandidateEpisodeSession
    from tools.model.clearance_task import pin_fit
    from tools.learning.runtime import verify_runtime,active_package
    xml=build_task_xml(file_directory=folder)
    (folder/'model.xml').write_text(xml,encoding='utf-8',newline='\n')
    guards=GuardCandidateConfig(math.radians(2.5),math.radians(.5))
    env=LearningEnvironment(guard_config=guards,model_xml=build_task_xml())
    session=CandidateEpisodeSession(environment=env,finish_criteria=finish_criteria(),geometry_checker=pin_fit)
    config=dict(task_id=TASK_ID,finish_criteria=finish_criteria(),guard_config=asdict(guards),
                dynamic_config=asdict(env.config),b2_config=asdict(session.controller_factory().config),
                cases=case_specs(),model_sha256=hashlib.sha256(xml.encode()).hexdigest(),
                display='Actual collision geometry; original narrow-hole female visual hidden',
                scope='development_preflight_only_no_training',input_sha256=input_hashes(),
                runtime_proof=verify_runtime(active_package()))
    write(folder/'configuration.json',config)
    return config


def record_error(run,ledger,entry,error,case,trace,env,session):
    """Keep the last good archive and persist known error facts independently."""
    from tools.validation.native313_matrix_audit import archive_nonfinite
    facts=dict(case=asdict(case),physical_stopped=None)
    for key in ('guard_facts','peaks','events','stop_samples'):
        try:facts[key]=getattr(env,key,None)
        except Exception as exc:facts[key]={'read_error':repr(exc)}
    try:
        controller=getattr(session,'controller',None)
        facts['controller_events']=getattr(controller,'events',None)
    except Exception as exc:
        facts['controller_events']={'read_error':repr(exc)}
    try:
        facts['initial_or_current_state']=dict(qpos=list(env.data.qpos),qvel=list(env.data.qvel),time_s=float(env.data.time))
    except Exception as exc:
        facts['initial_or_current_state']={'read_error':repr(exc)}
    facts=archive_nonfinite(facts)
    entry.update(status='error',error=repr(error),ended_at=now(),error_facts=facts,
                 control_cycles=0 if session is None else getattr(session,'cycle_id',0),
                 physical_substeps=0 if env is None else getattr(env,'physical_steps',0))
    ledger.update(status='error',ended_at=now(),unused_closed=ledger['max_new_episodes']-len(ledger['episodes']))
    # First preserve a small receipt even if the large archive cannot be saved.
    try:write(run/'ledger.json',ledger)
    except Exception as exc:entry['ledger_write_error']=repr(exc)
    try:
        entry['error_archive_sha256']=archive_episode(run/(entry['id']+'.error.json.gz'),
            dict(status='error',error=repr(error),trace=trace,**facts))
    except Exception as exc:entry['archive_error']=repr(exc)
    try:write(run/'ledger.json',ledger)
    except Exception as exc:
        entry['final_ledger_write_error']=repr(exc)
        # Do not claim canonical ledger success; separate best-effort receipt.
        with (run/'failure_receipt.json').open('x',encoding='utf-8') as stream:
            json.dump(ledger,stream,ensure_ascii=False,allow_nan=False)


def execute(folder):
    import numpy as np
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    from tools.learning.guarded_session import CandidateEpisodeSession
    from tools.model.clearance_task import build_task_xml,finish_criteria,pin_fit,pin_clearance_m
    from tools.validation.run_contact_cases import ContactCase
    from tools.control.search_recovery import SearchRecovery,SearchConfig
    run=folder/'run';ledger=claim_run(run)
    config=json.loads((folder/'configuration.json').read_text(encoding='utf-8'))
    if config['input_sha256'] != input_hashes():
        ledger.update(status='input_changed',ended_at=now());write(run/'ledger.json',ledger)
        raise RuntimeError('Preflight source changed after preparation')
    ledger['status']='running';write(run/'ledger.json',ledger)
    while (spec:=next_case(ledger['episodes'])) is not None:
        entry=dict(id=spec['id'],status='running',started_at=now(),control_cycles=0,physical_substeps=0)
        ledger['episodes'].append(entry);write(run/'ledger.json',ledger)
        trace=[];env=None;session=None;start=time.monotonic()
        path=run/(spec['id']+'.json.gz')
        case=ContactCase(spec['id'],spec['x_um']*1e-6,spec['y_um']*1e-6,0.,0.,-.004,.004)
        try:
            env=LearningEnvironment(guard_config=GuardCandidateConfig(**config['guard_config']),model_xml=build_task_xml())
            session=CandidateEpisodeSession(environment=env,
                controller_factory=lambda:SearchRecovery(SearchConfig(**config['b2_config'])),
                finish_criteria=finish_criteria(),geometry_checker=pin_fit)
            session.reset(case);trace.append(session.initial_trace_row)
            limit=math.ceil((session.controller.config.total_action_time_s+session.controller.config.settle_time_s+3)/env.config.control_period)
            while not session.done:
                if session.cycle_id>=limit or time.monotonic()-start>1200 or (folder/'STOP').exists():
                    raise RuntimeError('Bounded preflight interrupted; no retry')
                result=session.advance_cycle([0.,0.,0.,0.]);trace.append(result.trace_row)
                if session.cycle_id%500==0:
                    entry.update(control_cycles=session.cycle_id,physical_substeps=env.physical_steps,
                                 simulated_time_s=float(env.data.time),updated_at=now())
                    write(run/'ledger.json',ledger)
                    archive_episode(path,dict(status='partial',case=asdict(case),trace=trace,events=env.events,
                                             stop_samples=env.stop_samples,guard_facts=env.guard_facts))
                    print(json.dumps(dict(case=spec['id'],cycles=session.cycle_id,time_s=float(env.data.time))),flush=True)
            outcome=session.adjudicate();final=env.observe()
            entry.update(status='finished',ended_at=now(),outcome=outcome,reason=session.reason,
                control_cycles=session.cycle_id,physical_substeps=env.physical_steps,wall_seconds=time.monotonic()-start,
                xy_um=float(np.linalg.norm(final['position_m'][:2])*1e6),z_um=float(final['position_m'][2]*1e6),
                pin_clearance_um=pin_clearance_m(final)*1e6,peaks=env.peaks,
                contact_cycles=sum(r['contact_count']>0 for r in trace[1:]),
                search_cycles=sum(r['policy_phase']=='SEARCH' for r in trace[1:]),
                stop_time=session.stop_time,task_end_time=session.task_end_time,end_time=float(env.data.time))
            entry['archive_sha256']=archive_episode(path,dict(status='finished',case=asdict(case),trace=trace,
                events=env.events,stop_samples=env.stop_samples,guard_facts=env.guard_facts,summary=entry.copy()))
            write(run/'ledger.json',ledger)
            print(json.dumps(entry,ensure_ascii=False),flush=True)
        except BaseException as exc:
            record_error(run,ledger,entry,exc,case,trace,env,session)
            raise
    ledger.update(status='complete' if len(ledger['episodes'])==9 else 'controlled_stop',ended_at=now(),
                  unused_closed=9-len(ledger['episodes']),inputs_unchanged=config['input_sha256']==input_hashes())
    write(run/'ledger.json',ledger)
    return ledger


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if args.prepare==args.execute:parser.error('Choose exactly one operation')
    from tools.validation.run_actor_lr_comparison import select_qualified_runtime
    select_qualified_runtime()
    if args.prepare:
        if (DELIVERY/'configuration.json').exists():raise FileExistsError('Preparation already exists')
        prepare(DELIVERY)
        print('Prepared static model and inputs; dynamic episodes=0, training=0')
    else:
        result=execute(DELIVERY);print(json.dumps(dict(status=result['status'],episodes=len(result['episodes']))))


if __name__=='__main__':
    main()
