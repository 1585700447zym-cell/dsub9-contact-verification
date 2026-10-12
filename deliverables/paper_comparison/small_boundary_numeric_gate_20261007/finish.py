"""Seal prepared numeric scripts only; grants remain unissued."""
from pathlib import Path
import datetime,shutil,sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from numeric_contract import ROOT,read,sha,write
import verify


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Already sealed')
    count=verify.main();plan=ROOT/'docs/superpowers/plans/2026-10-07-small-boundary-numeric-gate.md'
    shutil.copyfile(plan,OUT/'implementation_plan_snapshot.md')
    write(OUT/'closure_verification.json',dict(passed=True,preseal_checks=count,pure_tests=read(OUT/'offline_tests.json')['tests_passed'],
        old_files_unchanged=765,shared_inputs_unchanged=1057,actual_numeric_computations=0,actual_new_dynamics=0,
        cumulative_dynamic=208,automatic_tracking='PAUSED',numeric_authorized=False,training_admitted=False,
        review=read(OUT/'review.json'),next='Explicit new 4/32 synthetic-only authorization required before actual numerical verification'))
    with (OUT/'progress.md').open('a',encoding='utf8') as f:
        f.write('\nStage complete: 数值门脚本、授权请求和离线协议证据交付，真实数值门未授权/未执行。五份资料快照同步，765旧文件/1057共享输入保持，实际计算0、累计208、PAUSED。保留原工作区全部修改，无提交/清理。本阶段完成后暂停汇报并请求具体4/32合成数值授权。\n')
    files={}
    for p in sorted(OUT.rglob('*')):
        if not p.is_file() or any(x in ('__pycache__','.pytest_cache') or x.startswith('.test_tmp') for x in p.relative_to(OUT).parts):continue
        rel=p.relative_to(OUT).as_posix()
        if rel!='delivery_manifest.json':files[rel]=dict(sha256=sha(p),bytes=p.stat().st_size)
    write(OUT/'delivery_manifest.json',dict(version='pc13_prepared_numeric_kit_v1',status='SEALED_PREPARATION_NOT_AUTHORIZED',
        created_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
        actual_numeric_computations=0,cumulative_dynamic=208,numeric_authorized=False,training_admitted=False,files=files))
    verify.main();print('SEALED UNAUTHORIZED NUMERIC KIT',len(files),'files; actual computations0 cumulative208 PAUSED')


if __name__=='__main__':main()
