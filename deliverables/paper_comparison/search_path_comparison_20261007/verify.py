"""Independent raw arithmetic checks plus source/rolling-document consistency."""
from pathlib import Path
import csv,gzip,hashlib,json,math,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
sys.path.insert(0,str(OUT))
import analyze

def close(a,b,tol=1e-9):
    if not math.isclose(a,b,abs_tol=tol,rel_tol=0):raise AssertionError((a,b,tol))

def main():
    d=analyze.read(OUT/'diagnosis.json');proof=analyze.verify_sources();assert proof==d['source_proof']
    full=list(csv.DictReader((OUT/'search_cycles.csv').open(encoding='utf8')))
    align=list(csv.DictReader((OUT/'alignment.csv').open(encoding='utf8')))
    assert len(full)==15626 and d['archive_cycles']==28465 and d['search_segments']==5
    rows=boundaries=0
    for record in d['records']:
        p=ROOT/record['path'];assert analyze.sha(p)==record['sha256']
        raw=json.loads(gzip.decompress(p.read_bytes()))
        index=next(s['start'] for s in raw['observation_schema'] if s['name']=='policy_phase')
        selected=[i for i,t in enumerate(raw['transitions']) if t['observation'][index+2]==1.]
        expected=[i for s in record['segments'] for i in range(s['start_cycle'],s['end_cycle_exclusive'])]
        assert selected==expected
        for k,seg in enumerate(record['segments'],1):
            start,end=seg['start_cycle'],seg['end_cycle_exclusive'];tr=raw['trace'][start:end+1]
            ts=raw['transitions'][start:end];actions=raw['actions'][start:end]
            close(sum(t['dt'] for t in ts),seg['duration_s'])
            physical=sum(math.hypot(b['position_m'][0]-a['position_m'][0],b['position_m'][1]-a['position_m'][1]) for a,b in zip(tr,tr[1:]))*1e6
            reference=sum(math.hypot(b['reference_qpos'][0]-a['reference_qpos'][0],b['reference_qpos'][1]-a['reference_qpos'][1]) for a,b in zip(tr,tr[1:]))*1e6
            close(physical,seg['actual_xy_path_um']);close(reference,seg['reference_xy_path_um'])
            peak_origin=seg['exit_event']['progress_origin_z_m'] if 'progress_origin_z_m' in seg['exit_event'] else tr[-1]['search_progress_origin_z_m']
            maximum=(max(r['position_m'][2] for r in tr)-raw['trace'][0]['position_m'][2]-peak_origin)*1e6
            close(maximum,seg['max_net_depth_beyond_frozen_peak_um'])
            saved=[r for r in full if r['method']==record['method'] and int(r['search'])==k]
            assert len(saved)==end-start
            for r,i in zip(saved,range(start,end)):
                close(float(r['time_s']),raw['trace'][i]['time_s'],1e-12)
                close(float(r['actual_y']),raw['trace'][i]['position_m'][1]*1e6)
                close(float(r['command_roll_mrad_s']),raw['actions'][i]['actual_end_limited_command'][3]*1000)
                close(float(r['action_y']),raw['actions'][i]['raw_action'][1],1e-12)
                rows+=1
            if record['method']=='G50':
                event=seg['exit_event'];radius=120e-6
                assert math.hypot(*event['reference_xy_m'])<=radius+1e-12
                assert math.hypot(*event['predicted_reference_xy_m'])>radius+1e-12
                assert maximum<0 and event['reference_boundary_end'] and not event['reference_boundary_final_segment']
                theta=tr[-1]['spiral_theta_rad'];dt=raw['transitions'][end]['dt'];b=40e-6/(2*math.pi)
                nxt=theta+150e-6/math.hypot(b*theta,b)*dt
                for axis,fun in enumerate((math.cos,math.sin)):
                    current=b*theta*fun(theta);target=b*nxt*fun(nxt)
                    ff=(target-current)/dt;tracking=5*(current-event['reference_xy_m'][axis])
                    previous=tr[-1]['limited_command_world'][axis]
                    cmd=min(previous+.005*dt,max(previous-.005*dt,min(1e-3,max(-1e-3,min(300e-6,max(-300e-6,ff+tracking))))))
                    close(event['reference_xy_m'][axis]+cmd*dt,event['predicted_reference_xy_m'][axis],1e-15)
                boundaries+=1
            else:assert seg['exit_event']['reason']=='SEARCH_ADVANCED' and maximum>=100.
            for r in align:
                if r['method']!=record['method'] or int(r['search'])!=k:continue
                key=r['alignment_kind'];target=float(r['requested_value'])
                nearest=min(saved,key=lambda x:abs(float(x[key])-target))
                assert r['cycle']==nearest['cycle']
    assert rows==15626 and boundaries==2
    docs=__import__('update_documents').DOCS
    for name in docs:
        text=(ROOT/name).read_text(encoding='utf8');assert text.count('<!-- pc10-current -->')==1
        current=text.split('<!-- pc10-current -->')[1].split('<!-- /pc10-current -->')[0]
        assert all(v in current for v in ('208','PAUSED','新训练准入无','完整B.2/C','路线决定.md'))
        assert (OUT/'documents_snapshot'/name).read_bytes()==(ROOT/name).read_bytes()
        assert (OUT/'before_documents'/name).exists()
    proof2=analyze.verify_sources();assert proof2==proof
    result=dict(passed=True,archives=4,archive_cycles=28465,segments=5,independent_search_rows=rows,
        boundary_equations_exact=boundaries,source_proof=proof,rolling_documents_verified=len(docs),
        costs=d['costs'],training_admission=False,automatic_tracking='PAUSED',old_budgets='closed',
        checks='six hand cases plus 21 prior pure archive tests; independent raw arithmetic and source hashes',
        scope='offline stage evidence only, no full-repository/physics/paper/B.2/C acceptance claim')
    seal=OUT/'delivery_manifest.json'
    if seal.exists():
        for rel,meta in analyze.read(seal)['files'].items():
            p=OUT/rel;assert p.stat().st_size==meta['bytes'] and analyze.sha(p)==meta['sha256'],rel
        print('SEALED verification passed',len(analyze.read(seal)['files']),'files')
    else:analyze.write(OUT/'verification.json',result)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
