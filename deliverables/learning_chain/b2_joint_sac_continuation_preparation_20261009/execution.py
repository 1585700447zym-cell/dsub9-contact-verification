"""Fresh continuation admission and shared attempted-operation ledger; stdlib only."""
from contextlib import contextmanager
from pathlib import Path
import os, time
from joint_contract import OUT, ROOT, read, write, sha, digest, canonical, LIMITS
PHYSICAL_FIELDS = ('trace', 'actions', 'transitions', 'outcome', 'controller_events', 'events', 'stop_samples', 'peaks')
COST_KEYS = ('dynamic_episodes', 'environment_creations', 'resets', 'control_cycles', 'native_steps', 'observations',
             'formal_updates', 'policy_calls', 'learner_constructions', 'tensor_loads', 'checkpoint_saves', 'replay_publications', 'archive_rebuilds')

def verify_grant(candidate, grant, pin, binding_pin):
    if (digest(grant) != pin or grant.get('version') != 'b2_joint_continuation_grant_v1' or grant.get('status') != 'OPEN' or
        grant.get('explicit_user_authorized') is not True or not isinstance(grant.get('human_evidence'), str) or not grant['human_evidence'].strip()):
        raise PermissionError('A new explicitly authorized continuation grant is required')
    if (grant.get('candidate_sha256') != digest(candidate) or grant.get('binding_sha256') != binding_pin or
        grant.get('cumulative_before') != 245 or grant.get('limits') != LIMITS or
        candidate.get('status') != 'PREPARED_NOT_AUTHORIZED' or candidate.get('training_admitted') is not False or
        candidate.get('version') != 'b2_joint_continuation_candidate_v1'):
        raise ValueError('Wrong continuation scope, limits or candidate')

def verify_code(candidate):
    for name, pin in candidate['code_sha256'].items():
        if sha(OUT / name) != pin: raise ValueError('Candidate code changed: ' + name)

def verify_sources(binding):
    for path, pin in binding['files'].items():
        if sha(path) != pin: raise ValueError('Bound source changed: ' + path)
    for folder, expected in binding['inventories'].items():
        actual = sorted(p.relative_to(folder).as_posix() for p in Path(folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix != '.pyc')
        if actual != expected: raise ValueError('Bound runtime inventory changed: ' + folder)

def verify_execution_copies(folder):
    binding = read(OUT / 'source_binding.json')
    for name in ('configuration.json', 'model.xml'):
        if sha(Path(folder) / name) != binding['files'][str(OUT / name)]: raise ValueError('Execution copy changed: ' + name)

class Counter:
    @classmethod
    def create(cls, path, limits):
        path = Path(path)
        with path.open('x', encoding='utf8') as f:
            f.write(canonical(dict(status='OPEN', limits=limits, attempted={k: 0 for k in limits}, started=time.time(),
                                   deadline=time.monotonic() + LIMITS['whole_wall_s'], workers=[])))
        return cls(path)
    def __init__(self, path): self.path = Path(path)
    @contextmanager
    def locked(self):
        lock = self.path.with_suffix('.lock'); deadline = time.monotonic() + .5
        while True:
            try: fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY); break
            except FileExistsError:
                if time.monotonic() >= deadline: raise TimeoutError('Counter lock unavailable')
                time.sleep(.01)
        try: yield
        finally: os.close(fd); lock.unlink()
    def checked(self):
        data = read(self.path)
        if data['status'] != 'OPEN' or (self.path.parent / 'authorization_closure.json').exists() or (self.path.parent / 'STOP').exists():
            raise PermissionError('Closed continuation authorization')
        if time.monotonic() >= data['deadline']: raise PermissionError('Expired continuation authorization')
        return data
    def take(self, key, n=1):
        with self.locked():
            data = self.checked()
            if type(n) is not int or n < 1 or key not in data['limits'] or data['attempted'][key] + n > data['limits'][key]:
                raise RuntimeError('Invalid or exhausted cost: ' + key)
            data['attempted'][key] += n; write(self.path, data, deadline=data['deadline'])
    def claim(self, role, label):
        key = role + ':' + label
        if key not in ('parent:main', 'reader:warm', 'reader:final'): raise PermissionError('Unknown continuation worker')
        with self.locked():
            data = self.checked()
            if key in data['workers']: raise PermissionError('Worker already claimed')
            if key == 'reader:final' and 'reader:warm' not in data['workers']: raise PermissionError('Warm restore must precede final reader')
            data['workers'].append(key); write(self.path, data, deadline=data['deadline'])
    def close(self, *, owned_exit_confirmed=False):
        if owned_exit_confirmed is True: self.path.with_suffix('.lock').unlink(missing_ok=True)
        with self.locked():
            data = read(self.path); data['status'] = 'CLOSED'
            data['unused_closed'] = {k: v - data['attempted'][k] for k, v in data['limits'].items()}; write(self.path, data)

def restore_equal(parent, child):
    if not parent.get('state_digest') or parent.get('state_digest') != child.get('state_digest'): raise ValueError('Full restored chain state differs')
    if set(parent.get('physical', {})) != set(PHYSICAL_FIELDS) or set(child.get('physical', {})) != set(PHYSICAL_FIELDS): raise ValueError('Incomplete restore transcript')
    if parent['physical'] != child['physical']: raise ValueError('Independent physical replay differs')

class Admission:
    def __init__(self, folder):
        self.folder = Path(folder).resolve(); self.grant = read(self.folder / 'grant.json'); self.pin = read(self.folder / 'grant_pin.json')['sha256']
        self.candidate = read(OUT / 'candidate.json'); self.candidate_pin = sha(OUT / 'candidate.json'); self.binding_pin = sha(OUT / 'source_binding.json')
        verify_grant(self.candidate, self.grant, self.pin, self.binding_pin); verify_code(self.candidate)
        from continuation_contract import require_new_binding
        self.binding = dict(mode='F50', purpose='bounded_physical_pilot', qualification_sha256=self.pin, config_sha256=self.candidate['learning_config_sha256'])
        require_new_binding(self.binding, read(OUT / 'input_spec.json'))
    def verify(self, mode):
        if mode != 'F50': raise PermissionError('Only the registered F50 continuation is admitted')
        Counter(self.folder / 'counter.json').checked()
        if (sha(OUT / 'source_binding.json') != self.binding_pin or sha(OUT / 'candidate.json') != self.candidate_pin or
            digest(read(self.folder / 'grant.json')) != self.pin): raise ValueError('Continuation capability changed')
        if read(OUT / 'future_claims/consumed.json') != dict(grant_sha256=self.pin, output=str(self.folder)): raise PermissionError('One-shot execution identity differs')
        return dict(self.binding)
    def claim(self, role, label): self.verify('F50'); Counter(self.folder / 'counter.json').claim(role, label)
