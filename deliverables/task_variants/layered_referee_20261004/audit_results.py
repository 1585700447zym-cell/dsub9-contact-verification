"""Recompute search commands, frozen-state and progress gates from saved physics."""
from pathlib import Path
import json,gzip,math,os
import numpy as np
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed output')
    ledger=json.loads((OUT/'run/ledger.json').read_text(encoding='utf-8'))
    config=json.loads((OUT/'configuration.json').read_text(encoding='utf-8'));c=config['b2_config'];results={}
    for entry in ledger['episodes']:
        d=json.loads(gzip.decompress((OUT/'run'/f"{entry['id']}.json.gz").read_bytes()));rows=d['trace'];events=d['controller_events']
        at_cache={}
        def at(t):
            if t not in at_cache:at_cache[t]=min(rows,key=lambda r:abs(r['time_s']-t))
            return at_cache[t]
        starts=[e for e in events if e['reason']=='LOW_LOAD_SEARCH'];n=0;error=0.;offset_error=0.;velocity_error=0.;target_max=0.;refmax=0.;prediction_error=0.;limited_error=0.
        for prev,r in zip(rows,rows[1:]):
            comp=r['search_composition']
            if r['phase']!='RUNNING':assert comp is None
            if comp is None:continue
            t=comp['time_s'];assert abs(t-prev['time_s'])<1e-9
            start=max((e for e in starts if e['time_s']<=t+1e-9),key=lambda e:e['time_s']);origin=at(start['time_s'])
            b=c['spiral_pitch_m']/(2*math.pi);theta=comp['theta_rad'];radius=b*theta
            target=radius*np.array([math.cos(theta),math.sin(theta)]);rate=c['spiral_speed_m_s']/math.hypot(radius,b)
            next_theta=min(c['spiral_radius_m']/b,theta+rate*config['dynamic_config']['control_period'])
            tangent=(b*next_theta*np.array([math.cos(next_theta),math.sin(next_theta)])-target)/config['dynamic_config']['control_period']
            delta=np.array(prev['reference_qpos'][:2])-origin['position_m'][:2]
            xy=np.clip(tangent+c['search_tracking_gain_s']*(target-delta),-c['search_xy_component_speed_m_s'],c['search_xy_component_speed_m_s'])
            z=np.clip(c['axial_gain_m_s_N']*(c['search_force_N']+prev['contact_wrench_M'][2]),-c['unload_speed_m_s'],c['search_forward_speed_m_s'])
            error=max(error,float(np.max(np.abs(np.r_[xy,z]-r['raw_command_world'][:3]))))
            offset_error=max(offset_error,float(np.max(np.abs(np.array(prev['commanded_correction'][:2])-r['commanded_correction'][:2]))))
            velocity_error=max(velocity_error,float(np.max(np.abs(np.array(prev['admittance_velocity'][:2])-r['admittance_velocity'][:2]))))
            assert np.max(np.abs(target-comp['target_xy_m']))<1e-12
            assert r['search_progress_origin_z_m']==start['progress_origin_z_m']
            assert prev['position_m'][2]-rows[0]['position_m'][2]-start['progress_origin_z_m']<c['search_exit_advance_m']
            target_max=max(target_max,float(np.linalg.norm(target)));n+=1
            previous=np.array(prev['limited_command_world'][:2]);dt=config['dynamic_config']['control_period']
            limits=config['drive_limits'];predicted_limited=np.clip(np.clip(xy,-limits['linear_speed_m_s'],limits['linear_speed_m_s']),previous-limits['linear_acceleration_m_s2']*dt,previous+limits['linear_acceleration_m_s2']*dt)
            limited_error=max(limited_error,float(np.max(np.abs(predicted_limited-r['limited_command_world'][:2]))))
            assert np.max(np.abs(predicted_limited-comp['predicted_limited_xy_m_s']))<1e-12
            predicted=delta+predicted_limited*dt
            assert np.max(np.abs(predicted-comp['predicted_reference_xy_m']))<1e-12
            real=np.array(r['reference_qpos'][:2])-origin['position_m'][:2]
            prediction_error=max(prediction_error,float(np.max(np.abs(real-predicted))))
            refmax=max(refmax,float(np.linalg.norm(real)))
        assert limited_error<1e-12 and refmax<=c['spiral_radius_m']+1e-12
        assert error<1e-12 and offset_error==0. and velocity_error==0. and target_max<=c['spiral_radius_m']+1e-12
        phases=[]
        for i,start in enumerate(starts):
            t0=start['time_s'];p0=np.array(at(t0)['position_m'])
            end=next((e for e in events if e['time_s']>t0 and e['phase']!='SEARCH'),None)
            end_time=end['time_s'] if end else entry['stop_time']
            sample=[r for r in rows if t0<r['time_s']<=end_time+1e-9 and r['search_composition'] is not None]
            prefix=[r for r in rows if r['time_s']<=t0+1e-9 and r['phase']=='RUNNING']
            peak=max(r['position_m'][2]-rows[0]['position_m'][2] for r in prefix)
            assert abs(peak-start['progress_origin_z_m'])<1e-12
            actual=max([float(np.linalg.norm(np.array(r['position_m'][:2])-p0[:2])) for r in sample] or [0.])
            phases.append(dict(search_number=i+1,start_s=t0,end_s=end_time,end_reason=end['reason'] if end else entry['reason'],
                origin_xy_um=(p0[:2]*1e6).tolist(),start_z_mm=p0[2]*1000,end_z_mm=at(end_time)['position_m'][2]*1000,
                progress_origin_z_mm=(start['progress_origin_z_m']+rows[0]['position_m'][2])*1000,
                max_target_radius_um=max([np.linalg.norm(r['search_composition']['target_xy_m'])*1e6 for r in sample] or [0.]),
                max_actual_xy_excursion_um=actual*1e6,
                max_total_force_mN=max([float(np.linalg.norm(r['contact_wrench_M'][:3])*1000) for r in sample] or [0.])))
        advances=[]
        for e in events:
            if e['reason']!='SEARCH_ADVANCED':continue
            z=at(e['time_s'])['position_m'][2]-rows[0]['position_m'][2]
            net=z-e['progress_origin_z_m'];assert abs(net-e['net_advance_m'])<1e-12 and net>=c['search_exit_advance_m']
            advances.append(dict(time_s=e['time_s'],net_advance_um=net*1e6))
        results[entry['id']]=dict(max_actual_reference_radius_um=refmax*1e6,max_reference_prediction_error_um=prediction_error*1e6,max_limited_command_error_m_s=limited_error,reconstructed_commands=n,max_command_error_m_s=error,xy_offset_freeze_error_m=offset_error,
            xy_velocity_freeze_error_m_s=velocity_error,max_target_radius_um=target_max*1e6,stop_tail_composition_is_null=True,
            frozen_progress_origins_match_archived_peaks=True,searches=phases,advances=advances,environment_events=d['events'],
            final_advance_mm=(rows[-1]['position_m'][2]-rows[0]['position_m'][2])*1000,
            scope='Independent saved-cycle algebra and geometry; no new physics')
    (OUT/'diagnosis.json').write_text(json.dumps(results,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(results,ensure_ascii=False))
    os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'tmp/matplotlib_layered_referee'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    d=json.loads(gzip.decompress((OUT/'run/y_neg_150.json.gz').read_bytes()));rows=d['trace'];diag=results['y_neg_150']
    fig,ax=plt.subplots(2,1,figsize=(9,7.5));ax[1].plot([r['time_s'] for r in rows],[r['position_m'][2]*1000 for r in rows],label='Actual Z')
    for phase in diag['searches']:
        samples=[r for r in rows if phase['start_s']<r['time_s']<=phase['end_s']+1e-9 and r['search_composition'] is not None];i=phase['search_number'];t=[r['time_s'] for r in samples]
        ax[0].plot(t,[np.linalg.norm(r['search_composition']['target_xy_m'])*1e6 for r in samples],ls='--',label=f'Search {i} target radius')
        ax[0].plot(t,[np.linalg.norm(np.array(r['position_m'][:2])*1e6-phase['origin_xy_um']) for r in samples],label=f'Search {i} actual excursion')
        ax[1].hlines(phase['progress_origin_z_mm']+.1,phase['start_s'],phase['end_s'],linestyles='--',colors=f'C{i}',label=f'Search {i} net-progress exit depth')
    ax[0].set(ylabel='Distance from search origin (um)',xlabel='Simulation time (s)',title='XY active search: requested and actual excursion')
    ax[1].set(ylabel='Z position (mm)',xlabel='Simulation time (s)',title='Progress must exceed the previous sensed peak by 100 um')
    for a in ax:a.grid(alpha=.2);a.legend(fontsize=8)
    fig.tight_layout(pad=1.5);fig.savefig(OUT/'search_diagnosis.png',dpi=150);fig.savefig(OUT/'search_diagnosis.pdf');plt.close(fig)


if __name__=='__main__':main()
