"""Render actual saved B1 poses; playback never creates experimental data."""
import hashlib
import json
import numpy as np
import mujoco
from PIL import Image,ImageDraw,ImageFont
from tools.dynamics.cartesian import CartesianEnvironment
from tools.reporting.report_b1 import read_verified,reason,depth
from tools.validation.run_b1_baseline import OUTPUT,dump
from tools.visualization.render_scenes import style_model_for_display,_scene_option,CAMERAS,CameraPreset
from tools.visualization.font_support import find_chinese_font


def main():
    index,runs=read_verified();pair=runs[8:10]
    out=OUTPUT/'replay';out.mkdir(exist_ok=True)
    env=CartesianEnvironment(segments=256);model=env.model;data=env.data
    style_model_for_display(model,'collision_overlay')
    model.vis.global_.offwidth=1200;model.vis.global_.offheight=700
    model.vis.headlight.ambient[:]=(.5,.5,.5)
    model.vis.headlight.diffuse[:]=(.65,.65,.65)
    renderer=mujoco.Renderer(model,height=500,width=600)
    font=ImageFont.truetype(str(find_chinese_font()),22);small=ImageFont.truetype(str(find_chinese_font()),19)
    titlefont=ImageFont.truetype(str(find_chinese_font()),29)
    option=_scene_option('collision_overlay')
    fullgroups=model.geom_group.copy()

    def render(row,local=False):
        # qpos assignment is allowed only here: offline playback of already integrated states.
        data.qpos[:]=np.r_[row['position_m'],row['quaternion_wxyz']]
        mujoco.mj_kinematics(model,data)
        if local:
            model.geom_group[:]=3
            for i in range(model.ngeom):
                name=mujoco.mj_id2name(model,mujoco.mjtObj.mjOBJ_GEOM,i) or ''
                if name=='pin_05' or name.startswith('hole_convex256_05_'):
                    model.geom_group[i]=0
                    if name.startswith('hole_'):model.geom_rgba[i,3]=.30
            camera=CameraPreset((.00554,.00142,-.00035),.010,125,-12).build()
        else:
            model.geom_group[:]=fullgroups
            camera=CameraPreset((0,0,-.0005),.055,125,-22).build()
        renderer.update_scene(data,camera=camera,scene_option=option)
        return Image.fromarray(renderer.render().copy())

    def frame(rows,t,local):
        canvas=Image.new('RGB',(1200,700),'#F6F8FA');d=ImageDraw.Draw(canvas)
        d.text((24,14),'联合 A ×0.75：真实动力学轨迹回放',font=titlefont,fill='#172B4D')
        for j,(r,row,label) in enumerate(zip(pair,rows,['零反馈参考','B1 固定导纳'])):
            canvas.paste(render(row,local),(j*600,120))
            shown_time=min(t,r['trace'][-1]['time_s'])
            d.text((j*600+22,61),f'{label}   记录时刻 {shown_time:.2f} s',font=font,fill='#172B4D')
            z=(row['position_m'][2]-r['case']['start_origin_z_m'])*1000
            f=np.linalg.norm(row['contact_wrench_M'][:3])*1000
            d.text((j*600+22,92),f'推进 {z:.3f} mm   合力 {f:.2f} mN',font=small,fill='#445568')
            if t>=r['trace'][-1]['time_s']:
                d.text((j*600+22,625),f'回合结束：{reason(r)}（保持末帧）',font=small,fill='#8B4E37')
        caption='针 05 局部视图，孔壁透明仅用于观察。运动幅度保持真实尺度。' if local else '全阵列概览。橙色为针，蓝色为孔接触几何。透明显示不改变仿真。'
        d.text((22,664),caption,font=small,fill='#445568')
        return canvas

    times=[np.array([x['time_s'] for x in r['trace']]) for r in pair]
    end=max(t[-1] for t in times);requested=np.linspace(0,end,106)
    frames=[];mapping=[]
    try:
        for k,t in enumerate(requested):
            # Select recorded rows at or before this playback time, without interpolation.
            ids=[max(0,int(np.searchsorted(ts,t,side='right')-1)) for ts in times]
            rows=[r['trace'][i] for r,i in zip(pair,ids)]
            im=frame(rows,t,True);frames.append(im)
            mapping.append({'playback_s':float(t),'trace_indices':ids,'recorded_s':[r['time_s'] for r in rows]})
            if k in (0,52,105):im.save(out/f'局部回放_{k:03}.png')
        frame([r['trace'][-1] for r in pair],end,False).save(out/'全阵列_终态对照.png')
        render(pair[1]['trace'][-1],False).save(out/'B1终态_全阵列.png')
        frames[0].save(out/'B1联合偏差_真实轨迹回放.gif',save_all=True,append_images=frames[1:],duration=80,loop=0,optimize=False)
    finally:renderer.close()
    files=[index['runs'][i]['file'] for i in (8,9)]
    dump(out/'replay_manifest.json',{'source_runs':{p:hashlib.sha256((OUTPUT/p).read_bytes()).hexdigest() for p in files},
        'renderer_sha256':hashlib.sha256(__import__('pathlib').Path(__file__).read_bytes()).hexdigest(),
        'frames':mapping,'semantics':'offline recorded poses, no interpolation, final pose held after shorter episode',
        'simulation_time_s':end,'playback_duration_s':len(frames)*.08,'physical_motion_scale':1,
        'display_only_changes':['RGBA transparency','geom groups','camera'],'local_pin':'05'})
    print('Saved 106 recorded-state frames, GIF, and overview')


if __name__=='__main__':main()
