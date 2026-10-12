"""Pure source/runtime binding and immutable authorization request. No grant is created."""
from pathlib import Path
import ast
import sys
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from joint_contract import ROOT,read,write,sha,digest,LIMITS
from prepare import replace_once


def supervision_sources():
    old=OUT.parent/'b2_joint_admission_preflight_20261009'
    text=(old/'deadline_guard.py').read_text(encoding='utf-8')
    text=replace_once(text,'from scope_contract import ROOT,read,sha\nfrom execution_contract import write','from joint_contract import ROOT,read,sha,write')
    text=replace_once(text,'def bounded_process(command,base,timeout,*,job_factory=Job):','def bounded_process(command,base,timeout,*,job_factory=Job,phase_file=None):')
    text=replace_once(text,"            while child.poll() is None or job.active():\n                if time.monotonic()-began>=timeout:raise TimeoutError('Hard supervised deadline')",
        "            while child.poll() is None or job.active():\n                if time.monotonic()-began>=timeout:raise TimeoutError('Hard supervised deadline')\n                if phase_file is not None and Path(phase_file).exists():\n                    phase=read(phase_file)\n                    if type(phase.get('limit_s')) is not int or phase['limit_s'] not in (1200,1800) or time.time()-phase['started']>=phase['limit_s']:\n                        raise TimeoutError('Hard phase deadline')")
    return {'supervised.py':text,'windows_job.py':(old/'windows_job.py').read_text(encoding='utf-8')}


def main():
    if (OUT/'delivery_manifest.json').exists():raise PermissionError('Sealed candidate')
    for name,text in supervision_sources().items():ast.parse(text);(OUT/name).write_text(text,encoding='utf-8')
    old=read(OUT.parent/'b2_joint_admission_preflight_20261009/candidate_binding.json')
    numeric=read(ROOT/'deliverables/paper_comparison/small_boundary_numeric_gate_20261007/numeric_candidate.json')
    files=dict(old['files']);files.update(numeric['runtime_file_sha256'])
    for p in OUT.glob('*.py'):files[str(p)]=sha(p)
    for name in ('candidate.json','configuration.json','model.xml','adapter_provenance.json'):files[str(OUT/name)]=sha(OUT/name)
    for name in ('candidate.json','recommended_gate_v2.json','coverage_comparison.json'):
        p=OUT.parent/'b2_joint_coverage_review_20261009'/name
        if p.exists():files[str(p)]=sha(p)
    write(OUT/'source_binding.json',dict(version='b2_joint_sac_binding_v1',implementation_directory=str(OUT),
        files=files,inventories=old['inventories'],executable=old['executable'],runtime=numeric['runtime'],
        runtime_package_paths=numeric['runtime_package_paths'],old_scope_binding_sha256=sha(OUT.parent/'b2_joint_admission_preflight_20261009/candidate_binding.json')))
    write(OUT/'authorization_request.json',dict(version='b2_joint_sac_grant_v1',status='UNAPPROVED',explicit_user_authorized=False,
        candidate_sha256=digest(read(OUT/'candidate.json')),binding_sha256=sha(OUT/'source_binding.json'),limits=LIMITS,
        cumulative_before=237,human_evidence=None,purpose='One new joint F50 development pilot, including zero/final independent full-state restore; old grants stay closed'))
    print('Frozen '+str(len(files))+' inputs; explicit execution request remains UNAPPROVED.')


if __name__=='__main__':main()
