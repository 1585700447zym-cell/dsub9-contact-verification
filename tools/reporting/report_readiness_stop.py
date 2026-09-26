"""Audit and visualize the preserved passive-stop failure; no integration."""
import json
import numpy as np
from matplotlib import pyplot as plt
from tools.reporting.report_training_readiness import font
from tools.validation.validate_training_readiness import ROOT,OUT,sha,verify_hashes
from tools.validation.measure_readiness_stop import stop_qualified
from tools.validation.run_b2_search import read_run
from tools.validation.run_b1_baseline import dump


def main():
    folder=OUT/'old_b2_y_stop_extension_v1';p=folder/'results_index.json'
    index=json.loads(p.read_text(encoding='utf-8'))
    assert index['status']=='COMPLETE'
    verify_hashes(folder,index['files'])
    verify_hashes(folder/'source_snapshot',index['source_sha256'])
    # The captured v1 runner is retained; review fixed its final verdict only.
    wrapper='tools/validation/measure_readiness_stop.py'
    verify_hashes(ROOT,{k:v for k,v in index['protected_inputs'].items() if k!=wrapper})
    old=read_run(folder/'reproduced_original.json.gz');extension=read_run(folder/'passive_extension.json.gz')
    stop=old['stop_time_s'];rows=[r for r in old['trace'] if r['time_s']>=stop-1e-9]+extension['trace'][1:]
    assert all(np.isfinite(r['position_m']+r['velocity_world']+r['contact_wrench_G']).all() for r in rows)
    verdict=stop_qualified(phase=rows[-1]['phase'],events=extension['events'],recorded_time_s=rows[-1]['time_s'],
                          deadline_s=stop+2.,confirmed=index['stable_confirmation'],
                          final_stable=index['final_remains_stable'],peaks=extension['peaks'])
    assert verdict==index['pass']
    t=np.array([r['time_s']-stop for r in rows]);vel=np.array([r['velocity_world'] for r in rows])
    pos=np.array([r['position_m'] for r in rows]);force=np.array([r['contact_wrench_M'][:3] for r in rows])
    stopped=[r for r in rows if r['phase']=='STOPPING'];refs=np.array([r['reference_qpos'] for r in stopped])
    since=None;longest=0.
    for r in rows:
        stable=np.linalg.norm(r['velocity_world'][:3])<=1e-5 and np.linalg.norm(r['velocity_world'][3:])<=.001
        since=r['time_s'] if stable and since is None else since if stable else None
        if since is not None:longest=max(longest,r['time_s']-since)
    audit={'status':'BLOCKED_STOP_SETTLING' if not verdict else 'STOP_CHECK_PASS',
           'input_index_sha256':sha(p),'original_runner_sha256':index['source_sha256'][wrapper],
           'review_fixed_runner_sha256':sha(ROOT/wrapper),'recomputed_pass':verdict,
           'recorded_end_after_stop_s':float(t[-1]),'all_samples_finite':True,
           'new_events_during_extension':extension['events'][len(old['events']):],
           'position_range_per_axis_um':(np.ptp(pos,axis=0)*1e6).tolist(),
           'max_reference_component_change':float(np.max(np.ptp(refs,axis=0))),
           'peak_sampled_linear_um_s':float(np.max(np.linalg.norm(vel[:,:3],axis=1))*1e6),
           'original_one_s_linear_um_s':index['original_1s_linear_um_s'],
           'two_s_linear_um_s':index['two_s_linear_um_s'],'two_s_angular_rad_s':index['two_s_angular_rad_s'],
           'stable_confirmation':index['stable_confirmation'],'additional_net_displacement_um':index['additional_displacement_um'],
           'longest_stable_sample_span_over_full_two_s':longest,
           'interpretation':'No continuous settling within the prescribed observation; root cause not diagnosed. Tiny net displacement does not imply low instantaneous velocity. No training admission.'}
    dump(OUT/'停止复验审查.json',audit)
    font();fig,axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    axes[0,0].plot(t,np.linalg.norm(vel[:,:3],axis=1)*1e6,lw=.8);axes[0,0].axhline(10,c='#bd6046',ls='--',label='静止判据 10 μm/s')
    axes[0,0].set(ylabel='线速度 / μm/s',title='停止命令后仍有速度波动');axes[0,0].legend()
    axes[0,1].plot(t,np.linalg.norm(vel[:,3:],axis=1),lw=.8);axes[0,1].axhline(.001,c='#bd6046',ls='--',label='静止判据 0.001 rad/s')
    axes[0,1].set(ylabel='角速度 / rad/s',title='线速度与角速度必须同时满足');axes[0,1].legend()
    axes[1,0].plot(t,(pos-pos[0])*1e6,label=['X','Y','Z'],lw=.8);axes[1,0].legend(ncol=3)
    axes[1,0].set(ylabel='相对停止时刻的位置 / μm',title='净位置变化小，不等于速度已稳定')
    axes[1,1].plot(t,np.linalg.norm(force,axis=1)*1e3,lw=.8);axes[1,1].set(ylabel='接触合力 / mN',title='2 ms 采样的接触载荷')
    for ax in axes.flat:ax.set(xlabel='距发出停止命令 / s');ax.axvline(1,c='#888888',ls=':');ax.grid(alpha=.2)
    fig.suptitle('训练准入阻塞：原 B2 Y 的停止延续复验',fontsize=15)
    fig.supxlabel('竖线左侧为原 1 s 观察窗；右侧只延续零命令保持。原轨迹精确复现，未修改控制器或物理参数。')
    fig.savefig(OUT/'月报_停止验收阻塞.png');plt.close(fig)
    text=f'''# 停止延续复验：训练准入暂缓

原 B2 Y 回合的完整原始轨迹、事件、峰值及物理步数已精确复现。随后保持原 STOPPING 零命令，延续至停止后 2 s。

- 停止后 1 s：线速度 {index['original_1s_linear_um_s']:.6f} μm/s。
- 停止后 2 s：线速度 {index['two_s_linear_um_s']:.6f} μm/s，角速度 {index['two_s_angular_rad_s']:.9f} rad/s。
- 原判据：线速度≤10 μm/s，角速度≤0.001 rad/s；全段满足这两个条件的最长连续采样跨度约 {longest:.3f} s，未达到 0.1 s。
- 后一个 1 s 内位置净变化仅 {index['additional_displacement_um']:.6f} μm。不能将上述速度波动直接称为大幅漂移或已确定的数值爆炸；也不能仅因净位移小就判为停稳。
- 本段无新增无效事件或接触超限，保持参考未发生实质变化（各分量最大变化 {audit['max_reference_component_change']:.3g}）。根因仍未确定。

**结论：原 B2 已完成本轮基线选择，但停止要求仍有未解决项，不进入 SAC 训练，也不绕过该问题缩小范围宣称准入。** 短回合的时间步验证通过，不能代替这段长接触历史的停止验证。

下一步建议是一个有界的“停止可靠性修复与复验”能力：先核查保持驱动/接触求解的作用，再做必要的时间步对照；依据证据决定是否需要共同环境修复。若更换模型、接触参数或控制策略，先汇报方向和影响，再在同一新环境重新评价受影响的基线。当前未开展这些修改，也不继续任意延长观察窗口。

独立审查另指出验收脚本的最终数值错误判定漏洞，现已修复并增加测试。该漏洞未影响本次失败结果：原运行源码、记录与 pass=false 全部保留，修复后只读重判仍为 false，没有重写旧报告或伪造新积分。

![停止复验](月报_停止验收阻塞.png)

数据：[原始索引](old_b2_y_stop_extension_v1/results_index.json)、[只读复核](停止复验审查.json)。
'''
    (OUT/'停止复验与阻塞说明.md').write_text(text,encoding='utf-8',newline='\n')
    print(json.dumps(audit,ensure_ascii=False))


if __name__=='__main__':main()
