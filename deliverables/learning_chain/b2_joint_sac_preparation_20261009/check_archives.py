"""Read-only common/pose/zero-action regression on four old raw archives."""
from pathlib import Path
import ast
import gzip
import json
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from joint_contract import ROOT,COMMON,read,sha,write,case_kwargs,training_cases,check_initial_pose,digest


def analyze():
    old=OUT.parent/'b2_rebound_execution_20261008'
    runner=OUT.parent/'b2_preflight_rebound_20261008'
    binding=read(runner/'candidate_binding.json')
    current=read(OUT/'source_binding.json');common=read(OUT/'configuration.json')['common']
    shared={p:h for p,h in binding['files'].items() if p in current['files']}
    for p,h in shared.items():
        if current['files'][p]!=h or sha(p)!=h:raise ValueError('Baseline source drift: '+p)
    if sha(COMMON/'model.xml')!=sha(OUT/'model.xml'):raise ValueError('Model differs')
    rows=[]
    for case in training_cases():
        path=old/'run'/(case['id']+'_zero.json.gz');audit=read(path.with_name(case['id']+'_zero.audit.json'))
        if sha(path)!=audit['archive_sha256'] or audit['binding_sha256']!=sha(runner/'candidate_binding.json'):raise ValueError('Unpinned baseline')
        raw=json.loads(gzip.decompress(path.read_bytes()))
        if raw['simulation_case']!=case_kwargs(case):raise ValueError('Different baseline pose')
        check_initial_pose(case,raw['initial'])
        if raw['parameters']!=dict(dynamic_config=common['dynamic_config'],guard_config=common['guard_config']):raise ValueError('Different common physical parameters')
        from_case=dict(raw['spec']['case']);from_case.pop('script_sign')
        if from_case!=case or raw['spec']['arm']!='zero' or raw['spec']['network_policy'] is not False:raise ValueError('Baseline is not joint zero residual')
        if raw['initial']['time_s']!=0 or not raw['outcome']['simulation_valid'] or not raw['outcome']['physical_stopped']:raise ValueError('Baseline lifecycle/time mismatch')
        if raw['outcome']['task_outcome']!='FULL_SUCCESS':raise ValueError('Unexpected baseline outcome')
        rows.append(dict(case_id=case['id'],archive=str(path.relative_to(ROOT)),archive_sha256=sha(path),
            task_time_s=raw['task_end_time_s'],outcome=raw['outcome'],peaks=raw['peaks'],pose_verified=True,
            common_parameters_equal=True,role='reused_development_zero_residual_reference_not_F0',replay_publications=0))
    return dict(stage_id='B2-SCOPE-12',shared_bound_files=len(shared),model_equal=True,rows=rows,
        baseline_reuse='ACCEPTED_FOR_DEVELOPMENT_CONTEXT',primary_comparison='new matched F2000 versus new F0',
        comparison_limit='Different archive layout/session wrappers are not claimed byte-identical; same preserved controller factory, environment, finish criteria, pose and runtime sources. Old B2 references are contextual, not independent tests.',
        new_physics=0,new_learning=0)


if __name__=='__main__':
    result=analyze();write(OUT/'baseline_equivalence.json',result);print('Read four real archives; common and exact poses match; replay publication zero.')
