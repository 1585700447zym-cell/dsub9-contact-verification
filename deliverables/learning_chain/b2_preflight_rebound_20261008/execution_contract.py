"""Pure authorization, accounting and pose evidence. No simulation imports."""
import math
import os
from pathlib import Path
import re
import time
import uuid
from scope_contract import canonical, proposal, PROPOSAL_PIN, next_attempt, case_kwargs, sha, read


def write(path, value):
    path=Path(path)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    with temp.open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(canonical(value)+'\n');stream.flush();os.fsync(stream.fileno())
    for attempt in range(6):
        try:
            os.replace(temp,path);return
        except PermissionError:
            if attempt==5:raise
            time.sleep(.02)


def verify_files(files):
    for name,pin in files.items():
        if sha(Path(name))!=pin:raise ValueError('Bound source/runtime changed: '+name)


def validate_grant(grant,binding_pin,candidate):
    expected=dict(version='b2_pose_scope_grant_v1',status='OPEN',explicit_user_approval=True,
                  binding_sha256=binding_pin,proposal_sha256=PROPOSAL_PIN,
                  scope_key=candidate['draft_scope_key'],limits=candidate['proposed_limits'])
    if any(canonical(grant.get(k))!=canonical(v) for k,v in expected.items()):
        raise ValueError('Explicit new scope grant, binding and exact ceilings required')
    if not isinstance(grant.get('authorization_text'),str) or not grant['authorization_text'].strip():
        raise ValueError('Missing human authorization evidence')


def claim_once(claims,pin,output,identity):
    if not isinstance(pin,str) or not re.fullmatch('[0-9a-f]{64}',pin):raise ValueError('Invalid grant SHA')
    output=Path(output).resolve();claims=Path(claims)
    if output.exists():raise FileExistsError('Output must be new')
    claims.mkdir(parents=True,exist_ok=True)
    claim=claims/pin;claim.mkdir(exist_ok=False)
    write(claim/'identity.json',dict(identity,grant_sha256=pin,output=str(output),status='CONSUMED',retry_allowed=False))
    output.mkdir(parents=True,exist_ok=False)
    return claim


def check_initial_pose(spec,row):
    kw=case_kwargs(spec)
    try:
        p=row['position_m'];q=row['quaternion_wxyz']
        if len(p)!=3 or len(q)!=4 or any(type(x) not in (int,float) or not math.isfinite(x) for x in p+q):
            raise ValueError('Nonfinite pose')
        r=kw['roll_rad']/2;t=kw['pitch_rad']/2
        expected=[math.cos(t)*math.cos(r),math.cos(t)*math.sin(r),math.sin(t)*math.cos(r),-math.sin(t)*math.sin(r)]
        target=[kw['x_offset_m'],kw['y_offset_m'],kw['start_origin_z_m']]
        if (max(abs(x-y) for x,y in zip(p,target))>1e-12 or
            min(max(abs(x-y) for x,y in zip(q,expected)),max(abs(x+y) for x,y in zip(q,expected)))>1e-12):
            raise ValueError('Actual initial pose differs from registered nonzero angle')
    except (KeyError,TypeError,OverflowError) as exc:
        raise ValueError('Incomplete initial pose') from exc
    return True


def execute_matrix(candidate,folder,invoke):
    """invoke runs one already authorized, supervised attempt; injection keeps tests physical-free."""
    folder=Path(folder);started=time.monotonic()
    ledger=dict(status='OPEN',attempts=[],dynamic_attempts=0,static_attempts=0,retry_allowed=False,
                cumulative_before=candidate['cumulative_dynamic'],training_updates=0,network_forwards=0,replay_publications=0)
    write(folder/'ledger.json',ledger)
    try:
        while True:
            if (folder/'STOP').exists():ledger['status']='CLOSED_STOP';break
            if time.monotonic()-started>=candidate['proposed_limits']['total_supervised_wall_s']:
                raise TimeoutError('Whole-run deadline')
            spec=next_attempt(ledger['attempts'],candidate)
            if spec is None:
                complete=(len(ledger['attempts'])==25 and all(e['status']=='finished' and e['audit_passed'] is True
                    and (e['kind']=='static' or (e.get('outcome',{}).get('simulation_valid') is True
                    and e.get('outcome',{}).get('physical_stopped') is True
                    and e.get('outcome',{}).get('task_outcome') in ('FULL_SUCCESS','TASK_FAILURE')))
                    for e in ledger['attempts']))
                ledger['status']='CLOSED_COMPLETE' if complete else 'CLOSED_RULE';break
            entry=dict(id=spec['id'],kind=spec['kind'],status='running',audit_passed=False,
                       started_at=time.time(),physical_substeps_lower_bound=0,
                       physical_substeps_upper_bound=145000 if spec['kind']=='dynamic' else 0)
            ledger['attempts'].append(entry)
            ledger[spec['kind']+'_attempts']+=1
            write(folder/'ledger.json',ledger)
            try:
                result=invoke(spec,entry)
                if result.get('id',spec['id'])!=spec['id'] or result.get('kind',spec['kind'])!=spec['kind']:
                    raise ValueError('Worker returned another attempt')
                entry.update(result)
            except BaseException as exc:
                entry.update(status='error',error=repr(exc),audit_passed=False)
                raise
            finally:
                entry['ended_at']=time.time();write(folder/'ledger.json',ledger)
    except BaseException as exc:
        ledger.update(status='CLOSED_ERROR',error=repr(exc))
    finally:
        ledger.update(unused_static_closed=9-ledger['static_attempts'],unused_dynamic_closed=16-ledger['dynamic_attempts'],
                      ended_at=time.time(),elapsed_s=time.monotonic()-started,
                      physical_substeps_lower_bound=sum(e['physical_substeps_lower_bound'] for e in ledger['attempts']),
                      physical_substeps_upper_bound=sum(e['physical_substeps_upper_bound'] for e in ledger['attempts']))
        write(folder/'ledger.json',ledger)
    return ledger
