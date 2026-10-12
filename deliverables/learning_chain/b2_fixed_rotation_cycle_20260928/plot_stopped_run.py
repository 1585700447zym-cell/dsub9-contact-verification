"""Static figures from archived facts, without native or learning imports."""
from pathlib import Path
import gzip
import hashlib
import json
import math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.colors import ListedColormap
import numpy as np

D=Path(__file__).resolve().parent;OUT=D/'figures';OUT.mkdir(exist_ok=True)
font=FontProperties(fname='C:/Windows/Fonts/msyh.ttc').get_name()
plt.rcParams.update({'font.family':font,'font.size':10,'axes.unicode_minus':False,
    'axes.spines.top':False,'axes.spines.right':False,'svg.fonttype':'none'})
inputs={};outputs={}


def load(path):
    b=path.read_bytes();inputs[path.relative_to(D).as_posix()]=hashlib.sha256(b).hexdigest()
    return json.loads(gzip.decompress(b) if path.suffix=='.gz' else b)


def save(fig,name):
    for ext in ('png','svg'):
        path=OUT/(name+'.'+ext);fig.savefig(path,dpi=155,bbox_inches='tight')
        outputs[path.relative_to(D).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    plt.close(fig)


def main():
    a=load(D/'assessment.json');es=a['episodes'];train=[r for r in es if r['group']=='training']
    ids=['x_pos_100','x_neg_100','y_pos_100','y_neg_100'];labels=['+X','−X','+Y','−Y']
    groups={g:{r['id']:r for r in es if r['group']==g} for g in ('baseline','initial')}
    fig,axs=plt.subplots(2,2,figsize=(13.5,8.5),layout='constrained')
    fig.suptitle('固定转动残差候选｜力保护停止，B.2证据尚未完整',fontsize=16)
    matrix=[[int(groups[g][i]['outcome']=='FULL_SUCCESS') for i in ids] for g in groups]+[[-1]*4]
    ax=axs[0,0];ax.imshow(matrix,cmap=ListedColormap(['#e3e5e8','#d5907f','#7db7a7']),vmin=-1,vmax=1,aspect='auto')
    ax.set_xticks(range(4),labels);ax.set_yticks(range(3),['复用B2：3/4','新幅度初始：4/4','训练后最终：缺失'])
    for i,row in enumerate(matrix):
        for j,v in enumerate(row):ax.text(j,i,{-1:'未执行',0:'任务失败',1:'成功'}[v],ha='center',va='center')
    ax.set_title('A  固定四点确定性评价；初始结果不是学习收益',loc='left')
    ax=axs[0,1];colors={'FULL_SUCCESS':'#267f72','TASK_FAILURE':'#b38237','CONTACT_GUARD':'#bb4545'}
    for i in range(12):
        ax.bar(i+1,1,color=colors[train[i]['outcome']] if i<len(train) else '#e3e5e8',width=.72)
        if i<len(train):ax.text(i+1,.48,str(train[i]['updates_at_start']),ha='center',rotation=90,color='white')
    ax.axvline(4.5,ls='--',color='#555');ax.set_yticks([]);ax.set_xticks(range(1,13));ax.set_ylim(0,1.35)
    ax.text(2.5,1.1,'随机预热1/4',ha='center');ax.text(5,1.1,'力保护',ha='center',color='#a33')
    ax.text(9,1.1,'未执行',ha='center');ax.set_xlabel('训练回合；柱内为开始前更新批数')
    ax.set_title('B  绿=成功；黄=任务失败；红=保护；灰=未执行',loc='left')
    ax=axs[1,0]
    for g,marker,label in [('baseline','s','B2'),('initial','o','初始策略'),('training','^','随机采集')]:
        rows=[r for r in es if r['group']==g];ax.scatter([r['final_xy_um'] for r in rows],[r['final_angle_deg'] for r in rows],marker=marker,label=label,s=48)
    ax.axvline(50,color='#666',ls='--');ax.axhline(.5,color='#666',ls='--')
    f=train[-1];ax.annotate('第5回合：已回撤，未插入成功',(f['final_xy_um'],f['final_angle_deg']),xytext=(53,.27),arrowprops={'arrowstyle':'->'},fontsize=9)
    ax.set(xlabel='终态XY误差（微米）',ylabel='终态姿态角（度）',ylim=(0,.55));ax.legend(fontsize=9)
    ax.set_title('C  低姿态误差不代表满足深度与完整成功条件',loc='left')
    axs[1,1].axis('off');axs[1,1].text(.03,.95,
        '已完成：初始评价4回合；预热4回合\n已发布：22,766条经验；更新500批\n硬停止：第5回合，6,293条拒绝入池\n\n缺失：最终开发、独立恢复、独立评价\n剩余：23次启动、4,000批更新均不执行\n\n后台已停止，自动跟踪已暂停\n本轮不能宣称策略收益或B.2完成',va='top',linespacing=1.8,fontsize=12)
    save(fig,'01_结果台账与验收缺口')

    fig,axs=plt.subplots(2,2,figsize=(13.5,8.2),layout='constrained')
    fig.suptitle('已完成的B2与初始策略比较｜不代表训练后效果',fontsize=16)
    x=np.arange(4);width=.34
    for ax,key,mul,title,ylabel,threshold in [
        (axs[0,0],'force_peak_N',1,'A  接触力周期峰值','力（N）',.025),
        (axs[0,1],'torque_peak_Nm',1e3,'B  接触力矩周期峰值','力矩（mN·m）',.5),
        (axs[1,0],'sampled_penetration_peak_um',1,'C  周期末采样穿透最大值','穿透（微米）',30)]:
        for j,(g,label,c) in enumerate([('baseline','B2','#6486a6'),('initial','初始策略','#348f7b')]):
            ax.bar(x+(j-.5)*width,[groups[g][i][key]*mul for i in ids],width,label=label,color=c)
        ax.axhline(threshold,color='#a44',ls='--',label='冻结保护阈值');ax.set_xticks(x,labels)
        ax.set_title(title,loc='left');ax.set_ylabel(ylabel);ax.legend(fontsize=8)
    ax=axs[1,1];common=[i for i in ids if all(groups[g][i]['outcome']=='FULL_SUCCESS' for g in groups)]
    x=np.arange(len(common))
    for j,(g,label,c) in enumerate([('baseline','B2','#6486a6'),('initial','初始策略','#348f7b')]):
        ax.bar(x+(j-.5)*width,[groups[g][i]['task_stop_time_s'] for i in common],width,label=label,color=c)
    ax.set_xticks(x,[labels[ids.index(i)] for i in common]);ax.set_ylabel('至任务停止决策的仿真时间（秒）')
    ax.set_title('D  仅配对共同成功的3点；失败不算更快',loc='left');ax.legend(fontsize=9)
    fig.supxlabel('B2 3/4、初始4/4；载荷图包含全部4点。周期峰值由冻结奖励公式反算；采样穿透不是子步峰值。',fontsize=10)
    save(fig,'02_已有对照载荷与共同成功耗时')

    raw=load(D/'run/training_episodes/train_04/episode.json.gz');updates=load(D/'run/training/updates.json')
    rows=raw['transitions'];t=np.array([r['trace_row']['time_s'] for r in rows])
    forces=[.025*math.sqrt(max(0.,-r['reward_terms']['force']/(.2*r['dt']))) for r in rows]
    ang=[];request=[];effective=[]
    for r in rows:
        q=r['trace_row']['quaternion_wxyz'];ang.append(math.degrees(2*math.acos(min(1.,abs(q[0])/math.sqrt(sum(v*v for v in q))))))
        request.append(np.linalg.norm(r['action_log']['applied_residual'][3:])*1e3)
        effective.append(np.linalg.norm(r['action_log']['effective_command_delta'][3:])*1e3)
    fig,axs=plt.subplots(4,1,figsize=(13.5,11),layout='constrained')
    fig.suptitle('第5回合恢复后力保护｜500批后的首个随机策略采集',fontsize=16)
    axs[0].plot(t,forces,color='#b34a42',lw=1);axs[0].axhline(.025,ls='--',color='#555')
    axs[0].set_ylabel('力周期峰值（N）');axs[0].set_title('A  最大0.0250018 N，触发冻结0.025 N力门',loc='left')
    axs[1].plot(t,ang,color='#4c75a2');axs[1].axhline(.5,color='#555',ls='--')
    axs[1].set_ylabel('实际姿态角（度）');axs[1].set_title('B  全回合子步最大姿态0.191°；仍未完成插接',loc='left')
    axs[2].plot(t,request,label='允许执行的转动残差请求模长',lw=.9,color='#967641')
    axs[2].plot(t,effective,label='同状态限幅后命令增量模长',lw=.9,color='#378977')
    axs[2].set_ylabel('角速度（mrad/s）');axs[2].legend(fontsize=9,loc='upper right')
    axs[2].set_title('C  保护后残差归零；命令增量不是零残差反事实运动',loc='left')
    resume=a['failure']['resume_time_s'];trigger=a['failure']['trigger_time_s']
    for ax in axs[:3]:
        ax.axvline(resume,color='#467',ls=':');ax.axvline(trigger,color='#a44',ls=':')
        ax.axvspan(trigger,raw['audit_end_time_s'],color='#ddd',alpha=.45)
        ax.set_xlim(8.9,12.65);ax.set_xlabel('仿真时间（秒）；蓝点线=恢复，红点线=力保护，灰区=最终停止尾段')
    ax=axs[3];ax.plot(range(1,501),[r['critic_loss'] for r in updates],color='#6586a6',lw=.7)
    ax.set_xlabel('实际完成的更新批次');ax.set_ylabel('critic损失');ax.set_title('D  500批更新诊断；损失不能代替任务效果',loc='left')
    right=ax.twinx();right.plot(range(1,501),[r['alpha_after'] for r in updates],color='#ad7140');right.set_ylabel('温度α',color='#ad7140')
    save(fig,'03_力保护时序与更新诊断')
    for name,pin in inputs.items():assert hashlib.sha256((D/name).read_bytes()).hexdigest()==pin
    manifest=dict(inputs_sha256=inputs,outputs_sha256=outputs,renderer_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        additional_physical_starts=0,additional_optimizer_calls=0,limitations=['No final policy evaluation exists.','Sampled penetration is not a substep peak.'])
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Created 3 PNG and 3 SVG figures from sealed data only.')


if __name__=='__main__':main()
