"""Retain started operational faults separately from complete policy evaluations."""
import gzip,json
import validation_contract as C
from tools.learning.sac_checkpoint import _audit_physics

def display_status(identity,finished,failed):
    if identity in finished:return 'completed'
    if any(x['id']==identity for x in failed):return 'runtime_fault'
    return 'unexecuted'

def audit_failed_attempts(ledger,run,checkpoints,origin):
    rows=[]
    for attempt in ledger.state['attempts']:
        if attempt['status']!='failed':continue
        i=attempt['identity'];folder=run/'collections'/i['id']/i['id'];path=folder/'episode.json.gz'
        row=dict(id=i['id'],identity=i,status='runtime_fault',actual_start_charged=True,complete_policy_evaluation=False,
            reserved_cycles=attempt['reserved_cycles'],error=attempt.get('error'),archive_present=path.exists(),
            policy_checkpoint_matched=False,policy_identity_available=False,full_physics_audit=False)
        if path.exists():
            row.update(archive_path=path.relative_to(C.ROOT).as_posix(),archive_sha256=C.digest(path),archive_bytes=path.stat().st_size)
            try:raw=json.loads(gzip.decompress(path.read_bytes()))
            except (OSError,ValueError,EOFError) as exc:row['archive_parse_error']=repr(exc);rows.append(row);continue
            row.update(available_cycles=len(raw.get('transitions',[])),fault=raw.get('fault'),guard_facts=raw.get('guard_facts'),outcome=raw.get('outcome'),
                policy_sha256=raw.get('policy_sha256'),optimizer_batches=raw.get('optimizer_steps'),raw_identity=raw.get('episode_id'))
            if raw.get('episode_id')!=i['id'] or raw.get('qualification_sha256')!=ledger.state['binding_sha256']:raise ValueError('Fault archive identity differs')
            try:_audit_physics(raw);row['full_physics_audit']=True
            except (ValueError,TypeError,KeyError,IndexError,AssertionError) as exc:row['physics_audit_error']=repr(exc)
            fingerprint=raw.get('policy_sha256');n=raw.get('optimizer_steps')
            if fingerprint is not None and type(n) is int:
                row['policy_identity_available']=True
                if n==0:matched=fingerprint==origin.get('actor')
                else:matched=any(x['arm']==i['arm'] and x['batches']==n and x['actor_sha256']==fingerprint for x in checkpoints)
                if not matched:raise ValueError('Fault triggering policy lacks matching preserved checkpoint')
                row['policy_checkpoint_matched']=True
        failure=run/'collections'/i['id']/'failure.json'
        if failure.exists():row.update(failure_record_path=failure.relative_to(C.ROOT).as_posix(),failure_record_sha256=C.digest(failure))
        receipt=folder/'status.json'
        if receipt.exists():row.update(receipt_path=receipt.relative_to(C.ROOT).as_posix(),receipt_sha256=C.digest(receipt))
        rows.append(row)
    return rows
