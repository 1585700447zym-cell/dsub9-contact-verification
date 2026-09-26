"""One exact replay of old B2 Y, then bounded passive hold observation."""
import argparse
import json
import numpy as np
from tools.reporting.report_b2 import verified
from tools.control.search_recovery import SearchRecovery, SearchConfig
from tools.dynamics.cartesian import CartesianEnvironment
from tools.validation.run_b1_baseline import cases, dump
from tools.validation.run_b2_search import hashes, run_search_episode, save_run
from tools.validation.validate_training_readiness import ROOT, OUT, sha, new_target, verify_hashes
from tools.validation.diagnose_v1_applicability import fingerprint


def stop_qualified(*,phase,events,recorded_time_s,deadline_s,confirmed,final_stable,peaks):
    invalid=any('INVALID' in e['reason'] or e['reason'] in ('SIMULATION_ERROR','OUT_OF_BOUNDS') for e in events)
    return bool(phase=='STOPPING' and not invalid and recorded_time_s>=deadline_s-1e-9 and
                confirmed and final_stable and peaks['force_N']<.025 and
                peaks['torque_G_Nm']<.0005 and peaks['penetration_m']<30e-6)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag',default='old_b2_y_stop_extension_v1')
    target=new_target(OUT,parser.parse_args().tag)
    folder,index,old=verified('matrix_v1_7cases')
    reference=next(r for r in old if r['case']['name']=='y_offset_neg_100um' and 'search_count' in r)
    assert index['source_sha256']==hashes() and index['historical_source_sha256']==fingerprint()
    case=next(c for c in cases() if c.name=='y_offset_neg_100um')
    code={**hashes(),'tools/validation/measure_readiness_stop.py':sha(ROOT/'tools/validation/measure_readiness_stop.py')}
    protected={**code,'deliverables/baseline_training_readiness/停止延续复验协议.md':sha(OUT/'停止延续复验协议.md'),
               (folder/'results_index.json').relative_to(ROOT).as_posix():sha(folder/'results_index.json')}
    target.mkdir(parents=True)
    for name in code:
        dest=target/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/name).read_bytes())
    (target/'停止延续复验协议.md').write_bytes((OUT/'停止延续复验协议.md').read_bytes())
    status={'status':'RUNNING','protected_inputs':protected,'source_sha256':code,'historical_source_sha256':fingerprint()}
    dump(target/'results_index.json',status)
    env=CartesianEnvironment(segments=256);partial=[];original=env.step
    def capture(cmd):
        r=original(cmd);partial.append(dict(r));return r
    env.step=capture
    try:
        run=run_search_episode(env,case,SearchRecovery(SearchConfig(**index['config'])))
        save_run(target/'reproduced_original.json.gz',run)
        fields=('case','environment','finish_criteria','trace','events','termination','peaks','physical_steps')
        equality={k:run[k]==reference[k] for k in fields}
        status['prefix_equality']=equality
        if not all(equality.values()):raise ValueError('Historical trajectory not reproduced exactly')
        stop=run['stop_time_s'];rows=[env.observe()]
        while env.data.time < stop+2.-1e-10:
            assert env.phase=='STOPPING'
            rows.append(env.step(np.zeros(6)))
        since=None;confirmed=None
        for r in rows:
            ok=np.linalg.norm(r['velocity_world'][:3])<=1e-5 and np.linalg.norm(r['velocity_world'][3:])<=.001
            since=r['time_s'] if ok and since is None else since if ok else None
            if since is not None and r['time_s']-since>=.1-1e-10 and confirmed is None:
                confirmed={'stable_since_after_stop_s':since-stop,'confirmed_after_stop_s':r['time_s']-stop}
        save_run(target/'passive_extension.json.gz',{'trace':rows,'events':env.events,'peaks':env.peaks})
        verify_hashes(ROOT,protected);assert fingerprint()==status['historical_source_sha256']
        status.update(status='COMPLETE',original_termination=run['termination'],original_stop_time_s=stop,
                      original_1s_linear_um_s=float(np.linalg.norm(run['final']['velocity_world'][:3])*1e6),
                      two_s_linear_um_s=float(np.linalg.norm(rows[-1]['velocity_world'][:3])*1e6),
                      two_s_angular_rad_s=float(np.linalg.norm(rows[-1]['velocity_world'][3:])),
                      additional_displacement_um=float(np.linalg.norm(np.asarray(rows[-1]['position_m'])-rows[0]['position_m'])*1e6),
                      stable_confirmation=confirmed,final_remains_stable=bool(since is not None and rows[-1]['time_s']-since>=.1-1e-10),
                      extended_peaks=env.peaks,
                      files={p.name:sha(p) for p in target.glob('*.json.gz')})
        status['pass']=stop_qualified(phase=env.phase,events=env.events,recorded_time_s=rows[-1]['time_s'],
                                      deadline_s=stop+2.,confirmed=confirmed,
                                      final_stable=status['final_remains_stable'],peaks=env.peaks)
        dump(target/'results_index.json',status);print(json.dumps({k:v for k,v in status.items() if k not in ('protected_inputs','source_sha256','historical_source_sha256')},ensure_ascii=False),flush=True)
    except (Exception,KeyboardInterrupt) as error:
        save_run(target/'partial_trace.json.gz',{'trace':partial,'termination':'INCOMPLETE_ERROR'})
        status.update(status='ERROR',error=repr(error));dump(target/'results_index.json',status);raise


if __name__=='__main__':main()
