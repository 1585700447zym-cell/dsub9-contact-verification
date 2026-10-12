"""File-only binding and ungranted request. Never imports torch/native modules."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from numeric_contract import (ROOT,PC12,PC12_SEAL,LIMITS,read,sha,write,digest,profile_contract,profile_pin,verify_runtime_files)


def source_proof():
    # Read PC12's immutable stored proof; validate every old member independently.
    if sha(PC12/'delivery_manifest.json')!=PC12_SEAL:raise ValueError('PC12 seal changed')
    previous=read(PC12/'source_bindings.json');pins={**previous['sealed_manifest_pins'],PC12.name:PC12_SEAL};counts={}
    for name,pin in pins.items():
        folder=OUT.parent/name
        if sha(folder/'delivery_manifest.json')!=pin:raise ValueError('Old seal changed')
        files=read(folder/'delivery_manifest.json')['files'];counts[name]=len(files)
        for rel,m in files.items():
            if sha(folder/rel)!=m['sha256'] or (folder/rel).stat().st_size!=m['bytes']:raise ValueError('Old member changed: '+name+'/'+rel)
    for rel,pin in previous['production_inputs'].items():
        if sha(ROOT/rel)!=pin:raise ValueError('Original shared input changed')
    pc6=read(OUT.parent/'v4_learning_requalification_20261006/configuration.json')
    return dict(seal_pins=pins,sealed_files=counts,old_files=sum(counts.values()),production_inputs=previous['production_inputs'],
        shared_input_count=len(previous['production_inputs']),runtime=pc6['learning_runtime'],
        model_sha256=previous['old_model_sha256'],common_key=previous['common_key'])


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Already sealed; do not regenerate')
    proof=source_proof();runtime=proof['runtime']
    env=read(ROOT/'deliverables/residual_interface/learning_tensor_20260924/environment.json')
    torch_root=Path(env['package_paths']['torch']).parent
    pins={str(torch_root/'lib'/name):pin for name,pin in runtime['torch_dll_sha256'].items()}
    pins.update(runtime['native']['dll_sha256'])
    lock=ROOT/'deliverables/residual_interface/learning_tensor_20260924/requirements.lock.txt'
    if sha(lock)!=runtime['lock_sha256']:raise ValueError('Learning dependency lock changed')
    pins[str(lock)]=runtime['lock_sha256'];pins[runtime['executable']]=sha(runtime['executable'])
    package_paths={name:env['package_paths'][name] for name in ('torch','stable_baselines3','gymnasium')}
    for path in package_paths.values():pins[path]=sha(path)
    env_path=ROOT/'deliverables/residual_interface/learning_tensor_20260924/environment.json'
    pins[str(env_path)]=sha(env_path)
    verify_runtime_files(pins)
    code={p.relative_to(ROOT).as_posix():sha(p) for p in (OUT/'numeric_contract.py',OUT/'synthetic_data.py',OUT/'numeric_worker.py')}
    hot={**code}
    for rel,pin in proof['production_inputs'].items():
        if rel.startswith('tools/learning/') and rel.endswith('.py'):hot[rel]=pin
    for name in ('small_bound_profile.py','small_bound_learning.py','small_bound_session.py'):hot[(PC12/name).relative_to(ROOT).as_posix()]=sha(PC12/name)
    contract=profile_contract()
    candidate=dict(version='pc13_numeric_candidate_v1',status='PREPARED_NOT_AUTHORIZED',training_admitted=False,
        dynamic_authorized=False,numeric_authorized=False,numeric_verified=False,automatic_tracking='PAUSED',
        outer_contract=contract,profile_sha256=profile_pin(),limits=LIMITS,source_proof_sha256=digest(proof),
        execution_source_sha256=code,hot_source_sha256=hot,runtime=runtime,runtime_file_sha256=pins,runtime_package_paths=package_paths,
        runtime_files_verified_without_import=len(pins),
        future_work=dict(parent_update_batches=3,reader_update_batches=1,parent_test_states=16,reader_test_states=16,
            new_synthetic_episodes=5,new_synthetic_rows=400,new_physical_episodes=0,formal_update_batches=0,
            comparison='full tensor/Adam/replay/terminal-boundary/RNG and next sampling state, excluding measured wall_s only',
            auxiliary_costs='measure all original model constructions and CPU tensor reads separately; transaction-internal SAC passes are part of each update'),
        actual_at_preparation=dict(learner_constructions=0,tensor_checkpoint_reads=0,network_forwards=0,
            synthetic_update_batches=0,synthetic_rows_published=0,dynamic_episodes=0,physical_substeps=0,cumulative_dynamic=208),
        physical_backend_implemented=False,physical_training_admitted=False)
    write(OUT/'source_bindings.json',proof);write(OUT/'numeric_candidate.json',candidate)
    request=dict(version='pc13_numeric_authorization_v1',status='REQUEST_NOT_GRANTED',explicit_user_authorized=False,
        scope='synthetic_numeric_only',candidate_sha256=digest(candidate),profile_sha256=profile_pin(),limits=LIMITS,prior_dynamic=208)
    write(OUT/'authorization_request.json',request)
    print('UNAUTHORIZED NUMERIC KIT',proof['old_files'],'old files,',proof['shared_input_count'],'inputs;',len(pins),'runtime file pins; actual computations0')


if __name__=='__main__':main()
