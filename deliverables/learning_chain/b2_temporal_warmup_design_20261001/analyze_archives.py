"""Saved-byte analysis only. Never imports a model, environment, or trainer."""
import builtins,gzip,hashlib,json,math,statistics
from pathlib import Path
original=builtins.__import__
def guard(name,*a,**k):
    if name.split('.')[0] in ('torch','mujoco','stable_baselines3','tools'):
        raise RuntimeError('Archive-only analysis forbids execution imports')
    return original(name,*a,**k)
builtins.__import__=guard
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OLD=ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
B=ROOT/'deliverables/learning_chain/b2_actor_lr_b_eval_20261001'
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
pins=read(OLD/'sealed_files.json');pins.update(read(B/'result_analysis/assessment.json')['input_sha256'])
inputs={}
def raw(path):
    key=path.relative_to(ROOT).as_posix();actual=sha(path)
    if pins[key]!=actual:raise ValueError('Archived input changed: '+key)
    inputs[key]=actual;return json.loads(gzip.decompress(path.read_bytes()))
def windows(rows,width):
    # Full non-overlapping windows; reset at every permission discontinuity.
    out=[];block=[]
    for r in rows:
        if not r['action_active']:block=[];continue
        block.append(r)
        if len(block)==width:
            out.append([sum(x['action'][j]*x['dt'] for x in block)/sum(x['dt'] for x in block) for j in range(4)])
            block=[]
    return out
def stats(raw):
    rows=raw['transitions'];active=[r for r in rows if r['action_active']]
    first_contact=next((r for r in rows if r['trace_row']['contact_count']>0),None)
    first_cross=next((r for r in rows if raw['case']['x_offset_m'] and r['trace_row']['position_m'][0]*raw['case']['x_offset_m']<0),None)
    start=rows[0]['observation'];pre=[r for r in active if all(v==0 for v in r['observation'][:24])]
    result=dict(case=raw['case'],outcome=raw['outcome'],cycles=len(rows),active_cycles=len(active),
        first_contact_s=None if first_contact is None else first_contact['trace_row']['time_s'],
        first_cross_s=None if first_cross is None else first_cross['trace_row']['time_s'],
        initial_observation=start,zero_wrench_history_active_cycles=len(pre),
        zero_wrench_history_x_mean=statistics.mean(r['action'][0] for r in pre) if pre else None,
        full_active_x_mean=statistics.mean(r['action'][0] for r in active),windows={})
    for width in (10,50,200):
        blocks=windows(rows,width)
        result['windows'][str(width*.002)]=dict(count=len(blocks),axes=[dict(
            rms_mean=math.sqrt(statistics.mean(b[j]**2 for b in blocks)),
            max_abs_mean=max(abs(b[j]) for b in blocks),
            fraction_abs_mean_ge_08=sum(abs(b[j])>=.8 for b in blocks)/len(blocks),
            positive_fraction=sum(b[j]>0 for b in blocks)/len(blocks)) for j in range(4)])
    return result
data={}
for i in range(4):data['warmup_'+str(i)]=stats(raw(OLD/f'run/training_episodes/train_{i:02d}/episode.json.gz'))
for case in ('x_pos_100','x_neg_100'):
    data['initial_'+case]=stats(raw(OLD/f'run/initial/episodes/{case}/episode.json.gz'))
    data['B_'+case]=stats(raw(B/f'run/episodes/{case}/episode.json.gz'))
positive=data['B_x_pos_100']['initial_observation'];negative=data['B_x_neg_100']['initial_observation']
diffs=[dict(index=i,positive=a,negative=b) for i,(a,b) in enumerate(zip(positive,negative)) if a!=b]
pooled={}
for width in ('0.02','0.1','0.4'):
    count=sum(data['warmup_'+str(i)]['windows'][width]['count'] for i in range(4))
    pooled[width]=dict(count=count,axes=[])
    for j in range(4):
        entries=[data['warmup_'+str(i)]['windows'][width] for i in range(4)]
        pooled[width]['axes'].append(dict(rms_mean=math.sqrt(sum(e['count']*e['axes'][j]['rms_mean']**2 for e in entries)/count),
            max_abs_mean=max(e['axes'][j]['max_abs_mean'] for e in entries),
            fraction_abs_mean_ge_08=sum(e['count']*e['axes'][j]['fraction_abs_mean_ge_08'] for e in entries)/count))
result=dict(status='archive_analysis_complete',new_model_forwards=0,new_physics=0,new_updates=0,
    first_observation_width=len(positive),opposite_x_initial_observations_equal=not diffs,initial_differences=diffs,
    pooled_warmup_windows=pooled,episodes=data,input_sha256=inputs,
    interpretation='Window statistics describe saved requests, not physical counterfactuals or policy value.')
with (HERE/'archive_analysis.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
print(json.dumps({k:v for k,v in result.items() if k not in ('episodes','input_sha256')},ensure_ascii=False))
for name,r in data.items():
    print(json.dumps(dict(name=name,first_contact=r['first_contact_s'],first_cross=r['first_cross_s'],
        x_mean=r['full_active_x_mean'],x_100ms=r['windows']['0.1']['axes'][0]),ensure_ascii=False))
