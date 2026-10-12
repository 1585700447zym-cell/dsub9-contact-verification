"""Prepare immutable source pins and an unsigned request, using standard library only."""
from pathlib import Path
import ast,importlib.abc,sys
OUT=Path(__file__).resolve().parent;ROOT=OUT.parents[2];sys.path.insert(0,str(OUT))
from joint_contract import read,write,sha,digest,learning_config
from gate_contract import LIMITS,ROLE_LIMITS,WHOLE_WALL_S,READER_WALL_S,verify_sources
from gate_worker import NoPhysics
from import_graph import collect_graph,check_guard
KIT=OUT.parent/'b2_joint_sac_preparation_20261009';OLD=OUT.parent/'b2_joint_sac_execution_20261009'
REPAIR=OUT.parent/'b2_joint_io_repair_20261009'
PREV=OUT.parent/'b2_warm_reconstruction_preparation_20261009';FAILED=OUT.parent/'b2_warm_reconstruction_execution_20261009'
CODE=['bounded_io.py','phase_deadline.py','supervised.py','windows_job.py','joint_contract.py','recovery_audit.py',
    'gate_contract.py','numeric_state.py','gate_worker.py','run_gate.py','import_graph.py']

def main():
    if (OUT/'delivery_manifest.json').exists() or (OUT/'future_claims').exists():raise PermissionError('Frozen or claimed candidate')
    spec=read(OUT/'input_spec.json');binding=read(KIT/'source_binding.json')
    graph=collect_graph(ROOT,OUT,['numeric_state','gate_worker','run_gate']);targets=check_guard(graph,NoPhysics())
    safety=ROOT/'tools/dynamics/safety.py';tree=ast.parse(safety.read_text(encoding='utf8'))
    imports=[]
    for node in ast.walk(tree):
        if isinstance(node,ast.Import):imports.extend(n.name for n in node.names)
        elif isinstance(node,ast.ImportFrom):imports.append(node.module)
    if sorted(imports)!=['__future__','numpy','numpy.typing']:raise ValueError('Helper imports changed')
    for node in tree.body:
        if not (isinstance(node,(ast.Import,ast.ImportFrom,ast.FunctionDef)) or
            isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str)):
            raise ValueError('Unexpected helper module-level execution')
    if sha(safety)!=binding['files'][str(safety)]:raise ValueError('Unreviewed pure helper')
    old_tree=ast.parse((PREV/'gate_worker.py').read_text(encoding='utf8'));old_class=next(n for n in old_tree.body if isinstance(n,ast.ClassDef) and n.name=='NoPhysics')
    ns=dict(importlib=importlib);exec(compile(ast.Module(body=[old_class],type_ignores=[]),str(PREV/'gate_worker.py'),'exec'),ns)
    old_rejections=[]
    for name in targets:
        try:ns['NoPhysics']().find_spec(name)
        except PermissionError:old_rejections.append(name)
    if old_rejections!=['tools.dynamics.safety']:raise ValueError('Unexpected prior graph incompatibility')
    write(OUT/'import_audit.json',dict(stage_id='B2-SCOPE-17',status='STATIC_REPOSITORY_IMPORT_COMPATIBILITY_CHECKED',graph=graph,
        exact_exception=dict(module='tools.dynamics.safety',path=str(safety),sha256=sha(safety),imports=imports),
        old_guard_rejections=old_rejections,new_guard_rejections=[],runtime_import_verified=False,numeric_restore_verified=False,
        limitations='No third-party import execution or recursive third-party analysis; deferred imports are recorded, not assumed executed. Dynamic import analysis covers recognized direct __import__/importlib.import_module calls and explicit import aliases, not arbitrary callable assignment/data flow. The live guard remains authoritative.'))
    paths=[OUT/n for n in CODE]+[OUT/'input_spec.json',OUT/'import_audit.json',REPAIR/'delivery_manifest.json',REPAIR/'recovery_assessment.json',OLD/'delivery_manifest.json',
        PREV/'delivery_manifest.json',FAILED/'delivery_manifest.json',FAILED/'authorization_closure.json',FAILED/'failure_diagnosis.json']
    paths += [Path(spec[k]) for k in ('zero_manifest','zero_state','source_closure','source_summary','probe_archive')]
    paths += [Path(s[k]) for s in spec['warmup'] for k in ('archive','receipt')]
    for path in paths:binding['files'][str(path.resolve())]=sha(path)
    binding['purpose']='standalone_archived_warm_state_verification_only'
    verify_sources(binding);write(OUT/'source_binding.json',binding)
    candidate=dict(version='b2_warm_restore_candidate_v1',stage_id='B2-SCOPE-17',status='PREPARED_NOT_AUTHORIZED',
        numeric_verified=False,training_admitted=False,limits=LIMITS,role_limits=ROLE_LIMITS,
        whole_wall_s=WHOLE_WALL_S,reader_wall_s=READER_WALL_S,source_binding_sha256=sha(OUT/'source_binding.json'),
        input_spec_sha256=digest(spec),config_sha256=digest(learning_config()),code_sha256={n:sha(OUT/n) for n in CODE},
        import_audit_sha256=sha(OUT/'import_audit.json'),supersedes_failed_candidate=digest(read(PREV/'candidate.json')))
    write(OUT/'candidate.json',candidate)
    write(OUT/'authorization_request.json',dict(status='NOT_AUTHORIZED',explicit_user_authorized=False,
        candidate_sha256=digest(candidate),binding_sha256=sha(OUT/'source_binding.json'),limits=LIMITS,
        whole_wall_s=WHOLE_WALL_S,reader_wall_s=READER_WALL_S,cumulative_before=245,
        operations='parent: original zero load, four archived rebuilds, save; reader: saved load, four rebuilds, live restore; one deterministic probe per role',
        no_retry=True,old_run_remains_closed=True,training_admitted=False,automatic_tracking='PAUSED'))
    print('Prepared unsigned candidate; bound files='+str(len(binding['files'])))

if __name__=='__main__':main()
