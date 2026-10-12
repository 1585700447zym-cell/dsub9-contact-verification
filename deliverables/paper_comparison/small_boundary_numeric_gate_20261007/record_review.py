"""Record the one completed review and author's single fix pass; no re-review."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from numeric_contract import ROOT,read,write,sha


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed')
    before=(read(OUT/'review.json')['reviewed_source_sha256'] if (OUT/'review.json').exists()
            else read(OUT/'numeric_candidate.json')['execution_source_sha256'])
    tests=read(OUT/'offline_tests.json');assert tests['passed']
    after=tests['implementation_source_sha256']
    findings=[
        dict(id='I1',original_severity='Important',issue='Returned forward/committed critic batch was lost when later audit failed',
             fix='Record actual completion before output audit; exception after committed critic is also counted',tests=['returned_forward','committed_update']),
        dict(id='I2',original_severity='Important',issue='Durable receipt then interrupted ledger projection prevented failure closure',
             fix='Failure-only reconstruction from durable receipts; close unused quota, expose unknown completion bounds, never resume',tests=['interrupted_projection[attempt]','interrupted_projection[complete]']),
        dict(id='I3',original_severity='Important',issue='Windows venv launcher timeout could leave real Python reader alive',
             fix='Popen wait retains live root for tree kill; check stop receipt and recorded real PID/creation time/image; uncertain stop cannot close/reopen quota',tests=['reader_timeout','cleanup_failure']),
        dict(id='I4',original_severity='Important',issue='Same-version external packages could pass metadata/DLL binding',
             fix='Both workers use -I; verify package origin before and after import, bind three init files and environment registration',tests=['runtime_resolution']),
        dict(id='M1',original_severity='Minor',author_severity='Important',issue='Model construction and CPU tensor-read costs not recorded separately',
             rationale='PC12 numeric checklist explicitly requires these costs; misleading 4/32 accounting would affect approval scope',
             fix='Transparent constructor/load attempt/completion/time counters, restored in finally, preserve costs on failure',tests=['numeric_costs','failed_constructor'])]
    for f in findings:f['status']='AUTHOR_FIX_VALIDATED_BY_PURE_TESTS'
    result=dict(independent_reviewer='/root/pc13_review',independent_reviews=1,author_fix_passes=1,independent_rereview=False,
        original_counts=dict(Critical=0,Important=4,Minor=1),author_regraded_minor_to_important=['M1'],
        critical_open=0,important_open=0,minor_deferred=0,findings=findings,
        reviewed_source_sha256=before,validated_source_sha256=after,
        fix_delta={k:dict(before=before[k],after=after[k]) for k in before if before[k]!=after[k]},
        tests_passed=tests['tests_passed'],scope='offline preparation only; actual CPU/Windows numeric integration not executed',
        author_discovered_findings=[dict(id='A1',severity='Important',status='AUTHOR_FIX_VALIDATED_BY_PURE_TESTS',
            issue='PC12 same-named prepare/verify helpers shadowed PC13 imports during final source verification',
            fix='Put PC13 helper directory first after installing frozen dependency paths; one origin regression RED→GREEN')],
        actual_numeric_computations=0)
    write(OUT/'review.json',result)
    write(OUT/'review_regressions.json',dict(record_kind='observed command outcome summary, not reconstructed raw stdout',
        review_red=dict(command="python -I -m pytest test_numeric_contract.py test_numeric_protocol.py -q -p no:cacheprovider -k 'interrupted_projection or returned_forward or committed_update or runtime_resolution or reader_timeout or numeric_costs' --basetemp=.test_tmp_review_red_a",failed=7,deselected=14),
        review_green=dict(passed=7,deselected=14),zero_origin_red=dict(failed=1,deselected=14),
        zero_origin_and_failure_accounting_green=dict(passed=3,deselected=12),final_suite=dict(passed=tests['tests_passed'],exit_code=tests['exit_code']),
        stage_helper_red=dict(failed=1,deselected=9),stage_helper_green=dict(passed=1,deselected=9),
        intermediate_mixed_suite=dict(failed=1,passed=77,reason='pytest collection prepended PC12 test path after PC13 initialization',
            correction='run helper-origin regression in a fresh -I process matching real entrypoint; no torch import'),
        real_torch_imports=0,real_model_constructions=0,real_tensor_reads=0,real_updates=0,real_physics=0))
    (OUT/'review.md').write_text('''# PC-13 一次限定审查与一轮作者修复

独立审查由 /root/pc13_review 完成，原分级0 Critical、4 Important、1 Minor。作者只做一轮修复，无第二次独立审查；“open=0”是作者依据纯回归的关闭判断，不是独立复审或实际数值通过。

| 项 | 问题与修复 | 证据与边界 |
|---|---|---|
| I1 | 返回前向与已提交critic批先记实际完成，后做结果审查；失败仍保留事实 | 2纯反例RED→GREEN；没有真实SAC计算 |
| I2 | 收据写入后投影失败，只重建关闭账本；没有完成回执时保留未知范围 | 2中断点RED→GREEN；禁止重试/重新分配 |
| I3 | 保持launcher存活直至整棵所属树结束；检查stop结果，另查真实PID/创建时间/镜像 | timeout纯反例RED→GREEN、停止失败保留不确定证据；真实Windows终止路径未运行 |
| I4 | -I与导入前后包路径核对，36文件绑定含3包入口与环境登记 | 外部同版本包来源纯反例RED→GREEN；真实CPU加载未执行 |
| M1→Important | 按PC-12明确要求，将辅助构造/读取开销漏记升级并在同轮修复 | 成功、失败fake构造/load分别计尝试/完成/时间，恢复原方法；没有真实构造或读取 |

验收清单核对另补空优化器、空回放、历史/边界与三个RNG起点的显式断言和证据保存；对应纯状态反例RED→GREEN。不修改原引擎、封存PC-12或历史资料。

最终收口作者自查A1：来源核验触发失败，定位为PC-12同名prepare_candidate/verify脚本遮蔽新目录。保留依赖路径并将PC-13自身置首；专门路径反例1 RED→1 GREEN，重新运行全部关联检查并重绑候选。属于本轮作者修复收口，未增加独立审查。历史文件不改。

全关联结果见[offline_tests](offline_tests.json)，逐项状态/源码前后绑定见[review.json](review.json)，已观察RED/GREEN摘要见[review_regressions](review_regressions.json)。代码仍是未授权候选。模型构造与读取的实际次数、墙钟时间及完整数值恢复仅可在新授权后确定。
''',encoding='utf8')
    print('ONE REVIEW / ONE AUTHOR FIX PASS; original0/4/1; open0; real numeric0')


if __name__=='__main__':main()
