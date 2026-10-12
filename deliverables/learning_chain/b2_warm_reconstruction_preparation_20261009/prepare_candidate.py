"""Prepare immutable source pins and an unsigned request, using standard library only."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
from joint_contract import read,write,sha,digest,learning_config
from gate_contract import LIMITS,ROLE_LIMITS,WHOLE_WALL_S,READER_WALL_S,verify_sources
KIT=OUT.parent/'b2_joint_sac_preparation_20261009';OLD=OUT.parent/'b2_joint_sac_execution_20261009'
REPAIR=OUT.parent/'b2_joint_io_repair_20261009'
CODE=['bounded_io.py','phase_deadline.py','supervised.py','windows_job.py','joint_contract.py','recovery_audit.py',
    'gate_contract.py','numeric_state.py','gate_worker.py','run_gate.py']

def main():
    if (OUT/'delivery_manifest.json').exists() or (OUT/'future_claims').exists():raise PermissionError('Frozen or claimed candidate')
    spec=read(OUT/'input_spec.json');binding=read(KIT/'source_binding.json')
    paths=[OUT/n for n in CODE]+[OUT/'input_spec.json',REPAIR/'delivery_manifest.json',REPAIR/'recovery_assessment.json',OLD/'delivery_manifest.json']
    paths += [Path(spec[k]) for k in ('zero_manifest','zero_state','source_closure','source_summary','probe_archive')]
    paths += [Path(s[k]) for s in spec['warmup'] for k in ('archive','receipt')]
    for path in paths:binding['files'][str(path.resolve())]=sha(path)
    binding['purpose']='standalone_archived_warm_state_verification_only'
    verify_sources(binding);write(OUT/'source_binding.json',binding)
    candidate=dict(version='b2_warm_restore_candidate_v1',stage_id='B2-SCOPE-15',status='PREPARED_NOT_AUTHORIZED',
        numeric_verified=False,training_admitted=False,limits=LIMITS,role_limits=ROLE_LIMITS,
        whole_wall_s=WHOLE_WALL_S,reader_wall_s=READER_WALL_S,source_binding_sha256=sha(OUT/'source_binding.json'),
        input_spec_sha256=digest(spec),config_sha256=digest(learning_config()),code_sha256={n:sha(OUT/n) for n in CODE})
    write(OUT/'candidate.json',candidate)
    write(OUT/'authorization_request.json',dict(status='NOT_AUTHORIZED',explicit_user_authorized=False,
        candidate_sha256=digest(candidate),binding_sha256=sha(OUT/'source_binding.json'),limits=LIMITS,
        whole_wall_s=WHOLE_WALL_S,reader_wall_s=READER_WALL_S,cumulative_before=245,
        operations='parent: original zero load, four archived rebuilds, save; reader: saved load, four rebuilds, live restore; one deterministic probe per role',
        no_retry=True,old_run_remains_closed=True,training_admitted=False,automatic_tracking='PAUSED'))
    print('Prepared unsigned candidate; bound files='+str(len(binding['files'])))

if __name__=='__main__':main()
