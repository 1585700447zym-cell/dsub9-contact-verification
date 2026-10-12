"""New scope runner. Check-only is standard-library-only; execution needs a new grant."""
import argparse
import importlib.abc
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
sys.path[:0]=[str(OUT),str(ROOT)]
from scope_contract import proposal, canonical, read, sha, validate_candidate, attempt_specs
from execution_contract import write, verify_files, validate_grant, claim_once, execute_matrix

BINDING=OUT/'candidate_binding.json'
REGISTERED_ROOT=Path('D:/dsub9项目计划/first_stage_sim/.worktrees/dsub9-v1-contact-validation').resolve()
REGISTERED_OUT=REGISTERED_ROOT/'deliverables/learning_chain/b2_joint_admission_preflight_20261009'
CLAIMS=REGISTERED_OUT/'claims'


def require_registered_location():
    if ROOT!=REGISTERED_ROOT or OUT!=REGISTERED_OUT or Path(__file__).resolve()!=REGISTERED_OUT/'run_preflight.py':
        raise PermissionError('Relocated entrypoint cannot inherit this binding or create another claim store')
    # All private modules resolved through the registered implementation folder.
    for name in ('scope_contract','execution_contract','physical_worker','assess','offline_math','windows_job','deadline_guard','evidence_checks','recovery_fixture','coverage_checks'):
        loaded=sys.modules.get(name)
        if loaded is not None and Path(loaded.__file__).resolve()!=REGISTERED_OUT/(name+'.py'):
            raise PermissionError('Private execution module loaded from another directory: '+name)


class NoLearning(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[0] in {'torch','stable_baselines3','gymnasium','tensorflow','jax'}:
            raise ImportError('Learning runtime forbidden in B.2 scope preflight: '+fullname)


def check_limits(*,kind,cycles,steps,elapsed,whole,static_elapsed):
    limits=proposal()['proposed_limits']
    if whole>=limits['total_supervised_wall_s']:raise TimeoutError('Whole scope deadline')
    if kind=='dynamic':
        if cycles>=limits['control_cycles_per_episode'] or steps>=limits['physical_substeps_per_episode'] or elapsed>=limits['per_episode_wall_s']:
            raise TimeoutError('Dynamic ceiling includes stopping tail')
    else:raise ValueError('Unknown attempt kind')


def output_path(path):
    path=Path(path).resolve()
    if not path.is_relative_to(ROOT) or path==ROOT:raise ValueError('Output must stay inside the worktree')
    if path.exists():raise FileExistsError('Output must be new')
    return path


def check_binding():
    require_registered_location()
    candidate=proposal();parent=read(ROOT/candidate['parent']['configuration'])
    validate_candidate(candidate,parent)
    binding=read(BINDING)
    if binding['implementation_directory']!=str(REGISTERED_OUT):raise PermissionError('Binding directory differs')
    if binding['version']!='b2_joint_preflight_binding_v1' or binding['proposal_sha256']!=sha(OUT/'candidate.json'):
        raise ValueError('Wrong candidate binding')
    if binding['scope_key']!=candidate['draft_scope_key']:raise ValueError('Wrong pose scope')
    numerical_pins=ROOT/'deliverables/paper_comparison/small_boundary_numeric_execution_20261008/prior_source_bindings.json'
    if str(numerical_pins) not in binding['files']:
        raise ValueError('Missing numerical pin input binding')
    verify_files(binding['files'])
    for directory,inventory in binding['inventories'].items():
        actual=sorted(p.relative_to(directory).as_posix() for p in Path(directory).rglob('*')
                      if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
        if actual!=inventory:raise ValueError('Runtime inventory changed: '+directory)
    return candidate,binding


def require_interpreter(binding):
    if not sys.flags.isolated or Path(sys.executable).resolve()!=Path(binding['executable']).resolve():
        raise PermissionError('Explicit isolated registered CPU interpreter required')


def worker(request_path,request_pin):
    # Every check here precedes runtime imports and every reset/step.
    request_path=Path(request_path).resolve()
    if sha(request_path)!=request_pin:raise ValueError('Worker request SHA differs')
    request=read(request_path);folder=Path(request['output']).resolve();claim=CLAIMS/request['grant_sha256']
    if not folder.is_relative_to(ROOT) or request_path.parent!=folder:raise ValueError('Request outside claimed output')
    identity=read(claim/'identity.json')
    if (claim/'closed.json').exists():raise PermissionError('Grant already closed')
    if identity['output']!=str(folder) or identity['binding_sha256']!=sha(BINDING):raise ValueError('Claim identity differs')
    if identity['parent_pid']!=request['parent_pid'] or identity['registered_at']!=request['registered_at']:
        raise ValueError('Worker parent registration differs')
    candidate,binding=check_binding();require_interpreter(binding)
    grant=read(folder/'grant.json')
    if sha(folder/'grant.json')!=request['grant_sha256']:raise ValueError('Copied grant changed')
    validate_grant(grant,sha(BINDING),candidate)
    spec=request['spec']
    if request['binding_sha256']!=sha(BINDING):raise ValueError('Worker binding pin mismatch')
    if spec not in attempt_specs(candidate):raise ValueError('Worker spec is not registered')
    ledger=read(folder/'ledger.json')
    if ledger['status']!='OPEN' or ledger['attempts'][-1]['id']!=spec['id'] or ledger['attempts'][-1]['status']!='running':
        raise ValueError('Attempt was not durably reserved')
    from tools.validation.process_parent import require_registered_parent
    proof=require_registered_parent(request['parent_pid'],request['registered_at'])
    base=folder/spec['id']
    write(base.with_suffix('.ready.json'),dict(request_sha256=request_pin,proof=proof))
    deadline=time.monotonic()+30
    while not base.with_suffix('.go.json').exists():
        if time.monotonic()>=deadline or (folder/'STOP').exists():raise TimeoutError('No supervised GO')
        time.sleep(.05)
    go=read(base.with_suffix('.go.json'))
    if go!=dict(request_sha256=request_pin,pid=os.getpid(),job_assigned=True):raise ValueError('GO identity mismatch')
    require_registered_parent(request['parent_pid'],request['registered_at'])
    # Exclusive per-attempt ticket: a second invocation cannot repeat a reset.
    (claim/(spec['id']+'.consumed')).mkdir(exist_ok=False)
    if (folder/'STOP').exists() or time.time()>=request['deadline']:raise TimeoutError('Scope stopped before runtime')
    sys.meta_path.insert(0,NoLearning())
    from physical_worker import run_case
    raw=run_case(request,binding)
    result=audit_completed_raw(raw,spec,binding)
    if time.time()>=request['deadline']:raise TimeoutError('Attempt deadline includes source and raw audit')
    write(base.with_suffix('.audit.json'),dict(id=spec['id'],binding_sha256=sha(BINDING),
        archive_sha256=sha(base.with_suffix('.json.gz')),physical_substeps=raw['physical_substeps'],assessment=result))


def audit_completed_raw(raw,spec,binding):
    """Worker's post-physics audit: exact registered revision and producer pin."""
    require_registered_location()
    verify_files(binding['files'])
    from assess import assess_raw
    return assess_raw(raw,spec,dict(binding,binding_sha256=sha(BINDING)))


def supervised_attempt(spec,entry,*,folder,claim,binding,identity,whole_started,static_started):
    from windows_job import Job
    from tools.validation.process_parent import windows_process,validate_chain
    began=time.monotonic();limit=60 if spec['kind']=='static' else 1200
    remaining=21600-(began-whole_started)
    if spec['kind']=='static':remaining=min(remaining,600-(began-static_started))
    if remaining<=0:raise TimeoutError('Batch deadline before launch')
    timeout=min(limit,remaining)
    request=dict(spec=spec,output=str(folder),grant_sha256=identity['grant_sha256'],
        parent_pid=identity['parent_pid'],registered_at=identity['registered_at'],
        binding_sha256=sha(BINDING),deadline=time.time()+timeout,nonce=uuid.uuid4().hex)
    request_path=folder/(spec['id']+'.request.json');write(request_path,request);pin=sha(request_path)
    command=[binding['executable'],'-I','-X','utf8','-B',str(Path(__file__).resolve()),
             '--worker',str(request_path),'--request-pin',pin]
    base=folder/spec['id'];receipt=dict(process_exit_confirmed=False,physical_stop_confirmed=False)
    with Job() as job,base.with_suffix('.log').open('x',encoding='utf-8') as log:
        assigned=False
        child=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,
                               creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            job.assign(child._handle);assigned=True
            ready=base.with_suffix('.ready.json')
            while not ready.exists():
                if child.poll() is not None:raise RuntimeError('Worker exited before readiness')
                if time.monotonic()-began>=min(timeout,35) or (folder/'STOP').exists():raise TimeoutError('Worker readiness/STOP')
                time.sleep(.05)
            response=read(ready)
            if response['request_sha256']!=pin:raise ValueError('Readiness pin differs')
            proof=response['proof']
            # Revalidate the complete live chain while native-worker handles are held.
            with windows_process(proof['pid']) as native,windows_process(os.getpid()) as parent:
                with windows_process(native['parent_pid']) as immediate:
                    validate_chain(expected_pid=os.getpid(),registered_at=identity['registered_at'],now=time.time(),
                        child=native,parent=immediate,registered=parent,python_image=sys._base_executable,
                        launcher_image=binding['executable'])
                    if native!=proof['child']:raise ValueError('Native worker identity changed')
                    # A venv launcher may spawn before it joins our job. Assign
                    # the native worker as well; same-job assignment is a no-op.
                    job.assign_pid(native['pid'])
                    write(base.with_suffix('.go.json'),dict(request_sha256=pin,pid=native['pid'],job_assigned=True))
            while child.poll() is None or job.active():
                if time.monotonic()-began>=timeout:raise TimeoutError('Supervised attempt deadline')
                if (folder/'STOP').exists():raise InterruptedError('Explicit STOP; no remaining launches')
                time.sleep(.1)
            receipt.update(process_exit_confirmed=True,returncode=child.returncode,proof=proof)
            if child.returncode:raise RuntimeError('Worker failed; partial evidence retained')
        except BaseException:
            try:
                job.stop()
                if not assigned and child.poll() is None:child.terminate()
                child.wait(timeout=15);receipt['owned_launcher_exit_confirmed']=True
                receipt['process_exit_confirmed']=assigned and job.active()==0
            finally:write(base.with_suffix('.supervisor.json'),receipt)
            raise
        finally:
            receipt['wall_seconds']=time.monotonic()-began
            write(base.with_suffix('.supervisor.json'),receipt)
    # Source hashing, decompression and assessment completed inside the bounded
    # worker. Only a small receipt is read here; the hard outer supervisor also
    # bounds this parent and the complete final matrix assessment.
    receipt_path=base.with_suffix('.audit.json')
    if receipt_path.stat().st_size>1000000:raise ValueError('Oversized audit receipt')
    audit=read(receipt_path)
    if audit['id']!=spec['id'] or audit['binding_sha256']!=sha(BINDING):raise ValueError('Audit identity differs')
    result=audit['assessment']
    if time.monotonic()-began>=timeout:raise TimeoutError('Attempt deadline includes audit receipt')
    if time.monotonic()-whole_started>=21600:raise TimeoutError('Whole deadline includes archive audit')
    if spec['kind']=='static' and time.monotonic()-static_started>=600:raise TimeoutError('Static batch includes audit')
    entry.update(archive_sha256=audit['archive_sha256'],archive=spec['id']+'.json.gz',assessment=result)
    return dict(status='finished',audit_passed=result['audit_passed'],outcome=result.get('outcome'),
                physical_substeps_lower_bound=audit['physical_substeps'],physical_substeps_upper_bound=audit['physical_substeps'])


def close_interrupted(folder,grant_pin,gate,error):
    """After owned job exit, close only a claim created by this unique launcher."""
    folder=Path(folder).resolve();claim=CLAIMS/grant_pin
    if not folder.is_relative_to(ROOT) or not (claim/'identity.json').exists():return
    identity=read(claim/'identity.json')
    if identity.get('outer_gate')!=str(gate) or identity['output']!=str(folder):return
    record=folder/'ledger.json'
    if record.exists():
        ledger=read(record)
        ledger.update(status='CLOSED_SUPERVISOR_TIMEOUT' if isinstance(error,TimeoutError) else 'CLOSED_SUPERVISOR_ERROR',
            supervisor_error=repr(error),retry_allowed=False,unused_static_closed=0-ledger['static_attempts'],
            unused_dynamic_closed=12-ledger['dynamic_attempts'],ended_at=time.time())
        for entry in ledger['attempts']:
            if entry['status']=='running':entry.update(status='partial_unknown',audit_passed=False)
        write(record,ledger)
        closure={k:ledger[k] for k in ('status','unused_static_closed','unused_dynamic_closed')}
    else:closure=dict(status='CLOSED_BEFORE_LEDGER',unused_static_closed=0,unused_dynamic_closed=12)
    write(claim/'closed.json',dict(closure,output=str(folder),retry_allowed=False,outer_gate=str(gate)))


def execute(grant_path,grant_pin,output,*,outer_gate=None):
    require_registered_location()
    whole_started=time.monotonic()
    if not grant_path or not grant_pin or not output:raise PermissionError('Explicit --grant, --grant-pin, --output required')
    path=Path(grant_path)
    if sha(path)!=grant_pin:raise ValueError('Grant bytes differ from explicit pin')
    candidate,binding=check_binding();require_interpreter(binding)
    validate_grant(read(path),sha(BINDING),candidate)
    folder=output_path(output)
    identity=dict(binding_sha256=sha(BINDING),parent_pid=os.getpid(),registered_at=time.time(),grant_sha256=grant_pin,
                  outer_gate=outer_gate)
    claim=claim_once(CLAIMS,grant_pin,folder,identity)
    (folder/'grant.json').write_bytes(path.read_bytes())
    static_started=time.monotonic()
    invoke=lambda spec,entry:supervised_attempt(spec,entry,folder=folder,claim=claim,binding=binding,
        identity=identity,whole_started=whole_started,static_started=static_started)
    try:
        result=execute_matrix(candidate,folder,invoke)
        from assess import assess
        write(folder/'assessment.json',assess(folder))
        return result
    finally:
        ledger=read(folder/'ledger.json') if (folder/'ledger.json').exists() else {}
        write(claim/'closed.json',dict(status=ledger.get('status','CLOSED_ERROR'),output=str(folder),unused_closed=True,retry_allowed=False))


def main(argv=None):
    require_registered_location()
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only',action='store_true');mode.add_argument('--execute',action='store_true');mode.add_argument('--worker')
    mode.add_argument('--execution-child',action='store_true')
    parser.add_argument('--grant');parser.add_argument('--grant-pin');parser.add_argument('--output');parser.add_argument('--request-pin')
    parser.add_argument('outer_gate',nargs='?');parser.add_argument('outer_parent',nargs='?');parser.add_argument('outer_registered',nargs='?')
    args=parser.parse_args(argv)
    if args.check_only:
        c,b=check_binding()
        assert not any(k.split('.')[0] in {'mujoco','torch','stable_baselines3','numpy'} for k in sys.modules)
        print(canonical(dict(status='CHECK_ONLY_PASSED',binding_sha256=sha(BINDING),files=len(b['files']),
            engine_loads=0,static_initializations=0,dynamic_attempts=0,training_admitted=False)))
    elif args.worker:worker(args.worker,args.request_pin)
    elif args.execution_child:
        if not all((args.outer_gate,args.outer_parent,args.outer_registered)):raise PermissionError('Missing outer supervisor')
        from deadline_guard import enter_gate
        enter_gate(args.outer_gate,args.outer_parent,args.outer_registered)
        result=execute(args.grant,args.grant_pin,args.output,outer_gate=args.outer_gate);print(canonical(result))
        return 0 if result['status']=='CLOSED_COMPLETE' else 2
    else:
        if not all((args.grant,args.grant_pin,args.output)):raise PermissionError('Explicit --grant, --grant-pin, --output required')
        c,b=check_binding();require_interpreter(b)
        if sha(args.grant)!=args.grant_pin:raise ValueError('Grant pin differs')
        validate_grant(read(args.grant),sha(BINDING),c)
        from deadline_guard import bounded_process
        gate=ROOT/'tmp/b2_joint_supervisors'/uuid.uuid4().hex/'outer'
        command=[sys.executable,'-I','-X','utf8','-B',str(REGISTERED_OUT/'run_preflight.py'),'--execution-child',
            '--grant',args.grant,'--grant-pin',args.grant_pin,'--output',args.output]
        try:bounded_process(command,gate,21600.)
        except BaseException as exc:
            # Unknown/timeout cannot resume. Preserve attempts and conservative
            # step bounds even if the inner supervisor died during its audit.
            close_interrupted(args.output,args.grant_pin,gate,exc)
            raise
        print(canonical(dict(status='SUPERVISED_EXECUTION_FINISHED',output=str(Path(args.output).resolve()),outer_receipt=str(gate.with_suffix('.supervisor.json')))))
    return 0


if __name__=='__main__':raise SystemExit(main())
