"""Full original B2 Y under one isolated contact candidate; bounded 2 s final stop."""
import argparse
from contextlib import contextmanager
import json
import mujoco
import numpy as np
from tools.dynamics.contact_candidate import candidate_environment
from tools.control.search_recovery import SearchRecovery,SearchConfig
from tools.validation.run_b1_baseline import cases,dump
from tools.validation.run_b2_search import hashes,run_search_episode,save_run
from tools.validation.measure_readiness_stop import stop_qualified
from tools.validation.validate_training_readiness import ROOT,sha,verify_hashes,new_target

OUT=ROOT/'deliverables/contact_consistency_repair'


@contextmanager
def stop_steps(env):
    original=mujoco.mj_step;rows=[]
    def step(model,data):
        result=original(model,data)
        if data is env.data and env.phase=='STOPPING':
            rows.append(dict(time_s=float(data.time),linear_m_s=float(np.linalg.norm(data.qvel[:3])),
                             angular_rad_s=float(np.linalg.norm(data.qvel[3:]))))
        return result
    mujoco.mj_step=step
    try:yield rows
    finally:mujoco.mj_step=original


def physical_tail_pass(rows,end,dt):
    tail=[r for r in rows if r['time_s']>=end-.1-dt/2]
    if not tail or tail[0]['time_s']>end-.1+dt/2 or abs(tail[-1]['time_s']-end)>dt/2:return False
    times=np.array([r['time_s'] for r in tail])
    if np.any(np.diff(times)>dt*1.01) or np.any(np.diff(times)<=0):return False
    return all(np.isfinite([r['linear_m_s'],r['angular_rad_s']]).all() and
               r['linear_m_s']<=1e-5 and r['angular_rad_s']<=.001 for r in tail)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--tag',required=True)
    parser.add_argument('--timestep',type=float,choices=[.0002,.0001],required=True);args=parser.parse_args()
    target=new_target(OUT,args.tag)
    gatepath=OUT/'static_gate_v1/results.json';gate=json.loads(gatepath.read_text(encoding='utf-8'))
    assert gate['passed'];verify_hashes(ROOT,gate['input_sha256']);verify_hashes(ROOT,gate['historical_source_sha256'])
    oldpath=ROOT/'deliverables/b2_search_recovery/matrix_v1_7cases/results_index.json'
    old=json.loads(oldpath.read_text(encoding='utf-8'));verify_hashes(ROOT,old['source_sha256'])
    code={**hashes(),**{p:sha(ROOT/p) for p in ['tools/dynamics/contact_candidate.py','tools/validation/run_contact_candidate_stop.py',
                                               'tools/validation/measure_readiness_stop.py']}}
    protected={**code,gatepath.relative_to(ROOT).as_posix():sha(gatepath),oldpath.relative_to(ROOT).as_posix():sha(oldpath),
               'deliverables/contact_consistency_repair/候选复验协议.md':sha(OUT/'候选复验协议.md')}
    target.mkdir(parents=True)
    for name in code:
        p=target/'source_snapshot'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes((ROOT/name).read_bytes())
    status=dict(status='RUNNING',timestep=args.timestep,protected_inputs=protected,
                source_sha256=code,historical_source_sha256=gate['historical_source_sha256'])
    dump(target/'results_index.json',status)
    env=candidate_environment(timestep=args.timestep);partial=[];original=env.step
    def capture(command):
        row=original(command);partial.append(dict(row));return row
    env.step=capture
    try:
        with stop_steps(env) as steps:
            run=run_search_episode(env,next(c for c in cases() if c.name=='y_offset_neg_100um'),SearchRecovery(SearchConfig(**old['config'])))
            save_run(target/'original_duration.json.gz',run)
            stop=run['stop_time_s'];extension=[env.observe()]
            if stop is not None:
                while env.phase=='STOPPING' and env.data.time<stop+2.-1e-10:
                    extension.append(env.step(np.zeros(6)))
            end=float(env.data.time)
        passed_tail=physical_tail_pass(steps,end,args.timestep)
        passed=stop is not None and stop_qualified(phase=env.phase,events=env.events,recorded_time_s=end,
                    deadline_s=stop+2.,confirmed=passed_tail,final_stable=passed_tail,peaks=env.peaks)
        save_run(target/'stop_extension.json.gz',dict(trace=extension,physical_stop_samples=steps,events=env.events,peaks=env.peaks))
        verify_hashes(ROOT,protected);verify_hashes(ROOT,gate['historical_source_sha256'])
        status.update(status='COMPLETE',passed=bool(passed),physical_tail_pass=bool(passed_tail),
                      final=env.observe(),peaks=env.peaks,events=env.events,original_termination=run['termination'],
                      stop_time_s=stop,end_time_s=end,files={p.name:sha(p) for p in target.glob('*.json.gz')})
        dump(target/'results_index.json',status)
        print(json.dumps({k:v for k,v in status.items() if k not in ('protected_inputs','source_sha256','historical_source_sha256','final')},ensure_ascii=False),flush=True)
    except (Exception,KeyboardInterrupt) as error:
        save_run(target/'partial.json.gz',dict(trace=partial,termination='INCOMPLETE_ERROR'))
        status.update(status='ERROR',error=repr(error));dump(target/'results_index.json',status);raise


if __name__=='__main__':main()
