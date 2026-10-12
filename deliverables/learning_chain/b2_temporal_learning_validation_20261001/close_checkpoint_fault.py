"""Reconcile a failed run and its separate offline writer repair, without compute."""
import hashlib,json,re,os
from datetime import datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2];OUT=HERE/'result_analysis'
FIX=HERE.with_name('b2_temporal_checkpoint_write_fix_20261001')
S=HERE.relative_to(ROOT).as_posix();F=FIX.relative_to(ROOT).as_posix()
read=lambda p:json.loads(p.read_text(encoding='utf-8'))
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def create(p,value):
    with p.open('x',encoding='utf-8') as f:
        f.write(value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False));f.flush();os.fsync(f.fileno())
a=read(OUT/'assessment.json');g=read(FIX/'writer_final_green.json');pins=read(HERE/'execution_pins.json')
assert a['judgement']=='operational_verification_blocked' and a['checkpoints']==[]
assert g['tests']==7 and not g['failures'] and not g['errors'] and not any(g['actual_calls'].values())
assert a['accounting']['formal_batches_completed']==500 and len(a['rows'])==4
fault='我新增的检查点代码把只接受字节/文本的 `_flush_write` 接口误当作回调接口，触发 `TypeError: a bytes-like object is required, not function`。此前174项协议没有覆盖真实序列化保存路径。'
loss='C已完成500批更新，但首次保存留下0字节 `state.pt`，有效检查点0；进程已退出，C500训练状态无法恢复。学后在线、固定四点和独立恢复动态均未执行，不能判定100ms方法有效或无效。'
repair='保存修复已在单独目录完成：直接在排他二进制文件中序列化完整状态，flush/fsync后写入字节清单，再原子发布目录；原封存故障源码和0字节证据保持。7项离线检查全过，包含完整状态真实落盘、独立进程零更新状态加载、非空Adam合成张量往返、重复发布拒绝及写清单故障留档，新增模型前向/优化/物理均0。合成与零更新夹具不代表丢失的C500已恢复，也不证明策略效果。'
next_text='保存修复及离线验证已完成；本轮故障账本关闭，余20动态/4500批不执行、不结转。后续效果验证必须另行绑定修复版本、明确新起点及累计成本，不能从丢失的C500续跑或重用本轮入口。自动跟踪PAUSED，B.2未完成。'
summary=f'**100ms预热学习验证已收口（2026-10-01）：** 运行故障阻止完成修复判定。共同零更新起点4/4成功；C完成500批、A0批，但我新增的保存代码接口使用错误，C500未落盘且无法恢复，学后评价0。保存修复已完成7项离线检查（模型/优化/物理0），不等于策略修复。新增4/24动态，累计72/92；余20动态/4500批关闭，旧余不使用，自动跟踪PAUSED，B.2未完成。[结果与图]({S}/result_analysis/结果说明.md)、[保存修复]({F}/README.md)。'
p=OUT/'结果说明.md';t=p.read_text(encoding='utf-8')
t=t.replace('本轮运行故障与策略任务失败分开记录，不能强行判定修复有效或无效。',fault+'\n\n'+loss+'\n\n'+repair,1)
t=t.replace('保护停止是预登记验证终点，不是漏做后续测试。','本轮触发的是保存程序故障，四个已完成动态均无保护；故障按预登记规则终止整个阶段。')
t=t.replace('每500批后、下一在线回合前保存完整状态，失败不会丢失触发策略。','原计划每500批后、下一在线回合前保存完整状态；首次保存实际失败，不能声称触发策略已保留。有效检查点0，丢失C500权重/Adam/RNG，只有已落盘的更新历史与采样记录可审核。')
t=t.replace('训练信用/抽样轨迹和检查点','训练信用/抽样轨迹、检查点缺失及0字节暂存证据')
t=t.replace('协议和数据存取修复成立，不替代策略效果验收。','此前174协议通过仍漏掉本次接口错误，不能称真实保存已通过；本次补充7项真实存取离线检查全过，仍不替代策略效果验收。')
t=t.replace('先依据本轮故障档案修复运行/起点问题，保留已消耗预算；未经新授权不重跑。',next_text)
t+=f'\n## 保存故障的修复交付\n\n[修复说明与7项检查](../../{FIX.name}/README.md)、[终点独立审查](独立结果审查.md)。修复实现独立封存，尚未接入任何新的训练入口。\n'
p.write_text(t,encoding='utf-8')
docs=[ROOT/'项目进度跟踪.md',ROOT/'项目交付总览.md',ROOT/'项目当前入口.md',ROOT/'deliverables/monthly_progress/2026-10/月报素材_2026-10.md']
for p in docs:
    t=p.read_text(encoding='utf-8');s=summary
    if p.name=='月报素材_2026-10.md':s=s.replace(S,'../../learning_chain/'+HERE.name).replace(F,'../../learning_chain/'+FIX.name)
    t=re.sub(r'^\*\*100ms预热学习验证已收口（2026-10-01）：\*\*.*$',s,t,flags=re.M)
    t=t.replace('先依据本轮故障档案修复运行/起点问题，保留已消耗预算；未经新授权不重跑。',next_text)
    t=t.replace('所有实测档案与完整检查点重新审核通过','所有实测档案重新审核，实际有效检查点0；保存修复另7项离线检查通过')
    t=t.replace('本阶段每500批前置保存完整不可变状态，离线结构/来源/信用/RNG/Adam复核；C独立动态恢复完成0/4','C500首次保存失败、有效检查点0、训练状态丢失；修复以真实完整零更新夹具跨进程加载核验，C独立动态恢复仍0/4')
    t=t.replace('任一保护终止、完整状态保存，未扩大外推','首次检查点保存错误终止、C500状态未保存，未扩大外推')
    t=t.replace('100ms预热候选完成本次有界学习验证：','100ms预热候选的本次验证在保存故障处终止：')
    t=t.replace('使用：只读结果、原始账本/档案与检查点；','使用：只读结果与原始账本/档案；本轮有效检查点0；')
    t=t.replace('全部已完成回合、成本、抽样信用和完整检查点重新审核','全部已完成回合、成本、抽样信用和0字节保存故障证据重新审核')
    t=t.replace('全部失败、完整检查点与余量关闭记录保留','保存故障、0字节暂存及余量关闭记录保留；有效检查点0，C500状态丢失')
    if p.name=='月报素材_2026-10.md':
        t=t.replace('运行故障阻止完成修复判定。本轮运行故障与策略任务失败分开记录，不能强行判定修复有效或无效。',fault+' '+loss+' 保存修复7项离线检查通过，效果验证仍受阻。')
        t=t.replace('位置、残差与载荷完整归档轨迹，不是重跑。','最后零更新起点的完整位置/请求/载荷轨迹，非学后策略或重跑。')
        t=t.replace('| 100ms预热学习验证 | 新增4动态、500批；C500/A0 |','| 100ms预热学习验证 | 零更新起点4/4；新增4动态、500批；C500/A0，学后评价0/有效检查点0 |')
        t=t.replace('## 三、负结果与限制\n\n','## 三、负结果与限制\n\n'+repair+'\n\n',1)
        t+=f'\n2026-10-01｜检查点接口错误已离线修复：7/7真实存取检查，实际计算0；[独立修复交付](../../learning_chain/{FIX.name}/README.md)。C500无法恢复，策略效果仍未知。\n'
    p.write_text(t,encoding='utf-8')
review='''# 终点独立审查（2026-10-01）

审查者：独立只读代理 `/root/temporal_validation_review`。本次审查仅针对新出现的检查点接口故障、分离修复及终点解释；不是重复审查原三项问题。

Critical 0 / Important 0。修复可作为离线修复交付，不能恢复实验执行资格。直接核对 `_flush_write` 实际接口、二进制 `torch.save` 与flush/fsync、字节清单、暂存目录及排他发布，原封存源码不修改；修复没有训练启动入口。审查已阅读六项全绿真实存取结果，含完整状态往返、另一进程零更新加载、原CRLF字节、重复发布拒绝与清单错误留档，实际计算均0。随后补充第七项非空Adam合成张量序列化检查，全绿且实际计算0，未改动修复实现。

终点判定为运行故障阻断，不能判定100ms修复有效或无效。实际共同零更新起点4/4，C500批/1500Adam，学后动态0，有效检查点0；累计72，余20动态/4500批关闭。零更新夹具证明真实存取路径可工作，不恢复丢失的C500，也不验证训练收益。审核输入摘要与账本/成本一致。

审查未编辑文件或运行模型/优化/物理。本文件为主代理依据其最终审查回复整理，不冒充额外全实验复验。
'''
create(OUT/'独立结果审查.md',review)
ra=dict(ready=True,critical=0,important=0,scope='offline_writer_repair_and_terminal_interpretation',reviewer='/root/temporal_validation_review',reviewed_tests=6,additional_synthetic_serialization_test_passed=True,effect_validation_complete=False,resume_execution_allowed=False)
create(OUT/'review_assessment.json',ra);create(FIX/'review.md',review);create(FIX/'review_assessment.json',ra)
create(FIX/'README.md',f'''# 检查点保存接口修复：离线交付

2026-10-01。**程序保存问题已修复并通过7项离线检查；100ms策略效果仍未知。**

{fault}

{loss}

{repair}

实现见 [corrected_runtime.py](corrected_runtime.py)：继承原完整捕获逻辑，仅替换保存方法。未来执行必须明确绑定该版本，故障轮源码保持原字节。没有训练入口，原账本不能再运行。

验证证据：[原错误反例（6项中5失败）](writer_red.json)、[修复后6项全过](writer_green.json)、[最终7项全过](writer_final_green.json)、[逐项输出](writer_final_green.txt)、[独立审查](review.md)。真实完整零更新夹具含网络/目标/三类Adam/温度、经验/索引/原归档、原始资格字节、历史和随机状态，独立进程加载不执行网络；第七项仅为明确标记的非空Adam合成张量文件往返，未进行优化，也不是训练检查点。

本次修复新增模型前向/Adam调用/物理步均0。实验实际成本仍为4动态/500批/1500Adam/244300物理子步，累计72。{next_text}

故障证据与策略结果见 [本轮结果](../{HERE.name}/result_analysis/结果说明.md)。原0字节暂存文件保留，不覆盖、不清理、不伪造恢复。
''')
record=dict(version='checkpoint_writer_offline_fix_v1',root_cause='flush_write_received_callback_instead_of_bytes',producer_fixed=True,actual_failed_state_recoverable=False,
    tests=g,review=ra,original_execution_binding_sha256=pins['binding_sha256'],original_authorization_sha256=pins['authorization_sha256'],
    parent_assessment_sha256=digest(OUT/'assessment.json'),parent_failure_sha256=digest(HERE/'run/main_failure.json'),
    original_runtime_sha256=digest(HERE/'learning_runtime.py'),accounting=a['accounting'],original_costs=a['actual_costs'],
    judgement='operational_verification_blocked',policy_effect_validated=False,retry_allowed=False,b2_complete=False,automatic_tracking='PAUSED',
    created_at=datetime.now().astimezone().isoformat())
create(FIX/'assessment.json',record)
p=HERE/'progress.md';t=p.read_text(encoding='utf-8')
t+='\nNew issue: original save passed a callback to byte writer, C500 first checkpoint failed (0-byte state.pt). C500 memory state is lost; zero learned-policy dynamics. Separate corrected writer completed 7/7 genuine file protocols, actual calls0; reviewer Critical0/Important0. This closes offline repair only, never reopens training ledger.\n'
p.write_text(t,encoding='utf-8')
print(json.dumps(dict(documents=4,writer_tests=7,actual_calls=g['actual_calls'],judgement=a['judgement']),ensure_ascii=False))
