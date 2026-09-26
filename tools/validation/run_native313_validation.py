"""Isolated version regression; historical controller and validation code stay frozen."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'deliverables/native313_validation'


def require_static_gate(gate, version):
    if version != '3.13.0' or gate.get('mujoco_version') != version:
        raise ValueError('Only the isolated 3.13.0 environment is admitted')
    if not all(gate.get(k) is True for k in ('passed', 'strict_pairs_pass', 'new_failure_pass')):
        raise ValueError('Complete static evidence is required before dynamics')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def snapshot(mujoco):
    import numpy as np
    from tools.dynamics.contact_candidate import candidate_environment
    env = candidate_environment()
    options = {}
    for name in dir(env.model.opt):
        if name.startswith('_'):
            continue
        value = getattr(env.model.opt, name)
        if isinstance(value, np.ndarray):
            options[name] = value.tolist()
        elif isinstance(value, (int, float, bool, str)):
            options[name] = value
    arrays = {}
    for name in ('geom_size', 'geom_pos', 'geom_quat', 'mesh_vert', 'mesh_face',
                 'body_pos', 'body_quat', 'body_mass', 'body_inertia', 'body_ipos',
                 'geom_solref', 'geom_solimp', 'geom_friction', 'geom_margin', 'geom_gap',
                 'geom_contype', 'geom_conaffinity', 'dof_damping', 'dof_frictionloss'):
        a = np.ascontiguousarray(getattr(env.model, name))
        arrays[name] = dict(shape=list(a.shape), dtype=str(a.dtype), sha256=hashlib.sha256(a.tobytes()).hexdigest())
    dlls = {str(p): sha(p) for p in Path(mujoco.__file__).parent.glob('*.dll')}
    result = dict(mujoco_version=mujoco.__version__, module_file=mujoco.__file__, dll_sha256=dlls,
                  options=options, arrays=arrays, dynamic_config=asdict(env.config),
                  source_sha256={str(Path(__file__).relative_to(ROOT).as_posix()):sha(Path(__file__))})
    write(OUT / f'compatibility_{mujoco.__version__}.json', result)
    print('Snapshot', mujoco.__version__, len(options), 'effective option fields', flush=True)


def static(mujoco):
    import numpy as np
    from tools.validation import validate_contact_candidate as old
    from tools.dynamics.contact_candidate import candidate_environment
    from tools.validation.audit_contact_candidate import wall_pairs_pass
    from tools.validation.validate_training_readiness import verify_hashes
    comparison = json.loads((OUT/'compatibility_comparison.json').read_text(encoding='utf-8'))
    if not comparison['passed']:
        raise ValueError('Compatibility comparison has not passed')
    verify_hashes(ROOT, comparison['source_sha256'])
    old.OUT = OUT
    sys.argv = [sys.argv[0], '--tag', 'static_gate_v1']
    old.main()
    original = OUT/'static_gate_v1/results.json'
    data = json.loads(original.read_text(encoding='utf-8'))
    model = candidate_environment().model
    source = ROOT/'deliverables/contact_consistency_repair/新增失败冻结姿态.json'
    pose = json.loads(source.read_text(encoding='utf-8'))['pose']
    shifts_nm = sorted(set(range(-100,101,10)) | {-1,1})
    rows = []
    for nm in shifts_nm:
        q = list(pose); q[2] += nm*1e-9
        row = old.inspect(model, q); row['shift_nm'] = nm; rows.append(row)
    jumps = [dict(from_nm=a['shift_nm'], to_nm=b['shift_nm'],
                  delta_depth_m=abs(b['depth_m']-a['depth_m']),
                  passed=bool(abs(b['depth_m']-a['depth_m']) <= (b['shift_nm']-a['shift_nm']+1)*1e-9))
             for a,b in zip(rows,rows[1:])]
    q=list(pose);q[2]+=1e-6
    positive=old.inspect(model,q)
    positive['nine_corresponding_main_pairs']=wall_pairs_pass(positive)
    strict = wall_pairs_pass(next(r for r in data['special'] if r['name']=='wall_x'))
    new_pass = bool(all(r['passed'] for r in rows) and all(r['passed'] for r in jumps)
                    and positive['nine_corresponding_main_pairs'])
    sources = [source, original, OUT/'候选复验协议.md', Path(__file__), OUT/'compatibility_comparison.json']
    result = dict(mujoco_version=mujoco.__version__, module_file=mujoco.__file__,
                  passed=bool(data['passed'] and strict and new_pass),strict_pairs_pass=strict,
                  new_failure_pass=new_pass,rows=rows,jumps=jumps,positive=positive,
                  historical_checks=63+len(data['trajectory'])+len(data['coverage'])+len(data['special']),
                  new_checks=len(rows)+1,
                  source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sources})
    write(OUT/'static_extended.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','jumps','positive','source_sha256')},ensure_ascii=False),flush=True)


def dynamic(mujoco, timestep):
    from tools.validation import run_contact_candidate_stop as old
    from tools.validation.validate_training_readiness import verify_hashes
    gate_path=OUT/'static_extended.json'
    gate=json.loads(gate_path.read_text(encoding='utf-8'))
    require_static_gate(gate,mujoco.__version__)
    verify_hashes(ROOT,gate['source_sha256'])
    protected={gate_path.relative_to(ROOT).as_posix():sha(gate_path),
               Path(__file__).relative_to(ROOT).as_posix():sha(Path(__file__))}
    tag='stop_dt0p2_v1' if timestep==.0002 else 'stop_dt0p1_v1'
    write(OUT/(tag+'_runtime.json'),dict(mujoco_version=mujoco.__version__,module_file=mujoco.__file__,
                                       timestep=timestep,source_sha256=protected))
    old.OUT=OUT
    sys.argv=[sys.argv[0],'--tag',tag,'--timestep',str(timestep)]
    old.main()
    verify_hashes(ROOT,protected)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['snapshot','static','dynamic'])
    p.add_argument('--package-path',type=Path)
    p.add_argument('--timestep',type=float,choices=[.0002,.0001])
    args=p.parse_args()
    if args.package_path:
        sys.path.insert(0,str(args.package_path.resolve()))
    import mujoco
    if args.mode!='snapshot' and (mujoco.__version__!='3.13.0' or not args.package_path
                                 or not Path(mujoco.__file__).resolve().is_relative_to(args.package_path.resolve())):
        raise ValueError('Explicit isolated 3.13.0 package is required')
    if args.mode=='snapshot':snapshot(mujoco)
    elif args.mode=='static':static(mujoco)
    elif args.timestep is None:raise ValueError('--timestep is required')
    else:dynamic(mujoco,args.timestep)


if __name__=='__main__':main()
