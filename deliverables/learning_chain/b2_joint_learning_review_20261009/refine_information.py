"""Resolve event alignment and whole-trajectory clipping from existing records."""
import gzip
import json
import math
from pathlib import Path
import sys

OUT=Path(r'D:\dsub9项目计划\first_stage_sim\.worktrees\dsub9-v1-contact-validation\deliverables\learning_chain\b2_joint_learning_review_20261009')
sys.path.insert(0,str(OUT))
from analyze import SOURCE,read,sha,save

def main():
    assert not (OUT/'delivery_manifest.json').exists()
    analysis=read(OUT/'analysis.json'); short={}; results=[]
    for episode in analysis['episodes']:
        name=episode['id'];p=SOURCE/'run'/(name+'.json.gz')
        assert sha(p)==episode['source_archive_sha256']
        with gzip.open(p,'rt',encoding='utf-8') as stream:raw=json.load(stream)
        fields={}; vectors=0; snapshots=[c['before'] for c in raw['cycles']]+[raw['cycles'][-1]['after']]
        for i,s in enumerate(snapshots):
            vectors+=1
            for field in raw['observation_schema']:
                for component,(value,scale) in enumerate(zip(s['policy_raw'][field['name']],field['scale'])):
                    normalized=value/scale;recorded=s['policy_observation'][field['start']+component]
                    assert math.isfinite(normalized) and math.isfinite(recorded)
                    assert math.isclose(recorded,max(-10.,min(10.,normalized)),rel_tol=2e-7,abs_tol=1e-8)
                    if abs(normalized)<=10:continue
                    key=field['name']+'['+str(component)+']'
                    row=fields.setdefault(key,dict(occurrences=0,permitted=0,contact=0,
                        first_time_s=s['time_s'],last_time_s=s['time_s'],max_abs_unclipped_normalized=0.,phases={}))
                    row['occurrences']+=1;row['permitted']+=int(s['residual_enabled'])
                    row['contact']+=int(s['state']['contact_count']>0);row['last_time_s']=s['time_s']
                    row['max_abs_unclipped_normalized']=max(row['max_abs_unclipped_normalized'],abs(normalized))
                    phase=s['controller_state']['phase']+'/'+s['state']['phase']
                    row['phases'][phase]=row['phases'].get(phase,0)+1
        results.append(dict(id=name,vectors_checked=vectors,clipped_fields=fields,
                            clipped_occurrences=sum(f['occurrences'] for f in fields.values())))
        short[name]=[dict(time_s=s['time_s'],vector=s['policy_observation'],
                        features=s['policy_observation'][:6]+s['policy_observation'][24:30],
                        contact=s['state']['contact_count'],enabled=s['residual_enabled']) for s in snapshots[:163]]
        print(json.dumps(dict(id=name,vectors=vectors,fields=fields),ensure_ascii=False),flush=True)
        del raw,snapshots
    pairs=[]
    for left,right in [('J01_zero','J03_zero'),('J02_zero','J04_zero')]:
        a=short[left];b=short[right];n=162
        assert a[n]['contact']>0 and b[n]['contact']>0 and a[n]['time_s']==b[n]['time_s']
        pre=[(x,y) for x,y in zip(a,b) if not x['contact'] and not y['contact']]
        pairs.append(dict(left=left,right=right,same_time_s=a[n]['time_s'],
                          both_contact=True,both_enabled=a[n]['enabled'] and b[n]['enabled'],
                          same_time_normalized_feature_difference=[x-y for x,y in zip(a[n]['features'],b[n]['features'])],
                          left_features=a[n]['features'],right_features=b[n]['features'],
                          precontact_common_vectors=len(pre),precontact_max_vector_difference=max(abs(x-y) for z,s in pre for x,y in zip(z['vector'],s['vector'])),
                          exact_initial_equality=a[0]['vector']==b[0]['vector'],
                          sensor_noise_or_identifiability_test=False))
    initial=analysis['episodes'][0]['initial_vector']
    save('information_refinement.json',dict(episodes=results,same_time_zero_pairs=pairs,
         all_eight_initial_vectors_identical=all(e['initial_vector']==initial for e in analysis['episodes']),
         total_vectors_checked=sum(e['vectors_checked'] for e in results),new_physics=0,new_policy_forwards=0,new_updates=0,
         note='Clipping uses raw/scale > 10, including final observation. No noise threshold fitted.'))
    print(json.dumps(dict(same_time_zero_pairs=pairs),ensure_ascii=False),flush=True)

if __name__=='__main__':main()
