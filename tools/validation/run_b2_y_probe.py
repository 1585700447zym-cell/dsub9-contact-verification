"""One prespecified Y trial; preserve old V2 inputs and every new attempt."""
import argparse
import json
from dataclasses import asdict
from pathlib import Path

from tools.control.search_probe import SearchPauseProbe, ProbeConfig
from tools.control.search_recovery import SearchConfig
from tools.control.search_exit_v2 import ExitGateConfig
from tools.dynamics.cartesian import CartesianEnvironment
from tools.reporting.report_b2_exit_gate import collect
from tools.validation.run_b1_baseline import cases, dump
from tools.validation.run_b2_search import run_search_episode, save_run
from tools.validation.run_b2_exit_gate import source_hashes as inherited_hashes, sha
from tools.validation.diagnose_v1_applicability import fingerprint
from tools.validation.run_contact_cases import ROOT

OUT = ROOT/'deliverables/b2_y_probe'
X_OUT = ROOT/'deliverables/b2_xy_probe'
PROTOCOL = OUT/'实验协议.md'
EXTRA_SOURCES = ('tools/control/search_probe.py','tools/validation/run_b2_xy_probe.py','tools/validation/run_b2_y_probe.py')


def source_hashes():
    return {**inherited_hashes(), **{p:sha(ROOT/p) for p in EXTRA_SOURCES}}


def new_target(base, tag):
    if not tag or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in tag):
        raise ValueError('Use a new simple folder name')
    target=base/tag
    if target.exists():raise FileExistsError('Preserve existing attempts; choose a new tag')
    return target


def select_inputs():
    # Frozen X implementation is the treatment; Y only changes the initial case.
    manifest=json.loads((X_OUT/'delivery_manifest.json').read_text(encoding='utf-8'))
    for relative,digest in manifest.items():assert sha(ROOT/relative)==digest,relative
    x_index=json.loads((X_OUT/'first_frozen_x100/results_index.json').read_text(encoding='utf-8'))
    pairs,_=collect(('verified_frozen_x100','verified_frozen_y100'))
    folder,_,reference=pairs[1]
    controller=SearchPauseProbe(SearchConfig(**reference['controller']['config']),
                                ExitGateConfig(**reference['controller']['exit_gate']),ProbeConfig())
    assert json.loads(json.dumps(controller.metadata()))==x_index['controller']
    case=next(c for c in cases() if c.name=='y_offset_neg_100um')
    assert asdict(case)==reference['case']
    return folder,reference,case,controller


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tag', required=True)
    args=parser.parse_args()
    target=new_target(OUT,args.tag)
    reference_folder,reference,case,controller=select_inputs()
    index_path=reference_folder/'results_index.json'
    index=json.loads(index_path.read_text(encoding='utf-8'))
    reference_path=reference_folder/index['runs'][0]['file']
    code=source_hashes();history=fingerprint();protocol_sha=sha(PROTOCOL)
    target.mkdir(parents=True);(target/'runs').mkdir()
    for relative in code:
        dest=target/'source_snapshot'/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes((ROOT/relative).read_bytes())
    (target/'实验协议.md').write_bytes(PROTOCOL.read_bytes())
    status={'status':'PREFLIGHT','candidate':'B2_v2_xy_pause_first_frozen_y100',
            'x_trial_index_sha256':sha(X_OUT/'first_frozen_x100/results_index.json'),
            'case':asdict(case),'controller':controller.metadata(),
            'source_sha256':code,'historical_source_sha256':history,'protocol_sha256':protocol_sha,
            'reference':{'file':reference_path.relative_to(ROOT).as_posix(),'sha256':sha(reference_path),
                         'index':index_path.relative_to(ROOT).as_posix(),'index_sha256':sha(index_path)},'runs':[]}
    dump(target/'results_index.json',status)
    partial=[];env=None
    try:
        env=CartesianEnvironment(segments=256)
        assert env.metadata()==reference['environment']
        assert json.loads(json.dumps(controller.metadata()['admittance']))==reference['controller']['admittance']
        original=env.step
        def capture(command):
            row=original(command);partial.append(dict(row));return row
        env.step=capture
        status['status']='RUNNING';dump(target/'results_index.json',status)
        run=run_search_episode(env,case,controller)
        for key in ('case','environment','finish_criteria','max_time_s','settle_time_s'):
            assert run[key]==reference[key],key
        assert code==source_hashes() and history==fingerprint() and protocol_sha==sha(PROTOCOL)
        assert sha(reference_path)==status['reference']['sha256']
        assert sha(index_path)==status['reference']['index_sha256']
        run.update(source_sha256=code,historical_source_sha256=history,
                   candidate=status['candidate'],probe_events=controller.probe_events,probe_trace=controller.probe_trace)
        name='runs/y_offset_neg_100um_xy_probe.json.gz';save_run(target/name,run)
        status['runs']=[{'file':name,'sha256':sha(target/name),'termination':run['termination']}]
        status['status']='COMPLETE';dump(target/'results_index.json',status)
        print(json.dumps({'termination':run['termination'],
                          'advance_mm':(run['final']['position_m'][2]-case.start_origin_z_m)*1000,
                          'probe_events':controller.probe_events,'wall_seconds':run['wall_seconds']},ensure_ascii=False),flush=True)
    except (Exception,KeyboardInterrupt) as error:
        status.update(status='ERROR' if partial else 'PREFLIGHT_FAILED',error=repr(error),
                      physical_steps=env.physical_steps if env is not None and hasattr(env,'physical_steps') else 0)
        if partial:save_run(target/'partial_trace.json.gz',{'trace':partial,'termination':'INCOMPLETE_ERROR',
                                                          'probe_events':controller.probe_events,
                                                          'probe_trace':controller.probe_trace})
        dump(target/'results_index.json',status)
        raise


if __name__=='__main__':main()
