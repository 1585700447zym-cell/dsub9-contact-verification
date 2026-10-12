"""Publish verified offline implementation into existing rolling materials."""
from pathlib import Path
import re
import shutil
import sys

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
import scope_contract as c


def main():
    review=c.read(OUT/'review_resolution.json')
    if review['unresolved_critical_important']:raise ValueError('Finish substantive review fixes before publishing')
    tests=(OUT/'tests_full_final.log').read_text(encoding='utf-8')
    n=int(re.search(r'Ran (\d+) tests',tests).group(1))
    if '\nOK' not in tests or 'FAILED (' in tests:raise ValueError('Fresh full suite required')
    sources=len(c.read(OUT/'source_binding.json')['files'])
    suffix='b2_stratified_zero_baseline_entry_20261011/结果说明.md'
    monthly='deliverables/monthly_progress/2026-10/月报素材_2026-10.md'
    summary=f'独立21点纯B2评价入口已实现，{n}项新增标准库检查通过；实际初始化审计、一次性尝试、外部整包/单回合监督、完整档案及25点分层审核已接通。静态筛查不升级真实动态或非零SAC资格。'
    costs='本轮新增物理回合/模型构造/策略调用/学习器/张量/训练更新/经验发布均0，累计动态258，自动跟踪PAUSED，独立测试0，完整B.2/C未验收；真实21次物理评价未执行，无新训练准入。'
    limits='新有限物理提案：仅21个新增组合的零残差B2，各14500周期/145000子步/1200秒，全包304500周期/3045000子步/6小时；策略/学习器/张量/更新/经验池/独立测试0，重试0。授权请求保持DRAFT，旧预算不重开。'
    nxt='下一项（待开始）：取得并核对这一次21点纯B2有限物理授权，按已审阅入口检查真实复位并取得基线数据；旧4点只读复用。实际包收口后再准备冻结F0/F2000的21点分层开发评价，当前不追加同四点训练、不进入C。'
    reminder='课题主方法继续应用强化学习；纯B2是共同对照。B.2达到验收条件、准备进入C之前，主动提醒阶段性成果总结和汇总。'
    old='历史准备套件26/27通过；test_unauthorized_CLI_rejects_before_any_scientific_import的旧“execution目录不存在”断言在已执行四点评价后失败。原测试/档案保留；新入口实际CLI未授权/DRAFT拒绝及运行状态保持另行检查通过。'
    def marker(month=False):
        target=('../../learning_chain/' if month else 'deliverables/learning_chain/')+suffix
        return '\n'.join(['<!-- b2-scope-current -->','**2026-10-11｜当前阶段B.2第3项；任务：21点纯B2评价入口实现与离线核验，已完成；真实21次评价待开始。**',
            '',summary,'',f'本轮绑定{sources}份输入，共同模型/控制/裁判、旧4点范围指纹与新25点范围指纹保持；旧3处逐profile缺口不追改。','',limits,'',costs,'',nxt,'',reminder,'',
            '[入口结果与证据]('+target+')。以下历史记录保留各自时点，当前下一项以本段为准。','<!-- /b2-scope-current -->'])
    def replace_section(text,heading,body):
        start=text.index(heading+'\n')+len(heading)+1;end=text.find('\n## ',start)
        if end<0:end=len(text)
        return text[:start]+'\n'+body+'\n'+text[end:]
    docs=['项目当前入口.md','项目进度跟踪.md','研究推进计划_当前版.md','项目交付总览.md',monthly]
    for name in docs:
        path=c.ROOT/name;text=path.read_text(encoding='utf-8')
        text,count=re.subn(r'<!-- b2-scope-current -->.*?<!-- /b2-scope-current -->',lambda m:marker(name==monthly),text,count=1,flags=re.S)
        if count!=1:raise ValueError('Missing current-state marker')
        if name=='项目进度跟踪.md':
            row=next(l for l in text.splitlines() if l.startswith('| B.2 小规模学习与评价包 |'))
            text=text.replace(row,'| B.2 小规模学习与评价包 | 待验收；21点纯B2入口实现与离线核验完成 | [入口证据](deliverables/learning_chain/'+suffix+') | 下一次21点真实复位/零残差评价；SAC分层、第4/5项仍待 |',1)
            start=text.index('## 原八项任务对应\n');end=text.index('## 当前风险和准入门\n',start)
            segment=text[start:end].replace('25点针体入口筛查通过；21新点真实复位/完整碰撞/动态仍待','21点入口及离线检查完成；真实复位/完整碰撞/动态仍待').replace('25点范围21新点入口待实现','25点范围21新点入口完成，真实评价待').replace('累计258；未来仅21次零残差B2提案，DRAFT','累计258；已实现21次零残差B2入口，物理提案DRAFT')
            text=text[:start]+segment+text[end:]
            pos=text.index('## 当前风险和准入门\n')+len('## 当前风险和准入门\n')
            text=text[:pos]+'\n当前入口限制：'+costs+' '+old+'\n\n'+text[pos:]
            text=replace_section(text,'## 下一项交付',nxt+'\n\n'+limits+'\n\n'+costs+'\n\n'+reminder+'\n\n[本轮入口结果](deliverables/learning_chain/'+suffix+')、[当月月报]('+monthly+')。')
            cut=text.index('## 追加式阶段记录')
            old_next='下一项（待开始）：实现并离线核验独立21点零残差纯B2评价入口。在每个实际回合内检查初始化并取得基线数据，旧4点只读复用；入口交付后另有新有限物理授权和逐项准入才执行。随后准备冻结F0/F2000的分层开发评价，不追加原四点短训，不启动C。'
            text=text[:cut].replace(old_next,nxt)+text[cut:]
            text+='\n\n### 2026-10-11｜B.2第3项21点纯B2入口实现与离线核验\n\n'+summary+'\n\n'+costs+'\n\n'+old+'\n\n验收仅本次离线入口能力；Windows嵌套作业树、真实初始化/停止及新点效果须在新21次实际包内验证。'+nxt+'\n\n证据：[结果](deliverables/learning_chain/'+suffix+')、[核验](deliverables/learning_chain/b2_stratified_zero_baseline_entry_20261011/verification.json)、[审查处理](deliverables/learning_chain/b2_stratified_zero_baseline_entry_20261011/review_resolution.json)、[滚动月报]('+monthly+')。\n'
        elif name=='研究推进计划_当前版.md':
            for heading in ['## 研究目标和保留架构','### B.2 小规模学习与评价包']:
                pos=text.index(heading+'\n')+len(heading)+1
                text=text[:pos]+'\n2026-10-11当前入口交付：'+summary+' '+costs+'\n\n'+nxt+'\n\n'+reminder+'\n\n以下离线范围准备及此前记录保留历史时点：\n'+text[pos:]
        elif name=='项目交付总览.md':
            pos=text.index('## 基线与接口交付\n')+len('## 基线与接口交付\n')
            body='\n### B.2第3项21点纯B2入口实现与离线核验｜2026-10-11\n\n'+summary+'\n\n成果/使用：[结果](deliverables/learning_chain/'+suffix+')、[入口](deliverables/learning_chain/b2_stratified_zero_baseline_entry_20261011/baseline_entry.py)、[未来DRAFT请求](deliverables/learning_chain/b2_stratified_zero_baseline_entry_20261011/authorization_request.json)、[核验](deliverables/learning_chain/b2_stratified_zero_baseline_entry_20261011/verification.json)、[审查处理](deliverables/learning_chain/b2_stratified_zero_baseline_entry_20261011/review_resolution.json)。`baseline_entry.py --check`仅标准库核对来源；`--execute`须单独匹配新授权，DRAFT/缺授权会拒绝，不能重试已存在execution。\n\n'+old+'\n\n'+limits+'\n\n'+costs+' '+reminder+'\n\n'+nxt+'\n'
            text=text[:pos]+body+text[pos:]
        elif name==monthly:
            inserts={
                '## 一、本月综合摘要':'**本轮入口实现交付：** '+summary+' '+costs+' '+nxt+'\n\n以下此前离线范围及四点结果保留：',
                '## 二、关键数字与证据':f'| 本轮入口项 | 结果 |\n|---|---|\n| 新标准库检查 | {n}项通过 |\n| 绑定输入 | {sources}份，含数值文件和新封装 |\n| 旧准备套件 | 26/27；1项旧目录时点假设失败，保留 |\n| 拟新物理/实际物理 | 21 / 0 |\n| 实际推理/更新/经验 | 0 / 0 / 0 |\n| 当前累计/自动跟踪 | 258 / PAUSED |\n\n以下此前数字保留：',
                '## 三、负结果与限制':old+'\n\n新入口离线通过不代表21点动态成功或非零SAC范围准入；嵌套Windows监督、初始化、载荷/穿透、停止和逐点结果仍待实际包验证。完整B.2/C未验收，原3覆盖缺口及单种子限制保留。以下此前限制保留：',
                '## 四、图表与讲稿':'本轮展示[入口、检查与有限执行表](../../learning_chain/'+suffix+')；没有新物理性能曲线。讲稿：“当前是B.2第3项，21点纯B2入口实现和离线检查完成，但真实21次尚未执行。下一包在每个回合内检查复位并取得共同基线，再做冻结SAC分层对照；进入C前汇总B.2成果。”\n\n以下此前图表讲稿保留：'}
            for heading,body in inserts.items():text=text.replace(heading+'\n',heading+'\n\n'+body+'\n',1)
            text=replace_section(text,'## 五、下一项',nxt+'\n\n'+limits+'\n\n'+costs+'\n\n'+reminder+'\n\n[本轮入口结果](../../learning_chain/'+suffix+')。')
            text+='\n\n2026-10-11｜B.2第3项21点纯B2入口交付：[结果](../../learning_chain/'+suffix+')、[检查](../../learning_chain/b2_stratified_zero_baseline_entry_20261011/verification.json)、[审查处理](../../learning_chain/b2_stratified_zero_baseline_entry_20261011/review_resolution.json)。'+summary+' '+costs+' '+old+'\n'
        path.write_text(text,encoding='utf-8')
    for name in ['AGENTS.md']+docs:
        dest=OUT/'after_documents'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(c.ROOT/name,dest)
    shutil.copyfile(c.ROOT/'docs/superpowers/plans/2026-10-11-b2-stratified-zero-baseline-entry.md',OUT/'入口实现计划快照.md')
    c.write(OUT/'document_update.json',dict(status='INTEGRATED',files=docs,monthly_sections=5,AGENTS_modified=False))
    print('Five rolling documents and six snapshot pairs updated.')


if __name__=='__main__':main()
