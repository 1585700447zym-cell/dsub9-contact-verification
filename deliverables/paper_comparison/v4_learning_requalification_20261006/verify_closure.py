"""Offline closure checks; never rerun physics or optimizers."""
from pathlib import Path
import datetime, hashlib, json, zipfile
OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
def read(p): return json.loads(p.read_text(encoding='utf8'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert not (OUT/'delivery_manifest.json').exists(), 'Already sealed'
    a=read(OUT/'assessment.json'); l=read(OUT/'run/ledger.json'); c=read(OUT/'configuration.json')
    assert a['status']==l['status']=='complete' and a['completed']==28 and a['audit_errors']==[]
    assert a['formal_updates']==a['formal_update_attempts']==4000 and l['unused_closed']==0
    assert all(e['status']=='finished' for e in l['episodes']) and l['inputs_unchanged']
    assert all(e['outcome']['simulation_valid'] and e['outcome']['physical_stopped'] and not any(e['outcome']['guard_violations'].values()) for e in l['episodes'])
    assert all(not e.get('reference_problems',[]) and not e.get('actual_reference_failed',False) for e in l['episodes'])
    restores=[e for e in l['episodes'] if e['spec']['stage']=='restore']
    assert len(restores)==2 and all(e['restore_exact'] for e in restores)
    pins=c['input_sha256']; changed={k for k,v in pins.items() if sha(ROOT/k)!=v}
    assert not changed, changed
    snapshot=read(OUT/'source_snapshot.json')
    assert snapshot['files']==pins and sha(OUT/'source_snapshot.zip')==snapshot['archive_sha256']
    with zipfile.ZipFile(OUT/'source_snapshot.zip') as z:
        assert set(z.namelist())==set(pins)
        assert all(hashlib.sha256(z.read(k)).hexdigest()==v for k,v in pins.items())
    previous={}
    for relative, digest in [
        ('paper_comparison/search_boundary_fix_20261006/delivery_manifest.json','ae124ffa9d47d2ed2719b64cbf1202241ded4287c5be842b61ea962b13c8e8e5'),
        ('paper_comparison/v4_learning_pilot_20261006/delivery_manifest_v2.json','f740dd75a922b5962c293da16213bdc2818fef6bca6ec885a7b28a1d3f3c80a9'),
        ('paper_comparison/v4_continuation_20261006/delivery_manifest.json','536a599cd5b8baaab8fbb8951f8b1557a6eb40bc2d215f12603103d0a07a4673'),
        ('project_audit/complexity_20261006/delivery_manifest.json','11081e20a423bdefede246a1686db9a58d9723b2d1e962977eed31a86bedfdbc')]:
        p=ROOT/'deliverables'/relative; m=read(p); assert sha(p)==digest
        for k,v in m['files'].items():
            assert sha(p.parent/k)==v['sha256'] and (p.parent/k).stat().st_size==v['bytes'], k
        previous[relative]=dict(sha256=digest,files=len(m['files']),unchanged=True)
    gates={}
    for mode in ('F50','S50'):
        files=sorted((OUT/'run').glob(mode+'*.reader.json')); assert len(files)==9
        states=[read(p) for p in files]; final=read(OUT/'run'/(mode+'_online_3.reader.json'))
        cp=a['checkpoints'][mode]
        assert final['counts']==cp['updates']==dict(critic=2000,actor=2000,temperature=2000,target=2000)
        assert final['fingerprints']==cp['fingerprints'] and final['replay_rows']==cp['replay_rows']
        h=read(OUT/'run'/(mode+'_history.json')); assert len(h)==2000
        assert [r['critic_batches'] for r in h]==list(range(1,2001))
        journal=[json.loads(x) for x in (OUT/'run/chains'/mode/'update_journal.jsonl').read_text(encoding='utf8').splitlines()]
        assert len(journal)==4000
        assert all(journal[2*i]['event']=='attempt' and journal[2*i+1]['event']=='complete' and journal[2*i]['attempt']==journal[2*i+1]['attempt']==i+1 for i in range(2000))
        publications=[e for e in l['episodes'] if e['spec']['mode']==mode and e.get('publication')]
        assert len(publications)==8 and all(e['spec']['stage'] in ('warmup','online') for e in publications)
        gates[mode]=dict(complete_read_gates=len(states),counts=final['counts'],replay_rows=final['replay_rows'],history_batches=len(h),durable_journal_events=len(journal))
    negatives=[e['id'] for e in l['episodes'] if e['outcome']['task_outcome']=='TASK_FAILURE']
    assert len(negatives)==2 and all(e.get('publication',{}).get('committed',0)>0 for e in l['episodes'] if e['id'] in negatives)
    recoveries=[x for x in (OUT/'execution.log').read_text(encoding='utf8').splitlines() if x.startswith('atomic_json_replace_recovered:')]
    elapsed=(datetime.datetime.fromisoformat(l['ended_at'])-datetime.datetime.fromisoformat(l['started_at'])).total_seconds()
    result=dict(passed=True,at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(),
        source_files=len(pins),source_unchanged=True,zip_members_checked=len(pins),previous_seals=previous,
        independent_archive_reward_rows=sum(r['independent_reward_rows'] for r in a['rows']),
        checkpoint_gates=gates,negative_episodes_published=negatives,restore_exact=2,
        json_replace_recoveries=recoveries,optimizer_or_physical_retry=0,total_elapsed_seconds=elapsed,
        scope='registered finite development pilot; no independent-test or method-superiority claim')
    (OUT/'closure_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({k:v for k,v in result.items() if k not in ('previous_seals','json_replace_recoveries')},ensure_ascii=False))
if __name__=='__main__': main()
