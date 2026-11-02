"""VS Code entry for inspection, recorded replay and unmodified live controllers."""
import argparse
from contextlib import contextmanager
import copy
from datetime import datetime
import gzip
import hashlib
import json
from pathlib import Path
from queue import SimpleQueue
import sys
import time
import uuid

import mujoco
import mujoco.viewer
import numpy as np

from tools.control.fixed_admittance import FixedAdmittance
from tools.control.search_recovery import SearchRecovery
from tools.control.search_exit_v2 import SearchRecoveryV2
from tools.dynamics.cartesian import CartesianEnvironment
from tools.reporting.report_b1 import read_verified
from tools.reporting.report_b2 import verified, CASE_LABELS, REASONS
from tools.validation.diagnose_v1_applicability import fingerprint
from tools.validation.run_b1_baseline import cases, run_episode, dump
from tools.validation.run_b2_search import run_search_episode, save_run, hashes
from tools.validation.run_b2_exit_gate import source_hashes
from tools.validation.run_contact_cases import ROOT
from tools.visualization.render_scenes import style_model_for_display

OUTPUT = ROOT/'deliverables/interactive_sessions'


class UserCancelled(Exception):
    pass


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def new_output(base, policy, case):
    base.mkdir(parents=True, exist_ok=True)
    folder = base/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+policy+'_'+case+'_'+uuid.uuid4().hex[:6])
    folder.mkdir(exist_ok=False)
    return folder


def load_record(path):
    path = Path(path)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as f:
        run = json.load(f)
    rows = run.get('trace')
    if not rows:
        raise ValueError('记录没有轨迹，无法回放。')
    try:
        values = np.array([[s['time_s']]+s['position_m']+s['quaternion_wxyz'] for s in rows])
        valid = values.shape == (len(rows), 8) and np.isfinite(values).all()
        valid = valid and np.all(np.diff(values[:,0]) > 0) and np.all(np.linalg.norm(values[:,4:8], axis=1) > 1e-12)
    except (KeyError, ValueError, TypeError):
        valid = False
    if not valid:
        raise ValueError('轨迹位姿或时间记录无效，无法回放。')
    return run


class DisplayModel:
    """Viewer edits can affect this copy only, never the live model or state."""
    def __init__(self, model):
        self.model = copy.copy(model)
        self.data = mujoco.MjData(self.model)
        self.groups = self.model.geom_group.copy()
        self.visual_rgba = self.model.geom_rgba.copy()
        style_model_for_display(self.model, 'collision')
        self.collision_rgba = self.model.geom_rgba.copy()
        self.model.vis.headlight.ambient[:] = (.5, .5, .5)
        self.model.vis.headlight.diffuse[:] = (.7, .7, .7)

    def update(self, row):
        self.data.qpos[:] = row['position_m']+row['quaternion_wxyz']
        self.data.time = row['time_s']
        self.data.qvel[:] = 0
        self.data.qfrc_applied[:] = 0
        self.data.xfrc_applied[:] = 0
        # Kinematics only: contact measurements always come from the saved/live row.
        mujoco.mj_kinematics(self.model, self.data)
        mujoco.mj_camlight(self.model, self.data)

    def set_view(self, view, camera, option):
        self.model.geom_group[:] = self.groups
        self.model.geom_rgba[:] = self.visual_rgba if view == 1 else self.collision_rgba
        option.geomgroup[:] = 0
        option.flags[mujoco.mjtVisFlag.mjVIS_STATIC] = 1
        option.geomgroup[0 if view != 1 else 2] = 1
        camera.lookat[:] = (0, 0, -.0005)
        camera.distance = .08 if view == 1 else .045
        camera.azimuth = 125
        camera.elevation = -22
        if view == 3:
            self.model.geom_group[:] = 3
            for i in range(self.model.ngeom):
                name = mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, i) or ''
                if name == 'pin_05' or (name.startswith('hole_convex256_05_') and
                        np.cos(int(name.split('_')[-1])*2*np.pi/256-np.radians(125)) > .2):
                    self.model.geom_group[i] = 0
            camera.lookat[:] = (.00554, .00142, .001)
            camera.distance = .015
            camera.elevation = -12


class PlaybackControls:
    def __init__(self):
        self.paused = True
        self.pending_steps = 0
        self.quit = False
        self.restart = False
        self.view = 1
        self.view_changed = True
        self.keys = SimpleQueue()

    def on_key(self, key):
        self.keys.put(key)

    def consume_keys(self):
        while not self.keys.empty():
            key = self.keys.get()
            if key == ord('P'):
                self.paused = not self.paused
                self.pending_steps = 0
            elif key == ord('N'):
                self.paused = True
                self.pending_steps += 1
            elif key == ord('Q'):
                self.quit = True
            elif key == ord('R'):
                self.restart = True
            elif key in (ord('1'), ord('2'), ord('3')):
                self.view = key-ord('0')
                self.view_changed = True

    def allow_step(self):
        if self.quit:
            return False
        if not self.paused:
            return True
        if self.pending_steps:
            self.pending_steps -= 1
            return True
        return False


@contextmanager
def observe_steps(env, before, after):
    original = env.step
    def step(command):
        before()
        row = original(command)
        after(row)
        return row
    env.step = step
    try:
        yield
    finally:
        env.step = original


class VisualWindow:
    def __init__(self, model, row, mode, *, auto_start=False, smoke_seconds=None):
        self.display = DisplayModel(model)
        self.controls = PlaybackControls()
        self.controls.paused = not auto_start
        self.row = row
        self.initial_z = row['position_m'][2]
        self.mode = mode
        self.phase = row.get('policy_phase', row.get('phase', ''))
        self.finished = ''
        self.last_draw = 0
        self.started = time.perf_counter()
        self.smoke_seconds = smoke_seconds
        self.display.update(row)
        self.viewer = mujoco.viewer.launch_passive(self.display.model, self.display.data,
            key_callback=self.controls.on_key, show_left_ui=False, show_right_ui=False)
        self.draw(force=True)

    def draw(self, force=False):
        if not self.viewer.is_running():
            return
        now = time.perf_counter()
        if not force and now-self.last_draw < .05:
            return
        with self.viewer.lock():
            if self.controls.view_changed:
                self.display.set_view(self.controls.view, self.viewer.cam, self.viewer.opt)
                self.controls.view_changed = False
            self.display.update(self.row)
        force_mn = np.linalg.norm(self.row.get('contact_wrench_M', [0]*6)[:3])*1000
        state = self.finished or ('PAUSED - press P' if self.controls.paused else 'RUNNING')
        text = (f'D-sub9 | {self.mode} | {state}\n'
                f"Sim t: {self.row['time_s']:.3f} s | advance: {(self.row['position_m'][2]-self.initial_z)*1000:.3f} mm\n"
                f"Recorded F: {force_mn:.3f} mN | penetration: {self.row.get('penetration_m',0)*1e6:.3f} um\n"
                f'Phase: {self.phase}\n'
                'P: run/pause | N: one sample | Q: close\n'
                '1: CAD | 2: collision | 3: pin05 cutaway\n'
                'R: replay restart only | mouse: camera\n'
                'Viewer sliders do not control the experiment')
        self.viewer.set_texts((None, mujoco.mjtGridPos.mjGRID_TOPLEFT, text, ''))
        self.viewer.sync()
        self.last_draw = now

    def pump(self):
        self.controls.consume_keys()
        if self.smoke_seconds is not None and time.perf_counter()-self.started >= self.smoke_seconds:
            self.controls.quit = True
        if self.controls.quit or not self.viewer.is_running():
            raise UserCancelled()
        self.draw()

    def before_step(self):
        while True:
            self.pump()
            if self.controls.allow_step():
                return
            time.sleep(.02)

    def update(self, row, phase=''):
        self.row = row
        self.phase = phase or row.get('policy_phase', row.get('phase', ''))
        self.draw()

    def hold(self, status):
        self.finished = status
        self.draw(force=True)
        try:
            while True:
                self.pump()
                time.sleep(.02)
        except UserCancelled:
            pass

    def close(self):
        self.viewer.close()


def reference_record(policy, case_name):
    if policy == 'b1':
        _, runs = read_verified()
        return next(r for r in runs if r['case']['name'] == case_name and r['controller']['name'] == 'B1_fixed_admittance')
    if policy == 'b2':
        _, _, runs = verified('matrix_v1_7cases')
        return next(r for r in runs if r['case']['name'] == case_name and r['controller']['name'] == 'B2_bounded_search_recovery')
    tags = {'x_offset_pos_100um':'verified_frozen_x100', 'y_offset_neg_100um':'verified_frozen_y100'}
    if case_name not in tags:
        raise ValueError('新版退出判据目前只有 X +100 / Y -100 两例回放，请选这两例。')
    folder = ROOT/'deliverables/b2_exit_gate_v2'/tags[case_name]
    index = json.loads((folder/'results_index.json').read_text(encoding='utf-8'))
    entry = index['runs'][0]
    if index['status'] != 'COMPLETE' or sha(folder/entry['file']) != entry['sha256']:
        raise ValueError('回放原始记录校验失败。')
    return load_record(folder/entry['file'])


def replay_record(window, run):
    rows = run['trace']
    index = 0
    origin_wall = time.perf_counter()
    origin_sim = rows[0]['time_s']
    while True:
        try:
            window.pump()
        except UserCancelled:
            return
        c = window.controls
        if c.restart:
            index = 0; c.restart = False; window.finished = ''
            origin_wall = time.perf_counter(); origin_sim = rows[0]['time_s']
        if c.paused:
            origin_wall = time.perf_counter(); origin_sim = rows[index]['time_s']
            if c.allow_step():
                index = min(index+1, len(rows)-1)
        else:
            target = origin_sim + time.perf_counter()-origin_wall
            while index+1 < len(rows) and rows[index+1]['time_s'] <= target:
                index += 1
        window.update(rows[index])
        if index == len(rows)-1:
            window.finished = 'REPLAY END: '+run.get('termination', 'UNKNOWN')
            c.paused = True
        time.sleep(.01)


def session_report(folder, run, reference):
    from tools.visualization.font_support import find_chinese_font
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt, font_manager
    font_manager.fontManager.addfont(str(find_chinese_font()))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(find_chinese_font())).get_name(), 'axes.unicode_minus':False})
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), layout='constrained')
    for r, label, color in ((reference, '保存的基线', '#8b939c'), (run, '本次可视化重跑', '#087f8c')):
        if r is None:
            continue
        t = [s['time_s'] for s in r['trace']]
        axes[0].plot(t, [(s['position_m'][2]-r['case']['start_origin_z_m'])*1000 for s in r['trace']], label=label, color=color)
        axes[1].plot(t, [np.linalg.norm(s['contact_wrench_M'][:3])*1000 for s in r['trace']], label=label, color=color)
    axes[0].set(ylabel='推进 / mm', title=CASE_LABELS[run['case']['name']]+'｜'+REASONS.get(run['termination'],run['termination']))
    axes[1].set(xlabel='仿真时间 / s', ylabel='合力 / mN')
    for ax in axes:
        ax.grid(alpha=.2); ax.legend()
    fig.savefig(folder/'本次结果.png', dpi=150); plt.close(fig)
    same = reference is not None and run['trace'] == reference['trace']
    summary = {'termination':run['termination'], 'advance_mm':(run['final']['position_m'][2]-run['case']['start_origin_z_m'])*1000,
               'peak_force_N':run['peaks']['force_N'], 'reference_available':reference is not None,
               'all_trace_samples_equal_to_reference':same}
    dump(folder/'数值核对.json', summary)
    message = '全部轨迹采样与保存基线一致。' if same else '没有逐样本一致的基线核对结论；请查看数值记录。'
    (folder/'本次仿真结果.md').write_text(
        f"# 本次可视化仿真\n\n工况：{CASE_LABELS[run['case']['name']]}。\n\n结束原因：{REASONS.get(run['termination'],run['termination'])}。"
        f"推进：{summary['advance_mm']:.6f} mm。\n\n{message}\n\n"
        '[查看曲线](本次结果.png) · [数值核对](数值核对.json) · [运行索引](session.json)\n\n'
        '这是重新计算的数值动力学记录，不是实物实验；完成状态按原控制器标准判断。\n', encoding='utf-8', newline='\n')


def run_live(args, env, case, window):
    folder = new_output(OUTPUT, args.policy, case.name)
    code = source_hashes()
    code['tools/usage/visual_sim.py'] = sha(Path(__file__))
    historical = fingerprint()
    manifest = {'status':'RUNNING', 'mode':'live', 'policy':args.policy, 'case':case.name,
                'source_sha256':code, 'historical_source_sha256':historical,
                'display_isolated_from_physics':True, 'result':None}
    dump(folder/'session.json', manifest)
    for relative in code:
        p = folder/'source_snapshot'/relative
        p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes((ROOT/relative).read_bytes())
    print('本次结果自动保存到：'+str(folder), flush=True)
    controller = {'b1':FixedAdmittance, 'b2':SearchRecovery, 'b2_v2':SearchRecoveryV2}[args.policy]()
    partial = [env.observe()]
    def after(row):
        partial.append(row)
        window.update(row, getattr(controller, 'phase', row['phase']))
    try:
        with observe_steps(env, window.before_step, after):
            if args.policy == 'b1':
                run = run_episode(env, case, controller)
            else:
                run = run_search_episode(env, case, controller)
        if historical != fingerprint() or any(sha(ROOT/p) != h for p,h in code.items()):
            raise RuntimeError('运行期间输入文件发生改变，本次不能作为有效复现。')
        run.update(source_sha256=code, historical_source_sha256=historical, execution_mode='live_isolated_viewer')
        save_run(folder/'run.json.gz', run)
        manifest.update(status='COMPLETE', result='run.json.gz', result_sha256=sha(folder/'run.json.gz'), termination=run['termination'])
        dump(folder/'session.json', manifest)
    except (UserCancelled, KeyboardInterrupt):
        manifest.update(status='INTERRUPTED_BY_USER', result='partial_trace.json.gz')
        save_run(folder/'partial_trace.json.gz', {'trace':partial, 'termination':'INTERRUPTED_BY_USER', 'case':vars(case)})
        dump(folder/'session.json', manifest)
        print('已中断并保存部分轨迹；不算完整仿真实验。', flush=True)
        return
    except Exception as error:
        manifest.update(status='ERROR', error=str(error), result='partial_trace.json.gz')
        save_run(folder/'partial_trace.json.gz', {'trace':partial, 'termination':'ERROR', 'case':vars(case)})
        dump(folder/'session.json', manifest)
        raise
    # A completed numerical experiment stays complete if presentation fails.
    try:
        try:
            reference = reference_record(args.policy, case.name)
        except (ValueError, StopIteration):
            reference = None
        session_report(folder, run, reference)
        manifest['report_status'] = 'COMPLETE'
    except (Exception, KeyboardInterrupt) as error:
        manifest.update(report_status='ERROR', report_error=repr(error))
        print('完整仿真记录已保存，但报告生成未完成：'+repr(error), flush=True)
    dump(folder/'session.json', manifest)
    print('仿真完成：'+REASONS.get(run['termination'], run['termination'])+'；结果目录：'+str(folder), flush=True)
    if not args.close_when_done:
        try:
            window.hold('DONE: '+run['termination'])
        except (UserCancelled, KeyboardInterrupt):
            pass


def main():
    parser = argparse.ArgumentParser(description='VS Code + MuJoCo 可视化仿真入口')
    parser.add_argument('--mode', choices=['model','replay','live'], required=True)
    parser.add_argument('--case', choices=[c.name for c in cases()], default='combined_a_scale_0.75')
    parser.add_argument('--policy', choices=['b1','b2','b2_v2'], default='b1')
    parser.add_argument('--record', help='可选：回放自己保存的 run.json.gz 或 partial_trace.json.gz')
    parser.add_argument('--auto-start', action='store_true', help='验证用；默认等待按 P 开始')
    parser.add_argument('--close-when-done', action='store_true')
    parser.add_argument('--smoke-seconds', type=float, help='仅界面启动验证：到时关闭；实时运行将标记中断')
    args = parser.parse_args()
    print('正在准备 256 段模型；窗口默认暂停。点击 MuJoCo 窗口后按 P 开始，N 单步，Q 退出。', flush=True)
    env = CartesianEnvironment(segments=256)
    case = next(c for c in cases() if c.name == args.case)
    row = env.reset(case)
    run = None
    if args.mode == 'replay':
        run = load_record(Path(args.record)) if args.record else reference_record(args.policy, case.name)
        row = run['trace'][0]
    window = VisualWindow(env.model, row, args.mode.upper(), auto_start=args.auto_start, smoke_seconds=args.smoke_seconds)
    try:
        if args.mode == 'live':
            run_live(args, env, case, window)
        elif args.mode == 'replay':
            replay_record(window, run)
        else:
            window.hold('MODEL INSPECTION - no integration')
    finally:
        window.close()


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    main()
