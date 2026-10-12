"""Prepared exploration primitive; not connected to a training/physics entry.

The caller supplies its registered uniform RNG and must checkpoint that RNG
together with this state. No observation, geometry, case label or learned model
is consumed here. Base control and guard checks still run every control cycle.
"""
import math
from numbers import Real

PHASES=('INSERT','UNLOAD','SEARCH','WAIT_RECOVERY','FAILED')

def _action(value):
    try:result=list(value)
    except TypeError as exc:raise ValueError('Finite normalized action4 required') from exc
    if len(result)!=4 or any(isinstance(x,bool) or not isinstance(x,Real) or not math.isfinite(x) or abs(x)>1 for x in result):
        raise ValueError('Finite normalized action4 required')
    return [float(x) for x in result]

class WarmupHold:
    VERSION='prepared_temporal_warmup_v1'
    def __init__(self,draw,*,hold_cycles=50):
        if type(hold_cycles) is not int or hold_cycles not in (1,50):
            raise ValueError('Only registered 2ms control or 100ms candidate allowed')
        if not callable(draw):raise TypeError('External registered uniform RNG callable required')
        self.draw=draw;self.hold_cycles=hold_cycles;self.last_cycle=-1
        self.action=None;self.phase=None;self.remaining=0;self.draw_count=0;self.failed=False
        self.active_cycles=0;self.block_start_cycle=None

    def next(self,cycle_id,phase,enabled):
        if self.failed:raise RuntimeError('Sampling failed; automatic retry refused')
        if type(cycle_id) is not int or cycle_id!=self.last_cycle+1:
            raise ValueError('Exactly one call for each consecutive control cycle required')
        if cycle_id>=13000:raise RuntimeError('Total episode cycle cap reached')
        if type(enabled) is not bool or phase not in PHASES or (enabled and phase not in ('INSERT','SEARCH')):
            raise ValueError('Known policy phase and actual residual permission required')
        redrawn=False
        if not enabled:
            self.action=None;self.phase=None;self.remaining=0;self.block_start_cycle=None;action=[0.]*4
        else:
            if self.phase!=phase or self.remaining==0:
                try:action=_action(self.draw())
                except BaseException:
                    self.failed=True;raise
                self.action=action;self.remaining=self.hold_cycles;self.draw_count+=1;redrawn=True;self.block_start_cycle=cycle_id
            self.phase=phase;self.remaining-=1;self.active_cycles+=1;action=self.action.copy()
        self.last_cycle=cycle_id
        return dict(action=action.copy(),redrawn=redrawn,draw_count=self.draw_count,
            remaining=self.remaining,cycle_id=cycle_id,enabled=enabled,policy_phase=phase,block_start_cycle=self.block_start_cycle)

    def snapshot(self):
        return dict(version=self.VERSION,hold_cycles=self.hold_cycles,last_cycle=self.last_cycle,
            action=None if self.action is None else self.action.copy(),phase=self.phase,
            remaining=self.remaining,draw_count=self.draw_count,failed=self.failed,
            active_cycles=self.active_cycles,block_start_cycle=self.block_start_cycle)

    @classmethod
    def restore(cls,draw,state,*,expected_hold_cycles):
        new=cls(draw,hold_cycles=expected_hold_cycles)
        if not isinstance(state,dict) or set(state)!=set(new.snapshot()):raise ValueError('Complete sampler state required')
        if state['version']!=cls.VERSION or state['hold_cycles']!=expected_hold_cycles or type(state['hold_cycles']) is not int or state['failed'] is not False:
            raise ValueError('Sampler identity or failure state differs')
        for key,lo,hi in [('last_cycle',-1,12999),('remaining',0,expected_hold_cycles-1),('draw_count',0,13000),('active_cycles',0,13000)]:
            if type(state[key]) is not int or not lo<=state[key]<=hi:raise ValueError('Invalid sampler counter: '+key)
        active=state['active_cycles'];draws=state['draw_count'];last=state['last_cycle']
        if not 0<=active<=last+1 or not math.ceil(active/expected_hold_cycles)<=draws<=active:
            raise ValueError('Impossible active-cycle or RNG accounting')
        if state['phase'] is None:
            if state['action'] is not None or state['remaining']!=0 or state['block_start_cycle'] is not None:
                raise ValueError('Inactive sampler contains a stale action')
            if last>=0 and active>last:raise ValueError('Inactive current cycle counted as active')
        elif state['phase'] not in ('INSERT','SEARCH') or state['draw_count']==0:
            raise ValueError('Unregistered held-action state')
        else:
            start=state['block_start_cycle']
            if type(start) is not int or not 0<=start<=last or last-start>=expected_hold_cycles:
                raise ValueError('Impossible held block start')
            length=last-start+1
            if (state['remaining']!=expected_hold_cycles-length or active<length or
                    not draws-1<=active-length<=(draws-1)*expected_hold_cycles):
                raise ValueError('Held-block duration differs from counters')
            new.action=_action(state['action'])
        new.last_cycle=state['last_cycle'];new.remaining=state['remaining'];new.draw_count=state['draw_count'];new.phase=state['phase']
        new.active_cycles=state['active_cycles'];new.block_start_cycle=state['block_start_cycle']
        return new
