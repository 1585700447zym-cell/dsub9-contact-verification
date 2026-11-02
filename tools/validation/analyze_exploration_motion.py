"""Resolve endpoint-velocity versus actual displacement using existing V1 bytes."""
import gzip
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.validation.run_exploration_execution import OUT,read,write,sha


def main():
    results={}; pins={}
    for receipt in read(OUT/'ledger.json')['episodes']:
        name=receipt['case_id']; folder=OUT/'run'/name
        path=folder/'episode.json.gz';pins[name]=sha(path)
        raw=json.loads(gzip.decompress(path.read_bytes()))
        trace=raw['trace'];rows=raw['transitions']; groups={}
        i=0
        while i<len(rows):
            if not rows[i]['action_active']:i+=1;continue
            stage=rows[i]['action_log']['composition_inputs']['phase'];end=i
            while (end<len(rows) and end<i+10 and rows[end]['action_active']
                   and rows[end]['action_log']['composition_inputs']['phase']==stage):end+=1
            dt=(end-i)*.002
            displacement=np.asarray(trace[end]['position_m'])[:2]-np.asarray(trace[i]['position_m'])[:2]
            cmd=np.array([r['limited_command_world'][:2] for r in trace[i+1:end+1]])
            measured=displacement/dt;intended=cmd.mean(axis=0)
            contact=any(r['contact_count'] for r in trace[i:end+1])
            ref=np.array([r['reference_qpos'][:3] for r in trace[i:end+1]])
            command3=np.array([r['limited_command_world'][:3] for r in trace[i+1:end+1]])
            ref_delta=np.diff(ref,axis=0)-command3*.002
            nonintegral=np.linalg.norm(ref_delta,axis=1)>1e-9
            nonintegral_xy=np.linalg.norm(ref_delta[:,:2],axis=1)>1e-9
            for key in ['all',stage,'contact' if contact else 'free']:
                b=groups.setdefault(key,dict(seconds=0.,windows=0,cycles=0,
                    error=np.zeros(2),command=np.zeros(2),motion=np.zeros(2),nonintegral=0,nonintegral_xy=0))
                b['seconds']+=dt;b['windows']+=1;b['cycles']+=end-i
                b['error']+=abs(measured-intended)*dt
                b['command']+=abs(intended)*dt;b['motion']+=abs(measured)*dt
                b['nonintegral']+=int(nonintegral.sum())
                b['nonintegral_xy']+=int(nonintegral_xy.sum())
            i=end
        results[name]={key:dict(seconds=b['seconds'],windows=b['windows'],
            mean_absolute_window_velocity_error_um_s=(b['error']/b['seconds']*1e6).tolist(),
            mean_absolute_window_command_um_s=(b['command']/b['seconds']*1e6).tolist(),
            mean_absolute_window_actual_um_s=(b['motion']/b['seconds']*1e6).tolist(),
            reference_nonintegrating_cycle_fraction=b['nonintegral']/b['cycles'],
            reference_xy_nonintegrating_cycle_fraction=b['nonintegral_xy']/b['cycles'])
            for key,b in groups.items()}
    write(OUT/'actual_motion_window_diagnostics.json',dict(results=results,archive_sha256=pins,
        extra_initializations=0,extra_updates=0,neural_inference=0,
        interpretation='Measured position differences over 20 ms windows versus integrated command; not causal residual displacement'))
    lines=['# 实际运动跟随补充核查','',
        '2026-10-26。只读使用同一4份原始档案；新增初始化、物理子步、网络推理和更新均0。', '',
        '单个2 ms采样末端速度与命令差距可能包含接触振动，不能只据此认定持续位移跟随失败。'
        '因此用同样20 ms窗口的实际位置差，比较受限命令积分；阶段/权限边界拆段，接触/无接触分别报告。', '',
        '| 回合 | 范围 | 秒 | 命令速度绝对均值X/Y（μm/s） | 实际窗口速度绝对均值X/Y（μm/s） | 跟踪误差X/Y（μm/s） | XYZ/XY参考非积分周期比例 |',
        '|---|---|---:|---|---|---|---|']
    for name,groups in results.items():
        for key,b in groups.items():
            pair=lambda values:'/'.join(f'{x:.2f}' for x in values)
            lines.append(f'| {name} | {key} | {b["seconds"]:.3f} | '+
                pair(b['mean_absolute_window_command_um_s'])+' | '+
                pair(b['mean_absolute_window_actual_um_s'])+' | '+
                pair(b['mean_absolute_window_velocity_error_um_s'])+
                f' | {100*b["reference_nonintegrating_cycle_fraction"]:.2f}%/'+
                f'{100*b["reference_xy_nonintegrating_cycle_fraction"]:.2f}% |')
    lines+=['','参考非纯积分可能来自原有前导限制、阶段重置或一次性参考释放；该比例不是残差参考盘过滤率，'
        '不能仅据它断定具体重置原因，也不能把命令层G解释为实际残差位移。', '',
        '原完成记录与原始档案保留；本补充不新增试验、不放松限制。具体解释需结合本表的接触与无接触差异。','']
    (OUT/'实际运动跟随补充核查.md').write_text('\n'.join(lines),encoding='utf-8')
    for name,groups in results.items():
        print(name,json.dumps({k:groups[k] for k in ('free','contact')},ensure_ascii=False))


if __name__=='__main__':main()
