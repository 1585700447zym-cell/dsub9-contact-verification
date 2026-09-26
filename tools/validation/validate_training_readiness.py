"""Preserved, prespecified 256-segment timestep audit; never edits old runs."""
import argparse
import copy
import hashlib
import json
from dataclasses import asdict
import numpy as np
import mujoco

from tools.dynamics.cartesian import CartesianEnvironment, DynamicConfig
from tools.validation.validate_dynamic_actuator import scenarios, run_episode, compare, sources
from tools.validation.run_b1_baseline import cases, dump
from tools.validation.run_b2_search import save_run
from tools.validation.run_contact_cases import ROOT
from tools.validation.diagnose_v1_applicability import fingerprint

OUT = ROOT/'deliverables/baseline_training_readiness'
PROTOCOL = OUT/'数值复验协议.md'
REFERENCE = ROOT/'deliverables/dynamic_actuator_v1/n256_dt0.0002.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_hashes(root, expected):
    for name, digest in expected.items():
        if sha(root/name) != digest:
            raise ValueError('Input changed: '+name)


def new_target(base, tag):
    if not tag or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in tag):
        raise ValueError('Use a new simple tag')
    target = base/tag
    if target.exists():
        raise FileExistsError('Preserve previous attempts; choose a new tag')
    return target


def compare_pair(a, b):
    for key in ('name', 'case', 'command_world', 'drive_duration_s'):
        if a[key] != b[key]:
            raise ValueError('Unfair comparison: '+key)
    ma, mb = copy.deepcopy(a['metadata']), copy.deepcopy(b['metadata'])
    for m in (ma, mb):
        m['config'].pop('timestep')
        if 'effective_options' in m:
            m['effective_options'].pop('timestep')
    if ma != mb:
        raise ValueError('Unfair comparison: metadata')
    return compare(a, b)


def check_run(r):
    stop = r['stop_check_0p2']
    rows = np.array([x['position_m']+x['quaternion_wxyz']+x['velocity_world']+
                     x['contact_wrench_M']+x['contact_wrench_G'] for x in r['trace']])
    bad = ('INVALID_SIMULATION', 'INVALID_PENETRATION', 'SIMULATION_ERROR', 'OUT_OF_BOUNDS')
    return {'case':r['name'], 'timestep':r['metadata']['config']['timestep'],
            'finite_valid':bool(np.isfinite(rows).all() and not any(e['reason'] in bad for e in r['events'])),
            'stop_linear_speed_m_s':None if stop is None else float(np.linalg.norm(stop['velocity_world'][:3])),
            'stop_angular_speed_rad_s':None if stop is None else float(np.linalg.norm(stop['velocity_world'][3:])),
            'stop_linear_pass':bool(stop is not None and np.linalg.norm(stop['velocity_world'][:3])<1e-5),
            'stop_angular_pass':bool(stop is not None and np.linalg.norm(stop['velocity_world'][3:])<=.001),
            'effort_bounded':bool(max(r['peaks']['drive_force_components_N'])<=r['metadata']['config']['force_limit_N']+1e-12 and
                                  max(r['peaks']['drive_torque_components_Nm'])<=r['metadata']['config']['torque_limit_Nm']+1e-12),
            'recovery':r['recovery'], 'recovery_z_change_m':r['final']['position_m'][2]-r['stopped']['position_m'][2],
            'contact_observed':r['first_contact'] is not None}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--tag', required=True)
    args=parser.parse_args();target=new_target(OUT,args.tag)
    historic=json.loads(REFERENCE.read_text(encoding='utf-8'))
    manifest=json.loads((REFERENCE.parent/'delivery_manifest.json').read_text(encoding='utf-8'))
    reference_name=REFERENCE.relative_to(ROOT).as_posix()
    verify_hashes(ROOT,{reference_name:manifest[reference_name]})
    verify_hashes(ROOT,historic['source_sha256'])
    if fingerprint()!=historic['historical_source_sha256']:
        raise ValueError('Historical model inputs changed')
    code={**sources(), 'tools/validation/validate_training_readiness.py':sha(ROOT/'tools/validation/validate_training_readiness.py'),
          'tools/validation/run_b1_baseline.py':sha(ROOT/'tools/validation/run_b1_baseline.py'),
          'tools/validation/run_b2_search.py':sha(ROOT/'tools/validation/run_b2_search.py')}
    protected={reference_name:sha(REFERENCE),PROTOCOL.relative_to(ROOT).as_posix():sha(PROTOCOL),**code}
    target.mkdir(parents=True);(target/'runs').mkdir()
    for rel in code:
        dest=target/'source_snapshot'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes((ROOT/rel).read_bytes())
    (target/'数值复验协议.md').write_bytes(PROTOCOL.read_bytes())
    index={'status':'RUNNING','mujoco_version':mujoco.__version__,'source_sha256':code,
           'historical_source_sha256':historic['historical_source_sha256'],'protected_inputs':protected,
           'reference_file':reference_name,'reference_sha256':sha(REFERENCE),'runs':[],'comparisons':[]}
    dump(target/'results_index.json',index)
    partial=[];env=None
    try:
        env=CartesianEnvironment(DynamicConfig(timestep=.0001),256)
        original=env.step
        def capture(command):
            row=original(command);partial.append(dict(row));return row
        env.step=capture
        all_runs=list(historic['runs'])
        def execute(name,case,duration,recover):
            partial.clear()
            print('START',name,'dt',env.config.timestep,flush=True)
            r=run_episode(env,name,case,duration,recover)
            relative=f'runs/{name}_dt{env.config.timestep}.json.gz'
            save_run(target/relative,r)
            entry={'file':relative,'sha256':sha(target/relative),'checks':check_run(r),'wall_seconds':r['timing']['wall_seconds']}
            index['runs'].append(entry);all_runs.append(r);dump(target/'results_index.json',index)
            print(json.dumps(entry,ensure_ascii=False),flush=True)
            return r
        expected=scenarios()
        if [r['name'] for r in historic['runs']] != [s[0] for s in expected]:
            raise ValueError('Historical case order changed')
        for ref,(name,case,duration,recover) in zip(historic['runs'],expected):
            if ref['case']!=asdict(case):raise ValueError('Historical case changed')
            r=execute(name,case,duration,recover)
            result=compare_pair(ref,r);index['comparisons'].append(result)
            dump(target/'results_index.json',index);print('COMPARISON',json.dumps(result),flush=True)
        y=next(c for c in cases() if c.name=='y_offset_neg_100um')
        fine=execute('lateral_y',y,1.2,True)
        env=CartesianEnvironment(DynamicConfig(timestep=.0002),256);original=env.step;env.step=capture
        coarse=execute('lateral_y',y,1.2,True)
        index['comparisons'].append(compare_pair(coarse,fine))
        verify_hashes(ROOT,protected)
        if fingerprint()!=historic['historical_source_sha256']:raise ValueError('Historical inputs changed during run')
        checks=[check_run(r) for r in all_runs]
        index['all_run_checks']=checks
        index['status']='COMPLETE'
        index['timestep_pass']=all(c['pass'] for c in index['comparisons'])
        index['short_run_checks_pass']=all(all(c[k] for k in ('finite_valid','stop_linear_pass','stop_angular_pass','effort_bounded')) for c in checks)
        index['verdict']='LOCAL_SHORT_VALIDATION_PASS' if index['timestep_pass'] and index['short_run_checks_pass'] else 'BLOCKED_REQUIRES_REVIEW'
        dump(target/'results_index.json',index)
        print('VERDICT',index['verdict'],flush=True)
    except (Exception,KeyboardInterrupt) as error:
        index.update(status='ERROR',error=repr(error))
        if partial:save_run(target/'partial_trace.json.gz',{'trace':partial,'termination':'INCOMPLETE_ERROR'})
        dump(target/'results_index.json',index)
        raise


if __name__=='__main__':main()
