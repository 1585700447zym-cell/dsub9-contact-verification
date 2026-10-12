"""Exercise CLI refusal with request/old grant; no grant is created or consumed."""
from pathlib import Path
import json
import subprocess
import sys
import uuid
OUT=Path(__file__).resolve().parent;sys.path.insert(0,str(OUT))
from scope_contract import ROOT,sha,read
from execution_contract import write
def main():
    reports=[];binding=read(OUT/'candidate_binding.json')
    for name,grant in [('request',OUT/'authorization_request.json'),('old_grant',OUT.parent/'b2_rebound_execution_20261008/grant.json')]:
        target=ROOT/'tmp/b2_joint_unauthorized_probes'/uuid.uuid4().hex
        result=subprocess.run([binding['executable'],'-I','-X','utf8','-B',str(OUT/'run_preflight.py'),
            '--execute','--grant',str(grant),'--grant-pin',sha(grant),'--output',str(target)],cwd=ROOT,
            capture_output=True,text=True,encoding='utf-8',timeout=45)
        if result.returncode==0 or 'Explicit new scope grant' not in result.stderr:raise AssertionError(result.stderr)
        if target.exists() or (OUT/'claims').exists():raise AssertionError('Unauthorized side effect')
        reports.append(dict(input=name,input_sha256=sha(grant),returncode=result.returncode,
            refused_before_claim=True,output_created=False,last_error=result.stderr.strip().splitlines()[-1]))
    write(OUT/'unauthorized_cli.json',dict(status='PASS',probes=reports,new_physics=0))
    print(json.dumps(dict(status='PASS',refused=len(reports),claims_created=0,new_physics=0)))
if __name__=='__main__':main()
