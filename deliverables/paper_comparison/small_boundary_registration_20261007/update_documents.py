"""Maintain rolling status and snapshots; research implementation stays pending."""
from pathlib import Path
import re,shutil
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2]
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
SUMMARY='PC-11公平小边界登记草案完成：有条件只读继承25份B2/F0/S0/F2000/S2000评价，拟仅新增F12.5匹配训练，四轴物理尺度12.5μm/s与0.125mrad/s。拟21新动态/2000正式批（2预检＋19训练评价），数值门拟4合成更新/32测试状态单列；若以后获批，累计上限229。历史成本外推约2.10h、规划2–4h、拟整体硬限6h；不是新实测。'
STATE='本轮新物理/子步/检查点加载/网络推理/更新/经验发布0，实际累计208，自动跟踪PAUSED、新训练准入无、旧预算关闭。704旧封存文件及1057共享输入保持；草案完成不算新增训练能力，完整B.2/C仍待验收。'
NEXT='下一项只实现新F12.5薄适配与离线门，完成归一化动作/物理尺度一致、外层完整检查点、来源绑定和21次一次性驱动的可审阅候选。保持共享来源和共同key；继承门失败就停止本方案，不自动三组重训。数值/物理/训练计算须另有明确预算及准入，当前不启动。'

def section(s,title,value):
    pattern=re.escape(title)+r'\n.*?(?=\n## |\Z)'
    assert len(re.findall(pattern,s,re.S))==1,title
    return re.sub(pattern,lambda _:title+'\n\n'+value+'\n',s,count=1,flags=re.S)

def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    for name in DOCS:
        p=ROOT/name;before=OUT/'before_documents'/name
        if not before.exists():before.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,before)
        s=p.read_text(encoding='utf8');prefix='../../../' if name.startswith('deliverables/') else ''
        base=prefix+'deliverables/paper_comparison/small_boundary_registration_20261007/'
        design=prefix+'docs/superpowers/specs/2026-10-07-small-boundary-fair-comparison-design.md'
        block=f'''<!-- pc11-current -->
**PC-11收口（2026-10-07）：公平对照草案完成，实现/准入/执行未开始。** {SUMMARY}

旧S/F用时改善0.39%未过10%门保持，补小边界对照不把旧S升级为通过。本项主要问题是小边界匹配训练的学习收益与减少对中干扰；S作参照，四轴幅度/权限差异不冒称单变量或完整因子消融。

{STATE}

{NEXT}

[草案说明]({base}结果说明.md)、[完整设计与路线]({design})、[机器登记（非执行资格）]({base}draft_contract.json)、[预算依据]({base}budget_basis.json)。可交付阶段完成后暂停汇报；历史时点的旧下一项不作为当前授权。
<!-- /pc11-current -->'''
        pat=r'<!-- pc11-current -->.*?<!-- /pc11-current -->'
        if re.search(pat,s,re.S):s=re.sub(pat,lambda _:block,s,count=1,flags=re.S)
        else:s=s.replace('\n','\n\n'+block+'\n',1)
        if name=='项目进度跟踪.md':
            old='| C 候选约束与消融 | 待验收；PC-10离线路径证据已验收 | [失败证据与路线](deliverables/paper_comparison/search_path_comparison_20261007/结果说明.md) | 停止直接F→G部署；完整机制、匹配训练与正式消融未完成 |'
            new='| C 候选约束与消融 | 待验收；PC-11公平对照草案完成 | [登记设计](docs/superpowers/specs/2026-10-07-small-boundary-fair-comparison-design.md) | 旧S/F继续门失败保持；新小边界未实现/未准入，完整进展约束和消融未完成 |'
            assert old in s or new in s;s=s.replace(old,new)
            labels=['1 开发适用性','2 统一闭环/SAC接口','3 动态闭环/成本','4 B1','5 B2与批量评价','6 普通残差SAC','7 阶段与进展约束','8 正式证据与展示']
            values=['仅五个已用开发点，四消费首次位置排除；姿态/联合范围仍待',
                '137维/4维及1057共享输入保持；新小尺度动作/回放/完整检查点只有设计，尚未实现',
                'PC-11新增计算0，实际累计208；21动态/2000批和累计229仅为待批提案',
                '历史B1结果保持，本轮未补采',
                '拟只读继承25份既有评价，不能重贴key；本轮未新增B2或策略评价',
                'F12.5匹配训练拟采用同零起点与新数据；物理12.5μm/s、RP0.125mrad/s，仅草案',
                '旧S/F0.39%未过10%继续门，C不自动升级；本项主要审查小边界候选',
                'PC-11设计、21次拟矩阵、成本依据和后续路线交付；完整B.2/C及论文多种子/新最终测试仍待']
            for label,value in zip(labels,values):
                s,n=re.subn(r'\| '+re.escape(label)+r' \| [^\n]* \|',lambda _:f'| {label} | {value} |',s,count=1);assert n==1
            s=s.replace('本轮验收仅为离线失败原因与路线证据；G失败、S旧成功与PC-09固定部署结果均保持，未追加性能样本。',
                '本轮完成登记草案；生产实现、真实计算、准入及性能验收均未发生，历史G失败/S旧成功保持。')
            s=section(s,'## 下一项交付',NEXT+'\n\n'+STATE+'\n\n[未来实现计划（全部未开始）](docs/superpowers/plans/2026-10-07-small-boundary-fair-comparison.md)。')
            a=s.index('## 当前风险和准入门');b=s.index('下表保留历史限制',a)
            s=s[:a]+'## 当前风险和准入门\n\n'+SUMMARY+'\n\n'+STATE+'\n\n风险：元数据可比不等于数值恢复/训练准入；旧F/S权限的内部引擎身份不能掩盖新F12.5物理合同。保留归一化a、内部0.25a与实际命令的不同语义，继承门不通过即停止。旧S/F负结果不随新增baseline翻转。\n\n'+s[b:]
            marker='### 2026-10-07｜PC-11公平小边界登记草案交付'
            if marker not in s:s+='\n\n'+marker+'\n\n'+SUMMARY+' '+STATE+' '+NEXT+' 来源及设计：[草案]('+base+'结果说明.md)、[来源核对]('+base+'source_checks.json)、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            marker='### PC-11｜公平小边界登记草案（2026-10-07）'
            if marker not in s:s=s.replace('### PC-10｜',marker+'\n\n- **获得：** '+SUMMARY+'\n- **使用：** [设计]('+design+')、[机器草案]('+base+'draft_contract.json)、[成本依据]('+base+'budget_basis.json)、[后续计划（未执行）]('+prefix+'docs/superpowers/plans/2026-10-07-small-boundary-fair-comparison.md)。\n- **限制：** '+STATE+'\n\n### PC-10｜',1)
        elif name.startswith('deliverables/'):
            s=re.sub(r'统计截至：[^\n]*','统计截至：2026-10-07（北京时间，PC-11登记草案交付）。实时状态见[项目进度跟踪](../../../项目进度跟踪.md)，10月维护本文件；9月保持历史口径。',s,count=1)
            parts={'## 一、本月综合摘要':SUMMARY+' '+STATE,
                '## 二、关键数字与证据':'PC-11：只读继承拟25评价；本轮计算0、实际累计208。未来提案21动态/2000正式批＋4合成事务/32测试状态，累计上限229未启用；2.10h历史外推/2–4h窗口/6h拟硬限。704旧文件与1057共享输入保持。',
                '## 三、负结果与限制':'PC-11：旧S/F仅0.39%未过10%门，追加baseline不能翻转。新F12.5尺度和未缩放归一化回放尚未实现，旧元数据相同不是数值准入。单种子五开发点、四轴共同缩幅，不是泛化或完整权限×尺度消融。',
                '## 四、图表与讲稿':'PC-11沿用PC-10证据图，不新增实验图。[预算与来源]('+base+'budget_basis.json)。讲稿：“先补真正按小边界训练的合理对照，保留旧S没有明显优于F的负结果。相同起点和历史来源允许省重复成本，但必须重新审核新物理尺度与检查点；21次仍只是待批预算。”'}
            for i,(heading,value) in enumerate(parts.items()):
                marker='<!-- pc11-monthly-'+str(i)+' -->'
                if marker not in s:s=s.replace(heading+'\n',heading+'\n\n'+marker+'\n'+value+'\n',1)
            s=s.replace('[预算与来源]( '+base+'budget_basis.json)','[预算与来源]('+base+'budget_basis.json)')
            s=section(s,'## 五、下一项',NEXT+'\n\n'+STATE+'\n\n[完整设计]('+design+')。')
            marker='### 2026-10-07｜PC-11登记草案来源'
            if marker not in s:s+='\n\n'+marker+'\n\n'+SUMMARY+' '+STATE+' '+NEXT+' [机器草案]('+base+'draft_contract.json)、[成本依据]('+base+'budget_basis.json)、[设计]('+design+')。\n'
        p.write_text(s,encoding='utf8',newline='\n');snapshot=OUT/'documents_snapshot'/name
        snapshot.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,snapshot)
    print('Five rolling documents updated: draft complete, implementation/admission/execution pending')

if __name__=='__main__':main()
