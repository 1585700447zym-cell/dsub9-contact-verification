"""Attach diagnosed limitations to the generated, not-yet-sealed report."""
import paired_contract as C


def main():
    out=C.HERE/'result_analysis'
    if (out/'delivery_verification.json').exists():raise RuntimeError('Delivery already sealed')
    diagnostic=C.read(C.HERE/'offline_reader_diagnosis_20261003/result.json')
    post=C.read(out/'postprocess_execution.json')
    ledger=C.read(C.HERE/'run/ledger.json')
    if (not diagnostic['complete_equal'] or any(diagnostic['calls'].values()) or post['error'] is not None
            or any(post['calls'].values()) or diagnostic['ledger_sha256']!=C.digest(C.HERE/'run/ledger.json')
            or ledger['status']!='failed' or any(v!=dict(attempted=0,completed=0) for v in ledger['updates'].values())):
        raise ValueError('Exact stopped zero-update diagnostic boundary required')
    tests=dict(passed=5,exit_code=0,stdout='5 passed in 0.48s',
        command='python -X utf8 -B -m pytest deliverables/learning_chain/b2_stage_permission_20261002/test_reader_supervision.py -q -p no:cacheprovider --tb=short',
        red='Collection failed before implementation: missing reader_supervision',
        source_sha256={name:C.digest(C.HERE/name) for name in ('reader_supervision.py','test_reader_supervision.py','diagnose_reader_offline.py')},
        scope='Isolated subprocess and pure logging checks; no simulation, neural forward or optimization',
        integrated_training_run_verified=False)
    C.write(C.HERE/'reader_repair_tests.json',tests)
    a=C.read(out/'assessment.json')
    original=out/'assessment_before_reader_caveat.json'
    if not original.exists():C.write(original,a)
    a.update(main_costs_complete=a.get('main_costs_complete',a['costs_complete']),costs_complete=False,
        missing_cost_proofs=['original independent zero-checkpoint reader exit/call receipt'],
        original_reader_calls=None,offline_checkpoint_diagnosis=diagnostic,
        diagnostic_process_exit=1,diagnostic_post_result_error='Duplicate elapsed_s in terminal logging; fixed and unit checked without repeating restore',
        repair_protocol_passed=5,reader_supervision_integrated=False)
    names=['run/main_failure.json','process/process_exit.json','launch_failure.json',
        'offline_reader_diagnosis_20261003/result.json','offline_reader_diagnosis_20261003/events.jsonl',
        'offline_reader_diagnosis_20261003/script_at_execution.py','reader_repair_tests.json','failure_diagnosis.md']
    a['result_input_sha256'].update({(C.HERE/name).relative_to(C.ROOT).as_posix():C.digest(C.HERE/name) for name in names})
    C.write(out/'assessment.json',a)
    report=out/'结果说明.md';text=report.read_text(encoding='utf-8')
    text=text.replace('| F | 0/4 | 0/0 |','| F | 未执行 | 无学后结果 |').replace('| S | 0/4 | 0/0 |','| S | 未执行 | 无学后结果 |')
    text=text.replace('完整计数记录：True；已记录物理子步733800，逐进程初始化/模型/优化调用见assessment。未知调用不记为0。',
        '主进程物理成本完整可核对：733800子步；原独立读取子进程缺少退出/调用回执，全部子进程凭证并不完整，缺失项不记为0。详见assessment。')
    marker='<!-- diagnosed-reader-closeout -->'
    if marker not in text:
        text+='\n'+marker+'\n## 新故障及已完成修复\n\n原F零更新检查点读取超过固定60秒，整轮因此停止。新增一次只读核对完成完整状态比对：总65.863秒，恢复审核61.559秒，物理/模型前向/优化调用0；失败账本未变。该诊断的末尾日志发生字段重复错误，已修复并保留原错误记录。\n\n报告环境入口已修复并实际通过；新的300秒读取监督器及退出日志方案已准备，5项针对性检查通过，尚未接入新的正式训练。具体证据、局限和避免重采的后续方案见[故障诊断与最小修复](../failure_diagnosis.md)。\n\n预热F/S均3/4成功，活动经验分别18909/10089条。预热成功不是学习成功；本轮正式训练0批，F/S学后效果均未判定。\n\n![本轮已完成回合](results.png)\n'
    report.write_text(text,encoding='utf-8')
    print('Diagnostic evidence and reader-accounting limitation attached; experiment remains failed.')


if __name__=='__main__':main()
