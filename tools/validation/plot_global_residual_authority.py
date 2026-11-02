"""Plot only the hash-verified saved engineering traces; no simulation or learner."""
import gzip
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'deliverables/learning_chain/global_residual_authority_20261028'


def main():
    summary = json.loads((OUT / 'analysis/summary.json').read_text(encoding='utf-8'))
    target = OUT / 'analysis/命令与实际运动时序.png'
    if target.exists():
        raise FileExistsError(target)
    plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False
    fig, axs = plt.subplots(4, 2, figsize=(13, 11), sharex='col')
    colors = {'G0': '#2666ad', 'G1': '#d45a28'}
    for column, case in enumerate(('YAW_P15', 'YAW_M15')):
        for profile in ('G0', 'G1'):
            job = profile + '_' + case
            if job not in summary['episodes']:
                continue
            archive = OUT / 'run' / job / 'episode.json.gz'
            if not archive.exists():
                continue
            data = archive.read_bytes()
            key = archive.relative_to(ROOT).as_posix()
            if hashlib.sha256(data).hexdigest() != summary['input_sha256'][key]:
                raise ValueError('Archive changed')
            raw = json.loads(gzip.decompress(data))
            tr, rows = raw.get('trace', []), raw.get('transitions', [])
            if not rows or len(tr) != len(rows)+1:
                continue
            stop = summary['episodes'][job]['control_stop_time_s']
            t = np.array([r['time_s'] for r in tr])
            mask = t[1:] <= (t[-1] if stop is None else stop) + 1e-8
            q = np.array([r['quaternion_wxyz'] for r in tr]); q /= np.linalg.norm(q, axis=1)[:, None]
            w,x,y,z = q.T
            yaw = np.degrees(np.unwrap(np.arctan2(2*(w*z+x*y), 1-2*(y*y+z*z))))
            pos = np.array([r['position_m'] for r in tr])
            command = np.array([r['limited_command_world'] for r in tr[1:]])
            request = np.array([r['action_log']['requested_residual'] for r in rows])
            color = colors[profile]
            for axis in axs[:, column]:
                axis.grid(alpha=.22)
            axs[0,column].plot(t[:-1][mask], request[mask,5]*1e3, color=color, lw=1, ls='--', label=profile+' yaw请求')
            axs[0,column].plot(t[1:][mask], command[mask,5]*1e3, color=color, lw=1.2, label=profile+' yaw最终命令')
            axs[1,column].plot(t[1:][mask], yaw[1:][mask], color=color, label=profile)
            axs[2,column].plot(t[1:][mask], pos[1:][mask,0]*1e3, color=color, label=profile+' X')
            axs[2,column].plot(t[1:][mask], pos[1:][mask,1]*1e3, color=color, ls='--', label=profile+' Y')
            peaks = np.array([p['force_N'] for p in raw['cycle_peaks']])
            axs[3,column].plot(t[1:][mask], peaks[mask], color=color, lw=1, label=profile)
        axs[0,column].set_title('初始 yaw '+('+1.5°' if column == 0 else '−1.5°'))
        for axis in axs[:,column]:
            axis.legend(fontsize=8, loc='best')
        axs[3,column].set_xlabel('任务仿真时间 / s')
    for row, label in enumerate(('yaw请求/最终命令 / mrad/s', '实际 yaw / °', '实际 X/Y位置 / mm', '原生子步峰值力 / N')):
        axs[row,0].set_ylabel(label)
    fig.suptitle('G0旧尺度与G1扩大残差：同工况时序（脚本工程验证）', fontsize=14)
    fig.text(.5,.012,'虚线请求与实线最终命令展示限幅；实际运动差异含接触与基线反馈，不等同残差单独造成的位移。',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.03,1,.96))
    fig.savefig(target, dpi=150)
    plt.close(fig)
    print(str(target))


if __name__ == '__main__':
    main()
