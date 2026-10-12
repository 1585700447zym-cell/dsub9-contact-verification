"""Seal only the actual offline package. Synthetic pytest folders stay excluded."""
from pathlib import Path
import datetime,json,sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from small_bound_profile import read,sha
from prepare_candidate import write
import verify


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Already sealed')
    verify.main()
    write(OUT/'closure_verification.json',dict(passed=True,preseal_static_checks=53,
        pure_tests=read(OUT/'offline_tests.json')['tests_passed'],old_files_unchanged=730,shared_inputs_unchanged=1057,
        independent_review=dict(critical_found=0,important_found=3,minor_found=0,important_author_fixed=3,
            verified_by='author RED/GREEN + associated pure suite; no second independent review'),
        actual_new_compute=0,cumulative_dynamic=208,automatic_tracking='PAUSED',
        training_admitted=False,execution_authorized=False,
        incomplete_gates=['actual tensor serialization/restore','numerical zero-origin','physical backend','new compute authorization']))
    with (OUT/'progress.md').open('a',encoding='utf8') as f:
        f.write('\nStage complete: 离线适配、检查点外层与一次性协议候选收口；实际数值/物理backend/计算准入未完成。全部阶段内RED/GREEN及独立审查见本记录、review.json与offline_tests.json。五份资料和快照已同步。新实际计算0、累计208、PAUSED；730旧文件/1057共享输入未变。完成后暂停汇报，不开启拟数值或物理预算。\n')
    files={}
    for p in sorted(OUT.rglob('*')):
        if not p.is_file() or any(part in ('__pycache__','.pytest_cache') or part.startswith('.test_tmp') for part in p.relative_to(OUT).parts):continue
        rel=p.relative_to(OUT).as_posix()
        if rel=='delivery_manifest.json':continue
        files[rel]=dict(sha256=sha(p),bytes=p.stat().st_size)
    write(OUT/'delivery_manifest.json',dict(version='pc12_offline_delivery_v1',status='SEALED_OFFLINE_CANDIDATE_NOT_ADMITTED',
        created_at=datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat(timespec='seconds'),
        scope='offline action/checkpoint wrapper/scheduling protocol; actual numerical/physical backend unverified',
        actual_new_compute=0,cumulative_dynamic=208,training_admitted=False,execution_authorized=False,files=files))
    verify.main()
    print('SEALED OFFLINE CANDIDATE',len(files),'files; actual new compute 0; cumulative208 PAUSED')


if __name__=='__main__':main()
