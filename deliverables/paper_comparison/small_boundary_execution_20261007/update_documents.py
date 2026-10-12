"""Update the five rolling documents, preserving historical sealed material."""
from pathlib import Path
import re,shutil,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
from small_bound_profile import read
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
STATE='新增物理/子步/学习器构造/真实检查点加载/网络前向/优化更新/经验发布均0，累计208，自动跟踪PAUSED、新训练准入无、旧预算关闭；730旧封存文件与1057共享输入保持。完整B.2/C仍未验收。'
NEXT='下一项先实现并审阅独立数值集成脚本与runtime连接，形成最多4合成事务/32测试状态的可审阅数值门，再另行取得明确计算授权后验证零起点、完整落盘与新进程恢复。当前不启动该计算。物理backend尚未连接；21动态/2000正式批及累计229仍只是未启用提案，不能由协议通过或旧余额自动开启。'


def section(s,title,value):
    pattern=re.escape(title)+r'\n.*?(?=\n## |\Z)'
    assert len(re.findall(pattern,s,re.S))==1,title
    return re.sub(pattern,lambda _:title+'\n\n'+value+'\n',s,count=1,flags=re.S)


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    tests=read(OUT/'offline_tests.json');assert tests['passed']
    e=read(OUT/'command_equivalence.json');assert e['matched_command_states']==9750
    summary=f"PC-12小边界离线适配与协议候选完成：四轴F12.5物理尺度、未缩放归一化a、完整检查点外层和固定21次一次性调度已实现；{tests['tests_passed']}项纯检查通过。9752个既有状态中9750个命令级反算通过（7362启用），另2个停止边界无法由旧记录重建完整命令上下文，保留缺口；不是完整轨迹等价或数值恢复验收。"
    for name in DOCS:
        p=ROOT/name;before=OUT/'before_documents'/name
        if not before.exists():before.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,before)
        s=p.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else ''
        base=prefix+'deliverables/paper_comparison/small_boundary_execution_20261007/'
        block=f'''<!-- pc12-current -->
**PC-12（2026-10-07）：离线适配/协议候选完成；数值恢复、物理backend、训练准入未完成。** {summary}

{STATE}

{NEXT}

旧S/F0.39%未过10%继续门保持；本轮不产生新策略性能结论。[候选说明]({base}结果说明.md)、[未准入候选]({base}qualification_candidate.json)、[纯检查]({base}offline_tests.json)、[命令复算及缺口]({base}command_equivalence.json)、[下一数值门]({base}数值门清单.md)。本可交付阶段结束后暂停汇报，历史下一项保留当时口径。
<!-- /pc12-current -->'''
        pat=r'<!-- pc12-current -->.*?<!-- /pc12-current -->'
        if re.search(pat,s,re.S):s=re.sub(pat,lambda _:block,s,count=1,flags=re.S)
        else:s=s.replace('\n','\n\n'+block+'\n',1)
        if name=='项目进度跟踪.md':
            s,n=re.subn(r'\| C 候选约束与消融 \| [^\n]*',
                '| C 候选约束与消融 | 待验收；PC-12离线候选完成 | [适配与协议](deliverables/paper_comparison/small_boundary_execution_20261007/结果说明.md) | 数值/实际backend/准入未完成，不能称匹配训练有效；旧S/F负结果保持 |',s,count=1);assert n==1
            labels=['1 开发适用性','2 统一闭环/SAC接口','3 动态闭环/成本','4 B1','5 B2与批量评价','6 普通残差SAC','7 阶段与进展约束','8 正式证据与展示']
            values=['仅原五开发点；四消费首次位置排除，姿态/联合范围仍待',
                '137维/4维、1057共享输入保持；F12.5动作及检查点外层已实现纯协议，实际数值保存恢复未验收',
                'PC-12新增实际计算0，累计208；21动态/2000批和累计229提案未开启',
                '历史B1结果保持，本轮未补采',
                '25份历史评价只读；9750命令状态反算通过/2停止上下文缺口，未新增B2或策略评价',
                '新小尺度物理12.5μm/s、RP0.125mrad/s与未缩放a适配完成；未匹配训练、未实测新起点',
                '固定预算/保护后关闭/评价不入池协议完成；实际backend与数值/物理准入仍待，C未验收',
                'PC-12候选、检查与缺口交付，完整B.2/C及论文多种子/新最终测试仍待']
            for label,value in zip(labels,values):
                s,n=re.subn(r'\| '+re.escape(label)+r' \| [^\n]* \|',lambda _:f'| {label} | {value} |',s,count=1);assert n==1
            s=section(s,'## 下一项交付',NEXT+'\n\n'+STATE+'\n\n[数值门清单]('+base+'数值门清单.md)。PC-11冻结计划保持，实际部分进度见PC-12实施记录。')
            a=s.index('## 当前风险和准入门');b=s.index('下表保留历史限制',a)
            s=s[:a]+'## 当前风险和准入门\n\n'+summary+'\n\n'+STATE+'\n\n风险：外层协议字节fixture不证明真实张量/优化器/RNG恢复；2旧停止边界上下文缺口保留，不冒称全轨迹B2等价。实际backend与新数值门未完成，未准入候选必须先拒绝。继承来源失效则停止，不自动重训或改变共同key。\n\n'+s[b:]
            marker='### 2026-10-07｜PC-12小边界离线候选交付'
            if marker not in s:s+='\n\n'+marker+'\n\n'+summary+' '+STATE+' '+NEXT+' 来源：[候选]('+base+'结果说明.md)、[检查]('+base+'offline_tests.json)、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            marker='### PC-12｜小边界离线适配与协议候选（2026-10-07）'
            if marker not in s:s=s.replace('### PC-11｜',marker+'\n\n- **获得：** '+summary+'\n- **使用：** [说明]('+base+'结果说明.md)、[未准入候选]('+base+'qualification_candidate.json)、[复核]('+base+'verify.py)、[数值门]('+base+'数值门清单.md)。仅--inspect；--execute缺准入先拒绝，实际backend待。\n- **证据与限制：** '+STATE+' '+NEXT+'\n\n### PC-11｜',1)
        elif name.startswith('deliverables/'):
            s=re.sub(r'统计截至：[^\n]*','统计截至：2026-10-07（北京时间，PC-12离线候选交付）。实时状态见[项目进度跟踪](../../../项目进度跟踪.md)，10月维护本文件；9月保持历史口径。',s,count=1)
            parts={'## 一、本月综合摘要':summary+' '+STATE,
                '## 二、关键数字与证据':f"PC-12：{tests['tests_passed']}纯检查，9750/9752命令状态反算（7362启用、2停止边界缺口）；730旧封存/1057共享输入保持；实际新增计算0、累计208。候选21动态/2000批未启用。",
                '## 三、负结果与限制':'PC-12：2旧停止边界未重建完整上下文，未宣称全轨迹等价。真实零起点和Adam/RNG/回放恢复未验证，物理backend未连接；未准入候选缺计算授权必拒绝。旧S/F0.39%未过10%门不翻转，未新增策略效果证据。',
                '## 四、图表与讲稿':'PC-12使用[阶段证据表]('+base+'结果说明.md)，沿用PC-10原图。讲稿：“这轮把小边界学习的动作语义和一次性协议实现了，但还没有真实数值恢复或新训练；命令复算缺口与后台连接如实列出。”'}
            for title,value in parts.items():
                pos=s.index(title)+len(title);s=s[:pos]+'\n\n'+value+'\n'+s[pos:]
            s=section(s,'## 五、下一项',NEXT+'\n\n'+STATE+'\n\n[下一数值门]('+base+'数值门清单.md)。')
            marker='2026-10-07｜PC-12离线适配候选'
            if marker not in s:s+='\n\n'+marker+'｜'+summary+' '+STATE+' '+NEXT+' 来源：[说明]('+base+'结果说明.md)、[纯检查]('+base+'offline_tests.json)、[来源]('+base+'source_bindings.json)。\n'
        p.write_text(s,encoding='utf8')
        snap=OUT/'document_snapshots'/name;snap.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,snap)
    print('FIVE rolling documents and snapshots updated; historical plans and archives retained')


if __name__=='__main__':main()
