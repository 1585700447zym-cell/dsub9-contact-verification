"""Bounded XY reference/admittance rebase verification. No learning."""
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
DELIVERY = ROOT/'deliverables/task_variants/admittance_rebase_20261004'


from tools.validation.run_clearance_preflight import write, now, archive_episode, record_error


def case_specs():
    return [dict(id=name,x_um=x,y_um=y) for name,x,y in [
        ('y_neg_150',0,-150),('y_pos_150',0,150),('x_pos_150',150,0),('x_neg_150',-150,0),('aligned',0,0)]]


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
    if entries and entries[0]['outcome']['task_outcome']!='FULL_SUCCESS':return None
    return specs[len(entries)] if len(entries)<len(specs) else None


def claim_run(folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
    ledger=dict(status='prepared',started_at=now(),episodes=[],max_new_episodes=5,prior_cumulative=120,
                cumulative_limit=125,training_updates=0,policy_calls=0,independent_tests=0,retry_allowed=False)
    write(folder/'ledger.json',ledger)
    return ledger


def input_hashes():
    paths=list((ROOT/'tools').rglob('*.py'))+list((ROOT/'models').rglob('*.xml'))+list((ROOT/'assets').rglob('*.stl'))
    paths += [ROOT/'deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json',
              ROOT/'docs/superpowers/plans/2026-10-04-admittance-rebase.md',
              ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json',
              ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/admission.json']
    return {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}


def verify_prepared_files(folder):
    binding=json.loads((folder/'preparation_binding.json').read_text(encoding='utf-8'))
    if set(binding)!={'configuration.json','model.xml'}:
        raise RuntimeError('Incomplete preparation binding')
    for name,digest in binding.items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Prepared file changed: '+name)


def make_session(env,config=None):
    from tools.learning.rebase_session import RebasedLoadReliefSession
    from tools.control.search_recovery import SearchConfig
    from tools.control.risk_search import RotationRiskConfig
    from tools.control.load_search import LoadSearchRecovery,SearchLoadConfig
    from tools.model.clearance_task import finish_criteria,pin_fit
    config=config or dict(b2_config=asdict(SearchConfig()),rotation_risk=asdict(RotationRiskConfig()),search_load=asdict(SearchLoadConfig()))
    return RebasedLoadReliefSession(environment=env,
        controller_factory=lambda:LoadSearchRecovery(SearchConfig(**config['b2_config']),RotationRiskConfig(**config['rotation_risk']),SearchLoadConfig(**config['search_load'])),
        finish_criteria=finish_criteria(),geometry_checker=pin_fit)


def prepare(folder):
    from tools.model.clearance_task import build_task_xml,finish_criteria
    from tools.model.functional_task import TASK_ID
    from tools.control.risk_search import RotationRiskConfig
    from tools.control.load_search import SearchLoadConfig
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    from tools.learning.rebase_session import RebasedLoadReliefSession
    from tools.model.clearance_task import pin_fit
    from tools.learning.runtime import verify_runtime,active_package
    xml=build_task_xml(file_directory=folder)
    (folder/'model.xml').write_text(xml,encoding='utf-8',newline='\n')
    guards=GuardCandidateConfig(math.radians(2.5),math.radians(.5))
    env=LearningEnvironment(guard_config=guards,model_xml=build_task_xml())
    session=make_session(env)
    config=dict(task_id=TASK_ID,rotation_risk=asdict(RotationRiskConfig()),search_load=asdict(SearchLoadConfig()),controller_id='B2_search_load_rebase_v4',reference_release=dict(mode='XY_reference_and_admittance_offset_velocity',max_rebases=1,per_segment_xy_budget_m=.0005,renews_budget=True),success_mode='functional_geometry_depth_stability',precision_secondary='xy80um_angle0.5deg',finish_criteria=finish_criteria(),guard_config=asdict(guards),
                dynamic_config=asdict(env.config),b2_config=asdict(session.controller_factory().config),
                cases=case_specs(),model_sha256=hashlib.sha256(xml.encode()).hexdigest(),
                display='Actual collision geometry; original narrow-hole female visual hidden',
                scope='development_preflight_only_no_training',input_sha256=input_hashes(),
                runtime_proof=verify_runtime(active_package()))
    write(folder/'configuration.json',config)
    write(folder/'preparation_binding.json',{
        name:hashlib.sha256((folder/name).read_bytes()).hexdigest() for name in ['configuration.json','model.xml']})
    return config


def execute(folder):
    import numpy as np
    from tools.learning.guarded_environment import LearningEnvironment,GuardCandidateConfig
    from tools.learning.rebase_session import RebasedLoadReliefSession
    from tools.model.clearance_task import build_task_xml,finish_criteria,pin_fit,pin_clearance_m
    from tools.validation.run_contact_cases import ContactCase
    from tools.control.search_recovery import SearchConfig
    from tools.control.risk_search import RotationRiskConfig
    from tools.control.load_search import LoadSearchRecovery,SearchLoadConfig
    run=folder/'run';ledger=claim_run(run)
    try:
        verify_prepared_files(folder)
        config=json.loads((folder/'configuration.json').read_text(encoding='utf-8'))
        if config['input_sha256'] != input_hashes():
            raise RuntimeError('Preflight source changed after preparation')
    except Exception as exc:
        ledger.update(status='input_changed',ended_at=now(),unused_closed=5,error=repr(exc))
        write(run/'ledger.json',ledger)
        raise
    ledger['status']='running';write(run/'ledger.json',ledger)
    while (spec:=next_case(ledger['episodes'])) is not None:
        entry=dict(id=spec['id'],status='running',started_at=now(),control_cycles=0,physical_substeps=0)
        ledger['episodes'].append(entry);write(run/'ledger.json',ledger)
        trace=[];env=None;session=None;start=time.monotonic()
        path=run/(spec['id']+'.json.gz')
        case=ContactCase(spec['id'],spec['x_um']*1e-6,spec['y_um']*1e-6,0.,0.,-.004,.004)
        try:
            env=LearningEnvironment(guard_config=GuardCandidateConfig(**config['guard_config']),model_xml=build_task_xml())
            session=make_session(env,config)
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
                                             stop_samples=env.stop_samples,guard_facts=env.guard_facts,controller_events=session.controller.events))
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
                events=env.events,stop_samples=env.stop_samples,guard_facts=env.guard_facts,controller_events=session.controller.events,summary=entry.copy()))
            write(run/'ledger.json',ledger)
            print(json.dumps(entry,ensure_ascii=False),flush=True)
        except BaseException as exc:
            record_error(run,ledger,entry,exc,case,trace,env,session)
            raise
    verify_prepared_files(folder)
    ledger.update(status='complete' if len(ledger['episodes'])==5 else 'controlled_stop',ended_at=now(),
                  unused_closed=5-len(ledger['episodes']),inputs_unchanged=config['input_sha256']==input_hashes(),prepared_files_unchanged=True)
    write(run/'ledger.json',ledger)
    return ledger


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--prepare',action='store_true');parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    if args.prepare==args.execute:parser.error('Choose exactly one operation')
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_admittance_rebase'))
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
