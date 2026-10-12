"""Integrate the new implementation outcome; old snapshots/experiments stay sealed."""
from pathlib import Path
import os
import re
import shutil
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from scope_contract import ROOT,read,sha
from execution_contract import write
DOCS=['项目当前入口.md','项目进度跟踪.md','项目交付总览.md','研究推进计划_当前版.md','deliverables/monthly_progress/2026-10/月报素材_2026-10.md']

def section(text,heading,body):
    text,n=re.subn('('+re.escape(heading)+r'\n).*?(?=\n## |\Z)',lambda m:m.group(1)+'\n'+body.rstrip()+'\n',text,count=1,flags=re.S)
    assert n==1;return text

def main():
    if (OUT/'document_update.json').exists() or (OUT/'delivery_manifest.json').exists():raise PermissionError('Already documented/sealed')
    import json
    tests=json.loads((OUT/'offline_tests.txt').read_text(encoding='utf-8-sig').strip().splitlines()[-1])
    assert tests['status']=='PASS'
    summary=f"B2-SCOPE-09联合点预检候选实现及离线验收完成：固定A/B日程、一次工程恢复夹具、覆盖审核、新授权与一次性预算门已接入；{tests['tests']}项离线测试通过。既有J01_script的4834周期／4835观测只读回归与封存结果一致。"
    cost='本轮新增环境创建、reset、物理积分、学习器、张量读取、网络前向、优化和经验发布全0；实际累计动态225。自动跟踪PAUSED，旧预算关闭。固定12项新物理预检仍未授权、未执行，237只是以后全部执行的累计上限。'
    limits='当前只验收程序实现和离线证据，真实联合点动作／恢复覆盖仍待实测；纯状态替身和旧档案回归不算新物理成功。完整B.2/C未验收，±0.25°离散点不等于原±1.5°范围，独立评价0、无训练准入；137维及全部共同模型／保护／奖励保持。'
    next_task='下一项是审阅已绑定的12项新物理执行申请：8次A/B动作＋4次R工程恢复，单独静态0、训练0；每回合14500周期／145000子步、1200秒，合计174000周期／1740000子步、整体6小时，含停稳和审核。获明确新授权后才可执行，不重开旧额度或补采到通过。全部相关检查通过，也仅准备另行登记的普通SAC姿态匹配短训；C继续暂缓。'
    reg=read(OUT/'registration.json');updated={}
    for name in DOCS:
        path=ROOT/name;assert sha(path)==reg['before_documents'][name]
        t=path.read_text(encoding='utf-8');rel=os.path.relpath(OUT,path.parent).replace('\\','/')
        links=f'[接入与验收说明]({rel}/接入与验收说明.md)、[未授权执行申请]({rel}/authorization_request.json)、[来源绑定]({rel}/candidate_binding.json)、[离线测试]({rel}/offline_tests.txt)。'
        block='<!-- b2-scope-current -->\n**2026-10-09｜当前阶段B.2；任务：联合点预检候选实现及离线验收，已完成。** '+summary+'\n\n'+cost+'\n\n'+limits+'\n\n'+next_task+'\n\n'+links+' 以下历史阶段的旧下一项不代表当前授权。\n<!-- /b2-scope-current -->'
        t,n=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:block,t,count=1,flags=re.S);assert n==1
        if name=='项目进度跟踪.md':
            t,n=re.subn(r'^\| B\.2 小规模学习与评价包 \|.*$',f'| B.2 小规模学习与评价包 | 待验收；联合点预检实现／离线验收完成 | [B2-SCOPE-09]({rel}/接入与验收说明.md) | 12项物理预检尚未授权；匹配学习、冻结评价、原完整范围仍待 |',t,flags=re.M);assert n==1
            rows=[
                '1 开发适用性 | J01～J04离散点沿用；本轮完成预检程序，真实动作／恢复覆盖和原大范围未验收',
                '2 统一闭环/SAC接口 | 137维保持；新夹具复用原会话准备与恢复，纯逻辑核对无重复基线／历史采样',
                '3 动态闭环/成本 | 本轮动态0，实际累计225；拟12项／174万子步／整体6小时均未授权',
                '4 B1 | 原当前／历史资格按来源继承；只读回归J01，不重跑旧物理矩阵',
                '5 B2与批量评价 | 固定日程、恢复夹具、覆盖审核、新scope和一次性预算门实现；不等同物理资格',
                '6 普通残差SAC | 联合点预检待执行；匹配短训、共同参照、恢复和冻结评价仍需独立登记',
                '7 阶段与进展约束 | C继续暂缓；原PC11～14数值成果保留，不能替代B.2验收',
                '8 正式证据与展示 | 交付程序／测试／旧真实档案回归／来源绑定／未授权申请；新独立评价与策略效果0']
            t=section(t,'## 原八项任务对应','| 原任务 | 本次核对状态 |\n|---|---|\n'+'\n'.join('| '+r+' |' for r in rows)+'\n\n'+cost)
            start=t.index('## 当前风险和准入门');end=t.index('下表保留历史限制',start)
            t=t[:start]+'## 当前风险和准入门\n\n'+limits+'\n\n'+next_task+'\n\n固定代表性动作不证明任意策略安全；力矩／穿透峰值作用单列。保护失败如物理有效且停稳，仍按有效失败保留；进程退出不等于物理停稳。\n\n'+t[end:]
            t=section(t,'## 下一项交付',next_task+'\n\n'+cost+'\n\n'+links)
            t+='\n### 2026-10-09｜B2-SCOPE-09联合点预检候选实现与离线验收\n\n'+summary+'\n\n'+cost+'\n\n'+limits+'\n\n'+next_task+'\n\n'+links+' 最终校验见verification.json。同步[10月滚动月报](deliverables/monthly_progress/2026-10/月报素材_2026-10.md)，可交付阶段结束暂停汇报。\n'
        elif name=='项目交付总览.md':
            h='## 快速查找\n\n';assert h in t
            t=t.replace(h,h+'当前实现见[B2-SCOPE-09]('+rel+'/接入与验收说明.md)；执行申请未授权。'+next_task+'\n\n',1)
            t=t.replace('当前方案见[B2-SCOPE-08准入设计]','前轮方案见[B2-SCOPE-08准入设计]',1)
            entry='### B2-SCOPE-09｜联合点预检候选实现与离线验收（2026-10-09）\n\n'+summary+'\n\n'+cost+'\n\n使用：先读接入说明；离线check-only可核对绑定。执行申请本身不是grant；旧授权不能复用，同候选不可重复消费。\n\n'+limits+'\n\n'+links+'\n\n'
            t=t.replace('## 基线与接口交付\n\n','## 基线与接口交付\n\n'+entry,1)
        elif name=='研究推进计划_当前版.md':
            start=t.index('### B.2 小规模学习与评价包');end=t.index('\n1. 先在',start)
            t=t[:start]+'### B.2 小规模学习与评价包\n\n2026-10-09执行优先级更新：'+summary+' '+cost+' '+next_task+' 以下原要求保留，完整B.2/C未验收。\n'+t[end:]
        elif name.startswith('deliverables/'):
            parts={
                '## 一、本月综合摘要':'截至本轮B2-SCOPE-09：'+summary+' '+cost+'\n\n下一步是明确新授权后的定向物理预检；当前尚未执行。以下保留前轮证据：',
                '## 二、关键数字与证据':f'| 本轮B2-SCOPE-09项目 | 已完成／未执行提案 |\n|---|---|\n| 离线测试 | {tests["tests"]}项通过，引擎／学习导入拒绝门 |\n| 旧真实档案回归 | J01_script，4834周期／4835观测，50接触作用周期 |\n| A／B全局动作周期 | 408／816周期，含50和1周期保持块 |\n| 新物理／学习 | 全0，实际累计225 |\n| 拟新动态／单独静态 | 12／0，未授权、未执行 |\n| 拟合计子步／整体墙钟 | 1740000／6小时 |\n| 237 | 仅将来全部执行的累计上限 |\n\n'+links+'\n\n以下为前轮数字：',
                '## 三、负结果与限制':limits+'\n\n当前没有新回合可证明±1动作边界或联合姿态真实恢复通过；纯逻辑状态替身只核对代码路径。预计耗时仍为旧样本外推。以下保留前轮时点：',
                '## 四、图表与讲稿':f'本轮采用[程序／证据／预算表]({rel}/接入与验收说明.md)。讲稿：“仍在B.2，联合点预检程序已实现并通过离线检查。既有真实档案只读回归一致，但不能充当新覆盖。当前累计225，新拟12项尚未授权、未执行；先实测补动作与恢复缺口，之后才讨论匹配训练。”\n\n以下保留前轮讲稿：'}
            for h,b in parts.items():assert t.count(h)==1;t=t.replace(h+'\n',h+'\n\n'+b+'\n',1)
            t=section(t,'## 五、下一项',next_task+'\n\n'+cost+'\n\n'+limits)
            t+='\n### 2026-10-09｜B2-SCOPE-09实现与离线验收来源\n\n'+summary+'\n\n'+cost+'\n\n'+limits+'\n\n'+links+' 无新物理样本、学习结果或独立评价。\n'
        updated[name]=t
    for name,text in updated.items():(ROOT/name).write_text(text,encoding='utf-8')
    after={}
    for name in DOCS+['AGENTS.md']:
        dst=OUT/'document_snapshots'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst);after[name]=sha(dst)
    write(OUT/'document_update.json',dict(stage_id='B2-SCOPE-09',after_documents=after,rolling_documents_may_advance=True))
    print('Updated five rolling documents and six immutable after snapshots.')
if __name__=='__main__':main()
