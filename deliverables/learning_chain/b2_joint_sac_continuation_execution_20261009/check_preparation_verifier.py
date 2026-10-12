"""Preserve the historical preparation-checker's post-execution limitation."""
import json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
KIT=HERE.parent/'b2_joint_sac_continuation_preparation_20261009'
if __name__=='__main__':
    log=HERE/'historical_checker_after_claim.log'
    if log.exists():raise FileExistsError('Preserve first diagnostic')
    result=subprocess.run([sys.executable,'-I','-X','utf8','-B',str(KIT/'verify_delivery.py'),'--preflight'],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
    log.write_text(result.stdout+result.stderr,encoding='utf8')
    print(json.dumps(dict(returncode=result.returncode,expected_preparation_only_assertion='candidate not executed' in result.stderr,
                          numeric_operations=0),ensure_ascii=False))
    if result.returncode==0 or 'candidate not executed' not in result.stderr:raise AssertionError('Unexpected diagnosis')
