"""Static research figures from sealed archives; no physics or learning calls."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
from matplotlib.font_manager import FontProperties
import numpy as np

D=Path(__file__).resolve().parent
ROOT=D.parents[2]
sys.path.insert(0,str(ROOT))
from tools.visualization.font_support import find_chinese_font
plt.rcParams.update({'font.family':FontProperties(fname=str(find_chinese_font())).get_name(),
    'axes.unicode_minus':False,'font.size':10,'axes.spines.top':False,'axes.spines.right':False,
    'svg.fonttype':'none'})
OUT=D/'figures';OUT.mkdir(exist_ok=True)
inputs={};outputs=[]


def load(p):
    b=p.read_bytes();inputs[str(p.relative_to(D))]=hashlib.sha256(b).hexdigest()
    return json.loads(gzip.decompress(b) if p.suffix=='.gz' else b)


def save(fig,name):
    for ext in ['png','svg']:
        p=OUT/(name+'.'+ext);fig.savefig(p,dpi=160,bbox_inches='tight')
        outputs.append(str(p.relative_to(D)))
    plt.close(fig)


def main():
    a=load(D/'policy_analysis.json');episodes=a['episodes']
    train=[e for e in episodes if e['group']=='training']
    names=['x_pos_100','x_neg_100','y_pos_100','y_neg_100'];labels=['+X','−X','+Y','−Y']
    fig,axs=plt.subplots(2,2,figsize=(13,8),layout='constrained')
    fig.suptitle('本轮结果与缺口｜单种子、固定开发点，非最终学习效果',fontsize=16)
    cells=[]
    for group in ['baseline','initial']:
        by={e['id']:e for e in episodes if e['group']==group}
        cells.append([int(by[n]['outcome']['task_outcome']=='FULL_SUCCESS') for n in names])
    ax=axs[0,0];ax.imshow(cells,cmap=ListedColormap(['#e4a091','#80b7ad']),vmin=0,vmax=1,aspect='auto')
    ax.set_xticks(range(4),labels);ax.set_yticks(range(2),['纯B2：3/4','未训练策略：4/4'])
    for i in range(2):
        for j in range(4):ax.text(j,i,'成功' if cells[i][j] else '任务失败',ha='center',va='center')
    ax.set_title('A  已完成的确定性评价；训练后评价缺失',loc='left')
    ax=axs[0,1];colors={'FULL_SUCCESS':'#258777','TASK_FAILURE':'#b88436','CONTACT_GUARD':'#b63838'}
    for i,e in enumerate(train):
        ax.bar(i+1,1,color=colors[e['outcome']['task_outcome']],width=.7)
        ax.text(i+1,.48,str(e['updates_at_start']),ha='center',color='white',rotation=90)
    ax.set_ylim(0,1.3);ax.set_yticks([]);ax.set_xticks(range(1,11));ax.axvline(4.5,color='#555',ls='--')
    ax.text(2.5,1.1,'随机预热 2/4',ha='center');ax.text(7.5,1.1,'更新后随机采集 0/6',ha='center')
    ax.set_xlabel('训练回合；柱内为回合开始前更新批数')
    ax.set_title('B  采集台账：绿=成功，黄=任务失败，红=保护',loc='left')
    ax=axs[1,0]
    for group,marker,color,label in [('baseline','s','#45688b','B2确定性'),('initial','o','#258777','初始确定性'),('training','x','#b88436','随机采集')]:
        es=[e for e in episodes if e['group']==group]
        ax.scatter([e['final_xy_um'] for e in es],[e['final_angle_deg'] for e in es],marker=marker,c=color,s=48,label=label)
    for i in [4,5,7,9]:
        e=train[i];ax.annotate('T'+str(i+1),(e['final_xy_um'],e['final_angle_deg']),xytext=(5,5),textcoords='offset points',fontsize=9)
    ax.axvline(50,color='#b63838',ls='--');ax.axhline(.5,color='#b63838',ls='--')
    ax.axvspan(0,50,ymin=0,ymax=0,alpha=0)
    ax.set(xlabel='停稳后XY误差 / μm',ylabel='停稳后姿态误差 / °',xlim=(0,None),ylim=(0,None))
    ax.set_title('C  几何误差；虚线是两项成功门，非全部条件',loc='left');ax.legend(fontsize=9)
    ax=axs[1,1];ax.axis('off')
    ax.text(0,.97,'已完成与尚缺证据',fontsize=13,va='top',weight='bold')
    ax.text(0,.83,'• 9个回合入池，49,313条审核经验\n• 3,000 / 4,500批更新已完成\n• 第10回合触发穿透保护；6,383条拒绝入池\n• 已保存9个审核边界检查点\n\n尚缺：预定最终模型、最终开发评价、\n独立进程恢复重放、冻结后独立评价\n\n随机采集使用不同中间策略，不能把0/6\n当成最终策略成功率；也不能将初始4/4\n解释为学习收益。',va='top',linespacing=1.6)
    save(fig,'01_结果台账与姿态误差')

    u=load(D/'run/training/updates.json')
    fig,axs=plt.subplots(3,1,figsize=(12,9),layout='constrained');fig.suptitle('学习计算与动作行为｜诊断量不等于任务收益',fontsize=16)
    x=np.arange(1,len(u)+1);loss=np.array([r['critic_loss'] for r in u]);ax=axs[0]
    ax.plot(x,loss,color='#b9c8d6',alpha=.7,lw=.5,label='逐批损失')
    ax.plot(np.arange(250.5,3000,500),[b['critic_loss_mean'] for b in a['update_blocks']],color='#355d85',marker='o',label='每500批均值')
    ax.set(xlabel='累计更新批数',ylabel='critic损失',title='A  数值拟合：数据分布随采集变化');ax.legend()
    ax=axs[1];ax.plot(x,[r['alpha_after'] for r in u],color='#258777');ax.set(xlabel='累计更新批数',ylabel='温度 α',title='B  熵温度变化；不能由此单独判断探索是否合适')
    ax=axs[2]
    for j,label,color in [(2,'roll','#355d85'),(3,'pitch','#ad6538')]:
        ax.plot(range(1,11),[100*e['actions']['near_bound_fraction'][j] for e in train],marker='o',label=label,color=color)
    ax.axvspan(.5,4.5,color='#aaa',alpha=.13,label='随机预热');ax.set(xlim=(.5,10.5),ylim=(0,103),xticks=range(1,11),
        xlabel='采集回合（各回合开始时策略不同）',ylabel='|归一化请求| ≥ 0.95 的比例 / %',title='C  有动作权限周期中的转动请求贴边程度；0.95为诊断阈值')
    ax.legend();save(fig,'02_更新诊断与转动请求')

    raw=load(D/'run/training_episodes/train_09/episode.json.gz');rows=raw['transitions'];t=np.array([r['trace_row']['time_s'] for r in rows])
    select=t>=9.;ts=t[select];sub=[r for r,b in zip(rows,select) if b]
    angle=lambda r:math.degrees(2*math.acos(min(1,abs(r['trace_row']['quaternion_wxyz'][0])/np.linalg.norm(r['trace_row']['quaternion_wxyz']))))
    fig,axs=plt.subplots(3,1,figsize=(12,9),sharex=True,layout='constrained');fig.suptitle('第10回合：恢复后穿透保护｜已有轨迹离线回看',fontsize=16)
    axs[0].plot(ts,[r['trace_row']['penetration_m']*1e6 for r in sub],color='#b63838');axs[0].axhline(30,color='#333',ls='--',label='保护阈值30 μm')
    axs[0].set(ylabel='周期末穿透 / μm',title='A  10.7646秒子步触发；周期末最大30.104 μm，不等同精确子步峰值');axs[0].legend(loc='upper right')
    axs[1].plot(ts,[angle(r) for r in sub],color='#355d85');axs[1].axhline(.5,color='#333',ls='--',label='成功姿态门0.5°')
    axs[1].set(ylabel='姿态误差 / °',title='B  姿态与接触状态随恢复过程变化');axs[1].legend(loc='upper right')
    for j,label,color in [(2,'roll','#355d85'),(3,'pitch','#ad6538')]:axs[2].plot(ts,[r['action'][j] for r in sub],lw=.65,label=label,color=color,alpha=.8)
    axs[2].set(xlabel='仿真时间 / s',ylabel='归一化策略动作',ylim=(-1.08,1.08),title='C  保护触发后后续周期动作归零；触发周期开始时仍有权限');axs[2].legend(loc='upper right')
    for ax in axs:
        ax.axvspan(9.256,9.828,color='#999',alpha=.12);ax.axvspan(10.7646,12.766,color='#b63838',alpha=.055)
        ax.axvline(9.828,color='#258777',ls=':',label='恢复');ax.axvline(10.7646,color='#b63838',ls=':');ax.set_xlim(9,12.8)
    axs[0].text(9.828,3,'恢复',rotation=90,color='#258777',ha='right');axs[0].text(10.7646,4,'保护触发',rotation=90,color='#b63838',ha='right')
    save(fig,'03_恢复与保护事件时序')
    for name,pin in inputs.items():assert hashlib.sha256((D/name).read_bytes()).hexdigest()==pin
    record=dict(input_sha256=inputs,output_sha256={n:hashlib.sha256((D/n).read_bytes()).hexdigest() for n in outputs},
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),new_physical_starts=0,new_optimizer_updates=0)
    (OUT/'manifest.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(figures=len(outputs)//2,formats=['png','svg'],new_physical_starts=0,new_optimizer_updates=0)))


if __name__=='__main__':main()
