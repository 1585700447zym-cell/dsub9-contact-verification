"""Freeze an explicitly unqualified offline candidate, never issue admission."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from small_bound_profile import ROOT,REG,REG_SEAL,registration,outer_contract,profile_digest,read,sha,digest

EXECUTION_FILES=['small_bound_profile.py','small_bound_session.py','small_bound_learning.py','run_small_bound_pilot.py']


def write(p,v):
    import json
    p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')


def source_proof():
    r=registration();pins={**r['source_seals'],'small_boundary_registration_20261007':REG_SEAL};counts={}
    for name,pin in pins.items():
        folder=OUT.parent/name
        if sha(folder/'delivery_manifest.json')!=pin:raise ValueError('Old delivery seal changed: '+name)
        files=read(folder/'delivery_manifest.json')['files'];counts[name]=len(files)
        for rel,m in files.items():
            if sha(folder/rel)!=m['sha256'] or (folder/rel).stat().st_size!=m['bytes']:raise ValueError('Old evidence changed: '+name+'/'+rel)
    pc6=read(OUT.parent/'v4_learning_requalification_20261006/configuration.json');inputs=pc6['input_sha256']
    for rel,pin in inputs.items():
        if sha(ROOT/rel)!=pin:raise ValueError('Common input changed: '+rel)
    return dict(sealed_manifest_pins=pins,sealed_files=counts,production_inputs=inputs,
        old_sealed_file_count=sum(counts.values()),production_input_count=len(inputs),common_key=r['common_key'],
        old_model_sha256=sha(OUT.parent/'v4_learning_requalification_20261006/model.xml'),
        inherited_evaluation=r['inherited_evaluation'],runtime_reference=pc6.get('runtime',pc6.get('runtime_proof')),
        runtime_revalidated=False)


def main():
    if (OUT/'delivery_manifest.json').exists():raise RuntimeError('Sealed candidate; do not regenerate')
    r=registration();proof=source_proof();contract=outer_contract()
    write(OUT/'source_bindings.json',proof)
    candidate=dict(version='pc12_small_bound_offline_candidate_v1',status='OFFLINE_CANDIDATE_NOT_ADMITTED',
        training_admitted=False,execution_authorized=False,numeric_verified=False,
        runtime_backend_implemented=False,runtime_backend_verified=False,
        physical_preflight_verified=False,automatic_tracking='PAUSED',outer_contract=contract,
        profile_sha256=profile_digest(contract),registration_sha256=sha(REG/'draft_contract.json'),
        common_key=r['common_key'],source_bindings_sha256=digest(proof),
        execution_code_sha256={(OUT/name).relative_to(ROOT).as_posix():sha(OUT/name) for name in EXECUTION_FILES},
        limits={k:v for k,v in r['proposals'].items() if k!='attempts'},
        actual=dict(new_dynamics=0,new_physical_substeps=0,new_network_predictions=0,
            new_optimizer_batches=0,new_published_transitions=0,new_learner_constructions=0,cumulative_dynamic=208),
        next_gate='Complete numerical integration harness and separately authorize <=4 synthetic update transactions / <=32 test-state forwards; no dynamics or formal training in that gate',
        non_claims=['No actual full checkpoint saved/read/restored','No runnable physical backend yet',
                    'No numeric zero-origin fingerprints remeasured','No training or B.2/C acceptance'])
    write(OUT/'qualification_candidate.json',candidate)
    print('UNQUALIFIED OFFLINE CANDIDATE',proof['old_sealed_file_count'],'old files /',proof['production_input_count'],'shared inputs unchanged')


if __name__=='__main__':main()
