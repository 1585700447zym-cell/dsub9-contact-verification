"""Read one saved evaluation at a time; no simulation, policy or training runs."""
import argparse
from bisect import bisect_right
from collections import defaultdict
import csv
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from tools.validation.analyze_load_warning_retest import read_compact, frame_at, describe_recoveries
from tools.validation.analyze_g1_recovery import sha
from tools.validation.run_actor_lr_comparison import select_qualified_runtime


def analyze(batch,identity):
    select_qualified_runtime()
    import numpy as np
    from tools.model import layered_task as geometry
    out=Path(batch).resolve()/'review'
    out.mkdir(parents=True,exist_ok=True)
    folder=out.parent/'run'/identity
    receipt=read_compact(folder/'receipt.json')
    audit=json.loads((folder/'audit.json').read_bytes())
    group=identity.split('_',1)[1]
    if group not in ('ADMITTANCE','MLP','GRU'):
        raise ValueError('Expected ADMITTANCE, MLP or GRU directory suffix')
    if audit.get('verified') is not True or (group=='ADMITTANCE' and audit.get('zero_residual_verified') is not True):
        result=dict(episode_id=identity,comparison_group=group,audit_verified=False,
            reason=audit.get('error') or 'Incomplete physical or zero residual audit',
            zero_residual_verified=audit.get('zero_residual_verified'))
        (out/('trajectory_'+identity+'.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        return result
    raw_hash=sha(folder/'episode.json.gz')
    assert raw_hash==receipt['archive_sha256']==audit['archive_sha256']
    assert sha(folder/'model_used.xml')==receipt['model_xml_sha256']
    native=audit['load_warnings']
    ticks={x[k] for x in native['recoveries'] for k in ('start_tick','reached_tick','release_tick') if x.get(k) is not None}
    raw=read_compact(folder/'episode.json.gz',ticks)
    trace=raw['trace'];times=[r['time_s'] for r in trace]
    decision=receipt['stop_time_s']
    end=bisect_right(times,decision+1e-8)
    origins=np.asarray([r['position_m'] for r in trace])
    rotations=np.asarray([geometry._pose(r)[1] for r in trace])
    centers=np.einsum('nij,pj->npi',rotations,geometry._pin_centers)+origins[:,None,:]
    axes=rotations[:,:,2]
    radii=np.asarray(geometry._pin_sizes)[:,0]
    halves=np.asarray(geometry._pin_sizes)[:,1]
    rim=centers[:,:,2]+axes[:,2,None]*halves+np.sqrt(1-axes[:,2,None]**2)*radii
    tip=centers+axes[:,None,:]*halves[None,:,None]
    zlo=geometry._LAYERS[1][2]
    frames={}
    def snap(label,time):
        f=frame_at(trace,times,time,geometry)
        f['origin_advance_mm']=f['position_mm'][2]-origins[0,2]*1000
        frames[label]=f
        return f
    for label,key in (('initial',None),('decision','stop_time_s'),('task','task_end_time_s'),('audit','audit_end_time_s')):
        snap(label,times[0] if key is None else receipt[key])
    deepest=int(np.argmax(origins[:end,2]))
    snap('deepest_origin_before_decision',times[deepest])
    deepest_index,deepest_pin=np.unravel_index(int(np.argmax(tip[:end,:,2])),tip[:end,:,2].shape)
    snap('deepest_pin_tip_before_decision',times[deepest_index])
    first={}
    for i in range(9):
        first[i+1]={}
        for name,threshold in (('rim_past_entry',0.),('rim_into_main',zlo)):
            found=np.flatnonzero(rim[:end,i]>threshold+1e-12)
            first[i+1][name+'_s']=None if len(found)==0 else times[int(found[0])]
    all_main=np.flatnonzero(np.all(rim[:end]>zlo+1e-12,axis=1))
    if len(all_main):
        snap('first_all_main_axial_overlap',times[int(all_main[0])])
        first_fit=next((int(i) for i in all_main if geometry.layered_pin_fit(trace[int(i)])),None)
        frames['first_all_main_fit_saved']=None if first_fit is None else snap('first_all_main_fit_saved',times[first_fit])
    else:
        frames['first_all_main_axial_overlap']=None
        frames['first_all_main_fit_saved']=None
    events=raw['evidence']['controller_events']
    for i,event in enumerate(events):
        snap('controller_'+str(i)+'_'+event['reason'],event['time_s'])
    totals=defaultdict(float); segments=[]; active=None
    for i,(phase,enabled,dt) in enumerate(raw['executed']):
        if times[i]>=decision-1e-8:break
        totals[phase]+=dt
        if active is None or active['phase']!=phase:
            if active is not None:segments.append(active)
            active=dict(phase=phase,start_index=i,end_index=i+1,start_s=times[i],end_s=times[i+1],enabled_cycles=int(enabled))
        else:
            active.update(end_index=i+1,end_s=times[i+1],enabled_cycles=active['enabled_cycles']+int(enabled))
    if active is not None:segments.append(active)
    for row in segments:
        a,b=row.pop('start_index'),row.pop('end_index')
        row.update(duration_s=times[b]-times[a],origin_start_mm=origins[a].tolist(),origin_end_mm=origins[b].tolist(),
                   z_net_advance_um=(origins[b,2]-origins[a,2])*1e6,
                   xy_path_um=float(np.linalg.norm(np.diff(origins[a:b+1,:2],axis=0),axis=1).sum()*1e6),
                   xy_min_um=(origins[a:b+1,:2].min(axis=0)*1e6).tolist(),
                   xy_max_um=(origins[a:b+1,:2].max(axis=0)*1e6).tolist())
        row['origin_start_mm']=[x*1000 for x in row['origin_start_mm']]
        row['origin_end_mm']=[x*1000 for x in row['origin_end_mm']]
    milestones=[]
    for index in sorted(set(list(range(0,end,500))+[end-1])):
        f=snap('sample_'+f'{times[index]:.3f}',times[index])
        milestones.append({k:v for k,v in f.items() if k!='pins'})
    result=dict(episode_id=identity,comparison_group=group,zero_residual_verified=audit.get('zero_residual_verified'),case=raw['case'],physical_seed=raw['seed'],source_mode=raw['policy_mode'],
                archive_sha256=raw_hash,audit_verified=True,reason=receipt['final_reason'],outcome=receipt['outcome'],
                decision_time_s=decision,task_end_time_s=receipt['task_end_time_s'],audit_end_time_s=receipt['audit_end_time_s'],
                initial_pin_tip_depth_mm=(tip[0,:,2]*1000).tolist(),
                deepest_pin_before_decision=dict(pin=int(deepest_pin)+1,time_s=times[deepest_index],tip_depth_mm=float(tip[deepest_index,deepest_pin,2]*1000)),
                max_origin_advance_before_decision_mm=float((origins[:end,2].max()-origins[0,2])*1000),
                max_each_pin_tip_depth_before_decision_mm=(tip[:end,:,2].max(axis=0)*1000).tolist(),
                first_axial_crossings=first,frames=frames,controller_events=events,
                environment_events=raw['evidence']['environment_events'],phase_times_s=dict(totals),
                phase_segments=segments,recoveries=describe_recoveries(native['recoveries'],raw),native_load=native,
                guard_facts=raw['evidence']['guard_facts'],milestones=milestones,
                geometry_note='Crossings are saved 2 ms sample axial overlaps, not proof of cylinder fit; full margins evaluated at named frames.')
    target=out/('trajectory_'+identity+'.json')
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    f=result['frames']['decision']
    print(identity,result['outcome'],result['phase_times_s'],'decision gap mm',f['target_z_gap_mm'],'main fit',f['main_fit_count'])
    return result



GROUPS=('ADMITTANCE','MLP','GRU')
EXPECTED=tuple(p+'_'+g for p in ('E01','E02') for g in GROUPS)


def summarize_rows(trajectories):
    """Describe all registered slots; no checkpoint ranking or selection."""
    indexed={r['episode_id']:r for r in trajectories}
    if len(indexed)!=len(trajectories) or set(indexed)-set(EXPECTED):
        raise ValueError('Duplicate or unexpected comparison episode')
    rows=[]
    for identity in EXPECTED:
        if identity not in indexed:
            rows.append(dict(episode_id=identity,comparison_group=identity.split('_',1)[1],status='MISSING'))
            continue
        r=indexed[identity]
        if r['comparison_group']!=identity.split('_',1)[1]:
            raise ValueError('Comparison group differs from registered directory identity')
        if r.get('audit_verified') is not True:
            rows.append(dict(episode_id=identity,comparison_group=r['comparison_group'],status='INVALID',reason=r['reason']))
            continue
        if r['comparison_group']=='ADMITTANCE' and r.get('zero_residual_verified') is not True:
            raise ValueError('Pure admittance lacks the zero residual audit')
        f=r['frames']['task'];native=r['native_load'];load=native['exposure']['task']
        complete=r['audit_verified'] is True and native['verified'] is True
        success=r['outcome']=='FULL_SUCCESS'
        crosses=r['first_axial_crossings'].values()
        earliest=lambda key:min((x[key] for x in crosses if x[key] is not None),default=None)
        event_time=lambda reason:next((e['time_s'] for e in r['controller_events'] if e['reason']==reason),None)
        fitted=r['frames'].get('first_all_main_fit_saved')
        rows.append(dict(episode_id=identity,comparison_group=r['comparison_group'],pair_id=identity.split('_')[0],
            status=('SUCCESS' if success else 'FAILURE') if complete else 'INVALID',
            outcome=r['outcome'],reason=r['reason'],decision_time_s=r['decision_time_s'],task_end_time_s=r['task_end_time_s'],
            audit_end_time_s=r['audit_end_time_s'],time_score_s=min(r['task_end_time_s'],30.) if success else 30.,
            peak_force_N=load['warnings']['FORCE_GT5_N']['peak'],
            mean_force_N=load['mean_force_N'],rms_force_N=load['rms_force_N'],force_integral_Ns=load['integral_force_Ns'],
            warning_durations_s={k:v['over_duration_s'] for k,v in load['warnings'].items()},
            first_entry_rim_s=earliest('rim_past_entry_s'),first_main_rim_s=earliest('rim_into_main_s'),
            first_all_main_fit_s=None if fitted is None else fitted['time_s'],
            first_stall_s=event_time('AXIAL_STALL'),first_search_advanced_s=event_time('SEARCH_ADVANCED'),
            search_time_s=r['phase_times_s'].get('SEARCH',0.),recovery_count=len(r['recoveries']),
            actual_search_resumptions=native['actual_search_resumptions'],
            final_xy_um=[v*1000 for v in f['position_mm'][:2]],final_rpy_deg=f['rpy_deg'],
            final_target_gap_mm=f['target_z_gap_mm'],max_origin_advance_mm=r['max_origin_advance_before_decision_mm'],
            deepest_pin_before_decision=r['deepest_pin_before_decision'],final_main_fit_count=f['main_fit_count'],
            final_worst_pin=f['present_worst_pin'],final_worst_margin_um=f['present_worst_margin_um'],
            final_pins=f['pins'],archive_sha256=r['archive_sha256']))
    groups={}
    for group in GROUPS:
        members=[r for r in rows if r['comparison_group']==group]
        counts={s:sum(r['status']==s for r in members) for s in ('SUCCESS','FAILURE','INVALID','MISSING')}
        valid=counts['SUCCESS']+counts['FAILURE']
        groups[group]=dict(registered=2,valid=valid,counts=counts,success_rate_registered=counts['SUCCESS']/2,
            success_rate_valid=counts['SUCCESS']/valid if valid else None)
    return dict(version='load_warning_7pct_threeway_analysis_v1',rows=rows,groups=groups,
        complete=all(r['status']!='MISSING' for r in rows),selection_performed=False,
        limitations=['零更新闭环对照，不是本轮重新训练后的学习收益。',
            '仅两组开发工况；不据此宣布三种方法的泛化优劣。',
            '首次针孔几何发生时刻取2ms存档网格；轴向相交不等于完整配合通过。',
            '任务用时保留停稳保持阶段；动作预算限制决策停止≤30s，失败评分记30s。',
            '原点进给包括抵达孔口的空行程，不等于针尖入孔深度。',
            '纯导纳目录单独分组，底层policy_mode=mlp不改变其零残差对照身份。'])


def _fmt(v):
    return '—' if v is None else f'{v:.6f}'


def summary(batch):
    out=Path(batch).resolve()/'review'
    out.mkdir(parents=True,exist_ok=True)
    trajectories=[json.loads(p.read_bytes()) for p in sorted(out.glob('trajectory_E*.json'))]
    result=summarize_rows(trajectories)
    (out/'threeway_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    pins=[]
    for r in trajectories:
        for label,frame in r.get('frames',{}).items():
            if frame is not None:
                pins.extend(dict(episode_id=r['episode_id'],comparison_group=r['comparison_group'],
                    frame=label,time_s=frame['time_s'],**p) for p in frame['pins'])
    if pins:
        with (out/'per_pin.csv').open('w',encoding='utf-8-sig',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(pins[0]));writer.writeheader();writer.writerows(pins)
    lines=['# 三组零更新闭环对照复盘','',
        '以目录标签区分纯导纳、MLP、GRU；纯导纳要求额外零残差审核。仅汇总已保存证据，不训练或选择权重。','',
        '| 回合 | 状态/原因 | 任务用时 s | 峰力 N | 平均/RMS N | 力积分 Ns |',
        '|---|---|---|---|---|---|']
    for r in result['rows']:
        lines.append(f"| {r['episode_id']} | {r['status']}/{r.get('reason','未完成')} | "
            f"{_fmt(r.get('task_end_time_s'))} | {_fmt(r.get('peak_force_N'))} | "
            f"{_fmt(r.get('mean_force_N'))}/{_fmt(r.get('rms_force_N'))} | {_fmt(r.get('force_integral_Ns'))} |")
    lines+=['','| 回合 | 首次穿过入口/主孔平面 s | 首次九针配合 s | 首次搜索转插入 s | 搜索 s | 回撤/真实重搜 |',
        '|---|---|---|---|---|---|']
    for r in result['rows']:
        if r['status'] in ('MISSING','INVALID'):continue
        lines.append(f"| {r['episode_id']} | {_fmt(r['first_entry_rim_s'])}/{_fmt(r['first_main_rim_s'])} | "
            f"{_fmt(r['first_all_main_fit_s'])} | {_fmt(r['first_search_advanced_s'])} | "
            f"{_fmt(r['search_time_s'])} | {r['recovery_count']}/{r['actual_search_resumptions']} |")
    lines+=['','| 回合 | 末态XY µm | 末态yaw ° | 目标z差 mm | 最深针尖：针/深度mm/时间s | 主孔通过/最差余量µm |',
        '|---|---|---|---|---|---|']
    for r in result['rows']:
        if r['status'] in ('MISSING','INVALID'):continue
        d=r['deepest_pin_before_decision']
        lines.append(f"| {r['episode_id']} | "+'/'.join(_fmt(x) for x in r['final_xy_um'])+
            f" | {_fmt(r['final_rpy_deg'][2])} | {_fmt(r['final_target_gap_mm'])} | "
            f"{d['pin']}/{_fmt(d['tip_depth_mm'])}/{_fmt(d['time_s'])} | "
            f"{r['final_main_fit_count']}/9；{_fmt(r['final_worst_margin_um'])} |")
    lines+=['','各组预登记均为两条：']
    for g,v in result['groups'].items():
        lines.append(f"- {g}：成功 {v['counts']['SUCCESS']}/2，有效 {v['valid']}/2，"
            f"无效 {v['counts']['INVALID']}，缺失 {v['counts']['MISSING']}。")
    lines+=['','逐针绝对位置、局部偏差、针尖深度、entry/main余量和相交长度见 per_pin.csv 与 trajectory_<id>.json；'
        '汇总中的末态是任务终点，完整JSON另保留决策/审核终点。','']
    lines+=['- '+s for s in result['limitations']]
    (out/'三组闭环对照复盘.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(len(trajectories),'episodes;',len(pins),'pin rows; complete:',result['complete'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=Path,required=True)
    parser.add_argument('--episode')
    parser.add_argument('--summary',action='store_true')
    args=parser.parse_args()
    if args.episode:analyze(args.batch,args.episode)
    elif args.summary:summary(args.batch)
    else:parser.error('Choose an episode or summary')

