"""Four one-shot, zero-update request execution trials. No restart or retry."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
from pathlib import Path
import subprocess
import sys
import time
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.learning.five_axis_preparation import (OUT as ORIGINAL, COMMON, cases,
    read, sha, canonical, verify_inputs, freeze_sources, audit_archive)
from tools.validation.run_yaw_pilot import (write, publish_archive, actual_common,
    model_archive_bytes, supervise, reconcile_receipt, NoLearning, PYTHON)
from tools.validation.run_five_axis_training import select
from tools.learning.exploration_execution import HeldRequests, command_metrics

OUT = ROOT / 'deliverables/learning_chain/five_axis_exploration_execution_20261026'
SEED = 2026102601
MAX_CYCLES = 13500


def schedule():
    return [dict(id=f'H{hold:02d}_{point["name"]}', hold_cycles=hold, case=point)
            for hold in (1, 10) for point in cases()[2:]]


def prepare():
    old = read(ORIGINAL / 'registration.json')
    verify_inputs(old['inputs'])
    closed = ROOT / 'deliverables/learning_chain/five_axis_training_execution_20261024'
    proof = read(closed / 'completion_verification.json')
    if not proof['verified'] or proof['cumulative_initializations'] != 387:
        raise ValueError('Previous cost boundary not closed')
    if sha(ORIGINAL / 'training/ledger.json') != proof['ledger_sha256']:
        raise ValueError('Previous training ledger changed')
    OUT.mkdir()  # Refuse to overwrite even a partial package.
    extra = [ROOT / 'tools/learning/exploration_execution.py', Path(__file__),
             ROOT / 'tests/test_exploration_execution.py']
    pins = dict(old['inputs'])
    pins.update(freeze_sources(extra, folder=OUT / 'source_snapshot'))
    requests = np.random.default_rng(SEED).uniform(-1., 1., (MAX_CYCLES, 5))
    np.save(OUT / 'requests.npy', requests, allow_pickle=False)
    reg = dict(version='five_axis_exploration_execution_v1', inputs=pins, common=old['common'],
        parent_registration_sha256=sha(ORIGINAL / 'registration.json'),
        previous_closeout_sha256=sha(closed / 'completion_verification.json'),
        requests_sha256=sha(OUT / 'requests.npy'), seed=SEED, schedule=schedule(),
        max_initializations=4, cumulative_before=387, max_control_cycles=MAX_CYCLES,
        max_physical_substeps=540000, max_worker_wall_s=1800, max_parallel_workers=2,
        training_updates=0, neural_policy_calls=0, replay_publications=0, final_test_episodes=0,
        controls='unchanged N2/450, reward, geometry, sensing and all guards; 25 s task + 2 s stop',
        engineering_gate=dict(xy_gain_ratio_min=1.5, xy_error_ratio_max=.8,
            no_new_guard=True, valid_stop_and_schedule=True, reference_gain_admissible=True),
        authorization='2026-10-26 user: first check exploration execution, then controlled entropy strength; no history; efficient bounded diagnostics',
        retry=0)
    write(OUT / 'registration.json', reg)
    (OUT / '实施记录.md').write_text(
        '# 探索执行验证实施记录\n\n2026-10-26，B.2第3项。\n\n'
        '1. 已完成：保持/阶段打断/权限间断/重置、影子命令口径与中断成本核对的6项离线检查；未消耗物理初始化。\n'
        '2. 待执行：最多4个零更新回合，2 ms与20 ms各正负1.5°，同一均匀请求文件。\n'
        '3. 待完成：字节档案审核、命令与实际运动对照、五份滚动材料。\n\n'
        '实施决定：复用现有隔离工作区；只新增诊断文件，不改241份原冻结输入。'
        '为控制墙钟每次并行两个独立环境；完成第一对并审核后才准许下一对，无效即不再启动。'
        '不重复旧物理资格，不发布回放，不调用网络或优化器。'
        '当前只执行V1；熵强度训练对照另阶段，不能从本轮命令指标推断学习收益。\n', encoding='utf-8')
    print(json.dumps(dict(prepared=True, jobs=4, old_pins=len(old['inputs']), updates=0)), flush=True)


def validate(reg):
    verify_inputs(reg['inputs'])
    if (reg['schedule'] != schedule() or reg['max_initializations'] != 4
            or reg['max_control_cycles'] != MAX_CYCLES
            or sha(OUT / 'requests.npy') != reg['requests_sha256']):
        raise ValueError('Frozen diagnostic schedule/stream changed')


def worker(job_id):
    reg = read(OUT / 'registration.json'); validate(reg)
    job = next(job for job in reg['schedule'] if job['id'] == job_id)
    folder = OUT / 'run' / job_id
    with (folder / 'worker.claim').open('x'): pass
    blocker = NoLearning(); sys.meta_path.insert(0, blocker)
    receipt = dict(case_id=job_id, status='initializing', reset_attempted=0,
        physical_substeps=0, control_cycles=0, valid=False, stopped=False,
        policy_calls=0, training_updates=0, request_draws=0,
        registration_sha256=sha(OUT / 'registration.json'), hold_cycles=job['hold_cycles'])
    env = session = None; raw = {}; started = time.monotonic()
    held = HeldRequests(np.load(OUT / 'requests.npy', allow_pickle=False), hold_cycles=job['hold_cycles'])
    try:
        runtime = select()
        from tools.learning.five_axis_session import session_class
        from tools.learning.five_axis_collection import collect_episode, CollectionError
        from tools.learning.newton_profile import build_model_xml
        from tools.validation.yaw_pilot import environment_class, YawContactCase
        env = environment_class()()
        model_bytes = model_archive_bytes(build_model_xml(env.profile))
        (folder / 'model_used.xml').write_bytes(model_bytes)
        receipt.update(actual_common(env, runtime, model_bytes))
        if any(canonical(receipt[key]) != canonical(reg['common'][key]) for key in COMMON):
            raise ValueError('Common dynamics/runtime differ')
        Base = session_class()
        class BoundedSession(Base):
            def advance_cycle(self, action):
                if time.monotonic() - started > reg['max_worker_wall_s']:
                    raise RuntimeError('Worker wall bound; no retry')
                result = super().advance_cycle(action)
                if self.cycle_id % 100 == 0:
                    write(folder / 'progress.json', dict(cycles=self.cycle_id,
                        simulation_s=self.cycle_id * .002, physical_substeps=env.physical_steps,
                        reset_attempted=1, request_draws=held.draws, training_updates=0,
                        phase=result.next_snapshot.controller_state['phase']))
                return result
        session = BoundedSession(env); point = YawContactCase(**job['case'])
        def policy(observation):
            before = session.prepare_cycle()
            return held.select(session.cycle_id, before.controller_state['phase'])
        receipt.update(case=asdict(point), reset_attempted=1)
        write(folder / 'receipt.json', receipt)
        try:
            raw = collect_episode(session, point, policy=policy, seed=SEED, max_cycles=MAX_CYCLES)
        except CollectionError as exc:
            raw = exc.archive
            raise
        raw['diagnostic'] = dict(hold_cycles=job['hold_cycles'], requests_sha256=reg['requests_sha256'],
            training_updates=0, neural_policy_calls=0, replay_publications=0)
        receipt.update(status='finished', valid=raw['outcome']['simulation_valid'],
            stopped=raw['outcome']['physical_stopped'], outcome=raw['outcome']['task_outcome'],
            final_reason=session.reason, finish_criteria=session.finish_criteria)
    except BaseException as exc:
        receipt.update(status='error', error=repr(exc))
        raise
    finally:
        if blocker in sys.meta_path: sys.meta_path.remove(blocker)
        if env is not None:
            receipt.update(physical_substeps=env.physical_steps, guard_facts=env.guard_facts,
                control_cycles=getattr(session, 'cycle_id', 0))
        receipt.update(elapsed_wall_s=time.monotonic() - started, request_draws=held.draws)
        publish_archive(folder, raw, receipt)
    # Existing independent raw audit, once per completed archive. It imports
    # tensor validation only; no network is instantiated, no optimizer exists.
    raw, receipt, proof = audit_archive(folder, reg)
    check = HeldRequests(np.load(OUT / 'requests.npy', allow_pickle=False), hold_cycles=job['hold_cycles'])
    for i, row in enumerate(raw['transitions']):
        expected = (check.select(i, row['action_log']['composition_inputs']['phase'])
                    if row['action_active'] else np.zeros(5))
        if not np.array_equal(row['action'], expected):
            raise ValueError('Published hold schedule differs')
    if check.draws != receipt['request_draws']:
        raise ValueError('Request draw count differs')
    proof.update(hold_schedule_verified=True, archive_sha256=receipt['archive_sha256'],
                 registration_sha256=sha(OUT / 'registration.json'))
    write(folder / 'audit.json', proof)
    metrics = command_metrics(raw['transitions'])
    trace = raw['trace']; velocity = np.array([r['velocity_world'] for r in trace[1:]])
    active = np.array([r['action_active'] for r in raw['transitions']], dtype=bool)
    lead = np.array([np.asarray(r['reference_qpos'][:3]) - r['position_m'] for r in trace[1:]])
    metrics['physical'] = dict(terminal_position_m=trace[-1]['position_m'],
        terminal_quaternion_wxyz=trace[-1]['quaternion_wxyz'],
        z_advance_m=trace[-1]['position_m'][2] - trace[0]['position_m'][2],
        active_mean_abs_velocity=abs(velocity[active]).mean(axis=0).tolist(),
        active_absolute_motion_integral=(abs(velocity[active]).sum(axis=0) * .002).tolist(),
        maximum_absolute_reference_lead_m=abs(lead).max(axis=0).tolist(),
        peak_force_N=max(p['force_N'] for p in raw['cycle_peaks']),
        peak_torque_G_Nm=max(p['torque_G_Nm'] for p in raw['cycle_peaks']),
        controller_events=raw['evidence']['controller_events'],
        guard_facts=raw['evidence']['guard_facts'])
    write(folder / 'metrics.json', metrics)
    print(json.dumps(dict(job=job_id, verified=True, reason=receipt['final_reason'],
                          G=metrics['all']['gain'], E=metrics['all']['tracking_error'])), flush=True)


def reconcile_batch(ledger, jobs, run_folder):
    """Rebuild costs from all launched folders even after a failed future/interrupt."""
    episodes = []; failures = []
    for job in jobs:
        folder = Path(run_folder) / job['id']
        if not folder.exists(): continue
        proof = (read(folder / 'supervisor.json') if (folder / 'supervisor.json').exists()
                 else dict(started=(folder / 'worker.claim').exists(),
                           process_exit_confirmed=False, returncode=None))
        receipt = reconcile_receipt(folder, proof)
        # A partial worker may only have progress; retain the registered bound.
        if receipt.get('count_precision') == 'lower_bound':
            receipt['physical_substeps_upper_bound'] = 10 * MAX_CYCLES
        audit = read(folder / 'audit.json') if (folder / 'audit.json').exists() else {}
        valid = (receipt.get('status') == 'finished' and receipt.get('valid') is True
            and receipt.get('stopped') is True and receipt.get('returncode') == 0
            and audit.get('verified') is True and audit.get('hold_schedule_verified') is True
            and audit.get('archive_sha256') == receipt.get('archive_sha256'))
        receipt['audit_passed'] = valid
        episodes.append(receipt)
        if not valid: failures.append(job['id'])
    ledger.update(episodes=episodes,
        initialization_attempts=sum(r.get('reset_attempted', 0) for r in episodes),
        physical_substeps=sum(r.get('physical_substeps', 0) for r in episodes))
    return failures


def run():
    reg = read(OUT / 'registration.json'); validate(reg)
    (OUT / 'run').mkdir()  # No restart/resume even after a partial launch.
    ledger = dict(status='RUNNING', episodes=[], initialization_attempts=0,
        physical_substeps=0, neural_policy_calls=0, training_updates=0, replay_publications=0,
        cumulative_before=387, registration_sha256=sha(OUT / 'registration.json'))
    write(OUT / 'ledger.json', ledger); started = time.monotonic()
    def launch(job):
        folder = OUT / 'run' / job['id']; folder.mkdir()
        proof = supervise([str(PYTHON), '-B', '-X', 'utf8', str(Path(__file__)), '--worker', job['id']],
                          folder, timeout=reg['max_worker_wall_s'] + 180)
        return job, reconcile_receipt(folder, proof)
    try:
        for start in (0, 2):
            validate(reg)
            with ThreadPoolExecutor(max_workers=2) as pool:
                list(pool.map(launch, reg['schedule'][start:start + 2]))
            failures = reconcile_batch(ledger, reg['schedule'], OUT / 'run')
            write(OUT / 'ledger.json', ledger)
            if failures: raise RuntimeError('Invalid/unverified episode; batch stops: ' + ', '.join(failures))
        ledger['status'] = 'COMPLETED'
    except BaseException as exc:
        ledger.update(status='STOPPED', error=repr(exc))
        raise
    finally:
        reconcile_batch(ledger, reg['schedule'], OUT / 'run')
        ledger.update(elapsed_wall_s=time.monotonic() - started,
            cumulative_initializations=387 + ledger['initialization_attempts'])
        write(OUT / 'ledger.json', ledger)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true'); group.add_argument('--run', action='store_true')
    group.add_argument('--launch', action='store_true'); group.add_argument('--worker')
    args = parser.parse_args()
    if args.prepare: prepare()
    elif args.worker: worker(args.worker)
    elif args.run: run()
    else:
        with (OUT / 'launcher.claim').open('x'): pass
        with (OUT / 'launcher.log').open('xb') as log:
            proc = subprocess.Popen([str(PYTHON), '-B', '-X', 'utf8', str(Path(__file__)), '--run'],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            write(OUT / 'process_started.json', dict(pid=proc.pid, supervisor_pid=__import__('os').getpid()))
            code = proc.wait()
        write(OUT / 'process_exit.json', dict(process_exit_confirmed=True, exit_code=code))
        return code
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
