"""Teacher-report MuJoCo playback. No physics integration or policy execution."""
import argparse
import gzip
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.usage.report_demo_core import Timeline, checked_payload

BUNDLE = ROOT/'deliverables/report_demo_20261019'


def load():
    manifest=json.loads((BUNDLE/'manifest.json').read_text(encoding='utf-8'))
    model=checked_payload((BUNDLE/'model_used.xml').read_bytes(), manifest['model_sha256'])
    traces=[json.loads(gzip.decompress(checked_payload((BUNDLE/v['file']).read_bytes(),v['sha256']))) for v in manifest['variants']]
    for tr in traces:
        Timeline([a['time_s'] for a in tr])
        for a in tr:
            p=a['position_m']+a['quaternion_wxyz']
            if len(p)!=7 or not all(math.isfinite(x) for x in p): raise ValueError('存档位姿无效')
            if abs(sum(x*x for x in p[3:])-1)>1e-8: raise ValueError('存档四元数无效')
    from tools.learning.runtime import select_runtime, verify_runtime, active_package
    select_runtime(ROOT/manifest['runtime_record'],expected_digest=manifest['runtime_sha256'])
    verify_runtime(active_package())
    return manifest,model.decode('utf-8'),traces


class Display:
    def __init__(self, xml):
        import mujoco
        self.mj=mujoco
        # Includes and CAD assets are resolved against the project, not the bundle directory.
        os.chdir(ROOT)
        self.model=mujoco.MjModel.from_xml_string(xml)
        if self.model.nq!=7: raise ValueError('演示只支持原始单自由刚体7维位姿')
        self.data=mujoco.MjData(self.model)
        self.model.vis.global_.offwidth=1400
        self.model.vis.global_.offheight=900
        self.model.vis.headlight.ambient[:]=(.55,.55,.55)
        self.model.vis.headlight.diffuse[:]=(.65,.65,.65)
        self.original_group=self.model.geom_group.copy()
        self.original_rgba=self.model.geom_rgba.copy()
        self.names=[mujoco.mj_id2name(self.model,mujoco.mjtObj.mjOBJ_GEOM,i) or '' for i in range(self.model.ngeom)]

    def pose(self,row):
        self.data.qpos[:]=row['position_m']+row['quaternion_wxyz']
        self.data.time=row['time_s']
        # A saved state is displayed without evaluating contacts, integrating or resetting an environment.
        self.mj.mj_kinematics(self.model,self.data)
        self.mj.mj_camlight(self.model,self.data)

    def view(self,kind,camera,opt):
        self.model.geom_group[:]=3
        self.model.geom_rgba[:]=self.original_rgba
        opt.geomgroup[:]=0
        opt.geomgroup[0]=1
        opt.flags[self.mj.mjtVisFlag.mjVIS_STATIC]=1
        camera.azimuth=125
        camera.elevation=-15
        camera.lookat[:]=(0,0,.0004)
        camera.distance=.029
        for i,name in enumerate(self.names):
            if name.startswith('pin_'):
                if kind!=2 or name=='pin_03':
                    self.model.geom_group[i]=0
                    self.model.geom_rgba[i]=(1.,.47,.10,1.)
            elif name.startswith('hole_') and ('entry_' in name or 'main_' in name):
                if kind==2 and not name.startswith('hole_convex256_03_'): continue
                try: sector=int(name.rsplit('_',1)[1])
                except ValueError: continue
                # Remove the near half for the fixed report camera; geometry dimensions are untouched.
                if kind==3 or math.cos(sector*2*math.pi/256-math.radians(125))>.05:
                    self.model.geom_group[i]=0
                    self.model.geom_rgba[i]=(.12,.48,.73,1.)
        if kind==2:
            camera.lookat[:]=(0,.00142,-.00025)
            camera.distance=.014
        elif kind==3:
            camera.elevation=-55
            camera.distance=.030


def geometry(row):
    x,y,z=row['position_m'];w,qx,qy,qz=row['quaternion_wxyz']
    roll=math.degrees(math.atan2(2*(w*qx+qy*qz),1-2*(qx*qx+qy*qy)))
    pitch=math.degrees(math.asin(max(-1,min(1,2*(w*qy-qz*qx)))))
    force=math.sqrt(sum(a*a for a in row['contact_wrench_M'][:3]))
    torque=math.sqrt(sum(a*a for a in row['contact_wrench_G'][3:]))
    return x*1000,y*1000,(z+.005)*1000,roll,pitch,force,torque


def stills(display,traces):
    from PIL import Image
    mj=display.mj
    renderer=mj.Renderer(display.model,height=900,width=1400)
    results=[]
    try:
        for label,seconds,kind in [('initial_array',0.,1),('contact_array',6.,1),('search_pin03',13.,2),('success_array',20.008,1)]:
            tr=traces[0];idx=max(i for i,a in enumerate(tr) if a['time_s']<=seconds+1e-7)
            row=tr[idx];display.pose(row)
            cam=mj.MjvCamera();opt=mj.MjvOption();display.view(kind,cam,opt)
            renderer.update_scene(display.data,camera=cam,scene_option=opt)
            p=BUNDLE/(label+'.png');Image.fromarray(renderer.render()).save(p)
            results.append({'file':p.name,'time_s':row['time_s'],'view':kind})
    finally:renderer.close()
    return results


def gui(display,manifest,traces,smoke_seconds):
    import tkinter as tk
    from tkinter import ttk
    from queue import SimpleQueue
    import mujoco.viewer
    events=SimpleQueue()
    mj=display.mj
    panel=tk.Tk();panel.title('D-sub9 课题汇报｜真实轨迹回放')
    panel.geometry('610x490');panel.minsize(570,460)
    style=ttk.Style(panel);style.configure('TButton',font=('Microsoft YaHei UI',10),padding=7)
    panel.option_add('*Font',('Microsoft YaHei UI',10))
    frame=ttk.Frame(panel,padding=16);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='B.2 第3项｜位置—姿态联合偏差演示',font=('Microsoft YaHei UI',14,'bold')).pack(anchor='w')
    ttk.Label(frame,text='同一工况：X=Y=+0.30 mm；roll=−1.5°，pitch=+1.5°\n合径向偏差约0.424 mm；合轴倾约2.121°；针Ø1.00／孔Ø1.20 mm',justify='left').pack(anchor='w',pady=(10,12))
    pick=tk.StringVar(value='450 μm/s：成功（20.008 s）')
    combo=ttk.Combobox(frame,textvariable=pick,state='readonly',values=['450 μm/s：成功（20.008 s）','300 μm/s：超时（25 s截止）'])
    combo.pack(fill='x');combo.bind('<<ComboboxSelected>>',lambda e:events.put(('case',combo.current())))
    buttons=ttk.Frame(frame);buttons.pack(fill='x',pady=12)
    ttk.Button(buttons,text='开始／暂停',command=lambda:events.put(('toggle',None))).pack(side='left',padx=(0,6))
    ttk.Button(buttons,text='回到初始姿态',command=lambda:events.put(('restart',None))).pack(side='left',padx=6)
    for speed in [.5,1.,2.]:ttk.Button(buttons,text=f'{speed:g}倍速',command=lambda s=speed:events.put(('speed',s))).pack(side='left',padx=3)
    views=ttk.Frame(frame);views.pack(fill='x')
    for n,label in [(1,'九针剖视'),(2,'03号针特写'),(3,'九针全孔')]:
        ttk.Button(views,text=label,command=lambda k=n:events.put(('view',k))).pack(side='left',padx=(0,8))
    seek=tk.DoubleVar(value=0)
    slider=ttk.Scale(frame,from_=0,to=traces[0][-1]['time_s'],variable=seek)
    slider.pack(fill='x',pady=(15,0))
    slider.bind('<ButtonPress-1>',lambda e:events.put(('drag',True)))
    slider.bind('<ButtonRelease-1>',lambda e:events.put(('seek',seek.get())))
    status=tk.StringVar();ttk.Label(frame,textvariable=status,justify='left').pack(anchor='w',pady=10)
    ttk.Label(frame,text='操作：先看初始偏差 → 开始 → 搜索时暂停／切针特写 → 切换300对照。\n鼠标可旋转、滚轮缩放；剖视由固定方向切开，换角度后可重新点视图按钮。\n本窗口仅显示已记录状态；不运行新实验、策略或训练。',foreground='#555555',justify='left').pack(anchor='w',pady=5)
    ttk.Button(frame,text='关闭演示',command=lambda:events.put(('quit',None))).pack(anchor='e')
    panel.protocol('WM_DELETE_WINDOW',lambda:events.put(('quit',None)))
    def key(k):
        if k in (32,80,112):events.put(('toggle',None))
        elif k in (82,114):events.put(('restart',None))
        elif k in (49,50,51):events.put(('view',k-48))
        elif k in (81,113,256):events.put(('quit',None))
    case=0;view=1;drag=False;clock=Timeline([a['time_s'] for a in traces[case]])
    initial=time.perf_counter();iterations=0
    display.pose(traces[case][0])
    with mujoco.viewer.launch_passive(display.model,display.data,key_callback=key,show_left_ui=False,show_right_ui=False) as viewer:
        with viewer.lock():display.view(view,viewer.cam,viewer.opt)
        running=True
        while running and viewer.is_running():
            panel.update_idletasks();panel.update();now=time.perf_counter()
            while not events.empty():
                action,value=events.get()
                if action=='quit':running=False
                elif action=='toggle':
                    if clock.paused:
                        if clock.index==len(clock.times)-1:clock.restart(now)
                        clock.play(now)
                    else:clock.pause(now)
                elif action=='restart':clock.restart(now)
                elif action=='speed':clock.set_speed(value,now)
                elif action=='seek':clock.seek(value,now);drag=False
                elif action=='drag':drag=True;clock.pause(now)
                elif action=='case':
                    case=value;clock=Timeline([a['time_s'] for a in traces[case]])
                    slider.configure(to=clock.times[-1])
                elif action=='view':
                    view=value
                    with viewer.lock():display.view(view,viewer.cam,viewer.opt)
            # Smoke run exercises the actual GUI callbacks and saved-pose switching without dynamics.
            if smoke_seconds and iterations in (2,8,14,20,26):
                events.put({2:('toggle',None),8:('view',2),14:('case',1),20:('seek',12.),26:('restart',None)}[iterations])
            row=traces[case][clock.update(now)]
            with viewer.lock():display.pose(row)
            x,y,advance,roll,pitch,force,torque=geometry(row)
            if not drag:seek.set(clock.position)
            variant=manifest['variants'][case]
            outcome='成功' if variant['outcome']=='FULL_SUCCESS' else '超时失败'
            state='暂停' if clock.paused else '播放'
            status.set(f"{state}｜{row['time_s']:.3f} / {clock.times[-1]:.3f} s｜阶段：{row['policy_phase']}\nX={x:+.3f} mm，Y={y:+.3f} mm，推进={advance:.3f} mm\nroll={roll:+.3f}°，pitch={pitch:+.3f}°；接触力={force:.3f} N，力矩={torque:.4f} Nm\n该档最终结果：{outcome}；当前显示为存档采样（未插值、未放大偏差）")
            hud=f"TILT15_PP | recorded playback | {variant['speed_um_s']} um/s\nt={row['time_s']:.3f}s | {row['policy_phase']} | F={force:.3f} N\nX=Y initial +0.30mm | roll -1.5deg / pitch +1.5deg\nP: play/pause  R: restart  1/2/3: view  Q: quit"
            viewer.set_texts((None,mj.mjtGridPos.mjGRID_TOPLEFT,hud,''));viewer.sync()
            iterations+=1
            if smoke_seconds and now-initial>=smoke_seconds:running=False
            time.sleep(.015)
    panel.destroy()
    return {'iterations':iterations,'gui_closed':True,'saved_case_switch_exercised':bool(smoke_seconds and iterations>26)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--render-stills',action='store_true');parser.add_argument('--smoke-seconds',type=float,default=0)
    args=parser.parse_args()
    manifest,xml,traces=load();display=Display(xml)
    if args.render_stills:result={'stills':stills(display,traces)}
    else:result=gui(display,manifest,traces,args.smoke_seconds)
    result.update(new_dynamic_rollouts=0,policy_calls=0,training_updates=0,original_samples=True)
    (BUNDLE/('render_verification.json' if args.render_stills else 'last_viewer_session.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':main()
