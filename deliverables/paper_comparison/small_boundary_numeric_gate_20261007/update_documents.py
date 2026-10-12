"""Rolling status maintenance; frozen PC12 evidence remains untouched."""
from pathlib import Path
import re,shutil,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
from numeric_contract import read
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
STATE='本轮真实学习器构造/张量读取/网络前向/优化/经验发布/物理/子步均0，累计动态208、自动跟踪PAUSED，新数值/物理/训练授权无、旧预算关闭。765旧封存文件、1057共享输入保持。完整B.2/C仍未验收。'
NEXT='下一项申请并核验一次新的合成数值门授权：最多4更新事务（父3/reader1）、32显式测试状态（各16），新合成400行；物理/正式训练0。获明确授权后才用已绑定CPU解释器验证零起点、完整落盘和独立进程恢复。通过也不自动开启21动态/2000正式批；实际物理backend与新的物理/训练准入仍待。'


def section(s,title,value):
    pattern=re.escape(title)+r'\n.*?(?=\n## |\Z)'
    assert len(re.findall(pattern,s,re.S))==1,title
    return re.sub(pattern,lambda _:title+'\n\n'+value+'\n',s,count=1,flags=re.S)


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    tests=read(OUT/'offline_tests.json');assert tests['passed']
    summary=f"PC-13数值集成门脚本准备完成：授权先查、父/reader共享排他账本、全新合成数据、CPU runtime绑定、零起点与完整检查点/独立进程恢复/下一更新逐值对照脚本已实现；{tests['tests_passed']}项关联纯检查通过，36个runtime文件哈希核验。一轮审查修复覆盖计算收据、关闭余额、进程超时、隔离库来源和辅助开销统计；真正4批/32状态门未执行，不能记数值通过或新资格。"
    for name in DOCS:
        p=ROOT/name;before=OUT/'before_documents'/name
        if not before.exists():before.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,before)
        s=p.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else '';base=prefix+'deliverables/paper_comparison/small_boundary_numeric_gate_20261007/'
        block=f'''<!-- pc13-current -->
**PC-13（2026-10-07）：C公平对照的数值门脚本已准备，真实数值门未授权/未执行。** {summary}

{STATE}

{NEXT}

旧S/F0.39%继续门失败保持；PC-12的9750/9752命令反算与2停止边界缺口不改。本轮没有新性能结论。[准备说明]({base}结果说明.md)、[未授权数值候选]({base}numeric_candidate.json)、[授权请求（未批准）]({base}authorization_request.json)、[纯检查]({base}offline_tests.json)。本阶段完成后暂停汇报，历史下一项保留当时口径。
<!-- /pc13-current -->'''
        pat=r'<!-- pc13-current -->.*?<!-- /pc13-current -->'
        already=bool(re.search(pat,s,re.S))
        if already:
            prior=re.search(pat,s,re.S).group();match=re.search(r'(\d+)项关联纯检查',prior)
            if match:
                old=match[1]
                s=s.replace(old+'项关联纯检查',str(tests['tests_passed'])+'项关联纯检查').replace(old+'关联纯检查',str(tests['tests_passed'])+'关联纯检查')
            s=re.sub(pat,lambda _:block,s,count=1,flags=re.S)
        else:s=s.replace('\n','\n\n'+block+'\n',1)
        if name=='项目进度跟踪.md':
            s,n=re.subn(r'\| C 候选约束与消融 \| [^\n]*',
                '| C 候选约束与消融 | 待验收；PC-13数值门脚本准备完成 | [数值门候选](deliverables/paper_comparison/small_boundary_numeric_gate_20261007/结果说明.md) | 真实数值门待新授权；物理backend/准入仍待，没有新匹配训练或效果结论 |',s,count=1);assert n==1
            labels=['1 开发适用性','2 统一闭环/SAC接口','3 动态闭环/成本','4 B1','5 B2与批量评价','6 普通残差SAC','7 阶段与进展约束','8 正式证据与展示']
            values=['原五开发点范围保持；姿态/联合范围及新的冻结最终测试待',
                '137维/4维保持；新合成数值集成与完整独立恢复脚本准备完成，真实门未执行',
                'PC-13实际新增计算0，累计208；4合成批/32测试状态未授权，21动态/2000正式批也关闭',
                '历史B1结果保持，本轮未补采',
                '25历史评价只读与PC-12命令缺口保持，本轮新性能评价0',
                'F12.5未缩放a/物理尺度适配保持；CPU零起点/实际数值恢复待新门验证，匹配训练未开始',
                'C公平对照前置：全局数值授权/父reader额度/独立恢复候选；C研究验收仍待',
                'PC-13脚本/请求/证据与限制交付；完整B.2/C及论文D仍待']
            for label,value in zip(labels,values):
                s,n=re.subn(r'\| '+re.escape(label)+r' \| [^\n]* \|',lambda _:f'| {label} | {value} |',s,count=1);assert n==1
            s=s.replace('本轮完成登记草案；生产实现、真实计算、准入及性能验收均未发生，历史G失败/S旧成功保持。',
                '当前PC-13完成数值门脚本准备；PC-12适配实现已留证，真实数值门、准入及新性能评价未发生。历史G失败/S旧成功保持。')
            s=section(s,'## 下一项交付',NEXT+'\n\n'+STATE+'\n\n[待批数值门请求]('+base+'authorization_request.json)。')
            a=s.index('## 当前风险和准入门');b=s.index('下表保留历史限制',a)
            s=s[:a]+'## 当前风险和准入门\n\n'+summary+'\n\n'+STATE+'\n\n风险：静态runtime哈希与纯协议通过不证明CPU库加载或真实张量/Adam/RNG恢复。合成资格flags不代表物理停稳；新numeric结果即使通过也不能替代训练资格。未授权必先拒绝，继承/来源改变停止，不重开旧余额。\n\n'+s[b:]
            marker='### 2026-10-07｜PC-13合成数值门脚本准备'
            if marker not in s:s+='\n\n'+marker+'\n\n'+summary+' '+STATE+' '+NEXT+' 来源：[说明]('+base+'结果说明.md)、[检查]('+base+'offline_tests.json)、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            marker='### PC-13｜小边界数值集成门脚本（2026-10-07）'
            if marker not in s:s=s.replace('### PC-12｜',marker+'\n\n- **获得：** '+summary+'\n- **使用：** [说明]('+base+'结果说明.md)、[请求]('+base+'authorization_request.json)、[候选]('+base+'numeric_candidate.json)、[只读复核]('+base+'verify.py)。`numeric_worker.py --inspect`只查看；所有执行模式缺新授权先拒绝。\n- **限制：** '+STATE+' '+NEXT+'\n\n### PC-12｜',1)
        elif name.startswith('deliverables/'):
            s=re.sub(r'统计截至：[^\n]*','统计截至：2026-10-07（北京时间，PC-13数值门脚本准备）。实时状态见[项目进度跟踪](../../../项目进度跟踪.md)，10月维护本文件；9月保持历史口径。',s,count=1)
            parts={'## 一、本月综合摘要':summary+' '+STATE,
                '## 二、关键数字与证据':f"PC-13：{tests['tests_passed']}关联纯检查，36runtime文件哈希，765旧封存/1057共享输入保持。实际计算0、累计208。拟4合成批/32测试状态/400新合成行，模型构造与CPU读取另记开销；物理与正式训练0，额度未开启。",
                '## 三、负结果与限制':'PC-13：真实数值集成尚未执行，不能把协议fake对象或文件哈希当作Adam/RNG恢复通过；物理backend仍待。PC-12两停止上下文缺口保留；S/F0.39%继续门失败不翻转。',
                '## 四、图表与讲稿':'PC-13采用[数值门范围表]('+base+'结果说明.md)。讲稿：“这轮把独立数值恢复的可执行检查脚本准备好了，授权尚未开启；没有新训练性能，现有730+35旧文件和共享来源保持。”'}
            for title,value in parts.items():
                if not already:
                    pos=s.index(title)+len(title);s=s[:pos]+'\n\n'+value+'\n'+s[pos:]
            s=section(s,'## 五、下一项',NEXT+'\n\n'+STATE+'\n\n[授权请求]('+base+'authorization_request.json)。')
            marker='2026-10-07｜PC-13数值门脚本准备'
            if marker not in s:s+='\n\n'+marker+'｜'+summary+' '+STATE+' '+NEXT+' 来源：[说明]('+base+'结果说明.md)、[检查]('+base+'offline_tests.json)、[文件绑定]('+base+'source_bindings.json)。\n'
        p.write_text(s,encoding='utf8');snap=OUT/'document_snapshots'/name;snap.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,snap)
    print('FIVE current documents + snapshots updated; actual numeric gate remains unexecuted')


if __name__=='__main__':main()
