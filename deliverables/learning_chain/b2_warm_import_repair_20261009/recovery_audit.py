"""Read-only recovery-source auditor; never constructs a learner or publishes replay."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OLD=HERE.parent/'b2_joint_sac_execution_20261009'
KIT=HERE.parent/'b2_joint_sac_preparation_20261009'
sys.path.insert(0,str(HERE))
from joint_contract import read,write,sha,canonical

def vector(value,size):
    if not isinstance(value,list) or len(value)!=size or any(type(v) not in (int,float) or not math.isfinite(v) for v in value):
        raise ValueError('Finite fixed-width vector required')
    return value

def inspect_warmup(raw,receipt,expected_id,draws):
    if expected_id not in ['warmup_F50_J0'+str(i) for i in range(1,5)]:raise ValueError('Unregistered warmup ID')
    index=int(expected_id[-1])-1
    if (raw['episode_id']!=expected_id or raw['case_id']!='J0'+str(index+1) or raw['case_index']!=index or
        raw['stage']!='warmup' or raw['mode']!='F50' or raw['seed']!=2026092716 or raw['fault'] is not None or
        raw['optimizer_steps']!=0 or raw['optimizer_steps_start']!=0 or raw['policy_calls']!=0):
        raise ValueError('Not the registered zero-update warmup source')
    rows=raw['transitions'];out=raw['outcome']
    if not 0<len(rows)<=14500 or raw['control_cycles']!=len(rows):raise ValueError('Incomplete physical rows')
    if (not all(out[k] is True for k in ('simulation_valid','physical_stopped','valid_for_learning')) or
        out['task_outcome']!='FULL_SUCCESS' or any(out['guard_violations'].values())):
        raise ValueError('Unqualified source outcome')
    expected=dict(episode_id=expected_id,stage='warmup',case_index=index,optimizer_steps=0,
        policy_sha256=raw['policy_sha256'],steps=len(rows),committed=len(rows),outcome=out)
    if any(receipt.get(k)!=v for k,v in expected.items()):raise ValueError('Durable receipt differs')
    held=None;previous=None;active_count=0;last_active=None;digest=hashlib.sha256()
    for i,row in enumerate(rows):
        flags=[row[k] for k in ('action_active','next_action_active','terminated','truncated')]
        if any(type(v) is not bool for v in flags) or row['terminated']!=(i==len(rows)-1) or row['truncated']:
            raise ValueError('Complete natural terminal required')
        obs=vector(row['observation'],137);nxt=vector(row['next_observation'],137)
        if previous is not None and previous!=(obs,row['action_active']):raise ValueError('Discontinuous observation/permission')
        previous=(nxt,row['next_action_active'])
        request=vector(row['sampling_request'],4)
        if max(map(abs,request))>1:raise ValueError('Exploration outside normalized action range')
        if i%50==0:held=request.copy();draws+=1
        if request!=held:raise ValueError('Action hold changed before 50-cycle boundary')
        action=held if row['action_active'] else [0.]*4;log=row['action_log']
        if (row['action']!=action or log['raw_action']!=action or log['experience_action']!=action or
            log['enabled'] is not row['action_active']):raise ValueError('Request/action permission mismatch')
        if row['action_active']:active_count+=1;last_active=i
        scalars=[row[k] for k in ('reward','discount','dt')]
        if any(type(v) not in (float,int) or not math.isfinite(v) for v in scalars) or not 0<scalars[1]<=1 or scalars[2]<=0:
            raise ValueError('Invalid transition scalar')
        # Expected payload encoding only: no NumPy tensors or replay object created.
        for values in (obs,nxt,action,scalars):digest.update(struct.pack('<'+'f'*len(values),*values))
        digest.update(struct.pack('<????',*flags))
    if rows[-1]['next_action_active'] or raw['warmup_draws']!=draws:raise ValueError('Terminal permission/draw ledger differs')
    value=0.
    for i in range(len(rows)-1,(last_active if last_active is not None else 0)-1,-1):
        value=rows[i]['reward']+rows[i]['discount']*value
    if not math.isfinite(value):raise ValueError('Nonfinite boundary target')
    return dict(id=expected_id,rows=len(rows),active_rows=active_count,warm_draws=draws,held=held,
        last_active_row=last_active,tail_return_at_boundary=value,expected_float32_payload_sha256=digest.hexdigest(),
        actor_fingerprint=raw['policy_sha256'])

def main():
    if (HERE/'recovery_assessment.json').exists():raise FileExistsError('Do not overwrite recovery evidence')
    registration=read(HERE/'registration.json')
    if sha(OLD/'delivery_manifest.json')!=registration['old_manifest_sha256']:raise ValueError('Old evidence seal changed')
    sealed=read(OLD/'delivery_manifest.json')['files'];pins={}
    def original(name):
        p=OLD/name
        if sha(p)!=sealed[name]['sha256']:raise ValueError('Changed original source '+name)
        pins[p.relative_to(ROOT).as_posix()]=sha(p)
        return p
    summary=read(original('execution_summary.json'));counter=read(original('execution/counter.json'))
    if summary['attempts']!=8 or summary['updates_completed']!=0 or counter['status']!='CLOSED':raise ValueError('Not the closed pre-update boundary')
    if (OLD/'execution/run/chain/update_journal.jsonl').exists():raise ValueError('Unexpected update journal')
    checkpoint=original('execution/run/checkpoints/zero/state.pt') # Hash only; never deserialize.
    original('execution/run/checkpoints/zero/manifest.json')
    original('execution/run/zero.reply.json');original('execution/run/zero.request.json')
    zero=json.loads(gzip.decompress(original('execution/run/zero_F50_J01.json.gz').read_bytes()))
    actor=zero['policy_sha256'];qualification=zero['qualification_sha256'];config=zero['config_sha256'];del zero
    results=[];draws=0
    for i in range(1,5):
        key='warmup_F50_J0'+str(i);base='execution/run/chain/'+key+'/'
        archive=original(base+'episode.json.gz');receipt=read(original(base+'status.json'))
        if receipt['archive_sha256']!=sha(archive):raise ValueError('Publication archive bytes changed')
        raw=json.loads(gzip.decompress(archive.read_bytes()))
        if raw['policy_sha256']!=actor or raw['qualification_sha256']!=qualification or raw['config_sha256']!=config:
            raise ValueError('Warmup policy/config/qualification differs from F0')
        physical_row=next(r for r in summary['episodes'] if r['id']==key)
        if hashlib.sha256(canonical(raw).encode()).hexdigest()!=physical_row['content_sha256']:
            raise ValueError('Replay differs from sealed physical content')
        result=inspect_warmup(raw,receipt,key,draws);draws=result['warm_draws'];results.append(result);del raw
    if sum(r['rows'] for r in results)!=19300 or draws!=388:raise ValueError('Unexpected warmup history')
    for p in [KIT/n for n in ('joint_chain.py','joint_checkpoint.py','joint_rollout.py','pilot_worker.py')]+[ROOT/'tools/learning/v4_sac.py',ROOT/'tools/learning/v4_replay.py']:
        pins[p.relative_to(ROOT).as_posix()]=sha(p)
    report=dict(stage_id='B2-SCOPE-14',status='SOURCE_COMPLETE_NUMERIC_RECONSTRUCTION_PENDING',
        episodes=results,replay_rows=19300,active_rows=sum(r['active_rows'] for r in results),warm_vector_draws=388,
        warm_scalar_draws=1552,held=results[-1]['held'],source_pins=pins,zero_checkpoint_sha256=sha(checkpoint),
        provenance='Read-only SCOPE13 zero checkpoint and four original published warmup archives; old grant remains closed.',
        state_components={
            'network_optimizer_temperature':'Zero checkpoint exists, independent zero restore passed; recorded updates are zero and all archived actor hashes match. Actual rebuilt tensors not loaded here.',
            'replay_boundary':'All 19300 source rows and terminal boundaries available in order; expected float32 payload digests computed. Actual V4Replay/boundary reconstruction pending.',
            'warm_rng':'SeedSequence([2026092716,1]); 388 uniform(-1,1,4) draws implied by complete per-episode hold records. NumPy stream equality and final bit_generator state pending.',
            'replay_boundary_rng':'No sampling before first update in bound source; expected SeedSequence streams 2 and 3 remain initial. Actual state comparison pending.',
            'torch_rng':'F0 uses deterministic prediction through a forked RNG; no online sample/update occurred. Unchanged RNG is source-supported, requires frozen-runtime equality check.',
            'active_transaction':'Interrupted process had begun online J01 bookkeeping. Candidate must reconstruct the prior completed warmup boundary, not resume this active transaction.'},
        numeric_restore_verified=False,lossless_resume_verified=False,training_admitted=False,restart_authorized=False,
        new_physics=0,new_learning=0,new_checkpoint_loads=0,new_replay_publications=0,cumulative_dynamic=245,
        next_step='Prepare a separately bound numeric reconstruction and independent restore gate; do not rerun the eight completed physical episodes or reopen SCOPE13.')
    if any(k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3') for k in sys.modules):raise AssertionError('Backend import in offline audit')
    write(HERE/'recovery_assessment.json',report)
    print(json.dumps({k:report[k] for k in ('status','replay_rows','active_rows','warm_vector_draws','numeric_restore_verified','new_physics','new_learning')},ensure_ascii=False))

if __name__=='__main__':main()
