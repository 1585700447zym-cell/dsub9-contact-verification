"""Update existing rolling documents; preserve old sealed and historical records."""
from pathlib import Path
import json,re,shutil
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']

SUMMARY='PC-10离线搜索路径对照已完成：4份既有负Y档案/28,465周期，5段SEARCH/15,626周期。G两段最大净深度−6.140/−6.355μm，未超过旧峰值；参考到120μm圆后下一共同命令超界5.279/0.046nm，按原规则两次耗尽。S首段净深度100.021μm后退出并保持旧10.760s成功。启用命令、参考积分及边界公式核对无执行错误证据；不同演员/权限与前段历史未隔离，不能称唯一训练成因。停止F演员直接套G门控路线，保留匹配训练S及合理小固定边界公平对照方向。'
STATE='本轮新增物理/子步/网络推理/梯度/经验发布均0，累计动态208；旧预算关闭、自动跟踪PAUSED、新训练准入无。生产1057输入及旧658封存文件保持。完整B.2/C、合理小边界重训、多种子和新的冻结最终测试仍待验收。'
NEXT='下一项仅准备S50与合理小固定边界的公平对照登记草案：共同零更新起点、匹配权限/尺度数据、相同登记预算和开发分布、实际成本分列；先审查新来源与保存恢复准入，再另行批准预算。F12.5现有结果只是部署缩放，不当作小边界匹配训练证据；不申请G加训、不扫描门槛或扩网络，四已消费位置不再称未见最终测试。当前不执行新训练。'

def section(s,heading,text):
    pattern=re.escape(heading)+r'\n.*?(?=\n## |\Z)'
    if len(re.findall(pattern,s,re.S))!=1:raise ValueError('Unique rolling section required: '+heading)
    return re.sub(pattern,lambda _:heading+'\n\n'+text+'\n',s,count=1,flags=re.S)

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    for name in DOCS:
        p=ROOT/name;backup=OUT/'before_documents'/name
        if not backup.exists():backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,backup)
        s=p.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else ''
        base=prefix+'deliverables/paper_comparison/search_path_comparison_20261007/'
        block=f'''<!-- pc10-current -->
**PC-10收口（2026-10-07）：离线搜索路径证据交付已验收，完整B.2/C仍待。** {SUMMARY}

{STATE}

{NEXT}

[失败原因与路径图]({base}结果说明.md)、[一页路线决定]({base}路线决定.md)、[原始复算]({base}diagnosis.json)、[逐周期数据]({base}search_cycles.csv)。阶段完成后暂停汇报；下方保留各历史时点，旧“下一项”不作为当前执行授权。
<!-- /pc10-current -->'''
        pattern=r'<!-- pc10-current -->.*?<!-- /pc10-current -->'
        if re.search(pattern,s,re.S):s=re.sub(pattern,lambda _:block,s,count=1,flags=re.S)
        else:s=s.replace('\n','\n\n'+block+'\n',1)
        if name=='项目进度跟踪.md':
            old='| C 候选约束与消融 | 待验收；PC-09固定部署预检收口 | [结果及下一项](deliverables/paper_comparison/contact_gate_probe_20261007/结果说明.md) | 本项为冻结部署，不是G重训/正式消融；连续进展未实现 |'
            new='| C 候选约束与消融 | 待验收；PC-10离线路径证据已验收 | [失败证据与路线](deliverables/paper_comparison/search_path_comparison_20261007/结果说明.md) | 停止直接F→G部署；完整机制、匹配训练与正式消融未完成 |'
            assert old in s or new in s;s=s.replace(old,new)
            rows=['已有五开发点及四个已消费首次位置；PC-10只读负Y既有资料，未扩展姿态/硬件',
                '137维/4维及1057生产输入保持；离线复核接口行为，没有新训练准入',
                'PC-10新增物理/子步/推理/训练/发布0，累计208；4档案28,465周期、5搜索段15,626周期只读',
                '历史五点B1结果保持，本轮未补采',
                'PC-09 B2结果和冻结比较保留，本轮只复核共同SEARCH边界公式，不新增样本',
                '现有F50/F12.5成功档案保持；F12.5仍是部署缩放，公平小边界重训待登记',
                'PC-10确认G两段净进展不足/正常边界耗尽；匹配训练S首段成功，唯一因果及完整C未证',
                'PC-10五段逐周期CSV/对齐/两图/路线决定交付；单点单种子，无新增最终测试或论文优势验收']
            names=['1 开发适用性','2 统一闭环/SAC接口','3 动态闭环/成本','4 B1','5 B2与批量评价','6 普通残差SAC','7 阶段与进展约束','8 正式证据与展示']
            for label,value in zip(names,rows):
                s,n=re.subn(r'\| '+re.escape(label)+r' \| [^\n]* \|',lambda _:f'| {label} | {value} |',s,count=1)
                assert n==1,label
            s=s.replace('本轮仅收口两个已用位置的固定部署预检；G失败不改写为通过，运行有效与论文方法有效分别判断。',
                '本轮验收仅为离线失败原因与路线证据；G失败、S旧成功与PC-09固定部署结果均保持，未追加性能样本。')
            s=section(s,'## 下一项交付',NEXT+'\n\n'+STATE+'\n\n[路线决定]('+base+'路线决定.md)，已授权离线交付完成后暂停汇报。')
            start=s.index('## 当前风险和准入门');end=s.index('下表保留历史限制',start)
            s=s[:start]+'## 当前风险和准入门\n\n'+SUMMARY+'\n\n'+STATE+'\n\n风险：G/S演员与前段历史不同，不能把相近真实入口等同受控因果。第二段回撤回收不等于新进展；参考圆不是80μm附加精度。下一物理/训练仍须新登记，不能复用关闭预算。\n\n'+s[end:]
            marker='### 2026-10-07｜PC-10离线搜索路径对照收口'
            if marker not in s:s+='\n\n'+marker+'\n\n'+SUMMARY+' '+STATE+' 验收证据：6专项+21关联纯档案检查、全部来源摘要核对、边界和深度门原始复算；限定独立审查见新交付目录。限制及下一项：'+NEXT+' [本月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)、[原始证据]('+base+'diagnosis.json)。\n'
        elif name=='项目交付总览.md':
            marker='### PC-10｜离线搜索路径与路线决定（2026-10-07）'
            if marker not in s:
                entry=marker+'\n\n- **获得：** '+SUMMARY+'\n- **使用：** [结果与两图]('+base+'结果说明.md)、[路线决定]('+base+'路线决定.md)、[逐周期CSV]('+base+'search_cycles.csv)、[原始统计]('+base+'diagnosis.json)。分析器仅纯读取；封存后生成操作须在完整副本中复核。\n- **验收与限制：** 6专项+21相关检查及来源复核；'+STATE+'\n\n'
                s=s.replace('### PC-09｜',entry+'### PC-09｜',1)
        elif name.startswith('deliverables/'):
            s=re.sub(r'统计截至：[^\n]*', '统计截至：2026-10-07（北京时间，PC-10离线证据收口）。10月维护同一文件。实时状态见[项目进度跟踪](../../../项目进度跟踪.md)，成果入口见[项目交付总览](../../../项目交付总览.md)；[9月材料](../2026-09/月报素材_2026-09.md)保持历史口径。',s,count=1)
            additions={
                '## 一、本月综合摘要':SUMMARY+' '+STATE,
                '## 二、关键数字与证据':'PC-10：4既有档案/28,465周期；5搜索段/15,626周期；新增计算0，累计208。G最大净深度−6.140/−6.355μm，S100.021μm；两边界预测超圆5.279/0.046nm，658封存文件及1057生产输入保持。6专项+21相关纯档案检查通过。',
                '## 三、负结果与限制':'PC-10：G两次搜索未越过历史峰值，第二段251.097μm只是回收回撤；不同演员和接触历史未隔离，不能定唯一训练成因或断言G不可学。命令执行/参考积分一致、径向请求以内向为主，无依据优先加迟滞、扩大圆或扩网络。停止直接F→G部署；S旧成功不是新增样本。',
                '## 四、图表与讲稿':'PC-10：[五段真实/参考/净深度图]('+base+'search_paths.png)、[四维请求和总命令]('+base+'actions_commands.png)。讲稿：“参考转了圈，针未必同步入孔；恢复向前运动要先扣除旧回撤。匹配训练S到达净推进门，而套用F的G耗尽。当前只支持收缩路线，不支持无证据加训或扩模块。”'}
            for heading,content in additions.items():
                # First invocation only; repeat protection uses a per-section marker.
                m='<!-- pc10-'+str(list(additions).index(heading))+' -->'
                if m not in s:s=s.replace(heading+'\n',heading+'\n\n'+m+'\n'+content+'\n',1)
            s=section(s,'## 五、下一项',NEXT+'\n\n'+STATE+'\n\n[一页路线决定]('+base+'路线决定.md)。')
            marker='### 2026-10-07｜PC-10离线路径来源'
            if marker not in s:s+='\n\n'+marker+'\n\n'+SUMMARY+' '+STATE+' '+NEXT+' 来源：[原始复算]('+base+'diagnosis.json)、[全部搜索周期]('+base+'search_cycles.csv)、[路线决定]('+base+'路线决定.md)。\n'
        p.write_text(s,encoding='utf8',newline='\n')
        snapshot=OUT/'documents_snapshot'/name;snapshot.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,snapshot)
    print('Updated five rolling documents, preserved before copies and immutable snapshots')

if __name__=='__main__':main()
