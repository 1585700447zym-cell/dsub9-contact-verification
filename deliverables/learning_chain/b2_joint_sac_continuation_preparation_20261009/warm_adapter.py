"""Numerical adapter, imported only by an admitted owned worker."""
from copy import deepcopy
import hashlib, io
from pathlib import Path
import numpy as np
import torch
from joint_contract import OUT, read, sha, canonical
from joint_runtime import metered_load
from continuation_contract import migrate_warm_state

def state_digest(value):
    h = hashlib.sha256()
    def visit(x):
        def put(b): h.update(len(b).to_bytes(8, 'big')); h.update(b)
        put(type(x).__name__.encode())
        if isinstance(x, torch.Tensor):
            put(str(x.dtype).encode()); put(str(tuple(x.shape)).encode()); put(x.detach().cpu().contiguous().numpy().tobytes())
        elif isinstance(x, np.ndarray):
            put(str(x.dtype).encode()); put(str(x.shape).encode()); put(x.tobytes())
        elif isinstance(x, dict):
            put(str(len(x)).encode())
            for k in sorted(x, key=lambda k: (type(k).__name__, repr(k))): visit(k); visit(x[k])
        elif isinstance(x, (list, tuple)):
            put(str(len(x)).encode())
            for item in x: visit(item)
        elif isinstance(x, bytes): put(x)
        else: put(canonical(x).encode())
    visit(value); return h.hexdigest()

def equal(a, b, message):
    if state_digest(a) != state_digest(b): raise ValueError(message)

def boundary_state(boundary):
    return {k: dict(targets=torch.tensor(v[0].copy()), mask=torch.tensor(v[1].copy()), last_active=v[2]) for k, v in boundary.entries.items()}

def runtime_digest(chain):
    from joint_checkpoint import capture
    if (chain._audited_warm_rng.bit_generator.state != chain.warm_rng.bit_generator.state or
        chain._audited_warm_draws != chain.warm_draws or chain.active or chain.failed or chain.updater.failed or not chain.warm_gate()):
        raise ValueError('Incomplete operational warm/healthy boundary')
    return state_digest(dict(state=capture(chain), boundary=boundary_state(chain.boundary),
                             audited_warm_rng=chain._audited_warm_rng.bit_generator.state,
                             audited_warm_draws=chain._audited_warm_draws, active=chain.active, failed=chain.failed))

def load_warm(*, output, admission):
    spec = read(OUT / 'input_spec.json'); folder = Path(spec['restoration_folder'])
    if sha(folder / 'checkpoint/manifest.json') != spec['restoration_manifest_sha256']: raise ValueError('Restoration manifest drift')
    manifest = read(folder / 'checkpoint/manifest.json'); data = (folder / 'checkpoint/state.pt').read_bytes()
    if hashlib.sha256(data).hexdigest() != spec['restoration_state_sha256'] or manifest['state_sha256'] != spec['restoration_state_sha256']:
        raise ValueError('Restoration payload drift')
    envelope = metered_load(io.BytesIO(data), map_location='cpu', weights_only=True)
    if state_digest(envelope) != spec['restoration_state_digest'] or manifest['state_digest'] != spec['restoration_state_digest']:
        raise ValueError('Restoration complete typed state differs')
    binding = admission.verify('F50'); state = migrate_warm_state(envelope, binding, spec)
    equal(dict(state, binding=envelope['state']['binding']), envelope['state'], 'Migration changed source state besides admission')
    from joint_checkpoint import validate_state, install_state, capture
    components = validate_state(state, expected_binding=binding, admission=admission)
    equal(boundary_state(components[2]), envelope['boundary'], 'Inherited terminal boundary differs')
    chain = install_state(state, components=components, expected_binding=binding, output=output, admission=admission)
    equal(capture(chain), state, 'Installed complete chain state differs')
    runtime_digest(chain)
    if chain.available != 0 or chain.update_attempts != 0: raise ValueError('Warm archives cannot mint optimizer credit')
    return chain
