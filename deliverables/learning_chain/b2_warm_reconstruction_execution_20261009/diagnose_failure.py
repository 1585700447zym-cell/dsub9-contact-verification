"""Stdlib-only reproduction of the import refusal and evidence audit; never rerun the gate."""
from pathlib import Path
import ast,json,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
KIT=HERE.parent/'b2_warm_reconstruction_preparation_20261009';sys.path.insert(0,str(KIT))
from joint_contract import read,write,sha
from gate_worker import NoPhysics

def main():
    if (HERE/'failure_diagnosis.json').exists():raise FileExistsError('Keep diagnostic attempt')
    counter=read(HERE/'counter.json');closure=read(HERE/'authorization_closure.json');supervisor=read(HERE/'supervisor.supervisor.json')
    assert counter['status']=='CLOSED' and closure['status']=='CLOSED_ERROR'
    assert closure['counter_closed'] and closure['unused_closed'] and closure['no_retry']
    assert supervisor['process_exit_confirmed'] and supervisor['owned_launcher_exit_confirmed'] and supervisor['go_issued']
    assert supervisor['returncode']==1 and not supervisor['deadline_hit']
    assert all(v==0 for v in counter['attempted'].values()) and counter['unused_closed']==counter['limits']
    assert counter['roles']['parent']['claimed'] and not counter['roles']['reader']['claimed']
    assert not any((HERE/name).exists() for name in ('checkpoint','reader_reply.json','reader_request.json','assessment.json'))
    trace=(HERE/'supervisor.log').read_text(encoding='utf8')
    assert 'from tools.dynamics.safety import limit_command' in trace and 'Physical backend forbidden in restore gate' in trace
    paths=[KIT/'gate_worker.py',KIT/'numeric_state.py',ROOT/'tools/learning/v4_sac.py',ROOT/'tools/learning/audited_replay.py',ROOT/'tools/learning/action.py',ROOT/'tools/dynamics/safety.py']
    binding=read(KIT/'source_binding.json')
    for path in paths:assert sha(path)==binding['files'][str(path.resolve())]
    trees={str(p):ast.parse(p.read_text(encoding='utf8')) for p in paths}
    def has_from(path,module,name,level=0):
        return any(isinstance(n,ast.ImportFrom) and n.module==module and n.level==level and any(a.name==name for a in n.names) for n in ast.walk(trees[str(path)]))
    assert has_from(paths[1],'tools.learning.v4_sac','V4Updater')
    assert has_from(paths[2],'audited_replay','ReplayBatch',1)
    assert has_from(paths[3],'action','normalized_action',1)
    assert has_from(paths[4],'tools.dynamics.safety','limit_command')
    imports=[]
    for node in ast.walk(trees[str(paths[5])]):
        if isinstance(node,ast.Import):imports.extend(n.name for n in node.names)
        elif isinstance(node,ast.ImportFrom):imports.append(node.module)
    assert sorted(imports)==['__future__','numpy','numpy.typing']
    assert all(isinstance(n,(ast.Expr,ast.Import,ast.ImportFrom,ast.FunctionDef)) for n in trees[str(paths[5])].body)
    # Execute only the already-sealed standard-library predicate, not its blocked dependency.
    probes={}
    for name in ('tools.dynamics.safety','tools.dynamics.cartesian','mujoco','tools.learning.environment','tools.learning.v4_sac'):
        try:NoPhysics().find_spec(name);probes[name]='ALLOW'
        except PermissionError as exc:probes[name]='DENY: '+str(exc)
    assert probes['tools.dynamics.safety'].startswith('DENY') and probes['tools.learning.v4_sac']=='ALLOW'
    forbidden=[k for k in sys.modules if k.split('.')[0] in ('numpy','torch','mujoco','stable_baselines3')]
    assert not forbidden
    result=dict(stage_id='B2-SCOPE-16',status='CONFIRMED_IMPORT_GUARD_FALSE_POSITIVE',numeric_execution_status='CLOSED_ERROR',
        direct_cause='NoPhysics rejects every tools.dynamics.* module, including the pure NumPy safety helper imported by action.py',
        dependency_chain=['numeric_state','tools.learning.v4_sac','tools.learning.audited_replay','tools.learning.action','tools.dynamics.safety'],
        safety_helper_imports=imports,guard_probes=probes,source_pins={str(p):sha(p) for p in paths},
        runtime_import_started=True,actual_operations=counter['attempted'],reader_started=False,checkpoint_created=False,
        numeric_restore_verified=False,training_admitted=False,cumulative_dynamic=245,
        process_exit_confirmed=True,no_retry=True,automatic_tracking='PAUSED',diagnostic_forbidden_imports=forbidden,
        coverage_gap='Previous offline tests checked guard refusal but omitted compatibility of its real transitive learning imports',
        secondary_warning='Matplotlib user-cache write warning preceded the traceback; final failure is the explicit NoPhysics PermissionError',
        recommended_next='Offline narrow the import guard to admit only audited pure numerical helpers, test the real transitive dependency graph, preserve all old seals; do not rerun this closed grant')
    write(HERE/'failure_diagnosis.json',result)
    print(json.dumps(dict(status=result['status'],operations=result['actual_operations'],process_exit_confirmed=True,forbidden_imports=forbidden),ensure_ascii=False))

if __name__=='__main__':main()
