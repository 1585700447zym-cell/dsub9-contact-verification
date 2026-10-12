"""Closeout-only rolling docs update. Preserve all old logs and before snapshots."""
from pathlib import Path
import json
import re

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md',
      'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
PLAN='docs/superpowers/plans/2026-10-08-b2-pose-scope-preflight.md'
REL='deliverables/learning_chain/b2_pose_scope_preflight_20261008/'


def section(text,heading,end_marker,body):
    start=text.index(heading)+len(heading);end=text.index(end_marker,start)
    return text[:start]+'\n\n'+body+'\n\n'+text[end:]


def after(text,heading,body):
    assert text.count(heading)==1,heading
    return text.replace(heading,heading+'\n\n'+body,1)


def main():
    tests=json.loads((OUT/'offline_tests.json').read_text(encoding='utf-8'))
    assert tests['passed'] and tests['engine_imports']==[]
    assert 'Final disposition: OFFLINE_IMPLEMENTATION_READY' in (OUT/'review.md').read_text(encoding='utf-8')
    summary=('B2-SCOPE-02小倾角预检离线实现与审查收口：实际初始角贯通、固定9静态/16动态顺序、'
        '一次性新授权及进程监督、完整上下文归档和只读命令/奖励/几何/停止审核已准备。'
        '这属于B.2姿态/联合范围预检准备，真实初始化和动态尚未执行。')
    evidence=(f"{tests['new_tests']}项新离线/无仿真进程检查、12项关联父进程检查通过；一次独立审查及修复记录留档。"
        '950历史封存成员、19个B2-SCOPE-01成员、1057共享输入和63原始档案复核保持。')
    limit=('本轮物理引擎加载、真实初始化、动态/子步及全部神经网络/张量/优化/经验开销均0；'
        '实际累计动态208，自动跟踪PAUSED，旧预算关闭，当前无新训练准入。完整B.2/C未验收。'
        '±0.25°开发预检不覆盖±0.5°边界或原±1.5°目标，脚本作用不等于SAC收益。')
    next_item=('下一项是申请并核验本候选的一次新物理授权：最多9次无积分初始化＋16个零残差/脚本配对动态，'
        '共25次复位，训练/推理/经验发布0；整轮监督硬限6h、无重试。获明确授权后才执行；'
        '若全跑累计上限224，现在仍是208。静态任一失败关闭全部动态；有效停稳的普通失败继续，'
        '保护、无效或停止不明则关闭余量。C的F12.5物理接入继续暂缓。')
    edited={}
    for name in DOCS:
        raw=(ROOT/name).read_bytes();assert raw==(OUT/'before_documents'/name).read_bytes(),name
        text=raw.decode('utf-8').replace('\r\n','\n');prefix='../../../' if name.startswith('deliverables/') else ''
        links=(f'[实现说明]({prefix}{REL}结果说明.md)、[离线检查]({prefix}{REL}offline_tests.json)、'
               f'[审查]({prefix}{REL}review.md)、[新预算请求（未批准）]({prefix}{REL}authorization_request.json)')
        block=f'<!-- b2-scope-current -->\n**2026-10-08｜B.2范围预检离线实现完成，物理未执行。** {summary}\n\n{evidence}\n\n{limit}\n\n{next_item}\n\n{links}。以下旧阶段记录保留当时状态，其历史“下一项”不代表当前授权。\n<!-- /b2-scope-current -->'
        text,count=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda _:block,text,count=1,flags=re.S)
        assert count==1
        if name=='项目进度跟踪.md':
            lines=text.splitlines()
            changes={
                '| B.2 小规模学习与评价包 |':f'| B.2 小规模学习与评价包 | 位置里程碑完成；姿态/联合范围待验收 | [预检离线实现]({REL}结果说明.md)、PC-07位置评价 | 新9静态/16动态候选待物理授权；±0.5°边界/原±1.5°及匹配训练仍缺 |',
                '| 2 统一闭环/SAC接口 |':'| 2 统一闭环/SAC接口 | 新入口已贯通实际初始角并离线验证；真实姿态初始化/闭环证据待补 |',
                '| 5 B2与批量评价 |':'| 5 B2与批量评价 | 8点零残差/脚本运行器和审核已离线准备；9静态/16动态未执行 |',
                '| 8 正式证据与展示 |':'| 8 正式证据与展示 | 本轮交付程序/纯检查/审查/预算请求，无新实验曲线；正式多种子与最终测试仍属D |'}
            for start,value in changes.items():
                indexes=[i for i,line in enumerate(lines) if line.startswith(start)];assert len(indexes)==1,start
                lines[indexes[0]]=value
            text='\n'.join(lines)+'\n'
            text=text.replace('本轮B2-SCOPE-01只补范围审计与方案，历史G失败/S旧成功保持。',
                '本轮B2-SCOPE-02已完成预检离线实现，未新增物理或策略性能证据；历史G失败/S旧成功保持。',1)
            text=section(text,'## 当前风险和准入门','下表保留历史限制',summary+'\n\n'+limit+
                '\n\n新姿态范围尚无真实复位和动态证据，离线通过不能替代物理验收。原S/F0.39%未过10%继续门、首次位置附加精度0/4、旧两个STOP命令上下文缺口均保持。')
            text=section(text,'## 下一项交付','## 追加式阶段记录',next_item+'\n\n'+limit+'\n\n'+links)
            text+=f'\n### 2026-10-08｜B2-SCOPE-02小倾角预检离线实现\n\n{summary}\n\n{evidence}\n\n{limit}\n\n{next_item}\n\n{links}、[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)。\n'
        elif name=='项目交付总览.md':
            text=after(text,'## 快速查找',f'当前优先[B2-SCOPE-02预检程序与使用]({REL}结果说明.md)，物理运行需[新预算授权]({REL}authorization_request.json)。下面保留原审计入口。')
            text=after(text,'## 基线与接口交付',f'### B2-SCOPE-02｜姿态预检离线实现（2026-10-08）\n\n{summary}\n\n{evidence}\n\n{limit}\n\n{links}。使用 `run_preflight.py --check-only` 做无引擎检查；实际执行须新grant。')
        elif name=='研究推进计划_当前版.md':
            text,n=re.subn(r'2026-10-08执行优先级补充：.*?以下原要求保留。',
                lambda _:f'2026-10-08执行优先级更新：{summary} {next_item} 更大范围与原任务6仍待，B.2工程验收与SAC收益判断分开。以下原要求保留。',text,count=1)
            assert n==1
        elif name.startswith('deliverables/'):
            text=text.replace('B2-SCOPE-01离线范围审计；最近数值执行为PC-14','B2-SCOPE-02预检离线实现；最近数值执行为PC-14',1)
            text=after(text,'## 一、本月综合摘要',summary+' '+evidence+' '+limit+' 以下为此前阶段摘要：')
            text=after(text,'## 二、关键数字与证据',f'B2-SCOPE-02：{evidence} 新物理/学习0、累计208；拟9静态/16动态仍未授权。固定失败罚时沿用26s，功能与附加精度分列。')
            text=after(text,'## 三、负结果与限制','预检程序已准备，但没有真实小倾角结果。脚本未触发/无接触/无恢复须记覆盖不足，不能补跑或推断通过；旧S/F收益继续门失败及精度限制不变。')
            text=after(text,'## 四、图表与讲稿',f'本轮引用[固定8点与监督/审核说明](../../../{REL}结果说明.md)，无新实验曲线。讲稿：“当前在补B.2姿态范围，运行器和离线审查已完成，物理预检待新授权；累计208未变，完整B.2/C未验收。”')
            text=section(text,'## 五、下一项','## 六、来源记录',next_item+'\n\n'+limit)
            text+=f'\n### 2026-10-08｜B2-SCOPE-02离线实现来源\n\n{summary} {evidence}\n\n{links}。{limit}\n'
        edited[name]=text
    for name,text in edited.items():
        (ROOT/name).write_text(text,encoding='utf-8',newline='\n')
        target=OUT/'document_snapshots'/name;target.parent.mkdir(parents=True,exist_ok=True)
        with target.open('xb') as f:f.write((ROOT/name).read_bytes())
    p=ROOT/PLAN;text=p.read_text(encoding='utf-8')
    text=text.replace('本文件只完成方案，运行器尚未实现。','本次记录离线实现完成状态；物理执行仍待明确新授权。')
    text=text.replace('（尚未创建）','（已创建，离线实现完成）')
    text='\n'.join(line.replace('- [ ]','- [x]',1) if line.startswith('- [ ]') and '获得该具体新物理授权' not in line else line for line in text.splitlines())+'\n'
    text=text.replace('上述全部任务仍未勾选。','以上为原方案自审时点；2026-10-08更新：离线实施及审查证据见B2-SCOPE-02，实际物理执行步骤仍未完成。')
    text=text.replace('无独立代码审查，因本轮没有实现该运行器。','方案起草时尚无运行器实现和独立代码审查；本次离线实现后的单次审查与修复见B2-SCOPE-02/review.md。')
    text+='\n2026-10-08离线实施收口：'+summary+' '+evidence+' '+limit+' 实际物理执行项保留未勾选，收口项仅指本离线交付。\n'
    p.write_text(text,encoding='utf-8',newline='\n')
    snap=OUT/'document_snapshots'/PLAN;snap.parent.mkdir(parents=True,exist_ok=True)
    with snap.open('xb') as f:f.write(p.read_bytes())
    print('Updated five rolling documents and six immutable snapshots')


if __name__=='__main__':main()
