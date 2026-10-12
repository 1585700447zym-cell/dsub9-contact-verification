"""Frozen 12-attempt joint-pose schedule; standard library only."""
from copy import deepcopy
import hashlib
from itertools import product
import json
import math
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
PROPOSAL=OUT/'candidate.json'
# Set once by preparation before binding; this module is then included in binding.
PROPOSAL_PIN='1cde8986b548efb82ad971f3e47ad1c416b7ab5cd661f6fb7ee0881cbd10a986'

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'),parse_constant=lambda s:(_ for _ in ()).throw(ValueError('Nonfinite '+s)))
def proposal():
    if sha(PROPOSAL)!=PROPOSAL_PIN:raise ValueError('Scope proposal changed')
    return read(PROPOSAL)
def validate_candidate(candidate,parent):
    c=proposal()
    if canonical(candidate)!=canonical(c):raise ValueError('Unregistered candidate')
    source=ROOT/c['parent']['configuration']
    if sha(source)!=c['parent']['configuration_sha256'] or canonical(parent)!=canonical(read(source)):
        raise ValueError('Parent physical configuration changed')
    return deepcopy(c)
def case_kwargs(spec):
    if not any(canonical(spec)==canonical(row) for row in proposal()['cases']):raise ValueError('Unregistered case')
    return dict(name=spec['id'],x_offset_m=spec['x_um']*1e-6,y_offset_m=spec['y_um']*1e-6,
        roll_rad=math.radians(spec['roll_deg']),pitch_rad=math.radians(spec['pitch_deg']),
        start_origin_z_m=spec['start_origin_z_m'],target_depth_m=spec['target_depth_m'])

AXES=tuple(tuple(sign if i==axis else 0 for i in range(4)) for axis in range(4) for sign in (1,-1))
CORNERS=tuple(product((-1,1),repeat=4))
def schedule_position(profile,cycle):
    if type(cycle) is not int or cycle<0 or profile not in ('A_AXIS','B_CORNERS'):raise ValueError('Invalid schedule inputs')
    patterns=AXES if profile=='A_AXIS' else CORNERS
    offset=cycle%(len(patterns)*51)
    hold=50 if offset<len(patterns)*50 else 1
    index=offset//50 if hold==50 else offset-len(patterns)*50
    return patterns[index],hold,index
def profile_action(profile,cycle,enabled):
    if type(enabled) is not bool:raise ValueError('Boolean permission required')
    pattern,_,_=schedule_position(profile,cycle)
    return list(pattern) if enabled else [0.]*4
def attempt_specs(candidate):
    if canonical(candidate)!=canonical(proposal()):raise ValueError('Unregistered candidate')
    cases={c['id']:c for c in candidate['cases']}
    return [dict(row,kind='dynamic',purpose=row['kind'],case=deepcopy(cases[row['case']])) for row in candidate['attempts']]
def healthy(entry):
    out=entry.get('outcome') or {}
    return (entry.get('status')=='finished' and entry.get('audit_passed') is True and
        out.get('simulation_valid') is True and out.get('physical_stopped') is True and
        out.get('task_outcome') in ('FULL_SUCCESS','TASK_FAILURE') and out.get('guard_violations')=={'contact':False,'motion':False})
def next_attempt(entries,candidate):
    specs=attempt_specs(candidate)
    if len(entries)>len(specs):raise ValueError('Attempt ceiling exceeded')
    for index,row in enumerate(entries):
        if (row.get('id'),row.get('kind'))!=(specs[index]['id'],'dynamic'):raise ValueError('Skipped/duplicated/reordered attempt')
        if not healthy(row):return None
    return deepcopy(specs[len(entries)]) if len(entries)<len(specs) else None
