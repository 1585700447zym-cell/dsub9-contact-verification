"""Isolated repair regression only. Never grants training admission or publishes replay."""
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from probe import ROOT, HERE, write, native_diagnostics


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(dll, label):
    package = ROOT / 'tmp' / ('mujoco_3_13_' + label + '_runtime')
    if package.exists():
        raise FileExistsError(package)
    shutil.copytree(ROOT/'tmp/mujoco_3_13_probe/mujoco', package/'mujoco',
                    ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    shutil.copy2(dll, package/'mujoco/mujoco.dll')
    record = dict(label=label, package=str(package), training_admitted=False,
                  source_commit='123347c0eeab7e13c8da0828ab593bbd95bcf335',
                  files={p.relative_to(package).as_posix(): sha(p)
                         for p in sorted(package.rglob('*')) if p.is_file()})
    write(HERE/(label+'_runtime.json'), record)


def candidate_runtime(label):
    record = json.loads((HERE/(label+'_runtime.json')).read_text(encoding='utf-8'))
    package = Path(record['package'])
    for name, expected in record['files'].items():
        if sha(package/name) != expected:
            raise RuntimeError('Candidate package changed: '+name)
    if 'mujoco' not in sys.modules:
        sys.path.insert(0, str(package))
    module = importlib.import_module('mujoco')
    if Path(module.__file__).resolve() != (package/'mujoco/__init__.py').resolve():
        raise RuntimeError('Wrong candidate module')
    if module.__version__ != '3.13.0':
        raise RuntimeError('Wrong ABI version')
    return module, record


def worker(label, mode, out):
    out.mkdir(exist_ok=False)
    callback = native_diagnostics(out)
    mujoco, record = candidate_runtime(label)
    import numpy as np
    write(out/'started.json', dict(label=label, mode=mode, optimizer_calls=0,
          training_admitted=False, runtime_manifest_sha256=sha(HERE/(label+'_runtime.json'))))
    if mode == 'forward':
        m = mujoco.MjModel.from_binary_path('model.mjb', assets={'model.mjb': (HERE/'model.mjb').read_bytes()})
        d = mujoco.MjData(m)
        vector = np.load(HERE/'capture_02/pre_forward_state.npy')
        mujoco.mj_setState(m, d, vector, mujoco.mjtState.mjSTATE_INTEGRATION)
        mujoco.mj_forward(m, d)
        finite = all(np.isfinite(x).all() for x in (d.qpos, d.qvel, d.qacc, d.qfrc_constraint))
        write(out/'completed.json', dict(ncon=d.ncon, nefc=d.nefc, finite=bool(finite),
              warnings=[int(x.number) for x in d.warning], physical_steps=0, optimizer_calls=0))
        if not finite or any(x.number for x in d.warning):
            raise RuntimeError('Forward regression invalid')
        return
    if mode != 'episode':
        raise ValueError(mode)
    # Scoped dependency override for this diagnostic process only; the production
    # qualification gate and every frozen production file remain untouched.
    import tools.learning.runtime as runtime
    def diagnostic_only_verify(package_path):
        if Path(package_path).resolve() != (ROOT/'tmp/mujoco_3_13_probe').resolve():
            raise RuntimeError('Unexpected diagnostic dependency')
        _, verified = candidate_runtime(label)
        return dict(diagnostic_only=True, training_admitted=False, runtime=verified)
    runtime.verify_runtime = diagnostic_only_verify
    from tools.learning.bounded_contact import bounded_config, case_at, SEED
    from tools.learning.admitted_collection import _new_session, _physical_audit, _write_archive
    from tools.validation.run_contact_cases import ContactCase
    from dataclasses import asdict
    case = case_at('diagnostic_x_pos_100', .0001, 0.)
    rng = np.random.Generator(np.random.PCG64(np.random.SeedSequence([SEED, 1])))
    session = _new_session(bounded_config())
    start = time.monotonic()
    write(out/'dynamic_start.json', dict(seed=SEED, case=case, cycle_cap=13000,
          physical_starts=1, replay_published=0, optimizer_calls=0))
    session.reset(ContactCase(**case), seed=SEED)
    rows = []
    for cycle in range(13000):
        action = rng.uniform(-1., 1., 4).astype(np.float32)
        session.prepare_cycle()
        result = session.advance_cycle(action)
        rows.append(asdict(result))
        if (cycle+1) % 250 == 0 or result.done:
            write(out/'progress.json', dict(cycles=cycle+1, time=float(session.env.data.time),
                  qpos=session.env.data.qpos.tolist(), elapsed_s=time.monotonic()-start))
        if result.done:
            break
    e = session.env
    outcome = _physical_audit(session)
    raw = dict(case=case, seed=SEED, cycle_count=cycle+1, done=bool(session.done),
          outcome=outcome, guard_facts=e.guard_facts, events=e.events,
          stop_samples=e.stop_samples, stop_time=session.stop_time,
          audit_end_time_s=float(e.data.time), final_session=dict(
              task_finished=bool(session.task_finished), reason=session.reason, phase=e.phase),
          results=rows, optimizer_calls=0, replay_published=0, training_admitted=False)
    digest = _write_archive(out/'episode.json.gz', raw)
    write(out/'completed.json', {k:v for k,v in raw.items() if k not in ('results','stop_samples','events')}
          | dict(archive_sha256=digest, elapsed_s=time.monotonic()-start))
    if not session.done or not outcome['simulation_valid'] or not outcome['physical_stopped']:
        raise RuntimeError('Complete episode/physical audit failed')


if __name__ == '__main__':
    if sys.argv[1] == 'prepare':
        prepare(Path(sys.argv[2]), sys.argv[3])
    elif sys.argv[1] == '--worker':
        worker(sys.argv[2], sys.argv[3], Path(sys.argv[4]))
    else:
        label, mode, name = sys.argv[1:]
        with (HERE/(name+'.log')).open('x', encoding='utf-8') as log:
            p = subprocess.run([sys.executable, '-X', 'utf8', '-X', 'faulthandler', '-B',
                str(Path(__file__).resolve()), '--worker', label, mode, str(HERE/name)],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, timeout=900)
        write(HERE/(name+'_exit.json'), dict(returncode=p.returncode, hex=hex(p.returncode & 0xffffffff)))
        sys.exit(0 if p.returncode == 0 else 1)
