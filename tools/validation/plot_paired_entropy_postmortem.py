"""Plot saved postmortem arrays, with no simulation or neural inference."""
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'deliverables/learning_chain/five_axis_entropy_postmortem_20261027'


def main():
    data=np.load(OUT/'plot_arrays.npz')
    available={x.name for x in font_manager.fontManager.ttflist}
    font=next((f for f in ['Microsoft YaHei','SimHei','Arial Unicode MS'] if f in available),'DejaVu Sans')
    plt.rcParams.update({'font.family':font,'axes.unicode_minus':False,'font.size':10})
    fig,axes=plt.subplots(3,4,figsize=(15,9.8))
    cases=[('YAW_P10','初始yaw +1°'),('YAW_M10','初始yaw −1°'),
           ('YAW_P15','初始yaw +1.5°'),('YAW_M15','初始yaw −1.5°')]
    for col,(case,title) in enumerate(cases):
        for arm,color in [('A0','#2563eb'),('A2','#e67e22')]:
            key=arm+'_'+case;t=data[key+'_time'];p=data[key+'_position'];r=data[key+'_rpy']
            axes[0,col].plot(p[:,0]*1000,p[:,1]*1000,color=color,label=arm,lw=1.25)
            axes[0,col].scatter(p[-1,0]*1000,p[-1,1]*1000,color=color,s=20,marker='s')
            axes[1,col].plot(t,(p[:,2]-p[0,2])*1000,color=color,lw=1.25)
            axes[2,col].plot(t,r[:,2],color=color,lw=1.25)
        axes[0,col].scatter([0],[0],marker='+',color='black',s=75,label='孔组中心')
        axes[0,col].scatter([.3],[.3],marker='o',facecolors='none',edgecolors='black',s=30)
        axes[0,col].set_title(title);axes[0,col].set_xlabel('X（mm）');axes[0,col].set_ylabel('Y（mm）')
        axes[0,col].set_xlim(-.05,1.10);axes[0,col].set_ylim(-.10,.75)
        axes[0,col].set_aspect('equal',adjustable='box')
        axes[1,col].axhline(1,ls=':',color='#64748b',label='正姿态针尖到孔口')
        axes[1,col].axhline(5,ls='--',color='#475569',label='任务目标')
        axes[1,col].set_ylim(-.1,5.2);axes[1,col].set_ylabel('公头推进（mm）')
        axes[2,col].axhline(0,ls='--',color='#64748b')
        axes[2,col].set_ylim(-2.45,1.8);axes[2,col].set_ylabel('实际yaw（°）')
        for row in [1,2]:
            axes[row,col].set_xlim(0,25);axes[row,col].set_xlabel('实际控制时间（s）')
        for row in range(3):axes[row,col].grid(alpha=.18)
    axes[0,0].legend(fontsize=8,loc='upper left')
    axes[1,0].legend(fontsize=8,loc='upper right')
    fig.suptitle('A0/A2：实际平移、推进和yaw（只读原评价轨迹，截于25 s）',fontsize=14)
    fig.tight_layout(rect=[0,0,1,.96])
    fig.savefig(OUT/'实际运动与姿态对比.png',dpi=170,bbox_inches='tight')
    plt.close(fig)
    (OUT/'analysis_source_snapshot'/Path(__file__).name).write_bytes(Path(__file__).read_bytes())


if __name__=='__main__':main()
