"""Reproduce the Chinese B2 strategy overview, distinct from experimental data."""
import matplotlib
matplotlib.use('Agg')
from matplotlib import pyplot as plt,font_manager
from matplotlib.patches import FancyBboxPatch
from tools.visualization.font_support import find_chinese_font
from tools.validation.run_b2_search import OUT


def main():
    font_manager.fontManager.addfont(str(find_chinese_font()))
    plt.rcParams['font.family']=font_manager.FontProperties(fname=str(find_chinese_font())).get_name()
    fig,ax=plt.subplots(figsize=(12,7),dpi=160)
    ax.set(xlim=(0,12),ylim=(0,7));ax.axis('off')
    def box(x,y,title,sub,color='#e9f1f5'):
        ax.add_patch(FancyBboxPatch((x,y),3,1,boxstyle='round,pad=0.10',fc=color,ec='#628295'))
        ax.text(x+1.5,y+.67,title,ha='center',va='center',fontsize=13,weight='bold')
        ax.text(x+1.5,y+.25,sub,ha='center',va='center',fontsize=10)
    def arrow(a,b,label,xy):
        ax.annotate('',xy=b,xytext=a,arrowprops={'arrowstyle':'->','lw':1.6,'color':'#526f7e'})
        ax.text(*xy,label,ha='center',fontsize=9,bbox={'facecolor':'white','edgecolor':'none','pad':1})
    box(.3,4.9,'正常推进','固定四轴导纳 + Z 推进')
    box(4.5,4.9,'有限减载','低速后退，最多 1 秒')
    box(8.7,4.9,'局部搜索','低载荷 + 有界横向螺旋')
    box(8.7,2.4,'停止与条件回撤','最多回撤一次，随后重新搜索')
    box(.3,2.4,'几何完成判定','到目标后停止，稳定保持 0.1 秒','#e8f2e7')
    box(4.5,.45,'记录失败并停止','保护触发 / 超时 / 预算耗尽','#f8e9e4')
    arrow((3.4,5.4),(4.35,5.4),'轴向受阻',(3.9,5.8))
    arrow((7.6,5.4),(8.55,5.4),'载荷降低',(8.1,5.8))
    arrow((10.2,4.8),(10.2,3.55),'搜索预算耗尽',(10.2,4.1))
    arrow((11.5,3.5),(11.5,4.8),'满足恢复条件',(11.0,3.9))
    arrow((1.8,4.8),(1.8,3.55),'到达目标',(1.8,4.1))
    arrow((8.6,2.6),(7.6,1.45),'恢复条件不满足',(7.5,2.2))
    ax.annotate('',xy=(1.8,6.0),xytext=(10.2,6.0),arrowprops={'arrowstyle':'->','connectionstyle':'arc3,rad=.15','lw':1.4,'color':'#526f7e'})
    ax.text(6,6.6,'实际推进超过 0.10 mm → 退出搜索，恢复正常推进',ha='center',fontsize=11,
            bbox={'facecolor':'white','edgecolor':'none','pad':2})
    ax.text(6,1.7,'所有状态共用：20 秒动作预算；原有力、力矩、穿透与行程保护',ha='center',fontsize=11,color='#9b4b40')
    fig.suptitle('B2-2｜待检验的受限搜索策略',fontsize=18)
    fig.savefig(OUT/'02_B2策略流程图.png',bbox_inches='tight');plt.close(fig)


if __name__=='__main__':main()
