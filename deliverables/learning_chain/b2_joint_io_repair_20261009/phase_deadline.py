"""Remember a phase's monotonic deadline across transient file access conflicts."""
import math
import time
from bounded_io import read

class PhaseDeadline:
    def __init__(self,whole_deadline):
        if type(whole_deadline) not in (int,float) or not math.isfinite(whole_deadline):
            raise ValueError('Finite whole-run deadline required')
        self.whole_deadline=whole_deadline;self.deadline=whole_deadline;self.last=None

    def check(self):
        if time.monotonic()>=self.deadline:raise TimeoutError('Hard supervised/phase deadline')

    def read_phase(self,path):
        self.check()
        try:phase=read(path,deadline=self.deadline)
        except FileNotFoundError:
            if self.last is not None:raise
            self.check();return None
        self.check()  # A new file cannot rescue a previously expired phase.
        if not isinstance(phase,dict):raise ValueError('Phase object required')
        kind=phase.get('kind');started=phase.get('started');limit=phase.get('limit_s')
        if (type(started) not in (int,float) or not math.isfinite(started) or started<=0 or
            type(limit) is not int or kind not in ('physical','between_episodes') or
            limit!=(1200 if kind=='physical' else 1800)):
            raise ValueError('Invalid phase kind/time/limit')
        if kind=='physical' and (not isinstance(phase.get('id'),str) or not phase['id']):
            raise ValueError('Physical phase ID required')
        if phase==self.last:return phase
        wall=time.time();mono=time.monotonic()
        if started>wall:raise ValueError('Phase cannot start in the future')
        if self.last is not None:
            if started<self.last['started']:raise ValueError('Phase order moved backward')
            if kind=='physical' and self.last.get('kind')==kind and phase['id']==self.last['id']:
                raise ValueError('Repeated physical phase changed its deadline')
        self.check()
        self.deadline=min(self.whole_deadline,mono+(started+limit-wall))
        self.last=phase;self.check()
        return phase
