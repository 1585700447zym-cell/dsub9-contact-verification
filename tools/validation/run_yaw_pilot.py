"""One-shot four-case fixed-admittance pilot. No learning or automatic retry."""
import argparse
from dataclasses import asdict
import gzip
import hashlib
import importlib.abc
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'deliverables/learning_chain/b2_yaw_pilot_v2_20261023'
PARENT=ROOT/'deliverables/learning_chain/b2_search_speed450_20261019/run/TILT10_PP/receipt.json'
BASIS=ROOT/'deliverables/learning_chain/b2_search_speed450_complete_20261019/assessment.json'
RUNTIME=ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json'
PYTHON=ROOT/'tmp/learning_cpu_20260924/Scripts/python.exe'
COMMON_KEYS=('dynamic_config','effective_kd','model_xml_sha256','actual_model','runtime')
MAX_CYCLES=14500


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path,data):
    path=Path(path);temp=path.with_name(path.name+f'.{os.getpid()}.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,allow_nan=False,indent=2)+'\n',encoding='utf-8')
    # Bounded replacement: preserve the temp file if publication fails.
    for attempt in range(20):
        try:
            os.replace(temp,path)
            return
        except PermissionError:
            if attempt==19:raise
            time.sleep(.025)


def scope():
    return dict(version='fixed_admittance_yaw_four_v1',max_initializations=4,retries=0,
                cumulative_before=368,yaw_degrees=[1.,-1.,1.5,-1.5],
                case_ids=['YAW_P10','YAW_M10','YAW_P15','YAW_M15'],
                x_um=300.,y_um=300.,roll_deg=-1.,pitch_deg=1.,
                policy_calls=0,training_updates=0,max_cycles=MAX_CYCLES,seed=2026092716)


def claim_batch(out):
    (Path(out)/'run').mkdir()


def verify_inputs(pins,root=ROOT):
    for name,digest in pins.items():
        if sha(root/name)!=digest:raise ValueError('Source hash changed: '+name)


def check_common(actual,parent):
    canonical=lambda x:json.dumps(x,sort_keys=True)
    if any(canonical(actual.get(k))!=canonical(parent.get(k)) for k in COMMON_KEYS):
        raise ValueError('Physical/runtime constants differ from closed 450 baseline')


def continue_batch(receipt):
    return bool(receipt.get('status')=='finished' and receipt.get('valid') is True
                and receipt.get('stopped') is True and receipt.get('audit_passed') is True)


def nonfinite_encoded(value,paths,path='$'):
    if isinstance(value,float) and not math.isfinite(value):
        paths.append(path)
        return {'nonfinite':str(value)}
    if isinstance(value,dict):
        return {k:nonfinite_encoded(v,paths,path+'.'+str(k)) for k,v in value.items()}
    if isinstance(value,(list,tuple)):
        return [nonfinite_encoded(v,paths,f'{path}[{i}]') for i,v in enumerate(value)]
    return value


def publish_archive(folder,raw,receipt):
    paths=[];safe=nonfinite_encoded(raw,paths)
    receipt['nonfinite_fields']=paths
    errors=[]
    def publish_receipt():
        try:write(folder/'receipt.json',nonfinite_encoded(receipt,[]))
        except BaseException as exc:errors.append(exc)
    # Costs are published independently of raw encoding/compression/publication.
    publish_receipt()
    try:
        data=gzip.compress(json.dumps(safe,ensure_ascii=False,allow_nan=False,
                                     separators=(',',':')).encode('utf-8'),mtime=0)
        with (folder/'episode.json.gz').open('xb') as f:f.write(data)
        receipt['archive_sha256']=hashlib.sha256(data).hexdigest()
    except BaseException as exc:
        receipt.update(status='error',archive_error=repr(exc));errors.append(exc)
    finally:publish_receipt()
    if errors:raise errors[0]


def supervise(command,folder,timeout=3650):
    proof=dict(started=False,process_exit_confirmed=False,returncode=None)
    proc=None
    try:
        with (folder/'worker.log').open('wb') as log:
            proc=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            proof['started']=True
            try:proof['returncode']=proc.wait(timeout=timeout)
            except BaseException as exc:
                proof['supervision_error']=repr(exc)
                proc.kill();proof['returncode']=proc.wait()
            proof['process_exit_confirmed']=True
    except BaseException as exc:proof['supervision_error']=repr(exc)
    write(folder/'supervisor.json',proof)
    return proof


def reconcile_receipt(folder,proof):
    path=folder/'receipt.json'
    r=read(path) if path.exists() else dict(status='error',reset_attempted=0,physical_substeps=0,
                                         control_cycles=0,receipt_missing=True)
    r.update(proof)
    if r['status'] not in ('finished','error') or not path.exists():
        progress=read(folder/'progress.json') if (folder/'progress.json').exists() else {}
        r['physical_substeps']=max(r.get('physical_substeps',0),progress.get('physical_substeps',0))
        r['control_cycles']=max(r.get('control_cycles',0),progress.get('cycles',0))
        r['reset_attempted']=max(r.get('reset_attempted',0),progress.get('reset_attempted',0))
        r.update(status='error',count_precision='lower_bound',physical_substeps_upper_bound=10*MAX_CYCLES)
        if not path.exists() and proof.get('started'):
            r['reset_attempted_unknown']=True
    if proof.get('supervision_error') or proof.get('returncode')!=0:
        r['status']='error'
    return r


class NoLearning(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in ('torch','stable_baselines3'):
            raise PermissionError('This pilot forbids learning imports')


def actual_common(env,proof,model_bytes):
    return dict(dynamic_config=asdict(env.config),effective_kd=env.kd.tolist(),
        model_xml_sha256=hashlib.sha256(model_bytes).hexdigest(),runtime=proof,
        actual_model=dict(male_mass_kg=float(env.model.body_mass[env.male]),
            male_inertia_kg_m2=env.model.body_inertia[env.male].tolist(),
            timestep_s=float(env.model.opt.timestep),ccd_tolerance=float(env.model.opt.ccd_tolerance),
            solref_min=env.model.geom_solref.min(axis=0).tolist(),
            solref_max=env.model.geom_solref.max(axis=0).tolist()))


def model_archive_bytes(xml):
    # Match the exact byte format of the closed Windows baseline archive.
    return xml.replace('\r\n','\n').replace('\n','\r\n').encode('utf-8')


def snapshot_environment(receipt,env):
    receipt.update(physical_substeps=getattr(env,'physical_steps',0),
                   guard_facts=env.guard_facts,peaks=getattr(env,'peaks',{}))


def worker(index):
    if type(index) is not int or not 0<=index<4:raise ValueError('Four indices only')
    reg=read(OUT/'registration.json')
    if reg['scope']!=scope():raise ValueError('Pilot scope changed')
    verify_inputs(reg['inputs'])
    folder=OUT/'run'/scope()['case_ids'][index]
    with (folder/'worker.claim').open('x') as f:f.write(str(os.getpid()))
    sys.meta_path.insert(0,NoLearning())
    receipt=dict(case_id=folder.name,status='initializing',reset_attempted=0,reset_completed=0,
                 physical_substeps=0,control_cycles=0,policy_calls=0,training_updates=0,
                 valid=False,stopped=False,audit_passed=False)
    trace=[];cycle_peaks=[];env=session=None;started=time.monotonic()
    write(folder/'receipt.json',receipt)
    try:
        from tools.learning.runtime import select_runtime,verify_runtime,active_package
        select_runtime(RUNTIME,expected_digest=reg['runtime_sha256'])
        proof=verify_runtime(active_package())
        from tools.validation.yaw_pilot import environment_class,session_class,pilot_cases
        from tools.learning.newton_profile import build_model_xml
        env=environment_class()()
        model_bytes=model_archive_bytes(build_model_xml(env.profile))
        (folder/'model_used.xml').write_bytes(model_bytes)
        actual=actual_common(env,proof,model_bytes)
        receipt.update(actual,initialization_guard_config=asdict(env.guard_config),
                       initial_yaw_limit_rad=math.radians(1.5))
        check_common(actual,read(PARENT))
        session=session_class()(env)
        case=pilot_cases()[index]
        receipt.update(case=asdict(case),reset_attempted=1)
        write(folder/'receipt.json',receipt)
        session.reset(case,seed=scope()['seed'])
        receipt.update(reset_completed=1,controller_metadata=session.controller.metadata(),
                       finish_criteria=session.finish_criteria)
        trace.append(session.initial_trace_row)
        import mujoco
        pin_ids={mujoco.mj_name2id(env.model,mujoco.mjtObj.mjOBJ_GEOM,f'pin_{i:02d}'):i for i in range(1,10)}
        while not session.done:
            if session.cycle_id>=MAX_CYCLES or time.monotonic()-started>3600 or (OUT/'STOP').exists():
                raise RuntimeError('Pilot control/wall/external bound; no retry')
            result=session.advance_cycle([0.]*4)
            row=result.trace_row
            contact_pins=set()
            for contact in env.data.contact:
                for gid in (int(contact.geom1),int(contact.geom2)):
                    if gid in pin_ids:contact_pins.add(pin_ids[gid])
            row['diagnostic_contact_pins']=sorted(contact_pins)
            trace.append(row);cycle_peaks.append(result.cycle_peaks)
            if session.cycle_id%500==0:
                write(folder/'progress.json',dict(time_s=float(env.data.time),cycles=session.cycle_id,
                      phase=session.controller.phase,reset_attempted=1,physical_substeps=env.physical_steps))
        outcome=session.adjudicate()
        receipt.update(status='finished',valid=env.guard_facts['simulation_valid'],
            stopped=outcome['physical_stopped'],outcome=outcome['task_outcome'],
            guard_facts=env.guard_facts,peaks=env.peaks,final_reason=session.reason,
            task_time_s=session.task_end_time,stop_time_s=session.stop_time,
            audit_end_time_s=float(env.data.time),controller_events=session.controller.events,
            environment_events=env.events)
        receipt['audit_passed']=bool(len(trace)==session.cycle_id+1 and len(cycle_peaks)==session.cycle_id
            and env.physical_steps==10*session.cycle_id
            and env.guard_facts['checked_substeps']==env.physical_steps)
    except BaseException as exc:
        receipt.update(status='error',error=repr(exc))
        raise
    finally:
        if env is not None:
            snapshot_environment(receipt,env)
        if session is not None:receipt['control_cycles']=getattr(session,'cycle_id',0)
        receipt['elapsed_wall_s']=time.monotonic()-started
        raw=dict(trace=trace,cycle_peaks=cycle_peaks,stop_samples=getattr(env,'stop_samples',[]),
                 receipt=receipt)
        publish_archive(folder,raw,receipt)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    claim_batch(OUT)
    ledger=dict(status='RUNNING',scope=scope(),episodes=[],actual_initialization_attempts=0,
                physical_substeps=0,cumulative_initialization_attempts=368)
    write(OUT/'ledger.json',ledger)
    try:
        basis=read(BASIS)
        if basis.get('verified') is not True or basis.get('cumulative_initialization_attempts')!=368:
            raise ValueError('Closed cumulative-368 parent required')
        paths=list((ROOT/'tools').rglob('*.py'))+[PARENT,BASIS,RUNTIME,
            ROOT/'models/dsub9_pair.xml',ROOT/'docs/superpowers/plans/2026-10-23-yaw-four-case-pilot.md']
        paths+=list((ROOT/'models/includes').glob('*.xml'))
        paths+=[ROOT/'deliverables/learning_chain/b2_yaw_pilot_20261023/ledger.json',
                ROOT/'deliverables/learning_chain/b2_yaw_pilot_20261023/run/YAW_P10/worker.log',
                ROOT/'deliverables/learning_chain/b2_yaw_pilot_20261023/run/YAW_P10/receipt.json']
        pins={p.relative_to(ROOT).as_posix():sha(p) for p in paths}
        snap=OUT/'source_snapshot'
        for name in pins:
            target=snap/name;target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes((ROOT/name).read_bytes())
        reg=dict(scope=scope(),inputs=pins,runtime_sha256=sha(RUNTIME),
                 authorization='2026-10-23 user approved four specified nonzero five-axis development cases',
                 learning_admitted=False)
        write(OUT/'registration.json',reg)
        for i,name in enumerate(scope()['case_ids']):
            verify_inputs(pins)
            folder=OUT/'run'/name;folder.mkdir()
            proof=supervise([str(PYTHON),'-I','-B','-X','utf8',str(Path(__file__).resolve()),'--worker',str(i)],folder)
            receipt=reconcile_receipt(folder,proof)
            ledger['episodes'].append(receipt)
            ledger['actual_initialization_attempts']+=receipt['reset_attempted']
            ledger['physical_substeps']+=receipt['physical_substeps']
            ledger['cumulative_initialization_attempts']=368+ledger['actual_initialization_attempts']
            write(OUT/'ledger.json',ledger)
            print(json.dumps(dict(case=name,outcome=receipt.get('outcome'),status=receipt['status'],
                             task_time_s=receipt.get('task_time_s')),ensure_ascii=False),flush=True)
            if proof.get('supervision_error') or proof['returncode']!=0 or not continue_batch(receipt):
                ledger.update(status='STOPPED',stop_reason='INVALID_SIMULATION_OR_UNQUALIFIED_RECORD')
                break
        else:ledger['status']='COMPLETED'
    except BaseException as exc:
        ledger.update(status='STOPPED',error=repr(exc))
        raise
    finally:
        if ledger['status']=='RUNNING':ledger['status']='STOPPED'
        ledger['count_precision']='lower_bound' if any(r.get('count_precision') for r in ledger['episodes']) else 'exact'
        unknown=sum(bool(r.get('reset_attempted_unknown')) for r in ledger['episodes'])
        ledger['unknown_initialization_attempts_upper_bound']=unknown
        ledger['unused_closed']=4-ledger['actual_initialization_attempts']-unknown
        write(OUT/'ledger.json',ledger)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    command=parser.add_mutually_exclusive_group(required=True)
    command.add_argument('--run',action='store_true');command.add_argument('--worker',type=int)
    args=parser.parse_args();sys.path.insert(0,str(ROOT))
    if args.run:run()
    else:worker(args.worker)
