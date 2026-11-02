"""Offline B1 geometry diagnosis. No new dynamic trials and no recovered forces."""
import hashlib
import json
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt, font_manager
from matplotlib.patches import Circle

from tools.dynamics.cartesian import CartesianEnvironment
from tools.reporting.report_b1 import read_verified
from tools.validation.run_contact_cases import ROOT, FORMAL_MODEL
from tools.validation.run_b1_baseline import dump
from tools.visualization.font_support import find_chinese_font

OUT=ROOT/'deliverables/b2_search_recovery/diagnosis'
SELECTED=('x_offset_pos_100um','combined_a_scale_0.75')
LABELS=('单独横向偏差 X +100 μm','联合偏差 A ×0.75')


def projected_tip_overhang(center_xy, rotation, pin_radius, aperture_radius, segments=256):
    """Exact support of the projected distal disk against polygon halfspaces.

    Positive means the disk cannot pass by pure world-Z translation at this
    orientation/XY. This is NOT current penetration, nor a complete shaft fit
    check, nor a prediction of a future controller trajectory.
    """
    theta=np.arange(segments)*2*math.pi/segments
    normals=np.column_stack((np.cos(theta),np.sin(theta)))
    support=pin_radius*np.linalg.norm(normals @ np.asarray(rotation)[:2,:2],axis=1)
    return float(np.max(normals @ np.asarray(center_xy)+support-aperture_radius))


def angle(row):
    q=np.asarray(row['quaternion_wxyz'])
    return float(np.degrees(2*np.arccos(np.clip(abs(q[0])/np.linalg.norm(q),0,1))))


def snapshot(env, row, holes, params):
    # Offline geometry only; dynamics, contact loads and controller state are
    # taken from the saved trace, never from this reconstructed mj_forward.
    mujoco.mj_resetData(env.model,env.data)
    env.data.qpos[:]=row['position_m']+row['quaternion_wxyz']
    mujoco.mj_forward(env.model,env.data)
    contacts=[]
    for c in env.data.contact:
        names=[mujoco.mj_id2name(env.model,mujoco.mjtObj.mjOBJ_GEOM,int(g)) for g in (c.geom1,c.geom2)]
        contacts.append({'geoms':names,'position_m':c.pos.tolist(),'normal':c.frame[:3].tolist(),
                         'penetration_m':max(0.,-float(c.dist))})
    if len(contacts)!=row['contact_count']:
        raise RuntimeError('Reconstructed geometry count differs from saved state')
    if abs(max((c['penetration_m'] for c in contacts),default=0.)-row['penetration_m'])>1e-10:
        raise RuntimeError('Reconstructed penetration differs from saved state')
    pins=[]
    for i,hole in holes.items():
        name=f'pin_{i}'
        gid=mujoco.mj_name2id(env.model,mujoco.mjtObj.mjOBJ_GEOM,name)
        if gid<0:raise ValueError(name)
        r=env.data.geom_xmat[gid].reshape(3,3)
        radius,half=env.model.geom_size[gid,:2]
        tip=env.data.geom_xpos[gid]+r[:,2]*half
        offset=tip[:2]-hole[:2]
        pins.append({'pin':name,'hole_xy_m':hole[:2].tolist(),'tip_center_m':tip.tolist(),
                     'tip_xy_offset_m':offset.tolist(),'rotation':r.tolist(),'radius_m':float(radius),
                     'main_aperture_overhang_m':projected_tip_overhang(offset,r,radius,params['bore_radius']),
                     'entry_aperture_overhang_m':projected_tip_overhang(offset,r,radius,params['entry_radius'])})
    return {'time_s':row['time_s'],'position_m':row['position_m'],'angle_deg':angle(row),
            'saved_force_M_N':row['contact_wrench_M'][:3],'saved_torque_M_Nm':row['contact_wrench_M'][3:],
            'saved_correction_velocity':row['admittance_velocity'],'saved_phase':row['phase'],
            'saved_penetration_m':row['penetration_m'],'contacts':contacts,'pins':pins,
            'overhanging_pins':sum(p['main_aperture_overhang_m']>1e-9 for p in pins)}


def make_figure(runs, diagnoses, params):
    font_manager.fontManager.addfont(str(find_chinese_font()))
    plt.rcParams.update({'font.family':font_manager.FontProperties(fname=str(find_chinese_font())).get_name(),
                         'axes.unicode_minus':False,'font.size':10,'figure.dpi':160})
    fig,axes=plt.subplots(2,3,figsize=(15,8),layout='constrained')
    fig.suptitle('B2-1｜停止前接触位于主孔入口；姿态改善后仍存在针尖遮挡',fontsize=17)
    for k,(run,d) in enumerate(zip(runs,diagnoses)):
        s=d['prestop'];pin=max(s['pins'],key=lambda p:p['main_aperture_overhang_m'])
        ax=axes[k,0]
        ax.add_patch(Circle((0,0),params['entry_radius']*1e3,fc='#e7f1f5',ec='#7293a5',ls='--',label='入口孔'))
        ax.add_patch(Circle((0,0),params['bore_radius']*1e3,fc='white',ec='#177693',lw=2,label='主孔名义圆'))
        t=np.linspace(0,2*math.pi,513)
        r=np.array(pin['rotation']);c=np.array(pin['tip_xy_offset_m'])
        rim=c[:,None]+pin['radius_m']*(r[:2,0,None]*np.cos(t)+r[:2,1,None]*np.sin(t))
        ax.fill(rim[0]*1e3,rim[1]*1e3,color='#dc7d3d',alpha=.25)
        ax.plot(rim[0]*1e3,rim[1]*1e3,color='#ba6024',label='实际姿态针尖投影')
        hole=np.array(pin['hole_xy_m'])
        cc=np.array([x['position_m'][:2] for x in s['contacts'] if pin['pin'] in x['geoms']])
        if len(cc):ax.scatter((cc[:,0]-hole[0])*1e3,(cc[:,1]-hole[1])*1e3,c='#b4353e',s=14,zorder=5,label='重建接触点')
        ax.scatter([0,c[0]*1e3],[0,c[1]*1e3],c=['#177693','#ba6024'],marker='+')
        ax.set(xlim=(-.8,.8),ylim=(-.8,.8),aspect='equal',xlabel='相对孔中心 X / mm',ylabel='相对孔中心 Y / mm',
               title=f"{LABELS[k]}｜{pin['pin']}\n停止前 {s['time_s']:.3f} s；投影超界 {pin['main_aperture_overhang_m']*1e6:.2f} μm")
        if k==0:ax.legend(loc='lower left',fontsize=7)
        ax=axes[k,1]
        cz=np.array([c['position_m'][2] for c in s['contacts']])*1e3
        ax.scatter(np.arange(1,len(cz)+1),cz,s=12,c='#b4353e')
        ax.axhline(params['entry_depth']*1e3,color='#177693',ls='--',label='主孔入口台阶 z=0.250 mm')
        ax.set(xlabel='接触点序号（不是针编号）',ylabel='接触点 Z / mm',ylim=(.2498,.2503),
               title=f"{len(cz)} 个接触点的深度位置\n{ s['overhanging_pins']}/9 根针的投影超出主孔")
        ax.ticklabel_format(axis='y',style='plain',useOffset=False);ax.legend(fontsize=8)
        ax=axes[k,2]
        rows=[x for x in run['trace'] if x['time_s']<=run['stop_time_s']+1e-9]
        ts=[x['time_s'] for x in rows]
        ax.plot(ts,[(x['position_m'][2]-run['case']['start_origin_z_m'])*1e3 for x in rows],color='#177693',label='实际推进量')
        ax.axhline(.25,ls='--',color='#888888',label='同轴针尖到台阶的推进量')
        ax.set(xlabel='仿真时间 / s',ylabel='实际推进量 / mm',ylim=(0,.28),
               title=f"正式停止：{run['termination']}\n末 1 s 推进 {d['last_second_advance_um']:.3f} μm")
        ax.legend(loc='lower right',fontsize=8)
    for ax in axes.flat:ax.grid(alpha=.15)
    fig.supxlabel('接触点由已保存实际姿态重建；载荷和运动来自原始动力学轨迹。投影超界 ≠ 当前穿透；图中孔圆为名义尺寸。',fontsize=10)
    fig.savefig(OUT/'01_停止前接触位置与针尖遮挡.png');plt.close(fig)


def main():
    index,all_runs=read_verified()
    runs=[next(r for r in all_runs if r['case']['name']==name and r['controller']['name']=='B1_fixed_admittance') for name in SELECTED]
    root=ET.parse(FORMAL_MODEL).getroot()
    params={c.get('key'):float(c.get('value')) for c in root.findall('.//extension/plugin/instance/config')}
    holes={g.get('name')[-2:]:np.fromstring(g.get('pos'),sep=' ') for g in root.findall('.//geom[@type="sdf"]')}
    env=CartesianEnvironment(segments=256);out=[]
    OUT.mkdir(parents=True,exist_ok=True)
    for run in runs:
        # Stop record is sampled before the external stop call; use 10 ms before
        # it to make the loaded advancing state explicit and reproducible.
        row=min(run['trace'],key=lambda r:abs(r['time_s']-(run['stop_time_s']-.01)))
        stop_row=min(run['trace'],key=lambda r:abs(r['time_s']-run['stop_time_s']))
        earlier=min(run['trace'],key=lambda r:abs(r['time_s']-(stop_row['time_s']-1.)))
        active=[r for r in run['trace'] if earlier['time_s']<=r['time_s']<=stop_row['time_s']]
        w=np.array([r['contact_wrench_M'] for r in active])
        d={'case':run['case']['name'],'termination':run['termination'],'stop_time_s':run['stop_time_s'],
           'initial_angle_deg':angle(run['trace'][0]),'initial_xy_um':(np.array(run['trace'][0]['position_m'][:2])*1e6).tolist(),
           'last_second_advance_um':(stop_row['position_m'][2]-earlier['position_m'][2])*1e6,
           'last_second_mean_lateral_force_mN':float(np.mean(np.linalg.norm(w[:,:2],axis=1))*1e3),
           'last_second_mean_abs_axial_force_mN':float(np.mean(abs(w[:,2]))*1e3),
           'prestop':snapshot(env,row,holes,params),'peaks':run['peaks'],
           'controller_limited_steps':run['controller_limited_steps'],
           'source_file':f'deliverables/b1_fixed_admittance/runs/{run["case"]["name"]}_b1.json'}
        out.append(d)
    dump(OUT/'contact_diagnosis.json',{'scope':'offline_geometry_from_verified_B1_trajectories_not_new_dynamics',
         'geometry_parameters':params,'cases':out,'source_sha256':{d['source_file']:hashlib.sha256((ROOT/d['source_file']).read_bytes()).hexdigest() for d in out},
         'b1_code_sha256':index['source_sha256'],'historical_source_sha256':index['historical_source_sha256']})
    make_figure(runs,out,params)
    for d in out:
        s=d['prestop'];print(json.dumps({k:v for k,v in d.items() if k not in ('prestop','peaks')},ensure_ascii=False))
        print(json.dumps({'time':s['time_s'],'xy_um':(np.array(s['position_m'][:2])*1e6).tolist(),'angle_deg':s['angle_deg'],
              'contacts':len(s['contacts']),'pins_overhanging':s['overhanging_pins'],
              'overhang_range_um':(np.array([min(p['main_aperture_overhang_m'] for p in s['pins']),max(p['main_aperture_overhang_m'] for p in s['pins'])])*1e6).tolist(),
              'F_mN':(np.array(s['saved_force_M_N'])*1e3).tolist(),'correction_velocity':s['saved_correction_velocity']},ensure_ascii=False))


if __name__=='__main__':main()
