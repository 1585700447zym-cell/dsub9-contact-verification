"""Audit complete raw data after the known archive-reference error; never overwrite evidence."""
import json
import numpy as np
from tools.validation.run_native313_validation import ROOT, OUT, sha, write
from tools.validation.run_native313_stop import OLD_PROTOCOL, NEW_PROTOCOL, protocol_inputs, verify_static_dependencies
from tools.validation.validate_training_readiness import verify_hashes
from tools.validation.run_contact_candidate_stop import physical_tail_pass
from tools.validation.measure_readiness_stop import stop_qualified
from tools.validation.run_b2_search import read_run


def audit(tag):
    folder=OUT/tag
    index_path=folder/'results_index.json'
    index=json.loads(index_path.read_text(encoding='utf-8'))
    if index['status']!='ERROR' or index.get('error')!=repr(ValueError('Input changed: '+OLD_PROTOCOL)):
        raise ValueError('This recovery applies only to the exact known archive-reference error')
    expected=protocol_inputs(index['protected_inputs'],sha(ROOT/NEW_PROTOCOL))
    verify_hashes(ROOT,expected)
    verify_hashes(ROOT,index['historical_source_sha256'])
    runtime_path=OUT/(tag+'_runtime.json')
    runtime=json.loads(runtime_path.read_text(encoding='utf-8'))
    assert runtime['mujoco_version']=='3.13.0'
    verify_hashes(ROOT,runtime['source_sha256'])
    verify_static_dependencies()
    run=read_run(folder/'original_duration.json.gz')
    extension=read_run(folder/'stop_extension.json.gz')
    partial=read_run(folder/'partial.json.gz')
    assert partial['termination']=='INCOMPLETE_ERROR'
    assert run['final']==extension['trace'][0]
    rows=run['trace']+extension['trace'][1:]
    assert len(partial['trace'])==len(rows)-1
    for a,b in zip(partial['trace'],rows[1:]):
        for key in ('time_s','position_m','quaternion_wxyz','velocity_world','contact_wrench_G','phase'):
            assert a[key]==b[key],key
    times=np.array([r['time_s'] for r in rows])
    assert len(times)>1 and np.all(np.diff(times)>0) and np.all(np.diff(times)<=.002+1e-9)
    finite=all(np.isfinite(r['position_m']+r['quaternion_wxyz']+r['velocity_world']+
                           r['contact_wrench_G']+[r['penetration_m']]).all() for r in rows)
    assert finite
    final=rows[-1];end=final['time_s'];stop=run['stop_time_s'];dt=index['timestep']
    tail=physical_tail_pass(extension['physical_stop_samples'],end,dt)
    passed=stop is not None and stop_qualified(phase=final['phase'],events=extension['events'],recorded_time_s=end,
                    deadline_s=stop+2.,confirmed=tail,final_stable=tail,peaks=extension['peaks'])
    paths=[index_path,runtime_path,folder/'original_duration.json.gz',folder/'stop_extension.json.gz',
           folder/'partial.json.gz',OUT/'时间步判读补充.md',ROOT/'tools/validation/audit_native313_results.py',
           ROOT/'tools/validation/run_native313_stop.py',ROOT/'tools/validation/audit_contact_candidate.py']
    result=dict(status='RAW_DATA_AUDITED_AFTER_ARCHIVE_ERROR',original_runner_status='ERROR',
                archive_error=index['error'],mujoco_version='3.13.0',timestep=dt,
                passed=bool(passed),physical_tail_pass=bool(tail),data_continuity_pass=True,finite=finite,
                original_termination=run['termination'],stop_time_s=stop,end_time_s=end,final=final,
                events=extension['events'],peaks=extension['peaks'],physical_stop_samples=len(extension['physical_stop_samples']),
                corrected_protected_inputs=expected,
                source_sha256={p.relative_to(ROOT).as_posix():sha(p) for p in paths})
    write(folder/'audited_results.json',result)
    print(tag,json.dumps({k:result[k] for k in ('status','passed','physical_tail_pass','original_termination','end_time_s','peaks')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tag',required=True)
    audit(p.parse_args().tag)
