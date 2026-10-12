"""One-claim protocol driver candidate. No runtime admission is issued here."""
from copy import deepcopy
from pathlib import Path
import argparse,json,math,os,time,uuid,sys,re
SCRIPT_DIR=Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:sys.path.insert(0,str(SCRIPT_DIR))
from small_bound_profile import (OUT,ROOT,canonical,digest,read,sha,registration,
                                outer_contract,profile_digest,validate_outer_contract)

CAPS=dict(episode=1200,update=1200,checkpoint_read=300)
CLAIM_DIRECTORY=OUT/'execution_claims'


def attempt_specs(contract):
    registered=registration()
    if canonical(contract)!=canonical(registered):raise ValueError('Exact sealed registration required')
    return deepcopy(contract['proposals']['attempts'])


def task_specs(contract):
    tasks=[]
    for a in attempt_specs(contract):
        if a['stage']=='initial' and a['case']['id']=='y_neg_150':
            tasks.append(dict(id='read_zero_checkpoint',kind='checkpoint_read',checkpoint='zero'))
        if a['stage']=='restore':
            tasks.append(dict(id='read_final_checkpoint_new_process',kind='checkpoint_read',checkpoint='final_2000'))
        tasks.append(dict(id=a['id'],kind='episode',attempt=a))
        if a['stage']=='online':tasks.append(dict(id='update_after_'+a['id'],kind='update',batches=500))
    return tasks


def reserve_task(kind,remaining_wall_s):
    if kind not in CAPS or isinstance(remaining_wall_s,bool) or not isinstance(remaining_wall_s,(int,float)) or not math.isfinite(remaining_wall_s) or remaining_wall_s<CAPS[kind]:
        raise ValueError('Insufficient worst-case wall reservation; do not start')
    return CAPS[kind]


def verify_admission(candidate,authorization,qualification):
    """Explicit new grant + qualified candidate; historical budgets never qualify."""
    if (not isinstance(candidate,dict) or candidate.get('status')!='QUALIFIED' or
        candidate.get('training_admitted') is not True or candidate.get('execution_authorized') is not True or
        candidate.get('numeric_verified') is not True or candidate.get('runtime_backend_verified') is not True):
        raise PermissionError('PC12 offline candidate is not numerical/physical/training admission')
    pin=validate_outer_contract(candidate['outer_contract'])
    if pin!=candidate['profile_sha256']:raise ValueError('Candidate profile differs')
    if (not isinstance(authorization,dict) or authorization.get('version')!='pc12_new_execution_authorization_v1' or
        authorization.get('explicit_user_authorized') is not True or authorization.get('status')!='OPEN' or
        authorization.get('candidate_sha256')!=digest(candidate) or authorization.get('prior_dynamic')!=208 or
        authorization.get('limits')!=candidate['limits']):
        raise PermissionError('New explicit bounded authorization required; old balance is closed')
    if (not isinstance(qualification,dict) or qualification.get('version')!='pc12_small_bound_qualification_v1' or
        qualification.get('passed') is not True or qualification.get('candidate_sha256')!=digest(candidate) or
        qualification.get('profile_sha256')!=pin or qualification.get('numeric_gate_passed') is not True or
        qualification.get('physical_preflights_passed') is not True):
        raise PermissionError('New bound numeric and physical qualification required')
    for rel,pin in candidate['execution_code_sha256'].items():
        if sha(ROOT/rel)!=pin:raise ValueError('New execution source changed')
    source=read(OUT/'source_bindings.json')
    if digest(source)!=candidate['source_bindings_sha256']:raise ValueError('Source bindings changed')
    for rel,pin in source['production_inputs'].items():
        if sha(ROOT/rel)!=pin:raise ValueError('Common production source changed')
    return dict(profile_sha256=candidate['profile_sha256'],qualification_sha256=digest(qualification),
                candidate_sha256=digest(candidate),authorization_sha256=digest(authorization))


def _write(path,value):
    pending=path.with_name(path.name+'.write-'+uuid.uuid4().hex)
    with pending.open('x',encoding='utf8') as f:f.write(canonical(value));f.flush();os.fsync(f.fileno())
    os.replace(pending,path)


class ProtocolLedger:
    """Protocol-only fixtures cannot dispatch runtime. Production claim is exclusive."""
    def __init__(self,folder,contract,*,protocol_only,admission=None):
        self.tasks=task_specs(contract);self.contract=deepcopy(contract);self.protocol_only=protocol_only
        if type(protocol_only) is not bool:raise ValueError('Explicit protocol-only scope required')
        if not protocol_only:
            if admission is None:raise PermissionError('Actual ledger requires new admission')
            receipt=admission.verify('claim',profile_digest(outer_contract()))
            fields={'authorization_sha256','qualification_sha256','candidate_sha256','profile_sha256'}
            if (not isinstance(receipt,dict) or set(receipt)!=fields or
                any(not isinstance(receipt[k],str) or not re.fullmatch('[0-9a-f]{64}',receipt[k]) for k in fields) or
                receipt['profile_sha256']!=profile_digest(outer_contract())):
                raise PermissionError('Verified new authorization identity required for global claim')
        folder=Path(folder)
        if folder.exists():raise FileExistsError('A claimed attempt is never restarted or reclaimed')
        if not protocol_only:
            # Authorization identity, independent of caller-chosen output folder.
            # Keep this claim consumed even if folder creation or process setup fails.
            CLAIM_DIRECTORY.mkdir(parents=True,exist_ok=True)
            claim=CLAIM_DIRECTORY/(receipt['authorization_sha256']+'.json')
            with claim.open('x',encoding='utf8') as f:
                f.write(canonical(dict(receipt=receipt,folder=str(folder.resolve()))));f.flush();os.fsync(f.fileno())
        folder.mkdir(parents=True);self.path=folder/'ledger.json'
        with (folder/'claim.json').open('x',encoding='utf8') as f:
            f.write(canonical(dict(version='pc12_once_claim_v1',protocol_only=protocol_only,registration_sha256=digest(contract))))
            f.flush();os.fsync(f.fileno())
        self.data=dict(version='pc12_once_ledger_v1',protocol_only=protocol_only,status='open',next_task=0,active=None,
            physical_attempts_started=0,update_batches_reserved=0,updates_attempted=0,updates_completed=0,credit_earned=0,
            control_cycles=0,physical_substeps=0,policy_calls=0,published_rows=0,warm_active_rows=0,
            warm_active_cases=[],elapsed_wall_s=0.,results=[],unused_closed=None)
        _write(self.path,self.data)

    def _check(self,elapsed):
        if read(self.path)!=self.data:raise ValueError('Durable ledger changed; no continuation')
        if self.data['status']!='open':raise RuntimeError('Closed budget cannot be reopened')
        if isinstance(elapsed,bool) or not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or elapsed<self.data['elapsed_wall_s']:
            raise ValueError('Monotonic finite whole-execution elapsed time required')
        self.data['elapsed_wall_s']=float(elapsed)

    def close(self,reason):
        self.data.update(status='closed',close_reason=reason,
            unused_closed=dict(physical_attempts=21-self.data['physical_attempts_started'],update_batches=2000-self.data['update_batches_reserved']))
        _write(self.path,self.data)

    def start(self,*,elapsed_wall_s):
        self._check(elapsed_wall_s)
        if self.data['active'] is not None:raise RuntimeError('Unresolved attempt; no retry or parallel start')
        index=self.data['next_task']
        if index>=len(self.tasks):raise RuntimeError('No extra warmup, evaluation or retry')
        task=deepcopy(self.tasks[index])
        try:cap=reserve_task(task['kind'],21600-elapsed_wall_s)
        except ValueError:self.close('insufficient_global_wall_budget');raise
        if task['kind']=='episode':
            if self.data['physical_attempts_started']>=21:raise ValueError('Dynamic quota exhausted')
            self.data['physical_attempts_started']+=1
        elif task['kind']=='update':
            n=task['batches']
            if self.data['update_batches_reserved']+n>min(2000,self.data['credit_earned']):
                self.close('unearned_or_exhausted_update_credit');raise ValueError('No update credit')
            self.data['update_batches_reserved']+=n
        self.data['active']=dict(**task,started_elapsed_wall_s=elapsed_wall_s,reserved_wall_s=cap)
        _write(self.path,self.data) # persist charging before any backend dispatch
        return task

    def finish(self,result,*,elapsed_wall_s):
        self._check(elapsed_wall_s);task=self.data['active']
        if task is None:raise RuntimeError('No started task')
        try:
            canonical(result)
            if elapsed_wall_s-task['started_elapsed_wall_s']>task['reserved_wall_s'] or elapsed_wall_s>21600:
                raise ValueError('Atomic/global wall cap exceeded')
            if task['kind']=='episode':
                if any(type(result[k]) is not bool for k in ('valid','stopped','reference_ok','guard')):raise ValueError('Boolean physical audit required')
                for k in ('cycles','substeps','policy_calls','published_rows'):
                    if type(result[k]) is not int or result[k]<0:raise ValueError('Nonnegative actual counter required')
                if not 0<result['cycles']<=14500 or result['substeps']!=10*result['cycles'] or result['policy_calls']>result['cycles']:
                    raise ValueError('Cycle/substep/policy quota differs')
                stage=task['attempt']['stage']
                if stage not in ('warmup','online') and result['published_rows']!=0:raise ValueError('Evaluation/preflight/restore cannot enter replay')
                if stage in ('warmup','preflight') and result['policy_calls']!=0:raise ValueError('Script/warmup must not call network')
                for k,v in [('control_cycles','cycles'),('physical_substeps','substeps'),('policy_calls','policy_calls'),('published_rows','published_rows')]:self.data[k]+=result[v]
                if self.data['control_cycles']>304500 or self.data['physical_substeps']>3045000 or self.data['policy_calls']>217500:
                    raise ValueError('Whole-execution compute quota exceeded')
                if not all(result[k] for k in ('valid','stopped','reference_ok')) or result['guard']:
                    self.data['results'].append(dict(task=task,result=result));self.close('physical_fault_stop_or_guard');return
                if stage=='warmup':
                    count=result.get('active_rows',0)
                    if type(count) is not int or not 0<=count<=result['cycles']:raise ValueError('Warm active count differs')
                    self.data['warm_active_rows']+=count
                    if count:self.data['warm_active_cases'].append(task['attempt']['case']['id'])
                    if task['attempt']['case']['id']=='x_neg_150' and (self.data['warm_active_rows']<256 or len(set(self.data['warm_active_cases']))<2):
                        self.data['results'].append(dict(task=task,result=result));self.close('warmup_gate_failed_no_extra_collection');return
                if stage=='online':self.data['credit_earned']+=500
            elif task['kind']=='update':
                completed=result.get('completed_batches');attempted=result.get('attempted_batches')
                if type(completed) is not int or not 0<=completed<=task['batches']:raise ValueError('Invalid completed update count')
                if attempted is None and completed==task['batches'] and not result.get('error'):attempted=completed
                if attempted is not None and (type(attempted) is not int or not completed<=attempted<=task['batches']):
                    raise ValueError('Invalid attempted update count')
                self.data['updates_completed']+=completed
                self.data['updates_attempted']=None if attempted is None or self.data['updates_attempted'] is None else self.data['updates_attempted']+attempted
                if completed!=task['batches'] or result.get('error'):
                    self.data['results'].append(dict(task=task,result=deepcopy(result)))
                    self.close('partial_update_no_retry');raise ValueError('Update block incomplete; actual counts and failure retained')
            else:
                if result.get('verified') is not True or result.get('checkpoint')!=task['checkpoint']:
                    raise ValueError('Only registered zero/final2000 checkpoint can be read')
            self.data['results'].append(dict(task=task,result=result));self.data['active']=None;self.data['next_task']+=1
            if self.data['next_task']==len(self.tasks):self.close('fixed_matrix_completed')
            else:_write(self.path,self.data)
        except (ValueError,KeyError,TypeError):self.close('audit_or_protocol_failure');raise

    def record_backend_failure(self,error,*,elapsed_wall_s,result=None):
        """Persist partial measured facts, or mark unknown rather than claim zero."""
        if self.data['status']!='open':return
        if result is not None:
            try:self.finish(result,elapsed_wall_s=elapsed_wall_s)
            except (ValueError,KeyError,TypeError):pass
            if self.data['status']=='open':self.close('backend_failure_no_retry')
            return
        task=self.data['active'];facts=dict(error=repr(error),actual_counters_verified=False,
            note='No backend counter snapshot; reconcile retained backend journal, never rerun')
        if task and task['kind']=='update':
            self.data['known_updates_completed_before_unresolved']=self.data['updates_completed']
            self.data['known_updates_attempted_before_unresolved']=self.data['updates_attempted']
            self.data['updates_completed']=self.data['updates_attempted']=None
        self.data['results'].append(dict(task=deepcopy(task),result=facts))
        self.close('backend_failure_or_interruption_no_retry')


def execute_protocol(ledger,admission,backend):
    """Inject a separately qualified runtime backend; this file imports none."""
    if ledger.protocol_only:raise PermissionError('Offline protocol fixture cannot execute runtime')
    origin=time.monotonic();pin=profile_digest(outer_contract())
    while ledger.data['status']=='open':
        admission.verify('dispatch',pin)
        task=ledger.start(elapsed_wall_s=time.monotonic()-origin)
        try:
            result=backend.run(task,ledger=ledger,admission=admission)
            admission.verify('dispatch',pin)
            ledger.finish(result,elapsed_wall_s=time.monotonic()-origin)
        except BaseException as exc:
            facts=None
            if hasattr(backend,'failure_result'):
                try:facts=backend.failure_result(task)
                except BaseException:pass
            ledger.record_backend_failure(exc,elapsed_wall_s=time.monotonic()-origin,result=facts)
            raise
    return deepcopy(ledger.data)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inspect',action='store_true');parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    candidate=read(OUT/'qualification_candidate.json')
    if args.execute:
        # There is no automatic manufacture of authorization or numerical proof.
        verify_admission(candidate,None,None)
    print(json.dumps(dict(status=candidate['status'],profile_sha256=candidate['profile_sha256'],
        fixed_attempts=21,formal_update_budget_proposed=2000,actual_new_compute=0,
        numeric_gate='pending separate authorization',runtime_backend='pending numerical integration gate'),ensure_ascii=False))


if __name__=='__main__':main()
