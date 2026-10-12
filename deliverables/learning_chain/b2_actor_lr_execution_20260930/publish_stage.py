"""Maintain the same three rolling documents after monitored protocol acceptance."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT=Path(__file__).resolve().parents[3];HERE=Path(__file__).resolve().parent
STAGE='deliverables/learning_chain/b2_actor_lr_execution_20260930'
MARK='actor率对照执行适配与协议准备（2026-09-30）'

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def save(name,value):
    data=((json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2) if not isinstance(value,str) else value)+'\n').encode('utf-8')
    path=HERE/name
    if path.exists() and path.read_bytes()!=data:raise ValueError('Published evidence already exists: '+name)
    if not path.exists():path.write_bytes(data)
def verify(mapping):
    for rel,pin in mapping.items():assert sha(ROOT/rel)==pin,rel

r=read(HERE/'final_protocol_results.json');n=r['tests']
assert n>=200 and r['exit_code']==r['failures']==r['errors']==0 and not any(r['forbidden_call_counts'].values())
assert sha(HERE/'final_protocol.xml')==r['report_sha256']
assert read(HERE/'review.json')['important_remaining']==0
verify(read(HERE/'protected_before.json'));verify(read(HERE/'parent_files.json'))
old=ROOT/'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929';sealed=read(old/'sealed_files.json');verify(sealed)
mapping=read(ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930/parent_source_snapshots.json')
for rel,pin in read(old/'candidate.json')['source_sha256'].items():assert sha(ROOT/mapping.get(rel,rel))==pin
assert subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()=='feature/dsub9-dynamic-actuator-v1'
assert 'status = "PAUSED"' in Path('C:/Users/ok everything/.codex/automations/b-2/automation.toml').read_text(encoding='utf-8')
assert not (HERE/'authorization.json').exists() and not (HERE/'run').exists()
sources={p.relative_to(ROOT).as_posix():sha(p) for folder in ('tools','tests','docs/stage_b')
    for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
save('assessment.json',dict(status='execution_protocol_preparation_accepted',date='2026-09-30',tests=n,
    monitored_actual_calls=r['forbidden_call_counts'],current_sources=len(sources),protected_original_sources=286,
    protected_parent_artifacts=len(read(HERE/'parent_files.json')),old_sealed_files=len(sealed),inherited_original_source_bytes=929,
    execution_adapter_implemented=True,protocol_checks_passed=True,real_validation_passed=False,
    a_learning_reproduced=False,user_execution_authorized=False,training_launched=False,policy_effect_validated=False,
    old_unused_dynamic=19,old_unused_batches=2000,old_unused_consumed=0,automatic_tracking='PAUSED',b2_complete=False))
save('README.md',f'''# B.2 actor率对照执行适配与协议准备

2026-09-30。沿用指定工作树及feature/dsub9-dynamic-actuator-v1，保留全部原修改。本项接通执行代码并验收纯协议；**尚未运行真实数值验证、A学习复现、训练或物理评价，也没有证明修复有效。B.2未完成。**

## 已接通的路径

- [显式分支与授权合同](../../../tools/learning/actor_lr_contract.py)：A actor=3e-4，B=3e-5，critic/温度=3e-4。共同输入为[严格origin_v2](../b2_actor_lr_origin_20260930/origin_v2/manifest.json)的四预热22766行及固定500批抽样。不追加训练采集，不更改奖励、阈值、幅度、域或种子。
- [独立持久账本](../../../tools/learning/actor_lr_budget.py)：先刷盘预约再采样/计算；异常尝试仍计费、不重试。恢复校验阶段、门、顺序、逐条成本及终结结果；拒绝其它候选/授权和过期内存覆盖新账本。
- [离线学习与完整恢复](../../../tools/learning/actor_lr_engine.py)：完整来源、边界索引、网络、三个Adam、温度、计数、随机流、历史和分支绑定。A500批必须逐值复现旧train_03，只有身份和墙钟耗时排除；不符停止，B不能绕过。固定B500后冻结，不挑选中间策略。
- [真实验证与评价适配](../../../tools/learning/actor_lr_execution.py)：未来先运行4个私有事务和8个测试状态前向，覆盖独立actor率、无权限屏蔽、注入回滚、保存恢复/跨分支拒绝。全部通过后才A→B；随后对相同256状态做initial/A/B分布诊断共768状态，无额外critic。各固定检查点在新进程恢复，A四点结束才B四点；任意保护完整归档停稳后停止整轮，普通任务失败保留。
- [监督入口](../../../tools/validation/run_actor_lr_comparison.py)：授权先于runtime/模型/claim；登记父进程与独占启动。持续检查直接父、祖先监督者、全轮停止请求及持久账本。监督树停止不能确认时保留账本、记录未收口，不能冒称已停止或重置成本。

## 验证与负记录

最终统一{n}项协议检查全过，见[结果](final_protocol_results.json)、[JUnit](final_protocol.xml)、[阶段验收](assessment.json)；监控模型前向/Adam.step/原生物理均0。包含前项133项范围及本项拒绝/恢复/执行次序反例，历史和中间运行不能相加。实际SAC全量数值与物理检查因预算尚未批准而没有运行；模拟站位不能当真实学习证据。

独立审查发现的阶段造假、授权错配、A/B键错配、边界索引遗漏、阶段回退、监督未收口与祖先停止、诊断摘要缺口均修正，相关红/绿记录留存，见[审查](review.md)。首个测试命令使用了不存在的解释器路径，改为原CPU环境后运行；没有计算或改环境。原286源、{len(read(HERE/'parent_files.json'))}前项产物、4149旧封存和929旧源码原字节保持。

## 执行门与预算申请

[candidate.json](candidate.json)是协议准备候选；[摘要](candidate_pin.json)、[预检](preflight.json)、[未批准申请](authorization_request.json)随后封存。它明确real_validation_required=true。没有authorization.json、没有run目录，不以协议准备代替真实验证资格。

只读检查命令：在本工作树，用`tmp/learning_cpu_20260924/Scripts/python.exe -X utf8 -B -m tools.validation.run_actor_lr_comparison --candidate-sha256 <candidate_pin.json中的摘要> --verify-only`。该模式不执行模型或物理，也不授予计算权。

真实启动须单独批准新候选及上限：合成事务最多16、测试状态前向最多128（当前计划实际4/8），分布诊断768状态、A/B正式各500批、各四点最多8动态，既有57加本项最多65；每回合13000周期看门狗。全部门通过也只形成早期开发筛选，B须保持原初始4/4，优于退化A不足以称恢复；不能证明2500批在线危险状态问题已修复或独立泛化。

**旧余19次/2000批不结转、不执行；自动跟踪PAUSED。** 真实计算未批准，按项目阶段约定本项汇报后暂停。原三份滚动文档已同步；历史包、合同和阈值保持。
''')
summary=f'**{MARK}：** [执行适配]({STAGE}/README.md)已接通版本化A/B、独立持久账本、完整检查点、新进程冻结评价及真实验证前置代码；{n}项最终纯协议全过、实际前向/优化/物理0。审查发现的阶段/授权/恢复/监督/诊断门缺口已补反例并修正。原286源、前项产物、4149封存与929旧源码原字节保持。协议准备已验收，真实数值验证与A500学习复现尚未运行，效果未验证，B.2未完成；旧余19/2000不结转、跟踪PAUSED。新计算申请见[清单]({STAGE}/authorization_request.json)，需单独批准。'
progress=ROOT/'项目进度跟踪.md';text=progress.read_text(encoding='utf-8')
assert MARK not in text
pos=text.index('**四预热共同起点重建');text=text[:pos]+summary+'\n\n'+text[pos:]
lines=text.splitlines()
for i,line in enumerate(lines):
    if line.startswith('| B.2 小规模'):
        lines[i]=f'| B.2 小规模学习与评价包 | 待验收；actor率执行协议准备已验收，效果未验证 | [执行适配]({STAGE}/README.md)、[最终{n}项]({STAGE}/final_protocol_results.json)；严格四预热/500抽样沿用、实际计算0 | 新真实数值验证、A精确复现与A/B固定评价待单独预算批准；旧余19/2000不执行，最终/恢复/独立研究验收尚缺 |'
    elif line.startswith('| 6 普通残差SAC'):
        lines[i]=f'| 6 普通残差SAC | 原轮13动态/2500批受控停止保持；独立actor率、严格22766行共同起点与500抽样、完整执行/恢复/预算/监督适配已实现，{n}协议通过；真实前向/更新/物理0，A学习未复现、效果未验证，B.2未完成 |'
    elif line.startswith('| 单变量与有限对照可比性'):
        lines[i]='| 单变量与有限对照可比性 | 严格共同起点/抽样保持；版本化执行适配、独立账本、恢复与监督协议通过，实际学习未复现 | 单独批准后先真实数值验证及A精确复现；不符停止、不启动B；任何评价保护停止整轮，不能据代码通过宣称效果 |'
    elif line.startswith('| 原项目全量测试'):
        lines[i]=f'| 原项目全量测试 | 本阶段{n}项指定纯协议通过，监控前向/Adam.step/物理0 | 未运行真实数值或物理全量矩阵；协议/模拟次序不能当学习、恢复物理效果或研究收益通过，历史数字不相加 |'
text='\n'.join(lines)+'\n'
start=text.index('## 下一项交付');end=text.index('## 追加式阶段记录',start)
text=text[:start]+f'''## 下一项交付

[本阶段执行准备]({STAGE}/README.md)已验收；下一项单独批准[新预算申请]({STAGE}/authorization_request.json)后，依次真实数值验证→A500精确学习复现→B500→768固定状态分布诊断→最多8次冻结开发评价。A不符、运行/写盘/输入故障即止，任何评价保护完成停稳归档后停止整轮，不补足、不扩额、不续用旧19/2000。真实验证、学习和物理尚未执行，自动跟踪PAUSED。

仅actor3e-4→3e-5；B须保持原初始4/4能力，不能以优于退化A冒称恢复。500批固定数据筛选不证明2500批在线问题已解决，后续交互、正式恢复与独立评价另立研究阶段和预算。

'''+text[end:]
record=f'### 2026-09-30 B.2｜actor率对照执行协议准备\n\n- 用户继续授权范围内的执行适配；新增5生产/入口模块及5测试文件，全部旧修改保留。\n- 版本化候选/独立预算、固定数据学习、完整分支恢复、真实测试和冻结评价入口接通，保护/错误不重试。\n- 最终{n}项纯协议通过，实际模型前向/Adam.step/物理0；审查缺口与红/绿负记录见[交付]({STAGE}/README.md)、[审查]({STAGE}/review.md)。\n- [验收]({STAGE}/assessment.json)，原286源/前项产物/4149封存/929原源码保持；[9月滚动月报](deliverables/monthly_progress/2026-09/月报素材_2026-09.md)同步。真实数值/A复现/收益未验证，旧余19/2000与PAUSED保持，B.2未完成；阶段交付后汇报暂停，计算另批。\n\n'
text=text.replace('## 追加式阶段记录\n\n','## 追加式阶段记录\n\n'+record,1);progress.write_text(text,encoding='utf-8')
overview=ROOT/'项目交付总览.md';text=overview.read_text(encoding='utf-8');pos=text.index('| 四预热共同起点')
text=text[:pos]+f'| {MARK} | [执行入口与用法]({STAGE}/README.md)、[{n}项]({STAGE}/final_protocol_results.json)、[验收]({STAGE}/assessment.json) | 完整离线A/B、预算/监督/恢复/诊断/评价适配已接通；真实验证/A复现/效果未运行，预算另批 |\n'+text[pos:]
text=re.sub(r'^\| 下一候选改哪里.*$',f'| 下一候选改哪里、有限对照如何限制成本 | [执行准备]({STAGE}/README.md)、[独立预算申请]({STAGE}/authorization_request.json) | 仅actor率改变；严格共同起点与执行协议通过，真实数值/A复现未过，1000批/8动态及额外测试/诊断未授权 |',text,flags=re.M)
text+='\n### 2026-09-30｜actor率对照执行协议准备\n\n'+summary+'\n\n使用方式、门禁与新预算见上述README。该能力扩展原B2学习/恢复工程入口，不新增研究收益或B.2验收；自动跟踪继续暂停。\n';overview.write_text(text,encoding='utf-8')
monthly=ROOT/'deliverables/monthly_progress/2026-09/月报素材_2026-09.md';text=monthly.read_text(encoding='utf-8')
ms=summary.replace(STAGE,'../../learning_chain/b2_actor_lr_execution_20260930')
text=text.replace('## 一、可直接用于汇报的本月总结\n\n','## 一、可直接用于汇报的本月总结\n\n'+ms+'\n\n',1)
text=text.replace('## 二、按主题整理的成果与关键证据\n\n',f'## 二、按主题整理的成果与关键证据\n\n本阶段关键数字：{n}最终协议检查、286原源/4149旧封存/929历史原字节保持；新实际前向/优化/物理均0。新增计算申请上限16合成事务/128测试状态、768诊断状态、1000正式批/8动态，现均未批准、不计已完成实验。\n\n',1)
text=text.replace('## 三、必须保留的问题与负结果\n\n','## 三、必须保留的问题与负结果\n\n本阶段负记录：审查揭示账本阶段造假/回退、授权与分支错配、恢复字段遗漏、诊断可替换及监督未收口/祖先停止风险，已补拒绝反例并修正。首次测试解释器路径不存在，纠正后继续。它们是执行协议缺口，不能据修复推断原策略效果改善；真实数值和A学习尚未验证。\n\n',1)
text=text.replace('## 五、两分钟讲稿（截至本次整理）\n\n',f'## 五、两分钟讲稿（截至本次整理）\n\n最新讲稿：“我们接通了仅降低actor学习率的严格共同起点对照执行入口，{n}项纯协议通过且没有新增真实计算。执行与恢复门、预算和停止链已补齐；下一步在单独批准的新预算下先验证数值实现、复现原学习率A，再看B能否保持原初始四点能力。现在不能说危险价值偏差或策略效果已经修好。”\n\n',1)
text=text.replace('## 六、下一步素材需求\n\n','## 六、下一步素材需求\n\n最新：执行协议准备已完成，真实数值/A复现与有限A/B未批准；下次若实际通过才补分布和固定开发任务图。本阶段无新学习曲线/性能图，仍注明历史图日期和已批准计算来源。\n\n',1)
text=text.replace('## 七、阶段增量与来源追溯\n\n','## 七、阶段增量与来源追溯\n\n'+ms+'\n\n',1)
monthly.write_text(text,encoding='utf-8')
for path in (progress,overview,monthly):
    rel=path.relative_to(ROOT);target=HERE/'document_snapshot'/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
links=0
for path in (progress,overview,monthly):
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
        if '://' in target or target.startswith('#'):continue
        target=target.split('#')[0]
        if not target:continue
        resolved=(path.parent/target).resolve()
        # Candidate files are emitted next by build_candidate; verify afterward.
        if resolved in {HERE/name for name in ('candidate.json','candidate_pin.json','authorization_request.json','preflight.json')}:continue
        assert resolved.exists(),str(path)+': '+target;links+=1
save('document_verification.json',dict(local_links_before_candidate=links,updated_same_rolling_documents=3,
    source_documents_snapshotted=True,training_launched=False))
print(json.dumps(dict(tests=n,current_sources=len(sources),documents=3,local_links=links)))
