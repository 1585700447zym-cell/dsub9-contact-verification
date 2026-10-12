"""Offline-only binding preparation. No engine imports; never issues a grant."""
from pathlib import Path
import sys
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT))
from scope_contract import ROOT,proposal,sha,read,PROPOSAL_PIN
from execution_contract import verify_files,write


def prepare():
    if (OUT/'delivery_manifest.json').exists():raise PermissionError('Sealed preparation cannot be refreshed')
    c=proposal()
    numerical_pins=ROOT/'deliverables/paper_comparison/small_boundary_numeric_execution_20261008/prior_source_bindings.json'
    prior=read(numerical_pins)
    files={str(ROOT/n):h for n,h in prior['production_inputs'].items()}
    files[str(numerical_pins)]=sha(numerical_pins)
    for key in ('configuration','model'):
        files[str(ROOT/c['parent'][key])]=c['parent'][key+'_sha256']
    files[str(OUT/'candidate.json')]=PROPOSAL_PIN
    for name in ('b2_scope_audit_20261008','b2_pose_scope_preflight_20261008',
                 'b2_pose_scope_execution_20261008','b2_scope_auditor_fix_20261008'):
        path=OUT.parent/name/'delivery_manifest.json';files[str(path)]=sha(path)
    for name in ('run/ledger.json','authorization_closure.json'):
        path=OUT.parent/'b2_pose_scope_execution_20261008'/name;files[str(path)]=sha(path)
    for path in OUT.glob('*.py'):files[str(path)]=sha(path)
    runtime=ROOT/'deliverables/learning_chain/b2_repaired_cycle_v2_20260928/runtime.json'
    admission=read(runtime.with_name('admission.json'))
    files[str(runtime)]=admission['runtime_record_sha256'];files[str(runtime.with_name('admission.json'))]=sha(runtime.with_name('admission.json'))
    record=read(runtime);package=Path(record['module_file']).parent.parent
    files.update({str(package/name):pin for name,pin in record['files'].items()})
    env=ROOT/'tmp/learning_cpu_20260924';executable=env/'Scripts/python.exe'
    files[str(executable)]=sha(executable);files[str(env/'pyvenv.cfg')]=sha(env/'pyvenv.cfg')
    for path in (Path('D:/KEYANRUJIAN/python.exe'),Path('D:/KEYANRUJIAN/python313.dll')):files[str(path)]=sha(path)
    inventories={str(package/'mujoco'):sorted(Path(n).relative_to('mujoco').as_posix() for n in record['files'])}
    for directory in (env/'Lib/site-packages/numpy',env/'Lib/site-packages/numpy.libs'):
        paths=sorted(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc')
        if not paths:raise ValueError('Missing registered numerical package: '+str(directory))
        inventories[str(directory)]=sorted(p.relative_to(directory).as_posix() for p in paths)
        files.update({str(p):sha(p) for p in paths})
    verify_files(files)
    binding=dict(version='b2_pose_scope_binding_v1',status='PREPARED_NOT_AUTHORIZED',proposal_sha256=PROPOSAL_PIN,
        implementation_directory=str(OUT),
        scope_key=c['draft_scope_key'],parent_common_key=c['parent']['common_key'],executable=str(executable),
        files=files,inventories=inventories,training_admitted=False,static_authorized=False,dynamic_authorized=False,
        original_scope_qualification_inherited=False)
    write(OUT/'candidate_binding.json',binding)
    request=dict(version='b2_pose_scope_authorization_request_v1',status='REQUESTED_NOT_AUTHORIZED',explicit_user_approval=False,
        authorization_text=None,binding_sha256=sha(OUT/'candidate_binding.json'),proposal_sha256=PROPOSAL_PIN,
        scope_key=c['draft_scope_key'],limits=c['proposed_limits'],cumulative_before=c['cumulative_dynamic'],automatic_tracking='PAUSED',
        purpose='B.2 eight development pose points: nine static resets then at most sixteen zero/script rollouts',
        no_retry=True,close_old_budgets=True,training_admitted=False,
        grant_instructions='Only after explicit human approval, create a new b2_pose_scope_grant_v1 OPEN record with approval evidence and exact pins/limits. This request itself is rejected by the runner.')
    write(OUT/'authorization_request.json',request)
    print(dict(files=len(files),binding_sha256=request['binding_sha256'],physics=0,learning=0))


if __name__=='__main__':prepare()
