"""One frozen candidate, seven development cases, gated on numerical audit."""
import argparse
import json
from dataclasses import asdict

from tools.control.search_probe import SearchPauseProbe, ProbeConfig
from tools.control.search_recovery import SearchConfig
from tools.control.search_exit_v2 import ExitGateConfig
from tools.dynamics.cartesian import CartesianEnvironment
from tools.reporting.report_b2 import verified
from tools.reporting.report_b2_matrix import metrics
from tools.validation.run_b1_baseline import cases, dump
from tools.validation.run_b2_search import hashes, run_search_episode, save_run
from tools.validation.run_b2_exit_gate import source_hashes as inherited_hashes
from tools.validation.validate_training_readiness import OUT, sha, verify_hashes, new_target
from tools.validation.run_contact_cases import ROOT
from tools.validation.diagnose_v1_applicability import fingerprint

PROTOCOL=OUT/'候选比较协议.md'


def controller():
    return SearchPauseProbe(SearchConfig(),ExitGateConfig(),ProbeConfig(pause_s=2.,resume_s=.1))


def require_gate(gate):
    if gate.get('status')!='COMPLETE' or gate.get('verdict')!='LOCAL_SHORT_VALIDATION_PASS':
        raise ValueError('Current-path numerical gate has not passed')


def source_hashes():
    extras=('tools/control/search_probe.py','tools/validation/run_readiness_candidate.py',
            'tools/validation/validate_training_readiness.py','tools/reporting/report_b2.py',
            'tools/reporting/report_b2_matrix.py')
    return {**inherited_hashes(),**{p:sha(ROOT/p) for p in extras}}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--case',required=True,choices=[c.name for c in cases()]);p.add_argument('--tag',required=True)
    p.add_argument('--gate',default='numerical_gate_v1')
    args=p.parse_args();target=new_target(OUT,args.tag)
    # Validate tag syntax without permitting a path outside this capability.
    if not args.gate or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in args.gate):
        raise ValueError('Use a simple numerical gate tag')
    gate_path=OUT/args.gate/'results_index.json';gate=json.loads(gate_path.read_text(encoding='utf-8'))
    require_gate(gate);verify_hashes(ROOT,gate['protected_inputs'])
    for entry in gate['runs']:verify_hashes(gate_path.parent,{entry['file']:entry['sha256']})
    old_folder,old_index,old_runs=verified('matrix_v1_7cases')
    if old_index['source_sha256']!=hashes():raise ValueError('Frozen comparison sources changed')
    history=fingerprint()
    if old_index['historical_source_sha256']!=history or gate['historical_source_sha256']!=history:
        raise ValueError('Frozen model inputs changed')
    ref=next(r for r in old_runs if r['case']['name']==args.case and 'search_count' in r)
    case=next(c for c in cases() if c.name==args.case);ctrl=controller()
    if json.loads(json.dumps(asdict(ctrl.config)))!=old_index['config']:raise ValueError('Search budgets changed')
    if json.loads(json.dumps(ctrl.metadata()['admittance']))!=ref['controller']['admittance']:raise ValueError('Admittance changed')
    code=source_hashes()
    protected={**code,PROTOCOL.relative_to(ROOT).as_posix():sha(PROTOCOL),
               gate_path.relative_to(ROOT).as_posix():sha(gate_path),
               (old_folder/'results_index.json').relative_to(ROOT).as_posix():sha(old_folder/'results_index.json')}
    for entry in old_index['runs']:
        file=(old_folder/entry['file']).resolve();protected[file.relative_to(ROOT).as_posix()]=entry['sha256']
    target.mkdir(parents=True);(target/'runs').mkdir()
    for name in code:
        dest=target/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/name).read_bytes())
    (target/'候选比较协议.md').write_bytes(PROTOCOL.read_bytes())
    index={'status':'PREFLIGHT','candidate':'B2_V2_XY_pause_2s_resume_0p1s',
           'case':asdict(case),'controller':ctrl.metadata(),'source_sha256':code,
           'historical_source_sha256':history,'protected_inputs':protected,'runs':[]}
    dump(target/'results_index.json',index);partial=[];env=None
    try:
        env=CartesianEnvironment(segments=256)
        if env.metadata()!=ref['environment']:raise ValueError('Comparison environment changed')
        original=env.step
        def capture(command):
            row=original(command);partial.append(dict(row));return row
        env.step=capture
        index['status']='RUNNING';dump(target/'results_index.json',index)
        run=run_search_episode(env,case,ctrl)
        for key in ('case','environment','finish_criteria','max_time_s','settle_time_s'):
            if run[key]!=ref[key]:raise ValueError('Unfair comparison: '+key)
        verify_hashes(ROOT,protected)
        if history!=fingerprint():raise ValueError('Historical inputs changed during run')
        run.update(source_sha256=code,historical_source_sha256=history,candidate=index['candidate'],
                   probe_events=ctrl.probe_events,probe_trace=ctrl.probe_trace)
        name=f'runs/{case.name}_candidate.json.gz';save_run(target/name,run)
        index['runs']=[{'file':name,'sha256':sha(target/name),'metrics':metrics(run)}]
        index['status']='COMPLETE';dump(target/'results_index.json',index)
        print(json.dumps(index['runs'][0],ensure_ascii=False),flush=True)
    except (Exception,KeyboardInterrupt) as error:
        index.update(status='ERROR' if partial else 'PREFLIGHT_FAILED',error=repr(error))
        if partial:save_run(target/'partial_trace.json.gz',{'trace':partial,'termination':'INCOMPLETE_ERROR',
                                                        'probe_events':ctrl.probe_events,'probe_trace':ctrl.probe_trace})
        dump(target/'results_index.json',index)
        raise


if __name__=='__main__':main()
