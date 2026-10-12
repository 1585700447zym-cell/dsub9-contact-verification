"""Publish only after strict reconstruction and the final monitored tests pass."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
ORIGIN = HERE / 'origin_v2'
OLD = ROOT / 'deliverables/learning_chain/b2_atomic_repaired_cycle_20260929'
STAGE = 'deliverables/learning_chain/b2_actor_lr_origin_20260930'
MARK = '四预热共同起点重建（2026-09-30）'


def read(p):
    return json.loads(p.read_text(encoding='utf-8'))


def sha(p):
    with p.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def save(name, value):
    p = HERE / name
    data = ((json.dumps(value,ensure_ascii=False,allow_nan=False,indent=2) if not isinstance(value,str) else value)+'\n').encode('utf-8')
    if p.exists() and p.read_bytes() != data:
        raise ValueError('Do not overwrite published evidence: ' + name)
    if not p.exists():
        p.write_bytes(data)


result = read(HERE / 'final_strict_results.json')
assert result['tests'] == 133 and result['exit_code'] == result['failures'] == result['errors'] == 0
assert not any(result['forbidden_call_counts'].values())
assert sha(HERE / 'final_strict.xml') == result['report_sha256']
cases = list(ET.parse(HERE/'final_strict.xml').getroot().iter('testcase'))
assert len(cases) == 133 and all(not list(c) for c in cases)
manifest, rebuilt = read(ORIGIN/'manifest.json'), read(ORIGIN/'assessment.json')
assert rebuilt['status'] == 'common_origin_reconstructed_no_execution'
assert all(rebuilt[k] is True for k in ('prefix_3_warmup_exact', 'four_warmup_data_and_rng_exact',
    'warmup_requests_exact', 'empty_initial_weights_adam_temperature_torch_rng_exact',
    'draws_500_boundary_history_and_final_rng_exact', 'fork_only_actor_rate_and_identity_differ',
    'fork_mutable_storage_disjoint', 'save_load_exact', 'global_torch_rng_unchanged'))
assert rebuilt['a_500_learning_reproduced'] is rebuilt['qualification_issued'] is rebuilt['training_launched'] is rebuilt['policy_effect_validated'] is False
assert rebuilt['model_forward_calls'] == rebuilt['optimizer_step_calls'] == rebuilt['physics_calls'] == 0
assert sha(ORIGIN/'state.pt') == manifest['state_sha256']
assert sha(ORIGIN/'draw_plan.json.gz') == manifest['draw_plan_sha256']
assert sha(ORIGIN/'source_sha256.json') == manifest['source_manifest_sha256']
sources = read(ORIGIN/'source_sha256.json')
assert len(sources) == 286
for rel,pin in sources.items():
    assert sha(ROOT/rel) == pin, rel
actual_sources = {p.relative_to(ROOT).as_posix() for folder in ('tools','tests','docs/stage_b')
    for p in (ROOT/folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
assert actual_sources == set(sources)
intermediate_sources = read(HERE/'origin/source_sha256.json')
for rel,pin in intermediate_sources.items():
    path = HERE/'pre_strict_source_snapshots'/rel if rel == 'tools/learning/actor_lr_origin.py' else ROOT/rel
    assert sha(path) == pin, rel
before = read(HERE/'protected_before.json')
assert len(before) == 283
for rel,pin in before.items():
    assert sha(ROOT/rel) == pin, rel
parent_files = read(HERE/'parent_files.json')
for rel,pin in parent_files.items():
    assert sha(ROOT/rel) == pin, rel
sealed = read(OLD/'sealed_files.json')
for rel,pin in sealed.items():
    assert sha(ROOT/rel) == pin, rel
for rel,pin in manifest['archived_inputs_sha256'].items():
    assert sha(ROOT/rel) == pin == sealed[rel], rel
parent = ROOT/'deliverables/learning_chain/b2_actor_lr_implementation_20260930'
mapping = read(parent/'parent_source_snapshots.json')
candidate = read(OLD/'candidate.json')
for rel,pin in candidate['source_sha256'].items():
    assert sha(ROOT/mapping.get(rel,rel)) == pin, rel
branch = subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip()
assert branch == 'feature/dsub9-dynamic-actuator-v1'
automation = Path('C:/Users/ok everything/.codex/automations/b-2/automation.toml')
assert 'status = "PAUSED"' in automation.read_text(encoding='utf-8')
assert read(OLD/'stop_assessment.json')['unused_dynamic_starts'] == 19
assert read(OLD/'stop_assessment.json')['unused_formal_batches'] == 2000
assert (HERE/'review.md').is_file()
save('assessment.json', dict(status='common_origin_preparation_accepted',date='2026-09-30',branch=branch,
    tests=133, failures=0, errors=0, monitored_actual_calls=result['forbidden_call_counts'],
    reconstruction_manifest_sha256=sha(ORIGIN/'manifest.json'), state_sha256=manifest['state_sha256'],
    source_manifest_sha256=manifest['source_manifest_sha256'], current_sources=286,
    protected_original_sources=283, protected_parent_artifacts=len(parent_files), old_sealed_files=len(sealed),
    inherited_original_source_bytes=len(candidate['source_sha256']), replay_rows=22766,
    reconstruction_complete=True, a_learning_reproduced=False, actual_update_validated=False,
    execution_adapter_complete=False, qualification_issued=False, training_launched=False, policy_effect_validated=False,
    old_unused_dynamic=19, old_unused_batches=2000, automatic_tracking='PAUSED',b2_complete=False))
save('README.md', '''# B.2 四预热共同起点重建

2026-09-30，用户要求“继续”后，沿用指定工作树及feature/dsub9-dynamic-actuator-v1完成无新增执行预算的共同起点重建。本阶段只新增重建模块和2个测试文件；原283项源码/测试/冻结资料保持，不改旧合同、配置、实验或清单。

## 获得什么

[重建模块](../../../tools/learning/actor_lr_origin.py)从已封存的初始完整检查点及train_00～03归档，构造**四预热、零更新、22,766行经验**的共同状态。保留初始网络、空Adam、温度、torch随机状态、回放、边界标签、审核收据与全部随机流。整份原物理记录通过既有FORCE_ONLY规则重新审核，没有重新执行物理。

- 初始模型/优化器/温度/torch RNG与锁定初始化逐值一致；与train_02三预热零更新状态的原模型及数据前缀一致。
- 四预热数据、收据、warmup RNG与train_03已500批检查点一致；不借用其学习后权重、Adam或温度。22,766个四维原始随机请求逐值吻合，包含无权限阶段。
- 固定未来500批抽样，每批actor均匀256行、critic前240行加16边界；边界抽样序列与历史500批记录一致，最终replay/boundary RNG一致。没有执行梯度、更新或学习复现。
- A/B深拷贝只有actor学习率与身份不同，网络及回放张量存储不共享；共同状态序列化回读逐值一致，全局torch RNG未改变。

## 当前有效材料

| 内容 | 入口 | 用途与限制 |
|---|---|---|
| 完整共同状态 | [严格版state.pt](origin_v2/state.pt)、[外部摘要清单](origin_v2/manifest.json) | 重建数据产物；不是获准的执行检查点 |
| 固定500批抽样 | [draw_plan.json.gz](origin_v2/draw_plan.json.gz) | 同序列输入；不代表学习权重已复现 |
| 分支与当前源 | [A](origin_v2/branch_binding_A.json)、[B](origin_v2/branch_binding_B.json)、[286项清单](origin_v2/source_sha256.json) | 准备身份；没有新执行资格 |
| 重建证据 | [实际核对](origin_v2/assessment.json)、[阶段验收](assessment.json)、[最终核验](verification.json) | 旧数据审核/状态/抽样验收，效果未验证 |
| 测试与审查 | [133项最终结果](final_strict_results.json)、[JUnit](final_strict.xml)、[审查](review.md) | 指定纯协议子集；模型前向/Adam.step/物理调用0 |

[严格重建入口](build_origin.py)采用相同修复版MuJoCo及锁定CPU依赖，先核对所有输入摘要，主动阻断前向、Adam.step和物理。该脚本已生成origin_v2，重复执行会拒绝覆写；后续使用已锁定产物，不应再次生成以替代它。准备类型及原资格不能启动本对照。

## 验证与负记录

新增28项先红后绿；首次合并129项通过。独立审查指出归档请求先降为float32可能掩盖小于半ULP的差异，已添加4项反例，先红后绿，改为直接比较原归档数值。严格版本重新构造并另存origin_v2，原origin和中间记录保留；修改前重建源码也按中间清单的SHA256核验留存，避免旧版本失去字节追溯。最终统一133项全过（208.95秒）。它们是同一检查范围不同运行，不能相加。

初次只读检查曾使用错误的历史检查点相对目录，在读取第二份文件时失败，纠正路径后通过，物理/前向/优化0。初始28项红记录误经前项runner写在前项目录，原文件没有覆盖；同字节结果复制本目录保存，本阶段其余运行改用独立入口。前项39个既有产物及4149旧封存文件字节保持。

## 未完成与下一项

**共同起点和抽样已核验，A支500批学习仍未复现，策略效果未知，B.2未完成。** 没有真实前向、Adam.step或动态仿真，没有发行新资格/授权或恢复自动跟踪。torch.load仅读取已校验的本地字节，状态构造/保存不是新训练。

下一项是接通版本化对照执行入口、分支恢复和独立持久预算账本，并提交真实实现验证及A/B清单。实际最多16个合成事务、128测试状态前向、768诊断actor状态前向，以及1000正式批/最多8动态仍待单独批准。A学习复现不符即停止，B不能绕过；评价任何保护完成停稳归档后停止，不自动补足缺失点。

旧余19次/2000批不结转、不执行，自动跟踪PAUSED。500批筛选仍须保持初始4/4能力，不能证明原2500批在线问题已修复；最终开发、真实恢复和独立评价尚缺。
''')


def insert(text, anchor, value):
    assert text.count(anchor) == 1, anchor
    return text.replace(anchor, anchor+value,1)


def line(text, prefix, new):
    parts = text.splitlines(keepends=True)
    positions = [i for i,p in enumerate(parts) if p.startswith(prefix)]
    assert len(positions) == 1, prefix
    parts[positions[0]] = new+'\n'
    return ''.join(parts)


def update(path, transform):
    p = ROOT/path
    text = p.read_text(encoding='utf-8')
    if MARK in text:
        raise ValueError('Stage already published; do not duplicate rolling entry')
    text = transform(text)
    p.write_bytes(text.replace('\n','\r\n').encode('utf-8'))
    snapshot = HERE/'document_snapshot'/path
    snapshot.parent.mkdir(parents=True,exist_ok=True)
    with snapshot.open('xb') as stream:
        stream.write(p.read_bytes())


def progress(text):
    text = insert(text,'## 当前状态\n\n',f'**{MARK}：** [严格版共同起点]({STAGE}/README.md)已完成：初始完整学习状态和四份预热重审构造22766行回放/边界、空Adam/温度、全部随机流；与三预热零更新及四预热500批归档交叉核对，22766原请求精确一致。500批固定抽样/历史边界序列及最终随机流一致，但A支学习尚未复现。133项最终纯协议通过、独立审查精度问题已修正，实际模型前向/优化/物理0；原283资料及39前项产物、4149旧封存文件保持，当前286项另绑定。共同起点准备已验收，不是执行资格或策略效果；执行入口/新预算账本尚缺，真实计算未授权，旧余19/2000与跟踪PAUSED保持，B.2未完成。\n\n')
    text = line(text,'| B.2 小规模学习与评价包 |',f'| B.2 小规模学习与评价包 | 待验收；actor率实现和严格共同起点准备已验收，效果未验证 | [修复实现](deliverables/learning_chain/b2_actor_lr_implementation_20260930/README.md)、[共同起点]({STAGE}/README.md)；133项协议通过、实际前向/优化/物理0 | 新执行入口/账本/资格、A支学习复现及最终/恢复/独立评价尚缺；旧余19/2000不执行，拟议真实验证与1000批/8动态另批 |')
    text = line(text,'| 6 普通残差SAC |','| 6 普通残差SAC | 原轮13动态/2500批后三次力保护停止、旧余19/2000不执行；actor独立率已实现，22766行共同起点与500抽样/随机流已重建核对，133纯协议通过。A支学习未复现，新执行入口/资格尚缺；真实前向/优化/物理0，效果未验证，B.2未完成 |')
    text = line(text,'| 单变量与有限对照可比性 |','| 单变量与有限对照可比性 | 四预热/零更新完整状态、A/B存储隔离及500抽样已核对；历史训练结果还未复现 | 先接通新执行适配、恢复与独立预算账本/资格；真实测试和A学习复现另批，不符停止，不用旧资格或补跑预热 |')
    text = line(text,'| 原项目全量测试 |','| 原项目全量测试 | 本阶段133项指定纯协议通过；严格重建全轨迹/输入/随机流核对，监控前向/Adam.step/物理0 | 未运行真实学习或物理全量矩阵；状态/抽样核对不代表梯度、学习恢复或效果通过，不与中间/历史测试数相加 |')
    text = insert(text,'## 下一项交付\n\n',f'共同起点重建已完成，当前可用资料见[严格版交付]({STAGE}/README.md)。下一项接通版本化对照执行入口、完整分支恢复与独立持久预算账本；再提交新资格和真实计算清单供单独启动批准。A支500批学习必须先精确复现，不符停止；正式A/B1000批/最多8动态及额外16合成事务、128测试状态前向、768诊断actor状态前向均尚未批准。旧余19/2000与自动跟踪暂停保持。下文保留前项建议来源。\n\n')
    text = text.replace('单独actor学习率与纯协议准备已完成，见[验收](deliverables/learning_chain/b2_actor_lr_implementation_20260930/assessment.json)。下一项为新执行适配、完整同起点重建与状态验证，','前项单独actor学习率与纯协议准备已完成，见[验收](deliverables/learning_chain/b2_actor_lr_implementation_20260930/assessment.json)。其中完整同起点重建现已由本阶段完成；剩余新执行适配与真实状态验证，')
    return insert(text,'## 追加式阶段记录\n\n',f'### 2026-09-30 B.2｜严格四预热共同起点重建\n\n- 用户要求继续；原283源保持，新添重建模块和2测试。锁定初始/三预热/四预热三个检查点与四预热归档/收据共14输入，构造22766行、500信用的零更新状态，完整回放/边界/随机流保存回读一致。\n- 22766个原请求逐值一致；500抽样边界序列与最终随机流一致，A/B深拷贝只actor率/身份不同且存储不共享。A实际学习尚未复现。\n- 首28项红后绿，129中间回归通过；审查指出先降精度风险，4反例红后绿，另存origin_v2保留原记录。[133最终]({STAGE}/final_strict_results.json)通过、真实前向/优化/物理0；初始检查路径错误及红证据输出位置失误保留，不影响旧字节。\n- [交付]({STAGE}/README.md)、[验收]({STAGE}/assessment.json)；39前项产物、4149旧封存与929旧源码原字节保持，286当前源另绑定。原三份滚动资料/[9月月报](deliverables/monthly_progress/2026-09/月报素材_2026-09.md)同步；B.2未完成，旧余19/2000与PAUSED保持。按阶段约定汇报，下一项为执行入口/账本/资格，真实计算另批。\n\n')


def overview(text):
    text = insert(text,'|---|---|---|\n',f'| {MARK} | [严格版起点]({STAGE}/README.md)、[133项]({STAGE}/final_strict_results.json)、[验收]({STAGE}/assessment.json) | 22766行完整零更新状态、原请求和500抽样/随机流核对；前向/优化/物理0，A学习未复现，无新资格 |\n')
    text = line(text,'| 下一候选改哪里、有限对照如何限制成本 |',f'| 下一候选改哪里、有限对照如何限制成本 | [actor率实现](deliverables/learning_chain/b2_actor_lr_implementation_20260930/README.md)、[共同起点]({STAGE}/README.md)、[拟议预算](deliverables/learning_chain/b2_actor_lr_implementation_20260930/proposed_compute.json) | actor率已拆、共同状态已重建；A学习/新执行入口与资格未通过，1000批/8动态及额外真实测试未授权 |')
    return insert(text,'## 维护记录\n\n',f'### 2026-09-30｜四预热共同起点重建\n\n- [阶段交付]({STAGE}/README.md)保存严格origin_v2状态、固定500批抽样、新源/分支身份及重建证据；旧origin和中间结果保留，不将数据产物冒作可执行检查点。\n- 133最终纯协议通过，独立审查精度问题修正；原请求逐值一致，前向/优化/物理0。原283源和39前项产物/4149旧封存字节保持。\n- 原三份滚动资料同步；A学习尚未复现，执行适配/新预算账本/资格及真实计算未完成，B.2未完成，旧余19/2000与跟踪PAUSED保持。\n\n')


def monthly(text):
    stage = '../../learning_chain/b2_actor_lr_origin_20260930'
    text = insert(text,'## 一、可直接用于汇报的本月总结\n\n',f'**{MARK}：** 从旧初始完整检查点与四份预热重审构造22766行零更新状态，包括空Adam、温度、回放/边界及全部随机流；22766原请求逐值一致，500固定抽样/历史边界序列与最终随机流一致，分支深拷贝存储隔离、保存回读通过。133最终纯协议通过，审查指出的精度风险已补反例并另存严格版本。前向/优化/物理0；共同起点准备已验收，A实际学习尚未复现，新入口/账本/资格和真实计算未完成，效果未验证。旧余19/2000与PAUSED保持，B.2未完成。[交付]({stage}/README.md)、[证据]({stage}/origin_v2/assessment.json)。\n\n')
    text = insert(text,'|---|---|---|---|\n',f'| 严格四预热共同起点（9月30日） | 22766行完整状态/原请求、500抽样/随机流核对；分支存储隔离，133协议通过 | [严格版]({stage}/README.md)、[验收]({stage}/assessment.json) | 状态/抽样准备；真实调用0，A学习未复现，新执行资格/入口待补，非策略收益 |\n')
    text = insert(text,'### 数字使用规则\n\n','本阶段133包含32个新重建/精度反例及前项101范围，不与28/32/129中间运行相加。22766行与原四预热数据相同，不是新增经验；500指预登记抽样计划，本阶段真实更新0，不能与原2500相加。\n\n')
    text = insert(text,'## 三、必须保留的问题与负结果\n\n','共同起点、原请求和抽样已核验，但尚未执行A支500批梯度及Adam状态复现。严格版修正了归档先降为float32的精确性缺口，原重建和中间结果保留；不能以状态/随机序列一致称训练结果或策略效果已通过。\n\n')
    text = insert(text,'## 五、两分钟讲稿（截至本次整理）\n\n','9月30日最新进展：单独actor学习率实现后，已重建原四预热、零更新的共同起点，完整权重、优化器、经验与随机流得到交叉核验；133项协议通过。预登记500批抽样与历史记录吻合，但本阶段没有实际学习或物理评价，不能写成原学习结果已复现或策略效果提高。下一步接通对照执行入口与独立预算，真实计算另批。\n\n')
    text = insert(text,'## 六、下一步素材需求\n\n',f'最新：严格[共同起点]({stage}/README.md)已完成；仍需执行入口/账本/新资格及A学习复现。未来真实对照后才新增分布与任务图，本阶段无新性能图。\n\n')
    return insert(text,'## 七、阶段增量与来源追溯\n\n',f'2026-09-30共同起点增量：用户继续后核对283原源与39前项产物，重建22766行四预热零更新完整状态并交叉核对；500抽样/随机流一致，A学习尚未复现。[严格记录]({stage}/origin_v2/assessment.json)、[133最终]({stage}/final_strict_results.json)、[审查]({stage}/review.md)。精度缺口补4反例、旧origin保留，当前286源另绑定；初次路径及输出位置失误保留，旧封存未改。真实前向/优化/物理0，旧余19/2000和跟踪PAUSED保持，B.2未完成。\n\n')


update('项目进度跟踪.md',progress)
update('项目交付总览.md',overview)
update('deliverables/monthly_progress/2026-09/月报素材_2026-09.md',monthly)
links = []
for p in (HERE/'README.md', ROOT/'项目进度跟踪.md',ROOT/'项目交付总览.md',ROOT/'deliverables/monthly_progress/2026-09/月报素材_2026-09.md'):
    for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',p.read_text(encoding='utf-8')):
        target = target.strip('<>')
        if target.startswith(('http:','https:','#','app:','codex:')):
            continue
        local = target.split('#',1)[0]
        if not local:
            continue
        path = (p.parent/local).resolve()
        if path != (HERE/'verification.json').resolve():
            assert path.exists(),(p,local)
        links.append(str(path))
pins = {p.relative_to(HERE).as_posix():sha(p) for p in HERE.rglob('*')
    if p.is_file() and p.name != 'verification.json' and not any(part.endswith('_work') for part in p.parts)}
save('verification.json',dict(status='passed',date='2026-09-30',tests=133,local_links=len(links),
    source_files=286,protected_original_sources=283,protected_parent_artifacts=len(parent_files),
    old_sealed_files=len(sealed),inherited_source_original_bytes=len(candidate['source_sha256']),
    final_evidence_sha256=pins,qualification_issued=False,training_launched=False,policy_effect_validated=False))
print(json.dumps(dict(status='passed',tests=133,local_links=len(links),old_sealed_files=len(sealed),
    current_sources=286,reconstruction_complete=True,a_learning_reproduced=False,tracking='PAUSED'),ensure_ascii=True))
