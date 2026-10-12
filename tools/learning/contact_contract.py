"""Explicit execution version derived from the immutable B2-11 configuration."""
from copy import deepcopy
import json
import math
import numpy as np
from .admission import canonical, digest
from .runtime import ROOT

PREPARATION = ROOT/'deliverables/learning_chain/b2_contact_preparation_20260927'
PREPARATION_SHA = '5cd1a1857a5c4093c9962c50eda6f577d6f273f5957e12fb0727043545c4a020'
CONFIG = 'docs/stage_b/四点接触短训配置_v1.json'
POINTS = ((-.0001,0.),(.0001,0.),(0.,-.0001),(0.,.0001))


def contact_config():
    if digest(PREPARATION/'manifest.json') != PREPARATION_SHA: raise ValueError('Preparation manifest changed')
    files=json.loads((PREPARATION/'manifest.json').read_text(encoding='utf-8'))['files']
    if digest(ROOT/CONFIG)!=files[CONFIG]: raise ValueError('Preparation configuration changed')
    c=json.loads((ROOT/CONFIG).read_text(encoding='utf-8'))
    c['version']='contact_four_point_execution_v1'
    c['execution']['preparation_only']=False
    return c


def validate_config(config):
    if canonical(config)!=canonical(contact_config()): raise ValueError('Unreviewed contact execution configuration')


def validate_case(case):
    fields=('x_offset_m','y_offset_m','roll_rad','pitch_rad','start_origin_z_m','target_depth_m')
    if not isinstance(case,dict) or any(type(case.get(k)) not in (int,float) or not math.isfinite(case[k]) for k in fields):
        raise ValueError('Finite numeric case required')
    if ((case['x_offset_m'],case['y_offset_m']) not in POINTS or case['roll_rad']!=0 or case['pitch_rad']!=0 or
            case['start_origin_z_m']!=-.004 or case['target_depth_m']!=.004): raise ValueError('Case outside four registered points')


class ContactSampler:
    def __init__(self, config):
        validate_config(config); self.seed=config['sampling']['seed']; self.count=0
        self.rng=np.random.Generator(np.random.PCG64(np.random.SeedSequence([self.seed,0])))
    def next_case(self):
        if self.count>=6: raise RuntimeError('Six-attempt scope exhausted')
        x,y=POINTS[int(self.rng.integers(0,4))]
        case=dict(name=f'contact_{self.count:06d}',x_offset_m=x,y_offset_m=y,roll_rad=0.,pitch_rad=0.,
                  start_origin_z_m=-.004,target_depth_m=.004)
        self.count+=1
        return case
    def load_state(self,state):
        if set(state)!={'count','rng'} or type(state['count']) is not int or not 0<=state['count']<=6:
            raise ValueError('Invalid contact sampler state')
        other=ContactSampler(contact_config())
        for _ in range(state['count']): other.next_case()
        if canonical(other.rng.bit_generator.state)!=canonical(state['rng']): raise ValueError('Sampler RNG/count mismatch')
        self.count=other.count; self.rng=other.rng


def guard_clear(raw):
    facts=raw['guard_facts']; outcome=raw['outcome']
    return (facts.get('simulation_valid') is True and facts.get('contact_reasons')==[] and
        facts.get('motion_reasons')==[] and facts.get('invalid_reasons')==[] and
        outcome.get('simulation_valid') is True and outcome.get('physical_stopped') is True and
        outcome.get('valid_for_learning') is True and
        outcome.get('guard_violations')==dict(contact=False,motion=False) and
        outcome.get('task_outcome') in ('FULL_SUCCESS','TASK_FAILURE') and raw.get('fault') is None)
