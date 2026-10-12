"""One bounded read-only diagnosis; cannot restart the failed experiment."""
from copy import deepcopy
import json
import os
import threading
import time
import paired_contract as C


def event_payload(event, elapsed, details):
    return {**details, 'event': event, 'elapsed_s': elapsed}


def main():
    output = C.HERE / 'offline_reader_diagnosis_20261003'
    output.mkdir(exist_ok=False)
    started = time.perf_counter()
    calls = dict(physics=0, model_forward=0, optimizer=0)
    phase = {'name': 'startup'}

    def record(event, **details):
        with (output / 'events.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(event_payload(event, time.perf_counter()-started, details))+'\n')

    def deadline():
        record('deadline', phase=phase['name'], calls=calls)
        os._exit(124)

    timer = threading.Timer(300, deadline)
    timer.daemon = True
    timer.start()
    record('scope', dynamic=0, learning_batches=0, deadline_s=300, experiment_resume=False, pid=os.getpid())

    def timed(name, function, *args, **kwargs):
        prior = phase['name'];phase['name'] = name;t = time.perf_counter()
        record('begin', phase=name)
        try:
            return function(*args, **kwargs)
        finally:
            record('end', phase=name, duration_s=time.perf_counter()-t)
            phase['name'] = prior

    try:
        pins = C.read(C.HERE / 'execution_pins.json')
        timed('binding', C.verify, pins['binding_sha256'], pins['authorization_sha256'])
        from run_pair import select_runtime
        timed('qualified_runtime', select_runtime)
        import torch, mujoco

        def forbid(kind):
            def fail(*args, **kwargs):
                calls[kind] += 1
                raise RuntimeError('Read-only diagnosis forbids '+kind)
            return fail

        torch.nn.Module._call_impl = forbid('model_forward')
        torch.optim.Adam.step = forbid('optimizer')
        for name in ('mj_step','mj_step1','mj_step2','mj_forward','mj_resetData','mj_resetDataKeyframe'):
            setattr(mujoco, name, forbid('physics'))
        import learning_runtime as R
        ledger_path = C.HERE / 'run/ledger.json'
        ledger_pin = C.digest(ledger_path)
        state = C.read(ledger_path)
        if (state['status'] != 'failed' or state['active'] is not None or state['update_lease'] is not None
                or any(v != dict(attempted=0, completed=0) for v in state['updates'].values())):
            raise ValueError('Diagnosis requires the recorded failed, zero-update, idle boundary')

        class ReadOnlyEvidence:
            # No reservation, commit, update or run methods; failure status stays unchanged.
            def __init__(self):self.state = deepcopy(state)
            def healthy(self):
                if C.digest(ledger_path) != ledger_pin or self.state != state:
                    raise ValueError('Historical ledger changed during read-only diagnosis')

        original_append = R.Branch._append_audited
        def append(branch, ref, *args, **kwargs):
            return timed('archive:'+ref['id'], original_append, branch, ref, *args, **kwargs)
        R.Branch._append_audited = append
        original_load = R.torch.load
        R.torch.load = lambda *args, **kwargs: timed('torch_load', original_load, *args, **kwargs)
        original_zero = R.zero_updater
        R.zero_updater = lambda *args, **kwargs: timed('zero_origin', original_zero, *args, **kwargs)
        checkpoint = C.HERE / 'run/checkpoint_F_0000'
        manifest_pin = C.digest(checkpoint / 'manifest.json')
        branch = timed('complete_restore', R.restore, checkpoint, manifest_pin, 'F', ReadOnlyEvidence())
        if any(calls.values()) or branch.history or C.digest(ledger_path) != ledger_pin:
            raise ValueError('Read-only zero-state boundary changed')
        result = dict(complete_equal=True, elapsed_s=time.perf_counter()-started, calls=calls,
            checkpoint_manifest_sha256=manifest_pin, ledger_sha256=ledger_pin, ledger_status='failed',
            training_resumed=False, replay_rows=len(branch.replay), qualified_episodes=len(branch.refs))
        C.write(output / 'result.json', result)
        record('success', **result)
        print(json.dumps(result), flush=True)
    except BaseException as exc:
        record('error', error=repr(exc), calls=calls)
        raise
    finally:
        timer.cancel()


if __name__ == '__main__':
    main()
