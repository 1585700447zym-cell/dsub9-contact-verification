"""Lazy numeric reuse: only configuration validation and explicit metering differ."""
from joint_contract import validate_config
_counter=None
_episode=None
_updates=0


def configure(counter):
    global _counter
    if _counter is not None:raise RuntimeError('Runtime already attached')
    _counter=counter


def take(key):
    if _counter is None:raise PermissionError('No current execution capability')
    _counter.take(key)


def open_episode(stage):
    global _episode
    if _episode is not None:raise RuntimeError('Episode already active')
    take('dynamic_episodes');take('environment_creations');take('resets')
    # Reserve every possible control operation BEFORE entering the backend.
    _counter.take('control_cycles',14500);_counter.take('native_steps',145000);_counter.take('observations',14501)
    allowance=0 if stage=='warmup' else 14500
    if allowance:_counter.take('policy_calls',allowance)
    _episode=dict(remaining=allowance,calls=0)


def close_episode(actual_calls):
    global _episode
    if _episode is None or _episode['calls']!=actual_calls:raise ValueError('Policy cost differs from physical transcript')
    _episode=None


def allow_updates(n):
    global _updates
    if _updates:raise RuntimeError('Update block still active')
    _counter.take('formal_updates',n);_updates=n


def metered_load(*args,**kwargs):
    take('tensor_loads')
    import torch
    return torch.load(*args,**kwargs)


def __getattr__(name):
    if name!='V4Updater':raise AttributeError(name)
    if _counter is None:raise PermissionError('No current execution capability')
    from tools.learning.v4_sac import V4Updater as NumericUpdater
    class JointUpdater(NumericUpdater):
        config_validator=staticmethod(validate_config)
        def __init__(self,config):
            validate_config(config);take('learner_constructions');super().__init__(config)
        def predict(self,*args,**kwargs):
            if _episode is None or _episode['remaining']<=0:raise RuntimeError('No forward allowance')
            _episode['remaining']-=1;_episode['calls']+=1
            return super().predict(*args,**kwargs)
        def update(self,*args,**kwargs):
            global _updates
            if _updates<=0:raise RuntimeError('No update allowance')
            _updates-=1
            return super().update(*args,**kwargs)
    globals()['V4Updater']=JointUpdater
    return JointUpdater
