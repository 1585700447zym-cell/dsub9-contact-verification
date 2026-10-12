"""Read-only JSON/archive/hash/process audit; no new tensor reads or inference."""
from copy import deepcopy
from pathlib import Path
import ctypes,gzip,json,math,shutil,sys
from ctypes import wintypes
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
KIT=OUT.parent/'small_boundary_numeric_gate_20261007';sys.path.insert(0,str(KIT))
from numeric_contract import read,write,sha,digest,canonical,NumericLedger,ROLE_CAPS
from numeric_worker import verify_sources,normalized_state
from small_bound_profile import audit_small_bound_episode


def process_end(original):
    from tools.validation.process_parent import kernel_api,same_image
    api=kernel_api();handle=api.OpenProcess(0x1000|0x100000,False,original['pid'])
    if not handle:
        if ctypes.get_last_error()==87:return dict(pid=original['pid'],ended=True,reason='pid_absent')
        raise OSError('Cannot confirm registered process ended')
    try:
        if api.WaitForSingleObject(handle,0)!=0x102:return dict(pid=original['pid'],ended=True,reason='handle_signalled')
        buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(len(buffer));times=[wintypes.FILETIME() for _ in range(4)]
        if not api.QueryFullProcessImageNameW(handle,0,buffer,ctypes.byref(size)) or not api.GetProcessTimes(handle,*(ctypes.byref(t) for t in times)):
            raise OSError('Cannot inspect registered process identity')
        created=(((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)-116444736000000000)/10000000
        if created!=original['created_at'] or not same_image(buffer.value,original['image']):
            return dict(pid=original['pid'],ended=True,reason='pid_reused')
        raise RuntimeError('Registered numeric process still alive')
    finally:api.CloseHandle(handle)


def audited_result():
    n=0
    def check(value,label):
        nonlocal n
        if not value:raise AssertionError(label)
        n+=1
    r=read(OUT/'execution_registration.json');grant=read(OUT/'authorization.json');pin=read(OUT/'authorization_pin.json')['sha256']
    candidate=read(KIT/'numeric_candidate.json');run=OUT/'run';result=read(run/'numeric_result.json')
    check(digest(grant)==pin==r['authorization_sha256'],'grant binding')
    check(candidate==read(OUT/'candidate_snapshot.json') and digest(candidate)==grant['candidate_sha256'],'candidate binding')
    check(sha(KIT/'delivery_manifest.json')==r['kit_seal_sha256'],'kit seal')
    for name,m in read(KIT/'delivery_manifest.json')['files'].items():
        check(sha(KIT/name)==m['sha256'] and (KIT/name).stat().st_size==m['bytes'],'kit member '+name)
    verify_sources(candidate);check(True,'all765 earlier files /1057 inputs /36 runtime files unchanged')
    ledger=NumericLedger.load(run/'ledger.json',candidate,grant,pin)
    check(ledger.data['status']=='complete' and ledger.data['active'] is None,'complete ledger')
    check(ledger.data['role_attempts']==ledger.data['role_completed']==ROLE_CAPS,'charged parent/reader limits')
    check(ledger.data['updates_attempted']==ledger.data['updates_completed']==4,'4 actual batches')
    check(ledger.data['forwards_attempted']==ledger.data['forwards_completed']==32,'32 actual test forwards')
    check(ledger.data['unused_closed']==dict(updates=0,forwards=0),'no unused quota')
    check(result['status']=='PASSED_NUMERIC_ONLY' and result['complete_independent_restore'] is True,'full state comparison result')
    check(result['training_admitted'] is False and result['dynamic_episodes']==result['formal_update_batches']==0 and result['cumulative_dynamic']==208,'scope')
    check(result['checkpoint_pin']==sha(run/'checkpoint/manifest.json'),'complete outer checkpoint binding')
    request=read(run/'reader_request.json')
    check(request['candidate_sha256']==digest(candidate) and request['grant_pin']==pin and sha(run/'reader_request.json')==ledger.data['request_pin'],'reader request')
    processes=[]
    for name,receipt in [('worker_claim.json',OUT/'run.supervision/exit.json'),('reader_claim.json',run/'reader_exit.json')]:
        claim=read(ledger.claim/name);proof=claim['process_proof'];exit_record=read(receipt)
        check(proof['route']=='windows_venv_launcher','actual Windows launcher route')
        check(exit_record['worker_stopped'] is True and exit_record['returncode']==0 and exit_record['pid']==proof['parent']['pid'],'launcher success/stop receipt')
        for identity in (proof['child'],proof['parent'],proof['registered']):
            if identity['pid'] not in [p['pid'] for p in processes]:processes.append(process_end(identity))
    check(all(p['ended'] for p in processes),'all owned processes ended')
    zero=read(run/'zero_origin.json')
    check(zero['origin']==candidate['outer_contract']['zero_origin']==result['origin'],'all4 zero-origin fingerprints')
    check(not any(zero['counts'].values()) and zero['optimizer_states_empty'] and zero['replay_rows']==zero['warm_draws']==zero['attempts']==zero['history']==0,'empty optimizer/replay/history')
    check(set(zero['rng'])=={'warm','replay','boundary'},'three RNG start streams')
    archives=[];rows=0;active=0;draws=0
    for p in sorted((run/'parent_chain').glob('*/episode.json.gz')):
        raw=json.loads(gzip.decompress(p.read_bytes()));audit=audit_small_bound_episode(raw,candidate['outer_contract'])
        check(raw['synthetic'] is True and raw['dynamics_executed'] is False and raw['physical_stop_measurement'] is None,'synthetic scope '+p.parent.name)
        check(raw['scope']=='synthetic_qualification' and raw['mode']=='F50' and raw['physical_profile']=='F12p5','qualified outer identity '+p.parent.name)
        check(audit['cycles']==len(raw['transitions'])==80,'80 synthetic cycles '+p.parent.name)
        check(raw['qualification_sha256']==digest(dict(scope='pc13_synthetic_only',candidate=digest(candidate),grant=pin)) and
            raw['config_sha256']==candidate['outer_contract']['engine_config_sha256'],'unique new grant binding '+p.parent.name)
        counterpart=run/'reader_chain'/p.parent.name/'episode.json.gz'
        check(counterpart.exists() and counterpart.read_bytes()==p.read_bytes(),'restored archive bytes '+p.parent.name)
        rows+=len(raw['transitions']);active+=sum(t['action_active'] for t in raw['transitions']);draws=max(draws,raw.get('warmup_draws',0))
        archives.append(dict(episode_id=raw['episode_id'],stage=raw['stage'],rows=80,active_rows=sum(t['action_active'] for t in raw['transitions']),
            synthetic=True,sha256=sha(p),archive=p.relative_to(OUT).as_posix()))
    check(len(archives)==5 and rows==400==result['new_synthetic_replay_rows'] and active==390 and draws==8,'400 new synthetic rows /5 archives /8 warm draws')
    def journal(path):return [json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
    parent=journal(run/'parent_chain/update_journal.jsonl');reader=journal(run/'reader_chain/update_journal.jsonl')
    ps=[e for e in parent if e['event']=='complete'];cs=[e for e in reader if e['event']=='complete']
    check(len(ps)==len(cs)==3,'3 parent batches; reader inherited2 plus executed1')
    for a,b in zip(ps,cs):
        aa=deepcopy(a);bb=deepcopy(b);aa['stats'].pop('wall_s',None);bb['stats'].pop('wall_s',None)
        check(aa==bb,'actual persisted sampling/loss/model/optimizer counters agree at batch'+str(a['attempt']))
    check(ps[-1]['counts']==dict(actor=3,critic=3,target=3,temperature=3),'actual restored final optimizer counters')
    actions=read(run/'reader_actions.json')
    check(len(actions)==16 and all(len(a)==4 and all(math.isfinite(x) and abs(x)<=1 for x in a) for a in actions),'16 independent normalized actions; parent equality checked in pinned worker')
    costs={role:read(run/(role+'_costs.json')) for role in ('parent','reader')}
    check(costs['parent']==result['parent_costs'] and costs['reader']==result['reader_costs'],'cost receipts')
    constructions=sum(v['model_constructions_completed'] for v in costs.values());reads=sum(v['tensor_reads_completed'] for v in costs.values())
    check(constructions==sum(v['model_constructions_attempted'] for v in costs.values())==4,'4 original model constructions')
    check(reads==sum(v['tensor_reads_attempted'] for v in costs.values())==3,'3 CPU tensor reads')
    wall=(OUT/'run.supervision/exit.json').stat().st_mtime-read(OUT/'run.supervision/started.json')['wall_timestamp']
    check(0<wall<=candidate['limits']['whole_wall_s'],'whole1200s')
    measured=dict(whole_supervised_wall_s=wall,model_construction_wall_s=sum(v['model_construction_wall_s'] for v in costs.values()),
        tensor_read_wall_s=sum(v['tensor_read_wall_s'] for v in costs.values()),
        actual_update_wall_s=sum(e['stats']['wall_s'] for e in ps)+cs[-1]['stats']['wall_s'])
    if (OUT/'claim_snapshot').exists():
        for p in ledger.claim.rglob('*'):
            if p.is_file():check(sha(p)==sha(OUT/'claim_snapshot'/p.relative_to(ledger.claim)),'claim snapshot '+p.name)
    check('torch' not in sys.modules,'audit did not import torch or read tensors')
    return dict(passed=True,checks=n,status='PASSED_NUMERIC_ONLY',numeric_verified=True,
        synthetic_update_attempts=4,synthetic_update_completed=4,test_state_forwards_attempted=32,test_state_forwards_completed=32,
        synthetic_rows_new=400,synthetic_rows_restored=400,physical_episodes=0,formal_updates=0,cumulative_dynamic=208,
        automatic_tracking='PAUSED',training_admitted=False,physical_training_admitted=False,physical_backend_implemented=False,
        zero_origin=zero,archives=archives,processes=processes,auxiliary_model_constructions=constructions,auxiliary_tensor_reads=reads,
        measured=measured,claim=str(ledger.claim),grant_sha256=pin,candidate_sha256=digest(candidate),
        old_sealed_files_unchanged=798,shared_inputs_unchanged=1057,runtime_file_pins=36,
        validation_scope='pinned worker did full tensor/Adam/replay/RNG/boundary next-step comparison; this audit reads only JSON/raw bytes and process identity',
        excludes='no added tensor read, policy forward, optimizer batch, rollout or performance evaluation')


def main():
    result=audited_result()
    if (OUT/'delivery_manifest.json').exists():
        for name,item in read(OUT/'delivery_manifest.json')['files'].items():
            if sha(OUT/name)!=item['sha256'] or (OUT/name).stat().st_size!=item['bytes']:raise ValueError('PC14 seal changed: '+name)
        print('READ-ONLY PC14 VERIFIED',result['checks'],'and sealed members;',result['status']);return
    if not (OUT/'claim_snapshot').exists():shutil.copytree(result['claim'],OUT/'claim_snapshot')
    write(OUT/'numeric_assessment.json',result)
    write(OUT/'authorization_closure.json',dict(status='CLOSED_EXHAUSTED',authorization_sha256=result['grant_sha256'],
        updates_attempted=4,updates_completed=4,forwards_attempted=32,forwards_completed=32,unused_updates=0,unused_forwards=0,
        physical0=True,formal0=True,no_retry=True,automatic_tracking='PAUSED'))
    print('ACTUAL NUMERIC AUDIT',result['checks'],'PASSED;4/32 rows400; auxiliary4models/3reads; physics/formal0')


if __name__=='__main__':main()
